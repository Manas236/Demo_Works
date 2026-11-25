"""
The TERMS LIBRARY, one terms list per quotation print, and the edit log for
the price summary fields (26 November 2026, CLIENT_CHANGES.md §0 ninety-first
block; Yogesh, 25 Nov: "add these terms, plus any others there are or you know
of, and keep a place to add more").
"""

import copy
import hashlib
import re

import pytest
from werkzeug.datastructures import MultiDict

import pricesummary as PS
from store import STORE


@pytest.fixture(autouse=True)
def _keep_the_settings():
    """`STORE["settings"]` is not reset between tests: put it back as found."""
    import branding as B
    import settings as S
    saved = copy.deepcopy(STORE["settings"])
    yield
    STORE["settings"].clear()
    STORE["settings"].update(saved)
    B.apply_settings(S.load_saved())


def _fresh_library():
    STORE["settings"].pop(PS.RECORD, None)
    PS.ensure_seeded()


def _doc_part(html: str) -> str:
    return html[html.index('<div class="doc-outer'):]


# ── migration and seeding ──────────────────────────────────────────────────

def test_the_seed_migrates_to_eleven_on_terms_in_their_categories():
    STORE["settings"][PS.RECORD] = {"title": "", "tax_line": "",
                                    "terms": list(PS.DEFAULT_TERMS)}   # the 25 Nov shape
    PS.ensure_seeded()
    lib = PS.library()
    first = lib[:11]
    assert [e["text"] for e in first] == list(PS.DEFAULT_TERMS), "text unchanged, in order"
    assert all(e["on"] for e in first)
    assert [e["category"] for e in first] == [
        "Scope", "Scope", "Exclusions", "Exclusions", "Site", "Exclusions",
        "Payment", "Payment", "Payment", "Payment", "Taxes"]
    rest = lib[11:]
    assert len(rest) == len(PS.EXTRA_TERMS) == 17
    assert all(not e["on"] for e in rest), "the extras are seeded OFF"
    assert [(e["category"], e["text"]) for e in rest] == list(PS.EXTRA_TERMS)
    assert PS.default_terms() == list(PS.DEFAULT_TERMS)


def test_an_edited_default_list_migrates_without_loss():
    edited = [PS.DEFAULT_TERMS[0], "Our own clause.", PS.DEFAULT_TERMS[6]]
    STORE["settings"][PS.RECORD] = {"title": "T", "tax_line": "", "terms": edited}
    PS.ensure_seeded()
    rec = STORE["settings"][PS.RECORD]
    lib = PS.library()
    assert [e["text"] for e in lib[:3]] == edited
    assert [e["category"] for e in lib[:3]] == ["Scope", "Commercial", "Payment"]
    assert all(e["on"] for e in lib[:3])
    assert PS.default_terms() == edited
    assert rec["legacy_terms"] == edited and "terms" not in rec
    assert rec["title"] == "T"


def test_seeding_twice_changes_nothing_and_a_deleted_extra_stays_deleted():
    _fresh_library()
    once = copy.deepcopy(STORE["settings"][PS.RECORD])
    PS.ensure_seeded()
    assert STORE["settings"][PS.RECORD] == once
    # delete one extra, edit one seed term: neither comes back
    lib = STORE["settings"][PS.RECORD]["library"]
    lib[:] = [e for e in lib if e["text"] != PS.EXTRA_TERMS[0][1]]
    lib[0]["text"] = "Edited."
    PS.ensure_seeded()
    texts = [e["text"] for e in PS.library()]
    assert PS.EXTRA_TERMS[0][1] not in texts and texts[0] == "Edited."


# ── a new document, the picker, own terms ──────────────────────────────────

def test_a_new_boq_gets_exactly_the_on_terms_in_library_order(client):
    import test_boq as TB
    _fresh_library()
    lib = STORE["settings"][PS.RECORD]["library"]
    lib[1]["on"] = False                                  # untick one seed term
    lib[-1]["on"] = True                                  # tick the last extra
    want = [e["text"] for e in lib if e["on"]]
    assert client.post("/boq/create", data=TB.FORM).status_code == 302
    b = next(iter(STORE["boqs"].values()))
    assert b[PS.FIELD_TERMS] == want
    page = client.get("/boq/create").get_data(as_text=True)
    rows = re.findall(r'<textarea name="summary_term" rows="2">(.*?)</textarea>', page, re.S)
    import html as H
    assert [H.unescape(r) for r in rows if r] == want


def test_a_new_quotation_starts_with_the_on_terms_and_the_hint(client):
    _fresh_library()
    page = client.get("/quotation/create").get_data(as_text=True)
    assert PS.QUOTE_TERMS_HINT in page
    q = {}
    PS.apply_form(q, MultiDict(), creating=True)
    assert q[PS.FIELD_TERMS] == PS.default_terms() == list(PS.DEFAULT_TERMS)


def test_the_picker_offers_only_library_terms_not_on_the_document():
    _fresh_library()
    html = PS.editor_html([PS.DEFAULT_TERMS[0]])
    picker = html[html.index('class="ps-lib-pick"'):html.index("</select>")]
    assert PS.DEFAULT_TERMS[1].split(".")[0] in picker
    import html as H
    opts = [H.unescape(v) for v in re.findall(r'<option value="([^"]+)">', picker)]
    assert PS.DEFAULT_TERMS[0] not in opts
    assert PS.EXTRA_TERMS[0][1] in opts
    for c in PS.CATEGORIES:
        assert f'<optgroup label="{c}">' in picker


def test_add_from_library_and_own_terms_with_and_without_save(client):
    import test_boq as TB
    _fresh_library()
    picked = PS.EXTRA_TERMS[4][1]
    data = MultiDict(list(TB.FORM.items()))
    data.add(PS.MARK_TERMS, "1")
    for text, cat in ((PS.DEFAULT_TERMS[0], ""), (picked, ""),
                      ("Own, kept on this BOQ only.", ""),
                      ("Own, also saved.", "Legal")):
        data.add(PS.FIELD_TERM, text)
        data.add(PS.FIELD_TERM_LIB, cat)
    assert client.post("/boq/create", data=data).status_code == 302
    b = next(iter(STORE["boqs"].values()))
    assert b[PS.FIELD_TERMS] == [PS.DEFAULT_TERMS[0], picked,
                                 "Own, kept on this BOQ only.", "Own, also saved."]
    lib = {e["text"]: e for e in PS.library()}
    assert "Own, kept on this BOQ only." not in lib
    assert lib["Own, also saved."]["category"] == "Legal"
    assert lib["Own, also saved."]["on"] is False, "saved from a document: OFF by default"


def test_without_the_settings_permission_nothing_reaches_the_library():
    _fresh_library()
    doc = {}
    form = MultiDict([(PS.MARK_TERMS, "1"), (PS.FIELD_TERM, "Sneaky."),
                      (PS.FIELD_TERM_LIB, "Legal")])
    PS.apply_form(doc, form, creating=True, may_save_library=False)
    assert doc[PS.FIELD_TERMS] == ["Sneaky."]
    assert "Sneaky." not in [e["text"] for e in PS.library()]
    assert "Also save to library" not in PS.editor_html([], may_save_library=False)
    assert "Also save to library" in PS.editor_html([], may_save_library=True)


def test_a_library_edit_never_changes_an_existing_documents_print(client):
    import test_boq as TB
    _fresh_library()
    assert client.post("/boq/create", data=TB.FORM).status_code == 302
    bid = next(iter(STORE["boqs"]))
    before = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    lib = STORE["settings"][PS.RECORD]["library"]
    lib[0]["text"] = "Rewritten in the library."
    del lib[1]
    after = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert before == after


# ── the payment warning ────────────────────────────────────────────────────

WARN150 = "Payment terms add up to 150%."


def test_the_seed_payment_split_warns_at_150_everywhere_but_paper(client):
    import test_boq as TB
    _fresh_library()
    assert PS.payment_warning(PS.DEFAULT_TERMS) == WARN150
    assert WARN150 in client.get("/settings/").get_data(as_text=True)
    assert client.post("/boq/create", data=TB.FORM).status_code == 302
    bid = next(iter(STORE["boqs"]))
    assert WARN150 in client.get(f"/boq/edit/{bid}").get_data(as_text=True)
    page = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert WARN150 in page, "the print page's toolbar says it"
    assert WARN150 not in _doc_part(page), "never on the printed document"
    bar = page[:page.index('<div class="doc-outer')]
    assert 'class="no-print ps-pay-bar"' in bar


def test_payment_terms_that_add_up_to_100_say_nothing(client):
    terms = ["40% advance with the order.", "Balance 60% payment against running bills.",
             "Goods and Services Tax at 18% extra."]          # not a payment line
    assert PS.payment_total(terms, set()) == 100.0
    assert PS.payment_warning(terms, set()) == ""
    assert "Payment terms add up" not in PS.editor_html(terms).split("<template")[0] \
        .replace('<div class="ps-pay-note" role="note" hidden></div>', "")
    assert PS.payment_note_html(terms) == ""
    # a line typed on the document counts when it MATCHES a Payment library term
    assert PS.payment_total(["Clause: 70%."], {"Clause: 70%."}) == 70.0
    assert PS.payment_total(["Clause: 70%."], set()) is None


def test_the_quotation_print_toolbar_warns_too(client):
    q = _quote(summary_terms=list(PS.DEFAULT_TERMS))
    page = client.get(f"/quotation/view/{q['id']}").get_data(as_text=True)
    assert WARN150 in page and WARN150 not in _doc_part(page)


# ── one terms list per quotation print ─────────────────────────────────────

def _quote(**over):
    import test_print_golden as G
    q = {"id": "q-lib", "ref": "QT-0042", "date": "2026-04-10",
         "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
         "to": "Prudent Teqtis Pvt Ltd\nMr R Nair\nSurvey 21, Whitefield\nBangalore, Karnataka - 560066",
         "bill_gstin": "29AABCP1234C1ZX", "bill_state": "Karnataka",
         "ship_same": "on", "line_items": G._line_items(),
         "subtotal": 612880.0, "tax_type": "cgst_sgst", "tax_info": dict(G.TAX_INFO),
         "grand_total": 723198.40, "total_qty": 122.0,
         "validity_days": "30", "delivery_terms": "FOR Site", "payment_terms": "50% advance",
         "dispatch_through": "By Road", "delivery_date": "2026-05-01"}
    q.update(over)
    import pipeline as P
    P.ensure_fields(q)
    q["stage_history"] = []
    STORE["quotations"][q["id"]] = q
    return q


def test_summary_on_prints_one_terms_list_and_the_quotations_own_data(client):
    q = _quote(summary_terms=["Only this term.", "And this one."])
    doc = _doc_part(client.get(f"/quotation/view/{q['id']}").get_data(as_text=True))
    assert '<div class="tnc-section">' not in doc, "the old block does not print"
    assert "Terms and Conditions" not in doc
    assert doc.count("Only this term.") == 1 and doc.count("And this one.") == 1
    cover = doc[doc.index('<div class="ps-cover">'):doc.index('<div class="doc-box">')]
    for line in ("<b>Terms of Delivery:</b> FOR Site", "<b>Delivery:</b> 2026-05-01",
                 "<b>Dispatch Through:</b> By Road", "<b>Validity:</b> 30 days"):
        assert line in cover, line
    assert "50% advance" not in cover, "payment terms text does not print with the cover"
    # only filled ones
    q.update(delivery_date="", dispatch_through="", validity_days="")
    cover = _doc_part(client.get(f"/quotation/view/{q['id']}").get_data(as_text=True))
    assert "<b>Validity:</b>" not in cover and "<b>Dispatch Through:</b>" not in cover
    assert "<b>Terms of Delivery:</b> FOR Site" in cover


# Captured at 5c0749c (the last commit BEFORE the price summary pass) by
# rendering this same quotation through that commit's code in a git worktree:
# the printed document (from `<div class="doc-outer">` to the end) hashed
# d0e5e331833c7f28 / 49,919 characters. MEASURED on 26 Nov 2026: the whole
# page here equals that commit's whole page (b1ed6b6cd527fa24 / 132,163) once
# the screen-only Portrait / Landscape switch is cut out of the action bar,
# which is the one line the price summary pass added to a summary-OFF page.
SUMMARY_OFF_DOC = ("d0e5e331833c7f28", 49919)


def test_summary_off_prints_exactly_as_before_the_price_summary_pass(client):
    import test_print_golden as G
    saved = STORE["settings"].get("company")
    import settings as S
    import branding as B
    STORE["settings"]["company"] = dict(S.DEMO_COMPANY)
    B.apply_settings(S.load_saved())
    try:
        q = _quote(price_summary_on=False, summary_terms=["Never printed."])
        html = client.get(f"/quotation/view/{q['id']}").get_data(as_text=True)
    finally:
        if saved is None:
            STORE["settings"].pop("company", None)
        else:
            STORE["settings"]["company"] = saved
        B.apply_settings(S.load_saved())
    doc = _doc_part(html)
    assert (hashlib.sha256(doc.encode()).hexdigest()[:16], len(doc)) == SUMMARY_OFF_DOC
    assert "Payment terms add up" not in html, "no cover, no terms printed, no note"
    assert G  # the fixture data lives there


# ── the edit log ───────────────────────────────────────────────────────────

def _entries(rec, field):
    return [e for e in rec.get("edit_log") or [] if e.get("field") == field]


def test_boq_edits_of_terms_tick_and_orientation_are_logged(client):
    import test_boq_edit_nov2 as TE
    boq = TE._boq(client)
    before_terms = list(boq[PS.FIELD_TERMS])
    r = TE._post(client, boq, **{PS.MARK_ON: "1", PS.MARK_TERMS: "1",
                                 PS.FIELD_TERM: ["First.", "Second."],
                                 PS.FIELD_TERM_LIB: ["", ""]})
    assert r.status_code == 302
    (t,) = _entries(boq, "Summary terms")
    assert t["before"].startswith("1. " + before_terms[0])
    assert t["after"] == "1. First.\n2. Second."
    (o,) = _entries(boq, "Price summary page")
    assert (o["before"], o["after"]) == ("Yes", "No")
    assert t["by"]
    client.post(f"/boq/print/{boq['id']}/orientation", data={PS.FIELD_ORIENT: "portrait"})
    (p,) = _entries(boq, "Print orientation")
    assert (p["before"], p["after"]) == ("Landscape", "Portrait") and p["by"]
    client.post(f"/boq/print/{boq['id']}/orientation", data={PS.FIELD_ORIENT: "portrait"})
    assert len(_entries(boq, "Print orientation")) == 1, "no change, no entry"


def test_quotation_edits_of_terms_tick_and_orientation_are_logged(client):
    import test_quotation_edit as TQ
    q = TQ._q()
    q[PS.FIELD_TERMS] = ["Old term."]
    data = MultiDict(list(TQ._form(q).items()))
    data.add(PS.MARK_ON, "1")
    data.add(PS.MARK_TERMS, "1")
    data.add(PS.FIELD_TERM, "New term.")
    data.add(PS.FIELD_TERM_LIB, "")
    assert client.post(f"/quotation/edit/{q['id']}", data=data).status_code == 302
    q = STORE["quotations"][q["id"]]
    (t,) = _entries(q, "Summary terms")
    assert (t["before"], t["after"]) == ("1. Old term.", "1. New term.")
    assert _entries(q, "Price summary page")[0]["after"] == "No"
    client.post(f"/quotation/print/{q['id']}/orientation", data={PS.FIELD_ORIENT: "landscape"})
    (p,) = _entries(q, "Print orientation")
    assert (p["before"], p["after"]) == ("Portrait", "Landscape")


# ── escaping and wording ───────────────────────────────────────────────────

def test_library_strings_are_escaped_and_no_em_dash_in_new_text(client):
    evil = '<script>alert(1)</script>'
    _fresh_library()
    PS.library_add(evil, "Legal")
    assert evil not in client.get("/settings/").get_data(as_text=True)
    assert evil not in client.get("/boq/create").get_data(as_text=True)
    assert evil not in PS.editor_html([evil])
    for cat, text in PS.EXTRA_TERMS:
        assert "—" not in text
    for s in (PS.QUOTE_TERMS_HINT, PS.library_editor_html([]), PS.editor_html([]),
              PS.payment_warning(["150% advance payment."])):
        assert "—" not in s and "&mdash;" not in s
