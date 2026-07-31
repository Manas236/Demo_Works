"""
branding.py — Samruddhi Fire house identity
===========================================
Single source of truth for everything client-specific: legal identity, contact
block, colour tokens and logo artwork. No other module should hard-code a
company name, a hex colour or an image path — import from here instead.

╔══════════════════════════════════════════════════════════════════════════╗
║  FILL THESE IN BEFORE THE FIRST REAL QUOTATION GOES OUT                   ║
║  ------------------------------------------------------------------------║
║  The signboard photo only gave us the trading name and the logo, so the   ║
║  statutory / contact fields below are still blank. Anything left blank    ║
║  renders as a visible amber "add …" chip in the app and on the printed    ║
║  quotation, so nothing can quietly go out wrong:                          ║
║      COMPANY_LEGAL · COMPANY_ADDR · COMPANY_WEB · COMPANY_GSTIN           ║
║      COMPANY_PAN · COMPANY_BRANCHES                                       ║
║      BANK_NAME · BANK_ACCOUNT_NAME · BANK_ACCOUNT_NO · BANK_IFSC          ║
║      BANK_BRANCH                                                          ║
║  COMPANY_TAGLINE is an assumption drawn from the trading name — confirm   ║
║  the wording the client actually uses on their letterhead.                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import base64
from pathlib import Path

# =============================================================================
# 1. IDENTITY
# =============================================================================
COMPANY_NAME      = "SAMRUDDHI FIRE"           # trading name, from the signboard
COMPANY_LEGAL     = ""                         # e.g. "M/s Samruddhi Fire Services"
COMPANY_TAGLINE   = "Fire Protection Systems & Services"   # ASSUMPTION — confirm
COMPANY_ADDR      = ""
COMPANY_PHONE     = "8898420303"
COMPANY_EMAIL     = "samruddhifire@gmail.com"
COMPANY_WEB       = ""
COMPANY_GSTIN     = ""
COMPANY_PAN       = ""
COMPANY_BRANCHES  = ""
COMPANY_SIGNATORY = "Authorised Signatory"

# Short form used in reference numbers and compact UI (e.g. "SF/2026/0001")
COMPANY_SHORT     = "SF"

# The product/quotation app's own name, as the staff will see it.
APP_NAME          = "Samruddhi Fire"
APP_SUBTITLE      = "Quotation & Catalogue System"


# =============================================================================
# 1b. BANK DETAILS  (proforma invoice only)
# =============================================================================
# A proforma invoice is a request for money, so the remittance account has to
# print on it — a PI without these is not actionable by the customer's accounts
# department. Blank fields render as amber "add …" chips through field() exactly
# like the statutory block above, so an incomplete PI cannot go out looking
# finished. They are deliberately NOT used on the quotation: a quotation is an
# offer, not a demand for payment, and publishing the account number wider than
# necessary is a fraud surface.
BANK_NAME         = ""    # e.g. "HDFC Bank Ltd."
BANK_ACCOUNT_NAME = ""    # the name the account is held in (may differ from COMPANY_NAME)
BANK_ACCOUNT_NO   = ""
BANK_IFSC         = ""
BANK_BRANCH       = ""


def field(value: str, hint: str) -> str:
    """
    Render an identity field, or a visible placeholder when it is still blank.

    Blank statutory details must never look like a deliberate omission on a
    document that goes to a customer, so they are flagged rather than hidden.
    """
    value = (value or "").strip()
    return value if value else f'<span class="todo-chip">add {hint}</span>'


def name_html(accent_class: str) -> str:
    """
    Company name with its last word in the accent colour, the way the
    signboard paints it: SAMRUDDHI in red, FIRE in navy.
    """
    head, _, tail = COMPANY_NAME.rpartition(" ")
    if not head:
        return COMPANY_NAME
    return f'{head} <span class="{accent_class}">{tail}</span>'


def has(*values: str) -> bool:
    """True when every field passed has actually been filled in."""
    return all((v or "").strip() for v in values)


# =============================================================================
# 2. PALETTE  (sampled from the logo and the painted signboard)
# =============================================================================
RED        = "#D5121A"   # roundel "S" / SAMRUDDHI  — primary action colour
RED_DK     = "#A50D14"   # hover / pressed
RED_LT     = "#FDECEC"   # tinted surfaces, pills
NAVY       = "#2A086E"   # roundel "F" / FIRE       — headings, nav, document ink
NAVY_DK    = "#1C0449"
NAVY_LT    = "#EDEAF9"
SAFFRON    = "#F2944A"   # the Ganesh motif — used only as a small accent

# Dark-surface variants (the news module runs on a near-black canvas, where the
# print reds and navies go muddy).
RED_ON_DARK    = "#FF5A5F"
RED_ON_DARK_DK = "#E3392F"
RED_TINT_DARK  = "#3A1114"
INK        = "#1A1626"   # body text, warmed toward the navy
MUTED      = "#6B6478"
BORDER     = "#E4E0EC"
SURFACE    = "#FFFFFF"
CANVAS     = "#F6F4F9"

# CSS custom properties. Injected once at the top of the shared stylesheet so
# every existing var(--brand) reference re-themes without being touched.
CSS_TOKENS = f"""
  :root {{
    --bg:        {CANVAS};
    --surface:   {SURFACE};
    --brand:     {RED};
    --brand-dk:  {RED_DK};
    --brand-lt:  {RED_LT};
    --navy:      {NAVY};
    --navy-dk:   {NAVY_DK};
    --navy-lt:   {NAVY_LT};
    --saffron:   {SAFFRON};
    --text:      {INK};
    --muted:     {MUTED};
    --border:    {BORDER};
    --shadow-sm: 0 1px 3px rgba(26,22,38,.08), 0 1px 2px rgba(26,22,38,.06);
    --shadow-md: 0 6px 20px rgba(42,8,110,.14), 0 2px 6px rgba(26,22,38,.08);
    --radius:    14px;
    --font:      'DM Sans', 'Segoe UI', system-ui, sans-serif;
  }}

  /* Flags an identity field that still needs the client's real data. */
  .todo-chip {{
    display: inline-block;
    background: #FFF4D6;
    color: #8A5A00;
    border: 1px dashed #E0A93B;
    border-radius: 5px;
    padding: 0 .38em;
    font-size: .82em;
    font-weight: 600;
    font-style: normal;
    letter-spacing: 0;
    white-space: nowrap;
  }}
"""

# =============================================================================
# 2b. CHART PALETTE  (dashboard only — imported by dashboard.py, not by BASE_STYLES)
# =============================================================================
# Charts do not get to pick colours by eye. Two roles, two rules:
#
#   ORDINAL  — the sales funnel. Stage order carries meaning (Budgetary → PO
#              Expected), so the colour has to carry that order too: ONE hue,
#              stepping light → dark as the deal nears close. Derived at the
#              brand navy hue (#2A086E, OKLCH h=307°) so the funnel still reads
#              as house colour, with the lightest step held at 2.09:1 on white
#              so it never dissolves into the surface.
#
#   STATUS   — won / open / lost. These mean good-neutral-bad, so they wear
#              reserved status colours, never a series palette, and they always
#              ship with a text label beside the swatch (never colour alone).
#
# Both sets were checked with the dataviz validator rather than judged by eye:
# the ramp passes monotone-lightness, adjacent-ΔL and light-end contrast; the
# status trio passes the lightness band, chroma floor, CVD separation (worst
# adjacent pair ΔE 20.3 protan) and 3:1 contrast on the light surface.
# Re-run the validator if you change a single hex here.
CHART_NAVY = [
    "#B0ABF9",   # step 0 — earliest stage, lightest
    "#928BDC",
    "#756CC0",
    "#594DA5",
    "#402E89",
    "#2A086E",   # step 5 — brand navy, closest to close
]

CHART_WON     = "#0CA30C"   # status: good
CHART_LOST    = "#D03B3B"   # status: critical
CHART_SERIOUS = "#EC835A"   # status: serious  — chase this today
CHART_WARN    = "#FAB219"   # status: warning  — chase this week
CHART_OPEN    = CHART_NAVY[2]   # mid-ramp navy — "still in the funnel"

# Chart-only custom properties. Kept OUT of CSS_TOKENS so the quotation
# document and the other pages don't carry a palette they never draw with.
CHART_TOKENS = f"""
  :root {{
    --c-stage-0: {CHART_NAVY[0]};
    --c-stage-1: {CHART_NAVY[1]};
    --c-stage-2: {CHART_NAVY[2]};
    --c-stage-3: {CHART_NAVY[3]};
    --c-stage-4: {CHART_NAVY[4]};
    --c-stage-5: {CHART_NAVY[5]};
    --c-won:     {CHART_WON};
    --c-lost:    {CHART_LOST};
    --c-serious: {CHART_SERIOUS};
    --c-warn:    {CHART_WARN};
    --c-open:    {CHART_OPEN};
    --c-grid:    #ECE9F2;
    --c-track:   #F1EEF7;
  }}
"""

# =============================================================================
# 3. ARTWORK
# =============================================================================
# Logos are inlined as data URIs rather than served from /static: every page in
# this app is a self-contained render_template_string, and a printed or
# emailed quotation must still show the logo with no server to fetch it from.
_ASSETS = Path(__file__).resolve().parent / "assets"


def _data_uri(filename: str, mime: str = "image/png") -> str:
    """Base64 an asset for inline embedding; empty string if it is missing."""
    try:
        blob = (_ASSETS / filename).read_bytes()
    except OSError:
        return ""
    return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"


LOGO_URI     = _data_uri("logo-64.png")        # nav bar / small chrome
LOGO_DOC_URI = _data_uri("logo-256.png")       # letterhead, print quality
# A 32px PNG, not favicon.ico: the .ico carries every size up to 256 and would
# add ~68 KB of base64 to every page for a 16px tab icon.
FAVICON_URI  = _data_uri("favicon-32.png")
GANESH_URI   = _data_uri("ganesh.png")

# Drop into <head> of every page.
HEAD_ICON = f'<link rel="icon" href="{FAVICON_URI}"/>' if FAVICON_URI else ""


def page_title(page: str) -> str:
    """Consistent browser-tab titles: 'Quotations · Samruddhi Fire'."""
    return f"{page} &middot; {APP_NAME}"


def logo_img(px: int = 30, doc: bool = False, alt: str = "") -> str:
    """<img> for the roundel. `doc=True` uses the higher-resolution copy."""
    uri = LOGO_DOC_URI if doc else LOGO_URI
    if not uri:
        return ""
    alt = alt or f"{COMPANY_NAME} logo"
    return (f'<img src="{uri}" alt="{alt}" width="{px}" height="{px}" '
            f'style="width:{px}px;height:{px}px;object-fit:contain;display:block;"/>')
