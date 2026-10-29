"""
The preloaded authorised signature and company stamp (26 October 2026) —
CLIENT_CHANGES.md §0, the fifty-third block, change 1.

The rules under test:

* an **Owner** uploads, replaces and removes each mark at `/settings`; a
  **Director** (who holds `settings.edit`) is refused on the POST with a 403
  and nothing written, and is not shown the control at all;
* what is stored is a fresh PNG written by Pillow — not the uploaded bytes —
  so transparency survives, metadata does not, and a file that is not a
  JPEG/PNG/WebP by its leading bytes is refused;
* with a mark set, it prints in `docsheet.sig_block()`'s right-hand panel on
  every listed document — the tax invoice (ordinary, raised from a BOQ, the RA
  bill and the merged RA), the proforma, the quotation, the purchase order, the
  draft PO, the work order and the delivery challan — drafts included, on every
  statutory copy, and on the challan on OUR side only;
* with neither set, every one of those documents is byte-for-byte what it was.
  `tests/test_print_golden.py` and `tests/test_work_orders.py` pin the sheets
  that have goldens; the quotation has none, so this file pins its signature
  panel against the literal it used to write by hand;
* the statutory copy labels and the CANCELLED overprint survive both states.
"""

import base64
import io
import re

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, PngImagePlugin  # noqa: E402

import auth  # noqa: E402
import branding as B  # noqa: E402
import docsheet as DS  # noqa: E402
import pipeline as P  # noqa: E402
import settings as ST  # noqa: E402
from conftest import EXE_BYTES, PDF_BYTES  # noqa: E402
from store import STORE  # noqa: E402
from test_print_golden import (  # noqa: E402,F401
    GOLD_DC, GOLD_DPO, GOLD_MERGED, GOLD_PI, GOLD_PO, GOLD_Q, GOLD_TI,
    golden, golden_dc, golden_dpo, golden_merged, golden_ms, golden_ra,
    pinned_identity)
from test_work_orders import GOLD_WO, golden_wo  # noqa: E402,F401


# ── Files ──────────────────────────────────────────────────────────────────

def _signature_png() -> bytes:
    """A blue stroke on a transparent ground, carrying a text chunk to strip."""
    img = Image.new("RGBA", (186, 94), (0, 0, 0, 0))
    for x in range(20, 160):
        for y in (40, 41, 42):
            img.putpixel((x, y), (20, 40, 160, 255))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Author", "somebody's scanner")
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=meta)
    return buf.getvalue()


def _stamp_png() -> bytes:
    """Transparent corners, an opaque disc — the shape of the client's stamp."""
    img = Image.new("RGBA", (174, 174), (0, 0, 0, 0))
    for x in range(174):
        for y in range(174):
            if (x - 87) ** 2 + (y - 87) ** 2 < 80 ** 2:
                img.putpixel((x, y), (30, 90, 200, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _jpeg(w=900, h=450) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (250, 250, 250)).save(buf, "JPEG")
    return buf.getvalue()


def _post(client, action, data=None, name="mark.png"):
    form = {"action": action}
    if data is not None:
        form["image"] = (io.BytesIO(data), name)
    return client.post("/settings/", data=form, content_type="multipart/form-data")


def _decoded(uri: str) -> Image.Image:
    img = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    img.load()
    return img


# ── People ─────────────────────────────────────────────────────────────────

def _user(name, role_ids):
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, name.replace("-", " ").title(), f"pw-{name}-12345",
                            role_ids, created_by="sign-stamp-test")


def _as(client, user):
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = user["id"]


@pytest.fixture()
def director(client):
    auth.ensure_builtin_roles()
    d = _user("mark-director", ["role-director"])
    assert not auth.is_owner(d) and "settings.edit" in auth.permissions_of(d)
    yield d
    STORE["users"].pop(d["id"], None)


@pytest.fixture()
def clean_marks(client):
    """Neither mark set going in; neither left behind for the next test."""
    def _strip():
        rec = STORE["settings"].get(ST.RECORD_ID)
        if rec:
            for k in B.IMAGE_KEYS:
                rec.pop(k, None)
        B.apply_settings(ST.load_saved())
    _strip()
    yield
    _strip()


@pytest.fixture()
def marks(client, pinned_identity, clean_marks):
    """Both marks uploaded by the Owner, through the route. Yields the two URIs."""
    assert _post(client, "signature_upload", _signature_png()).status_code == 302
    assert _post(client, "stamp_upload", _stamp_png()).status_code == 302
    assert B.SIGNATURE_IMAGE and B.STAMP_IMAGE
    yield B.SIGNATURE_IMAGE, B.STAMP_IMAGE


# The listed documents and the copies each print. A tax invoice, an RA bill, a
# merged RA and a challan print their statutory set — three copies, three
# signature panels.
DOCS = [
    ("tax invoice",        f"/invoice/view/{GOLD_TI}",   3),
    ("RA tax invoice",     "/ra/print/gold-ra",           3),
    ("merged RA",          f"/merged/print/{GOLD_MERGED}", 3),
    ("proforma",           f"/proforma/view/{GOLD_PI}",  1),
    ("quotation",          f"/quotation/view/{GOLD_Q}",  1),
    ("purchase order",     f"/purchase/view/{GOLD_PO}",  1),
    ("draft PO",           f"/po/print/{GOLD_DPO}",      1),
    ("work order",         f"/wo/print/{GOLD_WO}",       1),
    ("delivery challan",   f"/dc/print/{GOLD_DC}",       3),
]
DOC_IDS = [d[0] for d in DOCS]


@pytest.fixture()
def every_doc(golden, golden_ra, golden_dc, golden_dpo, golden_merged, golden_wo):
    """Every listed document, from the print goldens' own fixed records."""
    yield


def _panels(html: str) -> list:
    """Each `.sig-block` on the page, up to the close of its right-hand panel."""
    out = []
    for m in re.finditer(r'<div class="sig-block"', html):
        end = html.index('<div class="sig-name"', m.start())
        out.append(html[m.start():html.index("</div>", end) + 6])
    return out


# ══ 1. With both marks set, each listed document prints them ═══════════════

@pytest.mark.parametrize("name,url,copies", DOCS, ids=DOC_IDS)
def test_each_document_prints_the_signature_and_the_stamp(client, every_doc, marks,
                                                           name, url, copies):
    sign, stamp = marks
    r = client.get(url)
    assert r.status_code == 200, name
    html = r.get_data(as_text=True)
    panels = _panels(html)
    assert len(panels) == copies, f"{name}: {len(panels)} signature panels"
    for panel in panels:
        right = panel[panel.index('<div class="sig-right">'):]
        assert f'src="{sign}"' in right and f'src="{stamp}"' in right, name
        # Above the Authorised Signatory line, below "For …".
        assert (right.index('class="sig-for"') < right.index('class="sig-art"')
                < right.index('class="sig-name"')), name
        assert "mix-blend-mode:multiply" in right
        assert "width:40mm" in right and "width:28mm" in right


def test_the_tax_invoice_raised_from_a_boq_prints_them(client, marks):
    """The /invoice/from-boq route writes an ordinary invoice; it prints the marks."""
    import json

    import boq as BQ
    import demo_data as DD

    client.get("/boq/")
    bid = DD.BOQ_META["id"]
    line = next(li for li in STORE["boqs"][bid]["line_items"]
                if not li.get("is_header") and BQ._line_id(li.get("line_id")))
    before = set(STORE["invoices"])
    r = client.post(f"/invoice/from-boq/{bid}", data={
        "date": "2026-10-26", "place_of_supply": "Karnataka",
        "advance_received": "0", "leg": "supply", "tax_type": "cgst_sgst",
        "ti_json": json.dumps({"lines": [{"line_id": line["line_id"], "qty": "2"}]})})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    (tid,) = set(STORE["invoices"]) - before
    assert STORE["invoices"][tid]["boq_id"] == bid
    html = client.get(f"/invoice/view/{tid}").get_data(as_text=True)
    assert len(_panels(html)) == 3
    assert html.count(f'src="{marks[0]}"') == 3 and html.count(f'src="{marks[1]}"') == 3


def test_drafts_print_them_too(client, every_doc, marks):
    """A draft work order, a Draft purchase order and a draft RA bill."""
    STORE["work_orders"][GOLD_WO]["status"] = "draft"
    STORE["purchases"][GOLD_PO]["status"] = "Draft"
    STORE["ra_bills"]["gold-ra"]["status"] = "draft"
    for url in (f"/wo/print/{GOLD_WO}", f"/purchase/view/{GOLD_PO}", "/ra/print/gold-ra"):
        html = client.get(url).get_data(as_text=True)
        assert f'src="{marks[0]}"' in html and f'src="{marks[1]}"' in html, url
    assert "lc-draft" in client.get(f"/wo/print/{GOLD_WO}").get_data(as_text=True)


def test_on_the_challan_the_receivers_box_stays_blank(client, golden_dc, marks):
    html = client.get(f"/dc/print/{GOLD_DC}").get_data(as_text=True)
    for panel in _panels(html):
        left = panel[:panel.index('<div class="sig-right">')]
        assert "Name &amp; Signature of Receiver" in left or "Receiver" in left
        assert "<img" not in left and "data:image" not in left


def test_only_one_mark_prints_only_that_one(client, golden, pinned_identity, clean_marks):
    assert _post(client, "stamp_upload", _stamp_png()).status_code == 302
    html = client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True)
    assert 'class="sig-stamp"' in html and 'class="sig-sign"' not in html


# ══ 2. With neither set, each document is unchanged ════════════════════════

@pytest.mark.parametrize("name,url,copies", DOCS, ids=DOC_IDS)
def test_set_then_removed_prints_byte_for_byte_what_it_did(client, every_doc, clean_marks,
                                                            name, url, copies):
    before = client.get(url).get_data(as_text=True)
    assert "sig-art" not in before and "sig-stamp" not in before
    assert _post(client, "signature_upload", _signature_png()).status_code == 302
    assert _post(client, "stamp_upload", _stamp_png()).status_code == 302
    assert client.get(url).get_data(as_text=True) != before, "the marks never printed"
    assert _post(client, "signature_remove").status_code == 302
    assert _post(client, "stamp_remove").status_code == 302
    assert client.get(url).get_data(as_text=True) == before, name


def test_the_quotations_panel_is_the_literal_it_used_to_write(client, golden, clean_marks):
    """
    The quotation has no print golden, and `view_quotation()` wrote this panel
    by hand until 26 October 2026. The call that replaced it must emit exactly
    those bytes; this is the old literal, reconstructed from the template.
    """
    html = client.get(f"/quotation/view/{GOLD_Q}").get_data(as_text=True)
    comp_br, signatory = P.esc(B.COMPANY_NAME), P.esc(B.COMPANY_SIGNATORY)
    legacy = f"""

  <div class="sig-block">
    <div class="sig-kv">
      <span>GSTIN</span><span>: <b>{B.field(B.COMPANY_GSTIN, "GSTIN")}</b></span>
      <span>PAN No.</span><span>: <b>{B.field(B.COMPANY_PAN, "PAN")}</b></span>
    </div>
    <div class="sig-right">
      <div class="sig-for">For {comp_br}</div>
      <div class="sig-name">{signatory}</div>
    </div>
  </div>
  <div class="sig-note">This is a Computer Generated Document, no signature required</div>

  </td></tr></tbody>"""
    assert legacy in html


def test_the_shared_panel_emits_the_old_bytes_with_no_mark():
    saved = (B.SIGNATURE_IMAGE, B.STAMP_IMAGE)
    B.SIGNATURE_IMAGE = B.STAMP_IMAGE = ""
    try:
        assert DS._sig_art() == ""
        out = DS.sig_block("ACME", "Signer")
        assert ('<div class="sig-for">For ACME</div>\n'
                '      <div class="sig-name">Signer</div>') in out
    finally:
        B.SIGNATURE_IMAGE, B.STAMP_IMAGE = saved


# ══ 3. Owner only ══════════════════════════════════════════════════════════

def test_a_director_is_refused_on_the_post_and_nothing_is_written(client, director,
                                                                   clean_marks):
    _as(client, director)
    r = _post(client, "signature_upload", _signature_png())
    assert r.status_code == 403
    assert ST.MARK_OWNER_ONLY in r.get_data(as_text=True)
    assert "SIGNATURE_IMAGE" not in ST.load_saved() and B.SIGNATURE_IMAGE == ""


def test_a_director_cannot_remove_what_an_owner_set(client, director, clean_marks):
    assert _post(client, "stamp_upload", _stamp_png()).status_code == 302   # the Owner
    stamp = B.STAMP_IMAGE
    _as(client, director)
    assert _post(client, "stamp_remove").status_code == 403
    assert B.STAMP_IMAGE == stamp and ST.load_saved()["STAMP_IMAGE"] == stamp


def test_the_control_is_drawn_for_an_owner_and_not_for_a_director(client, director,
                                                                   clean_marks):
    owner_page = client.get("/settings/").get_data(as_text=True)
    assert 'value="signature_upload"' in owner_page and 'value="stamp_upload"' in owner_page
    _as(client, director)
    r = client.get("/settings/")
    assert r.status_code == 200, "a Director keeps the rest of the page"
    page = r.get_data(as_text=True)
    assert "_upload" not in page and "Signature &amp; Stamp" not in page
    assert 'enctype="multipart/form-data"' not in page


def test_a_directors_text_save_keeps_the_marks(client, director, clean_marks):
    """Saving the main form rebuilds the record — the marks must ride across."""
    assert _post(client, "signature_upload", _signature_png()).status_code == 302
    sign = B.SIGNATURE_IMAGE
    _as(client, director)
    form = {k: v for k, v in B.current_settings().items()}
    form["COMPANY_LEGAL"] = "M/s Renamed Fire Services"
    assert client.post("/settings/", data=form).status_code == 302
    assert ST.load_saved()["SIGNATURE_IMAGE"] == sign and B.SIGNATURE_IMAGE == sign
    assert B.COMPANY_LEGAL == "M/s Renamed Fire Services"


def test_a_role_without_settings_edit_never_reaches_the_route(client, clean_marks):
    auth.ensure_builtin_roles()
    acct = _user("mark-accountant", ["role-accountant"])
    try:
        _as(client, acct)
        assert _post(client, "signature_upload", _signature_png()).status_code == 403
        assert B.SIGNATURE_IMAGE == ""
    finally:
        STORE["users"].pop(acct["id"], None)


# ══ 4. What is stored ══════════════════════════════════════════════════════

@pytest.mark.parametrize("data,name", [
    (b"just some text, not a picture", "signature.png"),
    (PDF_BYTES, "signature.png"),
    (EXE_BYTES, "signature.png"),
], ids=["text", "pdf", "exe"])
def test_an_upload_that_is_not_an_image_is_refused(client, clean_marks, data, name):
    r = _post(client, "signature_upload", data, name)
    assert r.status_code == 200
    assert "That file is not a JPEG, PNG or WebP image." in r.get_data(as_text=True)
    assert "SIGNATURE_IMAGE" not in ST.load_saved() and B.SIGNATURE_IMAGE == ""


def test_no_file_at_all_is_refused(client, clean_marks):
    r = _post(client, "stamp_upload")
    assert "No company stamp was chosen." in r.get_data(as_text=True)
    assert B.STAMP_IMAGE == ""


def test_transparency_survives_and_metadata_does_not(client, clean_marks):
    assert _post(client, "signature_upload", _signature_png()).status_code == 302
    img = _decoded(B.SIGNATURE_IMAGE)
    assert img.format == "PNG" and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0, "the transparent ground was flattened"
    assert img.getpixel((60, 41)) == (20, 40, 160, 255), "the ink moved"
    assert "Author" not in img.info and not img.text


def test_a_jpeg_is_stored_as_png_and_shrunk(client, clean_marks):
    assert _post(client, "stamp_upload", _jpeg(), "stamp.jpg").status_code == 302
    img = _decoded(B.STAMP_IMAGE)
    assert img.format == "PNG" and max(img.size) == ST.MARK_MAX_SIDE


def test_a_tampered_record_never_reaches_a_document(client, golden, pinned_identity,
                                                     clean_marks):
    rec = STORE["settings"][ST.RECORD_ID]
    rec["SIGNATURE_IMAGE"] = 'data:image/png;base64,AAAA"><script>alert(1)</script>'
    rec["STAMP_IMAGE"] = "data:image/jpeg;base64,/9j/AAAA"
    B.apply_settings(ST.load_saved())
    assert B.SIGNATURE_IMAGE == "" and B.STAMP_IMAGE == ""
    html = client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True)
    assert "sig-art" not in html and "<script>alert(1)" not in html


def test_set_mark_is_the_one_writer_and_refuses_what_the_route_refuses(clean_marks):
    from werkzeug.datastructures import FileStorage

    bad = FileStorage(stream=io.BytesIO(EXE_BYTES), filename="s.png")
    assert ST.set_mark("signature", bad) == "That file is not a JPEG, PNG or WebP image."
    good = FileStorage(stream=io.BytesIO(_signature_png()), filename="s.png")
    assert ST.set_mark("signature", good) == ""
    assert B.SIGNATURE_IMAGE.startswith("data:image/png;base64,")
    assert ST.clear_mark("signature") == "" and B.SIGNATURE_IMAGE == ""
    assert ST.clear_mark("signature") == "There is no authorised signature to remove."


# ══ 5. What else on the sheet must survive ═════════════════════════════════

@pytest.mark.parametrize("url,labels", [
    (f"/dc/print/{GOLD_DC}", DS.COPIES_DC),
    (f"/invoice/view/{GOLD_TI}", DS.COPIES_TAX_INVOICE),
    ("/ra/print/gold-ra", DS.COPIES_TAX_INVOICE),
], ids=["delivery challan", "tax invoice", "RA tax invoice"])
@pytest.mark.parametrize("with_marks", [False, True], ids=["unset", "set"])
def test_the_copy_labels_are_still_printed(client, every_doc, clean_marks, url, labels,
                                           with_marks):
    if with_marks:
        _post(client, "signature_upload", _signature_png())
        _post(client, "stamp_upload", _stamp_png())
    html = client.get(url).get_data(as_text=True)
    for label in labels:
        assert f'<span class="copy-lbl">{label}</span>' in html, (url, label)


def test_a_cancelled_tax_invoice_keeps_its_overprint_on_top(client, golden, marks):
    STORE["invoices"][GOLD_TI]["status"] = "cancelled"
    html = client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True)
    assert html.count('<div class="lc-mark lc-cancelled">CANCELLED</div>') == 3
    assert html.count('class="sig-stamp"') == 3
    # The watermark is stacked above everything else on the sheet; the stamp
    # takes no z-index of its own, so it can never come up through it.
    assert "z-index:2" in html[html.index(".lc-mark"):html.index(".lc-mark") + 400]
    art = html[html.index('class="sig-art"'):html.index('class="sig-name"')]
    assert "z-index" not in art


# ══ 6. A SIGNED sheet stops saying it is unsigned ══════════════════════════
#
# 29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, A4 — an
# INTENDED print change, and it reverses the fifty-third block's own fourth
# judgement call by name: *"'This is a Computer Generated Document, no
# signature required' still prints under the documents that carried it"*,
# which put a sentence saying the sheet is unsigned directly under a signature
# and a company stamp.

NOTE = '<div class="sig-note">This is a Computer Generated Document, no signature required</div>'


@pytest.mark.parametrize("name,url,copies", DOCS, ids=DOC_IDS)
def test_the_computer_generated_line_is_gone_once_a_mark_is_set(
        client, every_doc, marks, name, url, copies):
    html = client.get(url).get_data(as_text=True)
    assert NOTE not in html, f"{name} still says it needs no signature"
    assert 'class="sig-note"' not in html, name
    # And the marks really are on it, so this is not passing on a blank page.
    assert html.count('class="sig-art"') == copies, name


# ⚠ **Only SIX of the nine documents ever carried the line**, and the set is
#   derived from the call sites rather than listed, so a document that starts
#   or stops passing `computer_generated=True` moves this table with it. The
#   tax invoice, the RA bill, the challan and the joint measurement sheet
#   never passed it and therefore have nothing to lose here.
def _modules_that_ask_for_the_line() -> set:
    import ast
    import pathlib as _pl
    out = set()
    for f in _pl.Path(DS.__file__).parent.glob("*.py"):
        src = f.read_text(encoding="utf8")
        if "computer_generated=True" in src and f.stem != "docsheet":
            out.add(f.stem)
    return out


CARRIES_THE_LINE = {"proforma", "quotation", "purchase", "po_draft",
                    "workorder", "merged_ra"}
WITH_LINE = [d for d in DOCS if d[0] in (
    "proforma", "quotation", "purchase order", "draft PO", "work order",
    "merged RA")]
WITH_LINE_IDS = [d[0] for d in WITH_LINE]


def test_the_set_of_documents_that_carry_the_line_is_the_one_under_test():
    """
    Derived from the call sites, so a seventh document that starts printing
    the line fails here until it is added to the table above and to the two
    parametrised tests that read it.
    """
    assert _modules_that_ask_for_the_line() == CARRIES_THE_LINE


@pytest.mark.parametrize("name,url,copies", WITH_LINE, ids=WITH_LINE_IDS)
def test_the_line_is_still_there_with_neither_mark_set(
        client, every_doc, pinned_identity, clean_marks, name, url, copies):
    """
    ⚠ The other half, and the one that keeps every pinned golden still: the
    goldens are captured against a store with no marks, so the line must come
    back byte-for-byte when they are removed.
    """
    html = client.get(url).get_data(as_text=True)
    assert html.count(NOTE) == copies, name
    assert 'class="sig-art"' not in html, name


@pytest.mark.parametrize("name,url,copies", DOCS, ids=DOC_IDS)
def test_a_document_that_never_carried_the_line_is_unaffected(
        client, every_doc, pinned_identity, clean_marks, name, url, copies):
    """
    The tax invoice, the RA bill, the challan — none of them ever printed the
    line, so A4 must not have added one to any of them in either state.
    """
    if name in WITH_LINE_IDS:
        pytest.skip("this document does carry the line")
    assert NOTE not in client.get(url).get_data(as_text=True), name


def test_removing_the_marks_brings_the_line_back(client, every_doc, marks):
    """
    The whole point of leaving `computer_generated` at every call site: it
    still says *"this document type would otherwise print the line"*, so the
    line returns the moment an Owner clears the marks at `/settings`.
    """
    # ⚠ The merged RA, not the tax invoice: the ordinary TI has never passed
    #   `computer_generated=True` and has no line to bring back.
    url = f"/merged/print/{GOLD_MERGED}"
    assert NOTE not in client.get(url).get_data(as_text=True)
    assert _post(client, "signature_remove").status_code == 302
    assert NOTE not in client.get(url).get_data(as_text=True), (
        "the stamp alone is still a mark")
    assert _post(client, "stamp_remove").status_code == 302
    assert client.get(url).get_data(as_text=True).count(NOTE) == 3


def test_one_mark_alone_is_enough_to_hide_it(client, every_doc, pinned_identity,
                                             clean_marks):
    url = f"/proforma/view/{GOLD_PI}"
    assert NOTE in client.get(url).get_data(as_text=True)
    assert _post(client, "stamp_upload", _stamp_png()).status_code == 302
    html = client.get(url).get_data(as_text=True)
    assert NOTE not in html and 'class="sig-art"' in html


def test_the_panel_itself_decides_and_not_the_caller():
    """
    ⚠ `_sig_art()` is the one thing that knows whether this sheet is signed,
    and the note reads the SAME value — so a document cannot print a mark and
    the line at once however it is called. Asserted on the function rather
    than through a page, because that is where the coupling lives.
    """
    saved = (B.SIGNATURE_IMAGE, B.STAMP_IMAGE)
    try:
        B.SIGNATURE_IMAGE = B.STAMP_IMAGE = ""
        assert DS._sig_art() == ""
        assert NOTE in DS.sig_block("ACME", "Signer", computer_generated=True)
        B.SIGNATURE_IMAGE = "data:image/png;base64,iVBORw0KGgo="
        out = DS.sig_block("ACME", "Signer", computer_generated=True)
        assert DS._sig_art() != ""
        assert NOTE not in out and 'class="sig-art"' in out
        # And a document that never asked for the line never gets one either.
        assert 'class="sig-note"' not in DS.sig_block("ACME", "Signer")
    finally:
        B.SIGNATURE_IMAGE, B.STAMP_IMAGE = saved


def test_the_joint_measurement_sheet_keeps_its_two_party_signature_block(
        client, golden_ms, marks):
    """
    ⚠ **A4's brief asked to "verify the joint measurement sheet keeps sign +
    stamp", and the premise is WRONG on this code — MEASURED, not assumed.**

    The **joint** sheet does not draw `docsheet.sig_block()` at all. It has
    its own two-party `.jm-sign` block, and that is the twenty-third §0
    block's whole point: the document is called *joint* because it is
    **countersigned by the main contractor's site engineer**, in ink, in the
    field. So it never carried the preloaded marks and never carried the
    "Computer Generated Document" line either, and A4 changes nothing about
    it.

    What A4 had to be checked for here is the opposite claim: that it did not
    *break* the block. It does not.

    The fifty-third block's third judgement call — *"the merged RA and the
    measurement sheet too, which were not named"* — means the **flat**
    (non-joint) measurement sheet, which does draw `sig_block()` and does
    carry the marks. That is the test below.
    """
    import pathlib as _pl
    from test_print_golden import GOLD_MS
    import measurement as MS
    assert MS.is_joint(STORE["measurements"][GOLD_MS])
    src = _pl.Path(MS.__file__).read_text(encoding="utf8")
    assert "computer_generated=True" not in src, (
        "no measurement sheet has ever printed the line and none must start")

    html = client.get(f"/measurement/print/{GOLD_MS}").get_data(as_text=True)
    assert 'class="jm-sign"' in html, "the joint sheet lost its sign-off block"
    assert 'class="sig-block"' not in html, (
        "the joint sheet must not start drawing the shared panel")
    assert 'class="sig-art"' not in html
    assert NOTE not in html


def test_the_FLAT_measurement_sheet_carries_the_marks_and_never_the_line(
        client, golden_ms, marks):
    """
    The sheet the fifty-third block's third judgement call actually means.
    Built from the joint golden's record with its grid model flipped, so the
    only difference under test is which document half renders.
    """
    from test_print_golden import GOLD_MS
    import measurement as MS
    flat = dict(STORE["measurements"][GOLD_MS])
    flat["id"] = "sign-flat-ms"
    flat["grid_model"] = "flat"
    STORE["measurements"]["sign-flat-ms"] = flat
    assert not MS.is_joint(flat)
    html = client.get("/measurement/print/sign-flat-ms").get_data(as_text=True)
    assert 'class="sig-block"' in html
    assert 'class="sig-art"' in html, "the flat sheet lost its signature"
    assert 'class="sig-sign"' in html and 'class="sig-stamp"' in html
    assert NOTE not in html, "it has never carried the line"
