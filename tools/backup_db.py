"""
tools/backup_db.py — take a backup before anything destructive.

Run it before any operation that could lose data: dropping or truncating a
table, dropping the database, a schema change, or a migration script. It is
cheap and it is the difference between "we can put that back" and "that is
gone".

    python tools/backup_db.py                 # writes the PAIR, see below
    python tools/backup_db.py --label pre-ra  # ...-pre-ra.sql / ...-pre-ra-attachments.zip
    python tools/backup_db.py --restore-attachments backups/<name>-attachments.zip

⚠ **A BACKUP OF THIS APPLICATION IS TWO FILES, NOT ONE** (CC-2 **B8**,
  2 September 2026). `attachment.py` keeps uploaded files on disk under
  `attachment.root()` and puts only a **relative path** on the database record,
  so a `mysqldump` covers strictly less than the whole of the application's
  state: the metadata rows are in the dump and **the files are not**. Restoring
  the dump alone gives rows pointing at files that do not exist —
  `attachment.abs_path()` resolves them to a path that is not there and every
  download 404s, silently and one row at a time. ABOUT.md §4 is the long form.

  So one run writes **both halves, under one stamp and one label**:

      backups/samruddhi_qms-20260903-2242-pre-ra.sql              the database
      backups/samruddhi_qms-20260903-2242-pre-ra-attachments.zip  the files

  **The pair shares a stem** so the two halves of one moment cannot be
  mismatched by eye at restore time, and that is the whole of the naming rule.
  Retention is the same as it has always been for `backups/`: dated files,
  never pruned, gitignored, confidential.

  ⚠ **The zip is written even when the store is empty**, and that is
  deliberate. An absent file cannot be told apart from a snapshot that failed,
  and "there were no attachments that day" is exactly the fact a restore needs
  to be able to trust.

Reads the same `.env` the app does, so it always backs up the database the app
is actually using rather than one hardcoded here. `mysqldump` is found on PATH
or in the usual MySQL Server install location on Windows.

⚠ The dump contains the whole database, including the settings row. Treat both
  files as confidential; `backups/` is gitignored.
"""

import argparse
import datetime
import glob
import os
import pathlib
import subprocess
import sys
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import attachment as _att  # noqa: E402  (reads ATTACHMENT_DIR on every call)
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


def _stem(label: str = "") -> str:
    """The shared stem both halves of one backup are named from."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{_db.CONFIG['name']}-{stamp}" + (f"-{label}" if label else "")


def backup_attachments(stem: str) -> pathlib.Path:
    """
    Snapshot `attachment.root()` to `backups/<stem>-attachments.zip`.

    ⚠ **Paths in the archive are RELATIVE to the store root**, which is the same
    contract `attachment.stored_path` keeps and for the same reason: an absolute
    path publishes the disk layout of the machine that took the backup into an
    archive that gets handed around, and it would stop the store being restored
    anywhere but where it came from. `restore_attachments()` below is the other
    half of that contract.

    ⚠ **`attachment.root()` is called, never `REPO / "attachments"`.** The store
    is relocatable with `ATTACHMENT_DIR` precisely so a deployment can put it on
    another volume, and a backup that hardcoded the default would quietly
    snapshot an empty directory on exactly the machine that had moved it.
    """
    root = _att.root()
    out = BACKUP_DIR / f"{stem}-attachments.zip"

    files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(root).as_posix())

    # The dump's own "refusing to call that a backup" check, in the shape this
    # payload allows. A byte-size floor cannot work here — an empty store is a
    # legitimate snapshot and compresses to 22 bytes — so what is verified is
    # that the archive re-opens and holds exactly what was walked.
    with zipfile.ZipFile(out) as zf:
        if zf.testzip() is not None:
            raise SystemExit(f"attachment archive {out} is corrupt — not a backup")
        got = len(zf.namelist())
    if got != len(files):
        raise SystemExit(
            f"attachment archive holds {got} entries, expected {len(files)} — not a backup")

    print(f"attachments written: {out}  ({out.stat().st_size:,} bytes, "
          f"{len(files)} file(s) from {root})")
    return out


def restore_attachments(archive, root=None) -> int:
    """
    Unpack an attachments archive back into the store. Returns the file count.

    ⚠ **Additive, never destructive.** It restores what the archive holds and
    does not remove anything already in the store: a restore is run when files
    are missing, and deleting a file that survived the incident the restore is
    answering would be the tool causing the loss it exists to undo. An existing
    file of the same relative path IS overwritten, because the archive is the
    authority on what that path should contain.

    ⚠ **Every member is re-validated against the root before extraction.**
    `ZipFile.extractall` is safe in modern CPython, but this archive reaches the
    tool from the filesystem — a different trust boundary from the one it was
    written across — and `attachment.abs_path()` makes exactly the same argument
    about a `stored_path` arriving from the database. A member naming
    `../../app.py` is refused rather than sanitised.
    """
    archive = pathlib.Path(archive)
    if not archive.is_file():
        raise SystemExit(f"no such archive: {archive}")
    root = pathlib.Path(root).resolve() if root else _att.root()
    root.mkdir(parents=True, exist_ok=True)

    written = 0
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            dest = (root / name).resolve()
            if dest != root and root not in dest.parents:
                raise SystemExit(f"archive member escapes the store root: {name!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            written += 1

    print(f"attachments restored: {written} file(s) into {root}")
    return written


def backup(label: str = "") -> tuple:
    """The pair. Returns `(sql_path, zip_path)`."""
    cfg = _db.CONFIG
    BACKUP_DIR.mkdir(exist_ok=True)
    stem = _stem(label)
    out = BACKUP_DIR / f"{stem}.sql"

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

    # ⚠ **After the dump, and it raises rather than warning.** A half-taken
    #   backup that reports success is the failure mode this whole file exists
    #   to prevent, and the caller is usually about to do something
    #   destructive. The `.sql` is deliberately NOT unlinked on this path — it
    #   is valid, it is the more expensive half to retake, and destroying data
    #   on the way out of a backup tool is indefensible.
    zip_out = backup_attachments(stem)
    return out, zip_out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="", help="suffix for the filename")
    ap.add_argument("--restore-attachments", metavar="ZIP", default="",
                    help="unpack an attachments archive back into the store "
                         "and exit; takes no backup")
    args = ap.parse_args()
    if args.restore_attachments:
        restore_attachments(args.restore_attachments)
    else:
        backup(args.label)
