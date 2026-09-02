"""
CC-2 **B8** — file attachments on a charge and on a receipt.

Built 2 September 2026 under the first override block of that date.

⚠ **Every guard in this file is proved NON-VACUOUS by a control.** A test that
asserts "the bad case is refused" and never checks that the good case is
accepted will go on passing when the feature stops working entirely — refusing
everything satisfies it. So each refusal here is paired with the acceptance it
must not also be refusing:

| guard | the refusal | its control |
|---|---|---|
| 5 MB cap | one byte over is refused | one byte under is saved |
| type gate | a renamed `.exe` labelled `image/png` | the same bytes as a real PNG |
| compulsory on a charge | no file, no charge | with a file, a charge |
| optional on a receipt | *(none — that is the point)* | no file, still a receipt |
| cascade | the file is gone from disk | it was on disk a moment before |
| B7 on download | unapproved refuses | approved downloads |
| B7 permits viewing | — | unapproved still views inline |

⚠ **The files never touch the developer's real store.** `conftest._attachment_store`
is autouse and points `ATTACHMENT_DIR` at a per-test temporary directory. The
cascade tests below delete files, and without that fixture they would be
deleting real scanned supplier bills.
"""

import io

import pytest

import approval
import attachment
from store import STORE

from conftest import (EXE_BYTES, JPEG_BYTES, PDF_BYTES, PNG_BYTES,
                      charge_form, ensure_test_user, upload)


# =============================================================================
# HELPERS
# =============================================================================

def _only_new(before: dict, after: dict) -> dict:
    added = [v for k, v in after.items() if k not in before]
    assert len(added) == 1, f"expected exactly one new record, got {len(added)}"
    return added[0]


def _make_charge(client, **over):
    before = dict(STORE.setdefault("charges", {}))
    r = client.post("/charge/new", data=charge_form(**over),
                    content_type="multipart/form-data", follow_redirects=False)
    return r, before


def _charge_with_file(client):
    """One saved charge and its one attachment."""
    r, before = _make_charge(client)
    assert r.status_code in (302, 303), r.status_code
    charge = _only_new(before, STORE["charges"])
    files = attachment.for_parent("charge", charge["id"])
    assert len(files) == 1
    return charge, files[0]


def _seed_bill(client):
    """A BOQ and an issued RA bill, so a receipt has something to pay."""
    import ra as RA
    client.get("/boq/")
    boq_id = next(iter(STORE["boqs"]))
    from conftest import chain_ready
    chain_ready(boq_id)
    bill_id = "att-bill-1"
    STORE.setdefault("ra_bills", {})[bill_id] = {
        "id": bill_id, "ref": "SF/RA/26-27/9001", "fy": "26-27",
        "date": "2026-08-20", "boq_id": boq_id, "ra_no": 1, "leg": "supply",
        "status": "issued", "claims": [], "claim_subtotal": 100000.0,
        "deductions": [], "deduction_total": 0.0, "net_payable": 100000.0,
        "grand_total": 100000.0, "project_name": "Test",
    }
    return bill_id


# =============================================================================
# 1. THE TYPE GATE — content, never the name and never the claimed type
# =============================================================================

@pytest.mark.parametrize("data,mime", [
    (PNG_BYTES, "image/png"),
    (JPEG_BYTES, "image/jpeg"),
    (PDF_BYTES, "application/pdf"),
])
def test_the_three_types_cc2_names_are_accepted(data, mime):
    """The control for every refusal below: these three really do get through."""
    assert attachment.sniff(data) == mime


def test_a_renamed_executable_is_refused_even_labelled_image_png(client):
    """
    ⚠ **The mutation proof for the type gate.** The file is named `.png`, the
    browser says `image/png`, and only the bytes disagree — which is exactly the
    upload CC-2's *"validate by content"* requirement exists for.

    Asserted at BOTH levels, because they can fail independently: `sniff()` must
    not recognise it, and the charge form must not save a charge around it.
    """
    assert attachment.sniff(EXE_BYTES) == "", (
        "sniff() recognised a Windows executable as one of the three allowed "
        "types. Every other guard in this file is downstream of this one.")

    before = dict(STORE.setdefault("charges", {}))
    r = client.post("/charge/new",
                    data=charge_form(attachment=upload(EXE_BYTES, "invoice.png",
                                                       "image/png")),
                    content_type="multipart/form-data", follow_redirects=False)

    assert r.status_code == 200, (
        "a renamed executable was accepted — the form redirected instead of "
        "re-rendering with an error")
    assert dict(STORE["charges"]) == before, (
        "a charge was created around a file that is not a JPEG, PNG or PDF")
    assert not attachment.for_parent("charge", "any"), "no attachment may exist"


def test_the_extension_alone_does_not_admit_a_file(client):
    """
    The other half of the same rule: a REAL png named `.exe` is fine.

    Without this the type gate could be an extension check that happens to
    reject the executable, and the test above would not tell the difference.
    """
    r, before = _make_charge(client,
                             attachment=upload(PNG_BYTES, "scan.exe",
                                               "application/octet-stream"))
    assert r.status_code in (302, 303), (
        "a genuine PNG was refused because of its name — the gate is reading "
        "the extension, not the content")
    charge = _only_new(before, STORE["charges"])
    files = attachment.for_parent("charge", charge["id"])
    assert len(files) == 1
    assert files[0]["mime_type"] == "image/png"
    assert files[0]["stored_path"].endswith(".png"), (
        "the file was stored under the extension it was UPLOADED with. The name "
        "on disk must come from the sniffed type or it can disagree with the "
        "bytes in it.")


# =============================================================================
# 2. THE SIZE CAP — refused before anything reaches the store
# =============================================================================

def test_a_file_one_byte_over_the_cap_is_refused(client):
    """⚠ The mutation proof for the cap, at the boundary rather than at 50 MB."""
    over = PNG_BYTES + bytes(attachment.MAX_BYTES - len(PNG_BYTES) + 1)
    assert len(over) == attachment.MAX_BYTES + 1

    ok, why, _mime, size = attachment.validate(upload(over)[0] and
                                               _fs(over, "big.png"))
    assert not ok, f"a file of {size} bytes passed a {attachment.MAX_BYTES} cap"
    assert "limit" in why.lower() or "MB" in why

    before = dict(STORE.setdefault("charges", {}))
    r = client.post("/charge/new",
                    data=charge_form(attachment=upload(over, "big.png")),
                    content_type="multipart/form-data", follow_redirects=False)
    assert r.status_code == 200
    assert dict(STORE["charges"]) == before, "an over-cap upload created a charge"

    # ⚠ NOTHING reached the store — not a stray file, not a metadata row.
    assert not list(attachment.root().rglob("*.png")), (
        "an over-cap file was written to the attachment store before being "
        "refused. The cap must be checked before the write, not after.")
    assert not STORE.get("attachments"), "an over-cap upload left a metadata row"


def test_a_file_one_byte_under_the_cap_is_accepted(client):
    """
    ⚠ **The control that makes the cap test mean something.** Without it, a
    `validate()` that refused everything would pass the test above.
    """
    under = PNG_BYTES + bytes(attachment.MAX_BYTES - len(PNG_BYTES) - 1)
    assert len(under) == attachment.MAX_BYTES - 1

    r, before = _make_charge(client, attachment=upload(under, "big.png"))
    assert r.status_code in (302, 303), "a legal file just under the cap was refused"
    charge = _only_new(before, STORE["charges"])
    files = attachment.for_parent("charge", charge["id"])
    assert len(files) == 1
    assert files[0]["size_bytes"] == attachment.MAX_BYTES - 1


def test_an_empty_file_is_refused():
    ok, why, _m, _s = attachment.validate(_fs(b"", "empty.png"))
    assert not ok and "empty" in why.lower()


def _fs(data: bytes, name: str = "f.png", ctype: str = "image/png"):
    """A Werkzeug FileStorage, for calling `validate()` without a request."""
    from werkzeug.datastructures import FileStorage

    return FileStorage(stream=io.BytesIO(data), filename=name, content_type=ctype)


# =============================================================================
# 3. COMPULSORY ON A CHARGE, OPTIONAL ON A RECEIPT — CC-2's asymmetry
# =============================================================================

def test_a_charge_cannot_be_saved_without_an_attachment(client):
    """
    CC-2 B8: *"Charges: attachment is compulsory (client requirement)"*, and the
    19 August list: *"Compulsory document ATTACHMENT in the charge section"*.
    """
    before = dict(STORE.setdefault("charges", {}))
    form = charge_form()
    form.pop("attachment")
    r = client.post("/charge/new", data=form,
                    content_type="multipart/form-data", follow_redirects=False)
    assert r.status_code == 200, "a charge with no attachment was saved"
    assert dict(STORE["charges"]) == before


def test_a_charge_with_an_attachment_is_saved(client):
    """The control: the requirement must not be refusing every charge."""
    charge, att = _charge_with_file(client)
    assert att["parent_type"] == "charge"
    assert att["parent_id"] == charge["id"]
    assert attachment.abs_path(att).is_file()


def test_a_receipt_saves_with_no_attachment(client):
    """
    ⚠ **CC-2's stated reason, and it must not be tidied into consistency:**
    *"bank transfers often have no separate slip, and compulsory would block
    honest entries."* A pass that makes this symmetrical with the charge has
    broken the specification, not fixed an inconsistency.
    """
    bill_id = _seed_bill(client)
    before = dict(STORE.setdefault("receipts", {}))
    r = client.post(f"/receipt/new?ra={bill_id}", data={
        "date": "2026-08-21", "amount": "50000", "mode": "neft",
        "instrument_ref": "UTR-NO-SLIP", "instrument_date": "2026-08-21",
        "notes": "", "write_off": "",
    }, content_type="multipart/form-data", follow_redirects=False)
    assert r.status_code in (302, 303), r.status_code
    rec = _only_new(before, STORE["receipts"])
    assert attachment.for_parent("receipt", rec["id"]) == []


def test_a_receipt_accepts_an_attachment_when_there_is_one(client):
    bill_id = _seed_bill(client)
    before = dict(STORE.setdefault("receipts", {}))
    r = client.post(f"/receipt/new?ra={bill_id}", data={
        "date": "2026-08-21", "amount": "50000", "mode": "cheque",
        "instrument_ref": "112233", "instrument_date": "2026-08-21",
        "notes": "", "write_off": "",
        "attachment": upload(PDF_BYTES, "bank-slip.pdf", "application/pdf"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert r.status_code in (302, 303), r.status_code
    rec = _only_new(before, STORE["receipts"])
    files = attachment.for_parent("receipt", rec["id"])
    assert len(files) == 1
    assert files[0]["mime_type"] == "application/pdf"


def test_the_requirement_is_data_and_not_a_branch():
    """
    The asymmetry lives in `PARENTS`, so it is visible in one place.

    If a later pass makes a receipt's attachment compulsory, this fails and
    points at the override block that would be needed.
    """
    assert attachment.PARENTS["charge"]["required"] is True
    assert attachment.PARENTS["receipt"]["required"] is False


def test_the_receipt_attachment_is_not_called_a_receipt():
    """
    ⚠ CC-2's vocabulary warning: *"receipt" already means the payment record.
    What is attached to it is a proof of payment. Do not overload the word.*
    """
    noun = attachment.PARENTS["receipt"]["noun"]
    assert "receipt" not in noun.lower(), (
        f"the receipt's attachment is called {noun!r}, which overloads the word "
        f"CC-2 explicitly warns against overloading")
    assert noun == "proof of payment"


# =============================================================================
# 4. THE CASCADE — no orphans, on disk or in the store
# =============================================================================

def test_deleting_a_charge_deletes_its_file_from_disk(client):
    """
    ⚠ **The proof CC-2's *"No orphans"* asks for, and it reads the DISK.**

    Asserting the metadata row is gone would pass against an implementation that
    left a 5 MB file behind forever, which is the failure this is about.
    """
    charge, att = _charge_with_file(client)
    path = attachment.abs_path(att)
    assert path.is_file(), "precondition: the file is on disk before the delete"

    r = client.post(f"/charge/delete/{charge['id']}", follow_redirects=False)
    assert r.status_code in (302, 303), r.status_code

    assert not path.exists(), (
        f"{path.name} is still on disk after its charge was deleted — B8's "
        f"cascade left an orphan file")
    assert att["id"] not in STORE.get("attachments", {}), (
        "the metadata row outlived the charge it belonged to")
    assert charge["id"] not in STORE["charges"]


def test_deleting_a_receipt_deletes_its_file_from_disk(client):
    bill_id = _seed_bill(client)
    before = dict(STORE.setdefault("receipts", {}))
    client.post(f"/receipt/new?ra={bill_id}", data={
        "date": "2026-08-21", "amount": "5000", "mode": "cheque",
        "instrument_ref": "9", "instrument_date": "2026-08-21",
        "notes": "", "write_off": "",
        "attachment": upload(JPEG_BYTES, "slip.jpg", "image/jpeg"),
    }, content_type="multipart/form-data", follow_redirects=False)
    rec = _only_new(before, STORE["receipts"])
    att = attachment.for_parent("receipt", rec["id"])[0]
    path = attachment.abs_path(att)
    assert path.is_file()

    client.post(f"/receipt/delete/{rec['id']}", follow_redirects=False)

    assert not path.exists(), "a deleted receipt left its proof of payment on disk"
    assert att["id"] not in STORE.get("attachments", {})


def test_the_cascade_takes_every_file_not_only_the_first(client):
    """One parent accumulates several files. All of them go."""
    charge, first = _charge_with_file(client)
    second, _e = attachment.save(_fs(PDF_BYTES, "second.pdf", "application/pdf"),
                                 "charge", charge["id"])
    assert second is not None
    paths = [attachment.abs_path(first), attachment.abs_path(second)]
    assert all(p.is_file() for p in paths)

    client.post(f"/charge/delete/{charge['id']}", follow_redirects=False)

    assert not any(p.exists() for p in paths), (
        "the cascade removed only some of the files on the deleted charge")
    assert not STORE.get("attachments"), "metadata rows survived the cascade"


def test_the_cascade_leaves_another_records_files_alone(client):
    """
    ⚠ **The control.** A cascade that deleted the whole store would satisfy
    every test above it.
    """
    keep_charge, keep_att = _charge_with_file(client)
    doomed_charge, doomed_att = _charge_with_file(client)
    assert keep_charge["id"] != doomed_charge["id"]

    client.post(f"/charge/delete/{doomed_charge['id']}", follow_redirects=False)

    assert not attachment.abs_path(doomed_att).exists()
    assert attachment.abs_path(keep_att).is_file(), (
        "deleting one charge destroyed another charge's supporting document")
    assert keep_att["id"] in STORE["attachments"]


def test_no_orphan_files_are_left_behind(client):
    """`orphan_files()` is how the tolerated failure mode stays findable."""
    charge, _att = _charge_with_file(client)
    assert attachment.orphan_files() == []
    client.post(f"/charge/delete/{charge['id']}", follow_redirects=False)
    assert attachment.orphan_files() == [], (
        "a file with no metadata row was left under the attachment store")


def test_the_last_attachment_cannot_be_removed_from_a_charge(client):
    """
    The compulsory rule enforced at the SECOND door.

    A requirement checked only at creation is a speed bump: save the charge with
    a file, then delete the file.
    """
    charge, att = _charge_with_file(client)
    r = client.post(f"/attachment/charge/delete/{att['id']}", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert attachment.abs_path(att).is_file(), (
        "the only supporting document on a charge was removed, leaving a charge "
        "CC-2 says may not exist")
    assert att["id"] in STORE["attachments"]


def test_a_second_attachment_can_be_removed(client):
    """The control: the rule guards the last file, not every file."""
    charge, first = _charge_with_file(client)
    second, _e = attachment.save(_fs(PNG_BYTES, "extra.png"), "charge", charge["id"])
    path = attachment.abs_path(second)
    assert path.is_file()

    r = client.post(f"/attachment/charge/delete/{second['id']}", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert not path.exists(), "a removable second attachment was not removed"
    assert attachment.abs_path(first).is_file()


# =============================================================================
# 5. B7 ON AN ATTACHMENT — ours, not CC-2's, and it goes through B7's function
# =============================================================================

def test_an_unapproved_charges_attachment_does_not_download(client):
    """
    ⚠ **UNSPECCED-BUT-CONSISTENT SCOPE**, recorded in PROGRESS.md §4c.

    B7 gates the document; leaving its supporting file downloadable would be a
    hole big enough to drive the document through — photograph the attachment
    and you have the figures.
    """
    charge, att = _charge_with_file(client)
    assert not approval.is_approved(charge), "precondition: not approved"

    r = client.get(f"/attachment/charge/download/{att['id']}", follow_redirects=False)
    assert r.status_code in (302, 303), (
        "an unapproved charge's attachment downloaded. B7 is not being applied "
        "to the supporting file.")
    assert "/charge" in r.headers.get("Location", "")


def test_an_approved_charges_attachment_downloads(client):
    """⚠ **The control**, and the one that proves the gate is B7's and not a wall."""
    charge, att = _charge_with_file(client)
    charge["approval_status"] = approval.APPROVED

    r = client.get(f"/attachment/charge/download/{att['id']}")
    assert r.status_code == 200, (
        "an approved charge's attachment was refused — the gate is refusing "
        "everything, not applying B7")
    assert r.data.startswith(bytes.fromhex("89504e47")), "the bytes came back wrong"
    assert "attachment" in r.headers.get("Content-Disposition", "")


def test_an_unapproved_charges_attachment_still_VIEWS(client):
    """
    ⚠ **B7's permitting half, and it is as load-bearing as the refusing half.**
    CC-2: *"an unapproved document may be viewed, but not printed or
    downloaded."* A gate that also blocked viewing would be over-applying B7.
    """
    charge, att = _charge_with_file(client)
    assert not approval.is_approved(charge)

    r = client.get(f"/attachment/charge/view/{att['id']}")
    assert r.status_code == 200, (
        "an unapproved charge's attachment could not be viewed on screen, which "
        "B7 explicitly permits")
    assert "inline" in r.headers.get("Content-Disposition", "").lower()


def test_a_receipts_attachment_downloads_because_a_receipt_has_no_ladder(client):
    """
    Not an exemption written here — a fact about `approval.DOCUMENTS`.

    If a receipt ever joins the ladder, this test changes and `attachment.py`
    does not, which is the property the module docstring claims.
    """
    assert "receipt" not in approval.DOCUMENTS
    bill_id = _seed_bill(client)
    before = dict(STORE.setdefault("receipts", {}))
    client.post(f"/receipt/new?ra={bill_id}", data={
        "date": "2026-08-21", "amount": "5000", "mode": "cheque",
        "instrument_ref": "9", "instrument_date": "2026-08-21",
        "notes": "", "write_off": "",
        "attachment": upload(PDF_BYTES, "slip.pdf", "application/pdf"),
    }, content_type="multipart/form-data", follow_redirects=False)
    rec = _only_new(before, STORE["receipts"])
    att = attachment.for_parent("receipt", rec["id"])[0]

    r = client.get(f"/attachment/receipt/download/{att['id']}")
    assert r.status_code == 200


def test_the_download_gate_calls_b7_rather_than_restating_it():
    """
    ⚠ `may_download()` must reach `approval.can_print()`.

    A second copy of B7's rule would have to be kept in step with the two named
    print exemptions, the grandfather clause and the rejected case — and would
    not be. Asserted against the source, the way
    `test_approval.py::test_every_approval_endpoint_reaches_the_guard` does.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(attachment.may_download))
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "approval.can_print" in calls, (
        "may_download() no longer calls approval.can_print(). B7's rule has been "
        "restated here instead of consumed, and the copies will drift.")


# =============================================================================
# 6. THE ROUTES ARE PER-PARENT, AND THE TYPE IN THE URL IS CHECKED
# =============================================================================

def test_every_attachment_endpoint_is_classified():
    """
    B5's default-deny, applied to the routes this module mints.

    `test_access_control.py` sweeps the whole url_map; this names the six so a
    parent type added to `PARENTS` without registry rows fails HERE, pointing at
    the reason, rather than in a generic sweep.
    """
    import auth

    for key in attachment.PARENTS:
        for verb in ("view", "download", "delete"):
            endpoint = f"attachment.{verb}_{key}"
            assert endpoint in auth.ROUTE_PERMISSIONS, (
                f"{endpoint} is not classified in auth.ROUTE_PERMISSIONS, so it "
                f"is refused to everybody including the Owner")


def test_the_endpoints_carry_the_parents_own_permission():
    """
    ⚠ **No new permission is minted for an attachment**, and the read/write
    split is honoured: `delete_*` answers POST and destroys, so it carries the
    parent's DELETE permission rather than its view one (§7 gap 24b).
    """
    import auth

    assert auth.ROUTE_PERMISSIONS["attachment.view_charge"] == "charge.view"
    assert auth.ROUTE_PERMISSIONS["attachment.download_charge"] == "charge.view"
    assert auth.ROUTE_PERMISSIONS["attachment.delete_charge"] == "charge.delete"
    assert auth.ROUTE_PERMISSIONS["attachment.view_receipt"] == "receipt.view"
    assert auth.ROUTE_PERMISSIONS["attachment.download_receipt"] == "receipt.view"
    assert auth.ROUTE_PERMISSIONS["attachment.delete_receipt"] == "receipt.delete"

    minted = [p for p in auth.PERMISSIONS if p.startswith("attachment.")]
    assert minted == [], (
        f"B8 minted {minted}. Whoever may view a charge may view what it is "
        f"evidenced by; a separate family is one more thing to grant and to "
        f"leave ungranted (ABOUT.md §2g).")


def test_the_parent_type_in_the_url_is_checked_against_the_record(client):
    """
    ⚠ **Without this the per-parent split would be decoration.** A charge's
    attachment reached through the `receipt` URL would be served under
    `receipt.view` — the weaker permission for the stronger record.
    """
    _charge, att = _charge_with_file(client)
    assert att["parent_type"] == "charge"

    r = client.get(f"/attachment/receipt/view/{att['id']}")

    # ⚠ **`abort(404)` arrives as a 302 here, and that is the APPLICATION's
    #   shape rather than anything this module does**: `app.page_not_found()`
    #   redirects every 404 to the dashboard. So the assertion is on the
    #   property that matters — the bytes were NOT served — rather than on a
    #   status code this app does not use.
    assert r.status_code != 200, (
        "a charge's attachment was served through the receipt endpoint, which "
        "carries receipt.view rather than charge.view")
    assert not r.get_data().startswith(bytes.fromhex("89504e47")), (
        "the PNG came back through the wrong parent's endpoint")


def test_an_unknown_attachment_serves_nothing(client):
    """
    ⚠ Named for what it asserts rather than for a status code. `abort(404)` is
    remapped to a 302 by `app.page_not_found()` for every route in this
    application, so "is a 404" would be asserting the opposite of the truth.
    """
    for url in ("/attachment/charge/view/nope",
                "/attachment/charge/download/nope",
                "/attachment/receipt/view/nope"):
        r = client.get(url)
        assert r.status_code != 200, f"{url} served something"


def test_delete_answers_post_only(client):
    """ABOUT.md §7.9f — a link that destroys is a link a prefetch fires."""
    _charge, att = _charge_with_file(client)
    r = client.get(f"/attachment/charge/delete/{att['id']}")
    assert r.status_code == 405, (
        "GET on the attachment delete route was accepted. A crawler, a prefetch "
        "or a back button will eventually fire it.")
    assert attachment.abs_path(att).is_file(), "the GET destroyed the file anyway"


# =============================================================================
# 7. THE STORED SHAPE — what B8's requirement 2 asks the record to carry
# =============================================================================

def test_the_record_carries_everything_b8_asks_for(client):
    _charge, att = _charge_with_file(client)
    for field in ("filename", "stored_path", "size_bytes", "mime_type",
                  "parent_type", "parent_id", "uploaded_by", "uploaded_at"):
        assert field in att, f"the attachment record has no {field!r}"
    assert att["uploaded_by"] == ensure_test_user()["id"]
    assert att["size_bytes"] == len(PNG_BYTES)


def test_the_stored_path_is_relative_and_not_absolute(client):
    """
    ⚠ An absolute path publishes the disk layout of the machine the app runs on
    into a database that gets dumped and handed around.
    """
    import os

    _charge, att = _charge_with_file(client)
    stored = att["stored_path"]
    assert not os.path.isabs(stored), f"{stored!r} is an absolute path"
    assert ":" not in stored, f"{stored!r} carries a Windows drive letter"
    assert str(attachment.root()) not in stored
    # ...and it still resolves.
    assert attachment.abs_path(att).is_file()


def test_the_bytes_are_not_in_the_store(client):
    """
    ⚠ **The finding of 30 August 2026, pinned so it cannot be undone quietly.**

    `db._blob()` writes bytes through `json.dumps(default=str)` and reloads them
    as a corrupted STRING with no exception raised. A later pass that "simplifies"
    by putting the payload on the record re-opens exactly that, silently.
    """
    import json

    _charge, att = _charge_with_file(client)
    blob = json.dumps(STORE["attachments"], sort_keys=True, default=str)
    assert "PNG" not in blob and "\\x89" not in blob, (
        "the attachment payload is inside STORE. It must be a file on disk — "
        "db.py cannot carry bytes and does not say so when it fails.")
    assert att["stored_path"] in blob, "the path is what the record should carry"


def test_a_stored_path_cannot_escape_the_root(client):
    """
    Defence in depth. Nothing user-supplied reaches `stored_path` — but the
    value arrives here from the DATABASE, which is a different trust boundary
    from the one it was written across.
    """
    evil = {"stored_path": "../../../app.py"}
    resolved = attachment.abs_path(evil)
    assert not resolved.exists() or resolved.name == "__outside_root__", (
        f"a stored path escaped the attachment root and resolved to {resolved}")


def test_the_filename_is_kept_but_never_builds_a_path(client):
    """A file called `../../app.py` is a display string, not a write target."""
    r, before = _make_charge(client,
                             attachment=upload(PNG_BYTES, "../../app.py", "image/png"))
    assert r.status_code in (302, 303)
    charge = _only_new(before, STORE["charges"])
    att = attachment.for_parent("charge", charge["id"])[0]
    assert att["filename"] == "../../app.py", "the operator's own name was not kept"
    assert ".." not in att["stored_path"]
    assert attachment.abs_path(att).is_file()
    assert attachment.abs_path(att).parent == attachment.root() / "charge"


# =============================================================================
# 8. THE RESPONSE HEADERS — serving user-uploaded bytes from our own origin
# =============================================================================

def test_the_served_file_carries_the_sniffed_type_and_nosniff(client):
    charge, att = _charge_with_file(client)
    r = client.get(f"/attachment/charge/view/{att['id']}")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("image/png")
    assert r.headers["X-Content-Type-Options"] == "nosniff", (
        "without nosniff a browser may disregard our Content-Type and guess "
        "from the bytes, re-opening the hole the magic-byte check closed")
    assert "sandbox" in r.headers.get("Content-Security-Policy", ""), (
        "a PDF is an active document format and this app serves it from its own "
        "origin, where it would run with the operator's session")


def test_the_upload_form_declares_multipart(client):
    """
    ⚠ Without `enctype`, the browser posts the FILENAME as an ordinary string,
    `request.files` is empty, and a compulsory attachment looks exactly like an
    operator who attached nothing.
    """
    body = client.get("/charge/new").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in body, "the charge form is not multipart"
    assert 'type="file"' in body and 'name="attachment"' in body
