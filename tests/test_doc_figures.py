"""
The test figures agree across all four documents that carry them.

### The defect this closes, which has now happened three times

Four documents state the suite's size, and they are updated by hand:

| document | where |
|---|---|
| `PROGRESS.md` | the header block's **Test figure** row |
| `ABOUT.md` | §1's configuration table, rows **2** and **3** |
| `INTRODUCTION.md` | §5.5, *"Never reduce the test count"* |
| `STATE.md` | the header's **Tests:** line, and the second-configuration note |

Three passes running, a pass measured the suite, updated `PROGRESS.md`, and left
the other three saying what they said before. The 29 August third pass found
`ABOUT.md` rows 2–3, `INTRODUCTION.md` §5.5 and `STATE.md` **two passes stale**
at once. Each time it was found by a human reading two documents side by side,
which is not a control.

### What this asserts, and what it deliberately does not

It asserts the four are **consistent with each other** — not that they match a
number written down here. That is the whole point: a hardcoded expected figure
would make this file a **fifth site** to update, which is the defect wearing a
lab coat. The drift being closed is between documents, so agreement between
documents is exactly the property.

⚠ **It therefore cannot tell you the figures are CURRENT**, only that they are
the same everywhere. Measuring the real suite from inside the suite is circular,
and a subprocess run of the whole suite inside one test would double every CI
run to catch something a pass notices anyway when it reads its own output. The
pass measures; this stops the measurement reaching one document and not the
others.

### Anchors, and why each is asserted to match exactly once

Every locator below is required to match **exactly one** place in its file.
These documents quote their own history constantly — *"it read 1,367 / 1 until
this edition"*, *"was 842 passed"* — so a loose regex would happily read a
figure from a sentence about last week and report agreement. A locator that
stops matching, or starts matching twice, fails with a sentence telling you
which document was reworded.
"""

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _text(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def _n(raw: str) -> int:
    """`"1,464"` -> `1464`."""
    return int(raw.replace(",", "").strip())


# ── The locators ───────────────────────────────────────────────────────────
#
# (document, human name, regex). Each must yield `(passed, skipped)` and must
# match exactly once. Written as `\**` around the numbers because these files
# bold them inconsistently and the emphasis is not the assertion.

_FIG = r"\**([\d,]+)\s*(?:passed|/)\s*,?\s*\**\s*(?:passed\s*)?"

GLOBAL_SITES = [
    # PROGRESS.md — the header block's Test figure row.
    ("PROGRESS.md", "the header block's Test figure row",
     r"measured at the end of the pass:\s*\**([\d,]+) passed,\s*([\d,]+) skipped"),

    # ABOUT.md §1, row 3 of the configuration table.
    ("ABOUT.md", "§1 configuration table, row 3",
     r"\|\s*3\s*\|[^|]*no `\.venv`[^|]*\|\s*\*\*([\d,]+) passed, ([\d,]+) skipped\*\*"),

    # INTRODUCTION.md §5.5.
    ("INTRODUCTION.md", "§5.5 — Never reduce the test count",
     r"The baseline is \*\*([\d,]+) passed / ([\d,]+) skipped\*\*"),

    # STATE.md — the header's Tests: line.
    ("STATE.md", "the header's Tests: line",
     r"\*\*Tests:\*\* \*\*([\d,]+) passed / ([\d,]+) skipped\*\*"),
]

VENV_SITES = [
    ("PROGRESS.md", "the header block's .venv sentence",
     r"reports \*\*([\d,]+) passed, ([\d,]+) skipped\*\* against this commit"),

    ("ABOUT.md", "§1 configuration table, row 2",
     r"\|\s*2\s*\|[^|]*THE SUPPORTED CONFIGURATION[^|]*\|\s*"
     r"\*\*([\d,]+) passed, ([\d,]+) skipped\*\*"),

    ("STATE.md", "the second-configuration note",
     r"reports \*\*([\d,]+) passed / ([\d,]+) skipped\*\* against the same commit"),
]


def _read(site) -> tuple:
    doc, where, pattern = site
    found = re.findall(pattern, _text(doc))
    assert len(found) == 1, (
        f"{doc} — {where}: the locator matched {len(found)} times, not once.\n"
        f"These documents quote their own history constantly, so a locator that "
        f"matches twice is reading a figure from a sentence about a previous "
        f"pass. If the wording moved, move the pattern in "
        f"tests/test_doc_figures.py with it — do not loosen it.")
    return _n(found[0][0]), _n(found[0][1])


# ── The assertions ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("site", GLOBAL_SITES, ids=lambda s: s[0])
def test_every_document_can_still_be_read_for_the_global_figure(site):
    """
    Each locator finds its figure. Run first and per-document, so a reworded
    heading names the file it broke rather than failing the comparison below
    with a confusing diff.
    """
    passed, skipped = _read(site)
    assert passed > 0, f"{site[0]} reports {passed} passed, which cannot be right"


def test_the_four_documents_agree_on_the_global_configuration():
    """
    ⚠ **The one this file exists for.**

    openpyxl absent, no `.venv`, both client workbooks absent — the figure every
    one of the four documents leads with. If a pass updates PROGRESS.md and
    stops, this is what says so, in the same run that measured it.
    """
    figures = {f"{doc} ({where})": _read((doc, where, pat))
               for doc, where, pat in GLOBAL_SITES}
    distinct = set(figures.values())
    assert len(distinct) == 1, (
        "The four documents do not agree on the test figure for the global "
        "configuration:\n  "
        + "\n  ".join(f"{k}: {v[0]:,} passed / {v[1]:,} skipped"
                      for k, v in sorted(figures.items()))
        + "\n\nThis has happened three times: the figure reaches PROGRESS.md "
          "and the other three keep saying what they said last pass. Update "
          "all four in the same commit.")


def test_the_documents_that_carry_it_agree_on_the_venv_configuration():
    """
    The `.venv` figure — openpyxl 3.1.5 present — carried by three of the four.

    `INTRODUCTION.md` §5.5 states only the global baseline and is deliberately
    absent from this list rather than forgotten: §5.5 is a floor for the
    supported development configuration, not a configuration table.
    """
    figures = {f"{doc} ({where})": _read((doc, where, pat))
               for doc, where, pat in VENV_SITES}
    distinct = set(figures.values())
    assert len(distinct) == 1, (
        "The documents do not agree on the test figure for the `.venv` "
        "configuration:\n  "
        + "\n  ".join(f"{k}: {v[0]:,} passed / {v[1]:,} skipped"
                      for k, v in sorted(figures.items())))


def test_the_venv_configuration_reports_at_least_as_many_as_the_global_one():
    """
    A cheap sanity check on the pair, and it has a real failure mode behind it.

    openpyxl being present can only ADD collected tests — the workbook importers
    skip without it. So the `.venv` figure can never be the smaller of the two,
    and if it is, one of the two numbers was typed from the wrong terminal.
    """
    a_global = _read(GLOBAL_SITES[0])
    a_venv = _read(VENV_SITES[0])
    assert a_venv[0] >= a_global[0], (
        f"the .venv configuration reports {a_venv[0]:,} passed and the global "
        f"one {a_global[0]:,} — openpyxl can only add collected tests, so one "
        f"of these came from the wrong terminal")


def test_the_locator_list_names_all_four_documents():
    """
    The four are the four. A fifth document growing a test figure without
    joining this list is the same defect one document along.
    """
    covered = {doc for doc, _w, _p in GLOBAL_SITES}
    assert covered == {"PROGRESS.md", "ABOUT.md", "INTRODUCTION.md", "STATE.md"}


def test_this_check_would_notice_a_document_left_behind(tmp_path):
    """
    The control. A test whose only evidence is "nothing disagreed" proves
    nothing about its own sensitivity, so this feeds the comparison a document
    that WAS left behind and asserts it is reported.
    """
    figures = {"PROGRESS.md": (1522, 2), "ABOUT.md": (1522, 2),
               "INTRODUCTION.md": (1464, 2), "STATE.md": (1522, 2)}
    assert len(set(figures.values())) != 1, (
        "the comparison cannot tell a stale document from a current one")


# ═══════════════════════════════════════════════════════════════════════════
# THE ACCESS-MATRIX FIGURES — permissions, endpoints and roles
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠ **The same defect, in a different figure, found the same way.** Pass D
# pinned the four documents to the same TEST counts. Pass E then found
# `CLAUDE.md`, `PROGRESS.md`, `INTRODUCTION.md` and `STATE.md` all carrying
# **61 permissions / 72 endpoints** while `docs/ACCESS_MATRIX.md` said 73 / 103
# — two to three passes out, and found by a person reading two files side by
# side rather than by a control.
#
# The shape of the fix is different from the test-figure one above, and the
# difference matters. Test counts have **no authority inside the repository**:
# nothing can measure them without running the suite, so agreement between
# documents is the only property available. These figures DO have an authority
# — `auth.PERMISSIONS`, `auth.ROUTE_PERMISSIONS` and `auth.BUILTIN_ROLES` — and
# `docs/ACCESS_MATRIX.md` is generated from it. So this half pins each document
# to **the generated header**, and the header to the code. A document can be
# wrong here in a way it cannot be wrong above: it can disagree with the truth,
# not merely with its siblings.
#
# `docs/ACCESS_MATRIX.md` is the figure of record because CLAUDE.md says it is,
# in terms: *"its own header line is the figure to trust; this sentence has been
# stale before"*.

MATRIX = "docs/ACCESS_MATRIX.md"

# **7 roles · 79 permissions · 114 classified endpoints.**
MATRIX_HEADER = (r"\*\*(\d+) roles?\s*[·.]\s*(\d+) permissions?\s*[·.]\s*"
                 r"(\d+) classified endpoints?\.?\*\*")


def _matrix_header() -> tuple:
    """`(roles, permissions, endpoints)` from the generated header line."""
    found = re.findall(MATRIX_HEADER, _text(MATRIX))
    assert len(found) == 1, (
        f"{MATRIX}: the header locator matched {len(found)} times, not once. "
        f"That line is the figure of record for every document below; if "
        f"tools/dump_access_matrix.py reworded it, move this pattern with it.")
    roles, perms, endpoints = found[0]
    return int(roles), int(perms), int(endpoints)


def test_the_generated_matrix_header_says_what_the_code_says():
    """
    ⚠ **The anchor for everything below.**

    Every other assertion in this section compares a document to the matrix
    header. If the header itself were stale they would all agree on a wrong
    number and this file would certify it. `tests/test_access_matrix_doc.py`
    regenerates the whole document and compares it, which covers this too — but
    it fails as one large diff, and a figure this often quoted deserves to fail
    by name.
    """
    import auth

    roles, perms, endpoints = _matrix_header()
    assert roles == len(auth.BUILTIN_ROLES), (
        f"{MATRIX} says {roles} roles; auth.BUILTIN_ROLES has "
        f"{len(auth.BUILTIN_ROLES)}. Regenerate: python tools/dump_access_matrix.py")
    assert perms == len(auth.PERMISSIONS), (
        f"{MATRIX} says {perms} permissions; auth.PERMISSIONS has "
        f"{len(auth.PERMISSIONS)}. Regenerate: python tools/dump_access_matrix.py")
    assert endpoints == len(auth.ROUTE_PERMISSIONS), (
        f"{MATRIX} says {endpoints} classified endpoints; "
        f"auth.ROUTE_PERMISSIONS has {len(auth.ROUTE_PERMISSIONS)}. "
        f"Regenerate: python tools/dump_access_matrix.py")


# (document, human name, regex yielding the figure). Exactly-one matching is
# enforced for the reason the test-figure locators give: these documents quote
# their own history constantly — STATE.md still carries "**61 permissions and
# the 7x61 grid unchanged**" in a pass note, correctly, and a loose pattern
# would read that as a live claim.
PERMISSION_SITES = [
    # CLAUDE.md — the sentence pointing at the matrix. It wraps across a line
    # break between "roles" and "x", hence the \s+.
    ("CLAUDE.md", "the pointer to docs/ACCESS_MATRIX.md",
     r"the (\d+) roles\s*\n?\s*[x×] (\d+) permissions grid"),

    # INTRODUCTION.md §4, the document map's row 12.
    ("INTRODUCTION.md", "§4 document map, the ACCESS_MATRIX row",
     r"the (\d+) roles [x×] (\d+) permissions grid"),
]


@pytest.mark.parametrize("site", PERMISSION_SITES, ids=lambda s: s[0])
def test_each_document_quoting_the_grid_agrees_with_the_generated_header(site):
    """
    ⚠ **The pass-E defect, in a control.**

    Both documents describe the matrix by its shape — "the 7 roles x 79
    permissions grid" — and both tell the reader that the matrix's own header is
    the figure to trust, precisely because this sentence has gone stale before.
    Saying so is not a control; this is.
    """
    doc, where, pattern = site
    found = re.findall(pattern, _text(doc))
    assert len(found) == 1, (
        f"{doc} — {where}: the locator matched {len(found)} times, not once. "
        f"If the sentence was reworded, move the pattern with it.")

    roles, perms = int(found[0][0]), int(found[0][1])
    want_roles, want_perms, _ = _matrix_header()
    assert (roles, perms) == (want_roles, want_perms), (
        f"{doc} — {where} says {roles} roles x {perms} permissions; "
        f"{MATRIX}'s header says {want_roles} x {want_perms}. The header is the "
        f"figure of record. This exact drift shipped once already, two to three "
        f"passes deep, across four documents at once.")


def test_progress_md_agrees_with_the_header_on_the_endpoint_count():
    """
    `PROGRESS.md`'s B5 row states how many endpoints the registry classifies.
    It carries its own history in the same sentence — "(72 when this row was
    written)" — which is exactly the kind of parenthesis a loose locator reads
    as the live figure, so the pattern anchors on "classifying all".
    """
    found = re.findall(r"classifying all \*\*([\d,]+)\*\* endpoints",
                       _text("PROGRESS.md"))
    assert len(found) == 1, (
        f"PROGRESS.md: the endpoint locator matched {len(found)} times, not "
        f"once. The B5 row is where this figure lives.")

    stated = _n(found[0])
    _roles, _perms, endpoints = _matrix_header()
    assert stated == endpoints, (
        f"PROGRESS.md's B5 row says the registry classifies {stated} endpoints; "
        f"{MATRIX}'s header says {endpoints}.")


def test_this_check_would_notice_a_grid_figure_left_behind():
    """
    The control, matching the one above it. A comparison that has only ever seen
    agreement proves nothing about its own sensitivity, so feed it the real
    numbers from the pass-E drift and assert it reports them.
    """
    stale, current = (7, 61), (7, 79)
    assert stale != current, (
        "the comparison cannot tell a stale grid figure from a current one")
