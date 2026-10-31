"""
Every saved BOQ's items join the Specification library.

31 October 2026, CLIENT_CHANGES.md §0 sixty-first block. Yogesh, on the call:
whatever goes into a BOQ should be in the library, so it can be picked on a
purchase order. Manas: on EVERY BOQ save, automatically, plus a one-time
backfill of the BOQs already on the box.

Pinned here:

1. **The mapping.** A specification header becomes a clause and the sizes under
   it become its variants; a stand-alone line becomes a one-size clause.
   Installation-only lines (labour) are not learned. Rates are BASE rates.
2. **Add-only.** A clause already in the library is reused, a missing size is
   appended, a rate fills only where the library has none — nothing the
   library holds is ever changed.
3. **Exact text, nothing fuzzy.** 150 NB and 150mm dia are two sizes.
4. **The save path.** `/boq/create` learns after the save, says how many it
   added, and can never block the BOQ.
5. **The backfill.** Dry run writes nothing; `--write` is idempotent.
"""

import json

import pytest

import boq as BQ
import spec as SP
from store import STORE


def a_line(**kw):
    li = {"line_id": "", "item_no": "1", "parent_item_no": "", "section": "A",
          "is_header": False, "description": "Pipe", "remark": "", "unit": "Mtr",
          "area_qty": {}, "total_qty": "10",
          "supply_base_rate": "", "supply_escalation_pct": "", "supply_rate": "100",
          "supply_hsn": "", "supply_gst_rate": "",
          "install_base_rate": "", "install_escalation_pct": "", "install_rate": "",
          "install_sac": "", "install_gst_rate": "",
          "supply_disc_pct": "", "install_disc_pct": ""}
    li.update(kw)
    return li


def save(client, *lines, **form):
    data = {"date": "2026-10-31", "project_name": "Learn", "account_name": "A",
            "boq_json": json.dumps({"sections": [{"code": "A", "title": "", "areas": []}],
                                    "lines": list(lines)})}
    data.update(form)
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data=data)
    new = set(STORE["boqs"]) - before
    assert r.status_code == 302 and new, r.get_data(as_text=True)[:600]
    return STORE["boqs"][new.pop()], r


CLAUSE = ("Supply, Fabrication, Installtion, Testing of Heavy 'C' class Galvanised "
          "Iron pipes as per IS 1239 with screwed joints\nSecond line of the clause")


def family(*sizes, base=None, unit="Mtrs"):
    head = a_line(item_no="7", is_header=True, description=CLAUSE, unit="",
                  supply_rate="", total_qty="")
    kids = [a_line(item_no=f"7.{n}", parent_item_no="7", description=s, unit=unit,
                   supply_base_rate=("" if base is None else str(base)),
                   supply_rate="120", supply_hsn="73063090", supply_gst_rate="18")
            for n, s in enumerate(sizes, start=1)]
    return [head] + kids


def learned():
    return [s for s in STORE["specs"].values() if s.get("created_from") == "boq"]


# ══ 1. The mapping ══════════════════════════════════════════════════════════

def test_a_header_and_its_sizes_become_one_clause_with_variants(client):
    _boq, r = save(client, *family("25 NB", "50 NB", base=90))
    got = learned()
    assert len(got) == 1
    s = got[0]
    assert s["spec_text"] == CLAUSE
    assert [v["label"] for v in s["variants"]] == ["25 NB", "50 NB"]
    assert all(v["unit"] == "Mtrs" for v in s["variants"])
    assert all(v["default_supply_base_rate"] == 90.0 for v in s["variants"])
    assert s["code"].startswith("BOQ-") and s["supply_hsn"] == "73063090"
    assert s["title"].startswith("Heavy 'C' class Galvanised Iron pipes")
    assert "Second line" not in s["title"]
    assert s["category"] == "Piping"
    assert s["learned_from_boq_ref"] == _boq["ref"]


def test_a_stand_alone_line_becomes_a_one_size_clause(client):
    save(client, a_line(description="Fire alarm panel 4 zone", unit="Nos",
                        supply_base_rate="15000"))
    s = learned()[0]
    assert len(s["variants"]) == 1 and s["variants"][0]["label"] == ""
    assert s["variants"][0]["default_supply_base_rate"] == 15000.0
    assert s["category"] == "Panels"


def test_installation_only_lines_are_not_learned(client):
    save(client, a_line(description="Installation of pipes", supply_rate="",
                        install_rate="300"),
         a_line(description="Ball valve 25mm", unit="Nos"))
    texts = [s["spec_text"] for s in learned()]
    assert texts == ["Ball valve 25mm"]


def test_the_selling_rate_is_never_learned_as_a_rate(client):
    save(client, a_line(description="Gate valve 80mm", unit="Nos",
                        supply_base_rate="", supply_rate="5000"))
    assert learned()[0]["variants"][0]["default_supply_base_rate"] is None


def test_a_header_with_nothing_learnable_under_it_is_skipped(client):
    head = a_line(item_no="9", is_header=True, description="A lonely clause",
                  unit="", supply_rate="", total_qty="")
    save(client, head, a_line(description="Ball valve 25mm", unit="Nos"))
    assert "A lonely clause" not in [s["spec_text"] for s in learned()]


# ══ 2. Add-only ═════════════════════════════════════════════════════════════

def test_a_second_boq_appends_only_the_missing_sizes(client):
    save(client, *family("25 NB", "50 NB"))
    save(client, *family("50 NB", "80 NB"))
    got = learned()
    assert len(got) == 1
    assert [v["label"] for v in got[0]["variants"]] == ["25 NB", "50 NB", "80 NB"]


def test_a_rate_fills_only_where_the_library_has_none(client):
    save(client, *family("25 NB"))                    # no base rate
    save(client, *family("25 NB", base=95))           # fills it
    save(client, *family("25 NB", base=999))          # never overwrites
    v = learned()[0]["variants"][0]
    assert v["default_supply_base_rate"] == 95.0


def test_nothing_the_library_already_holds_is_changed(client):
    SP.ensure_demo_specs()
    sid, s = next(iter(STORE["specs"].items()))
    before = json.dumps(s, sort_keys=True)
    lines = [a_line(item_no="3", is_header=True, description=s["spec_text"], unit="",
                    supply_rate="", total_qty="")]
    lines += [a_line(item_no="3.1", parent_item_no="3",
                     description=s["variants"][0].get("label") or "x",
                     unit=s["variants"][0].get("unit") or "Nos",
                     supply_base_rate="1")]
    save(client, *lines)
    after = STORE["specs"][sid]
    # the title, code, category and every existing rate stand
    for k in ("code", "title", "category", "spec_text", "supply_hsn"):
        assert after[k] == json.loads(before)[k]
    old_rate = json.loads(before)["variants"][0]["default_supply_base_rate"]
    if old_rate is not None:
        assert after["variants"][0]["default_supply_base_rate"] == old_rate


def test_the_seeded_demo_boq_adds_nothing_to_the_seeded_library(client):
    BQ.ensure_demo_boq()
    boq = next(iter(STORE["boqs"].values()))
    n = len(STORE["specs"])
    rep = SP.learn_from_clauses(BQ.library_payload(boq))
    assert rep["new_specs"] == 0 and rep["new_variants"] == 0
    assert len(STORE["specs"]) == n


# ══ 3. Exact text ═══════════════════════════════════════════════════════════

@pytest.mark.parametrize("one, two", [("150 NB", "150mm dia"), ("1.5 mm", "15 mm"),
                                      ("50 NB 5mm thk", "50 NB 6mm thk")])
def test_sizes_are_never_merged_on_a_guess(client, one, two):
    save(client, *family(one, two))
    assert len(learned()[0]["variants"]) == 2


def test_ms_and_gi_clauses_stay_two_clauses(client):
    save(client, a_line(description="MS pipe 50 NB"), a_line(description="GI pipe 50 NB"))
    assert len(learned()) == 2


# ══ 4. The save path ════════════════════════════════════════════════════════

def test_the_save_message_says_how_many_were_added(client):
    _boq, r = save(client, *family("25 NB", "50 NB"))
    assert "2+new+items+added+to+the+Spec+library" in r.headers["Location"] or \
           "2 new items added to the Spec library" in r.headers["Location"]


def test_a_failure_in_learning_never_blocks_the_boq(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("library down")
    monkeypatch.setattr(SP, "learn_from_clauses", boom)
    boq, _r = save(client, a_line(description="Ball valve 25mm"))
    assert boq["id"] in STORE["boqs"]


def test_a_learned_clause_passes_its_own_edit_form(client):
    """Learned data must not make the clause refuse its own /spec edit."""
    save(client, *family("25 NB", "50 NB", base=90))
    s = learned()[0]
    form = {"code": s["code"], "title": s["title"], "spec_text": s["spec_text"],
            "category": s["category"], "supply_hsn": s["supply_hsn"],
            "install_sac": s["install_sac"],
            "supply_gst_rate": str(s["supply_gst_rate"]),
            "install_gst_rate": str(s["install_gst_rate"]),
            "var_label": [v["label"] for v in s["variants"]],
            "var_dimension": ["" for _ in s["variants"]],
            "var_dim_unit": ["" for _ in s["variants"]],
            "var_unit": [v["unit"] for v in s["variants"]],
            "var_supply": [str(v["default_supply_base_rate"] or "") for v in s["variants"]],
            "var_install": ["" for _ in s["variants"]]}
    from werkzeug.datastructures import MultiDict
    md = MultiDict()
    for k, v in form.items():
        for x in (v if isinstance(v, list) else [v]):
            md.add(k, x)
    _data, err = SP._validate(md, spec_id=s["id"])
    assert err == "", err


def test_a_learned_size_is_offered_on_the_purchase_order(client):
    import auth
    import buypick as BYP
    saved = set(auth.HIDDEN_BLUEPRINTS)
    auth.HIDDEN_BLUEPRINTS.clear(); auth.HIDDEN_BLUEPRINTS.add("product")
    try:
        save(client, *family("25 NB"))
        sid = learned()[0]["id"]
        assert any(e["value"] == f"spec:{sid}:0" for e in BYP.spec_entries())
    finally:
        auth.HIDDEN_BLUEPRINTS.clear(); auth.HIDDEN_BLUEPRINTS.update(saved)


# ══ 5. The backfill tool ════════════════════════════════════════════════════

def _tool():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "backfill_spec_from_boqs.py"
    spec = importlib.util.spec_from_file_location("backfill_spec_from_boqs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_backfill_dry_run_writes_nothing_and_write_is_idempotent(client, capsys):
    tool = _tool()
    SP.ensure_demo_specs()
    STORE["boqs"]["bk1"] = {"id": "bk1", "ref": "SF/BOQ/T/1", "date": "2026-10-01",
                            "supersedes": "", "line_items": [
        {"line_id": "aaaaaaaaaa01", "is_header": False, "item_no": "1",
         "description": "Hose reel drum 30m", "unit": "Nos", "supply_rate": 9000.0,
         "supply_base_rate": 8000.0, "install_rate": None}]}
    n = len(STORE["specs"])
    tool.backfill(write=False)
    assert len(STORE["specs"]) == n
    first = tool.backfill(write=True)
    assert first["new_specs"] == 1 and len(STORE["specs"]) == n + 1
    again = tool.backfill(write=True)
    assert again["new_specs"] == 0 and again["new_variants"] == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_the_backfill_reads_only_current_revisions(client):
    tool = _tool()
    STORE["boqs"]["old"] = {"id": "old", "ref": "B/1", "date": "2026-09-01",
                            "supersedes": "", "line_items": [
        {"line_id": "aaaaaaaaaa02", "is_header": False, "description": "Old wording valve",
         "unit": "Nos", "supply_rate": 1.0, "supply_base_rate": 1.0}]}
    STORE["boqs"]["new"] = {"id": "new", "ref": "B/1/1", "date": "2026-10-01",
                            "supersedes": "old", "line_items": [
        {"line_id": "aaaaaaaaaa03", "is_header": False, "description": "New wording valve",
         "unit": "Nos", "supply_rate": 1.0, "supply_base_rate": 1.0}]}
    tool.backfill(write=True)
    texts = {s["spec_text"] for s in learned()}
    assert "New wording valve" in texts and "Old wording valve" not in texts


def test_the_dry_run_counts_exactly_what_write_will_do(client, capsys):
    """A clause new in one BOQ and repeated in the next is ONE clause, dry or not."""
    tool = _tool()
    SP.ensure_demo_specs()
    for n, bid in enumerate(("d1", "d2"), start=1):
        STORE["boqs"][bid] = {"id": bid, "ref": f"D/{n}", "date": f"2026-10-0{n}",
                              "supersedes": "", "line_items": [
            {"line_id": f"aaaaaaaaab0{n}", "is_header": False,
             "description": "Shared hose reel", "unit": "Nos",
             "supply_rate": 1.0, "supply_base_rate": 1.0}]}
    before = json.dumps(STORE["specs"], sort_keys=True)
    dry = tool.backfill(write=False)
    assert json.dumps(STORE["specs"], sort_keys=True) == before
    wet = tool.backfill(write=True)
    assert dry == wet and wet["new_specs"] == 1
