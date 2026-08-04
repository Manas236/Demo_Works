"""
tools/backup_db.py — take a mysqldump before anything destructive.

Run it before any operation that could lose data: dropping or truncating a
table, dropping the database, a schema change, or a migration script. It is
cheap and it is the difference between "we can put that back" and "that is
gone".

    python tools/backup_db.py                 # writes backups/<db>-<stamp>.sql
    python tools/backup_db.py --label pre-ra  # ...-pre-ra.sql

Reads the same `.env` the app does, so it always backs up the database the app
is actually using rather than one hardcoded here. `mysqldump` is found on PATH
or in the usual MySQL Server install location on Windows.

⚠ The dump contains the whole database, including the settings row. Treat it
  as confidential; `backups/` is gitignored.
"""

import argparse
import datetime
import glob
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import db as _db  # noqa: E402  (reads .env on import)

BACKUP_DIR = REPO / "backups"


def _mysqldump() -> str:
    """The mysqldump binary — PATH first, then the standard Windows install."""
    from shutil import which

    found = which("mysqldump")
    if found:
        return found
    for pattern in (r"C:\Program Files\MySQL\MySQL Server*\bin\mysqldump.exe",
                    r"C:\Program Files (x86)\MySQL\MySQL Server*\bin\mysqldump.exe"):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    raise SystemExit("mysqldump not found — add it to PATH and re-run")


def backup(label: str = "") -> pathlib.Path:
    cfg = _db.CONFIG
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{cfg['name']}-{stamp}" + (f"-{label}" if label else "") + ".sql"
    out = BACKUP_DIR / name

    cmd = [_mysqldump(),
           f"--host={cfg['host']}", f"--port={cfg['port']}",
           f"--user={cfg['user']}",
           "--databases", cfg["name"],
           "--routines", "--events", "--single-transaction",
           "--add-drop-database"]

    env = dict(os.environ)
    if cfg["password"]:
        # Via the environment, never on the command line — argv is visible to
        # every other process on the machine.
        env["MYSQL_PWD"] = cfg["password"]

    with open(out, "w", encoding="utf8") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE,
                              text=True, env=env)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise SystemExit(f"mysqldump failed:\n{proc.stderr}")

    size = out.stat().st_size
    if size < 100:
        raise SystemExit(f"dump is only {size} bytes — refusing to call that a backup")
    print(f"backup written: {out}  ({size:,} bytes)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="", help="suffix for the filename")
    backup(ap.parse_args().label)
