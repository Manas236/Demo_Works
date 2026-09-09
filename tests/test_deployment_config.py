"""
tests/test_deployment_config.py — the deployment surface, 9 September 2026
=========================================================================

Three subjects, and each of them is a thing that is invisible until it is wrong
on a real server:

1. **The session cookie flags** (`auth.session_cookie_config`). `Secure` was
   Flask's default of `False` and nothing set it, so the cookie `auth.enforce()`
   trusts travelled in clear. The flags are now env-driven — and the test that
   matters is not that they can be set but that a **typo cannot silently turn
   `Secure` off**, because that failure has no symptom.

2. **The bind address** (`app.DEV_HOST` / `app._dev_port`). Specifically that
   the dev server's default host is **not** `0.0.0.0`: `app.py` runs Werkzeug
   with `debug=True`, and a debug console on a public interface is a remote
   shell.

3. **`.env.example` hygiene.** It shipped `SECRET_KEY=qms-demo-secret-2024` —
   the literal `tests/test_auth.py` scans every root module's AST to keep out of
   the code. `cp .env.example .env` is step one of ABOUT.md's own cold-start
   block, so the value the code refuses to contain was being handed back through
   a tracked file, and `auth.secret_key_warning()` cannot see it: a published
   placeholder is indistinguishable from a real key from inside the process.

⚠ **This file sets environment variables through `monkeypatch`**, which undoes
  them per test. `auth.session_cookie_config()` re-reads `os.getenv` on every
  call and caches nothing, which is what makes that work — the same property
  `attachment.root()` is written for and for the same reason.
"""

import ast
import pathlib
import re

import pytest

import app as app_module
import auth

REPO = pathlib.Path(__file__).resolve().parent.parent


# ── 1. Session cookie flags ────────────────────────────────────────────────

def test_the_defaults_are_the_local_dev_values_and_secure_is_off():
    """
    Not an aspiration — the documented default, asserted.

    `Secure=True` by default would break `python app.py`: a browser never sends
    a Secure cookie over `http://127.0.0.1`, so the operator cannot sign in and
    nothing tells them why. A default that breaks the documented dev command is
    a default somebody deletes, taking the production value with it.
    """
    config, problems = auth.session_cookie_config()
    assert problems == []
    assert config["SESSION_COOKIE_SECURE"] is False
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_samesite_is_set_at_all_which_flask_does_not_do():
    """Flask's own default is `None` — the flag absent from the cookie. This app
    is single-origin, so `Lax` costs nothing and removes the cross-site POST."""
    assert auth.SESSION_COOKIE_DEFAULTS["SESSION_COOKIE_SAMESITE"] == "Lax"


@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
    ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
])
def test_secure_reads_the_usual_spellings_of_a_boolean(monkeypatch, raw, expected):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", raw)
    config, problems = auth.session_cookie_config()
    assert config["SESSION_COOKIE_SECURE"] is expected
    assert problems == []


def test_a_blank_value_means_unset_rather_than_false(monkeypatch):
    """`SESSION_COOKIE_SECURE=` in a `.env` is somebody who has not decided yet,
    not somebody asking for it to be off. It takes the default and says nothing —
    the default already IS off, so this is about not reporting a false problem."""
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "   ")
    config, problems = auth.session_cookie_config()
    assert config["SESSION_COOKIE_SECURE"] is False
    assert problems == []


def test_an_unparseable_secure_is_REPORTED_and_never_silently_true(monkeypatch):
    """
    ⚠ **The test this file exists for.**

    `SESSION_COOKIE_SECURE=ture` must not resolve to `True` by truthiness, and
    it must not resolve to `False` in silence either. It takes the documented
    default and **names the variable and the value**, because this is the one
    misconfiguration on the list with no observable symptom: the app works, the
    operator is satisfied, and the session token is in clear on the wire.
    """
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "ture")
    config, problems = auth.session_cookie_config()
    assert config["SESSION_COOKIE_SECURE"] is False, (
        "an unparseable value became True by truthiness")
    assert len(problems) == 1
    assert "SESSION_COOKIE_SECURE" in problems[0]
    assert "ture" in problems[0]


def test_an_unparseable_httponly_is_reported_too(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_HTTPONLY", "sometimes")
    config, problems = auth.session_cookie_config()
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert any("SESSION_COOKIE_HTTPONLY" in p for p in problems)


@pytest.mark.parametrize("raw,expected", [
    ("Lax", "Lax"), ("lax", "Lax"), ("STRICT", "Strict"), ("none", "None"),
])
def test_samesite_is_accepted_case_insensitively_and_normalised(monkeypatch, raw, expected):
    """Normalised rather than passed through: Werkzeug writes the value into the
    header as given, and `samesite=LAX` is not what the RFC spells."""
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", raw)
    config, problems = auth.session_cookie_config()
    assert config["SESSION_COOKIE_SAMESITE"] == expected
    assert problems == []


def test_a_nonsense_samesite_is_reported_and_falls_back(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "Laxx")
    config, problems = auth.session_cookie_config()
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert any("SESSION_COOKIE_SAMESITE" in p for p in problems)


def test_config_is_always_usable_even_when_everything_is_wrong(monkeypatch):
    """
    `address._validate()`'s contract — always return data — held here for the
    same reason: a deployment whose environment is mistyped must be *told*, not
    prevented from booting. An app that will not start gets its guard deleted.
    """
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "banana")
    monkeypatch.setenv("SESSION_COOKIE_HTTPONLY", "banana")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "banana")
    config, problems = auth.session_cookie_config()
    assert config == auth.SESSION_COOKIE_DEFAULTS
    assert len(problems) == 3


def test_install_actually_applies_the_flags_to_the_app(monkeypatch):
    """
    The half that makes the rest matter. `session_cookie_config()` returning the
    right dict is worth nothing if `install()` does not put it on the app — so
    this asserts through a real Flask app rather than through the helper.
    """
    import flask
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "Strict")
    probe = flask.Flask(__name__)
    auth.install(probe)
    assert probe.config["SESSION_COOKIE_SECURE"] is True
    assert probe.config["SESSION_COOKIE_SAMESITE"] == "Strict"
    assert probe.config["SESSION_COOKIE_HTTPONLY"] is True


def test_the_live_app_carries_the_flags():
    """The app the suite actually drives has them set, rather than Flask's
    defaults. `SESSION_COOKIE_SAMESITE` is the tell: Flask leaves it None."""
    assert app_module.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app_module.app.config["SESSION_COOKIE_HTTPONLY"] is True


# ── 2. The bind address ────────────────────────────────────────────────────

def test_the_dev_server_does_not_default_to_every_interface():
    """
    ⚠ `app.py` runs `app.run(debug=True, ...)`. Werkzeug's debugger offers an
    interactive console on a traceback, so binding the dev server to `0.0.0.0`
    by default would publish a remote shell on the LAN. Production uses
    `wsgi.py`, which sets no debug flag.
    """
    assert app_module.DEV_HOST == "127.0.0.1"


@pytest.mark.parametrize("raw,expected", [
    ("5000", 5000), ("8080", 8080), (" 8000 ", 8000), ("1", 1), ("65535", 65535),
])
def test_the_bind_port_parses(raw, expected):
    assert app_module._dev_port(raw) == expected


@pytest.mark.parametrize("raw", ["", "eighty", "0", "-1", "65536", "80.5", None])
def test_a_bad_bind_port_falls_back_to_5000_and_never_raises(raw):
    """A mistyped port must not be a traceback at startup: the operator is
    looking at a terminal, and `ValueError: invalid literal for int()` does not
    tell them which variable they got wrong."""
    assert app_module._dev_port(raw) == 5000


# ── 3. .env.example hygiene ────────────────────────────────────────────────

ENV_EXAMPLE = REPO / ".env.example"


def test_env_example_exists_and_is_tracked():
    assert ENV_EXAMPLE.is_file()


def test_env_example_does_not_hand_back_the_published_demo_secret_key():
    """
    ⚠ The hole this closes, stated as the assertion.

    `tests/test_auth.py::test_the_demo_secret_key_is_gone_from_the_codebase`
    scans every root module's AST for `qms-demo-secret-2024` — and
    `.env.example` is not a module, so it escaped. It shipped that literal as
    the value of `SECRET_KEY`, and ABOUT.md's cold-start block says
    `cp .env.example .env`, so every install built by following the
    documentation signed its session cookies with a key published in this
    repository's history.

    It is silent, too, which is what makes it worth a test rather than a note:
    `auth.secret_key_warning()` fires only for the `file` and `minted` sources.
    A key that came from `SECRET_KEY` is treated as deployment-supplied, because
    from inside the process a published placeholder looks exactly like a real
    key.
    """
    text = ENV_EXAMPLE.read_text(encoding="utf8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() in ("SECRET_KEY", "SAMRUDDHI_SECRET_KEY"):
            assert value.strip() == "", (
                f"{name.strip()} in .env.example has the value {value.strip()!r}. "
                f"It must be blank: anything here is copied into a real .env by "
                f"the documented cold-start step, and a key supplied that way "
                f"raises no warning at all.")


def test_env_example_carries_no_value_that_looks_like_a_real_secret():
    """
    The general form, so the next variable to arrive is covered too.

    Every assignment in the file must be blank, a safe local-dev literal, or a
    documented default. A long high-entropy value is the shape of a real secret
    and this file is tracked.
    """
    allowed_nonblank = {
        "DB_ENABLED", "DB_STRICT", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER",
        "SAMRUDDHI_HOST", "SAMRUDDHI_PORT",
        "SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
    }
    for line in ENV_EXAMPLE.read_text(encoding="utf8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name, value = name.strip(), value.strip()
        if not value:
            continue
        assert name in allowed_nonblank, (
            f"{name} has a non-blank value in the TRACKED file .env.example. "
            f"Either it is a safe local-dev default — add it to the list in "
            f"this test and say why — or it is a secret and must not be here.")
        assert len(value) < 32, f"{name}={value!r} is long enough to be a real secret"


def test_env_example_names_every_variable_the_app_reads():
    """
    ⚠ **The drift guard.** A variable added to the code and not to
    `.env.example` is a variable the next deployment does not know exists — and
    `docs/ENVIRONMENT.md` is generated from neither, so nothing else catches it.

    Read from the AST of the root modules rather than by string search, so a
    name in a docstring does not count as support for it.
    """
    found = set()
    for path in sorted(REPO.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = ""
            if isinstance(node.func, ast.Attribute):
                target = node.func.attr
            if target not in ("getenv",):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                found.add(node.args[0].value)

    text = ENV_EXAMPLE.read_text(encoding="utf8")
    # Variables deliberately absent from .env.example, each with its reason.
    exempt = {
        # Two-name fallbacks: the bare names exist only so a host that already
        # sets them is honoured. Documenting both in .env.example would invite
        # somebody to set both and wonder which wins.
        "HOST", "PORT", "SECRET_KEY",
        # The override is commented out in the file on purpose — an operator who
        # uncomments it has read why they should not.
        "SAMRUDDHI_ALLOW_MULTIPROCESS",
        # Diagnostics only; there is no reason for a deployment to set it.
        "SAMRUDDHI_LOCK_FILE",
    }
    missing = sorted(
        name for name in found - exempt
        if not re.search(rf"^\s*#?\s*{re.escape(name)}=", text, re.M))
    assert not missing, (
        f"{missing} are read by the application and appear nowhere in "
        f".env.example. Add them there and to docs/ENVIRONMENT.md, or add them "
        f"to this test's `exempt` set with the reason.")


def test_samruddhi_secret_key_is_the_name_the_code_prefers():
    """Guards the documentation against the code: `.env.example` explains
    `SECRET_KEY`, so the two-step order in `auth` must still put the
    `SAMRUDDHI_`-prefixed name first."""
    source = (REPO / "auth.py").read_text(encoding="utf8")
    assert 'for var in ("SAMRUDDHI_SECRET_KEY", "SECRET_KEY")' in source
