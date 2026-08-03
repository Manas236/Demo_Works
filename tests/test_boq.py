"""
Phase 1 acceptance — section A of the Sify BOQ, entered by hand.

The payload below is section A of `sify_boq.xlsx` transcribed from the sheet:
21 priced lines under one specification header, two areas (External / L0),
supply and installation priced separately, three lines whose agreed rate
deliberately differs from base x (1 + escalation), and two lines whose base
rate is "-" because the rate was negotiated directly.

It is typed out rather than read from the workbook on purpose. The importer is
Phase 2; this test has to prove the form and the printed document stand up on
their own, with nothing but a browser and somebody keying in a schedule.

    ACCEPTANCE: the section subtotal reads 483764.50 supply / 311350 installation.
"""

import json

import pytest

from store import STORE

# The specification paragraph off row 5 — 1184 characters, kept verbatim
# including the client's own mojibake around "C" class, because the point of
# carrying it here is that real text of this size survives the round trip.
SPEC_4 = (
    'Supply, Fabrication, Installtion, Testing of Heavy, �C� class Mild Steel '
    'pipes as per IS 1239 and "ISI" marked with Roll Grooved joints or '
    'Pre-fabricated Flanged joints including  neccessary Grooved or weld Type '
    'flanges and malleable iron fittings & MS supports. The work includes, the '
    'preparation of Sprinkler pipe network as per plan, by cutting the pipes to '
    'correct lengths and making each segment as per shop darwings. All required '
    'fittings shall be Heavy Duty threaded malleable iron fitting used for pipe '
    'size up to 50 NB & below and Rolled grooved or Socket weld flange Joints '
    'for 65 NB & above.\n'
    'Piping shall be Pre-Fabricated off-site  and assembled at site.    Welded '
    'joints shall not be acceptable.\n'
    'Fixing with clamps to M.S. brackets / hangers including inserted rubber '
    'gaskets, painting,  with one coat of Zinc Dichromate primer and two coats '
    'of approved Red enamel paint.\n'
    'Hydraulic Testing of full piping netwrok shall be done at 14 kgs/cm2 '
    'pressure for 24 hours.\n'
    'Vendor shall submitt all the Manufacturing and Test certifiates with the '
    'delivery of pipes at site. All pipes and fittings shall be ISI Marked.\n'
    'Vendor should provide FDT calculations alongside shop drawings.'
)


def line(item_no, desc, unit, ext, l0, s_base, s_pct, s_rate,
         i_base, i_pct, i_rate, parent="", remark=""):
    """One priced line. `ext`/`l0` are the two area quantities; None = blank."""
    area = {}
    if ext is not None:
        area["External"] = ext
    if l0 is not None:
        area["L0"] = l0
    return {
        "item_no": item_no, "parent_item_no": parent, "section": "A",
        "is_header": False, "description": desc, "remark": remark, "unit": unit,
        "area_qty": area, "total_qty": "",
        "supply_base_rate": s_base, "supply_escalation_pct": s_pct,
        "supply_rate": s_rate, "supply_hsn": "", "supply_gst_rate": "18",
        "install_base_rate": i_base, "install_escalation_pct": i_pct,
        "install_rate": i_rate, "install_sac": "", "install_gst_rate": "18",
    }


SECTION_A = {
    "sections": [{
        "code": "A",
        "title": "WET SPRINKLER SYSTEM, As per Techncial Specifictions Part-A",
        "areas": ["External", "L0"],
    }],
    "lines": [
        # The specification header — paragraph only, no quantity, no rate.
        {"item_no": "4", "parent_item_no": "", "section": "A", "is_header": True,
         "description": SPEC_4, "remark": "", "unit": "", "area_qty": {},
         "total_qty": "", "supply_base_rate": "", "supply_escalation_pct": "",
         "supply_rate": "", "supply_hsn": "", "supply_gst_rate": "",
         "install_base_rate": "", "install_escalation_pct": "",
         "install_rate": "", "install_sac": "", "install_gst_rate": ""},

        # 4.1 - 4.8, the pipe schedule under it.
        line("4.1", "150mm dia     ISI", "Mtrs.", None,   4, "1760", "15", "2024",   "1200", "0", "1200", parent="4"),
        line("4.2", "100mm dia     ISI", "Mtrs.", None,  12, "1040", "15", "1196",    "900", "0",  "900", parent="4"),
        line("4.3", "80mm dia     ISI",  "Mtrs.", None,  62,  "850", "15", "977.5",   "800", "0",  "800", parent="4"),
        line("4.4", "65mm dia     ISI",  "Mtrs.", None,  90,  "750", "15", "862.5",   "700", "0",  "700", parent="4"),
        line("4.5", "50mm dia     ISI",  "Mtrs.", None,  60,  "650", "15", "747.5",   "600", "0",  "600", parent="4"),
        line("4.6", "40mm dia     ISI",  "Mtrs.",   12,  28,  "625", "15", "718.75",  "400", "0",  "400", parent="4"),
        line("4.7", "32mm dia     ISI",  "Mtrs.",   10,  28,  "600", "15", "690",     "300", "0",  "300", parent="4"),
        line("4.8", "25mm dia     ISI",  "Mtrs.",   18,  80,  "430", "15", "494.5",   "250", "0",  "250", parent="4"),

        # Rate deliberately above base x (1 + escalation) — the sprinkler guard
        # is priced into the line and the client's own sheet says so in the
        # remark column. The form must keep the rate as entered.
        line("5", "Supply Installation testing & comissioning of Upright Type, Quick "
                  "Response, Intermidiate, Red colour, Sprinkler 15 NB, K-80, 68 deg "
                  "with SS 304 sprinkler guard.", "Nos", 20, 135, "200", "", "410",
             "200", "0", "200", remark="sprinkler + guard"),
        line("6", "Supply Installation testing & comissioning of Upright Type, Quick "
                  "Response Sprinkler, 15 NB.", "Nos", None, 1, "200", "", "450",
             "200", "0", "200", remark="sprinkler + guard"),
        line("9", "Supply Installation testing & comissioning of Pendent Type, "
                  "Standard Response Sprinkler with rosette plate.", "Nos", None, 1,
             "200", "", "310", "200", "0", "200", remark="sprinkler + rossete plate"),

        # Base rate "-" — negotiated directly, not escalated. Not zero.
        line("17", "Supply, Installation, testing & comissioning of 1500 mm Long SS "
                   "Braided Sprinkler Flexible Drop Pipes.", "Nos", None, 1,
             "-", "", "1800", "-", "", "400"),

        line("17", "Supply, Installation, testing & comissioning of Cast Iron 150 NB "
                   "Gear operated Butterfly valve.", "Nos", None, 1,
             "11750", "7", "14572.5", "1500", "0", "1500",
             remark="2000/nos extra for Tamper switch"),
        line("19", "Supply, Installation, Testing and commissioning of 50-150 NB, "
                   "Flow Switch.", "Nos", 1, 1, "6500", "7", "6955", "3000", "0", "3000"),
        line("20", "Supply installation Testing & commissioning of 50 mm dia Gate "
                   "valve with Tamper switch.", "Nos", None, 1, "5500", "7", "7885",
             "600", "0", "600", remark="2000/nos extra for Tamper switch"),
        line("21", "Supply installation Testing & commissioning of 50 mm dia Ball "
                   "valve with Tamper switch.", "Nos", 4, 3, "2450", "7", "4621.5",
             "600", "0", "600", remark="2000/nos extra for Tamper switch"),
        line("22", "Supply installation Testing & commissioning of 25 mm Test Valve "
                   "Drain assembly.", "Nos", None, 1, "5500", "7", "5885", "5250", "0", "5250"),
        line("23", "Supply installation Testing & commissioning of 25mm dia Air Vent "
                   "Valve.", "Nos", None, 1, "1000", "7", "1070", "500", "0", "500"),
        line("24", "Supply installation Testing & commissioning of Pressure Guage "
                   "with range 0-16 bar.", "Nos", None, 1, "1500", "15", "1725",
             "400", "0", "400"),
        line("25", "Providing, Fixing, Fabricating, Painting of the MS C-Channel "
                   "(100 X 50) support assembly for the pipes running on the "
                   "compound wall.", "Kgs.", 450, None, "65", "7", "69.55",
             "100", "0", "100"),
    ],
}

FORM = {
    "date": "2026-07-31",
    "rev_no": "0",
    "project_name": "Sify Bangalore",
    "site_location": "Bangalore, Karnataka",
    "rate_basis_label": "Mohali Rates",
    "account_name": "Prudent Teqtis Pvt Ltd",
    "bill_city": "Bengaluru",
    "bill_state": "Karnataka",
    "payment_terms": "50% Advance, Balance Before Dispatch",
    "delivery_terms": "FOR Site",
    "boq_json": json.dumps(SECTION_A),
}


@pytest.fixture()
def created(client):
    r = client.post("/boq/create", data=FORM)
    assert r.status_code == 302, r.data[:2000]
    assert len(STORE["boqs"]) == 1
    bid = next(iter(STORE["boqs"]))
    return bid, STORE["boqs"][bid]


# ── The acceptance ─────────────────────────────────────────────────────────

def test_section_a_subtotals(created):
    import boq

    _bid, b = created
    supply, install = boq.section_totals(b, "A")
    assert round(supply, 2) == 483764.50
    assert round(install, 2) == 311350.00


def test_subtotals_print_on_the_document(client, created):
    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "BASIC VALUE SUBTOTAL (A)" in html
    # Indian digit grouping, no currency symbol — quotation._inr().
    assert "4,83,764.50" in html
    assert "3,11,350.00" in html


def test_record_level_subtotals_match_the_lines(created):
    import boq

    _bid, b = created
    supply, install, total = boq.boq_totals(b)
    assert round(b["supply_subtotal"], 2) == round(supply, 2) == 483764.50
    assert round(b["install_subtotal"], 2) == round(install, 2) == 311350.00
    assert round(b["subtotal"], 2) == round(total, 2) == 795114.50


# ── The shape (§4.2 / §4.3) ────────────────────────────────────────────────

def test_item_no_is_a_string_never_a_float(created):
    _bid, b = created
    for li in b["line_items"]:
        assert isinstance(li["item_no"], str)
        assert isinstance(li["parent_item_no"], str)
    nos = [li["item_no"] for li in b["line_items"]]
    assert "4.1" in nos and "4.4" in nos
    assert not any("0000000" in n for n in nos)


def test_item_no_normaliser_kills_float_dust():
    """The two values the source workbook actually holds."""
    from boq import _item_no

    assert _item_no(4.0999999999999996) == "4.1"
    assert _item_no(4.4000000000000004) == "4.4"
    assert _item_no(4.5999999999999996) == "4.6"
    assert _item_no("24.b") == "24.b"
    assert _item_no(24) == "24"


def test_dash_base_rate_is_none_not_zero(created):
    """
    "-" means the rate was agreed directly. It is not zero and not missing.
    """
    _bid, b = created
    drop = [li for li in b["line_items"]
            if li["description"].startswith("Supply, Installation, testing & comissioning of 1500")][0]
    assert drop["supply_base_rate"] is None
    assert drop["install_base_rate"] is None
    assert drop["supply_rate"] == 1800.0
    assert drop["install_rate"] == 400.0


def test_rate_is_kept_as_entered_when_it_contradicts_the_escalation(created):
    """
    Item 20 is 5500 + 7%, which is 5885 — but the agreed rate is 7885 because a
    tamper switch is priced into the line. Recomputing it from the escalation
    would rewrite an agreed price.
    """
    _bid, b = created
    li = [x for x in b["line_items"] if x["item_no"] == "20"][0]
    assert li["supply_base_rate"] == 5500.0
    assert li["supply_escalation_pct"] == 7.0
    assert li["supply_rate"] == 7885.0
    assert li["supply_amount"] == 7885.0


def test_header_row_carries_the_spec_and_no_numbers(created):
    _bid, b = created
    hdr = [li for li in b["line_items"] if li["is_header"]][0]
    assert hdr["item_no"] == "4"
    assert len(hdr["description"]) > 1000
    assert hdr["total_qty"] == 0.0
    assert hdr["supply_amount"] == 0.0
    assert hdr["install_amount"] == 0.0
    assert hdr["area_qty"] == {}


def test_header_row_is_excluded_from_the_subtotal(created):
    """A header has no amount, so it cannot move a subtotal even if one crept in."""
    import boq

    _bid, b = created
    b["line_items"][0]["supply_amount"] = 999999.0   # a header, per the test above
    supply, _install = boq.section_totals(b, "A")
    assert round(supply, 2) == 483764.50


def test_total_qty_is_the_sum_of_its_areas(created):
    _bid, b = created
    for li in b["line_items"]:
        if li["is_header"] or not li["area_qty"]:
            continue
        assert round(sum(li["area_qty"].values()), 6) == round(li["total_qty"], 6)
    # 4.6: 12 External + 28 L0 = 40
    li46 = [x for x in b["line_items"] if x["item_no"] == "4.6"][0]
    assert li46["total_qty"] == 40.0
    assert li46["area_qty"] == {"External": 12.0, "L0": 28.0}


def test_blank_area_is_absent_not_zero(created):
    """
    An item that is not on a floor has no entry for it. Storing 0.0 would put
    every item on every floor with a quantity of none, which is a different
    claim and prints a different sheet.
    """
    _bid, b = created
    li41 = [x for x in b["line_items"] if x["item_no"] == "4.1"][0]
    assert li41["area_qty"] == {"L0": 4.0}
    assert "External" not in li41["area_qty"]


def test_areas_live_on_the_section(created):
    _bid, b = created
    assert b["sections"] == [{
        "code": "A",
        "title": "WET SPRINKLER SYSTEM, As per Techncial Specifictions Part-A",
        "areas": ["External", "L0"],
    }]


def test_ref_is_fy_scoped_and_max_plus_one(client, created):
    _bid, b = created
    assert b["ref"] == "SF/BOQ/26-27/0001"
    assert b["fy"] == "26-27"
    client.post("/boq/create", data=FORM)
    refs = sorted(x["ref"] for x in STORE["boqs"].values())
    assert refs == ["SF/BOQ/26-27/0001", "SF/BOQ/26-27/0002"]


# ── The document ───────────────────────────────────────────────────────────

def test_document_prints_landscape(client, created):
    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "size:A4 landscape" in html


def test_responsive_breakpoint_is_scoped_to_screen(client, created):
    """An unscoped max-width breakpoint fires on paper — ABOUT.md §5."""
    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "@media screen and (max-width:760px)" in html
    assert "@media (max-width:760px)" not in html


def test_area_columns_are_the_sections_own(client, created):
    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert '<th class="b-area">External</th>' in html
    assert '<th class="b-area">L0</th>' in html


def test_dash_prints_as_a_dash_not_a_zero(client, created):
    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert '<td class="b-base">-</td>' in html


def test_remarks_do_not_print(client, created):
    """
    Internal pricing notes stay off the customer's copy — the same call the
    quotation makes about deal-desk fields. `boq.PRINT_REMARKS` flips it.
    """
    import boq

    assert boq.PRINT_REMARKS is False
    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "2000/nos extra for Tamper switch" not in html
    # …but the value is still on the record.
    li = [x for x in STORE["boqs"][bid]["line_items"] if x["item_no"] == "20"][0]
    assert li["remark"] == "2000/nos extra for Tamper switch"


def test_user_text_is_escaped(client):
    """
    ~1500 characters of client text go onto a printed document. proforma.py's
    discipline, not quotation.py's.
    """
    payload = json.loads(FORM["boq_json"])
    payload["lines"][1]["description"] = '<script>alert("x")</script> & 100mm'
    form = dict(FORM, boq_json=json.dumps(payload),
                account_name='Acme <b>Ltd</b> & Co')
    r = client.post("/boq/create", data=form)
    bid = next(iter(STORE["boqs"]))
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert "Acme &lt;b&gt;Ltd&lt;/b&gt; &amp; Co" in html


# ── Validation ─────────────────────────────────────────────────────────────

def test_rejected_post_writes_nothing(client):
    r = client.post("/boq/create", data=dict(FORM, account_name=""))
    assert r.status_code == 200
    assert STORE["boqs"] == {}
    assert "customer account name" in r.get_data(as_text=True)


def test_line_in_an_undeclared_section_is_rejected(client):
    payload = json.loads(FORM["boq_json"])
    payload["lines"][1]["section"] = "Z"
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(payload)))
    assert r.status_code == 200
    assert STORE["boqs"] == {}
    assert "not defined above" in r.get_data(as_text=True)


def test_duplicate_section_code_is_rejected(client):
    payload = json.loads(FORM["boq_json"])
    payload["sections"].append({"code": "A", "title": "again", "areas": []})
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(payload)))
    assert r.status_code == 200
    assert STORE["boqs"] == {}
    assert "used twice" in r.get_data(as_text=True)


def test_bad_hsn_is_rejected(client):
    payload = json.loads(FORM["boq_json"])
    payload["lines"][1]["supply_hsn"] = "8413-A"
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(payload)))
    assert r.status_code == 200
    assert STORE["boqs"] == {}
    assert "4, 6 or 8 digits" in r.get_data(as_text=True)


def test_a_nil_priced_line_is_valid(client):
    """
    Section B rows 89/91/92/93 carry a quantity and no rate at all. They are
    real lines and must not be rejected — handover §4.2 rule 7.
    """
    payload = json.loads(FORM["boq_json"])
    payload["lines"].append(line(
        "37", "Exacavation of trenches up to 1.5 mts. in depth.", "Mtrs",
        140, None, "", "", "", "", "", ""))
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(payload)))
    assert r.status_code == 302
    b = next(iter(STORE["boqs"].values()))
    nil = [x for x in b["line_items"] if x["item_no"] == "37"][0]
    assert nil["total_qty"] == 140.0
    assert nil["supply_rate"] == 0.0
    assert nil["supply_amount"] == 0.0


def test_section_with_no_areas_takes_a_typed_total(client):
    """
    Section C declares no areas at all: the total quantity stands alone and
    there is nothing to reconcile it against.
    """
    payload = {
        "sections": [{"code": "C", "title": "FIRE FIGHTING PUMPS", "areas": []}],
        "lines": [dict(line("1a", "Main Sprinkler Pump", "Nos.", None, None,
                            "", "", "", "60000", "0", "60000"),
                       section="C", total_qty="1")],
    }
    r = client.post("/boq/create", data=dict(FORM, boq_json=json.dumps(payload)))
    assert r.status_code == 302
    b = next(iter(STORE["boqs"].values()))
    li = b["line_items"][0]
    assert li["area_qty"] == {}
    assert li["total_qty"] == 1.0
    assert li["install_amount"] == 60000.0
    assert li["supply_amount"] == 0.0


# ── The register ───────────────────────────────────────────────────────────

def test_register_lists_the_boq(client, created):
    html = client.get("/boq/").get_data(as_text=True)
    assert "SF/BOQ/26-27/0001" in html
    assert "Sify Bangalore" in html


def test_view_of_a_missing_boq_redirects(client):
    r = client.get("/boq/view/nope")
    assert r.status_code == 302
    assert "/boq/" in r.headers["Location"]


def test_every_row_has_the_same_column_count(client, created):
    """
    Every table row must span exactly as many columns as the head declares.

    A colspan that is one out does not raise — the browser silently reflows the
    table and the money columns stop lining up under their headings, which is
    the kind of defect that only shows up on paper after it has been sent.
    """
    from html.parser import HTMLParser

    bid, _b = created
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    body = html.split('<table class="boq-table">')[1].split("</table>")[0]

    class Rows(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.cur, self.pending = [], None, {}
            self.row_i = 0

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "tr":
                self.cur = self.pending.pop(self.row_i, 0)
            elif tag in ("td", "th") and self.cur is not None:
                self.cur += int(a.get("colspan", 1))
                for r in range(1, int(a.get("rowspan", 1))):
                    self.pending[self.row_i + r] = self.pending.get(self.row_i + r, 0) + int(a.get("colspan", 1))

        def handle_endtag(self, tag):
            if tag == "tr" and self.cur is not None:
                self.rows.append(self.cur)
                self.cur = None
                self.row_i += 1

    p = Rows()
    p.feed(body)
    assert p.rows, "no rows parsed"
    assert len(set(p.rows)) == 1, f"ragged table: column counts {sorted(set(p.rows))}"
