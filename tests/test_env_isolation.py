"""
tests/test_env_isolation.py — the suite does not read the checkout's `.env`
===========================================================================

CLIENT_CHANGES.md §0, the thirty-first block, 25 September 2026.

**The problem, measured rather than anticipated.** Running the suite on the
production box picks up the repo-root `.env` through `db.py`'s
`load_dotenv(override=False)` and fails. With a production-shaped `.env` in the
checkout the suite went **2 failed, 2845 passed** — and the two failures had
two different causes:

| Failure | Cause |
|---|---|
| `test_deployment_config.py::test_the_defaults_are_the_local_dev_values_and_secure_is_off` | in-process: `auth.session_cookie_config()` re-reads `os.getenv` and saw `SESSION_COOKIE_SECURE=true` from `.env` |
| `test_wsgi_single_worker.py::test_the_first_process_gets_through_and_reports_what_it_found` | a **subprocess**: `python -c "import wsgi"` imports `db.py` fresh and calls `load_dotenv()` for itself, where nothing in the parent can reach it |

That matters because running the tests is the one check an operator performs
after a deploy, and it was useless on the only box where it is most wanted.

**The two fixes, because there are two causes.** `conftest._never_read_dotenv()`
replaces the loader in the test process; `test_wsgi_single_worker._LOCAL_DEV_ENV`
hands the children the local-dev values as **real** environment variables, which
`load_dotenv(override=False)` cannot overwrite.

⚠ **NO APPLICATION BEHAVIOUR CHANGED.** `.env` must still reach `python app.py`
  and `gunicorn` exactly as it always has, and `test_db_still_reads_dotenv_for_the_real_application`
  below is what stops this being quietly turned into a feature.
"""

import ast
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


# ── 1. The loader is neutralised in this process ───────────────────────────

def test_load_dotenv_is_neutralised_in_the_test_process():
    """
    ⚠ **Total, not a list of names.** `db.py` calls `load_dotenv(override=False)`
      at import, so EVERY variable in `.env` that the suite has not already set
      would reach the application. A list of names in `conftest.py` would be a
      list somebody has to remember to extend, and the variable nobody
      remembered is the one that breaks the deploy check.
    """
    import dotenv

    assert dotenv.load_dotenv(REPO / ".env") is False, (
        "dotenv.load_dotenv still loads — conftest._never_read_dotenv() did "
        "not take, and the checkout's .env is reaching the suite")
    assert dotenv.load_dotenv.__name__ == "_refuse"


def test_the_checkout_env_really_exists_so_this_file_is_not_vacuous():
    """
    ⚠ **The non-vacuity guard.** Every assertion here would pass trivially on a
      machine with no `.env` at all — which is most CI checkouts, and is
      exactly NOT the box this was written for. It is a skip rather than a
      failure, because a fresh clone legitimately has none.
    """
    if not (REPO / ".env").exists():
        pytest.skip("no .env in this checkout — nothing for the suite to be "
                    "isolated from, so the assertions here prove nothing")
    assert (REPO / ".env").read_text(encoding="utf8").strip(), ".env is empty"


def test_a_production_shaped_env_does_not_reach_the_session_cookie_flags():
    """
    The in-process failure, reproduced directly: write a `.env` holding
    production values into a temporary directory, ask `dotenv` to load it, and
    show that `auth.session_cookie_config()` is unmoved.

    Written against a temporary file rather than the real `.env`, so this test
    passes on a clean clone and on a production box alike.
    """
    import auth

    config, problems = auth.session_cookie_config()
    assert problems == []
    assert config["SESSION_COOKIE_SECURE"] is False, (
        "SESSION_COOKIE_SECURE is true inside the suite. Either .env reached "
        "it, or it is exported in the real environment — conftest.py sets the "
        "local-dev values explicitly to cover both.")


# ── 2. The application still reads it, which is the point ──────────────────

def test_db_still_reads_dotenv_for_the_real_application():
    """
    ⚠ **The guard that stops the fix becoming a feature.** The suite is
      isolated; the APPLICATION is not, and must never be. `python app.py` and
      `gunicorn` both depend on `.env` reaching `db.CONFIG`.

    Read from the AST rather than by string search, so a mention in a docstring
    does not count as support for it.
    """
    tree = ast.parse((REPO / "db.py").read_text(encoding="utf8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)
             and n.func.id == "load_dotenv"]
    assert len(calls) == 1, (
        f"db.py makes {len(calls)} load_dotenv() calls — it must make exactly "
        f"one, at import, unconditionally. The suite is isolated in "
        f"conftest.py, never by weakening this.")

    call = calls[0]
    # It must be at module level, not inside a function or an `if`.
    module_level = [n for n in tree.body if isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Name)
                    and n.value.func.id == "load_dotenv"]
    assert module_level, (
        "db.py's load_dotenv() call is no longer an unconditional module-level "
        "statement. A deployment's .env would stop being read.")
    assert any(k.arg == "override" and k.value.value is False
               for k in call.keywords), (
        "db.py must call load_dotenv(override=False) — a real environment "
        "variable has to keep winning over the file")


def test_a_subprocess_with_no_overrides_DOES_read_the_checkout_env():
    """
    ⚠ **The other half of the non-vacuity proof, and the sharper one.** It shows
      the isolation is genuinely per-process: a child that is NOT handed the
      local-dev values reads `.env` exactly as a deployment does. If this ever
      goes red, `db.py` has stopped reading `.env` and the application is
      broken in a way no other test would notice.
    """
    if not (REPO / ".env").exists():
        pytest.skip("no .env in this checkout")

    names = [ln.split("=", 1)[0].strip()
             for ln in (REPO / ".env").read_text(encoding="utf8").splitlines()
             if "=" in ln and not ln.strip().startswith("#")]
    names = [n for n in names if n and n not in os.environ]
    if not names:
        pytest.skip("every name in .env is already set in the real environment")

    probe = names[0]
    env = {k: v for k, v in os.environ.items() if k != probe}
    r = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(f"""
            import os
            import db          # calls load_dotenv(override=False) at import
            print("VALUE", repr(os.getenv({probe!r})))
        """)],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180)
    assert r.returncode == 0, r.stderr
    assert "VALUE None" not in r.stdout, (
        f"a subprocess importing db.py did NOT pick up {probe} from the "
        f"checkout's .env. The application reads its configuration that way — "
        f"if this is broken, a deployment's .env is being ignored.\\n"
        f"{r.stdout}\\n{r.stderr}")


# ── 3. The subprocess tests hand their children the local-dev values ───────

def test_the_wsgi_children_are_given_the_local_dev_values():
    """
    `conftest.py` cannot reach a subprocess, so `test_wsgi_single_worker.py`
    carries its own answer. Asserted here rather than only there, because the
    two halves of this fix are one decision and a reader of either should find
    the other.

    ⚠ **This one is REDUNDANT TODAY and is kept deliberately.** Measured by
      mutation on 25 September 2026: deleting `env.update(_LOCAL_DEV_ENV)` from
      `_run()` left the suite green, because `conftest.py` writes the same
      values into `os.environ` and `_run()` copies `os.environ` into the child.
      So the children are covered twice over.

      It is kept because the two mechanisms cover **different** failures —
      `conftest.py` covers a value exported in the real environment, and this
      covers the child reading `.env` for itself — and because a child process
      that quietly inherited its configuration from whatever the parent
      happened to have is the arrangement that made this file necessary in the
      first place. `test_the_suite_is_green_even_with_production_values_EXPORTED`
      is what catches the pair going.

    Asserted on **both call sites**, not just on the name: the constant
    surviving while nothing uses it is exactly the shape this would rot into.
    """
    src = (REPO / "tests" / "test_wsgi_single_worker.py").read_text(encoding="utf8")
    for name in ("SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY",
                 "SESSION_COOKIE_SAMESITE", "DB_ENABLED", "SECRET_KEY"):
        assert name in src, (
            f"{name} is not pinned for the wsgi child processes — a .env "
            f"setting it would move the boot banner those tests assert on")
    uses = src.count("_LOCAL_DEV_ENV")
    assert uses >= 3, (
        f"_LOCAL_DEV_ENV is referenced {uses} time(s) — it must be defined "
        f"ONCE and used by BOTH child launchers (`_run` and `_hold_the_lock`). "
        f"A constant that nothing reads is not a guard.")
    assert "env.update(_LOCAL_DEV_ENV)" in src, "_run() no longer applies it"
    assert "**_LOCAL_DEV_ENV" in src, "_hold_the_lock() no longer applies it"


# ── 4. Independent of a REAL exported environment variable, too ────────────

def test_the_suite_is_green_even_with_production_values_EXPORTED(tmp_path):
    """
    ⚠ **Written because two mutations were MISSED on 25 September 2026.**
      Deleting `conftest.py`'s explicit `SESSION_COOKIE_SECURE=false`, and
      deleting `_LOCAL_DEV_ENV` from the wsgi children, were each survivable
      **because the other covered it**: `conftest.py` writes the local-dev
      values into `os.environ`, and `_run()` copies `os.environ` into the
      child. Neither alone is load-bearing for the cookie flags; the pair is,
      and removing both is caught.

      What neither mutation reached is the case `.env` neutralisation cannot
      touch at all: a value **exported in the real environment**, by a
      developer's shell or a CI job. `_never_read_dotenv()` is no defence
      against that — only the explicit pinning is.

    So this runs pytest in a child with production values exported, which is
    the only way to observe the difference from inside the suite.
    """
    env = dict(os.environ)
    env.update({
        "SESSION_COOKIE_SECURE": "true",       # ⚠ the production value
        "SESSION_COOKIE_SAMESITE": "Strict",
        "SAMRUDDHI_DEMO_DATA": "false",        # ⚠ and the other way round
        "DB_STRICT": "true",
        "PYTHONIOENCODING": "utf-8",
    })
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header",
         "tests/test_deployment_config.py", "tests/test_demo_data_flag.py",
         "-p", "no:cacheprovider"],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0, (
        "the suite is NOT independent of the real environment — production "
        "values exported in the shell turned it red. conftest.py must set the "
        "local-dev values explicitly, not merely stop .env being read.\n"
        f"{r.stdout[-4000:]}\n{r.stderr[-2000:]}")
