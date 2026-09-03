"""
The second half of a backup — `tools/backup_db.py`'s attachment archive.

`tools/` is not imported by the app, so nothing else in this suite would notice
if this script rotted — `tests/test_strip_certification.py` makes the same
point about the same directory, and this file borrows its loader.

**Why this exists at all.** B8 (2 September 2026) put uploaded files on disk and
only a relative path on the database record, so from that day a `mysqldump`
stopped being a backup of this application: the metadata rows are in the dump
and the files are not. Restoring the dump alone gives rows pointing at files
that are not there, `attachment.abs_path()` resolves them to a path that does
not exist, and every download 404s — silently, one row at a time, with nothing
anywhere reporting that the restore was half a restore. ABOUT.md §4 is the long
form and CLIENT_CHANGES.md §0's 3 September 2026 block is the authorisation.

⚠ **The property under test is that a FILE comes back, never that a row does.**
A test asserting the archive merely exists, or that its entry count is right,
would pass against an archive of absolute paths that no other machine can
restore. Every test below that matters reads bytes off the disk afterwards.
"""

import hashlib
import importlib.util
import pathlib
import sys
import zipfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

PNG = bytes.fromhex("89504e470d0a1a0a") + b"backup-round-trip" + bytes(32)


def _load():
    """Import the script by path — `tools/` is not a package on sys.path."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location(
        "backup_db", REPO / "tools" / "backup_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def bk(tmp_path, monkeypatch):
    """
    The tool, with both directories pointed somewhere disposable.

    `ATTACHMENT_DIR` is already a per-test temporary directory — conftest's
    autouse `_attachment_store` fixture sets it, and `attachment.root()` re-reads
    the environment on every call rather than caching it, which is what makes
    that work here as well as in the app.
    """
    mod = _load()
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    mod.BACKUP_DIR.mkdir()
    return mod


def _plant(bk, rel: str, payload: bytes = PNG) -> pathlib.Path:
    """One file in the attachment store, at the nested shape `save()` writes."""
    import attachment as att

    p = att.root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(payload)
    return p


# =============================================================================
# 1. THE ARCHIVE
# =============================================================================

def test_the_archive_holds_every_file_in_the_store(bk):
    """The walk is recursive — `save()` nests one directory per parent type."""
    _plant(bk, "charge/aaaa.png")
    _plant(bk, "charge/bbbb.png")
    _plant(bk, "receipt/cccc.png")

    out = bk.backup_attachments("stem")

    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == [
            "charge/aaaa.png", "charge/bbbb.png", "receipt/cccc.png"]


def test_paths_in_the_archive_are_RELATIVE_to_the_store_root(bk):
    """
    ⚠ **The property the round trip rests on**, and the one a count check
    cannot see. An absolute path publishes the disk layout of the machine that
    took the backup and cannot be restored anywhere else — the same argument
    `attachment.stored_path` makes about the database record.

    ⚠ **The assertion has to be an EQUALITY against the store's own relative
    paths, and the weaker version of this test was vacuous.** It began life
    asserting only that no member was absolute, carried a drive letter or held a
    backslash — and `zipfile.write()` with no `arcname` *already* strips the
    drive and the leading separator, so an archive of
    `Users/manas/.../attachments/charge/aaaa.png` passed all three checks while
    being exactly the unrestorable thing the test was written to forbid. Caught
    by mutation on 3 September 2026, which is the only reason it is known.

    Non-vacuous by mutation: changing `zf.write(p, p.relative_to(root)...)` to
    `zf.write(p)` now fails on the equality.
    """
    import attachment as att

    _plant(bk, "charge/aaaa.png")
    _plant(bk, "receipt/nested/bbbb.png")
    root = att.root()

    with zipfile.ZipFile(bk.backup_attachments("stem")) as zf:
        names = zf.namelist()
        assert set(names) == {p.relative_to(root).as_posix()
                              for p in root.rglob("*") if p.is_file()}
        for name in names:
            assert not pathlib.PurePosixPath(name).is_absolute(), name
            assert ":" not in name, f"a drive letter reached the archive: {name!r}"
            assert "\\" not in name, f"a backslash reached the archive: {name!r}"


def test_an_empty_store_still_produces_an_archive(bk):
    """
    ⚠ **Deliberate.** An absent file cannot be told apart from a snapshot that
    failed, and "there were no attachments that day" is exactly the fact a
    restore needs to be able to trust.
    """
    out = bk.backup_attachments("stem")

    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == []


def test_a_store_that_does_not_exist_yet_is_not_an_error(bk):
    """A clone that has never had an upload has no `attachments/` directory."""
    import attachment as att
    import shutil

    shutil.rmtree(att.root())
    assert not att.root().exists()

    with zipfile.ZipFile(bk.backup_attachments("stem")) as zf:
        assert zf.namelist() == []


def test_the_archive_is_named_from_the_same_stem_as_the_dump(bk):
    """
    The pair shares a stem so the two halves of one moment cannot be mismatched
    by eye at restore time. That is the whole of the naming rule.
    """
    out = bk.backup_attachments("samruddhi_qms-20260903-2242-pre-ra")

    assert out.name == "samruddhi_qms-20260903-2242-pre-ra-attachments.zip"
    assert out.parent == bk.BACKUP_DIR


def test_the_entry_count_is_verified_and_a_short_archive_is_refused(bk, monkeypatch):
    """
    The dump's own "refusing to call that a backup" check, in the shape this
    payload allows: a byte floor cannot work when an empty store is legitimate.

    Non-vacuous by mutation: this drops one file between the walk and the
    verification, which is what a silently-skipped write would look like.
    """
    _plant(bk, "charge/aaaa.png")
    _plant(bk, "charge/bbbb.png")

    real_write = zipfile.ZipFile.write
    state = {"n": 0}

    def lossy(self, filename, arcname=None, *a, **kw):
        state["n"] += 1
        if state["n"] == 2:          # the second file never lands
            return None
        return real_write(self, filename, arcname, *a, **kw)

    monkeypatch.setattr(zipfile.ZipFile, "write", lossy)

    with pytest.raises(SystemExit) as exc:
        bk.backup_attachments("stem")
    assert "expected 2" in str(exc.value)


# =============================================================================
# 2. THE RESTORE — the half that makes the archive a backup
# =============================================================================

def test_a_deleted_file_comes_back_BYTE_FOR_BYTE(bk):
    """
    ⚠ **THE TEST THIS FILE EXISTS FOR.** Not that the row came back — that the
    FILE did, with the same bytes, into the same relative path, after its whole
    directory was destroyed.
    """
    import shutil

    import attachment as att

    planted = _plant(bk, "charge/deadbeef.png")
    before = hashlib.sha256(planted.read_bytes()).hexdigest()
    out = bk.backup_attachments("stem")

    shutil.rmtree(att.root() / "charge")
    assert not planted.exists(), "the fixture failed to delete the file"

    assert bk.restore_attachments(out) == 1

    assert planted.exists(), "the archive restored a row and not a file"
    assert hashlib.sha256(planted.read_bytes()).hexdigest() == before


def test_the_restore_rebuilds_directories_it_needs(bk):
    """`save()` nests by parent type, so a restore into an empty store has to
    recreate the tree and not just the leaves."""
    import shutil

    import attachment as att

    _plant(bk, "receipt/nested/deep.png")
    out = bk.backup_attachments("stem")
    shutil.rmtree(att.root())

    bk.restore_attachments(out)

    assert (att.root() / "receipt" / "nested" / "deep.png").is_file()


def test_the_restore_is_ADDITIVE_and_deletes_nothing(bk):
    """
    ⚠ A restore is run when files are missing. Deleting a file that survived
    the incident the restore is answering would make the tool cause the loss it
    exists to undo.
    """
    _plant(bk, "charge/in-archive.png")
    out = bk.backup_attachments("stem")

    survivor = _plant(bk, "charge/never-archived.png", b"%PDF-1.4 survivor")

    bk.restore_attachments(out)

    assert survivor.is_file(), "the restore deleted a file the archive did not hold"
    assert survivor.read_bytes() == b"%PDF-1.4 survivor"


def test_an_archive_member_escaping_the_store_root_is_REFUSED(bk, tmp_path):
    """
    The archive reaches this tool from the filesystem, which is a different
    trust boundary from the one it was written across —
    `attachment.abs_path()` makes exactly the same argument about a
    `stored_path` arriving from the database.

    Non-vacuous by mutation: deleting the two-line `root not in dest.parents`
    check writes `escaped.txt` outside the store and this fails on the last
    assertion rather than the first.
    """
    import attachment as att

    evil = bk.BACKUP_DIR / "evil-attachments.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../escaped.txt", b"pwned")

    with pytest.raises(SystemExit) as exc:
        bk.restore_attachments(evil)
    assert "escapes the store root" in str(exc.value)

    assert not (att.root().parent.parent / "escaped.txt").exists()


def test_a_missing_archive_is_refused_rather_than_silently_doing_nothing(bk):
    """A restore that quietly restores nothing is the failure this tool exists
    to prevent, one step along."""
    with pytest.raises(SystemExit) as exc:
        bk.restore_attachments(bk.BACKUP_DIR / "not-here-attachments.zip")
    assert "no such archive" in str(exc.value)


# =============================================================================
# 3. THE STORE IS RELOCATABLE, AND THE BACKUP HAS TO FOLLOW IT
# =============================================================================

def test_the_backup_follows_ATTACHMENT_DIR_and_not_the_default(bk, tmp_path, monkeypatch):
    """
    ⚠ `ATTACHMENT_DIR` exists so a deployment can put the store on another
    volume. A backup that hardcoded `<repo>/attachments/` would quietly snapshot
    an empty directory on exactly the machine that had moved it — and report
    success.

    Non-vacuous by mutation: replacing `_att.root()` in `backup_attachments()`
    with `REPO / "attachments"` empties the namelist and this fails.
    """
    moved = tmp_path / "on-another-volume"
    moved.mkdir()
    monkeypatch.setenv("ATTACHMENT_DIR", str(moved))
    (moved / "charge").mkdir()
    (moved / "charge" / "elsewhere.png").write_bytes(PNG)

    with zipfile.ZipFile(bk.backup_attachments("stem")) as zf:
        assert zf.namelist() == ["charge/elsewhere.png"]


# =============================================================================
# 4. THE PAIR — the naming contract the operator reads at restore time
# =============================================================================

def test_backup_returns_BOTH_halves(bk, monkeypatch):
    """
    `backup()` is the entry point every caller uses, and after B8 a backup is
    two files. A caller that got one path back would have no way to reach the
    other except by reconstructing the name.

    `mysqldump` is not run here — the subprocess and the schema check are the
    dump's own business and are stubbed, because what is under test is that the
    attachment half happens at all and that both paths are returned.
    """
    _plant(bk, "charge/aaaa.png")

    def fake_run(cmd, **kw):
        pathlib.Path(kw["stdout"].name).write_text("-- dump\n" + "x" * 200)

        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(bk.subprocess, "run", fake_run)
    monkeypatch.setattr(bk, "_mysqldump", lambda: "mysqldump")

    sql, zip_out = bk.backup("pre-ra")

    assert sql.suffix == ".sql" and zip_out.name.endswith("-attachments.zip")
    assert zip_out.name.startswith(sql.stem), (
        "the two halves of one backup do not share a stem, so a restore has to "
        "match them by timestamp arithmetic")
    with zipfile.ZipFile(zip_out) as zf:
        assert zf.namelist() == ["charge/aaaa.png"]
