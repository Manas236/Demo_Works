"""
`docs/ACCESS_MATRIX.md` is generated, and this is what keeps it that way.

The document exists so the client-facing owner can walk seven roles and 61
permissions past the client without reading `auth.py`. That is only worth
anything if it says what the code says. A hand-maintained table would be right
on the day it was written and wrong on the day after the first role edit — and
wrong *silently*, which is worse than absent, because somebody would be
briefing a client off it.

So: the file on disk must equal what the generator produces right now. If a
permission is added, a role edited, or an endpoint reclassified, this goes red
and the fix is one command.
"""

import subprocess
import sys

import pytest

import auth


REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "ACCESS_MATRIX.md"
TOOL = REPO / "tools" / "dump_access_matrix.py"


def _generated() -> str:
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import dump_access_matrix
        import importlib
        importlib.reload(dump_access_matrix)
        return dump_access_matrix.build()
    finally:
        sys.path.remove(str(REPO / "tools"))


def test_the_access_matrix_on_disk_matches_the_code():
    """
    The whole point of the file. Regenerate with:

        python tools/dump_access_matrix.py
    """
    assert DOC.exists(), f"{DOC} is missing — run python tools/dump_access_matrix.py"
    assert DOC.read_text(encoding="utf8") == _generated(), (
        "docs/ACCESS_MATRIX.md is out of date — a permission, a role or a "
        "route classification has changed since it was written. Regenerate it:\n"
        "    python tools/dump_access_matrix.py\n"
        "Do not edit the file by hand; it is generated from auth.py.")


def test_the_check_mode_actually_checks():
    """
    The control. `--check` is what a person or a hook would run, and a
    `--check` that always exits 0 is worse than no check at all.
    """
    ok = subprocess.run([sys.executable, str(TOOL), "--check"],
                        capture_output=True, text=True, cwd=str(REPO))
    assert ok.returncode == 0, f"--check failed on an up-to-date file: {ok.stdout}{ok.stderr}"
    assert "up to date" in ok.stdout


def test_every_role_and_permission_reaches_the_document():
    """
    A generated document can still be generated *wrongly* — a loop that skips a
    group, or a role list that has quietly gone stale, produces a file that
    matches itself perfectly and describes two thirds of the system.

    So this checks coverage rather than equality: every permission id and every
    role's display name is somewhere in the text.
    """
    text = DOC.read_text(encoding="utf8")

    missing_perms = sorted(p for p in auth.PERMISSIONS if f"`{p}`" not in text)
    assert not missing_perms, (
        f"these permissions exist but do not appear in the access matrix: "
        f"{missing_perms}")

    missing_roles = sorted(name for name, _ in auth.BUILTIN_ROLES.values()
                           if name not in text)
    assert not missing_roles, (
        f"these roles exist but do not appear in the access matrix: "
        f"{missing_roles}")


def test_the_document_marks_derived_cells_as_derived():
    """
    The reason the file was asked for.

    CLIENT_CHANGES-2.md carries no per-role grid, so almost every cell is our
    starting position rather than the client's instruction — and the 26 August
    override block in CLIENT_CHANGES.md §0 says in as many words that it
    "should be walked through with the client rather than presented as what he
    asked for."

    A version of this document that dropped the marking would look finished and
    would let somebody present our guesses as his decisions. That is the
    failure this test exists to catch, so it is asserted rather than trusted to
    the generator's good intentions.
    """
    text = DOC.read_text(encoding="utf8")

    assert "CLIENT_CHANGES-2.md contains no per-role permission grid" in text, (
        "the document no longer states that the grid is mostly derived")
    assert "starting position we chose" in text
    assert "Our derivation" in text
    # And the marks are really in the tables, not only in the legend.
    assert text.count("| · |") > 20, (
        "the derivation mark barely appears in the grid — the cells are no "
        "longer being marked")


@pytest.mark.parametrize("slug", sorted(auth.BUILTIN_ROLES))
def test_every_role_has_a_plain_english_description(slug):
    """
    Section 3 is the half a non-developer reads. A role added to
    `BUILTIN_ROLES` without a paragraph would appear in the grid as a column of
    marks and nowhere in words.

    The generator refuses to run in that state; this says so at the level of
    the individual role, so the failure names which one.
    """
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import dump_access_matrix
        assert slug in dump_access_matrix.ROLE_NOTES, (
            f"role {slug!r} has no plain-English description in "
            f"tools/dump_access_matrix.py ROLE_NOTES")
        note = dump_access_matrix.ROLE_NOTES[slug]
        assert note["can"].strip() and note["cannot"].strip()
    finally:
        sys.path.remove(str(REPO / "tools"))


def test_the_prose_is_checked_against_the_grid_rather_than_trusted():
    """
    The control for the generator's own safety net.

    `build()` verifies every "this role can/cannot do X" claim against the live
    permission set and refuses to write the file if one is wrong. That guard is
    the only thing stopping the prose drifting away from the table it sits
    under — so this proves the guard fires, by feeding it a claim that is
    false.
    """
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import dump_access_matrix as tool

        note = tool.ROLE_NOTES["accountant"]
        note["claims"]["holds"].append("boq.create")
        try:
            with pytest.raises(SystemExit) as raised:
                tool.build()
            assert "boq.create" in str(raised.value)
        finally:
            note["claims"]["holds"].remove("boq.create")

        # And it still builds once the false claim is withdrawn.
        assert tool.build()
    finally:
        sys.path.remove(str(REPO / "tools"))
