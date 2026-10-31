"""
The purchase order's item picker — Specification library + BOQ items.

31 October 2026, CLIENT_CHANGES.md §0 sixtieth block; ABOUT.md §7 gap 38
re-opened and re-closed; `buypick.py`.

The client opened `/purchase/create` on the 31 October call and found the item
dropdown empty: the 12 September catalogue switch had emptied it and nothing
took its place. What is pinned here:

1. **The two sources.** The library only while the catalogue is hidden; the
   BOQ items either way.
2. **What a BOQ offers.** Current revisions only, no headers, a child named
   with its clause, no installation-only (labour) lines, and an EXACT-text
   dedupe that never merges Dia with NB, 1.5 with 15, MS with GI or two wall
   thicknesses.
3. **The rate is a COST.** The library's supply base rate; a BOQ line's supply
   base rate from the newest current BOQ that has one; blank — never the
   selling rate, never 0 — when there is none.
4. **The POST.** Identity re-read from the source, a tampered or stale pick
   refused, a mixed order (library + BOQ + extra parts) saved.
5. **The snapshot.** Editing the spec, revising or deleting the BOQ moves
   nothing on a saved order, and the line carries `src_*` — never `line_id`,
   never the order's `boq_id` / `project_id`.
6. **The page.** The search box, the one option list, the fill script.
"""

import copy

import pytest

import address
import boq as BQ
import buypick as BYP
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"


@pytest.fixture()
def hidden():
    """The shipped configuration — the catalogue hidden."""
    import auth
    saved = set(auth.HIDDEN_BLUEPRINTS)
    auth.HIDDEN_BLUEPRINTS.clear()
    auth.HIDDEN_BLUEPRINTS.add("product")
    try:
        yield
    finally:
        auth.HIDDEN_BLUEPRINTS.clear()
        auth.HIDDEN_BLUEPRINTS.update(saved)


@pytest.fixture()
def shown():
    import auth
    saved = set(auth.HIDDEN_BLUEPRINTS)
    auth.HIDDEN_BLUEPRINTS.clear()
    try:
        yield
    finally:
        auth.HIDDEN_BLUEPRINTS.clear()
        auth.HIDDEN_BLUEPRINTS.update(saved)


def L(short):
    """A real line id — 12 hex characters, as `boq._line_id()` requires."""
    import hashlib
    return hashlib.md5(short.encode()).hexdigest()[:12]


def V(bid, short):
    """The pick value for BOQ `bid`'s line `short`."""
    return f"boq:{bid}:{L(short)}"


def _line(lid, desc, *, unit="Nos", s_base=None, s_rate=None, i_rate=None,
          header=False, item_no="1", remark=""):
    return {
        "line_id": L(lid), "item_no": item_no, "parent_item_no": "", "section": "A",
        "is_header": header, "description": desc, "remark": remark,
        "unit": "" if header else unit, "area_qty": {}, "total_qty": 1.0,
        "supply_base_rate": s_base, "supply_escalation_pct": 0.0,
        "supply_rate": s_rate, "supply_hsn": "73063090", "supply_gst_rate": 18.0,
        "install_base_rate": None, "install_escalation_pct": 0.0,
        "install_rate": i_rate, "install_sac": "995462", "install_gst_rate": 18.0,
    }


def _boq(bid, ref, date, lines, supersedes=""):
    rec = {"id": bid, "ref": ref, "date": date, "rev_no": 0, "fy": "26-27",
           "project_name": f"Project {ref}", "account_name": "Party",
           "supersedes": supersedes, "line_items": lines, "sections": []}
    STORE["boqs"][bid] = rec
    return rec


def _form(lines=(), extras=()):
    """`lines` is `[(value, qty, rate), ...]`; `extras` `[(desc, unit, qty, rate)]`."""
    return {
        "date": "2026-10-31", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0",
        "line_product_id": [v for v, _q, _r in lines],
        "line_qty": [str(q) for _v, q, _r in lines],
        "line_rate": [str(r) for _v, _q, r in lines],
        "line_discount": ["" for _ in lines],
        "line_make": ["" for _ in lines],
        "extra_desc": [e[0] for e in extras], "extra_unit": [e[1] for e in extras],
        "extra_qty": [str(e[2]) for e in extras], "extra_rate": [str(e[3]) for e in extras],
        "extra_discount": ["" for _ in extras],
    }


def _seed():
    address.ensure_demo_addresses()
    BYP.ensure_seeded()


def _newest_po():
    return list(STORE["purchases"].values())[-1]


def _values(entries):
    return {e["value"] for e in entries}


# ══ 1. The two sources ══════════════════════════════════════════════════════

def test_the_library_is_offered_only_while_the_catalogue_is_hidden(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve 25mm", s_base=100.0, s_rate=120.0)])
    html = PU._product_options()
    assert 'optgroup label="Specification library"' in html
    assert 'optgroup label="BOQ items"' in html
    assert html.index("Specification library") < html.index("BOQ items")


def test_the_boq_items_are_offered_with_the_catalogue_on_too(client, shown):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve 25mm", s_base=100.0, s_rate=120.0)])
    html = PU._product_options()
    assert 'optgroup label="Specification library"' not in html
    assert f'value="{V("b1", "l1")}"' in html


def test_no_boq_means_no_boq_group(client, hidden):
    _seed()
    assert 'optgroup label="BOQ items"' not in PU._product_options()


def test_every_library_variant_is_offered(client, hidden):
    _seed()
    n = sum(len(s.get("variants") or []) for s in STORE["specs"].values())
    assert len(BYP.spec_entries()) == n > 0


# ══ 2. What a BOQ offers ════════════════════════════════════════════════════

def test_a_superseded_revision_is_never_offered(client):
    _boq("old", "B-1", "2026-09-01", [_line("l1", "Ball valve 25mm", s_base=100.0)])
    _boq("new", "B-1/R1", "2026-10-01", [_line("l1", "Ball valve 25mm", s_base=110.0)],
         supersedes="old")
    vals = _values(BYP.boq_entries())
    assert vals == {V("new", "l1")}


def test_headers_are_never_offered_and_a_child_carries_its_clause(client):
    lines = [
        _line("h4", "Heavy C class Mild Steel pipes as per IS 1239 ISI marked\nsecond line",
              header=True, item_no="4"),
        _line("c1", "150mm dia     ISI", unit="Mtrs.", s_base=1760.0, s_rate=2024.0,
              item_no="4.1"),
    ]
    lines[1]["parent_item_no"] = "4"
    _boq("b1", "B-1", "2026-10-01", lines)
    ents = BYP.boq_entries()
    assert _values(ents) == {V("b1", "c1")}
    name = ents[0]["name"]
    assert name.startswith("Heavy C class Mild Steel pipes as per IS 1239 ISI marked")
    assert name.endswith("— 150mm dia ISI")
    assert "second line" not in name


def test_a_long_clause_is_cut_on_a_word_boundary(client):
    clause = "Supply of " + "very long words " * 40
    lines = [_line("h", clause, header=True, item_no="4"),
             _line("c", "25 NB", s_base=10.0, item_no="4.1")]
    lines[1]["parent_item_no"] = "4"
    _boq("b1", "B-1", "2026-10-01", lines)
    name = BYP.boq_entries()[0]["name"]
    head = name.split(" — ")[0]
    assert head.endswith("…") and len(head) <= BYP.CLAUSE_CHARS + 1
    assert name.endswith("— 25 NB")


def test_installation_only_lines_are_labour_and_not_offered(client):
    _boq("b1", "B-1", "2026-10-01", [
        _line("lab", "Installation of pipes", s_rate=None, i_rate=300.0),
        _line("mat", "MS pipe 25 NB", s_base=100.0, s_rate=120.0, i_rate=50.0),
        _line("blank", "As-is line with no rates"),
    ])
    assert _values(BYP.boq_entries()) == {V("b1", "mat"), V("b1", "blank")}


def test_the_dedupe_merges_exact_duplicates_across_boqs(client):
    _boq("a", "B-A", "2026-09-01", [_line("x", "Ball  Valve 25mm", unit="Nos")])
    _boq("b", "B-B", "2026-10-01", [_line("y", "ball valve 25MM", unit="nos")])
    ents = BYP.boq_entries()
    assert len(ents) == 1
    # the NEWEST current BOQ owns the pick
    assert ents[0]["value"] == V("b", "y")


@pytest.mark.parametrize("one, two", [
    ("Pipe 150 NB", "Pipe 150mm dia"),       # nominal bore is not OD
    ("Plate 1.5 mm", "Plate 15 mm"),         # punctuation is NOT stripped
    ("MS pipe 50 NB", "GI pipe 50 NB"),      # material
    ("Pipe 50 NB 5mm thk", "Pipe 50 NB 6mm thk"),  # wall thickness
    ("Seamless pipe 80 NB", "ERW pipe 80 NB"),
])
def test_the_dedupe_never_merges_things_that_are_not_the_same(client, one, two):
    _boq("b1", "B-1", "2026-10-01", [_line("l1", one, s_base=1.0),
                                     _line("l2", two, s_base=1.0)])
    assert len(BYP.boq_entries()) == 2


def test_the_same_text_in_two_units_is_two_items(client):
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Pipe 25 NB", unit="Mtrs"),
                                     _line("l2", "Pipe 25 NB", unit="Nos")])
    assert len(BYP.boq_entries()) == 2


# ══ 3. The rate is a COST ═══════════════════════════════════════════════════

def test_the_boq_rate_is_the_supply_base_rate_never_the_selling_rate(client):
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve", s_base=100.0, s_rate=135.0)])
    rates, _makes = BYP.prefill_maps(with_spec=False)
    assert rates == {V("b1", "l1"): 100.0}


def test_a_selling_rate_only_line_prefills_blank(client):
    """An Excel BOQ imported with selling rates only: base blank → rate ABSENT."""
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve", s_base=None, s_rate=135.0)])
    rates, _ = BYP.prefill_maps(with_spec=False)
    assert rates == {}


def test_the_rate_comes_from_the_newest_boq_that_has_one(client):
    _boq("a", "B-A", "2026-08-01", [_line("x", "Ball valve", s_base=90.0)])
    _boq("b", "B-B", "2026-09-01", [_line("y", "Ball valve", s_base=95.0)])
    _boq("c", "B-C", "2026-10-01", [_line("z", "Ball valve", s_base=None, s_rate=140.0)])
    ents = BYP.boq_entries()
    assert len(ents) == 1
    assert ents[0]["value"] == V("c", "z") and ents[0]["rate"] == 95.0


def test_a_zero_base_rate_is_a_zero_not_a_blank(client):
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Free issue item", s_base=0.0)])
    rates, _ = BYP.prefill_maps(with_spec=False)
    assert rates == {V("b1", "l1"): 0.0}


def test_the_library_rate_is_its_supply_base_rate(client, hidden):
    _seed()
    by_value = {e["value"]: e for e in BYP.spec_entries()}
    for sid, s in STORE["specs"].items():
        for i, v in enumerate(s.get("variants") or []):
            want = v.get("default_supply_base_rate")
            got = by_value[f"spec:{sid}:{i}"]["rate"]
            assert got == (None if want is None else float(want))


def test_a_boq_make_in_the_remark_prefills_the_make(client):
    remark = "Make: SANT"
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Butterfly valve 80mm", s_base=1.0,
                                            remark=remark)])
    # `boq.make_from_remark()` arrived on 29 Oct 2026; on a checkout that
    # predates it the leaf offers no make at all, and that is what is pinned.
    parse = getattr(BQ, "make_from_remark", None)
    want = parse(remark) if parse else ""
    _rates, makes = BYP.prefill_maps(with_spec=False)
    assert makes == ({V("b1", "l1"): want} if want else {})


# ══ 4. The POST ═════════════════════════════════════════════════════════════

def test_a_mixed_order_saves_with_identity_from_the_source(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve 25mm", unit="Nos",
                                            s_base=100.0, s_rate=135.0)])
    sid, s = next((k, v) for k, v in STORE["specs"].items() if v.get("variants"))
    r = client.post("/purchase/create", data=_form(
        lines=[(V("b1", "l1"), 2, 100), (f"spec:{sid}:0", 3, 50)],
        extras=[("Cutting wheel", "Nos", 4, 10)]))
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    po = _newest_po()
    a, b = po["line_items"]
    assert a["name"] == "Ball valve 25mm" and a["unit"] == "Nos" and a["hsn"] == "73063090"
    assert a["part_no"] == ""
    assert (a["source"], a["src_boq_id"], a["src_line_id"], a["src_boq_ref"]) == \
        ("boq", "b1", L("l1"), "B-1")
    assert b["source"] == "spec" and b["src_spec_id"] == sid and b["src_vidx"] == 0
    assert b["part_no"] == s.get("code")
    assert b["hsn"] == s.get("supply_hsn", "")
    assert len(po["extra_lines"]) == 1
    assert po["subtotal"] == 200.0 + 150.0 + 40.0


def test_a_pick_never_carries_line_id_nor_sets_the_orders_boq_or_project(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve", s_base=1.0)])
    STORE["boqs"]["b1"]["project_id"] = "proj-x"
    assert client.post("/purchase/create", data=_form(
        lines=[(V("b1", "l1"), 1, 1)])).status_code == 302
    po = _newest_po()
    assert "line_id" not in po["line_items"][0]
    assert po["boq_id"] == "" and po["project_id"] == ""


def test_the_posted_text_is_never_trusted(client, hidden):
    """Only the value is posted; the name is the BOQ's, whatever else arrives."""
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Real name", s_base=1.0)])
    data = _form(lines=[(V("b1", "l1"), 1, 1)])
    data["line_name"] = ["Forged name"]
    assert client.post("/purchase/create", data=data).status_code == 302
    assert _newest_po()["line_items"][0]["name"] == "Real name"


@pytest.mark.parametrize("value", [
    "spec:no-such-spec:0",
    V("no-such-boq", "l1"),
    "boq:b1:no-such-line",
    V("b1", "h"),            # a header
    V("b1", "lab"),          # installation only
    V("old", "l1"),          # superseded
])
def test_a_stale_or_tampered_pick_is_refused_and_nothing_is_written(client, hidden, value):
    _seed()
    _boq("old", "B-0", "2026-09-01", [_line("l1", "Ball valve", s_base=1.0)])
    _boq("b1", "B-1", "2026-10-01", [_line("h", "Clause", header=True),
                                     _line("lab", "Labour", i_rate=10.0),
                                     _line("l1", "Ball valve", s_base=1.0)],
         supersedes="old")
    before = len(STORE["purchases"])
    r = client.post("/purchase/create", data=_form(lines=[(value, 1, 1)]))
    assert r.status_code == 200
    assert 'class="alert alert-error"' in r.get_data(as_text=True)
    assert len(STORE["purchases"]) == before


@pytest.mark.parametrize("vidx", ["99", "-1", "x"])
def test_a_bad_library_size_is_refused(client, hidden, vidx):
    _seed()
    sid = next(iter(STORE["specs"]))
    r = client.post("/purchase/create", data=_form(lines=[(f"spec:{sid}:{vidx}", 1, 1)]))
    assert r.status_code == 200 and 'alert alert-error' in r.get_data(as_text=True)


def test_a_pick_is_valid_whatever_the_switch_says(client, shown):
    """gap 38's rule kept: validity never reads the display switch."""
    _seed()
    sid = next(iter(STORE["specs"]))
    r = client.post("/purchase/create", data=_form(lines=[(f"spec:{sid}:0", 1, 1)]))
    assert r.status_code == 302


def test_a_catalogue_line_keeps_its_old_shape(client, shown):
    from product import ensure_demo_products
    ensure_demo_products()
    _seed()
    pid = "a1000001-beef-4000-8000-000000000001"
    assert client.post("/purchase/create", data=_form(lines=[(pid, 1, 5)])).status_code == 302
    line = _newest_po()["line_items"][0]
    assert not any(k.startswith("src_") for k in line) and "source" not in line


def test_a_refused_post_keeps_the_pick_selected(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve", s_base=1.0)])
    data = _form(lines=[(V("b1", "l1"), 0, 1)])     # qty 0 is refused
    html = client.post("/purchase/create", data=data).get_data(as_text=True)
    assert 'alert alert-error' in html
    assert f'value="{V("b1", "l1")}" selected' in html


# ══ 5. The snapshot ═════════════════════════════════════════════════════════

def test_editing_the_spec_after_save_moves_nothing(client, hidden):
    _seed()
    sid, s = next((k, v) for k, v in STORE["specs"].items() if v.get("variants"))
    assert client.post("/purchase/create", data=_form(
        lines=[(f"spec:{sid}:0", 1, 1)])).status_code == 302
    po = _newest_po()
    name = po["line_items"][0]["name"]
    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    s["title"] = "RENAMED IN THE LIBRARY"
    s["variants"][0]["unit"] = "Zzz"
    after = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert po["line_items"][0]["name"] == name
    assert "RENAMED IN THE LIBRARY" not in after
    assert view == after


def test_revising_or_deleting_the_boq_after_save_moves_nothing(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve 25mm", s_base=1.0)])
    assert client.post("/purchase/create", data=_form(
        lines=[(V("b1", "l1"), 2, 7)])).status_code == 302
    po = _newest_po()
    before = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    STORE["boqs"]["b1"]["line_items"][0]["description"] = "Changed on the BOQ"
    rev = copy.deepcopy(STORE["boqs"]["b1"])
    rev.update(id="b2", ref="B-1/R1", supersedes="b1")
    STORE["boqs"]["b2"] = rev
    assert client.get(f"/purchase/view/{po['id']}").get_data(as_text=True) == before
    STORE["boqs"].clear()
    assert client.get(f"/purchase/view/{po['id']}").get_data(as_text=True) == before
    assert "Ball valve 25mm" in before


# ══ 6. The page ═════════════════════════════════════════════════════════════

def test_the_page_carries_the_search_box_and_one_option_list(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve 25mm", s_base=1.0)])
    html = client.get("/purchase/create").get_data(as_text=True)
    assert 'class="pick-find"' in html and "function findItem(" in html
    assert '<template id="item-opts">' in html and "function fillOptions(" in html
    # the full list is written once; empty rows carry the placeholder alone
    assert html.count(f'value="{V("b1", "l1")}"') == 1
    # the search box is never posted
    assert 'name="pick-find"' not in html
    # bind() must not hand the search box to recalc()
    assert "#lines input:not(.pick-find)" in html


def test_the_boq_option_text_is_escaped(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", 'Valve <script>alert(1)</script>', s_base=1.0)])
    html = client.get("/purchase/create").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_the_reprice_form_keeps_a_picks_reference(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line("l1", "Ball valve", s_base=1.0)])
    assert client.post("/purchase/create", data=_form(
        lines=[(V("b1", "l1"), 2, 10)])).status_code == 302
    po = _newest_po()
    r = client.post(f"/purchase/edit/{po['id']}", data={
        "line_rate": ["12"], "line_discount": [""], "line_make": [""]})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:400]
    line = po["line_items"][0]
    assert line["price"] == 12.0 and line["total"] == 24.0
    assert line["src_line_id"] == L("l1")


# ══ 7. The label fits the screen (31 Oct 2026, after the first prod look) ════
# A native dropdown sizes its popup to its longest option; at 150 characters
# Chrome pushed it off the left edge and cut off what the item IS.

def test_a_child_label_is_size_first_and_short(client):
    lines = [_line("h", "Supply, Fabrication, Installtion, Testing of Heavy, 'C' class "
                        "Mild Steel pipes as per IS 1239 with roll grooved joints",
                   header=True, item_no="4"),
             _line("c", "50mm dia ISI", unit="Mtrs.", s_base=1.0, item_no="4.1")]
    lines[1]["parent_item_no"] = "4"
    _boq("b1", "B-1", "2026-10-01", lines)
    e = BYP.boq_entries()[0]
    assert e["label"].startswith("50mm dia ISI · Heavy, 'C' class Mild Steel")
    assert e["label"].endswith("(Mtrs.)")
    assert len(e["label"]) <= BYP.OPTION_CHARS + len(" (Mtrs.)")
    # the stored name is never cut by the label rule
    assert e["name"].startswith("Supply, Fabrication, Installtion")


def test_the_scope_of_work_lead_in_is_stripped_from_the_label_only(client):
    _boq("b1", "B-1", "2026-10-01", [_line(
        "l1", "Supply Installation testing & comissioning of Pendent Type Sprinkler",
        s_base=1.0)])
    e = BYP.boq_entries()[0]
    assert e["label"].startswith("Pendent Type Sprinkler")
    assert e["name"].startswith("Supply Installation testing")


def test_every_label_fits(client, hidden):
    _seed()
    BQ.ensure_demo_boq()
    for e in BYP.boq_entries() + BYP.spec_entries():
        bare = e["label"].rsplit(" (", 1)[0] if e["label"].endswith(")") else e["label"]
        assert len(bare) <= BYP.OPTION_CHARS + 1, e["label"]


def test_the_full_name_is_the_tooltip_and_the_search_text(client, hidden):
    _seed()
    _boq("b1", "B-1", "2026-10-01", [_line(
        "l1", "Supply of " + "very long words " * 12 + "Mild Steel tail", s_base=1.0)])
    html = PU._product_options()
    opt = html.split(f'value="{V("b1", "l1")}"', 1)[1].split("</option>", 1)[0]
    assert 'title="Supply of very long words' in opt
    assert "mild steel tail" in opt.split('data-s="', 1)[1].split('"', 1)[0]
    assert "Mild Steel tail" not in opt.split(">", 1)[1]      # cut from the label
    assert "getAttribute('data-s')" in BYP.FIND_JS
