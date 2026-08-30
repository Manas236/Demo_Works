"""
`tools/clean_site_data.py` — the one-off cleanup, and the refusals that matter.

Authorised by the **FIFTH override block of 30 August 2026** in
`CLIENT_CHANGES.md` §0. Not CC-2 scope; PROGRESS.md §4c.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **A PURGE THAT WOULD ORPHAN A DOCUMENT IS REFUSED, and the refusal is not
   overridable.** This is the whole safety property. The live database has a
   delivery challan, a measurement sheet and a draft PO hanging off a BOQ that
   belongs to a project named like a test row — and a challan is the record that
   goods physically moved, a measurement is the ceiling somebody's claim is
   checked against. Deleting either because a project is called "Banglore" is
   the failure this script exists not to have.
2. ⚠ **NOTHING IS FUZZY-MATCHED AND NOTHING GENERALISES.** Every label it acts
   on is a constant in the file. There is no merge engine, no threshold and no
   `--force`, and tests below assert their absence rather than trusting it.
3. ⚠ **The address is deleted only once `references_of()` is empty**, and if it
   is not the script stops rather than forcing.
4. **A record on the purge list is not repointed first** — work whose result
   nobody can check afterwards.
5. **A dry run writes nothing**, and a second `--write` is a no-op.

⚠ **Do not weaken (1) to make a red suite green.** If it fails, this script is
able to delete a document somebody signed for.
"""

import ast
import pathlib
import sys

import pytest

from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import clean_site_data as CSD  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────
#
# ⚠ These build a MINIATURE of the live database rather than a convenient one,
#   because the properties above are all about the awkward shapes the live data
#   actually has: two projects on the misspelled address, one of them on the
#   purge list, and a BOQ under it carrying documents.

TOUCHED = ("projects", "addresses", "employees", "attendance",
           "boqs", "charges", "purchases", "purchase_orders",
           "delivery_challans", "measurements", "ra_bills")


@pytest.fixture(autouse=True)
def _clean():
    saved = {k: dict(STORE.get(k) or {}) for k in TOUCHED}
    for k in TOUCHED:
        STORE.setdefault(k, {}).clear()
    yield
    for k in TOUCHED:
        STORE.setdefault(k, {}).clear()
        STORE[k].update(saved[k])


def _addr(aid, label, atype="site"):
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": atype, "contact_name": "",
        "company": "", "line1": "", "line2": "", "landmark": "", "city": "",
        "state": "", "pincode": "", "country": "India", "phone": "",
        "email": "", "gstin": "",
    }
    return aid


def _project(pid, name, client, label="", aid=""):
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": name, "client": client,
        "site_address": label, "site_address_id": aid, "notes": ""}
    return STORE["projects"][pid]


def _employee(eid, name, code, site="", aid="", source="book"):
    STORE.setdefault("employees", {})[eid] = {
        "id": eid, "name": name, "code": code, "designation": "Fitter",
        "site": site, "site_address_id": aid, "site_source": source,
        "day_rate": 900.0, "active": True}
    return STORE["employees"][eid]


def _marking(rid, eid, code, name, site="", aid="", source="book"):
    STORE.setdefault("attendance", {})[rid] = {
        "id": rid, "date": "2026-08-30", "employee_id": eid,
        "employee_name": name, "employee_code": code, "day_rate": 900.0,
        "site": site, "site_address_id": aid, "site_source": source,
        "status": "present", "ot_hours": 0.0}
    return STORE["attendance"][rid]


def _live():
    """The shape the live database is actually in — the point of the fixtures."""
    canon = _addr("a-good", CSD.CANONICAL_LABEL)
    dup = _addr("a-bad", CSD.DUPLICATE_LABEL)
    _addr("a-hinj", "Hinjewadi Project Site")

    # Two projects on the MISSPELLED address: one purge target, one that must
    # never be purged and must still be repointed.
    _project("p-bang", "Banglore", "Manas", CSD.DUPLICATE_LABEL, dup)
    _project("p-sify3", "Sify3", "Vishwakarma", CSD.DUPLICATE_LABEL, dup)
    _project("p-sifyb", "Sify Bangalore", "Prudent", CSD.CANONICAL_LABEL, canon)
    _project("p-ts2", "Test Supplier2", "Manas2", "Hinjewadi Project Site",
             "a-hinj")

    _employee("e-100", "Test", "SF-100", "Hinjewadi Project Site", "a-hinj")
    _marking("m-100", "e-100", "SF-100", "Test",
             CSD.UNMAPPED_STRING, "", "unmapped")
    return canon, dup


def _run(write=False):
    argv = ["clean_site_data.py"] + (["--write"] if write else [])
    old = sys.argv
    sys.argv = argv
    try:
        return CSD.main()
    finally:
        sys.argv = old


# ═══ 1. ⚠ THE ORPHAN REFUSAL — the property this script exists for ═════════

def test_a_purge_that_would_orphan_a_document_is_refused(capsys):
    """
    ⚠ **THE ONE THAT MUST NEVER GO GREEN BY BEING WEAKENED.**

    The live shape: project "Banglore" carries a BOQ, and that BOQ carries a
    delivery challan and a measurement sheet. A challan is the record that goods
    physically left the yard; a measurement is the ceiling every installation
    claim on that chain is checked against, and it is the only one that exists.
    Neither is a thing to delete because a project is named like a test row.
    """
    _live()
    STORE["boqs"]["b-1"] = {"id": "b-1", "ref": "SF/BOQ/26-27/0007",
                            "project_id": "p-bang", "subtotal": 26710.0}
    STORE["delivery_challans"]["dc-1"] = {"id": "dc-1", "ref": "3",
                                          "boq_id": "b-1"}
    STORE["measurements"]["ms-1"] = {"id": "ms-1", "ref": "SF/MS/26-27/0001",
                                     "boq_id": "b-1"}

    _run(write=True)
    out = capsys.readouterr().out

    assert "p-bang" not in STORE["projects"] or STORE["projects"].get("p-bang"), \
        "sanity"
    assert STORE["projects"].get("p-bang"), "the project was purged anyway"
    assert STORE["boqs"].get("b-1"), "its BOQ was deleted"
    assert STORE["delivery_challans"].get("dc-1"), "the challan was orphaned"
    assert STORE["measurements"].get("ms-1"), "the measurement was orphaned"

    assert "REFUSED" in out
    assert "SF/MS/26-27/0001" in out, "the refusal must NAME what it saved"
    assert "delivery challan 3" in out


def test_the_orphan_refusal_is_not_vacuous(capsys):
    """
    ⚠ **Mutation proof.** Take the challan and the measurement away and the very
    same purge must go through — otherwise the test above passes because the
    script never purges anything, which proves nothing.
    """
    _live()
    STORE["boqs"]["b-1"] = {"id": "b-1", "ref": "SF/BOQ/26-27/0007",
                            "project_id": "p-bang", "subtotal": 26710.0}
    # NOTE: no challan, no measurement, no draft PO — nothing hangs off b-1.

    _run(write=True)
    out = capsys.readouterr().out

    assert "p-bang" not in STORE["projects"], (
        "with nothing to orphan the purge must proceed — if it does not, the "
        "refusal test above is passing for the wrong reason")
    assert "b-1" not in STORE["boqs"], "the BOQ should have cascaded"
    assert "REFUSED" not in out


@pytest.mark.parametrize("coll,rec", [
    ("ra_bills", {"id": "x", "ref": "SF/RA/26-27/0009", "boq_id": "b-1"}),
    ("delivery_challans", {"id": "x", "ref": "9", "boq_id": "b-1"}),
    ("measurements", {"id": "x", "ref": "SF/MS/26-27/0009", "boq_id": "b-1"}),
    ("purchase_orders", {"id": "x", "ref": "SF/DPO/0009", "boq_id": "b-1"}),
])
def test_every_kind_of_dependant_blocks_the_purge(coll, rec, capsys):
    """
    Each dependant collection on its own. A guard that catches a challan and
    misses a measurement sheet is a guard nobody can rely on.
    """
    _live()
    STORE["boqs"]["b-1"] = {"id": "b-1", "ref": "SF/BOQ/26-27/0007",
                            "project_id": "p-bang"}
    STORE.setdefault(coll, {})["x"] = rec

    _run(write=True)
    capsys.readouterr()

    assert STORE["projects"].get("p-bang"), f"a {coll} row did not block the purge"
    assert STORE[coll].get("x"), f"the {coll} row was orphaned"


def test_a_record_inside_the_cascade_is_not_also_reported_as_an_orphan(capsys):
    """
    ⚠ A purchase order raised from the project's own BOQ carries **both** the
    project id and the boq id. It is deleted with the project, so it cannot also
    be stranded by that deletion — and reporting it as an orphan would refuse a
    purge that is perfectly safe, on the strength of a record already on the
    list to go.
    """
    _live()
    STORE["boqs"]["b-1"] = {"id": "b-1", "ref": "SF/BOQ/26-27/0007",
                            "project_id": "p-bang"}
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "SF/PO/26-27/0002",
                                  "project_id": "p-bang", "boq_id": "b-1",
                                  "status": "Draft"}

    _run(write=True)
    out = capsys.readouterr().out

    assert "REFUSED" not in out, (
        "a record already inside the cascade was counted as something the "
        "cascade would orphan")
    assert "p-bang" not in STORE["projects"]
    assert "po-1" not in STORE["purchases"], "the PO should have cascaded"


# ═══ 2. ⚠ 5a — the fold, and the refusal that guards the delete ════════════

def test_the_fold_repoints_every_reference_then_deletes(capsys):
    """Both projects move to the canonical address; the misspelling goes."""
    canon, dup = _live()

    _run(write=True)
    capsys.readouterr()

    assert dup not in STORE["addresses"], "the misspelled address survived"
    assert "a-bad" not in STORE["addresses"]
    assert STORE["projects"]["p-sify3"]["site_address_id"] == canon
    assert STORE["projects"]["p-sify3"]["site_address"] == CSD.CANONICAL_LABEL


def test_sify3_is_repointed_and_otherwise_untouched(capsys):
    """
    ⚠ **The instruction that looked like a collision, settled.** `Sify3` is
    never purged; it IS repointed, because the misspelled address cannot be
    deleted while it points there. Everything else about the project is the
    same record it was.
    """
    _live()
    before = dict(STORE["projects"]["p-sify3"])

    _run(write=True)
    capsys.readouterr()
    after = STORE["projects"]["p-sify3"]

    assert after["name"] == before["name"] == "Sify3"
    assert after["client"] == before["client"]
    assert after["id"] == before["id"]
    changed = {k for k in set(before) | set(after)
               if before.get(k) != after.get(k)}
    assert changed == {"site_address_id", "site_address"}, (
        f"the repoint changed more than the site link: {changed}")


def test_the_delete_is_refused_while_anything_still_points_at_it(capsys):
    """
    ⚠ **The `references_of()` stop, and it must not be forced.** A reference the
    repoint does not know how to follow means something points at that address
    by a route this script has not been told about.

    Built by planting a record `references_of()` finds and the repoint does not
    move — a delivery challan naming the address by its SNAPSHOT STRING, which
    is exactly the legacy shape `references_of()` exists to catch.
    """
    _live()
    STORE["delivery_challans"]["dc-x"] = {
        "id": "dc-x", "ref": "77", "consignee_id": "",
        "consignee_name": CSD.DUPLICATE_LABEL}

    _run(write=True)
    out = capsys.readouterr().out

    assert "a-bad" in STORE["addresses"], (
        "the address was deleted with a reference still on it — this is the "
        "one place the script must stop rather than force")
    assert "STOP" in out or "still has" in out
    assert "NOT deleted" in out or "not deleted" in out.lower()


# ═══ 3. 5b — mapping, and the skip ═════════════════════════════════════════

def test_a_purge_listed_record_is_skipped_rather_than_mapped(capsys):
    """
    The one unmapped marking on the live database belongs to SF-100, who is on
    the purge list. Repointing a row on its way out reports a number nobody can
    check afterwards, so it is skipped and said so.
    """
    _live()

    _run(write=True)
    out = capsys.readouterr().out

    assert "SKIP" in out
    assert "purge list" in out
    assert "m-100" not in STORE["attendance"], "it should have been purged"


def test_an_unmapped_record_NOT_on_the_purge_list_is_mapped(capsys):
    """The control. Otherwise the skip above could be the only path there is."""
    canon, _ = _live()
    _employee("e-real", "Ramesh Patil", "SF-200",
              CSD.UNMAPPED_STRING, "", "unmapped")

    _run(write=True)
    capsys.readouterr()

    e = STORE["employees"]["e-real"]
    assert e["site_address_id"] == canon
    assert e["site"] == CSD.CANONICAL_LABEL
    assert e["site_source"] == "book"


# ═══ 4. Dry run, and idempotence ═══════════════════════════════════════════

def test_a_dry_run_writes_nothing(capsys):
    _live()
    before = {k: dict(STORE[k]) for k in TOUCHED}

    _run(write=False)
    out = capsys.readouterr().out

    assert "DRY RUN" in out
    for k in TOUCHED:
        assert STORE[k] == before[k], f"the dry run mutated {k}"


def test_the_second_write_is_a_no_op(capsys):
    _live()
    _run(write=True)
    capsys.readouterr()
    after_first = {k: dict(STORE[k]) for k in TOUCHED}

    _run(write=True)
    out = capsys.readouterr().out

    for k in TOUCHED:
        assert STORE[k] == after_first[k], f"the second run changed {k}"
    assert "is not in the book" in out, (
        "the second run should say the misspelled address is already gone")


# ═══ 5. ⚠ WHAT THE SCRIPT IS NOT ═══════════════════════════════════════════

def test_it_is_not_a_merge_engine_and_has_no_force():
    """
    ⚠ **The override block authorised a one-off repoint of ONE named pair.** A
    reusable address-merge operation is a different thing with a different blast
    radius and was explicitly not authorised; a `--force` would turn every
    refusal above into a warning somebody clicks past.
    """
    src = (REPO / "tools" / "clean_site_data.py").read_text(encoding="utf8")
    tree = ast.parse(src)

    # ⚠ **Asked of the AST, not of the text.** The module docstring says in
    #   words that there is no `--force`, and a substring check on the source
    #   therefore fails on the sentence promising the property it is testing.
    flags = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value)
    assert flags == {"--write"}, (
        f"the script takes {sorted(flags)}. It may take exactly one flag: a "
        f"--force (or anything like it) turns every refusal above into a "
        f"warning somebody clicks past.")

    # Every label it acts on is a module constant, so a reviewer can see the
    # whole blast radius without reading the code.
    assert CSD.CANONICAL_LABEL == "Bangalore, Karnataka"
    assert CSD.DUPLICATE_LABEL == "Banglore, Karnataka"
    assert CSD.UNMAPPED_STRING == "Banglore"
    assert len(CSD.PURGE_PROJECTS) == 2 and len(CSD.PURGE_EMPLOYEES) == 3

    # ⚠ And no similarity function of any kind — asked of the CODE, with every
    #   docstring stripped, for the same reason as above.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body[0].value.value = ""
    code = ast.dump(tree)
    for banned in ("edit_distance", "casefold", "difflib", "SequenceMatcher",
                   "startswith", "levenshtein", "get_close_matches"):
        assert banned not in code, (
            f"{banned!r} appears in the code — this script matches exact "
            f"strings it was given and must never guess at one")


@pytest.mark.parametrize("name", ["Sify Bangalore", "Sify 2", "Sify3"])
def test_the_sify_projects_are_never_purge_targets(name):
    """Named in the brief and in the override block; asserted rather than trusted."""
    assert name not in [n for n, _ in CSD.PURGE_PROJECTS]


def test_hinjewadi_is_never_a_label_this_script_acts_on():
    src_labels = {CSD.CANONICAL_LABEL, CSD.DUPLICATE_LABEL, CSD.UNMAPPED_STRING}
    assert "Hinjewadi Project Site" not in src_labels


def test_it_is_not_reachable_from_the_application():
    """
    ⚠ A destructive script that a request can reach is a destructive request.
    Nothing in the app imports it, and `tools/` is not on the app's import path.
    """
    for path in REPO.glob("*.py"):
        src = path.read_text(encoding="utf8")
        assert "clean_site_data" not in src, (
            f"{path.name} references the cleanup script — it is a command-line "
            f"tool and nothing in the application may reach it")
