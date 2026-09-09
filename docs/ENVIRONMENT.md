# Environment variables — the complete list

> **This is the one list.** Every environment variable the application reads,
> what it defaults to, and which ones are mandatory in production.
>
> It is maintained by hand, and
> `tests/test_deployment_config.py::test_env_example_names_every_variable_the_app_reads`
> is what stops it drifting: that test reads the **AST** of every root module for
> `os.getenv(...)` calls and fails if a name appears in the code and not in
> [`.env.example`](../.env.example). Add a variable to the code, and you add it
> to `.env.example` and to this file in the same commit.
>
> ⚠ **Nothing secret belongs in a tracked file.** `.env.example` is tracked;
> `.env`, `secret_key.txt` and `backups/` are gitignored. Every value in
> `.env.example` is blank or a safe local-dev default, and a test asserts it.

**Measured on 9 September 2026**, against a brand new empty MySQL schema — the
first time this application had ever been started against one.

---

## How configuration is read

`db.py` calls `load_dotenv(override=False)` **once, at import**. Two
consequences, and both have bitten:

- **A real environment variable wins over `.env`.** That is what lets
  `tests/conftest.py` force `DB_ENABLED=false` before importing `app`, and what
  lets a deployment set values without editing a file.
- **`db.CONFIG` is built at import time.** Changing `DB_*` after `import db` has
  no effect. `attachment.root()` and `auth.session_cookie_config()` deliberately
  do the opposite and re-read on every call — see the note on `ATTACHMENT_DIR`.

---

## 1. Database — `db.py`

| Variable | Default | Production | What it does |
|---|---|---|---|
| `DB_ENABLED` | `true` | **must be `true`** | `false` runs entirely in RAM and loses everything on restart. The suite sets it false; a server must not. |
| `DB_STRICT` | `false` | **should be `true`** | `true` refuses to start when MySQL is unreachable. At `false` the app starts anyway, prints a banner and runs in memory — which on a real server means taking work all day and saving none of it. |
| `DB_HOST` | `127.0.0.1` | set it | |
| `DB_PORT` | `3306` | set it | |
| `DB_NAME` | `samruddhi_qms` | set it | `db.init()` issues `CREATE DATABASE IF NOT EXISTS`, so **the schema does not have to exist** — the app creates its own, and all 22 tables with it. |
| `DB_USER` | `root` | **set it** | `root` is a local-dev convenience, not a deployment answer. |
| `DB_PASSWORD` | `""` (empty) | **mandatory** | ⚠ Never in a tracked file. |

**There is no migration step.** `db.init()` creates the schema and every table at
boot (`CREATE TABLE IF NOT EXISTS` for all 22 collections), so pointing a fresh
app at an empty MySQL is the whole of the database install.

---

## 2. Signing key — `auth.py`

| Variable | Default | Production | What it does |
|---|---|---|---|
| `SAMRUDDHI_SECRET_KEY` | — | **mandatory** | Signs the session cookie. Checked **first**. |
| `SECRET_KEY` | — | alternative | Checked **second**. Honoured because `tests/conftest.py` has set it since before `auth.py` existed, and a live install may already carry it. Read, never written. |

When neither is set, `auth.resolve_secret_key()` reads `secret_key.txt` beside
the code, mints a random 256-bit key if that is absent, and **prints a loud
banner to stderr** saying so (`auth.secret_key_warning()`). It warns; it does not
refuse to start — ABOUT.md §7 and PROGRESS.md row 32 have the reasoning.

⚠ **A key supplied through either variable raises no warning at all**, because
from inside the process a published placeholder is indistinguishable from a real
key. That is why `.env.example` now ships `SECRET_KEY=` **blank**: it used to
ship `SECRET_KEY=qms-demo-secret-2024`, the exact literal
`tests/test_auth.py::test_the_demo_secret_key_is_gone_from_the_codebase` scans
every root module to keep *out* of the code — and ABOUT.md's own cold-start block
says `cp .env.example .env`, so following the documentation handed it back.
Generate a real one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

⚠ **If `secret_key.txt` is lost or differs between restarts, every session
cookie is invalidated** and everybody is signed out. That is a logout, not a
data loss — but on a deployment, set the variable and do not rely on the file.

---

## 3. Attachment store — `attachment.py`

| Variable | Default | Production | What it does |
|---|---|---|---|
| `ATTACHMENT_DIR` | `<repo>/attachments` | **set it, outside the checkout** | Where CC-2 B8's uploaded files live. The database row holds only a **relative path**. |

⚠ **Re-read on every call, never cached in a module constant.** The tests point
it at a temporary directory per test, and a value read once at import would make
the first test's directory the one every later test wrote into.

⚠ **A backup of this application is two files, not one.** A `mysqldump` covers
the attachment *metadata* and not the files. `tools/backup_db.py` writes both
halves under one stamp — see [`docs/COLD_START.md`](COLD_START.md) and
ABOUT.md §4. Put this directory **outside** the checkout so a redeploy cannot
delete the client's uploads.

---

## 4. Bind address — `app.py` (the development server only)

| Variable | Default | Production | What it does |
|---|---|---|---|
| `SAMRUDDHI_HOST` | `127.0.0.1` | **not used** | Checked first. |
| `HOST` | `127.0.0.1` | **not used** | Checked second, for a host that already sets it. |
| `SAMRUDDHI_PORT` | `5000` | **not used** | Checked first. A value that is not a number in 1–65535 falls back to 5000 with a named warning, never a traceback. |
| `PORT` | `5000` | **not used** | Checked second. |

⚠ **These affect `python app.py` and nothing else.** A production server takes
its own bind argument (`gunicorn --bind`), and these four are not consulted.

⚠ **The default host is `127.0.0.1` and that is deliberate.** `app.py` runs
`app.run(debug=True, ...)`, which serves Werkzeug's interactive debugger — a
remote shell. Defaulting the dev server to `0.0.0.0` would publish it on the LAN.
Use `wsgi.py` in production.

---

## 5. Session cookie — `auth.install()`

| Variable | Default | Production | What it does |
|---|---|---|---|
| `SESSION_COOKIE_SECURE` | `false` | ⚠ **MANDATORY `true`** | At `false` the cookie `auth.enforce()` trusts is sent over plain HTTP. |
| `SESSION_COOKIE_HTTPONLY` | `true` | keep `true` | Stops JavaScript reading the cookie. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | keep `Lax` | `Lax`, `Strict` or `None`, case-insensitive. Flask's own default leaves the flag **unset**; this app is single-origin, so `Lax` costs nothing. `None` is only legal alongside `Secure`. |

⚠ **The defaults are the LOCAL-DEV values, not the production ones.** `Secure`
defaults to `false` because a browser never sends a Secure cookie over
`http://127.0.0.1` — it silently drops it, nobody can sign in, and nothing says
why. A default that breaks `python app.py` is a default that gets deleted,
taking the production value with it. `wsgi.py` prints a warning at every boot
while `Secure` is off.

**A value that does not parse is reported and the default is used.** The app
still boots — a deployment with a typo must be *told*, not prevented from
starting — but `SESSION_COOKIE_SECURE=ture` never resolves to `True` by
truthiness. That is the one misconfiguration on this page with no symptom at
all, and `tests/test_deployment_config.py` exists mostly for it.

---

## 6. Single-worker guard — `wsgi.py`

| Variable | Default | Production | What it does |
|---|---|---|---|
| `SAMRUDDHI_ALLOW_MULTIPROCESS` | unset | ⚠ **never set it** | Turns the single-worker refusal off. Warns loudly every boot. It exists so the refusal can be tested. |
| `SAMRUDDHI_LOCK_FILE` | `<tmp>/samruddhi-qms-<host>-<port>-<schema>.lock` | leave unset | Where the lock lives. Keyed by the database so two deployments on one box do not report each other as a rogue worker. |

⚠ **`--workers 1` is a correctness requirement, not a tuning choice.**
`store.STORE` is one dict in one process's RAM. Two workers is two divergent
copies of the whole application state overwriting each other **with no error at
all**. `wsgi.py` refuses to start rather than allow it. Scale with `--threads`,
which share one STORE.

---

## 7. Tooling — not read by the application

| Variable | Read by | What it does |
|---|---|---|
| `SAMRUDDHI_SEED_PASSWORD` | `tools/seed_users.py` | The first Owner's password, as an alternative to `--password`. **No default, ever**, and placeholders are refused. |
| `SAMRUDDHI_NEW_PASSWORD` | `tools/set_password.py` | Same, for resetting an existing account. That tool **cannot create** one. |
| `SF_E2E_USER_*` / `SF_E2E_PASS_*` | `tools/e2e_chain.py` | Credentials for the end-to-end driver. |

---

## A minimum production environment

Everything marked mandatory above, and nothing else:

```bash
DB_ENABLED=true
DB_STRICT=true
DB_HOST=...
DB_PORT=3306
DB_NAME=...
DB_USER=...
DB_PASSWORD=...              # never in a tracked file
SAMRUDDHI_SECRET_KEY=...     # python -c "import secrets; print(secrets.token_hex(32))"
ATTACHMENT_DIR=/var/lib/samruddhi/attachments    # outside the checkout
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
```

Then:

```bash
gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8000 wsgi:application
```

[`docs/COLD_START.md`](COLD_START.md) is the sequence that takes an empty
database to a working, logged-in application, and records what was actually run.
