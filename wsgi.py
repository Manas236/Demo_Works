"""
wsgi.py — the production entry point, and the thing that stops a silent disaster
===============================================================================

    gunicorn --workers 1 --bind 0.0.0.0:8000 wsgi:application

`app.py` is the **development** entry point: its `__main__` block runs Werkzeug
with `debug=True`, which must never face a network. This module is the other
one. It imports the same `app` object, adds nothing to it, and exists almost
entirely for the guard below.


THE FAILURE THIS FILE EXISTS TO PREVENT
---------------------------------------
**`store.STORE` is one dict in ONE process's RAM.** `db.sync()` re-serialises
the whole of it after every request and writes back whatever changed
(ABOUT.md §4). Nothing in that design is shared between processes.

So two workers is not "a bit of cache staleness". It is **two complete,
divergent copies of the entire application state**, each convinced it is
authoritative, each overwriting the other's rows on whichever request happens to
land last:

    worker A  loads BOQ at boot        worker B  loads BOQ at boot
    request 1 -> A: add RA bill        request 2 -> B: edit the BOQ
    A.sync()  writes A's whole world   B.sync() writes B's whole world
                                       ...and B's world has no RA bill in it.

The bill is gone. No exception was raised, no log line was written, nothing is
red. Somebody finds out three weeks later when a claim they are sure they raised
is not in the register. **This is the single deadliest deployment mistake this
architecture makes available, and its native failure mode is silence** — which
is why the response here is to refuse to run rather than to warn.

⚠ **The real fix is one process. This is a guard, not a licence.** Making STORE
  safe across workers means moving state out of RAM, which is a rewrite of
  `db.py` and of the assumption every blueprint is built on. Until that happens,
  one worker is not a tuning choice; it is a correctness requirement.


TWO GUARDS, BECAUSE GUNICORN HAS TWO MODES
------------------------------------------
One check is not enough, and the gap between them is easy to miss:

1. **An exclusive OS lock, taken at import.** Without `--preload`, gunicorn
   forks first and each worker imports this module for itself, so the second
   worker's lock attempt fails and it refuses to boot. An OS advisory lock is
   used rather than a pidfile because the kernel drops it when the process dies —
   a crash cannot leave a stale file that bricks the next start.

2. **A per-request PID check.** With `--preload`, gunicorn imports this module
   **once** in the arbiter and then forks. On POSIX the lock lives on the open
   file description and is *inherited*, so guard 1 sees nothing wrong and both
   children run. `_PID_AT_IMPORT` is what catches that: a process whose pid is
   not the one that took the lock is a fork, and it refuses every request.

Guard 1 alone would have shipped a hole exactly the size of `--preload`.


WHY IT IS NOT IN app.py
-----------------------
Two reasons, and both are constraints rather than preferences:

* **The dev flow.** `python app.py` runs the reloader, which is deliberately
  *two* processes — a stat-watcher and the worker it restarts. An import-time
  single-process lock in `app.py` would make the documented dev command fail on
  the second process, every time.
* **The test suite.** `tests/conftest.py` imports `app`, and pytest may run it
  in more than one process. A guard there would have to be disabled for tests,
  and a guard that is off where the code is exercised is not a guard.

Importing `app` stays free of all of this. Only the production path pays.
"""

import os
import pathlib
import sys
import tempfile

# Importing `app` boots persistence, seeds the company identity, registers every
# blueprint, installs identity and closes the app with `auth.enforce()`. It is
# the same object `python app.py` serves — this module deliberately does not
# configure it differently, because a production-only code path is a path nobody
# has tested.
from app import app as application  # noqa: F401  (gunicorn looks this name up)

import auth
import db

# The pid that took the lock. Any other pid serving a request is a fork — see
# guard 2 in the header.
_PID_AT_IMPORT = os.getpid()

# Set to a truthy value ONLY to test the refusal, or by an operator who has
# genuinely made STORE shared and knows why this file is wrong. It warns every
# time; it is not a quiet escape hatch.
_OVERRIDE = "SAMRUDDHI_ALLOW_MULTIPROCESS"

# Kept at module scope for the life of the process. An OS advisory lock is
# released when the handle closes, so letting this be garbage collected would
# quietly release the lock and admit a second worker.
_lock_handle = None


def lock_path() -> pathlib.Path:
    """
    Where the single-worker lock lives.

    **The system temp directory, not the checkout.** A read-only deployment
    directory is normal and a lock file that cannot be created would turn this
    guard into a boot failure on a correct single-worker install.

    **Keyed by the database it is guarding**, so two deployments on one box —
    staging and production against different schemas — do not fight over one
    lock and report each other as a second worker.
    """
    override = (os.getenv("SAMRUDDHI_LOCK_FILE") or "").strip()
    if override:
        return pathlib.Path(override)
    key = f"{db.CONFIG['host']}-{db.CONFIG['port']}-{db.CONFIG['name']}"
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in key)
    return pathlib.Path(tempfile.gettempdir()) / f"samruddhi-qms-{safe}.lock"


def _take_exclusive_lock(path: pathlib.Path):
    """
    `(handle, None)` when this process got the lock, `(None, reason)` when it did
    not. Never raises — the caller turns the reason into the banner.

    Advisory, non-blocking, and released by the kernel on exit. `msvcrt` on
    Windows and `fcntl` on everything else; both lock one byte, which is all an
    advisory lock needs.
    """
    try:
        handle = open(path, "a+")
    except OSError as exc:
        # Cannot create the lock file at all. Do NOT refuse to boot over this —
        # a correct single-worker install must not be stopped by a permissions
        # problem in a temp directory. Guard 2 still stands.
        return None, f"could not open {path} ({exc})"

    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        held_by = ""
        try:
            handle.seek(0)
            held_by = handle.read(64).strip()
        except OSError:
            pass
        handle.close()
        return None, ("another process already holds it"
                      + (f" (pid {held_by})" if held_by else ""))

    try:
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
    except OSError:
        pass
    return handle, None


def _banner(lines) -> str:
    """A refusal nobody can scroll past. 74 columns, the width db.py's uses."""
    bar = "=" * 74
    body = "\n".join(f"  {line}" for line in lines)
    return f"\n{bar}\n{body}\n{bar}\n"


def refusal_text(reason: str) -> str:
    """The multi-process refusal, as text, so a test can read it without dying."""
    return _banner([
        # ASCII only, deliberately. This banner is read in a Windows console
        # (cp1252) as often as in a Linux log, and an em-dash prints as a
        # replacement character there - which makes the loudest line in the file
        # look like a different kind of fault.
        "REFUSING TO START - THIS APPLICATION CANNOT RUN MORE THAN ONE WORKER.",
        "",
        f"Reason: {reason}.",
        "",
        "store.STORE is one dict in ONE process's RAM, and db.sync() writes the",
        "whole of it back after every request. A second worker is a second,",
        "divergent copy of the entire application state. The two overwrite each",
        "other's records SILENTLY - no exception, no log line, nothing red. You",
        "find out weeks later when a bill somebody raised is not in the register.",
        "",
        "Run exactly one worker:",
        "",
        "    gunicorn --workers 1 --bind 0.0.0.0:8000 wsgi:application",
        "",
        "If you need more throughput, run one worker with more THREADS",
        "(--threads 4). Threads share one STORE; processes do not.",
        "",
        f"To override - and you almost certainly must not - set {_OVERRIDE}=1.",
    ])


def _refuse(reason: str) -> None:
    """Print the banner and stop this process. stderr, for the reason db.py gives."""
    print(refusal_text(reason), file=sys.stderr, flush=True)
    # RuntimeError rather than SystemExit: gunicorn logs "Worker failed to boot"
    # with the traceback attached, so the reason reaches the log and not only the
    # console of whoever happened to be watching.
    raise RuntimeError(f"refusing to run multi-process: {reason}")


def _startup_report() -> str:
    """
    What a correct production boot looks like, so it can be recognised.

    Deliberately names the **four** things that are wrong on a default install
    and right on a configured one. A banner that only says "started" tells you
    the process is up, which was never the question.
    """
    secure = application.config.get("SESSION_COOKIE_SECURE")
    lines = [
        "Samruddhi Fire QMS - production entry point (wsgi.py)",
        "",
        f"  single worker  : OK - pid {os.getpid()} holds {lock_path()}",
        f"  database       : {db.status()}",
        f"  DB_STRICT      : {db.CONFIG['strict']}"
        + ("" if db.CONFIG["strict"] else "   <-- set DB_STRICT=true in production"),
        f"  attachments    : {_attachment_root()}",
        f"  session cookie : Secure={secure} "
        f"HttpOnly={application.config.get('SESSION_COOKIE_HTTPONLY')} "
        f"SameSite={application.config.get('SESSION_COOKIE_SAMESITE')}"
        + ("" if secure else "\n                   <-- SESSION_COOKIE_SECURE is FALSE; "
                            "the session token travels in clear. Set it to true."),
        f"  users on file  : {len(auth.users())}"
        + (" <-- none: every URL redirects to /setup until one exists"
           if not auth.users() else ""),
    ]
    return _banner(lines)


def _attachment_root() -> str:
    """Reported rather than assumed — `attachment.root()` re-reads the env."""
    try:
        import attachment
        return str(attachment.root())
    except Exception as exc:          # pragma: no cover - diagnostics only
        return f"(could not resolve: {exc})"


# ── Guard 1: the import-time exclusive lock ──────────────────────────────────
if os.getenv(_OVERRIDE, "").strip():
    print(_banner([
        f"WARNING: {_OVERRIDE} is set. The single-worker guard is OFF.",
        "",
        "If this application is running more than one worker, its records are",
        "being corrupted right now, silently. See wsgi.py's header.",
    ]), file=sys.stderr, flush=True)
else:
    _lock_handle, _why = _take_exclusive_lock(lock_path())
    if _lock_handle is None:
        if "already holds it" in (_why or ""):
            _refuse(f"the single-worker lock is held - {_why}")
        else:
            # Could not create the lock file. Say so and carry on: guard 2 below
            # still catches the fork case, and refusing here would stop a correct
            # install over a temp-directory permission.
            print(f"  * WARNING: single-worker lock unavailable - {_why}. "
                  f"Guard 2 (pid check) still applies.",
                  file=sys.stderr, flush=True)


# ── Guard 2: the per-request pid check, for gunicorn --preload ───────────────
_real_wsgi_app = application.wsgi_app


def _single_process_wsgi(environ, start_response):
    """
    Refuse a request served by a process that is not the one that imported this
    module. With `--preload` that is the only signal there is — see the header.

    One `os.getpid()` per request. The cost is a syscall; what it buys is that
    `--preload --workers 2` fails visibly instead of quietly writing wrong data.
    """
    if os.getpid() != _PID_AT_IMPORT and not os.getenv(_OVERRIDE, "").strip():
        reason = (f"this worker is pid {os.getpid()}, forked from the process "
                  f"that imported wsgi.py (pid {_PID_AT_IMPORT}) - that is "
                  f"gunicorn --preload with more than one worker")
        print(refusal_text(reason), file=sys.stderr, flush=True)
        body = (b"This deployment is running more than one worker. The "
                b"application has refused the request rather than corrupt its "
                b"records. See the server log, and wsgi.py.\n")
        start_response("503 Service Unavailable",
                       [("Content-Type", "text/plain; charset=utf-8"),
                        ("Content-Length", str(len(body)))])
        return [body]
    return _real_wsgi_app(environ, start_response)


application.wsgi_app = _single_process_wsgi

# Printed once, at import, by the one process that got through both guards.
print(_startup_report(), file=sys.stderr, flush=True)
