"""
settings.py — Company Identity & Bank Details
=============================================
Blueprint  : settings_bp
Mounted at : /settings  (registered in app.py)

Routes
------
  GET,POST /settings/   — one form for everything client-specific

Why this exists
---------------
`branding.py` is the single source of truth for company identity, and it was
edited by hand. That is fine for a colour token and wrong for a GSTIN: the
people who know the registered address and the bank account are not the people
who open Python files. Every blank field prints as an amber "add …" chip on the
quotation and the proforma invoice, so until they are filled in no document is
ready to send — and the only way to fill them in was a code edit.

How it works
------------
The values in `branding.py` remain the **defaults**. This page saves overrides
to `STORE["settings"]["company"]` (persisted like any other collection) and
calls `branding.apply_settings()`, which pushes them onto the branding module.
Everything downstream keeps reading `B.COMPANY_ADDR` / `B.BANK_*` and picks the
new values up on the next render — no restart.

The one rule that makes that work: **read branding through the module.**
`B.COMPANY_ADDR` sees an override; `from branding import COMPANY_ADDR` binds a
copy at import and freezes on the default forever. `quotation.py` used to do
exactly that and was fixed when this page was added.

Clearing a field restores the default rather than saving a blank — see
`branding.apply_settings()`.
"""

import re
from flask import Blueprint, request, redirect, url_for

import branding as B
import pipeline as P
from dashboard import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES
from store import STORE

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

# The single record id. Company identity is a singleton — there is one company —
# so it is one row rather than a collection, which keeps db.py unchanged.
RECORD_ID = "company"


# =============================================================================
# FIELD DEFINITIONS — the form, the validation and the storage all read this
# =============================================================================
# (key, label, placeholder, validator or None)
#
# Every field is optional. A blank one falls back to the branding.py default and
# prints as an amber chip if that default is blank too, which is the existing
# and deliberate behaviour: a missing statutory detail must be visible, never
# silently empty.

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_PAN_RE   = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_IFSC_RE  = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+][0-9\s\-()]{6,19}$")
# Indian bank account numbers run 9–18 digits; no bank uses letters.
_ACCT_RE  = re.compile(r"^[0-9]{9,18}$")


def _v_gstin(v):  return "" if _GSTIN_RE.match(v) else "GSTIN must be 15 characters, e.g. 27AAACA1234A1Z5."
def _v_pan(v):    return "" if _PAN_RE.match(v)   else "PAN must be 10 characters, e.g. AAACA1234A."
def _v_ifsc(v):   return "" if _IFSC_RE.match(v)  else "IFSC must be 11 characters, e.g. HDFC0000123."
def _v_email(v):  return "" if _EMAIL_RE.match(v) else "That does not look like an e-mail address."
def _v_phone(v):  return "" if _PHONE_RE.match(v) else "Phone should be digits, optionally with + - ( ) or spaces."
def _v_acct(v):   return "" if _ACCT_RE.match(v)  else "Account number should be 9–18 digits, no spaces."


IDENTITY_FIELDS = [
    ("COMPANY_LEGAL",     "Legal Name",         "M/s Samruddhi Fire Services",        None),
    ("COMPANY_TAGLINE",   "Tagline",            "Fire Protection Systems & Services", None),
    ("COMPANY_ADDR",      "Registered Address", "Shop 3, …, Mumbai - 400001",         None),
    ("COMPANY_PHONE",     "Phone",              "8898420303",                         _v_phone),
    ("COMPANY_EMAIL",     "E-mail",             "samruddhifire@gmail.com",            _v_email),
    ("COMPANY_WEB",       "Website",            "www.samruddhifire.in",               None),
    ("COMPANY_GSTIN",     "GSTIN",              "27AAACA1234A1Z5",                    _v_gstin),
    ("COMPANY_PAN",       "PAN",                "AAACA1234A",                         _v_pan),
    ("COMPANY_BRANCHES",  "Branches",           "Mumbai · Pune",                      None),
    ("COMPANY_SIGNATORY", "Authorised Signatory", "Authorised Signatory",             None),
]

BANK_FIELDS = [
    ("BANK_NAME",         "Bank",         "HDFC Bank Ltd.",       None),
    ("BANK_ACCOUNT_NAME", "Account Name", "M/s Samruddhi Fire",   None),
    ("BANK_ACCOUNT_NO",   "Account No.",  "50200012345678",       _v_acct),
    ("BANK_IFSC",         "IFSC",         "HDFC0000123",          _v_ifsc),
    ("BANK_BRANCH",       "Branch",       "Andheri East, Mumbai", None),
]

ALL_FIELDS = IDENTITY_FIELDS + BANK_FIELDS

# Fields stored upper-cased, because that is how they are issued and how every
# downstream system expects to match them.
_UPPER = {"COMPANY_GSTIN", "COMPANY_PAN", "BANK_IFSC"}


# =============================================================================
# HELPERS
# =============================================================================

# =============================================================================
# SEED — specimen company identity
# =============================================================================
#
# ⚠ EVERY VALUE HERE IS SPECIMEN DATA, NOT SAMRUDDHI'S.
#   The statutory identifiers are deliberately template patterns and the bank
#   is named so nobody can mistake them for real. They exist so a fresh install
#   renders a complete-looking document instead of a page of amber "add …"
#   chips — and because a half-configured demo is harder to review than a
#   wrong-but-obviously-fake one.
#
#   Replace all of them at /settings before a document goes to a customer.
#   ABOUT.md §7.10 carries the same table and the same warning.
#
#   COMPANY_PHONE and COMPANY_EMAIL are the two REAL values and are therefore
#   not here: they are already the defaults in branding.py, and settings only
#   ever stores a value that differs from the default.
DEMO_COMPANY = {
    "COMPANY_LEGAL":       "M/s Samruddhi Fire Services",      # unconfirmed guess
    "COMPANY_ADDR":        ("Unit 7, Ganesh Industrial Estate, "
                            "Navi Mumbai - 400709, Maharashtra"),  # invented
    "COMPANY_WEB":         "www.samruddhifire.in",             # unverified
    "COMPANY_GSTIN":       "27AAAAA0000A1Z5",                  # all-A/all-zero template
    "COMPANY_PAN":         "AAAAA0000A",                       # template
    "COMPANY_BRANCHES":    "Navi Mumbai",
    "BANK_NAME":           "SPECIMEN BANK LTD.",
    "BANK_ACCOUNT_NAME":   "SAMRUDDHI FIRE SERVICES",
    "BANK_ACCOUNT_NO":     "50200000000000",                   # trailing zeros
    "BANK_IFSC":           "SPEC0000000",
    "BANK_BRANCH":         "Koparkhairne",
}


def ensure_demo_settings() -> None:
    """
    Seed the specimen company identity on first call; a no-op afterwards.

    This exists because the identity used to be **hand-entered** into
    `STORE["settings"]["company"]` and never seeded. It therefore lived only in
    one working database: dropping that database took the letterhead, the
    GSTIN, the PAN and the whole bank block with it, and every document started
    printing amber chips. ABOUT.md §7.10 described the data as "loaded", which
    was true of that one machine and of nowhere else.

    Called from `app._boot_persistence()` **after** `db.load_into()` and
    **before** `branding.apply_settings()`, because the letterhead is rendered
    by the first request and there is no route that reliably runs before it.
    Guarded by `STORE["_settings_seeded"]`, which is deliberately not persisted
    — the same contract as every other seeder in this app.

    ⚠ One consequence worth knowing: `edit_settings()` **deletes** the record
      when every field is left at its default, so "clear everything and
      restart" brings the specimen row back. That is the same behaviour
      `ensure_demo_products()` has on an emptied table and it is the price of
      an unpersisted flag. If a genuinely blank identity is ever wanted, it
      needs a persisted "deliberately cleared" marker rather than the absence
      of a record — the absence cannot tell "never set" from "set to nothing".
    """
    if STORE.get("_settings_seeded"):
        return
    # Only ever fills a gap. An identity somebody has actually entered — or
    # one loaded back out of MySQL a moment ago — is never overwritten.
    if RECORD_ID not in STORE["settings"]:
        STORE["settings"][RECORD_ID] = dict(DEMO_COMPANY)
    STORE["_settings_seeded"] = True


def load_saved() -> dict:
    """The stored overrides. Also the hook app.py calls at boot."""
    return STORE["settings"].get(RECORD_ID) or {}


def _validate(form) -> tuple:
    """
    Returns (data, error). **Always returns data**, so a rejected form
    re-renders with the user's input intact rather than throwing it away —
    the same contract as address._validate().

    Blank is always allowed: every one of these is optional, and clearing a
    field is how you go back to the branding.py default.
    """
    data, error = {}, ""
    for key, label, _ph, check in ALL_FIELDS:
        raw = (form.get(key) or "").strip()
        if key in _UPPER:
            raw = raw.upper()
        data[key] = raw
        if raw and check and not error:
            problem = check(raw)
            if problem:
                error = f"{label}: {problem}"
    return data, error


def _completeness(values: dict) -> tuple:
    """(filled, total) across the fields a document actually needs filled."""
    needed = [k for k, _l, _p, _c in ALL_FIELDS]
    filled = sum(1 for k in needed if (values.get(k) or "").strip())
    return filled, len(needed)


# =============================================================================
# CSS
# =============================================================================
# Reuses QUOTATION_STYLES for the form furniture (.form-section, .section-title,
# .fg2, .form-group, .alert) rather than re-declaring it. PRODUCT_STYLES, which
# address.py leans on, has the inputs but not the sectioned layout.
# Only the completeness meter and the blank-field marker are new.

SETTINGS_STYLES = """
<style>
  .set-intro {
    background:var(--surface); border:1px solid var(--border);
    border-left:3px solid var(--brand); border-radius:var(--radius);
    padding:1rem 1.2rem; margin-bottom:1.4rem; font-size:.88rem; line-height:1.6;
  }
  .set-intro b { color:var(--brand); }

  .set-meter { margin-top:.7rem; }
  .set-track {
    height:7px; background:var(--border); border-radius:99px; overflow:hidden;
  }
  .set-fill { height:100%; background:var(--brand); border-radius:99px; }
  .set-fill.done { background:#0CA30C; }
  .set-count {
    font-size:.78rem; color:var(--muted); margin-top:.35rem; font-weight:600;
  }

  /* A field left blank is not an error — it is a document that will print an
     amber chip. Say so next to the input rather than after the fact. */
  .fld-blank {
    font-size:.72rem; color:#8A5A00; font-weight:600; margin-top:.15rem;
  }
  .fld-hint { font-size:.72rem; color:var(--muted); margin-top:.15rem; }

  .set-actions {
    display:flex; gap:.75rem; align-items:center; flex-wrap:wrap;
    margin-top:1.4rem;
  }
  .set-actions .spacer { flex:1; }
  .set-note { font-size:.8rem; color:var(--muted); }
</style>
"""


# =============================================================================
# RENDERING — why this view does not call render_template_string()
# =============================================================================
#
# The page is a fully interpolated HTML string by the time the view returns it.
# Nothing is passed as Jinja context — ABOUT.md §1 says so explicitly — so
# handing the finished string back to Jinja parses it a second time for no
# benefit and one large cost: any `{{ … }}` or `{% … %}` that reached the output
# from USER INPUT is then executed as a template.
#
# That is not theoretical, and it is worst here. `pipeline.esc()` escapes
# `< > & " '` and deliberately not braces, so a company address saved with
# `{{ config }}` in it renders the Flask config — including SECRET_KEY — and
# `{% for x in y %}` raises a TemplateSyntaxError. These fields are pushed onto
# `branding` by `apply_settings()` and print in the LETTERHEAD, so one bad save
# used to reach every document and every page in the app at once, and the page
# needed to correct it was one of the ones that had stopped rendering.
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
# ROUTES
# =============================================================================

@settings_bp.route("/", methods=["GET", "POST"])
def edit_settings():
    error, notice = "", ""

    if request.method == "POST":
        data, error = _validate(request.form)
        if not error:
            # Store only what differs from the default, so a later change to
            # branding.py still reaches anyone who never overrode that field.
            overrides = {k: v for k, v in data.items()
                         if v and v != B.DEFAULTS.get(k, "")}
            if overrides:
                STORE["settings"][RECORD_ID] = overrides
            else:
                STORE["settings"].pop(RECORD_ID, None)

            B.apply_settings(overrides)
            return redirect(url_for("settings.edit_settings",
                                    msg="Company details saved.", type="success"))
        values = data
    else:
        values = B.current_settings()

    msg      = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    alert_html = ""
    if error:
        alert_html = f'<div class="alert alert-error">&#10007; {P.esc(error)}</div>'
    elif msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {P.esc(msg)}</div>'

    def _fields_html(fields) -> str:
        out = ""
        for key, label, placeholder, _check in fields:
            val   = values.get(key, "")
            blank = "" if str(val).strip() else (
                '<div class="fld-blank">blank — prints as an amber chip</div>')
            # The address is the only multi-line field; everything else is one
            # line and a textarea would just invite stray newlines into a
            # letterhead that has no room for them.
            if key == "COMPANY_ADDR":
                ctl = (f'<textarea id="{key}" name="{key}" rows="2" '
                       f'placeholder="{P.esc(placeholder)}">{P.esc(val)}</textarea>')
                cls = "form-group span2"
            else:
                ctl = (f'<input type="text" id="{key}" name="{key}" '
                       f'value="{P.esc(val)}" placeholder="{P.esc(placeholder)}"/>')
                cls = "form-group"
            out += (f'<div class="{cls}"><label for="{key}">{label}</label>'
                    f'{ctl}{blank}</div>')
        return out

    filled, total = _completeness(values)
    pct  = int(round(filled / total * 100)) if total else 0
    done = " done" if filled == total else ""

    dash_url = url_for("dashboard.index")

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Company Settings")}</title>{B.HEAD_ICON}
    {BASE_STYLES}{QUOTATION_STYLES}{SETTINGS_STYLES}</head>
    <body>{_nav()}
    <main>
      <div class="page-top">
        <h1>Company <span>Settings</span></h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
        </div>
      </div>

      {alert_html}

      <div class="set-intro">
        These are the details that print on every <b>quotation</b>,
        <b>proforma invoice</b> and <b>tax invoice</b> — the letterhead, the
        GSTIN/PAN line, and the bank account a customer pays into. The GSTIN
        does double duty: its first two digits are the State we supply from,
        which is how a tax invoice knows whether a supply attracts IGST or
        CGST&nbsp;+&nbsp;SGST. Anything left blank prints as a
        visible amber <span class="todo-chip">add …</span> marker rather than
        going out silently empty.
        <div class="set-meter">
          <div class="set-track"><div class="set-fill{done}" style="width:{pct}%;"></div></div>
          <div class="set-count">{filled} of {total} filled in</div>
        </div>
      </div>

      <form method="POST" action="{url_for("settings.edit_settings")}">

        <div class="form-section">
          <div class="section-title">Company Identity</div>
          <div class="fg2">{_fields_html(IDENTITY_FIELDS)}</div>
        </div>

        <div class="form-section">
          <div class="section-title">Bank Details &mdash; proforma invoice &amp; RA bill</div>
          <p class="fld-hint" style="margin:-.5rem 0 1rem;">
            These print on the proforma invoice and printed RA tax invoice, which request payment.
            They are deliberately kept off the quotation — that is an offer, not
            a demand for money.
          </p>
          <div class="fg2">{_fields_html(BANK_FIELDS)}</div>
        </div>

        <div class="set-actions">
          <button type="submit" class="btn">Save Details</button>
          <a href="{dash_url}" class="btn btn-ghost">Cancel</a>
          <span class="spacer"></span>
          <span class="set-note">Clearing a field restores its built-in default.</span>
        </div>
      </form>

      <footer><p>{B.COMPANY_NAME} · {B.APP_SUBTITLE} · company settings</p></footer>
    </main></body></html>"""
    return _page(template)
