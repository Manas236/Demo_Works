"""
`tools/backfill_project_sites.py` — the real script, driven in process.

⚠ **This imports and runs the SCRIPT, rather than reimplementing what it does.**
`tests/test_site_picker.py` tests its predecessor by re-writing the migration's
logic in a fixture, which is honest about being a model and is a weaker thing: a
model cannot fail when the script drifts away from it. Everything below calls
`main()` or the script's own functions.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **NOTHING IS FUZZY-MATCHED.** `Banglore` does not become `Bangalore`. A
   wrong automatic match puts a project on the wrong site and looks exactly like
   a right one — `po_parts.py`'s 156 invented aliases, ABOUT.md §2h.
2. ⚠ **NO SPELLING IS CORRECTED.** The created address is spelled exactly as the
   project spelled it. Creating `Bangalore` from `Banglore` is a silent edit of
   the client's own record of where his work happened.
3. ⚠ **DRY RUN IS THE DEFAULT AND WRITES NOTHING.**
4. ⚠ **THE SECOND RUN IS A NO-OP.** Idempotence is what makes it safe to run
   again after mapping a record by hand.
5. **`site_address` is not rewritten** — it is the label snapshot and already
   holds the right value.
6. **The duplicate pair is PRINTED and never folded**, and the site→project
   ambiguity count is **printed with no guard built on it**.
"""

import importlib.util
import pathlib

import pytest

import project as PJ
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "backfill_project_sites.py"


def _load():
    spec = importlib.util.spec_from_file_location("backfill_project_sites", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BF = _load()

_MINTED = set()


@pytest.fixture(autouse=True)
def _clean():
    STORE.setdefault("projects", {}).clear()
    _MINTED.clear()
    yield
    STORE.setdefault("projects", {}).clear()
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


def _addr(label, atype="site", aid=None):
    aid = aid or f"bfaddr-{label.lower().replace(' ', '-').replace(',', '')}"
    _MINTED.add(aid)
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": atype, "contact_name": "",
        "company": "", "line1": "1 Site Road", "line2": "", "landmark": "",
        "city": "Bengaluru", "state": "Karnataka", "pincode": "560066",
        "country": "India", "phone": "", "email": "", "gstin": "",
    }
    return aid


def _proj(pid, site, name=None):
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": name or pid, "norm_name": (name or pid).lower(),
        "client": "", "site_address": site, "notes": "",
        "created_at": "", "updated_at": ""}
    return STORE["projects"][pid]


def _run(monkeypatch, capsys, write=False):
    """Drive the real `main()`. Returns its stdout."""
    argv = ["backfill_project_sites.py"] + (["--write"] if write else [])
    monkeypatch.setattr(BF.sys, "argv", argv)
    before = set(STORE.get("addresses") or {})
    assert BF.main() == 0
    for aid in set(STORE.get("addresses") or {}) - before:
        _MINTED.add(aid)
    return capsys.readouterr().out


# ═══ 1. DRY RUN writes nothing ═════════════════════════════════════════════

def test_the_default_is_a_dry_run_and_it_writes_nothing(monkeypatch, capsys):
    _proj("p-1", "Banglore, Karnataka")
    n_before = len(STORE["addresses"])
    out = _run(monkeypatch, capsys)
    assert "DRY RUN" in out
    assert len(STORE["addresses"]) == n_before, "the dry run created an address"
    assert not STORE["projects"]["p-1"].get(PJ.SITE_ADDRESS_ID_FIELD)


# ═══ 2. EXACT match links; anything else CREATES, verbatim ═════════════════

def test_an_exact_label_match_links_and_creates_nothing(monkeypatch, capsys):
    aid = _addr("Whitefield, Karnataka")
    _proj("p-1", "Whitefield, Karnataka")
    n_before = len(STORE["addresses"])
    _run(monkeypatch, capsys, write=True)
    assert STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD] == aid
    assert len(STORE["addresses"]) == n_before, "it created a duplicate address"


def test_whitespace_is_the_ONLY_thing_stripped_before_matching(monkeypatch, capsys):
    aid = _addr("Whitefield")
    _proj("p-1", "  Whitefield  ")
    _run(monkeypatch, capsys, write=True)
    assert STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD] == aid


@pytest.mark.parametrize("stored,book", [
    ("Banglore, Karnataka", "Bangalore, Karnataka"),   # the live misspelling
    ("bangalore",           "Bangalore"),              # case
    ("Bangalore  Site",     "Bangalore Site"),         # collapsed whitespace
    ("Bangalore, KA",       "Bangalore"),              # a suffix
    ("Sify Bangalore",      "Bangalore"),              # a prefix
])
def test_a_NEAR_MISS_is_never_matched_and_creates_its_own_address(
        monkeypatch, capsys, stored, book):
    """
    ⚠ **THE TEST THIS WHOLE MIGRATION EXISTS TO BE SAFE UNDER.** Every row is a
    string a less careful matcher would happily link. Not one of them may be.
    """
    existing = _addr(book)
    _proj("p-1", stored)
    _run(monkeypatch, capsys, write=True)
    got = STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD]
    assert got != existing, (
        f"{stored!r} was linked to {book!r} — something here is fuzzy-matching")
    assert STORE["addresses"][got]["label"] == stored.strip(), (
        "the created address does not carry the string verbatim")


def test_NO_SPELLING_IS_CORRECTED(monkeypatch, capsys):
    _addr("Bangalore, Karnataka")
    _proj("p-1", "Banglore, Karnataka")
    _run(monkeypatch, capsys, write=True)
    aid = STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD]
    assert STORE["addresses"][aid]["label"] == "Banglore, Karnataka", (
        "the misspelling was corrected — that is a silent edit of the client's "
        "own record of where his work happened")


def test_a_created_address_is_a_SITE_and_is_offerable(monkeypatch, capsys):
    import address as AD
    _proj("p-1", "Whitefield, Karnataka")
    _run(monkeypatch, capsys, write=True)
    aid = STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD]
    assert STORE["addresses"][aid]["type"] == "site"
    assert AD.is_active(STORE["addresses"][aid]) is True
    assert aid in AD.picker_options(only_types=AD.SITE_TYPES)


def test_one_address_is_created_per_DISTINCT_string(monkeypatch, capsys):
    _proj("p-1", "Banglore, Karnataka")
    _proj("p-2", "Banglore, Karnataka")
    _proj("p-3", "Bangalore, Karnataka")
    n_before = len(STORE["addresses"])
    _run(monkeypatch, capsys, write=True)
    assert len(STORE["addresses"]) == n_before + 2, (
        "two distinct strings should produce two addresses, not three or one")
    assert (STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD]
            == STORE["projects"]["p-2"][PJ.SITE_ADDRESS_ID_FIELD])


def test_a_project_with_no_site_is_left_entirely_alone(monkeypatch, capsys):
    _proj("p-1", "")
    _run(monkeypatch, capsys, write=True)
    p = STORE["projects"]["p-1"]
    assert p["site_address"] == ""
    assert not p.get(PJ.SITE_ADDRESS_ID_FIELD), "a site was invented"


def test_site_address_is_NOT_rewritten_on_EITHER_branch(monkeypatch, capsys):
    """
    It is the label snapshot and it already holds the right value — the address
    was either created from it or matched against it exactly.

    ⚠ **Both branches, and the second one was added because the first was not
    enough.** A mutation that cleared `site_address` on the `link` branch went
    **uncaught** by an earlier version of this test, which only exercised
    `create`. A guard that covers one of two write paths covers neither.
    """
    _addr("Whitefield")
    _proj("p-link", "Whitefield")                 # the LINK branch
    _proj("p-create", "Banglore, Karnataka")      # the CREATE branch
    _run(monkeypatch, capsys, write=True)
    assert STORE["projects"]["p-link"]["site_address"] == "Whitefield"
    assert STORE["projects"]["p-create"]["site_address"] == "Banglore, Karnataka"


# ═══ 3. IDEMPOTENCE ════════════════════════════════════════════════════════

def test_the_second_run_changes_nothing(monkeypatch, capsys):
    _addr("Whitefield")
    _proj("p-1", "Whitefield")
    _proj("p-2", "Banglore, Karnataka")
    _run(monkeypatch, capsys, write=True)

    import copy
    after_first = copy.deepcopy(
        {"projects": STORE["projects"], "addresses": STORE["addresses"]})

    out = _run(monkeypatch, capsys, write=True)
    assert STORE["projects"] == after_first["projects"], (
        "the second run moved a project")
    assert STORE["addresses"] == after_first["addresses"], (
        "the second run created a second address for the same string")
    assert "0 address(es) created" in out


def test_a_project_mapped_BY_HAND_is_not_undone(monkeypatch, capsys):
    right = _addr("Bangalore, Karnataka")
    p = _proj("p-1", "Banglore, Karnataka")
    p[PJ.SITE_ADDRESS_ID_FIELD] = right          # a human resolved the pair
    n_before = len(STORE["addresses"])
    _run(monkeypatch, capsys, write=True)
    assert STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD] == right
    assert len(STORE["addresses"]) == n_before, (
        "it created an address for a project a person had already mapped")


# ═══ 4. The three REPORTS — printed, never applied ═════════════════════════

def test_near_misses_are_printed_and_not_applied(monkeypatch, capsys):
    existing = _addr("Bangalore, Karnataka")
    _proj("p-1", "bangalore, karnataka")
    out = _run(monkeypatch, capsys)
    assert "NEAR MISSES" in out
    assert "nearly matches address 'Bangalore, Karnataka'" in out
    assert not STORE["projects"]["p-1"].get(PJ.SITE_ADDRESS_ID_FIELD)
    assert existing  # the address it nearly matched is untouched


def test_the_duplicate_pair_is_printed_and_NOT_folded(monkeypatch, capsys):
    _proj("p-1", "Banglore, Karnataka")
    _proj("p-2", "Bangalore, Karnataka")
    out = _run(monkeypatch, capsys, write=True)
    assert "DUPLICATE REPORT" in out
    assert "'Banglore, Karnataka'" in out and "'Bangalore, Karnataka'" in out
    assert "edit distance 1" in out
    assert "NOT folded" in out
    a1 = STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD]
    a2 = STORE["projects"]["p-2"][PJ.SITE_ADDRESS_ID_FIELD]
    assert a1 != a2, "the two spellings were folded into one address"


def test_the_site_to_project_ambiguity_is_counted_and_NOT_guarded(
        monkeypatch, capsys):
    """
    ⚠ **No guard is built on this.** The client has said one project = one site;
    he has NOT said one site = one project, and the live data already has two
    projects on one string.
    """
    _proj("p-1", "Banglore, Karnataka")
    _proj("p-2", "Banglore, Karnataka")
    out = _run(monkeypatch, capsys, write=True)
    assert "SITE -> PROJECT AMBIGUITY" in out
    assert "2 project(s)" in out
    assert "MORE THAN ONE PROJECT ON ONE SITE" in out
    assert "NO GUARD IS BUILT ON THIS" in out
    assert (STORE["projects"]["p-1"][PJ.SITE_ADDRESS_ID_FIELD]
            == STORE["projects"]["p-2"][PJ.SITE_ADDRESS_ID_FIELD]), (
        "one of the two projects was refused its site")


def test_the_edit_distance_helper_is_a_real_levenshtein():
    assert BF._edit_distance("Banglore", "Bangalore") == 1
    assert BF._edit_distance("abc", "abc") == 0
    assert BF._edit_distance("", "abc") == 3
    assert BF._edit_distance("kitten", "sitting") == 3


def test_the_duplicate_report_does_not_pair_two_unrelated_places():
    pairs = BF._duplicate_pairs(["Mumbai", "Ahmedabad", "Coimbatore"])
    assert pairs == [], "unrelated labels were reported as a duplicate pair"


def test_the_near_miss_helper_never_reports_an_exact_match():
    index = {"Bangalore": "a-1"}
    assert BF._near_misses("Bangalore", index) == [], (
        "an exact match is a link, not a near miss — reporting it would tell a "
        "human to look at a decision the script already took correctly")
    assert BF._near_misses("bangalore", index) == ["Bangalore"]
