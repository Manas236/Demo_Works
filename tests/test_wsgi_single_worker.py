"""
tests/test_wsgi_single_worker.py — the guard that stops a silent disaster
=========================================================================

`wsgi.py` refuses to run under more than one process, because `store.STORE` is
one dict in one process's RAM and `db.sync()` writes the whole of it back after
every request. Two workers is two divergent copies of the entire application
state overwriting each other **with no error at all** — see `wsgi.py`'s header
for the worked sequence.

A guard against a silent failure has to be tested harder than one against a
crash, because there is nothing to notice if it stops working.

⚠ **THIS FILE IMPORTS `wsgi` IN A SUBPROCESS, NEVER IN THE TEST PROCESS.**
  Importing it here would take the single-worker lock for the whole pytest run
  and wrap `app.wsgi_app` for every other test file in the session. Both guards
  are therefore exercised the way a deployment meets them: guard 1 by starting
  real processes, guard 2 through its pure function with the pid faked, because
  Windows has no `fork()` and the condition cannot be produced natively here.
"""

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


# ── helpers ────────────────────────────────────────────────────────────────

def _run(code: str, env_extra=None, timeout=120):
    """Run `code` in a subprocess with DB persistence OFF. Returns CompletedProcess."""
    env = dict(os.environ)
    # No MySQL: the guard is about processes, not about the database, and a test
    # that needed a live server would be skipped on the machine that matters.
    env["DB_ENABLED"] = "false"
    env["SECRET_KEY"] = "test-secret"
    env.pop("SAMRUDDHI_ALLOW_MULTIPROCESS", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace")


def _lock_for(tmp_path) -> str:
    return str(tmp_path / "worker.lock")


def _hold_the_lock(lock: str, env_extra=None):
    """
    A subprocess that takes the lock and keeps it, returned once it really has it.

    ⚠ **Read until the marker, never just the first line.** `db.init()` prints
    its own banner to stdout before anything here runs, so
    `stdout.readline()` returns *that* — which made four tests fail on the
    holder's startup noise rather than on the thing under test.
    """
    env = {**os.environ, "DB_ENABLED": "false", "SECRET_KEY": "test-secret",
           "SAMRUDDHI_LOCK_FILE": lock}
    env.pop("SAMRUDDHI_ALLOW_MULTIPROCESS", None)
    env.update(env_extra or {})
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import wsgi, time; print('HOLDING', flush=True); time.sleep(60)"],
        cwd=str(REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace")
    for _ in range(60):
        line = proc.stdout.readline()
        if not line:
            break
        if "HOLDING" in line:
            return proc
    proc.kill()
    proc.wait(timeout=30)
    raise AssertionError("the lock holder never reported HOLDING")


# ── 1. The module is importable and the entry point has the expected name ──

def test_gunicorn_can_find_the_application_callable(tmp_path):
    """
    `gunicorn ... wsgi:application` resolves that attribute by name. A rename
    would make the documented production command fail with nothing but
    `AppImportError`, so the name is pinned.
    """
    r = _run("""
        import wsgi
        print("CALLABLE", callable(wsgi.application))
        print("NAME", type(wsgi.application).__name__)
    """, {"SAMRUDDHI_LOCK_FILE": _lock_for(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "CALLABLE True" in r.stdout
    assert "NAME Flask" in r.stdout


def test_the_first_process_gets_through_and_reports_what_it_found(tmp_path):
    """The success path, and it has to stay noisy: the startup banner is how the
    operator tells a configured install from a default one."""
    r = _run("""
        import wsgi
        print("STARTED")
    """, {"SAMRUDDHI_LOCK_FILE": _lock_for(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "STARTED" in r.stdout
    assert "production entry point" in r.stderr
    assert "single worker  : OK" in r.stderr
    # The four things that are wrong on a default install are named, not implied.
    assert "SESSION_COOKIE_SECURE is FALSE" in r.stderr
    assert "DB_STRICT" in r.stderr


# ── 2. Guard 1: a second process is REFUSED ────────────────────────────────

def test_a_second_process_on_the_same_lock_is_refused(tmp_path):
    """
    ⚠ **The headline.** Two processes, one lock, and the second must not run.

    The first process is held alive while the second tries, because a lock
    released by the kernel on exit would otherwise make this test pass by
    accident — which is exactly the vacuous version of it.
    """
    lock = _lock_for(tmp_path)
    # Wait for the holder to actually have the lock, rather than sleeping and
    # hoping — a timing-dependent guard test is worse than none.
    holder = _hold_the_lock(lock)
    try:
        second = _run("""
            import wsgi
            print("SECOND GOT THROUGH")
        """, {"SAMRUDDHI_LOCK_FILE": lock})

        assert second.returncode != 0, (
            "a SECOND process imported wsgi.py successfully while the first held "
            "the lock. Two workers means two divergent copies of STORE "
            "overwriting each other silently.")
        assert "SECOND GOT THROUGH" not in second.stdout
        assert "CANNOT RUN MORE THAN ONE WORKER" in second.stderr
        assert "refusing to run multi-process" in (second.stderr + second.stdout)
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_the_refusal_tells_the_operator_what_to_run_instead(tmp_path):
    """
    A refusal that does not say what to do instead gets worked around, usually by
    deleting the thing that refused. INTRODUCTION.md §2: an error that says only
    "invalid" costs somebody an afternoon.
    """
    lock = _lock_for(tmp_path)
    holder = _hold_the_lock(lock)
    try:
        second = _run("import wsgi", {"SAMRUDDHI_LOCK_FILE": lock})
        text = second.stderr
        assert "--workers 1" in text, "the refusal does not name the right command"
        assert "threads" in text.lower(), "it does not offer the way to scale"
        assert "SAMRUDDHI_ALLOW_MULTIPROCESS" in text, "it hides its own override"
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_the_lock_is_released_when_the_process_dies(tmp_path):
    """
    An OS advisory lock rather than a pidfile, and this is the difference.

    A crashed worker must not leave a file that stops the next start — that turns
    a guard into an outage, and the first thing anybody does about an outage is
    remove the guard.
    """
    lock = _lock_for(tmp_path)
    first = _run("import wsgi; print('ONE')", {"SAMRUDDHI_LOCK_FILE": lock})
    assert first.returncode == 0, first.stderr
    second = _run("import wsgi; print('TWO')", {"SAMRUDDHI_LOCK_FILE": lock})
    assert second.returncode == 0, (
        "the lock outlived the process that held it, so a restart after a crash "
        f"would be refused forever. stderr: {second.stderr}")
    assert "TWO" in second.stdout


def test_two_different_databases_do_not_fight_over_one_lock(tmp_path):
    """
    The lock is keyed by host/port/schema, so staging and production on one box
    each get their own. Without this, the second deployment reports the first as
    a rogue worker and neither starts.
    """
    # No SAMRUDDHI_LOCK_FILE: the point is the DEFAULT path, which is keyed by
    # host/port/schema. TMPDIR/TEMP move tempfile.gettempdir() into tmp_path.
    holder = _hold_the_lock("", {"DB_NAME": "schema_one", "TMPDIR": str(tmp_path),
                                 "TEMP": str(tmp_path)})
    try:
        other = _run("import wsgi; print('OTHER SCHEMA OK')",
                     {"DB_NAME": "schema_two", "TMPDIR": str(tmp_path),
                      "TEMP": str(tmp_path)})
        assert other.returncode == 0, other.stderr
        assert "OTHER SCHEMA OK" in other.stdout
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_the_lock_path_is_outside_the_checkout_by_default(tmp_path):
    """
    A read-only deployment directory is normal, and a lock file that cannot be
    created must not be a boot failure on a correct single-worker install.
    """
    # `__file__` does not exist under `python -c`; cwd IS the repo (see _run).
    r = _run("""
        import pathlib, wsgi
        p = wsgi.lock_path()
        print("LOCK", p)
        print("INSIDE_REPO", str(p).startswith(str(pathlib.Path.cwd().resolve())))
    """)
    assert r.returncode == 0, r.stderr
    assert "INSIDE_REPO False" in r.stdout
    assert "samruddhi-qms-" in r.stdout


# ── 3. Guard 2: the fork case, which guard 1 cannot see ───────────────────

def test_a_forked_worker_is_refused_even_though_it_inherited_the_lock(tmp_path):
    """
    ⚠ **The hole guard 1 leaves, exactly the size of `gunicorn --preload`.**

    With `--preload` the module is imported once in the arbiter and the workers
    are forked. On POSIX an `flock` lives on the open file description and is
    *inherited*, so guard 1 sees nothing wrong and every child runs. The pid
    check is what catches it.

    Windows has no `fork()`, so the condition is produced by faking the recorded
    pid — which tests the decision rather than the platform, and the decision is
    the part that can be broken by an edit.
    """
    r = _run("""
        import wsgi
        # Pretend this process is a fork: the pid that imported the module was
        # somebody else. This is what a --preload child looks like.
        wsgi._PID_AT_IMPORT = -1

        status = {}
        def start_response(code, headers):
            status["code"] = code
            status["headers"] = dict(headers)

        body = b"".join(wsgi._single_process_wsgi(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/", "SERVER_NAME": "x",
             "SERVER_PORT": "80", "wsgi.url_scheme": "http", "QUERY_STRING": ""},
            start_response))
        print("STATUS", status["code"])
        print("BODY", body.decode())
    """, {"SAMRUDDHI_LOCK_FILE": _lock_for(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "STATUS 503 Service Unavailable" in r.stdout, (
        "a forked worker served the request. With gunicorn --preload that is two "
        "workers writing over each other with no error at all.")
    assert "more than one worker" in r.stdout
    assert "CANNOT RUN MORE THAN ONE WORKER" in r.stderr, (
        "the 503 was returned but nothing reached the log")


def test_the_owning_process_is_NOT_refused(tmp_path):
    """
    The other half of the control, and the reason the test above is evidence
    rather than a tautology. A guard that refused every request would pass the
    assertion above while breaking the application completely — so the same
    wrapper, in the process that really owns the lock, must serve normally.
    """
    r = _run("""
        import wsgi
        status = {}
        def start_response(code, headers):
            status["code"] = code
            return lambda b: None
        body = b"".join(wsgi._single_process_wsgi(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/", "SERVER_NAME": "x",
             "SERVER_PORT": "80", "wsgi.url_scheme": "http", "QUERY_STRING": ""},
            start_response))
        print("STATUS", status["code"])
        print("IS503", "503" in status["code"])
    """, {"SAMRUDDHI_LOCK_FILE": _lock_for(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "IS503 False" in r.stdout, (
        "the owning process was refused its own request — the guard is refusing "
        "everybody, which would pass the fork test for the wrong reason")


# ── 4. The override is loud, and it is the only way through ───────────────

def test_the_override_lets_a_second_process_run_but_says_so_every_time(tmp_path):
    """
    The escape hatch exists so the refusal can be tested and so an operator who
    has genuinely made STORE shared is not stuck. It must never be quiet: a
    silent override is the same failure as no guard, one environment variable
    later.
    """
    lock = _lock_for(tmp_path)
    holder = _hold_the_lock(lock)
    try:
        second = _run("import wsgi; print('THROUGH')",
                      {"SAMRUDDHI_LOCK_FILE": lock,
                       "SAMRUDDHI_ALLOW_MULTIPROCESS": "1"})
        assert second.returncode == 0, second.stderr
        assert "THROUGH" in second.stdout
        assert "the single-worker guard is OFF" in second.stderr.lower() or \
               "guard is OFF" in second.stderr
        assert "corrupted" in second.stderr
    finally:
        holder.kill()
        holder.wait(timeout=30)


# ── 5. It must not have changed the app the suite drives ──────────────────

def test_importing_app_does_not_take_a_lock_or_wrap_anything():
    """
    ⚠ **The constraint, asserted.** The guard must not break the dev flow or the
    suite, and both import `app`, not `wsgi`.

    `python app.py` runs the stat reloader, which is deliberately *two*
    processes; a lock in `app.py` would make the documented dev command fail
    every time. And a guard disabled for tests is a guard that is off wherever
    the code is exercised.
    """
    r = _run("""
        import app
        print("WSGI_APP", app.app.wsgi_app.__class__.__name__)
        import sys
        print("WSGI_IMPORTED", "wsgi" in sys.modules)
    """)
    assert r.returncode == 0, r.stderr
    assert "WSGI_IMPORTED False" in r.stdout, (
        "importing app pulled in wsgi.py, so the suite and the dev reloader are "
        "now subject to the single-worker lock")
    assert "_single_process_wsgi" not in r.stdout


def test_wsgi_adds_no_route_and_no_permission():
    """
    `auth.ROUTE_PERMISSIONS` is default-deny and `tests/test_access_control.py`
    fails on an unclassified endpoint. `wsgi.py` must stay a pure entry point —
    if it ever registers a route, that test is where it has to be declared.
    """
    r = _run("""
        import auth
        before = set(auth.ROUTE_PERMISSIONS)
        import wsgi
        after = set(auth.ROUTE_PERMISSIONS)
        print("NEW", sorted(after - before))
        print("RULES", sorted(
            r.endpoint for r in wsgi.application.url_map.iter_rules()
            if r.endpoint not in auth.ROUTE_PERMISSIONS))
    """, {"SAMRUDDHI_LOCK_FILE": "", "SAMRUDDHI_ALLOW_MULTIPROCESS": "1"})
    assert r.returncode == 0, r.stderr
    assert "NEW []" in r.stdout
    assert "RULES []" in r.stdout
