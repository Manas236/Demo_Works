"""
docsheet.py — the printed A4 sheet, shared by every document that prints
=======================================================================

**This is the chrome, not the content.** Four documents in this app print the
same furniture — a letterhead, a party block, an items table, a totals block,
an amount in words, bank details, a signature — and until this module existed
each one wrote its own copy of it as a fresh f-string. They drifted, which is
what the client sees: four documents that do not look like they came from the
same office. The tax invoice and the purchase order shipped with the same
letterhead written twice and *already* differing by one line (§ `show_web`
below). The RA bill and the draft PO were each written from scratch and match
neither.

So: one module, taking data and returning HTML strings. Every consumer renders
through it, and a change to the letterhead is one edit rather than four.

What lives here
---------------
The **page frame** (`sheet_open` / `sheet_close`), the **letterhead**, the
**party block**, the **items-table shell**, the **totals rows**, the
**amount-in-words** line, the **bank block** and the **signature block**, plus
the stylesheet stack every sheet loads (`SHEET_STYLES`).

What deliberately does NOT live here
------------------------------------
**Any tax arithmetic, any per-chain business logic, and any route.** The
totals *rows* are furniture and are here; deciding what goes in them is not.
That distinction is load-bearing rather than tidy-minded: the RA chain's tax
block is **per line, with HSN/SAC per claim row**, and the sell chain's is
**document-level** off one `tax_info` dict. That difference is the reason
`ra.py` may not import `invoice.py` (ABOUT.md §2b), and collapsing the two into
a shared "tax block" here would smuggle the coupling back in through the
basement. Each chain composes its own block out of `sum_row()` and
`total_row()`.

Import direction — this module is a LEAF
----------------------------------------
```
docsheet.py ──► quotation.py   the A4 stylesheet and the document formatters
docsheet.py ──► branding, pipeline, dashboard, store
```

It imports **nothing** from `invoice.py`, `purchase.py`, `ra.py`, `boq.py`,
`proforma.py` or `po_draft.py`, and all of those may import it. That is what
lets the RA bill and the tax invoice share a letterhead **without either
importing the other** — they both depend on the leaf, and the standing
prohibition (`ra.py` must never import `invoice.py`) is untouched. Both halves
are asserted in `tests/test_import_directions.py`.

`quotation.py` is not on the forbidden list and is imported on purpose: it owns
`VIEW_DOC_STYLES` and the money formatters, it is frozen against edits
(INTRODUCTION.md §7) rather than against being depended on, and `ra.py`,
`boq.py` and `purchase.py` all already import it.

Byte-for-byte
-------------
Every builder below reproduces the exact bytes its callers used to emit,
including indentation, because `tests/test_print_golden.py` hashes the rendered
pages and was committed **before** this module existed. If you change a
builder, that file goes red and names the block — which is the point of it.
"""

import branding as B

# The A4 sheet and the document's own formatters. `_meta` is re-exported so a
# consumer needs one import rather than two.
from quotation import (          # noqa: F401  (_meta is re-exported)
    QUOTATION_STYLES,
    VIEW_DOC_STYLES,
    _amount_in_words,
    _fmt_qty,
    _inr,
    _meta,
)
from dashboard import BASE_STYLES
import pipeline as P


# =============================================================================
# STYLES
# =============================================================================

# The stack every printed sheet loads, in the order it has always been loaded
# in. A module layers its own sheet *after* this one and introduces no new
# font, type size or border weight — that restraint is why the documents look
# related, and it is stated in ABOUT.md §5 for each of them in turn.
SHEET_STYLES = f"{BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}"

# Rules for the blocks this module introduces to a sheet that did not carry
# them before. Scoped inside `.quotation-doc` exactly as `PROFORMA_STYLES` is,
# and using only the `--fs-*` and `--rule-*` already defined by
# `VIEW_DOC_STYLES`.
#
# The bank block's rules used to live in `PROFORMA_STYLES`, which is where they
# were written and the only place they were needed. They moved here when the RA
# bill needed the same block: `ra.py` may not import `proforma.py`, so leaving
# them there would have meant a second bank block that looked different from
# the first — the exact drift this module exists to end.
# The bank block's rules, as raw CSS rather than a finished `<style>` element.
#
# They are raw because there is exactly ONE copy of them and two sheets need to
# carry it: `PROFORMA_STYLES` splices both fragments back in at the character
# positions they have always occupied, so that page stays byte-for-byte what it
# was, and `DOCSHEET_STYLES` below wraps them for a sheet that does not load
# `PROFORMA_STYLES` — the RA bill, which may never import `proforma.py`.
#
# Two fragments and not one because the narrow-screen override sits further
# down that sheet, past the `.pi-note` rules. Joining them would have moved
# somebody else's CSS to tidy up mine.
#
# Both begin flush against the opening quotes (the trailing `\` suppresses the
# newline) so that splicing one in leaves the surrounding blank lines exactly
# as they were. A leading newline here is two extra bytes on two documents,
# which is precisely what the golden digests caught.
BANK_CSS = """\
  /* ── Bank block ───────────────────────────────────────────────────────
     A PI is a request for money; the remittance account is the operative
     detail, so it is framed rather than dropped into the terms as prose. */
  .quotation-doc .bank-box { border:var(--rule-box); margin-top:5mm; }
  .quotation-doc .bank-title {
    font-weight:700; font-size:var(--fs-md); padding:2px 6px;
    border-bottom:var(--rule);
  }
  .quotation-doc .bank-kv {
    display:grid; grid-template-columns:auto 1fr auto 1fr;
    gap:2px 6px; padding:4px 6px;
  }
  .quotation-doc .bank-kv .bk-l { color:var(--doc-soft); }
  .quotation-doc .bank-kv .bk-v { font-weight:700; overflow-wrap:anywhere; }
  .quotation-doc .bank-note {
    padding:2px 6px; border-top:var(--rule-hair); color:var(--doc-soft);
  }
"""

BANK_CSS_NARROW = """\
  @media screen and (max-width:760px){
    .quotation-doc .bank-kv { grid-template-columns:auto 1fr; }
  }
"""

# The rules for `sheet_open(title_band=…)`. Raw, and spliced into the one sheet
# that asks for a band — the same arrangement as `BANK_CSS` above and for the
# same reason: one copy of the rule, wherever it is needed.
BAND_CSS = """\
  /* ── Title band ───────────────────────────────────────────────────────
     The delivery challan is the one document whose title sits INSIDE the page
     frame and ABOVE the letterhead, and a `<caption>` is the only element a
     table gives us that can be in both places at once. See `sheet_open()` for
     why that mattered enough to use one. */
  .quotation-doc .page-frame > caption {
    caption-side:top; text-align:center; color:var(--doc-ink);
    font-size:var(--fs-lg); font-weight:700; letter-spacing:1.2px;
    padding:0 0 3px; text-decoration:underline;
  }
"""

DOCSHEET_STYLES = f"""
<style>
{BANK_CSS}{BANK_CSS_NARROW}</style>
"""


# =============================================================================
# THE PAGE FRAME AND THE LETTERHEAD
# =============================================================================

def _contact_bit(on: bool, label: str, value: str) -> str:
    """
    One optional `| Label: value` fragment of the letterhead contact line.

    `value` is escaped: all three callers pass a `/settings` field
    (`COMPANY_WEB`, `COMPANY_GSTIN`, `COMPANY_BRANCHES`), which is user text
    under Phase 3B's threat model. `label` is a literal at every call site.
    """
    if not on:
        return ""
    return "\n      {}".format(
        f'<span class="sep">|</span>{label}: {P.esc(value)}' if value else "")


def letterhead(show_web: bool = True, show_gstin: bool = True,
               show_branches: bool = False) -> str:
    """
    The company identity band, as the repeating `<thead>` of the page frame.

    `.page-frame` is an outer `<table>` and this is its header group, because
    `display:table-header-group` is the only mechanism a browser gives us to
    repeat a band on every printed page — `position:fixed` does not survive
    pagination in Chrome. ABOUT.md §5 has the rest of that story.

    Every value is read through the module (`B.COMPANY_ADDR`, never a
    from-import), so a setting saved at `/settings` reaches the paper without a
    restart. A blank field renders as `B.field()`'s amber chip rather than as
    nothing, which is how a half-configured identity stays visible.

    The three flags exist to preserve **observed** differences between the
    documents, not to offer a menu. Each one is a real difference somebody
    should eventually rule on:

    | | web | GSTIN | branches |
    |---|---|---|---|
    | tax invoice, RA bill | ✓ | ✓ | |
    | proforma invoice | ✓ | | ✓ |
    | purchase order | | ✓ | |

    - **GSTIN vs branches** is defensible and is kept: Rule 46 wants the
      supplier's GSTIN on the face of a tax invoice, and the RA bill is one.
      A proforma is not a statutory record and shows the branch list instead.
    - **`show_web=False` on the purchase order is not defensible and is not
      defended.** Every other sheet prints the web address and nothing anywhere
      records a reason. It reads as an omission, but correcting it would move a
      document this pass was under instruction to leave byte-identical, so it
      is preserved and reported instead (INTRODUCTION.md §5.6) — ABOUT.md §7
      gap 18. Drop the flag and the branch the day somebody rules on it.
    """
    return f"""  <thead><tr><td>
    <div class="lh">
      <div>
        <div class="lh-name">{B.name_html("lh-name-fire")}</div>
        <div class="lh-tag">&#8212; {P.esc(B.COMPANY_TAGLINE)} &#8212;</div>
        {f'<div class="lh-legal">{P.esc(B.COMPANY_LEGAL)}</div>' if B.COMPANY_LEGAL else ''}
      </div>
      <div class="lh-mark">{B.logo_img(56, doc=True)}</div>
    </div>
    <div class="lh-rule"></div>
    <div class="lh-addr">Registered Address: {B.field(B.COMPANY_ADDR, "registered address")}</div>
    <div class="lh-contact">
      Phone: {B.field(B.COMPANY_PHONE, "phone")}<span class="sep">|</span>
      Email: {B.field(B.COMPANY_EMAIL, "e-mail")}{
        _contact_bit(show_web, "Web", B.COMPANY_WEB)}{
        _contact_bit(show_gstin, "GSTIN", B.COMPANY_GSTIN)}{
        _contact_bit(show_branches, "Branches", B.COMPANY_BRANCHES)}
    </div>
  </td></tr></thead>"""


def foot_strip(text: str = "") -> str:
    """
    The band repeated at the foot of every printed page.

    Defaults to the house line — legal name and tagline. `boq.py` prints the
    schedule's reference here instead, which is why this takes a string rather
    than being baked in.
    """
    # `text` arrives escaped from its one caller (boq.py prints the schedule's
    # reference here); only the house fallback is escaped, so nothing is
    # escaped twice. `&middot;` is the house separator and stays outside.
    body = text or (f"{P.esc(B.COMPANY_LEGAL or B.COMPANY_NAME)} &middot; "
                    f"{P.esc(B.COMPANY_TAGLINE)}")
    return f"""  <tfoot><tr><td>
    <div class="lh-foot">{body}</div>
  </td></tr></tfoot>"""


def sheet_open(show_web: bool = True, show_gstin: bool = True,
               show_branches: bool = False, foot: str = "",
               title_band: str = None) -> str:
    """
    Everything from `<table class="page-frame">` down to the open of the body
    cell the document is written into. Pair it with `sheet_close()`.

    `title_band` renders the document's title **inside the page frame and above
    the letterhead**, which is where the client's own delivery challan puts it
    and nowhere else in this app does. It is a `<caption>` because that is the
    only child a `<table>` accepts before its `<thead>`: a `<div>` there is
    hoisted out of the table by every browser, and a second `<tr>` inside the
    `<thead>` would put the band inside the letterhead block that
    `tests/test_print_golden.py` requires to hash identically to the tax
    invoice's. The caption sits outside that block and the letterhead is
    untouched, which is the whole point.

    ⚠ It does **not** repeat on page two, and the letterhead does. A caption is
      painted once; only `display:table-header-group` repeats. That is a real
      difference and it is left as one — a challan is a one-page note, and
      making the band repeat would mean moving it into the `<thead>`, which is
      exactly what must not happen.

    **Defaults to `None`, and with `None` this function emits the bytes it
    always did** — the four existing callers render identically and the goldens
    prove it. The rule for `.page-frame > caption` is `BAND_CSS`, spliced into
    the sheet that asks for a band. A sheet that never passes one carries no
    rule for it.
    """
    band = ("" if title_band is None
            else f'  <caption class="sheet-band">{title_band}</caption>\n')
    return (f'  <table class="page-frame">\n'
            f'{band}'
            f'{letterhead(show_web, show_gstin, show_branches)}\n'
            f'\n'
            f'{foot_strip(foot)}\n'
            f'\n'
            f'  <tbody><tr><td>')


def sheet_close() -> str:
    """The close of the body cell and of the page frame."""
    return "  </td></tr></tbody>\n  </table>"


# =============================================================================
# THE PARTY BLOCK
# =============================================================================

def name_block(to_text: str) -> str:
    """
    A pre-joined address block with its first line set as the party's name.

    The first line is the party; everything under it is the address. Both the
    tax invoice's "To" and the purchase order's "To (Supplier)" are built this
    way, which is a fact worth having in one place: the buy side and the sell
    side put a **different party** in this box (ABOUT.md §5, `/purchase`), and
    the shape being shared is exactly what makes the roles worth naming at the
    call site.
    """
    lines = (to_text or "").strip().split("\n")
    if not (lines and lines[0].strip()):
        return ""
    out = f'<span class="dh-name">{P.esc(lines[0])}</span>'
    rest = "\n".join(lines[1:]).strip()
    if rest:
        out += f"\n{P.esc(rest)}"
    return out


def secondary_block(label: str, text: str) -> str:
    """
    The second party box under the first — *Ship To* on a sell-side document,
    *Deliver To* on a purchase order. Empty text renders nothing at all.
    """
    if not str(text or "").strip():
        return ""
    return ('<div class="dh-ship"><span class="dh-lbl">' + label + '</span>'
            f'<div class="dh-body">{P.esc(text)}</div></div>')


def party_block(label: str, body_html: str, extra_html: str,
                meta_col_1: str, meta_col_2: str) -> str:
    """
    The three-cell header grid: the party on the left, two columns of
    label/value meta on the right. Build the meta with `_meta()`.
    """
    return f"""    <div class="doc-header">
      <div class="dh-cell">
        <span class="dh-lbl">{label}</span>
        <div class="dh-body">{body_html}</div>
        {extra_html}
      </div>
      <div class="dh-cell">{meta_col_1}</div>
      <div class="dh-cell">{meta_col_2}</div>
    </div>"""


# =============================================================================
# THE ITEMS TABLE
# =============================================================================

# The eight columns the sell chain and the buy chain both print. Passed in
# rather than baked in, because the RA bill's set is different — a claim
# carries a previous quantity and a balance, and no part number.
SELL_COLUMNS = (("c-sno", "S.No"), ("c-partno", "Part No"),
                ("c-desc", "Description of Goods"), ("c-hsn", "HSN/SAC"),
                ("c-qty", "Qty"), ("c-unit", "Unit"),
                ("c-price", "Rate"), ("c-total", "Amount"))


def items_table(columns, rows_html: str) -> str:
    """
    The items-table shell. `columns` is a sequence of `(css_class, label)`;
    the rows are built by the caller, because what a row *says* is the one
    thing about this table that is not chrome.
    """
    heads = "\n".join(f'          <th class="{cls}">{label}</th>'
                      for cls, label in columns)
    return f"""    <div class="items-wrap">
      <table class="q-table">
        <thead><tr>
{heads}
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


# =============================================================================
# TOTALS
# =============================================================================
#
# Rows, not arithmetic. Every figure arrives already computed and already
# formatted; nothing here adds, rounds or decides a tax head.

def sum_row(label: str, amount: str, indent: int = 8) -> str:
    """One right-hand summary row — a subtotal, a tax line, a deduction."""
    pad = " " * indent
    return (f"\n{pad}<tr class=\"row-sum\">\n"
            f"{pad}  <td colspan=\"4\" class=\"sum-lbl\">{label}</td>\n"
            f"{pad}  <td class=\"c-qty\"></td><td class=\"c-unit\"></td>"
            f"<td class=\"c-price\"></td>\n"
            f"{pad}  <td class=\"c-total\">{amount}</td>\n"
            f"{pad}</tr>")


def total_row(label: str, qty: str, amount: str, indent: int = 4) -> str:
    """The closing row, carrying the document's total quantity and value."""
    pad = " " * indent
    return (f"\n{pad}<tr class=\"row-total row-sum\">\n"
            f"{pad}  <td colspan=\"4\" class=\"sum-lbl\">{label}</td>\n"
            f"{pad}  <td class=\"c-qty\">{qty}</td>\n"
            f"{pad}  <td class=\"c-unit\"></td><td class=\"c-price\"></td>\n"
            f"{pad}  <td class=\"c-total\">{amount}</td>\n"
            f"{pad}</tr>")


def amount_words(label: str, value: float) -> str:
    """
    The figure restated in words, in the Indian crore/lakh system.

    `_amount_in_words()` supplies its own `INR ` prefix — do not add another.
    The RA bill printed "INR INR Nine Lakh …" until that was noticed.
    """
    return f'    <div class="amount-words">{label} : {_amount_in_words(value)}</div>'


# =============================================================================
# BANK AND SIGNATURE
# =============================================================================

def bank_block(note_html: str = "") -> str:
    """
    The remittance account, from `branding.BANK_*`.

    Blank fields render as amber `B.field()` chips exactly as the statutory
    block does, so an incomplete document cannot go out looking finished.

    ⚠ **Not every document should carry one.** A quotation is an offer and a
      tax invoice records a supply that was normally already paid against the
      proforma; publishing the account number wider than it needs to go is a
      fraud surface, and ABOUT.md §6 states that as the rule. This is here for
      the documents that genuinely ask for money — the proforma invoice and
      the RA bill.
    """
    note = f'\n    <div class="bank-note">{note_html}</div>' if note_html else ""
    return f"""
  <div class="bank-box">
    <div class="bank-title">Bank Details for Remittance</div>
    <div class="bank-kv">
      <span class="bk-l">Bank</span>
      <span class="bk-v">{B.field(B.BANK_NAME, "bank name")}</span>
      <span class="bk-l">A/C Name</span>
      <span class="bk-v">{B.field(B.BANK_ACCOUNT_NAME, "account name")}</span>
      <span class="bk-l">A/C No.</span>
      <span class="bk-v">{B.field(B.BANK_ACCOUNT_NO, "account number")}</span>
      <span class="bk-l">IFSC</span>
      <span class="bk-v">{B.field(B.BANK_IFSC, "IFSC code")}</span>
      <span class="bk-l">Branch</span>
      <span class="bk-v">{B.field(B.BANK_BRANCH, "branch")}</span>
      <span class="bk-l">GSTIN</span>
      <span class="bk-v">{B.field(B.COMPANY_GSTIN, "GSTIN")}</span>
    </div>{note}
  </div>"""


def sig_block(branch: str = "", signatory: str = "",
              computer_generated: bool = False,
              left_html: str = None) -> str:
    """
    The statutory identifiers and the signature panel.

    `branch` and `signatory` are the document's own stored values; both fall
    back to the company defaults, and the caller escapes them because they came
    off a record.

    `left_html` replaces the GSTIN/PAN grid on the left of the panel. It exists
    for the delivery challan, which prints **"Name & Signature of Receiver"**
    there instead — a challan is handed over and signed for on arrival, and the
    person signing is the consignee rather than us. Every other document wants
    the statutory pair, so it **defaults to `None` and emits the bytes it
    always did**; the goldens prove that.
    """
    # `branch` and `signatory` arrive escaped from the caller (the docstring
    # above says so, and every caller does it), so only the fallbacks are
    # escaped here. `COMPANY_SIGNATORY` is a `/settings` field and is therefore
    # user text; `COMPANY_NAME` deliberately is not (branding.py §1c).
    comp = branch or B.COMPANY_NAME
    who = signatory or P.esc(B.COMPANY_SIGNATORY)
    note = ('\n  <div class="sig-note">This is a Computer Generated Document, '
            'no signature required</div>') if computer_generated else ""
    left = left_html if left_html is not None else f"""<div class="sig-kv">
      <span>GSTIN</span><span>: <b>{B.field(B.COMPANY_GSTIN, "GSTIN")}</b></span>
      <span>PAN No.</span><span>: <b>{B.field(B.COMPANY_PAN, "PAN")}</b></span>
    </div>"""
    return f"""  <div class="sig-block">
    {left}
    <div class="sig-right">
      <div class="sig-for">For {comp}</div>
      <div class="sig-name">{who}</div>
    </div>
  </div>{note}"""
