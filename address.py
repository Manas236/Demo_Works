"""
address.py — Address Book Module
================================
Blueprint : address_bp
Mounted at : /address  (registered in app.py)

A directory of Indian-format postal addresses — offices, project sites, billing
and delivery locations, and vendors.

⚠ **THIS IS A MASTER, NOT A SCRATCHPAD (30 August 2026, fourth pass).** The
docstring here read *"deliberately self-contained: nothing else in the app reads
STORE['addresses']"* until this pass, and it had not been true for weeks. Six
collections point into this book:

    projects.site_address_id        · employees.site_address_id
    attendance.site_address_id      · purchase_orders.vendor_id
    purchases.vendor_id             · delivery_challans.consignee_id

and some of those references are still **snapshot strings** rather than ids,
because the fields were free text before the pickers arrived. So:

  * `references_of()` is the one function that answers "what points at this?",
    matching on **both** the id and the snapshot string, exactly, never fuzzily;
  * **deletion is refused** while anything does, and the refusal names them;
  * **archiving** is the escape — a delete-refusal with no archive is a trap
    rather than a guard;
  * **editing is allowed and logged**, because the live data misspells a city
    and nothing repoints a record onto a different address;
  * **`type` is the one locked field**, because it is what the pickers filter on.

`SITE_TYPES` also lives here rather than in `employee.py`, so the muster's site
picker and the project form's cannot disagree about what counts as a site.

Address model (all fields are plain strings unless noted):
    id, label, type, contact_name, company,
    line1, line2, landmark, city, state, pincode, country,
    phone, email, gstin,
    active     — bool, ABSENT MEANS TRUE (the archive flag)
    edit_log   — list, absent until a referenced address is edited

Indian postal convention is followed top-to-bottom:
    Contact / Company
    Building, plot or unit          (line1)
    Street, road or locality        (line2)
    Landmark
    City - PIN
    State, India

⚠  In-memory only — everything is lost on server restart (by design here).
"""

import re
import uuid
from datetime import datetime

from flask import Blueprint, request, redirect, url_for
from markupsafe import escape

import branding as B
from dashboard import BASE_STYLES, _nav
from product import PRODUCT_STYLES          # reuse form / table / alert styling
from store import STORE

# ── Blueprint ─────────────────────────────────────────────────────────────────
address_bp = Blueprint("address", __name__, url_prefix="/address")


# =============================================================================
# REFERENCE DATA
# =============================================================================

# Address kinds. Key is what gets stored; value is the human label.
ADDRESS_TYPES = {
    "office":   "Office",
    "site":     "Project Site",
    "billing":  "Billing",
    "shipping": "Delivery",
    "vendor":   "Vendor",
}

# ⚠ **Which address types may be a SITE, and the narrowing is OURS.** This lived
#   in `employee.py` until 30 August 2026 (fourth pass), which was the wrong
#   home the moment a second module needed it: `project.py` and `employee.py`
#   would each have carried their own tuple, and **two pickers that can disagree
#   about what counts as a site is the defect** — a project filed under a type
#   the muster does not offer cannot be reconciled with the muster's own sites.
#   It lives here, beside `ADDRESS_TYPES`, because this module owns the
#   vocabulary; `employee.SITE_TYPES` is now an alias onto this name and every
#   existing reader keeps working.
#
#   The narrowing itself is unchanged and its reasoning is `employee.py`'s:
#   people work at sites and at the office; a **vendor**'s address is somebody
#   we buy from, and offering it as a place somebody worked a shift — or as the
#   site of a project — would put work against a supplier. `billing` and
#   `shipping` are where paperwork and goods go, not where a fitter stands. One
#   tuple to widen if a real site turns out to be filed under another type.
SITE_TYPES = ("site", "office")

# ── The archive flag ────────────────────────────────────────────────────────
#
# ⚠ **`active` is absent on every record written before 30 August 2026, and
#   ABSENT MEANS ACTIVE.** Never `addr["active"]` and never
#   `addr.get("active") is True` — six live records and every seeded one carry
#   no such key, and either of those readings would archive the whole book at a
#   stroke. `is_active()` below is the only reader; use it.
#
# **Why an archive exists at all.** `delete_address()` now refuses while
# anything references the address (`references_of()`), and **a delete-refusal
# with no archive is a trap rather than a guard** — the finding
# `measurement.can_delete()` already made one register along. One address typed
# wrongly and used once would otherwise sit in every picker forever with no move
# available to anybody. An archived address leaves every picker, still resolves
# for the records that point at it, and can be un-archived.
#
# ⚠ **An address nothing references stays HARD-deletable.** That is the cleanup
#   path for a duplicate and it is not replaced by the archive.
ACTIVE_FIELD = "active"

# Where an edit history lives on the record. See `_log_edit()`.
EDIT_LOG_FIELD = "edit_log"

# States and union territories, as printed on Indian postal addresses.
INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
    # Union territories
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
]

# India Post PINs never start with 0.
_PIN_RE   = re.compile(r"^[1-9][0-9]{5}$")
# 2-digit state code + 10-char PAN + entity digit + 'Z' + checksum.
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


# =============================================================================
# DEMO SEED DATA
# =============================================================================

_A = {
    "mumbai":    "b2000001-face-4000-8000-000000000001",
    "pune":      "b2000002-face-4000-8000-000000000002",
    "ahmedabad": "b2000003-face-4000-8000-000000000003",
    # Vendors — the buy side. purchase.py raises POs on these; without at least
    # one, the vendor picker on the PO form opens empty and the module looks
    # broken on a fresh install.
    "v_pumps":   "b2000004-face-4000-8000-000000000004",
    "v_fire":    "b2000005-face-4000-8000-000000000005",
    "v_steel":   "b2000006-face-4000-8000-000000000006",
}


def ensure_demo_addresses() -> None:
    """
    Seeds six realistic Indian addresses on first call; a no-op afterwards.
    Called at the top of every route that reads the book, so the page is never
    empty on a fresh server.

    Three are customer-side (office / site / delivery) and feed the quotation's
    Bill To and Ship To pickers. Three are **vendors** and feed the purchase
    order form — the buy side has to have somebody to buy from.

    ⚠  Demo data — company names, GSTINs and phone numbers are illustrative
       only. The vendor names are invented; they are not Samruddhi's suppliers.
    """
    if STORE.get("_addr_seeded"):
        return

    _seed(
        _A["mumbai"], "Head Office — Mumbai", "office",
        contact_name="Mr. Rajesh Kulkarni",
        company="Sunteck Realty Ltd.",
        line1="Unit 12, Shreeji Industrial Estate",
        line2="Off Andheri-Kurla Road, Sakinaka",
        landmark="Near Mittal Industrial Estate",
        city="Mumbai", state="Maharashtra", pincode="400072",
        phone="+91 98200 41122", email="rajesh.k@example.co.in",
        gstin="27AAACS1234F1Z5",
    )
    _seed(
        _A["pune"], "Hinjewadi Project Site", "site",
        contact_name="Ms. Sneha Deshpande",
        company="Kohinoor Techpark Pvt. Ltd.",
        line1="Building B, 3rd Floor, Plot No. 14",
        line2="Rajiv Gandhi Infotech Park, Phase II, Hinjewadi",
        landmark="Opposite Wipro Circle",
        city="Pune", state="Maharashtra", pincode="411057",
        phone="+91 20 2293 4410", email="sneha.d@example.co.in",
        gstin="",
    )
    _seed(
        _A["ahmedabad"], "Changodar Warehouse", "shipping",
        contact_name="Mr. Nilesh Patel",
        company="Torrent Power Ltd.",
        line1="Godown No. 7, Survey No. 218/2",
        line2="Sarkhej–Bavla Highway, Changodar",
        landmark="Near Gokul Dairy",
        city="Ahmedabad", state="Gujarat", pincode="382213",
        phone="+91 79 2664 3010", email="stores.ahd@example.co.in",
        gstin="24AAACT1234R1ZK",
    )

    # ── Vendors ───────────────────────────────────────────────────────────
    _seed(
        _A["v_pumps"], "Vishwakarma Pumps & Motors", "vendor",
        contact_name="Mr. S. Ramanathan",
        company="Vishwakarma Pumps & Motors Pvt. Ltd.",
        line1="Plot 44, SIDCO Industrial Estate",
        line2="Kurichi",
        city="Coimbatore", state="Tamil Nadu", pincode="641021",
        phone="+91 422 267 8890", email="sales@example.co.in",
        gstin="33AABCV5678M1Z2",
    )
    _seed(
        _A["v_fire"], "Agnirodh Fire Equipment", "vendor",
        contact_name="Mr. Faiz Shaikh",
        company="Agnirodh Fire Equipment Co.",
        line1="Gala 3, Sarvodaya Industrial Estate",
        line2="LBS Marg, Bhandup West",
        city="Mumbai", state="Maharashtra", pincode="400078",
        phone="+91 22 2596 7412", email="orders@example.co.in",
        gstin="27AAECA9012P1Z8",
    )
    _seed(
        _A["v_steel"], "Sanghvi Steel & Pipes", "vendor",
        contact_name="Mr. Dharmesh Sanghvi",
        company="Sanghvi Steel & Pipes",
        line1="Shed 21, Odhav GIDC",
        line2="Nikol Road",
        city="Ahmedabad", state="Gujarat", pincode="382415",
        phone="+91 79 2287 5566", email="dispatch@example.co.in",
        gstin="24AAGFS3456K1ZQ",
    )

    STORE["_addr_seeded"] = True


def _seed(aid: str, label: str, atype: str, **fields) -> None:
    """Write one demo address; skips silently if that ID already exists."""
    if aid in STORE["addresses"]:
        return
    STORE["addresses"][aid] = {
        "id":      aid,
        "label":   label,
        "type":    atype,
        "country": "India",
        **fields,
    }


# =============================================================================
# HELPERS
# =============================================================================

def _e(value) -> str:
    """HTML-escape a stored value for safe interpolation into a template."""
    return str(escape(value or ""))


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def is_active(addr) -> bool:
    """
    Whether this address is offered in pickers.

    ⚠ **Absent means active.** See the note on `ACTIVE_FIELD`: every record
    written before the archive existed carries no such key, and a reading that
    treated a missing key as archived would empty every picker in the
    application at once.
    """
    return (addr or {}).get(ACTIVE_FIELD, True) is not False


# =============================================================================
# THE BOOK IS A MASTER — who points at an address, and how
# =============================================================================
#
# ⚠ **The module docstring's "nothing else in the app reads STORE['addresses']"
#   stopped being true a long time ago.** Six collections point into this book,
#   and until 30 August 2026 (fourth pass) deleting a row silently dangled every
#   one of them — `delete_address()` said in terms that "nothing else in the app
#   references addresses, so there is no integrity check to run here", which was
#   the state of the world when it was written and has not been since.
#
# **This reads the other collections directly and imports none of them.** That
# is the one-way trick `boq.py` runs on `STORE["ra_bills"]` and it is what keeps
# the graph acyclic: `po_draft.py`, `purchase.py`, `challan.py` and
# `employee.py` all import THIS module, so an import back from here would be a
# cycle at boot. `project.py` imports it too, from the same pass.
#
# ⚠ **Quotations and BOQs are deliberately NOT here, and their absence is a
#   fact rather than an oversight.** `picker_payload()` is a *fill* helper: it
#   hands the browser the fields, JavaScript copies them into the form, and the
#   document stores its own party block with **no id and no label** pointing
#   back. Deleting an address cannot dangle a quotation because a quotation
#   never referenced one. The delete page has always said so.
#
# (collection, id field, snapshot field, human kind, label fields, view endpoint)
REFERENCE_SOURCES = (
    ("projects",          "site_address_id", "site_address",
     "Project",          ("name",),                     "projectview.view_project"),
    ("employees",         "site_address_id", "site",
     "Employee",         ("name", "code"),              "employee.view_employee"),
    ("attendance",        "site_address_id", "site",
     "Attendance",       ("employee_name", "date"),     "attendance.edit_attendance"),
    ("purchase_orders",   "vendor_id",       "vendor_name",
     "Draft PO",         ("ref",),                      "po_draft.view_po"),
    ("purchases",         "vendor_id",       "vendor_name",
     "Purchase order",   ("ref",),                      "purchase.view_purchase"),
    ("delivery_challans", "consignee_id",    "consignee_name",
     "Delivery challan", ("ref",),                      "challan.view_dc"),
)


def _snapshot_strings(addr: dict) -> set:
    """
    Every string a writer in this application copies OFF an address.

    Three of them, and each is here because a real writer produces it:
    `employee.py` and the project form snapshot the **label**; `purchase.py`
    writes `company or label`; `po_draft.py` and `challan.py` write
    `company or contact_name`.

    ⚠ **Blank values are excluded, and that is load-bearing.** An address with
    no company would otherwise match every record whose snapshot field is empty
    — which is most of them — and `references_of()` would refuse every deletion
    in the book.
    """
    return {s for s in (str((addr or {}).get("label") or "").strip(),
                        str((addr or {}).get("company") or "").strip(),
                        str((addr or {}).get("contact_name") or "").strip())
            if s}


def references_of(address_id: str) -> list:
    """
    Every record in the application that points at this address.

    Returns `[{"collection", "id", "kind", "label", "how", "endpoint"}, …]`,
    empty when nothing does. `how` is `"id"` or `"label"`.

    ⚠ **It matches on BOTH the id and the snapshot string, and it has to.**
    Some existing references are ids — `vendor_id`, `consignee_id`,
    `site_address_id` — and some are strings, because those fields were free
    text before the pickers arrived and the backfills deliberately left an
    unmatched string exactly as it stood. A guard that read only the id would
    pass a legacy record straight through and delete the address underneath it.

    ⚠ **The string comparison is EXACT after `strip()` and nothing else.** No
    casefolding, no whitespace collapsing, no prefix match — the rule
    `tools/backfill_site_links.py` set and the rule `po_parts.py` was made to
    obey. Nothing here is fuzzy-matched.

    ⚠ **It can over-report and never under-reports, deliberately.** Two
    addresses sharing a company name both claim a record that names that
    company, so both are refused deletion. A guard that errs is to err toward
    refusing; the escape is the archive, and an over-report is visible on screen
    because the refusal names the records.
    """
    aid = str(address_id or "").strip()
    if not aid:
        return []
    snaps = _snapshot_strings((STORE.get("addresses") or {}).get(aid) or {})

    out = []
    for coll, id_field, snap_field, kind, label_fields, endpoint in REFERENCE_SOURCES:
        for rid, rec in sorted((STORE.get(coll) or {}).items()):
            if not isinstance(rec, dict):
                continue
            if str(rec.get(id_field) or "").strip() == aid:
                how = "id"
            elif snaps and str(rec.get(snap_field) or "").strip() in snaps:
                how = "label"
            else:
                continue
            bits = [str(rec.get(f) or "").strip() for f in label_fields]
            out.append({
                "collection": coll,
                "id":         str(rid),
                "kind":       kind,
                "label":      " · ".join(b for b in bits if b) or str(rid)[:8],
                "how":        how,
                "endpoint":   endpoint,
            })
    return out


def _ref_chips(refs: list) -> str:
    """
    The referencing records as clickable chips — `ra.party_lock_bills()`'s
    shape on `/client/edit-party`, deliberately, rather than a second design.

    **A refusal that does not say what is blocking it is a dead end**: the
    operator is told no and given nothing to go and look at.

    An endpoint that cannot be built is rendered as a plain chip rather than
    raising — `url_for` fails on an endpoint the app has not registered, and a
    guard page is the last place that should 500.
    """
    out = ""
    for r in refs:
        text = (f'{_e(r["kind"])} &middot; {_e(r["label"])}'
                f'{" &middot; by name" if r["how"] == "label" else ""}')
        try:
            href = url_for(r["endpoint"], id=r["id"])
        except Exception:
            out += f'<span class="addr-ref">{text}</span>'
            continue
        out += f'<a class="addr-ref" href="{href}">{text}</a>'
    return out


# =============================================================================
# THE EDIT LOG — who changed what, on a record other records point at
# =============================================================================
#
# ⚠ **Editing a referenced address is ALLOWED, and that is a decision rather
#   than an omission.** `Banglore` is misspelled on the live database right now,
#   on two of the three projects that name a site at all. Freeze edits on a
#   referenced address and that misspelling is permanent, because there is no
#   repoint UI to move a project off it. The `type` field is the single
#   exception — see `_type_lock_error()`.
#
# ⚠ **The log records a USER ID, not a display name.** `purchase.reprice_log`
#   stores `display_name or username`, and that is a known open gap: rename the
#   user and the history restates itself; delete them and it points at a string
#   naming nobody. This does not repeat it. The id is what is stored; the
#   **screen** resolves it to a name at render time and says so plainly when the
#   account is gone.

# The fields whose movement is worth a history entry. `id` is not one, and
# neither are `active` or the log itself — archiving is its own act with its own
# route, and a log that logged its own writes would grow without bound.
LOGGED_FIELDS = ("label", "type", "contact_name", "company", "line1", "line2",
                 "landmark", "city", "state", "pincode", "country",
                 "phone", "email", "gstin")


def _editor_id() -> str:
    """
    Who is editing, as an **id**. `""` when nobody is signed in.

    Imported inside the function for `purchase._repricer()`'s reason: `auth.py`
    is a bottom-of-graph module, `dashboard.py` already pulls it in, and a
    module-level arrow here would be a new edge on ABOUT.md §2's graph for one
    string.
    """
    import auth
    return str((auth.current_user() or {}).get("id") or "")


def editor_label(user_id: str) -> str:
    """
    A user id resolved to something a human reads, at RENDER time.

    ⚠ **The resolution happens here and never at write time**, which is the
    whole of the fix over `reprice_log`. A renamed user's history follows the
    rename; a deleted one is named as deleted rather than silently pointing at a
    string that no longer identifies anybody.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return "not signed in"
    u = (STORE.get("users") or {}).get(uid) or {}
    name = str(u.get("display_name") or u.get("username") or "").strip()
    return name or f"deleted user {uid[:8]}"


def _log_edit(addr: dict, before: dict, after: dict, user_id: str) -> list:
    """
    Append one entry naming every field that moved. Returns the moved fields.

    Writes **nothing** when nothing moved: a submit that changes no field is not
    an edit, and a log full of "no change" rows is a log nobody reads —
    `_record_reprice()`'s rule, one module over.
    """
    changes = [{"field": f,
                "from":  str(before.get(f) or ""),
                "to":    str(after.get(f) or "")}
               for f in LOGGED_FIELDS
               if str(before.get(f) or "") != str(after.get(f) or "")]
    if not changes:
        return []
    addr.setdefault(EDIT_LOG_FIELD, []).append({
        "at":         _now(),
        "by_user_id": user_id,
        "changes":    changes,
    })
    return changes


def _type_lock_error(addr: dict, new_type: str, refs: list) -> str:
    """
    Why this address's `type` may not change, or `""`.

    ⚠ **`type` is the ONE field locked while anything references the address.**
    Every other field may move — see the note above. This one may not, because
    it is the field the pickers filter on: flip a `site` to a `vendor` and it
    drops out of `SITE_TYPES`, `employee.site_options()` and the project form
    stop offering it, and every existing reference goes dangling with **nothing
    on screen explaining why**. A silent disappearance is the failure mode; a
    refusal that names the records is not.
    """
    if not refs:
        return ""
    if str(new_type or "") == str(addr.get("type") or ""):
        return ""
    n = len(refs)
    return (f"The address type cannot be changed while {n} record"
            f"{'' if n == 1 else 's'} still point"
            f"{'s' if n == 1 else ''} at this address. Changing it from "
            f"'{ADDRESS_TYPES.get(addr.get('type'), addr.get('type'))}' to "
            f"'{ADDRESS_TYPES.get(new_type, new_type)}' would drop it out of "
            f"the pickers those records were chosen from, and each would be "
            f"left pointing at something no form offers any more. Every other "
            f"field on this address can still be corrected.")


def format_address_lines(addr: dict) -> list[str]:
    """
    Return the address as display lines, in Indian postal order.

    Kept here (and unused elsewhere) so the module stays self-contained; it is
    the one function another module would import if this ever gets wired into
    quotations.
    """
    lines: list[str] = []

    if addr.get("company"):
        lines.append(addr["company"])
    if addr.get("contact_name"):
        lines.append(f'Kind Attn: {addr["contact_name"]}')
    if addr.get("line1"):
        lines.append(addr["line1"])
    if addr.get("line2"):
        lines.append(addr["line2"])
    if addr.get("landmark"):
        lines.append(addr["landmark"])

    city_line = addr.get("city", "")
    if addr.get("pincode"):
        city_line = f'{city_line} - {addr["pincode"]}' if city_line else addr["pincode"]
    if city_line:
        lines.append(city_line)

    state_line = ", ".join(x for x in (addr.get("state"), addr.get("country", "India")) if x)
    if state_line:
        lines.append(state_line)

    return lines


def format_address_oneline(addr: dict) -> str:
    """Single-line form, e.g. for a dropdown label."""
    return ", ".join(format_address_lines(addr))


def _type_badge(atype: str) -> str:
    label = ADDRESS_TYPES.get(atype, atype.capitalize())
    return f'<span class="badge badge-addr-{_e(atype)}">{_e(label)}</span>'


# =============================================================================
# PICKER API — for other modules that want to reuse the book
# =============================================================================
# These two functions are the whole public surface for embedding an address
# picker elsewhere (quotation.py uses them for Bill To / Ship To). Keeping the
# shape here means the book can grow fields without the consumer knowing.

# Fields handed to a consuming form. Add one here and it becomes available to
# every picker automatically.
PICKER_FIELDS = ("label", "type", "contact_name", "company",
                 "line1", "line2", "landmark", "city", "state",
                 "pincode", "country", "phone", "email", "gstin")


def picker_payload() -> dict:
    """
    The whole book as {id: {field: value}}, ready to be JSON-embedded in a
    form so the browser can fill fields without a round trip.

    ⚠ **Archived addresses stay in here, and that is deliberate.** This is the
    table `picker_options()`'s selection is filled FROM, keyed by id. An
    archived address is still offered as the current selection on a form
    re-rendering an existing record (see `picker_options`), so dropping it here
    would offer an option that fills nothing.

    ⚠ **It no longer seeds** — see `picker_options()`.
    """
    return {
        aid: {f: (addr.get(f) or "") for f in PICKER_FIELDS}
        for aid, addr in STORE["addresses"].items()
    }


def picker_options(placeholder: str = "— choose from address book —",
                   only_types: tuple | list | None = None,
                   selected: str = "") -> str:
    """
    <option> list grouped by address type, for a picker <select>.

    Labelled "<label> — <city>" because that is how someone actually recognises
    a saved address; the full text is filled into the form on selection.

    ``only_types`` narrows the list to those address types — `("vendor",)` for
    the purchase order form, which must not offer a customer's site as somebody
    to buy from. Omitted (the default) it returns the whole book, which is what
    the quotation's Bill To / Ship To pickers want. ``selected`` marks one
    option, for a form re-rendering after a failed POST.

    Note the orphan group is suppressed when filtering: an address whose type is
    not in ADDRESS_TYPES is being rescued from disappearing, not offered as a
    match for a filter it does not satisfy.

    ⚠ **This no longer calls `ensure_demo_addresses()` (30 August 2026, fourth
    pass).** Rendering a form is not a reason to write six demo records into a
    client's database, and this function is reached from five other modules'
    forms. The seed still runs where the repo's other seeds run —
    `dashboard.index()` calls it beside `ensure_demo_products()` — and every
    route in this module still calls it. Nothing lost a seed; one form stopped
    causing one.

    ⚠ **An ARCHIVED address is not offered — except as the current
    `selected`.** An edit form re-rendering a record whose address was archived
    afterwards must not silently drop the vendor or the site it already carries;
    that option stays, marked, so the operator sees what the record holds and
    can change it deliberately. Everything else archived is gone from the list.
    """
    book = STORE["addresses"]
    html = f'<option value="">{_e(placeholder)}</option>'

    def _offerable(aid: str, a: dict) -> bool:
        return is_active(a) or aid == selected

    def _opt(aid: str, a: dict, with_city: bool = True) -> str:
        city = a.get("city") or ""
        tail = f' — {_e(city)}' if (with_city and city) else ""
        sel  = " selected" if aid == selected else ""
        arch = "" if is_active(a) else " (archived)"
        return (f'<option value="{_e(aid)}"{sel}>'
                f'{_e(a.get("label"))}{tail}{arch}</option>')

    wanted = tuple(only_types) if only_types else None

    for type_key, type_label in ADDRESS_TYPES.items():
        if wanted and type_key not in wanted:
            continue
        rows = [(aid, a) for aid, a in book.items()
                if a.get("type") == type_key and _offerable(aid, a)]
        if not rows:
            continue
        html += f'<optgroup label="{_e(type_label)}">'
        for aid, a in sorted(rows, key=lambda r: (r[1].get("label") or "").lower()):
            html += _opt(aid, a)
        html += "</optgroup>"

    # Addresses whose type is not in ADDRESS_TYPES would otherwise vanish.
    orphans = [(aid, a) for aid, a in book.items()
               if a.get("type") not in ADDRESS_TYPES and _offerable(aid, a)]
    if orphans and not wanted:
        html += '<optgroup label="Other">'
        for aid, a in orphans:
            html += _opt(aid, a, with_city=False)
        html += "</optgroup>"

    return html


def has_options(only_types: tuple | list | None = None) -> bool:
    """
    Whether any address would be offered for these types.

    The other half of `picker_options()` no longer seeding: a form that opens
    with an empty picker has to be able to say *"the book is empty — add
    one"* rather than render a `<select>` with a placeholder and no way out.
    """
    wanted = tuple(only_types) if only_types else None
    for a in (STORE.get("addresses") or {}).values():
        if not is_active(a):
            continue
        if wanted and a.get("type") not in wanted:
            continue
        return True
    return False


def _validate(form) -> tuple[dict, str | None]:
    """
    Pull an address dict out of a submitted form.
    Returns (data, error). `data` is always returned so the form can be
    re-rendered with whatever the user typed.
    """
    data = {
        "label":        form.get("label", "").strip(),
        "type":         form.get("type", "office"),
        "contact_name": form.get("contact_name", "").strip(),
        "company":      form.get("company", "").strip(),
        "line1":        form.get("line1", "").strip(),
        "line2":        form.get("line2", "").strip(),
        "landmark":     form.get("landmark", "").strip(),
        "city":         form.get("city", "").strip(),
        "state":        form.get("state", "").strip(),
        "pincode":      form.get("pincode", "").strip(),
        "country":      "India",
        "phone":        form.get("phone", "").strip(),
        "email":        form.get("email", "").strip(),
        "gstin":        form.get("gstin", "").strip().upper(),
    }

    if not data["label"]:
        return data, "Label is required — it is how this address is listed."
    if data["type"] not in ADDRESS_TYPES:
        return data, "Invalid address type."
    if not data["line1"]:
        return data, "Address Line 1 (building / plot / unit) is required."
    if not data["city"]:
        return data, "City / Town is required."
    if data["state"] not in INDIAN_STATES:
        return data, "Please pick a State or Union Territory from the list."
    if not _PIN_RE.match(data["pincode"]):
        return data, "PIN Code must be 6 digits and cannot start with 0."

    if data["phone"]:
        digits = re.sub(r"\D", "", data["phone"])
        if not 8 <= len(digits) <= 13:
            return data, "Phone number looks wrong — enter 8 to 13 digits, e.g. +91 98200 41122."
    if data["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", data["email"]):
        return data, "E-mail address is not valid."
    if data["gstin"] and not _GSTIN_RE.match(data["gstin"]):
        return data, "GSTIN must be 15 characters, e.g. 27AAACS1234F1Z5."

    return data, None


# =============================================================================
# CSS — address-module-specific (layered on BASE_STYLES + PRODUCT_STYLES)
# =============================================================================

ADDRESS_STYLES = """
<style>
  /* ── Card grid ──────────────────────────────────────────────────────── */
  .addr-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.25rem;
  }

  .addr-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem 1.6rem 1.25rem;
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    gap: .9rem;
    transition: box-shadow .2s ease, border-color .2s ease, transform .2s ease;
  }
  .addr-card:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--brand-lt);
    transform: translateY(-2px);
  }

  .addr-card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: .75rem;
  }
  .addr-label {
    font-size: 1rem;
    font-weight: 700;
    color: var(--navy);
    letter-spacing: -.2px;
    line-height: 1.35;
  }

  /* Postal block — deliberately monospaced-ish spacing, like an envelope. */
  .addr-block {
    font-size: .89rem;
    line-height: 1.65;
    color: var(--text);
  }
  .addr-block .addr-attn { color: var(--muted); font-size: .84rem; }
  .addr-block .addr-co   { font-weight: 600; }
  .addr-block .addr-pin  { font-weight: 600; letter-spacing: .02em; }

  /* Contact / statutory chips */
  .addr-meta {
    display: flex;
    flex-wrap: wrap;
    gap: .4rem;
    padding-top: .85rem;
    border-top: 1px solid var(--border);
  }
  .addr-chip {
    display: inline-flex;
    align-items: center;
    gap: .3rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: .22rem .7rem;
    font-size: .76rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .addr-chip b { color: var(--text); font-weight: 600; }
  .addr-chip-gst b { font-family: 'SFMono-Regular', Consolas, monospace; font-size: .74rem; }

  .addr-actions {
    display: flex;
    gap: .5rem;
    align-items: center;
    margin-top: .15rem;
  }
  .addr-actions .btn,
  .addr-actions .btn-delete { font-size: .78rem; padding: .3rem .8rem; }
  .btn-copy {
    font-family: var(--font);
    font-size: .78rem;
    font-weight: 600;
    color: var(--navy);
    background: var(--navy-lt);
    border: 1px solid transparent;
    border-radius: 6px;
    padding: .3rem .8rem;
    cursor: pointer;
    transition: background .15s, border-color .15s;
  }
  .btn-copy:hover  { border-color: var(--navy); }
  .btn-copy.copied { background: #dcfce7; color: #166534; }

  /* ── The book is a master: references, archive, edit history ────────── */
  .addr-card-tags { display:flex; flex-direction:column; align-items:flex-end; gap:.3rem; }
  .addr-label a { color: inherit; text-decoration: none; }
  .addr-label a:hover { text-decoration: underline; }
  .addr-card-archived { opacity: .72; border-style: dashed; }
  .addr-refcount {
    font-size: .7rem; font-weight: 600; color: var(--muted);
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 20px; padding: .1rem .55rem; white-space: nowrap;
  }
  .badge-addr-archived { background: #f1f0f5; color: #4b4459; }

  /* The refusal band and the reference chips. Deliberately `.cl-lock`'s
     shape on /client/edit-party rather than a second design — an operator
     who has met one has met both. */
  .addr-lock {
    border: 1px solid #fde68a; background: #fffbeb; border-radius: 10px;
    padding: .9rem 1.1rem; margin-bottom: 1.2rem;
    font-size: .82rem; line-height: 1.6;
  }
  .addr-free {
    border: 1px solid var(--border); background: var(--bg); border-radius: 10px;
    padding: .75rem 1.1rem; margin-bottom: 1.2rem;
    font-size: .82rem; line-height: 1.6; color: var(--muted);
  }
  .addr-archived-band {
    border: 1px solid var(--border); background: #f1f0f5; border-radius: 10px;
    padding: .75rem 1.1rem; margin-bottom: 1.2rem;
    font-size: .82rem; line-height: 1.6;
  }
  .addr-refs { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .7rem; }
  .addr-ref {
    display: inline-block; background: var(--surface);
    border: 1px solid var(--border); border-radius: 20px;
    padding: .18rem .7rem; font-size: .74rem; font-weight: 600;
    color: var(--navy); text-decoration: none; white-space: nowrap;
  }
  a.addr-ref:hover { border-color: var(--navy); }

  .addr-log { font-size: .82rem; }
  .addr-log .al-note { color: var(--muted); font-size: .76rem; line-height: 1.6; margin: 0 0 .8rem; }
  .al-entry { border-left: 2px solid var(--border); padding: .1rem 0 .5rem .8rem; margin-bottom: .7rem; }
  .al-when { font-weight: 600; color: var(--navy); font-size: .78rem; margin-bottom: .3rem; }
  .al-line { display: flex; gap: .6rem; flex-wrap: wrap; font-size: .78rem; padding: .1rem 0; }
  .al-field { color: var(--muted); min-width: 6rem; }
  .al-move { color: var(--text); }

  /* ── Type badges ────────────────────────────────────────────────────── */
  .badge-addr-office   { background: var(--navy-lt); color: var(--navy); }
  .badge-addr-site     { background: #FFF4D6; color: #8A5A00; }
  .badge-addr-billing  { background: #f0fdf4; color: #166534; }
  .badge-addr-shipping { background: #dbeafe; color: #1d4ed8; }
  .badge-addr-vendor   { background: #f1f0f5; color: #4b4459; }

  /* ── Form extras ────────────────────────────────────────────────────── */
  .form-card.addr-form { max-width: 760px; }
  .field-hint { font-size: .74rem; color: var(--muted); font-weight: 400; text-transform: none; letter-spacing: 0; }
  .form-section-title {
    grid-column: 1 / -1;
    font-size: .76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: var(--brand);
    margin-top: .5rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }
  .form-section-title:first-child { margin-top: 0; padding-top: 0; border-top: none; }

  /* A live envelope preview beside the form. */
  .addr-preview {
    background: var(--bg);
    border: 1px dashed var(--border);
    border-radius: 10px;
    padding: 1rem 1.15rem;
    font-size: .86rem;
    line-height: 1.6;
    color: var(--muted);
    grid-column: 1 / -1;
    white-space: pre-line;
    min-height: 4.5rem;
  }

  @media (max-width: 700px) {
    .addr-grid { grid-template-columns: 1fr; }
  }
</style>
"""

# Small helpers: clipboard copy on the list page, live preview on the form.
# Kept out of the f-string templates so the braces do not need doubling.
ADDRESS_SCRIPT = """
<script>
  function copyAddress(btn) {
    var text = btn.getAttribute('data-address');
    var done = function () {
      var original = btn.textContent;
      btn.textContent = 'Copied';
      btn.classList.add('copied');
      setTimeout(function () {
        btn.textContent = original;
        btn.classList.remove('copied');
      }, 1400);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done);
    } else {
      // http://localhost has no clipboard API in some browsers — fall back.
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (e) {}
      document.body.removeChild(ta);
    }
  }

  function updatePreview() {
    var box = document.getElementById('addr-preview');
    if (!box) return;
    var v = function (n) {
      var el = document.querySelector('[name="' + n + '"]');
      return el ? el.value.trim() : '';
    };
    var lines = [];
    if (v('company'))      lines.push(v('company'));
    if (v('contact_name')) lines.push('Kind Attn: ' + v('contact_name'));
    if (v('line1'))        lines.push(v('line1'));
    if (v('line2'))        lines.push(v('line2'));
    if (v('landmark'))     lines.push(v('landmark'));

    var cityLine = v('city');
    if (v('pincode')) cityLine = cityLine ? cityLine + ' - ' + v('pincode') : v('pincode');
    if (cityLine) lines.push(cityLine);
    if (v('state')) lines.push(v('state') + ', India');

    box.textContent = lines.length
      ? lines.join('\\n')
      : 'Start typing — the envelope preview appears here.';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('addr-form');
    if (!form) return;
    form.addEventListener('input',  updatePreview);
    form.addEventListener('change', updatePreview);
    updatePreview();
  });
</script>
"""


# =============================================================================
# RENDERING — why these views do not call render_template_string()
# =============================================================================
#
# Every page in this module is a fully interpolated HTML string by the time the
# view returns it. Nothing is passed as Jinja context — ABOUT.md §1 says so
# explicitly — so handing the finished string back to Jinja parses it a second
# time for no benefit and one large cost: any `{{ … }}` or `{% … %}` that
# reached the output from USER INPUT is then executed as a template.
#
# That is not theoretical. `_e()` escapes `< > & " '` and deliberately not
# braces, so an address whose company or street reads `{{ config }}` renders the
# Flask config — including SECRET_KEY — and one reading `{% for x in y %}`
# raises a TemplateSyntaxError. This module carries the widest blast radius of
# the six: the book is embedded in the quotation, purchase-order and BOQ
# pickers, so one bad record used to 500 three other modules' forms.
#
# Returning the string directly is what Flask does with any `str` a view
# returns. It removes the second parse, and with it the injection. HTML
# escaping still does its own job — this changes nothing about XSS.
#
# ⚠ Still open in `quotation.py` and `product.py`, and this one-liner does not
#   reach either: quotation.py builds its pages with `.format()` and has
#   attribute, <script> and option-text sinks besides; product.py does not
#   escape at all. Each wants its own pass — ABOUT.md §7.9d.
# =============================================================================

def _page(html: str) -> str:
    """A finished page. See the note above — deliberately not Jinja-rendered."""
    return html


# =============================================================================
# FORM RENDERER (shared by add + edit)
# =============================================================================

def _render_form(data: dict, *, heading: str, action_url: str,
                 submit_label: str, error: str | None,
                 refs: list | None = None, type_locked: bool = False) -> str:
    """Render the add/edit page. `data` holds the current field values."""
    list_url   = url_for("address.list_addresses")
    error_html = f'<div class="alert alert-error">&#10007; {_e(error)}</div>' if error else ""

    refs = refs or []
    lock_html = ""
    if refs:
        n = len(refs)
        lock_html = f"""
        <div class="addr-lock">
          <b>{n} record{"" if n == 1 else "s"} in this application
          point{"s" if n == 1 else ""} at this address.</b>
          Every field below can still be corrected &mdash; a misspelled city
          stays wrong forever otherwise, and nothing here repoints a record onto
          a different address. <b>The address TYPE is the one exception</b> and
          is shown read-only: changing it would drop this address out of the
          pickers those records were chosen from. Each change is recorded
          against your account and shown on the address page.
          <div class="addr-refs">{_ref_chips(refs)}</div>
        </div>"""

    type_opts = "".join(
        f'<option value="{_e(key)}" {"selected" if data.get("type") == key else ""}>{_e(label)}</option>'
        for key, label in ADDRESS_TYPES.items()
    )

    # ⚠ The hidden input is what makes the read-only control safe: a `readonly`
    #   text box submits its value, a disabled `<select>` submits nothing, and
    #   `_validate()` would then read `type` as its "office" default and rewrite
    #   the field the lock exists to protect. The server-side guard
    #   (`_type_lock_error()`) is the real one either way — this is the screen
    #   telling the truth about it.
    if type_locked:
        type_control = (
            f'<input type="text" value="'
            f'{_e(ADDRESS_TYPES.get(data.get("type"), data.get("type")))}" '
            f'readonly style="background:#f1f0f5;color:var(--muted);'
            f'cursor:not-allowed;"/>'
            f'<input type="hidden" name="type" value="{_e(data.get("type"))}"/>')
    else:
        type_control = f'<select name="type">{type_opts}</select>'
    state_opts = '<option value="">&#8212; Select state &#8212;</option>' + "".join(
        f'<option value="{_e(s)}" {"selected" if data.get("state") == s else ""}>{_e(s)}</option>'
        for s in INDIAN_STATES
    )

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title(heading)}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
      {PRODUCT_STYLES}
      {ADDRESS_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        {error_html}
        <div class="page-top">
          <h1>{_e(heading)}</h1>
          <a href="{list_url}" class="btn btn-ghost">&#8592; Address Book</a>
        </div>
        {lock_html}

        <div class="form-card addr-form">
          <form method="POST" action="{action_url}" id="addr-form">
            <div class="form-grid">

              <div class="form-section-title">Identification</div>

              <div class="form-group">
                <label>Label <span class="field-hint">— how it appears in the list</span></label>
                <input type="text" name="label" value="{_e(data.get('label'))}"
                       placeholder="e.g. Head Office — Mumbai" required/>
              </div>
              <div class="form-group">
                <label>Address Type</label>
                {type_control}
              </div>

              <div class="form-group">
                <label>Company / Firm</label>
                <input type="text" name="company" value="{_e(data.get('company'))}"
                       placeholder="e.g. Sunteck Realty Ltd."/>
              </div>
              <div class="form-group">
                <label>Contact Person</label>
                <input type="text" name="contact_name" value="{_e(data.get('contact_name'))}"
                       placeholder="e.g. Mr. Rajesh Kulkarni"/>
              </div>

              <div class="form-section-title">Postal Address</div>

              <div class="form-group full">
                <label>Address Line 1 <span class="field-hint">— building, plot, unit or survey no.</span></label>
                <input type="text" name="line1" value="{_e(data.get('line1'))}"
                       placeholder="e.g. Unit 12, Shreeji Industrial Estate" required/>
              </div>
              <div class="form-group full">
                <label>Address Line 2 <span class="field-hint">— road, street or locality</span></label>
                <input type="text" name="line2" value="{_e(data.get('line2'))}"
                       placeholder="e.g. Off Andheri-Kurla Road, Sakinaka"/>
              </div>
              <div class="form-group full">
                <label>Landmark <span class="field-hint">— optional, but Indian couriers rely on it</span></label>
                <input type="text" name="landmark" value="{_e(data.get('landmark'))}"
                       placeholder="e.g. Near Mittal Industrial Estate"/>
              </div>

              <div class="form-group">
                <label>City / Town</label>
                <input type="text" name="city" value="{_e(data.get('city'))}"
                       placeholder="e.g. Mumbai" required/>
              </div>
              <div class="form-group">
                <label>PIN Code</label>
                <input type="text" name="pincode" value="{_e(data.get('pincode'))}"
                       placeholder="e.g. 400072" inputmode="numeric"
                       pattern="[1-9][0-9]{{5}}" maxlength="6" required/>
              </div>

              <div class="form-group">
                <label>State / Union Territory</label>
                <select name="state" required>{state_opts}</select>
              </div>
              <div class="form-group">
                <label>Country</label>
                <input type="text" name="country" value="India" readonly
                       style="background:#f1f0f5;color:var(--muted);cursor:not-allowed;"/>
              </div>

              <div class="form-section-title">Contact &amp; Tax</div>

              <div class="form-group">
                <label>Phone</label>
                <input type="text" name="phone" value="{_e(data.get('phone'))}"
                       placeholder="+91 98200 41122"/>
              </div>
              <div class="form-group">
                <label>E-mail</label>
                <input type="text" name="email" value="{_e(data.get('email'))}"
                       placeholder="name@example.co.in"/>
              </div>
              <div class="form-group full">
                <label>GSTIN <span class="field-hint">— optional, 15 characters</span></label>
                <input type="text" name="gstin" value="{_e(data.get('gstin'))}"
                       placeholder="27AAACS1234F1Z5" maxlength="15"
                       style="text-transform:uppercase;font-family:'SFMono-Regular',Consolas,monospace;"/>
              </div>

              <div class="form-section-title">Envelope Preview</div>
              <div class="addr-preview" id="addr-preview"></div>

            </div>

            <div class="form-actions">
              <button type="submit" class="btn">{_e(submit_label)}</button>
              <a href="{list_url}" class="btn btn-ghost">Cancel</a>
            </div>
          </form>
        </div>

        <footer>
          <p>{B.COMPANY_NAME} &nbsp;&#183;&nbsp; {B.APP_SUBTITLE} &nbsp;&#183;&nbsp; address book</p>
        </footer>
      </main>
      {ADDRESS_SCRIPT}
    </body>
    </html>
    """
    return _page(template)


# =============================================================================
# ROUTES
# =============================================================================

@address_bp.route("/")
def list_addresses():
    """GET /address — the book, as envelope-style cards."""
    ensure_demo_addresses()

    addresses = STORE["addresses"]
    msg       = request.args.get("msg")
    msg_type  = request.args.get("type", "success")
    add_url   = url_for("address.add_address")
    dash_url  = url_for("dashboard.index")

    if addresses:
        cards = ""
        for aid, a in addresses.items():
            view_url   = url_for("address.view_address",   id=aid)
            edit_url   = url_for("address.edit_address",   id=aid)
            delete_url = url_for("address.delete_address", id=aid)
            n_refs     = len(references_of(aid))
            archived   = not is_active(a)

            # Postal block
            block = ""
            if a.get("company"):
                block += f'<div class="addr-co">{_e(a["company"])}</div>'
            if a.get("contact_name"):
                block += f'<div class="addr-attn">Kind Attn: {_e(a["contact_name"])}</div>'
            for key in ("line1", "line2", "landmark"):
                if a.get(key):
                    block += f'<div>{_e(a[key])}</div>'
            city_line = a.get("city", "")
            if a.get("pincode"):
                city_line = f'{city_line} - {a["pincode"]}' if city_line else a["pincode"]
            if city_line:
                block += f'<div class="addr-pin">{_e(city_line)}</div>'
            block += f'<div>{_e(a.get("state"))}, {_e(a.get("country", "India"))}</div>'

            chips = ""
            if a.get("phone"):
                chips += f'<span class="addr-chip">&#9742; <b>{_e(a["phone"])}</b></span>'
            if a.get("email"):
                chips += f'<span class="addr-chip">&#9993; <b>{_e(a["email"])}</b></span>'
            if a.get("gstin"):
                chips += f'<span class="addr-chip addr-chip-gst">GSTIN <b>{_e(a["gstin"])}</b></span>'
            chips_html = f'<div class="addr-meta">{chips}</div>' if chips else ""

            copy_text = _e("\n".join(format_address_lines(a)))

            # The two states an operator has to be able to see from the list:
            # archived (offered by no picker) and referenced (not deletable).
            state = ""
            if archived:
                state += '<span class="badge badge-addr-archived">Archived</span>'
            if n_refs:
                state += (f'<span class="addr-refcount" title="records pointing '
                          f'at this address">{n_refs} ref'
                          f'{"" if n_refs == 1 else "s"}</span>')

            cards += f"""
            <div class="addr-card{' addr-card-archived' if archived else ''}">
              <div class="addr-card-top">
                <div class="addr-label"><a href="{view_url}">{_e(a.get('label'))}</a></div>
                <div class="addr-card-tags">{_type_badge(a.get('type', 'office'))}{state}</div>
              </div>
              <div class="addr-block">{block}</div>
              {chips_html}
              <div class="addr-actions">
                <a href="{view_url}" class="btn btn-ghost">Open</a>
                <a href="{edit_url}" class="btn btn-ghost">Edit</a>
                <button type="button" class="btn-copy"
                        data-address="{copy_text}"
                        onclick="copyAddress(this)">Copy</button>
                <a href="{delete_url}" class="btn-delete" style="margin-left:auto;">
                  Delete
                </a>
              </div>
            </div>
            """
        body_html = f'<div class="addr-grid">{cards}</div>'
    else:
        body_html = """
        <div class="empty-state">
          <div style="font-size:2rem;">&#128205;</div>
          <p>No addresses yet. Add an office, site or delivery address to get started.</p>
        </div>
        """

    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{_e(msg_type)}">{icon} {_e(msg)}</div>'

    type_counts: dict[str, int] = {}
    for a in addresses.values():
        t = a.get("type", "office")
        type_counts[t] = type_counts.get(t, 0) + 1
    subtitle = " &nbsp;&#183;&nbsp; ".join(
        f"{n} {ADDRESS_TYPES.get(t, t).lower()}" for t, n in sorted(type_counts.items())
    )

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Address Book")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
      {PRODUCT_STYLES}
      {ADDRESS_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        {alert_html}
        <div class="page-top">
          <h1>Address <span>Book</span>
            <span style="font-size:.75rem;font-weight:500;color:var(--muted);margin-left:.6rem;">
              {len(addresses)} saved &nbsp;&#183;&nbsp; {subtitle}
            </span>
          </h1>
          <div style="display:flex;gap:.75rem;">
            <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
            <a href="{add_url}" class="btn">+ Add Address</a>
          </div>
        </div>
        {body_html}
        <footer>
          <p>{B.COMPANY_NAME} &nbsp;&#183;&nbsp; {B.APP_SUBTITLE} &nbsp;&#183;&nbsp; address book</p>
        </footer>
      </main>
      {ADDRESS_SCRIPT}
    </body>
    </html>
    """
    return _page(template)


@address_bp.route("/add", methods=["GET", "POST"])
def add_address():
    """
    GET  /address/add — blank form.
    POST /address/add — validate and write a new address to STORE.
    """
    ensure_demo_addresses()

    data  = {"type": "office", "country": "India"}
    error = None

    if request.method == "POST":
        data, error = _validate(request.form)
        if not error:
            new_id = str(uuid.uuid4())
            STORE["addresses"][new_id] = {"id": new_id, **data}
            return redirect(url_for(
                "address.list_addresses",
                msg=f"'{data['label']}' added to the address book.",
                type="success",
            ))

    return _render_form(
        data,
        heading="Add Address",
        action_url=url_for("address.add_address"),
        submit_label="Save Address",
        error=error,
    )


@address_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_address(id: str):
    """
    GET  /address/edit/<id> — form pre-filled with the stored address.
    POST /address/edit/<id> — validate and update it in place.

    ⚠ **Editing a REFERENCED address is allowed and logged**, `type` excepted.
    The reasoning is on the edit-log section above and it is not a small point:
    the live database misspells one city, and a freeze would make that permanent
    because there is no UI that repoints a record onto another address.

    ⚠ **The record is UPDATED, not replaced.** It used to be
    `STORE["addresses"][id] = {"id": id, **data}`, which discarded every key
    `_validate()` does not produce — which as of this pass is `active` and
    `edit_log`. Editing an archived address would have silently un-archived it
    and thrown its history away.
    """
    ensure_demo_addresses()

    existing = STORE["addresses"].get(id)
    if not existing:
        return redirect(url_for(
            "address.list_addresses",
            msg="That address no longer exists.",
            type="error",
        ))

    refs  = references_of(id)
    data  = dict(existing)
    error = None

    if request.method == "POST":
        data, error = _validate(request.form)
        if not error:
            error = _type_lock_error(existing, data.get("type"), refs) or None
        if not error:
            before = dict(existing)
            existing.update(data)
            if refs:
                _log_edit(existing, before, data, _editor_id())
            return redirect(url_for(
                "address.view_address", id=id,
                msg=f"'{data['label']}' updated.",
                type="success",
            ))

    return _render_form(
        data,
        heading="Edit Address",
        action_url=url_for("address.edit_address", id=id),
        submit_label="Update Address",
        error=error,
        refs=refs,
        type_locked=bool(refs),
    )


@address_bp.route("/view/<id>")
def view_address(id: str):
    """
    GET /address/view/<id> — one address, what points at it, and its history.

    ⚠ **New on 30 August 2026 (fourth pass), and it exists because the edit log
    needed somewhere to be seen.** A history nobody can read is not a control;
    it is a field in a database. The page also carries the archive control and
    the reference list, which are the two other things somebody standing in
    front of a refused deletion needs to see.

    Classified under the existing **`address.view`** permission — this is a
    reading of the book and nothing else.
    """
    ensure_demo_addresses()

    addr = STORE["addresses"].get(id)
    if not addr:
        return redirect(url_for("address.list_addresses",
                                msg="That address no longer exists.",
                                type="error"))

    refs   = references_of(id)
    active = is_active(addr)
    msg      = request.args.get("msg")
    msg_type = request.args.get("type", "success")

    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{_e(msg_type)}">{icon} {_e(msg)}</div>'

    block = "".join(f'<div>{_e(line)}</div>' for line in format_address_lines(addr))

    if refs:
        n = len(refs)
        by_name = sum(1 for r in refs if r["how"] == "label")
        name_note = ""
        if by_name:
            name_note = (f" {by_name} of them point{'s' if by_name == 1 else ''} "
                         f"at it <b>by name rather than by id</b> &mdash; a "
                         f"record written before that form became a picker. It "
                         f"counts here for exactly that reason: deleting the "
                         f"address would leave the name behind with nothing "
                         f"under it.")
        refs_html = f"""
      <div class="addr-lock">
        <b>{n} record{"" if n == 1 else "s"}
        point{"s" if n == 1 else ""} at this address.</b>
        It cannot be deleted while that is true.{name_note}
        Archive it instead if it should stop appearing in pickers &mdash; the
        records below go on resolving it.
        <div class="addr-refs">{_ref_chips(refs)}</div>
      </div>"""
    else:
        refs_html = """
      <div class="addr-free">
        <b>Nothing points at this address.</b> It can be deleted outright.
      </div>"""

    log = list(reversed(addr.get(EDIT_LOG_FIELD) or []))
    if log:
        entries = ""
        for e in log:
            rows = "".join(
                f'<div class="al-line"><span class="al-field">{_e(c.get("field"))}</span>'
                f'<span class="al-move">{_e(c.get("from")) or "(blank)"}'
                f' &#8594; {_e(c.get("to")) or "(blank)"}</span></div>'
                for c in (e.get("changes") or []))
            entries += (f'<div class="al-entry"><div class="al-when">'
                        f'{_e(e.get("at"))} &middot; '
                        f'{_e(editor_label(e.get("by_user_id")))}</div>'
                        f'{rows}</div>')
        log_html = f"""
      <div class="form-section-title">Edit history</div>
      <div class="addr-log">
        <p class="al-note">Recorded because other records point at this address.
        The account is stored as an <b>id</b> and resolved to a name when this
        page is rendered, so a renamed account reads correctly here and a
        deleted one says so.</p>
        {entries}
      </div>"""
    else:
        log_html = ""

    if active:
        arch_btn = (f'<form method="POST" action="'
                    f'{url_for("address.archive_address", id=id)}" '
                    f'style="display:inline;">'
                    f'<button type="submit" class="btn btn-ghost">Archive</button>'
                    f'</form>')
        arch_note = ""
    else:
        arch_btn = (f'<form method="POST" action="'
                    f'{url_for("address.unarchive_address", id=id)}" '
                    f'style="display:inline;">'
                    f'<button type="submit" class="btn">Un-archive</button>'
                    f'</form>')
        arch_note = """
      <div class="addr-archived-band">
        <b>This address is archived.</b> No picker offers it any more. Every
        record that already names it still resolves to it, and nothing printed
        or stored has changed. Un-archiving puts it back in the pickers.
      </div>"""

    return _page(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{B.page_title(str(addr.get('label') or 'Address'))}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{PRODUCT_STYLES}{ADDRESS_STYLES}
</head>
<body>
  {_nav()}
  <main>
    {alert_html}
    <div class="page-top">
      <h1>{_e(addr.get('label'))} {_type_badge(addr.get('type', 'office'))}</h1>
      <div style="display:flex;gap:.6rem;align-items:center;">
        <a href="{url_for('address.list_addresses')}" class="btn btn-ghost">&#8592; Address Book</a>
        <a href="{url_for('address.edit_address', id=id)}" class="btn">Edit</a>
        {arch_btn}
        <a href="{url_for('address.delete_address', id=id)}" class="btn-delete">Delete</a>
      </div>
    </div>
    {arch_note}
    {refs_html}
    <div class="form-card addr-form">
      <div class="addr-block">{block}</div>
    </div>
    {log_html}
    <footer>
      <p>{B.COMPANY_NAME} &nbsp;&#183;&nbsp; {B.APP_SUBTITLE} &nbsp;&#183;&nbsp; address book</p>
    </footer>
  </main>
</body>
</html>""")


@address_bp.route("/archive/<id>", methods=["POST"])
def archive_address(id: str):
    """
    POST /address/archive/<id> — take an address out of every picker.

    **POST only, and no GET half.** The delete route has a confirmation page
    because deletion is irreversible; this is reversible in one click from the
    same page, so a confirmation step would be ceremony rather than a guard.
    Nothing here destroys a record.

    Classified under the existing **`address.delete`** permission, not
    `address.edit`. It is what a refused delete becomes, and the person stopped
    by the guard is the person who needs the alternative; pulling an address out
    of every picker in the application is also a wider act than correcting one
    field on it. No permission was minted for this.
    """
    ensure_demo_addresses()
    addr = STORE["addresses"].get(id)
    if not addr:
        return redirect(url_for("address.list_addresses",
                                msg="That address no longer exists.",
                                type="error"))
    addr[ACTIVE_FIELD] = False
    return redirect(url_for("address.view_address", id=id,
                            msg=f"'{addr.get('label') or 'Address'}' archived — "
                                f"no picker offers it now.",
                            type="success"))


@address_bp.route("/unarchive/<id>", methods=["POST"])
def unarchive_address(id: str):
    """POST /address/unarchive/<id> — put it back in the pickers."""
    ensure_demo_addresses()
    addr = STORE["addresses"].get(id)
    if not addr:
        return redirect(url_for("address.list_addresses",
                                msg="That address no longer exists.",
                                type="error"))
    addr[ACTIVE_FIELD] = True
    return redirect(url_for("address.view_address", id=id,
                            msg=f"'{addr.get('label') or 'Address'}' is back in "
                                f"the pickers.",
                            type="success"))


@address_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_address(id: str):
    """
    Delete an address — **POST for the deletion, GET for the confirmation.**

    This used to destroy on GET, guarded only by a browser `confirm()`. A
    `confirm()` does not run for a link-prefetching browser, a crawler, a chat
    client unfurling a pasted URL, or a back button — all of which issue a plain
    GET. `ra.delete_ra()` is the pattern this now matches exactly; see ABOUT.md
    §7's delete audit.

    ⚠ **REFUSED while anything references the address (30 August 2026, fourth
    pass).** This docstring used to say *"nothing else in the app references
    addresses, so there is no integrity check to run here"*. That was true when
    it was written and has not been for a long time: six collections point into
    this book, and deleting a row dangled every reference silently.

    ⚠ **The refusal NAMES the records, as chips** — `ra.party_lock_bills()`'s
    shape on `/client/edit-party`. A refusal that does not say what is blocking
    it is a dead end, and the operator's next move is either to repoint those
    records or to archive this one, both of which need to know which they are.

    **The guard is on the POST as well as the GET**, `client.edit_party()`'s
    arrangement: the page and the guard cannot say different things, and a
    POST hand-made against a referenced address is refused rather than obeyed.
    """
    ensure_demo_addresses()

    addr = STORE["addresses"].get(id)
    if not addr:
        return redirect(url_for(
            "address.list_addresses",
            msg="That address no longer exists.",
            type="error",
        ))

    refs = references_of(id)

    if request.method == "POST":
        if refs:
            n = len(refs)
            names = ", ".join(f'{r["kind"]} {r["label"]}' for r in refs[:4])
            more = f" and {n - 4} more" if n > 4 else ""
            return redirect(url_for(
                "address.view_address", id=id,
                msg=(f"'{addr.get('label') or 'This address'}' cannot be "
                     f"deleted — {n} record{'' if n == 1 else 's'} still "
                     f"point{'s' if n == 1 else ''} at it: {names}{more}. "
                     f"Archive it instead if it should leave the pickers."),
                type="error",
            ))
        STORE["addresses"].pop(id, None)
        return redirect(url_for(
            "address.list_addresses",
            msg=f"'{addr.get('label', 'Address')}' deleted.",
            type="success",
        ))

    label = addr.get("label") or "this address"
    who = " &middot; ".join(x for x in [
        _e(addr.get("company")), _e(addr.get("contact_name")),
        _e(addr.get("city"))] if x)

    if refs:
        n = len(refs)
        body = f"""
    <div class="addr-lock">
      <b>This address cannot be deleted.</b>
      {n} record{"" if n == 1 else "s"} in this application
      point{"s" if n == 1 else ""} at it, and deleting it would leave
      {"that record" if n == 1 else "each of them"} naming something that no
      longer exists. Nothing here repoints a record onto a different address:
      that is done on the record itself.
      <div class="addr-refs">{_ref_chips(refs)}</div>
    </div>
    <p style="font-size:.85rem;line-height:1.6;">
      If this address should stop being offered in pickers, <b>archive</b> it.
      The records above go on resolving it, nothing already printed changes, and
      it can be un-archived at any time.
    </p>
    <div style="display:flex;gap:.7rem;">
      <form method="POST" action="{url_for('address.archive_address', id=id)}">
        <button type="submit" class="btn">Archive {_e(label)} instead</button>
      </form>
      <a href="{url_for('address.view_address', id=id)}" class="btn btn-ghost">Back to the address</a>
    </div>"""
    else:
        body = f"""
    <div style="border:1px solid #fecaca;background:#fef2f2;border-radius:10px;
                padding:1rem 1.1rem;margin-bottom:1.2rem;">
      <h2 style="margin:0 0 .5rem;font-size:1rem;color:var(--brand);">
        &#9888; This cannot be undone
      </h2>
      <div style="font-size:.82rem;line-height:1.6;">
        You are about to delete <b>{_e(label)}</b>{f" &mdash; {who}" if who else ""}.<br/><br/>
        Nothing in this application points at it &mdash; that was checked just
        now, by id and by name.<br/><br/>
        Quotations and purchase orders already issued keep the address they
        froze at the time, so nothing already sent changes. It only disappears
        from the picker.
      </div>
    </div>
    <form method="POST" action="{url_for('address.delete_address', id=id)}"
          style="display:flex;gap:.7rem;">
      <button type="submit" class="btn">Delete {_e(label)}</button>
      <a href="{url_for('address.list_addresses')}" class="btn btn-ghost">Keep it</a>
    </form>"""

    return _page(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{B.page_title("Delete Address")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{PRODUCT_STYLES}{ADDRESS_STYLES}
</head>
<body>
  {_nav()}
  <main>
    <div class="page-top"><h1>Delete <span>Address</span></h1></div>
    {body}
  </main>
</body>
</html>""")
