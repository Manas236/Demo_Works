"""
address.py — Address Book Module
================================
Blueprint : address_bp
Mounted at : /address  (registered in app.py)

A standalone directory of Indian-format postal addresses — offices, project
sites, billing and delivery locations. Deliberately self-contained:

  * nothing else in the app reads STORE["addresses"]
  * quotations and products are untouched
  * three demo addresses are seeded on first visit

Address model (all fields are plain strings):
    id, label, type, contact_name, company,
    line1, line2, landmark, city, state, pincode, country,
    phone, email, gstin

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
    """
    ensure_demo_addresses()
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
    """
    ensure_demo_addresses()
    book = STORE["addresses"]
    html = f'<option value="">{_e(placeholder)}</option>'

    def _opt(aid: str, a: dict, with_city: bool = True) -> str:
        city = a.get("city") or ""
        tail = f' — {_e(city)}' if (with_city and city) else ""
        sel  = " selected" if aid == selected else ""
        return f'<option value="{_e(aid)}"{sel}>{_e(a.get("label"))}{tail}</option>'

    wanted = tuple(only_types) if only_types else None

    for type_key, type_label in ADDRESS_TYPES.items():
        if wanted and type_key not in wanted:
            continue
        rows = [(aid, a) for aid, a in book.items() if a.get("type") == type_key]
        if not rows:
            continue
        html += f'<optgroup label="{_e(type_label)}">'
        for aid, a in sorted(rows, key=lambda r: (r[1].get("label") or "").lower()):
            html += _opt(aid, a)
        html += "</optgroup>"

    # Addresses whose type is not in ADDRESS_TYPES would otherwise vanish.
    orphans = [(aid, a) for aid, a in book.items()
               if a.get("type") not in ADDRESS_TYPES]
    if orphans and not wanted:
        html += '<optgroup label="Other">'
        for aid, a in orphans:
            html += _opt(aid, a, with_city=False)
        html += "</optgroup>"

    return html


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
                 submit_label: str, error: str | None) -> str:
    """Render the add/edit page. `data` holds the current field values."""
    list_url   = url_for("address.list_addresses")
    error_html = f'<div class="alert alert-error">&#10007; {_e(error)}</div>' if error else ""

    type_opts = "".join(
        f'<option value="{_e(key)}" {"selected" if data.get("type") == key else ""}>{_e(label)}</option>'
        for key, label in ADDRESS_TYPES.items()
    )
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
                <select name="type">{type_opts}</select>
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
            edit_url   = url_for("address.edit_address",   id=aid)
            delete_url = url_for("address.delete_address", id=aid)

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

            cards += f"""
            <div class="addr-card">
              <div class="addr-card-top">
                <div class="addr-label">{_e(a.get('label'))}</div>
                {_type_badge(a.get('type', 'office'))}
              </div>
              <div class="addr-block">{block}</div>
              {chips_html}
              <div class="addr-actions">
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
    POST /address/edit/<id> — validate and overwrite it in place.
    """
    ensure_demo_addresses()

    existing = STORE["addresses"].get(id)
    if not existing:
        return redirect(url_for(
            "address.list_addresses",
            msg="That address no longer exists.",
            type="error",
        ))

    data  = dict(existing)
    error = None

    if request.method == "POST":
        data, error = _validate(request.form)
        if not error:
            STORE["addresses"][id] = {"id": id, **data}
            return redirect(url_for(
                "address.list_addresses",
                msg=f"'{data['label']}' updated.",
                type="success",
            ))

    return _render_form(
        data,
        heading="Edit Address",
        action_url=url_for("address.edit_address", id=id),
        submit_label="Update Address",
        error=error,
    )


@address_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_address(id: str):
    """
    Delete an address — **POST for the deletion, GET for the confirmation.**

    This used to destroy on GET, guarded only by a browser `confirm()`. A
    `confirm()` does not run for a link-prefetching browser, a crawler, a chat
    client unfurling a pasted URL, or a back button — all of which issue a plain
    GET. `ra.delete_ra()` is the pattern this now matches exactly; see ABOUT.md
    §7's delete audit.

    Nothing else in the app references addresses, so there is no integrity check
    to run here (unlike products, which can be locked by an assembly).
    """
    ensure_demo_addresses()

    addr = STORE["addresses"].get(id)
    if not addr:
        return redirect(url_for(
            "address.list_addresses",
            msg="That address no longer exists.",
            type="error",
        ))

    if request.method == "POST":
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
    <div style="border:1px solid #fecaca;background:#fef2f2;border-radius:10px;
                padding:1rem 1.1rem;margin-bottom:1.2rem;">
      <h2 style="margin:0 0 .5rem;font-size:1rem;color:var(--brand);">
        &#9888; This cannot be undone
      </h2>
      <div style="font-size:.82rem;line-height:1.6;">
        You are about to delete <b>{_e(label)}</b>{f" &mdash; {who}" if who else ""}.<br/><br/>
        Quotations and purchase orders already issued keep the address they
        froze at the time, so nothing already sent changes. It only disappears
        from the picker.
      </div>
    </div>
    <form method="POST" action="{url_for('address.delete_address', id=id)}"
          style="display:flex;gap:.7rem;">
      <button type="submit" class="btn">Delete {_e(label)}</button>
      <a href="{url_for('address.list_addresses')}" class="btn btn-ghost">Keep it</a>
    </form>
  </main>
</body>
</html>""")
