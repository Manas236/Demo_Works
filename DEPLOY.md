# DEPLOY.md — Samruddhi Fire QMS on AWS Lightsail / Ubuntu LTS

> **Status: discovery only.** Nothing in this repository was modified to produce
> this document, and nothing in it has been executed against a server. It is
> derived by reading the code at commit `2515257`. Every non-obvious claim cites
> `file:line`.
>
> **Nobody has ever run this application on Linux.** Several things below are
> first-time-on-Linux facts rather than recollections, and they are marked
> ⚠ FIRST RUN where that matters.
>
> Code changes this pass found but deliberately did **not** make are collected in
> [§8](#8-code-changes-the-next-pass-must-make). Do not treat them as optional
> reading: two of them (8.1, 8.2) affect what a customer-facing document says.

---

## 0. State gate

Reported before anything else, as required. Nothing here was fixed.

| Item | Value |
|---|---|
| Branch | `antigravity-dev` |
| `git status --short` | **empty — the tree is clean** |
| HEAD | `2515257dcb99afa9d67cddd126ca366bb7e5105b` |
| Upstream | `origin/antigravity-dev` |
| Ahead / behind | **0 ahead, 0 behind — in sync** |
| `openpyxl` installed in `.venv` | **No** — `ModuleNotFoundError` |
| Client workbooks present | **No** — `fixtures/` contains only `README.md`; `sify_boq.xlsx` and `annexure.xlsx` are absent (both gitignored, `.gitignore:3-5`) |
| Local interpreter | CPython 3.14.6 (Windows) |

The test suite was **not** run, as instructed.

Neither missing item blocks deployment. See [§1.3](#13-openpyxl-and-the-client-workbooks)
for why `openpyxl` is irrelevant on the server.

---

## 1. RUNTIME

### 1.1 Python version

**Required: CPython ≥ 3.10. Recommended: the distribution Python on Ubuntu 24.04 LTS (3.12).**

`requirements.txt:22` claims "CPython 3.10 to 3.14", and that claim is correct —
but not for the reason a reader would assume. **Nothing in the application's own
syntax forces 3.10.** Scanned and found absent across all 153 root/tool/test
modules:

- no `match` statements;
- no `datetime.UTC`, `tomllib`, `ExceptionGroup`, `itertools.batched`,
  `zoneinfo`, `typing.Self` or `@override`;
- no PEP 701 f-string constructs. This was checked with an AST walk over every
  `FormattedValue` node rather than by eye, because this codebase is one
  enormous f-string and a single 3.12-only construct would fail at *import* on
  3.10. The scan found 15 candidate hits and **all 15 are false positives** — a
  `#` inside a *string literal* within the expression (HTML entities such as
  `&#8212;` at `spec.py:987`, `invoice.py:1147`, `employee.py:786`), which is
  legal pre-3.12. There are zero backslashes and zero quote-reuses in f-string
  expression parts.

**The 3.10 floor comes entirely from the pins**, and only two of them:

| Package | `Requires-Python` |
|---|---|
| `python-dotenv==1.2.2` (`requirements.txt:29`) | **`>=3.10`** |
| `click==8.3.1` (`requirements.txt:34`) | **`>=3.10`** |
| Flask, MarkupSafe, PyMySQL, blinker, Werkzeug | `>=3.9` |
| itsdangerous | `>=3.8` |
| Jinja2 | `>=3.7` |

Consequences for the target box:

- **Ubuntu 24.04 LTS ships Python 3.12** → two minor versions above the floor.
  **Use this.**
- **Ubuntu 22.04 LTS ships Python 3.10** → works, but sits exactly on the floor.
  A future pin raise would strand it.
- Do **not** install a PPA or build a custom Python. There is no reason to.

### 1.2 Dependencies and OS-level build packages

`requirements.txt` pins nine packages. The application's runtime third-party
imports were enumerated by AST scan of all 29 root modules, and they are exactly
five:

| Import | Used by | In requirements.txt? |
|---|---|---|
| `flask` | 28 modules | ✅ `Flask==3.1.3` |
| `markupsafe` | `address.py`, `product.py` | ✅ `MarkupSafe==3.0.3` |
| `pymysql` | `db.py` | ✅ `PyMySQL==1.2.0` |
| `dotenv` | `db.py` | ✅ `python-dotenv==1.2.2` |
| `werkzeug` | `auth.py:45` (`werkzeug.security`) | ✅ `Werkzeug==3.1.7` |

> 📝 **A small documentation error, no functional impact.** `requirements.txt:31-32`
> introduces the `blinker/click/itsdangerous/Jinja2/Werkzeug` block with
> *"nothing in this app imports them directly."* That is false for Werkzeug —
> `auth.py:45` is `from werkzeug.security import check_password_hash,
> generate_password_hash`. It is pinned regardless, so nothing breaks. Recorded
> in §8.7.

**No OS-level build packages are required.**

- `PyMySQL` is a **pure-Python** MySQL driver. ⚠ **Do not install
  `libmysqlclient-dev`, `default-libmysqlclient-dev`, `pkg-config` or
  `build-essential` "for MySQL".** Those are for `mysqlclient`, a different
  package this project does not use. Installing them is harmless but is a sign
  somebody has misread the stack.
- `Flask`, `Werkzeug`, `Jinja2`, `click`, `blinker`, `itsdangerous` and
  `python-dotenv` are pure Python.
- `MarkupSafe` is the only package with a C extension. It ships manylinux wheels
  for cp310–cp313 and carries a pure-Python fallback, so pip will not invoke a
  compiler on a supported Ubuntu Python.

What you **do** need from `apt`:

```
python3-venv      # Ubuntu splits venv out of the base python3 package
python3-pip
mysql-server      # co-located, per the brief
mysql-client      # for mysqldump — tools/backup_db.py:63-75 requires it on PATH
```

**`gunicorn` is NOT in `requirements.txt`** — it is commented out at
`requirements.txt:102` on purpose, so that installing this file into a shared
interpreter cannot downgrade anything. Install it separately, at the pin the
file names (`requirements.txt:83`): `pip install gunicorn==23.0.0`.

### 1.3 `openpyxl` and the client workbooks

**Nothing degrades. `openpyxl` is not needed on the server and should not be
installed there.**

Verified two ways — a grep across the whole repo and the AST import scan above.
`openpyxl` appears in exactly two places, neither of which is application code:

- `tools/gen_demo_data.py:8` — a **developer** tool that regenerates
  `demo_data.py` from `sify_boq.xlsx`. Its output is committed. It never runs on
  a server.
- `tests/test_fixtures.py:15` — `pytest.importorskip("openpyxl")` at module
  level.

`tests/test_fixtures.py:33` is an assertion that this stays true: it reads the
source of every root module and fails if `"openpyxl"` appears in any of them.
So the absence of the workbooks and of `openpyxl` on this dev box is a
**test-collection** fact and nothing more. No application feature reads a
workbook at runtime.

---

## 2. THE ARCHITECTURAL CONSTRAINTS — verified

Each of the three facts in the brief was checked against the code. **All three
are correct.** Two need a sharpening that changes what you type.

### 2.1 ✅ Single process — confirmed, and there is a guard

`store.STORE` is one plain dict (`store.py:29-57`) holding 22 collections.
`app.py:114-124` registers a `teardown_request` hook that calls `db.sync(STORE)`
after **every** request; `db.sync()` re-serialises and diffs the entire store
(`db.py:469-526`). Nothing is shared between processes.

`wsgi.py` enforces this with **two** guards, and it refuses to run rather than
warn:

1. **An import-time exclusive OS lock** (`wsgi.py:125-168`) — `fcntl.flock` on
   POSIX (`wsgi.py:148-149`), on a file in the system temp directory keyed by
   host/port/schema (`wsgi.py:120-122`). Catches plain `--workers 2`.
2. **A per-request pid check** (`wsgi.py:279-299`) — because with `--preload`
   the lock is taken once in the arbiter and *inherited* across `fork()`.

> ☠ **THE SINGLE MOST IMPORTANT LINE IN THIS DOCUMENT: NEVER USE `--preload`.
> NOT EVEN WITH `--workers 1`.**
>
> `wsgi.py:287` is `if os.getpid() != _PID_AT_IMPORT`. It tests pid *equality*,
> nothing else. With `--preload`, gunicorn imports `wsgi.py` in the **arbiter**
> and then forks — so the one and only worker is a fork, its pid differs, and it
> **returns 503 to every single request** (`wsgi.py:288-298`). Guard 2 cannot
> distinguish `--preload --workers 1` (which is actually safe) from
> `--preload --workers 2` (which is not).
>
> The failure mode is nasty in a specific way: the boot banner
> (`wsgi.py:215-241`) prints *successfully*, so the log says the app started
> correctly. Every request then 503s. Somebody will spend an hour on nginx.

> ⚠ **FIRST RUN.** Guard 2 has **never been exercised against a real fork.**
> `tests/test_wsgi_single_worker.py:14-20` says so in as many words: the pid is
> faked and the guard is called as a pure function "because Windows has no
> `fork()` and the condition cannot be produced natively here." Guard 1 has
> likewise only ever run through `msvcrt.locking` (`wsgi.py:146`), never through
> `fcntl.flock` (`wsgi.py:149`). **Step 9.3 tests both deliberately, once,
> before go-live.** Do not skip it.

### 2.2 ✅ No `/templates`, no `/static` — confirmed, with one correction

There is no `templates/` or `static/` directory, `app = Flask(__name__)`
(`app.py:77`) overrides no static folder, and no blueprint declares
`static_folder`. Images are base64 data URIs built at import from `assets/*.png`
(`branding.py:293-310`).

**There is no step in this runbook about serving or collecting static assets,
and there must not be one.** An nginx `location /static` block would be serving
an empty directory.

> 📌 **Correction to CLAUDE.md.** The project instructions state
> *"`render_template_string` is gone from every module; do not reintroduce it."*
> **That is not true.** `extractor.py:11` imports it and `extractor.py:408`
> calls it, on the `/extractor` Market News page (registered at `app.py:131`,
> permissioned at `auth.py:645`).
>
> **It is currently harmless, and I checked rather than assumed.** The string it
> renders interpolates only `SAMPLE_ARTICLES` (hardcoded, `extractor.py:24+`),
> `B.COMPANY_NAME` (`branding.py:31`) and `B.APP_SUBTITLE` (`branding.py:48`).
> Neither constant is in `SETTINGS_KEYS` (`branding.py:86-92`), so neither can
> be reached by `branding.apply_settings()` (`branding.py:100-111`) and neither
> is user-controllable. **No SSTI today.** It becomes SSTI the moment anybody
> interpolates a settings value or a record field into that page. Recorded in
> §8.6.

**One real filesystem dependency does exist.** `branding._data_uri()`
(`branding.py:296-302`) reads four files at import and returns `""` on `OSError`
(`branding.py:300-301`) — **it fails silently.** If `assets/` is missing or
unreadable, every page and every printed document renders with no logo and no
favicon, and nothing anywhere says why.

Required, with exact case (Linux is case-sensitive; all four verified present
and correctly cased):

```
assets/logo-64.png      assets/logo-256.png
assets/favicon-32.png   assets/ganesh.png
```

A repo-wide case-collision check (`git ls-files | tr A-Z a-z | sort | uniq -d`)
returned **nothing**. The checkout is safe to move from Windows to a
case-sensitive filesystem.

### 2.3 ✅ `CREATE TABLE IF NOT EXISTS`, no FKs, no migrations — confirmed

`db.py:175-200`. Verified: a grep for `FOREIGN KEY`, `ALTER TABLE`,
`CREATE INDEX` and `DROP TABLE` across the entire repository returns **zero**
hits. The complete SQL surface of this application is six statements:

| Statement | Line |
|---|---|
| `CREATE DATABASE IF NOT EXISTS … CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` | `db.py:180-183` |
| `CREATE TABLE IF NOT EXISTS <coll> … ENGINE=InnoDB DEFAULT CHARSET=utf8mb4` | `db.py:190-199` |
| `SELECT id, data FROM <coll>` | `db.py:392` |
| `INSERT … ON DUPLICATE KEY UPDATE data = VALUES(data)` | `db.py:430-433` |
| `DELETE FROM <coll> WHERE id = %s` | `db.py:441-444` |
| `DELETE FROM <coll>` (tests only — `db.reset()`) | `db.py:537` |

---

## 3. CONFIGURATION — the complete enumeration

### 3.0 How it is read — two behaviours that have bitten

`db.py:71` is `load_dotenv(override=False)`, called **once, at import**.

1. **A real environment variable beats `.env`.** (`override=False`.)
2. **`db.CONFIG` is frozen at import** (`db.py:99-107`). Changing any `DB_*`
   variable after `import db` does nothing. `attachment.root()`
   (`attachment.py:230`) and `auth.session_cookie_config()` (`auth.py:136-155`)
   deliberately do the opposite and re-read on every call.

> ✅ **Verified empirically, because it decides your systemd unit.** `.env` is
> located relative to **`db.py`'s own directory**, not to the working directory.
> I ran the interpreter from `C:\Users` with only `sys.path` pointing at the
> repo, and `db.CONFIG["password"]` still came back populated from the repo's
> `.env`. **So `WorkingDirectory=` is not required for `.env` to be found.**
> Set it anyway (§9.6) — `tools/backup_db.py` and the seeders are friendlier
> from the repo root — but do not waste time debugging it.

### 3.1 MUST-CHANGE before a client touches this system

| Variable | Read at | Current default | Why it must change |
|---|---|---|---|
| `DB_PASSWORD` | `db.py:106` | `""` (empty) | An empty password is not a deployment answer. Never in a tracked file. |
| `DB_USER` | `db.py:105` | `root` | The app must not run as MySQL root. See §4.3 for the exact GRANTs. |
| `DB_STRICT` | `db.py:101` | `false` | **At `false` the app boots happily with no database and takes work all day without saving any of it** (`db.py:218-231`, `app.py:94-96`). Set `true`. |
| `SAMRUDDHI_SECRET_KEY` | `auth.py:204` | unset → falls back to `secret_key.txt` | Without it the signing key lives on disk beside the code and is minted on first boot (`auth.py:214-222`). Losing the file signs everybody out. Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SESSION_COOKIE_SECURE` | `auth.py:136-141` | **`False`** | The defaults are the **local-dev** values (`auth.py:83-92`). At `false` the session cookie that `auth.enforce()` trusts (`app.py:212`) travels in clear. **This is the one misconfiguration on this page with no observable symptom.** |
| `ATTACHMENT_DIR` | `attachment.py:230` | `<repo>/attachments` | Must be **outside the checkout**, or a redeploy deletes the client's uploaded evidence. |
| `DB_NAME` | `db.py:104` | `samruddhi_qms` | Optional, but pick it deliberately — it keys the single-worker lock file (`wsgi.py:120`). |

### 3.2 Safe as-is (set them explicitly anyway, so nothing is implicit)

| Variable | Read at | Default | Note |
|---|---|---|---|
| `DB_ENABLED` | `db.py:100` | `true` | Correct. `false` runs entirely in RAM. |
| `DB_HOST` | `db.py:102` | `127.0.0.1` | Correct for a co-located MySQL. |
| `DB_PORT` | `db.py:103` | `3306` | Correct. |
| `SESSION_COOKIE_HTTPONLY` | `auth.py:136` | `True` | Correct. Keep. |
| `SESSION_COOKIE_SAMESITE` | `auth.py:145-155` | `Lax` | Correct. Flask's own default leaves this unset; `Lax` costs nothing single-origin. |
| `SECRET_KEY` | `auth.py:204` | unset | Checked **second**, after `SAMRUDDHI_SECRET_KEY`. Read, never written. Leave unset; use the namespaced one. |
| `SAMRUDDHI_HOST` / `HOST` | `app.py:264` | `127.0.0.1` | **Not consulted in production.** Dev server only. |
| `SAMRUDDHI_PORT` / `PORT` | `app.py:265` | `5000` | **Not consulted in production.** gunicorn takes `--bind`. |
| `SAMRUDDHI_LOCK_FILE` | `wsgi.py:117` | `<tmp>/samruddhi-qms-<host>-<port>-<schema>.lock` | Leave unset. |

### 3.3 ☠ NEVER SET

| Variable | Read at | Effect |
|---|---|---|
| `SAMRUDDHI_ALLOW_MULTIPROCESS` | `wsgi.py:254`, `wsgi.py:287` | **Disables both single-worker guards.** It exists so the refusal can be tested. On a real server it is the switch that silently corrupts the client's records. |

### 3.4 Tooling only — not read by the application

| Variable | Read at |
|---|---|
| `SAMRUDDHI_SEED_PASSWORD` | `tools/seed_users.py:118` |
| `SAMRUDDHI_NEW_PASSWORD` | `tools/set_password.py:85` |
| `SF_E2E_USER_*` / `SF_E2E_PASS_*` | `tools/e2e_chain.py:1864-1865` |

### 3.5 ⚠ HARDCODED WITH NO OVERRIDE MECHANISM AT ALL

**This is the list the brief asked for in full, now, rather than one at a time.**
Every one of these is a literal in a module. There is no env var, no `.env` key
and no `/settings` control. Changing any of them is a code edit and a redeploy.

| Value | Location | Current | Assessment for go-live |
|---|---|---|---|
| Session lifetime | `auth.py:65` → `auth.py:1481` | `SESSION_HOURS = 12` | **Fine.** Covers a working day. |
| Product catalogue visibility | `auth.py:486` | `HIDDEN_BLUEPRINTS = {"product"}` | **Intentional** (11–12 Sep 2026). `/product` is unreachable by everyone including an Owner, and `/quotation/create` is driven from the spec library instead. Confirm the client expects this. |
| Approval ladder | `approval.py:307` | `LADDER_ON = False` | **Intentional** (12 Sep 2026), and `docs/ENVIRONMENT.md` notes there is no `/settings` control *by design*. Every approve/reject route is refused for everyone; documents print as raised. **Confirm the client knows nothing is gated.** |
| Attachment size cap | `attachment.py:130` | `MAX_BYTES = 5 MB` | Fine, and it drives an nginx setting — see §9.5. |
| `app.MAX_CONTENT_LENGTH` | `attachment.py:125` | `None` (deliberately unset) | Fine; the per-field check gives a better error. |
| Form body cap | Flask default, documented at `app.py:233` | `MAX_FORM_MEMORY_SIZE = 500,000 bytes` | Not set in code. `boq.MAX_LINES = 600` (`boq.py:155`) plus a payload-byte check is what keeps a real BOQ under it. |
| BOQ line cap | `boq.py:155` | `MAX_LINES = 600` | Fine. |
| Trading name / app name | `branding.py:31`, `:47`, `:48` | `COMPANY_NAME = "SAMRUDDHI FIRE"` etc. | **Not editable from `/settings`** — absent from `SETTINGS_KEYS` (`branding.py:86-92`). If the client's trading name differs, that is a code edit. **Ask before go-live.** |
| Specimen company identity | `settings.py:129-142` | GSTIN `27AAAAA0000A1Z5`, `SPECIMEN BANK LTD.`, IFSC `SPEC0000000` | ☠ **See §6 — the single most dangerous default in the system.** |
| MySQL charset/collation | `db.py:161`, `:182`, `:198` | `utf8mb4` / `utf8mb4_unicode_ci` | **Correct.** Hardcoded is right here. |
| pymysql connect args | `db.py:157-163` | no `read_timeout`, no `write_timeout` | A hung MySQL blocks the request thread **indefinitely** while holding `db._lock`. Recorded in §8.5. |
| Logging | — | **there is none** | The app configures no logging at all. Only `current_app.logger.warning` at `auth.py:1307` (access refusals). Recorded in §8.3. |
| 500 handler | `app.py:224-227` | redirects to `/`, logs nothing | ☠ **A crash looks exactly like "the page went back to the dashboard."** Recorded in §8.3. |

---

## 4. DATABASE

### 4.1 MySQL version and features assumed

- **`JSON` column type** (`db.py:193`) → **MySQL ≥ 5.7.8**.
- **`ENGINE=InnoDB`** (`db.py:198`) → fine everywhere.
- **`VALUES()` in `ON DUPLICATE KEY UPDATE`** (`db.py:432`) → works in 5.7 and
  8.0/8.4, but is **deprecated since MySQL 8.0.20** in favour of the row-alias
  form. It still functions; it will warn. Not a blocker, recorded in §8.8.

**Ubuntu 24.04's `mysql-server` is 8.0.x.** That satisfies everything above.
Install it from `apt`; do not add an Oracle repo.

### 4.2 Charset and collation — and whether Devanagari is really in play

**`utf8mb4` is required, and the code already forces it in all three places
that matter** (`db.py:161` connection, `db.py:182` database, `db.py:198` table).
You do not need to change `character_set_server` in `my.cnf`; the explicit
clauses override the server defaults.

On Devanagari/Marathi specifically, since the brief asked:

- **There is no Devanagari anywhere in the source.** Grepped the full
  `U+0900–U+097F` range across every `.py` in the repo: zero hits.
- **But user data can be, and the code explicitly plans for it.**
  `attachment.py:441-444` refuses to run `secure_filename` on uploads with the
  stated reason that it *"mangles a perfectly ordinary `बिल.pdf` to nothing at
  all"*, and stores the original filename as display text.
- `db.py:360` serialises with `ensure_ascii=False`, so non-ASCII goes into the
  `data` column **raw**, not as `\uXXXX` escapes.
- The rupee sign `₹` (U+20B9, 3 bytes) is parsed out of money fields at
  `invoice.py:185`.

Devanagari is 3-byte UTF-8 and would survive `utf8mb3`; 4-byte characters
(emoji, some CJK extensions) would not. Since `utf8mb4` is already forced,
**both are safe and no action is needed** — but do not "simplify" any of those
three hardcoded clauses.

### 4.3 The exact GRANTs

Derived from the six statements in §2.3. The app needs, at runtime:

`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE`

It does **not** need `ALTER`, `INDEX`, `DROP`, `TRIGGER`, `REFERENCES`, or any
global privilege, and it must **not** run as `root`.

Two non-obvious requirements:

1. **`CREATE` is needed at every boot, not just the first.** `db.init()` →
   `_ensure_schema()` runs `CREATE DATABASE IF NOT EXISTS` (`db.py:180-183`) and
   22 × `CREATE TABLE IF NOT EXISTS` (`db.py:189-199`) on **every single
   start**, not conditionally.
2. **The app opens a connection with no default schema.** `_connect(with_db=False)`
   passes `database=None` (`db.py:160`) for the `CREATE DATABASE` call. The user
   must be able to connect without a default database — a plain
   `GRANT … ON samruddhi_qms.*` user can, so the recipe below satisfies it, but
   it rules out any setup that pins a required default schema.

**Recommended: pre-create the database as root, then grant the app user schema
scope only.** This keeps `CREATE DATABASE` a no-op (the `IF NOT EXISTS`
short-circuits) and avoids relying on database-level `CREATE` being accepted for
the `CREATE DATABASE` statement itself.

```sql
CREATE DATABASE IF NOT EXISTS samruddhi_qms
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'samruddhi'@'127.0.0.1' IDENTIFIED BY '<a real password>';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE
  ON samruddhi_qms.* TO 'samruddhi'@'127.0.0.1';

FLUSH PRIVILEGES;
```

⚠ Use `'samruddhi'@'127.0.0.1'`, not `@'localhost'`. `DB_HOST` defaults to
`127.0.0.1` (`db.py:102`), which MySQL treats as a **TCP** connection and matches
against the `127.0.0.1` host pattern — `localhost` would go over the unix socket
and match a different grant row. Getting this wrong produces
`Access denied for user` with an otherwise perfect password.

### 4.4 How the schema comes into existence, and is it safe on an empty database

**Yes — pointing the app at an empty MySQL *is* the entire database install.**
There is no migration step and no seed SQL.

The path is `app.py:111` → `_boot_persistence()` → `db.init()` (`db.py:207-231`)
→ `_ensure_schema()` (`db.py:175-200`) → `db.load_into(STORE)` (`db.py:375-400`).

Safe to re-run: every statement is `IF NOT EXISTS`, and the upserts/deletes in
`_sync_collection` are idempotent by construction (`db.py:405-410`).

### 4.5 Does anything assume tables already have rows?

**No — `load_into` on empty tables returns 0 and the app runs normally**
(`db.py:385-400`). There is no code that indexes into an assumed-present record.

**But the reverse problem exists and it is serious.** Nothing assumes rows are
there; several code paths *put rows there whether you want them or not*. That is
§6, and it is the thing on this page most likely to reach a customer.

### 4.6 Capacity notes

- **One record = one row = one whole JSON document** (`db.py:21-27`). There is no
  normalisation and no index other than the `id` primary key (`db.py:191-198`).
  MySQL cannot query inside a record.
- **`max_allowed_packet` is a real failure mode the code anticipates**
  (`db.py:484` names *"a `data` blob past `max_allowed_packet`"*). MySQL 8.0's
  default is 64 MB, comfortably above any single BOQ. Leave it alone; know that
  if it ever fires, the effect is per-collection and retried (§11), not fatal.
- **Attachment bytes are NOT in MySQL** (the `attachments` comment in
  `store.py:45`; `attachment.py:428-434`). A `mysqldump` is **half** a backup.
  See §10.

---

## 5. FILESYSTEM

Every path the application touches at runtime. There are only four, and
`backups/` is not among them.

| # | Path | Built from | Abs/rel | Survives restart? | Growth |
|---|---|---|---|---|---|
| 1 | **Attachment store** | `ATTACHMENT_DIR` resolved, else `<repo>/attachments` — `attachment.py:211`, `:230-231` | **Absolute** either way (`.resolve()` / `__file__`) | ☠ **MUST** | ≤ 5 MB/file (`attachment.py:130`); ~2–5 MB typical (`attachment.py:113`); **mandatory on every charge** (`attachment.py:186`), optional on receipts (`attachment.py:198-204`) |
| 2 | **`secret_key.txt`** | `<repo>/secret_key.txt` — `auth.py:169` | **Absolute** (`__file__`) | **Should** — unless `SAMRUDDHI_SECRET_KEY` is set | 64 bytes, once |
| 3 | **Single-worker lock** | `tempfile.gettempdir()/samruddhi-qms-<host>-<port>-<schema>.lock` — `wsgi.py:120-122` | **Absolute** | **MUST NOT** — the kernel releases it on exit, deliberately, so a crash cannot brick the next start (`wsgi.py:47-49`) | a pid string |
| 4 | **`assets/*.png`** | `<repo>/assets` — `branding.py:293` | **Absolute** (`__file__`) | read-only | fixed, ~55 KB read at import |

**Nothing is written relative to the working directory. Nothing writes a log
file. There are no temp files beyond the lock.**

### 5.1 Linux portability — checked, and it is clean

- **No backslash path building in runtime code.** The one stored relative path is
  `rel = f"{parent_type}/{aid}{ext}"` (`attachment.py:428`) — a forward slash,
  which `pathlib` handles identically on both platforms. **Attachment rows
  written on Windows resolve correctly on Linux.**
- **No `os.path.join` on Windows-shaped strings, no drive letters** in any
  runtime module. `tools/backup_db.py:70-72` has `C:\Program Files\MySQL\…`
  fallbacks, but it tries `shutil.which("mysqldump")` **first**
  (`tools/backup_db.py:67`), so it works on Linux via PATH.
- **Case sensitivity:** all four asset filenames verified present with exact
  case; no case collisions anywhere in `git ls-files`.
- **Path traversal is re-validated on every read** (`attachment.py:239-266`), so
  a row restored from a dump cannot escape the root.

### 5.2 Directory ownership

The attachment store must be writable by the service user — `_ensure_root()`
calls `mkdir(parents=True, exist_ok=True)` (`attachment.py:236`) on first upload,
so it will create its own tree, but it cannot create `/var/lib/samruddhi` if the
parent is root-owned.

**If you set `SAMRUDDHI_SECRET_KEY` (and you should), the checkout itself never
needs to be writable.** `auth.py:218-222` tolerates a read-only checkout by
catching `OSError` and carrying on with an in-memory key — but that means a new
key every boot and everybody signed out on every restart. Set the variable and
the question does not arise.

---

## 6. ☠ THE SPECIMEN DATA PROBLEM — read this before go-live

**This is the finding most likely to reach a real customer on a real document,
and it is not in `ABOUT.md`'s deployment notes because there are none.**

> ### ✅ FIXED — 25 September 2026, and this section is kept rather than deleted
>
> **`SAMRUDDHI_DEMO_DATA` now gates all four demo seeders and DEFAULTS TO
> OFF**, so a production box built from §9 grows none of what this section
> describes and a deletion stays deleted across a restart. ABOUT.md §7 gap 35
> and CLIENT_CHANGES.md §0, the thirty-first block.
>
> The section below is left standing because it is still the accurate account
> of **what a box that sets `SAMRUDDHI_DEMO_DATA=true` will do**, and of what
> is already in a database that booted with the demo on before this date —
> turning the flag off stops the seeding, it deletes nothing. Three
> corrections are marked inline: §6.1's trigger column, §6.2, and §6.3's last
> paragraph, which was **wrong**.
>
> ⚠ **§8.1 is therefore closed.** The rest of §8 is untouched.

### 6.1 What gets created without anybody asking

| Seeded | Trigger | Code |
|---|---|---|
| **Specimen company identity** — GSTIN `27AAAAA0000A1Z5`, `SPECIMEN BANK LTD.`, A/C `50200000000000`, IFSC `SPEC0000000`, an **invented** Navi Mumbai address | **every boot**, unconditionally | `app.py:102` → `settings.py:170-178`, values at `settings.py:129-142` |
| 10 demo products with placeholder prices and unverified HSN codes | first visit to `/` | `dashboard.py:2374-2377` → `product.py:82-158` |
| A 97-line BOQ for a **real third party** — project `"Sify Bangalore"`, account `"Prudent Teqtis Pvt Ltd"` | first visit to several `/boq` routes | `boq.py:1823`, `:2156`, `:2434`, `:2531` → `boq.py:562-618`, data at `demo_data.py:1395-1412` |
| Demo specification library | `/spec` routes | `spec.py:186-218` |
| Demo addresses | `/address` routes | `address.py:159-241` |

The product catalogue being hidden (`auth.py:486`) does **not** prevent this —
`ensure_demo_products()` is still called from `dashboard.py:2376`,
`quotation.py:1228` and `purchase.py:2054`. The rows are created; they are just
not browsable.

> ✅ **`SAMRUDDHI_DEMO_DATA=false` does prevent it** (25 September 2026), and
> at every one of those call sites including the two in frozen files.
> `product.py` may not be edited, so `app.disarm_frozen_demo_seeder()` pre-sets
> the `STORE["_seeded"]` guard the function already opens with — the same
> "toggle from outside" the catalogue hide used. The **Trigger** column above
> therefore reads "every boot" / "first visit to /" only while the flag is on.

### 6.2 Why deleting it does not work

**The seed flags are deliberately not persisted** (`db.py:82-85`). So `_seeded`,
`_boq_seeded`, `_spec_seeded` and `_settings_seeded` are `False` again after
every restart, and the seeders re-run.

`settings.py:162-168` states the consequence outright: *"'clear everything and
restart' brings the specimen row back… the absence cannot tell 'never set' from
'set to nothing'."* `boq.py:571-573` says the same for the demo BOQ.

**So the client deletes the specimen data, restarts a week later, and it is
back.**

> ✅ **Not any more, with `SAMRUDDHI_DEMO_DATA=false`** (25 September 2026).
> The seed flags are still deliberately unpersisted and `db.py:82-85` still
> says why — that is now harmless rather than load-bearing, because a seeder
> that is switched off has nothing to remember. `settings.py`'s note about
> "clear everything and restart" bringing the specimen row back is true only
> while the flag is on.

### 6.3 What this means operationally

☠ **A tax invoice, RA bill, proforma or PO printed before `/settings` is filled
in will carry GSTIN `27AAAAA0000A1Z5` and `SPECIMEN BANK LTD.` bank details on
the letterhead.** The customer will pay into a bank account that does not exist,
or file a template GSTIN.

**Mandatory go-live sequence, in this order:**

1. Boot the app once (this seeds the specimen row).
2. Sign in as the Owner.
3. Go to `/settings` and fill in **every** field in `SETTINGS_KEYS`
   (`branding.py:86-92`) with the client's real values — `COMPANY_LEGAL`,
   `COMPANY_TAGLINE`, `COMPANY_ADDR`, `COMPANY_PHONE`, `COMPANY_EMAIL`,
   `COMPANY_WEB`, `COMPANY_GSTIN`, `COMPANY_PAN`, `COMPANY_BRANCHES`,
   `COMPANY_SIGNATORY`, `BANK_NAME`, `BANK_ACCOUNT_NAME`, `BANK_ACCOUNT_NO`,
   `BANK_IFSC`, `BANK_BRANCH`.
4. **Verify by printing one document of each type** and reading the letterhead
   and the bank block.
5. Only then let anyone raise a real document.

⚠ **THIS PARAGRAPH WAS WRONG AND IS CORRECTED — 25 September 2026.** It read:

> *"Do not leave a field blank hoping it disappears. A blank field falls back
> to the `DEFAULTS` snapshot (`branding.py:104-111`) — which is the specimen
> value, not nothing."*

**It is not the specimen value.** `branding.DEFAULTS` is snapshotted from that
module's own import-time values, and those are `""` for every statutory field
(`branding.py:31-38`, `:62-66`). The specimen values only ever lived in
`settings.DEMO_COMPANY` and in the stored `STORE["settings"]["company"]` row.
So a blank field falls back to **blank**, and `branding.field()` draws the
amber `add …` chip — which is the behaviour the whole identity block was
written for.

**Measured, not argued**: with no identity seeded, all nine print routes
render `200` and none of the seven specimen strings appears on any of them —
`tests/test_print_golden.py::test_every_print_route_renders_with_a_blank_company_identity`,
with `test_the_blank_identity_sweep_is_not_vacuous` proving the check can fail.

**What stays true**: a blank statutory field prints a visible amber marker on a
document that goes to a customer, so step 3 is still mandatory before anybody
raises a real one. Blank is *safe*, not *finished*.

✅ **Delete the demo BOQ, products and addresses after step 3, and with
`SAMRUDDHI_DEMO_DATA=false` they stay deleted across a restart.** (The spec
library is a genuine default and is seeded whatever the flag says — do not
delete it, the BOQ and quotation pickers are written from it.)

---

## 7. PROCESS MODEL

### 7.1 How it is started today

`python app.py` → `app.run(debug=True, host=DEV_HOST, port=…, reloader_type="stat")`
(`app.py:291-292`), bound to `127.0.0.1:5000` by default (`app.py:264-265`).

☠ **This must never face a network.** `debug=True` serves Werkzeug's interactive
debugger, which is a remote shell. `app.py:260-263` says so, and the default host
is `127.0.0.1` rather than `0.0.0.0` for exactly this reason.

### 7.2 How it must be started

```
gunicorn --workers 1 --threads 1 --bind 127.0.0.1:8000 --timeout 120 wsgi:application
```

- `wsgi:application` — the name gunicorn looks up, aliased at `wsgi.py:85`.
- `--workers 1` — a correctness requirement, not tuning. §2.1.
- `--bind 127.0.0.1:8000` — **loopback, not `0.0.0.0`.** nginx is in front
  (§9.5). `requirements.txt:84` and `docs/ENVIRONMENT.md:192` both show
  `0.0.0.0:8000`; on a Lightsail box that would expose gunicorn directly to the
  internet. Bind loopback.
- `--timeout 120` — raised from the 30 s default because `db.py:157-163` sets no
  `read_timeout`/`write_timeout` (§8.5), and because the boot does a full
  `load_into` of every row (`db.py:375-400`).
- **NO `--preload`.** §2.1.
- `--threads 1` — the recommendation, and §7.3 is the reasoning.

### 7.3 ⚠ Is the code safe under gunicorn threads? — the honest answer

**Partly. The database path is safe. Document numbering is not.**

**What IS thread-safe:**

`db._lock` (`db.py:114`) is a `threading.Lock`, and `db.sync()` takes it around
the whole sync (`db.py:502`). The single shared `pymysql` connection
(`db.py:113`) is only ever used inside that lock — `_conn()` is called at
`db.py:508` within the `with`, and otherwise only from `load_into` at boot
(single-threaded) and `reset()` (tests). **This matters because pymysql
connections are not thread-safe**, and the lock is the only thing that makes the
shared connection legal.

**What is NOT thread-safe:**

`db._lock` is the **only lock in the entire application.** A grep for
`threading`, `Lock()` and `RLock` across all root modules returns `db.py` and
nothing else. Request handlers mutate `STORE` with no synchronisation whatever.

Two concrete failure modes:

**(a) Duplicate statutory invoice numbers. This is the one that matters.**

Every reference minter is an unguarded scan-for-max-then-add-one. There are ten
of them (`boq.py:212`, `challan.py:167`, `invoice.py:164`, `measurement.py:316`,
`po_draft.py:117`, `proforma.py:119`, `purchase.py:213`, `quotation.py:239`,
`ra.py:1030`, `receipt.py:174`). Taking `invoice._next_ref` as the worked case
(`invoice.py:182-191`):

```python
fy = _fy_of(datestr)
highest = 0
for ti in STORE["invoices"].values():      # scan
    ...
    highest = max(highest, int(tail))
return P.fy_ref(..., highest + 1, cap=16)  # +1, then the caller writes it
```

Two concurrent POSTs in the same financial year both read `highest`, both return
`highest + 1`, and **both write a record carrying the same tax invoice number.**

This is not a cosmetic collision. `invoice.py:166-175` states that this serial
exists to satisfy **GST Rule 46(b)**, which requires uniqueness within the
financial year. And there is **no unique index to catch it** — the only key on
any table is `id` (`db.py:191-198`), and `id` is a fresh UUID, so both rows
persist happily. The duplicate is discovered by the client's CA, at filing.

The same applies to `ra.next_tax_invoice_ref()` (`ra.py:1050+`), which is also a
statutory serial.

**(b) Torn reads during sync.** `_sync_collection` iterates `current.items()`
(`db.py:420`) and `json.dumps` each record (`db.py:421`) while another thread may
be mutating the same dict. Two effects:

- `RuntimeError: dictionary changed size during iteration` → caught per
  collection at `db.py:518`, that collection is marked failed and **retried on
  the next request** (`db.py:486-492`). The user sees the red "not being saved"
  strip (`db.py:286-324`) flicker. Self-healing, but alarming.
- A record serialised mid-mutation is persisted in a torn state and its digest
  advanced (`db.py:435-436`). It self-corrects on the next sync because the live
  record then differs from the stored digest — **unless the process dies in
  between**, in which case the torn record is what MySQL has.

**The recommendation: `--threads 1` for go-live.**

Reasoning: one fire-contractor's office is a handful of concurrent users; the app
already serialises every request on a full-store diff (§7.4), so threads buy much
less than they appear to; and `--threads 1` makes failure mode (a)
**structurally impossible** rather than merely unlikely.

> 📌 Note for context, not comfort: **this race already exists in dev.**
> `app.run()` sets `threaded=True` by default (Flask 3.1.3, `flask/app.py:655`
> in the installed package). It has never fired because one developer cannot POST
> twice at once. Moving to `--threads 1` in production is therefore *stricter*
> than what has been running, not a regression.

If throughput later demands `--threads 2..4`, do §8.2 first.

### 7.4 What gunicorn will actually be doing per request

`db.sync()` re-serialises and SHA-256s **every record in all 22 collections on
every request** (`db.py:418-424`). `db.py:136` records a measurement: a store of
200 BOQs is ~15 MB of JSON. That is ~15 MB of `json.dumps` plus hashing **per
request**, single-threaded, on 2 vCPU.

This is the application's scaling ceiling, and it is architectural, not
configuration. It is fine for an office; it is the reason `--threads` is not the
lever it looks like.

### 7.5 Memory on a 2 GB box

Comfortable, but account for it:

- `STORE` lives entirely in RAM, plus digests. `db.py:136` measures digests at
  0.5 MB against 30.2 MB for the old full-string cache. Python dict overhead puts
  a 15 MB JSON store at roughly 50–80 MB resident.
- Password hashing is **scrypt** (Werkzeug's default; `auth.py:1760` measures
  ~70 ms), which allocates ~32 MB per hash at the default `scrypt:32768:8:1`.
  Transient, and with `--threads 1` there is only ever one.
- MySQL 8.0's default `innodb_buffer_pool_size` is 128 MB. **Leave it.** Do not
  "tune it up" on a 2 GB box that is also running the app.
- **Add swap.** Lightsail instances ship without it, and MySQL 8.0's baseline RSS
  on 2 GB is tight. 2 GB of swap on the 60 GB SSD.

---

## 8. CODE CHANGES THE NEXT PASS MUST MAKE

**Recorded, not made.** This pass modified nothing. Ordered by how much damage
each one does if it ships as-is.

**8.1 — Specimen data cannot be removed.** ✅ **DONE — 25 September 2026.**
Built as the second of the two options this entry named: *"an env flag that
disables demo seeding in production"*. `SAMRUDDHI_DEMO_DATA` gates all four
demo seeders and **defaults to off**; the spec library, charge heads and
measurement columns are genuine defaults and are not gated. `product.py` is
frozen, so its seeder is disarmed from `app.disarm_frozen_demo_seeder()`
rather than edited — the trick the catalogue hide used. ABOUT.md §7 gap 35,
CLIENT_CHANGES.md §0 thirty-first block, `tests/test_demo_data_flag.py`.
The persisted "deliberately cleared" marker was **not** built and is not
needed: a seeder that never runs leaves nothing to mark.

**8.2 — Reference minting has no lock.** §7.3(a). Ten call sites; the GST-serial
ones (`invoice.py:182-191`, `ra.py:1050+`) are the statutory ones. Needs a mutex
around mint-and-insert, or a per-series counter record. Until then, `--threads 1`
is load-bearing, not a preference.

**8.3 — Errors are invisible in production.** `app.py:224-227` catches 500 and
redirects to the dashboard, logging nothing. The app configures no logging at
all. On a server, an exception is indistinguishable from a user clicking Home.
Needs `app.logger.exception()` in the handler and a basic logging config to
stderr (journald captures it). **Do this before go-live if you do only one item
from this list besides 8.1.**

**8.4 — `--preload` fails closed but unhelpfully.** `wsgi.py:287` compares pids,
so `--preload --workers 1` 503s every request while printing a healthy boot
banner. Needs to read gunicorn's actual worker count, or the banner needs to name
`--preload` as a cause.

**8.5 — No socket timeouts on the MySQL connection.** `db.py:157-163` sets
neither `read_timeout` nor `write_timeout`. A hung (not dropped) MySQL blocks a
request thread indefinitely *while holding `db._lock`*, stalling the process
until gunicorn's `--timeout` kills the worker. Mitigated by `--timeout 120`;
properly fixed by passing timeouts to `pymysql.connect`.

**8.6 — `render_template_string` survives in `extractor.py`.** §2.2. Harmless
today, one interpolation away from SSTI, and CLAUDE.md asserts it is gone. Either
remove the second parse or correct CLAUDE.md.

**8.7 — `requirements.txt:31-32` is wrong about Werkzeug.** It says nothing
imports that block directly; `auth.py:45` does. Comment-only.

**8.8 — `VALUES()` is deprecated.** `db.py:432`. Works on MySQL 8.0/8.4; move to
the row-alias form before a server upgrade forces it.

**8.9 — `docs/COLD_START.md` does not exist.** `docs/ENVIRONMENT.md:97` and
`:195-196` both link to it as the authoritative empty-database-to-working-app
sequence. `docs/` contains only `ACCESS_MATRIX.md` and `ENVIRONMENT.md`. Either
write it or point those links at this file.

---

## 9. THE RUNBOOK

Ordered. Do not reorder 9.1 → 9.4.

### 9.1 Server preparation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip mysql-server mysql-client nginx

# ☠ TIMEZONE — see 9.1a. Do this before the app ever writes a record.
sudo timedatectl set-timezone Asia/Kolkata
timedatectl        # verify: "Time zone: Asia/Kolkata (IST, +0530)"

# Swap — Lightsail ships without it and 2 GB is tight with MySQL co-located.
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

sudo mysql_secure_installation
```

#### 9.1a ☠ Why the timezone step is not boilerplate

**AWS Lightsail Ubuntu defaults to UTC. IST is UTC+05:30. This application uses
naive local time everywhere and has no timezone handling at all.**

There are ~35 call sites — `datetime.now()` / `date.today()` with no tz — at
`pipeline.py:190`, `pipeline.py:222`, `invoice.py:155`, `ra.py:2145`,
`ra.py:3238`, `receipt.py:214`, `boq.py:4114`, `challan.py:380`,
`measurement.py:324`, `proforma.py:106`, `purchase.py:206`, `charge.py:356`,
`attendance.py:341`, `employee.py:523`, `merged_ra.py:204` and twenty more.

On a UTC box:

- **Any document created between 00:00 and 05:30 IST is stamped with the previous
  calendar date.**
- Worse: `pipeline.fy_of()` (`pipeline.py:218-226`) derives the **financial year**
  from that date string. A document raised at 02:00 IST on **1 April** is stamped
  31 March, files under the **closing** FY, and **takes its serial from the wrong
  statutory series** — which `invoice.py:171-173` explains must be unique per FY
  under Rule 46(b).

This is a one-line server fix, which is why it is here and not in §8. Get it
wrong and it is a filing problem discovered a year later.

> 📝 MySQL's `updated_at` column (`db.py:194-196`) also follows the server
> timezone, but **nothing in the application ever reads it** — records carry their
> own `updated_at` written by app code (`charge.py:406`, `project.py:546` and
> others). The column is for forensics only.

### 9.2 Database

```bash
sudo mysql
```

Then run the SQL from §4.3 exactly, including the `@'127.0.0.1'` host pattern.
Verify from the shell:

```bash
mysql -h 127.0.0.1 -u samruddhi -p -e "SELECT 1;" samruddhi_qms
```

This must succeed **over TCP** before you go further. If it fails with
`Access denied`, re-read the `@'127.0.0.1'` vs `@'localhost'` note in §4.3.

### 9.3 Application

```bash
sudo adduser --system --group --home /opt/samruddhi samruddhi
sudo mkdir -p /var/lib/samruddhi/attachments
sudo chown -R samruddhi:samruddhi /var/lib/samruddhi

sudo -u samruddhi git clone <repo> /opt/samruddhi/app
cd /opt/samruddhi/app
sudo -u samruddhi python3 -m venv .venv
sudo -u samruddhi .venv/bin/pip install -r requirements.txt
sudo -u samruddhi .venv/bin/pip install gunicorn==23.0.0   # NOT in requirements.txt — §1.2
```

☠ **Do NOT copy `.env` or `secret_key.txt` from the development machine.** Both
are gitignored (`.gitignore:1-2`), both exist on the dev box right now, and the
dev `.env` holds a real local database password. Write a fresh `.env` on the
server.

Create `/opt/samruddhi/app/.env`, owned by `samruddhi`, mode `600`:

```
DB_ENABLED=true
DB_STRICT=true
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=samruddhi_qms
DB_USER=samruddhi
DB_PASSWORD=<the real one>

SAMRUDDHI_SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">

ATTACHMENT_DIR=/var/lib/samruddhi/attachments

SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax

# ⚠ Demo data OFF. The code already defaults to false (25 September 2026);
#   set it anyway, so nothing about this box is implicit. `true` here seeds
#   12 demo products, 6 addresses with invented GSTINs, a 97-line BOQ headed
#   with another company's name, and a SPECIMEN company identity. See §6.
SAMRUDDHI_DEMO_DATA=false
```

```bash
sudo chown samruddhi:samruddhi .env && sudo chmod 600 .env
```

**Then prove the guards, once, before anything else runs.** ⚠ FIRST RUN — §2.1:
neither guard has ever executed on Linux.

```bash
cd /opt/samruddhi/app

# (1) Correct start — expect the wsgi.py:215-241 banner, then serve.
sudo -u samruddhi .venv/bin/gunicorn --workers 1 --threads 1 \
     --bind 127.0.0.1:8000 --timeout 120 wsgi:application

# The banner must report:
#   single worker  : OK - pid <n> holds /tmp/samruddhi-qms-...lock
#   database       : MySQL samruddhi@127.0.0.1:3306/samruddhi_qms - persistence ON
#   DB_STRICT      : True
#   attachments    : /var/lib/samruddhi/attachments
#   session cookie : Secure=True HttpOnly=True SameSite=Lax
#   users on file  : 0 <-- none: every URL redirects to /setup until one exists

# (2) Guard 1 — must REFUSE (fcntl.flock path, never run before):
sudo -u samruddhi .venv/bin/gunicorn --workers 2 \
     --bind 127.0.0.1:8001 wsgi:application
#     expect the 74-column "REFUSING TO START" banner (wsgi.py:178-203)

# (3) Guard 2 — must 503 every request (real fork(), never run before):
sudo -u samruddhi .venv/bin/gunicorn --workers 1 --preload \
     --bind 127.0.0.1:8002 wsgi:application &
curl -i http://127.0.0.1:8002/
#     expect 503 + "This deployment is running more than one worker."
#     THIS CONFIRMS §2.1: --preload is unusable even at --workers 1.
```

If (2) or (3) behaves differently from the above, **stop** — the POSIX branches of
both guards are unproven, and a surprise there invalidates §2.1.

### 9.4 First administrator

Two equivalent paths (`tools/seed_users.py:4-7`). On a fresh database every URL
redirects to `/setup` (`auth.py:1377-1378`).

```bash
sudo -u samruddhi .venv/bin/python tools/seed_users.py --password "<a real one>"
```

The tool refuses to seed into memory if MySQL is not live
(`tools/seed_users.py:88-94`), enforces ≥ 8 characters (`tools/seed_users.py:48`)
and rejects 25 named placeholders (`tools/seed_users.py:40-46`). It is idempotent
— a re-run leaves an existing user untouched (`tools/seed_users.py:108-116`).

### 9.5 nginx and TLS

```nginx
server {
    listen 443 ssl http2;
    server_name <domain>;

    # ☠ REQUIRED. nginx defaults to 1 MB; attachment.py:130 allows 5 MB.
    # Without this, a 2-5 MB photographed supplier bill — the exact case
    # attachment.py:113 names — is rejected by nginx before Flask ever sees it,
    # and the operator gets a bare nginx 413 with no field named.
    client_max_body_size 8m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;    # match gunicorn --timeout
    }
}
```

Then `certbot --nginx`, and open only 22/80/443 in the Lightsail firewall.
**MySQL 3306 must not be reachable from outside the box.**

> ✅ **No `ProxyFix` is required, and this was checked rather than assumed.** A
> grep across every module for `ProxyFix`, `_external`, `remote_addr`,
> `is_secure` and `X-Forwarded` returns **zero hits**. The application never
> builds an absolute URL, never reads the client IP, and never branches on
> scheme. The `X-Forwarded-*` headers above are set for nginx's own logs and for
> whatever comes later; the app ignores them. `SESSION_COOKIE_SECURE=true` works
> regardless, because Flask sets the flag unconditionally rather than inferring
> it from the request.

### 9.6 systemd

`/etc/systemd/system/samruddhi.service`:

```ini
[Unit]
Description=Samruddhi Fire QMS
After=network.target mysql.service
Requires=mysql.service

[Service]
Type=simple
User=samruddhi
Group=samruddhi
WorkingDirectory=/opt/samruddhi/app
ExecStart=/opt/samruddhi/app/.venv/bin/gunicorn \
    --workers 1 --threads 1 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile - --error-logfile - \
    wsgi:application
Restart=always
RestartSec=5

# The banner and every persistence warning go to stderr/stdout — db.py:459,
# auth.py:1480, wsgi.py:305. journald is the only place they land: the app
# configures no logging of its own (§8.3).
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

⚠ **Do not add `--preload`** (§2.1). ⚠ **Do not raise `--workers`** (§2.1).

On `PrivateTmp=`: leaving it unset is simplest. If you set `PrivateTmp=true`, the
lock file (`wsgi.py:122`) moves into the unit's private `/tmp`, which is still
correct for a single service — but a manual `gunicorn` run outside systemd would
then no longer see it, which breaks the guard test in 9.3.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now samruddhi
sudo journalctl -u samruddhi -f     # read the boot banner
```

### 9.7 ☠ Settings — before any real document

**Do §6.3 now.** Not after the first invoice.

---

## 10. BACKUPS

**A backup of this application is TWO files, not one** — `tools/backup_db.py:13-27`.

`attachment.py:428-434` writes uploaded files to disk and stores only a
**relative path** on the database row. A `mysqldump` therefore captures the
attachment *metadata* and **not the files**. Restoring the dump alone gives rows
pointing at nothing, and `attachment.abs_path()` (`attachment.py:239-266`)
resolves them to a path that does not exist — every download 404s, **silently,
one row at a time.**

The supplied tool writes both halves under one shared stem
(`tools/backup_db.py:24-28`):

```bash
cd /opt/samruddhi/app
sudo -u samruddhi .venv/bin/python tools/backup_db.py --label nightly
# -> backups/samruddhi_qms-<stamp>-nightly.sql
# -> backups/samruddhi_qms-<stamp>-nightly-attachments.zip
```

Notes:

- It reads the same `.env` the app does (`tools/backup_db.py:36-38`), so it always
  backs up the database actually in use.
- It needs `mysqldump` on PATH (`tools/backup_db.py:63-75`) — the `mysql-client`
  package from §9.1.
- It writes to `<repo>/backups` (`tools/backup_db.py:60`), which is gitignored
  (`.gitignore:15`). **Ship those files off the box** — one Lightsail instance
  with the backups on the same SSD is not a backup.
- The dump contains the settings row; `tools/backup_db.py:42-43` says to treat
  both files as confidential.
- The zip is written even when the store is empty, deliberately
  (`tools/backup_db.py:32-36`) — "there were no attachments that day" is a fact a
  restore needs to be able to trust.

Add a nightly timer, and take one **before** `tools/seed_users.py` and before
anything in §8 ships (`tools/seed_users.py:22-23`).

---

## 11. WHAT TO WATCH AFTER GO-LIVE

| Signal | Where | Meaning |
|---|---|---|
| Red strip under the nav | rendered from `db.failure_note()` (`db.py:286-324`) | **A user's work is not being saved.** The raw error hangs off the strip's `title=` (`db.py:327-341`). |
| `!! persistence failed on '<coll>'` | journald, `db.py:459` | Printed only when the message *changes* (`db.py:455-458`), so a repeat is not suppressed noise — it is a new fault. |
| `* persistence recovered on '<coll>'` | journald, `db.py:466` | The retry landed. Failures are per-collection and per-request, never global (`db.py:486-492`). |
| `REFUSING TO START` banner | journald, `wsgi.py:178-203` | Someone added a worker. §2.1. |
| `SECRET_KEY IS NOT SET` banner | journald, `auth.py:1480` → `auth.py:224-250` | `SAMRUDDHI_SECRET_KEY` is missing and a local key is in use. §3.1. |
| `<-- SESSION_COOKIE_SECURE is FALSE` | boot banner, `wsgi.py:235-236` | The session token is travelling in clear. |
| A page that "went back to the dashboard" | nothing is logged | **Possibly a 500** (`app.py:224-227`). Until §8.3 is done, there is no way to tell this from a user clicking Home. |

---

## 12. GO-LIVE CHECKLIST

- [ ] `timedatectl` reports `Asia/Kolkata` — §9.1a
- [ ] `mysql -h 127.0.0.1 -u samruddhi -p` succeeds over TCP — §9.2
- [ ] `.env` is mode 600, owned by `samruddhi`, and was **written fresh on the server**
- [ ] `SAMRUDDHI_SECRET_KEY` is set (boot banner shows **no** key warning)
- [ ] Boot banner: `DB_STRICT : True`
- [ ] Boot banner: `session cookie : Secure=True HttpOnly=True SameSite=Lax`
- [ ] Boot banner: `attachments : /var/lib/samruddhi/attachments` (outside the checkout)
- [ ] Guard 1 refuses `--workers 2` — §9.3(2) ⚠ first run on Linux
- [ ] Guard 2 503s under `--preload` — §9.3(3) ⚠ first run on Linux
- [ ] systemd `ExecStart` contains **no** `--preload`, and `--workers 1`
- [ ] nginx `client_max_body_size 8m`, and a 4 MB PDF uploads successfully
- [ ] TLS live; 3306 not reachable from outside the box
- [ ] First Owner created; `/setup` no longer reachable
- [ ] **`/settings` fully populated with the client's real GSTIN, PAN and bank details — §6.3**
- [ ] **One document of each type printed and the letterhead read by a human** — no `27AAAAA0000A1Z5`, no `SPECIMEN BANK LTD.`
- [ ] Demo BOQ ("Sify Bangalore" / "Prudent Teqtis Pvt Ltd"), demo products, demo specs and demo addresses deleted — *and the team told they return on restart until §8.1 ships*
- [ ] Client informed: **approvals are switched off** (`approval.py:307`) and the **product catalogue is hidden** (`auth.py:486`)
- [ ] Backup pair taken and copied **off the box** — §10
- [ ] §8.3 (error logging) scheduled, ideally done before the first real document
