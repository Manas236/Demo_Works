"""
quotation.py — Quotation Generation Module  (v4 – fully fixed)
==============================================================
Blueprint : quotation_bp
Mounted at : /quotation  (registered in app.py)

Routes
------
  GET  /quotation             — list all saved quotations
  GET  /quotation/create      — full quotation form (CRM-style)
  POST /quotation/create      — validate → build line_items → save → redirect to view
  GET  /quotation/view/<id>   — rendered quotation document
"""

import json
import uuid
from datetime import date as _date
from flask import Blueprint, render_template_string, request, redirect, url_for

import branding as B
import pipeline as P
from address import INDIAN_STATES, picker_options, picker_payload
from dashboard import BASE_STYLES, _nav
from store import STORE

# ── Blueprint ──────────────────────────────────────────────────────────────────
quotation_bp = Blueprint("quotation", __name__, url_prefix="/quotation")


# =============================================================================
# COMPANY IDENTITY
# =============================================================================
# Owned by branding.py — edit it there, not here. Re-exported under the old
# names so the document templates below stay readable.
COMPANY_NAME      = B.COMPANY_NAME
COMPANY_LEGAL     = B.COMPANY_LEGAL
COMPANY_TAGLINE   = B.COMPANY_TAGLINE
COMPANY_ADDR      = B.COMPANY_ADDR
COMPANY_PHONE     = B.COMPANY_PHONE
COMPANY_EMAIL     = B.COMPANY_EMAIL
COMPANY_WEB       = B.COMPANY_WEB
COMPANY_GSTIN     = B.COMPANY_GSTIN
COMPANY_PAN       = B.COMPANY_PAN
COMPANY_BRANCHES  = B.COMPANY_BRANCHES
COMPANY_SIGNATORY = B.COMPANY_SIGNATORY


# =============================================================================
# HELPERS — amount in words (Indian system)
# =============================================================================

def _amount_in_words(amount: float) -> str:
    _ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    _tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _two(n):
        if n == 0:  return ""
        if n < 20:  return _ones[n]
        t = _tens[n // 10]; o = _ones[n % 10]
        return t + (" " + o if o else "")

    def _three(n):
        if n == 0:  return ""
        if n >= 100:
            rest = _two(n % 100)
            return _ones[n // 100] + " Hundred" + (" " + rest if rest else "")
        return _two(n)

    n = int(round(amount))
    if n == 0:  return "INR Zero Only"
    parts = []
    cr = n // 10_000_000;  n %= 10_000_000
    lk = n // 100_000;     n %= 100_000
    th = n // 1_000;       n %= 1_000
    if cr: parts.append(_three(cr) + " Crore")
    if lk: parts.append(_three(lk) + " Lakh")
    if th: parts.append(_three(th) + " Thousand")
    if n:  parts.append(_three(n))
    return "INR " + " ".join(parts) + " Only"


def _tax_lines(subtotal: float, tax_type: str,
               cgst_rate: float = 0, sgst_rate: float = 0,
               igst_rate: float = 0, vat_rate: float = 0) -> dict:
    """
    Compute tax amounts for each applicable head.
    Returns dict of { head_name: amount, ..., "total": sum }.
    Always stores the rates used so the view can display them.
    """
    if tax_type == "cgst_sgst":
        c = subtotal * (cgst_rate / 100.0)
        s = subtotal * (sgst_rate / 100.0)
        return {"CGST": c, "SGST": s, "total": c + s,
                "cgst_rate": cgst_rate, "sgst_rate": sgst_rate}
    if tax_type == "igst":
        t = subtotal * (igst_rate / 100.0)
        return {"IGST": t, "total": t, "igst_rate": igst_rate}
    if tax_type == "vat":
        t = subtotal * (vat_rate / 100.0)
        return {"VAT": t, "total": t, "vat_rate": vat_rate}
    return {"total": 0.0}


# =============================================================================
# DYNAMIC T&C BUILDER
# =============================================================================

def _build_tnc(q: dict) -> list:
    terms = []

    delivery = (q.get("delivery_terms") or "").strip()
    terms.append(
        f"The above prices are {delivery} assembled unpacked condition."
        if delivery else
        "The above prices are ex our works, assembled unpacked condition."
    )

    tax_type = q.get("tax_type", "exempt")
    tax_info = q.get("tax_info", {})
    if tax_type == "cgst_sgst":
        cr = tax_info.get("cgst_rate", 0)
        sr = tax_info.get("sgst_rate", 0)
        total_gst = cr + sr
        terms.append(
            f"GST – CGST @ {cr}% + SGST @ {sr}% = {total_gst}% applicable on all items "
            f"unless otherwise stated. Battery attracts 28% GST."
        )
    elif tax_type == "igst":
        ir = tax_info.get("igst_rate", 0)
        terms.append(
            f"IGST @ {ir}% applicable on all items unless otherwise stated. "
            f"Battery attracts 28% IGST."
        )
    elif tax_type == "vat":
        vr = tax_info.get("vat_rate", 0)
        terms.append(f"VAT @ {vr}% applicable on all items unless otherwise stated.")
    else:
        terms.append("Prices are exclusive of taxes. GST / VAT as applicable at the time of delivery.")

    delivery_date = (q.get("delivery_date") or "").strip()
    if delivery_date:
        terms.append(f"Delivery by {delivery_date} from the date of clear PO with advance.")
    else:
        terms.append("Delivery – 3–4 weeks from the date of clear PO with advance.")

    payment = (q.get("payment_terms") or "").strip()
    if payment:
        terms.append(
            f"Payment – {payment}. Delivery schedule will commence from Date of receipt of "
            f"Advance / Date of receipt of approved Documents / Date of Purchase Order "
            f"whichever is later."
        )
    else:
        terms.append(
            "Payment – 30% advance with PO, balance against Proforma Invoice prior to Delivery."
        )

    dispatch = (q.get("dispatch_through") or "").strip()
    if dispatch and dispatch.lower() not in ("in clients scope", "self pickup"):
        terms.append(f"Transportation – Via {dispatch}, charges extra unless included in price.")
    elif dispatch.lower() in ("in clients scope", "self pickup"):
        terms.append("Transportation – In client's scope.")
    else:
        terms.append("Transportation – To your a/c.")

    vdays = (q.get("validity_days") or "").strip()
    terms.append(
        f"Validity – {vdays} days from the date of offer submitted."
        if vdays else
        "Validity – 15 days from the date of offer submitted."
    )

    # ── Standing clauses ──────────────────────────────────────────────────────
    # NOTE: these are the trade terms that print on every quotation. They have
    # been written generically for a fire-protection contractor; have them
    # checked once against Samruddhi Fire's own commercial policy (warranty
    # period, commissioning scope, AMC) before the first customer sees them.
    terms += [
        "Scope – Supply only, unless erection, installation or commissioning is explicitly "
            "listed in the item description above.",
        "Any commissioning call will be given minimum 5 working days in advance, post "
            "check-list confirmation. Site readiness check-list to be complied with 100%.",
        "First visit for supervision of commissioning will be done free of cost after "
            "confirmation of site readiness. Further visits arising from site non-readiness "
            "will be charged on a per man-day basis.",
        "Any short supply must be brought to our notice within 3 working days of receipt of "
            "material. Claims raised later cannot be accepted for part replacement.",
        "Where an item requires transport to an authorised service centre for rectification "
            "within the warranty period, to & fro freight will be borne by the customer.",
        "Warranty – 12 months from the date of invoice or 12 months from the date of "
            "commissioning, whichever is earlier. Bought-out items carry only the original "
            "manufacturer's warranty. No warranty on electronic components.",
        "Equipment supplied is warranted for defects in material and workmanship only. "
            "Damage from incorrect installation, power fluctuation, dry running, "
            "or lack of prescribed maintenance is not covered.",
        "Fire-fighting equipment supplied conforms to the relevant IS / BIS specification "
            "quoted against each item. Statutory approvals from the local fire authority are "
            "in the customer's scope unless stated otherwise.",
        "Refilling, servicing and periodic testing after the warranty period are chargeable "
            "and can be covered under a separate AMC.",
        "Standard Force Majeure clause is applicable.",
        "A debit note of Rs 900.00 + GST will be raised each time a payment cheque is "
            "returned unpaid on presentation, and must be cleared before the next supply.",
        "Any statutory deviation in taxes & duties at the time of delivery will be to the "
            "customer's account.",
    ]

    return terms


# =============================================================================
# HELPERS — form / catalog
# =============================================================================

def _next_ref() -> str:
    n = len(STORE["quotations"]) + 1
    return f"QT-{n:04d}"


def _fmt_qty(q: float) -> str:
    return str(int(q)) if q == int(q) else f"{q:g}"


def _inr(v: float, dec: int = 2) -> str:
    """
    Money in the Indian digit grouping — 13,15,000.00, not 1,315,000.00.

    Python's ``{:,}`` groups in thousands, which is the one number format an
    Indian customer reads as a typo. Every figure on the printed document goes
    through here. No currency symbol: the document says INR once, in the
    amount-in-words line, exactly as the trade does it.
    """
    v = float(v or 0.0)
    neg = v < 0
    ip, _, fp = f"{abs(v):.{dec}f}".partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        ip = ",".join(groups + [tail])
    out = ip + ("." + fp if dec else "")
    return ("-" + out) if neg else out


def _meta(label: str, val: str) -> str:
    """
    One label/value pair in the document header.

    A blank value renders as an empty line, never as an em-dash — a grid of
    "—" reads as an unfinished document. ``.m-val`` carries a min-height so
    the rows stay on the same rhythm whether or not they are filled.
    """
    return (f'<div class="mrow"><span class="m-lbl">{label}</span>'
            f'<span class="m-val">{(val or "").strip()}</span></div>')


def _product_catalog_json() -> str:
    catalog: dict = {}
    for pid, p in STORE["products"].items():
        resolved_children = []
        for c in p.get("children", []):
            cp = STORE["products"].get(c["product_id"])
            if cp:
                resolved_children.append({
                    "pid":      c["product_id"],
                    "qty":      c["qty"],
                    "name":     cp["name"],
                    "part_no":  cp["part_no"],
                    "unit":     cp["unit"],
                    "price":    cp["base_price"],
                    "type":     cp.get("type", "standalone"),
                    "hsn":      cp.get("hsn", ""),
                })
        catalog[pid] = {
            "name":     p["name"],
            "part_no":  p["part_no"],
            "unit":     p["unit"],
            "price":    p["base_price"],
            "type":     p.get("type", "standalone"),
            "hsn":      p.get("hsn", ""),
            "children": resolved_children,
        }
    return json.dumps(catalog)


def _process_selections(data: list) -> list:
    line_items = []
    for item in data:
        p = STORE["products"].get(item.get("pid", ""))
        if not p:
            continue
        qty        = float(item.get("qty") or 1)
        price      = float(item.get("price") if item.get("price") is not None else p["base_price"])
        show_price = bool(item.get("show_price", True))
        eff_price  = price if show_price else 0.0

        line_items.append({
            "type":    "assembly" if p.get("type") == "assembly" else "item",
            "name":    p["name"],
            "part_no": p["part_no"],
            "hsn":     p.get("hsn", ""),
            "qty":     qty,
            "unit":    p["unit"],
            "price":   eff_price,
            "total":   eff_price * qty,
            "depth":   0,
        })

        for comp in item.get("components", []):
            cp = STORE["products"].get(comp.get("pid", ""))
            if not cp:
                continue
            cqty   = float(comp.get("qty") or 1)
            cprice = float(comp.get("price") if comp.get("price") is not None else 0)
            cshow  = bool(comp.get("show_price", False))
            ceff   = cprice if cshow else 0.0

            line_items.append({
                "type":    "assembly" if cp.get("type") == "assembly" else "item",
                "name":    cp["name"],
                "part_no": cp["part_no"],
                "hsn":     cp.get("hsn", ""),
                "qty":     cqty,
                "unit":    cp["unit"],
                "price":   ceff,
                "total":   ceff * cqty,
                "depth":   1,
            })

    return line_items


# =============================================================================
# CSS — create / list pages
# =============================================================================

QUOTATION_STYLES = """
<style>
  .page-top {
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:1.75rem; flex-wrap:wrap; gap:1rem;
  }
  .page-top h1 { font-size:1.5rem; font-weight:700; letter-spacing:-.4px; }
  .page-top h1 span { color:var(--brand); }

  .alert {
    padding:.8rem 1.1rem; border-radius:8px; font-size:.87rem;
    font-weight:500; margin-bottom:1.4rem;
    display:flex; align-items:center; gap:.5rem;
  }
  .alert-error   { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
  .alert-success { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }

  .table-wrap {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow-sm);
  }
  table { width:100%; border-collapse:collapse; font-size:.88rem; }
  thead { background:var(--bg); border-bottom:1px solid var(--border); }
  th {
    padding:.8rem 1.1rem; text-align:left; font-size:.73rem;
    font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
  }
  td { padding:.9rem 1.1rem; border-bottom:1px solid var(--border); vertical-align:middle; }
  tbody tr:last-child td { border-bottom:none; }
  tbody tr:hover { background:#f8fafc; }
  .td-ref   { font-family:'SFMono-Regular',Consolas,monospace; font-weight:700; color:var(--brand); }
  .td-cust  { font-weight:600; }
  .td-total { font-weight:700; color:var(--brand); }
  .td-muted { font-size:.82rem; color:var(--muted); }
  .btn-view {
    font-size:.75rem; font-weight:600; color:var(--brand); background:var(--brand-lt);
    border:1px solid #c7d2fe; border-radius:6px; padding:.28rem .7rem;
    text-decoration:none; display:inline-block; transition:background .13s;
  }
  .btn-view:hover { background:#c7d2fe; }
  .empty-state {
    text-align:center; padding:3.5rem 2rem; color:var(--muted);
    background:var(--surface); border:1px dashed var(--border); border-radius:var(--radius);
  }

  .form-section {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.6rem 1.9rem;
    box-shadow:var(--shadow-sm); margin-bottom:1.4rem;
  }
  .section-title {
    font-size:.73rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.09em; color:var(--brand); margin-bottom:1.2rem;
    display:flex; align-items:center; gap:.4rem;
    padding-bottom:.6rem; border-bottom:1px solid var(--border);
  }

  .fg2 { display:grid; grid-template-columns:1fr 1fr;            gap:.9rem; }
  .fg3 { display:grid; grid-template-columns:1fr 1fr 1fr;        gap:.9rem; }
  .fg4 { display:grid; grid-template-columns:1fr 1fr 1fr 1fr;    gap:.9rem; }
  .fg5 { display:grid; grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:.9rem; }
  .span2 { grid-column:span 2; }
  .span3 { grid-column:span 3; }
  .span4 { grid-column:span 4; }
  .span-all { grid-column:1/-1; }

  .form-group { display:flex; flex-direction:column; gap:.3rem; }

  /* ── Address book picker (Bill To / Ship To) ─────────────────────── */
  .addr-pick {
    display:flex; align-items:center; gap:.6rem; flex-wrap:wrap;
    margin-bottom:.8rem; padding-bottom:.8rem;
    border-bottom:1px dashed var(--border);
  }
  .addr-pick select {
    flex:1 1 260px; min-width:0;
    font-family:var(--font); font-size:.85rem; padding:.5rem .65rem;
    border:1px solid var(--border); border-radius:8px;
    background:var(--bg); color:var(--text);
  }
  .addr-pick select:focus { outline:none; border-color:var(--brand); background:var(--surface); }
  .addr-pick-link {
    font-size:.76rem; font-weight:600; color:var(--brand);
    text-decoration:none; white-space:nowrap;
  }
  .addr-pick-link:hover { text-decoration:underline; }

  label {
    font-size:.72rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.07em; color:var(--muted);
  }
  input[type="text"],
  input[type="date"],
  input[type="number"],
  input[type="email"],
  input[type="tel"],
  textarea,
  select {
    font-family:var(--font); font-size:.88rem; color:var(--text);
    background:var(--bg); border:1.5px solid var(--border);
    border-radius:7px; padding:.52rem .8rem; width:100%;
    transition:border-color .14s, box-shadow .14s; outline:none;
  }
  input:focus, textarea:focus, select:focus {
    border-color:var(--brand);
    box-shadow:0 0 0 3px rgba(79,70,229,.1); background:#fff;
  }
  input[type="checkbox"] { width:auto; cursor:pointer; accent-color:var(--brand); }
  textarea { resize:vertical; min-height:72px; }

  .check-row { display:flex; align-items:center; gap:.5rem; padding-top:.35rem; }
  .check-row label { text-transform:none; font-size:.86rem; font-weight:500; color:var(--text); letter-spacing:0; }

  .readonly-field {
    font-family:'SFMono-Regular',Consolas,monospace; font-size:.88rem;
    color:var(--brand); background:#f5f3ff; border:1.5px solid #c7d2fe;
    border-radius:7px; padding:.52rem .8rem; font-weight:700;
  }

  .addr-sub {
    border:1px solid var(--border); border-radius:8px;
    padding:1rem 1.1rem; margin-top:.75rem; background:#fafafa;
  }
  .addr-sub-title {
    font-size:.7rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.08em; color:var(--muted); margin-bottom:.8rem;
  }
  .ship-opts { display:flex; gap:1.2rem; margin-bottom:.7rem; flex-wrap:wrap; }
  .ship-opt  { display:flex; align-items:center; gap:.35rem; font-size:.84rem; font-weight:500; }

  /* Tax section */
  .tax-options { display:flex; gap:1.4rem; flex-wrap:wrap; margin-bottom:1rem; }
  .tax-opt { display:flex; align-items:center; gap:.4rem; font-size:.86rem; font-weight:500; cursor:pointer; }
  .tax-opt input[type="radio"] { accent-color:var(--brand); width:auto; }
  .tax-panel {
    display:none;
    align-items:center; flex-wrap:wrap; gap:.75rem;
    padding:.75rem 1rem; background:#f8f9ff;
    border:1px solid #e0e4ff; border-radius:8px; margin-top:.1rem;
  }
  .tax-panel.active { display:flex; }
  .tax-input-group { display:flex; flex-direction:column; gap:.3rem; }
  .tax-field-lbl {
    font-size:.68rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.07em; color:var(--muted);
  }
  .tax-field-inp {
    font-family:var(--font); font-size:1rem; font-weight:700; color:var(--brand);
    background:#fff; border:2px solid var(--brand); border-radius:7px;
    padding:.4rem .6rem; width:90px; text-align:center; outline:none;
    transition:border-color .14s, box-shadow .14s;
  }
  .tax-field-inp:focus { box-shadow:0 0 0 3px rgba(79,70,229,.15); }
  .tax-sep { font-size:1.3rem; font-weight:700; color:var(--muted); align-self:flex-end; padding-bottom:.45rem; }
  .tax-total-display {
    font-family:var(--font); font-size:1rem; font-weight:800; color:#166534;
    background:#f0fdf4; border:2px solid #86efac; border-radius:7px;
    padding:.4rem .7rem; min-width:90px; text-align:center;
  }
  .tax-hint { font-size:.78rem; color:var(--muted); align-self:center; max-width:260px; line-height:1.45; }

  /* Product picker */
  .picker-bar {
    display:grid; grid-template-columns:1fr 90px auto;
    gap:.6rem; align-items:end; margin-bottom:.75rem;
  }
  .picker-bar select, .picker-bar input { margin:0; }

  .add-error {
    font-size:.8rem; color:#b91c1c; background:#fef2f2;
    border:1px solid #fecaca; border-radius:6px;
    padding:.3rem .8rem; margin-bottom:.5rem; display:none;
  }

  #sel-container { display:flex; flex-direction:column; gap:.5rem; }
  #empty-notice {
    text-align:center; padding:1.6rem 1rem; color:var(--muted);
    font-size:.86rem; border:1.5px dashed var(--border); border-radius:8px; background:#fafafa;
  }

  .sel-root {
    border:1px solid var(--border); border-radius:9px;
    background:var(--bg); overflow:hidden;
    transition:border-color .13s;
  }
  .sel-root:hover { border-color:#a5b4fc; }

  .sel-root-head {
    display:grid; grid-template-columns:1fr auto;
    gap:.6rem; padding:.55rem .85rem; align-items:center;
  }
  .sel-root-info .sel-name  { font-size:.88rem; font-weight:700; color:var(--text); }
  .sel-root-info .sel-pno   { font-size:.72rem; color:var(--muted); font-family:'SFMono-Regular',Consolas,monospace; margin-top:1px; }
  .badge-asm {
    display:inline-block; font-size:.62rem; font-weight:700;
    text-transform:uppercase; letter-spacing:.06em;
    background:#dbeafe; color:#1d4ed8; border-radius:10px; padding:.1rem .4rem; margin-left:.4rem;
  }

  .sel-root-ctrl { display:flex; gap:.5rem; align-items:center; flex-wrap:wrap; }
  .ctrl-block { display:flex; flex-direction:column; gap:.15rem; align-items:center; }
  .ctrl-lbl   { font-size:.65rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
  .ctrl-input {
    font-family:var(--font); font-size:.86rem; color:var(--text);
    background:#fff; border:1.5px solid var(--border); border-radius:6px;
    padding:.35rem .5rem; outline:none; transition:border-color .14s;
  }
  .ctrl-input:focus { border-color:var(--brand); }
  .ctrl-input.w-qty   { width:70px; text-align:center; }
  .ctrl-input.w-price { width:110px; text-align:right; }
  .ctrl-check { accent-color:var(--brand); width:auto !important; cursor:pointer; }

  .btn-expand {
    font-family:var(--font); font-size:.74rem; font-weight:600;
    color:var(--brand); background:var(--brand-lt); border:1px solid #c7d2fe;
    border-radius:6px; padding:.3rem .65rem; cursor:pointer; white-space:nowrap;
    transition:background .13s;
  }
  .btn-expand:hover { background:#c7d2fe; }
  .btn-rm {
    font-family:var(--font); font-size:.96rem; font-weight:700;
    color:#ef4444; background:#fef2f2; border:1px solid #fecaca;
    border-radius:6px; cursor:pointer; width:30px; height:30px;
    display:flex; align-items:center; justify-content:center;
    flex-shrink:0; transition:background .13s;
  }
  .btn-rm:hover { background:#fee2e2; }

  .comp-area {
    border-top:1px dashed var(--border);
    background:#f8f9ff; padding:.5rem .85rem .6rem 1.5rem;
  }
  .comp-row {
    display:grid; grid-template-columns:1fr auto;
    gap:.5rem; align-items:center;
    padding:.35rem .5rem; border-radius:7px;
    border:1px solid #e8eaff; background:#fff; margin-bottom:.35rem;
  }
  .comp-row:last-of-type { margin-bottom:.5rem; }
  .comp-info .comp-name { font-size:.83rem; font-weight:600; color:var(--text); }
  .comp-info .comp-pno  { font-size:.7rem; color:var(--muted); font-family:'SFMono-Regular',Consolas,monospace; }

  .comp-ctrl { display:flex; gap:.4rem; align-items:center; flex-wrap:wrap; }

  .btn-add-comp {
    font-family:var(--font); font-size:.75rem; font-weight:600;
    color:#166534; background:#f0fdf4; border:1px dashed #86efac;
    border-radius:6px; padding:.3rem .75rem; cursor:pointer;
    transition:background .13s; display:inline-flex; align-items:center; gap:.3rem;
    margin-top:.25rem;
  }
  .btn-add-comp:hover { background:#dcfce7; }

  .comp-picker { display:flex; gap:.4rem; align-items:center; margin-top:.4rem; flex-wrap:wrap; }
  .comp-picker select { flex:1; min-width:180px; font-size:.82rem; padding:.35rem .6rem; }
  .comp-picker input  { width:70px; text-align:center; font-size:.82rem; padding:.35rem .5rem; }

  .form-actions { display:flex; gap:.75rem; margin-top:1.4rem; align-items:center; }

  /* ── Proforma links ───────────────────────────────────────────────────
     Lives here rather than in proforma.py because both sides need it: the
     deal panel lists the PIs raised against a quotation, and the convert page
     warns about the ones already issued. Every page that renders a chip
     already loads QUOTATION_STYLES. */
  .pi-block { margin-top:1.1rem; padding-top:.9rem; border-top:1px dashed var(--border); }
  .pi-lbl {
    font-size:.68rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.07em; color:var(--muted);
  }
  .pi-strip { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.5rem; }
  .pi-chip {
    font-size:.76rem; font-weight:600; text-decoration:none;
    border:1px solid var(--border); border-radius:8px;
    padding:.25rem .6rem; background:var(--surface); color:var(--navy);
    transition:border-color .13s;
  }
  .pi-chip:hover { border-color:var(--navy); }

  @media(max-width:800px){
    .fg2,.fg3,.fg4,.fg5 { grid-template-columns:1fr 1fr; }
    .span3,.span4,.span-all { grid-column:1/-1; }
    .picker-bar { grid-template-columns:1fr; }
    .sel-root-ctrl { gap:.35rem; }
    td,th { padding:.6rem .75rem; }
    .col-h { display:none; }
  }
  @media(max-width:520px){
    .fg2,.fg3,.fg4,.fg5 { grid-template-columns:1fr; }
  }
</style>
"""


# =============================================================================
# CSS — document view
# =============================================================================

VIEW_DOC_STYLES = """
<style>
  /* ══════════════════════════════════════════════════════════════════════
     THE PRINTED QUOTATION

     Four rules. They are short so that they stay followed — the previous
     version of this sheet had 3 font families, 9 type sizes and 11 border
     greys, and read as an accident rather than a document.

       1. ONE typeface — Arial. Money columns get `tabular-nums` instead of
          a second, monospaced family; digits line up without the switch.
       2. FIVE sizes — --fs-xs … --fs-xl. Nothing in between.
       3. THREE rules — --rule-box (heavy frame), --rule (cell grid),
          --rule-hair (soft internal separator). No other border weight.
       4. Emphasis is WEIGHT and RULE, never fill. The table head is the one
          background that carries meaning, and print explicitly forces it
          through; with backgrounds off the document is unchanged otherwise.

     Layout is in mm, because the output is A4 — not rem, which is a 16px
     screen unit and has no relationship to a pt-sized page.
     ══════════════════════════════════════════════════════════════════════ */

  .doc-outer { max-width:210mm; margin:0 auto; }

  .screen-acts {
    display:flex; gap:.75rem; margin-bottom:1.2rem; flex-wrap:wrap;
    align-items:center; justify-content:space-between;
  }

  .quotation-doc {
    --doc-ink:   #000;
    --doc-soft:  #454545;
    --doc-faint: #6f6f6f;
    --rule-box:  1.1pt solid #000;
    --rule:      0.5pt solid #000;
    --rule-hair: 0.5pt solid #a8a8a8;
    --fs-xs: 6.5pt;
    --fs-sm: 7.5pt;
    --fs-md: 8.5pt;
    --fs-lg: 12pt;
    --fs-xl: 17pt;

    background:#fff; color:var(--doc-ink);
    font-family:Arial, Helvetica, sans-serif;
    font-size:var(--fs-sm); line-height:1.35;
    text-transform:none; letter-spacing:normal;
    /* On screen, mimic the A4 margin so what you see matches what prints. */
    padding:9mm 8mm 7mm;
    border:1px solid #c5c5c5; box-shadow:0 4px 32px rgba(0,0,0,.10);
  }

  /* ── Page frame ───────────────────────────────────────────────────────
     The letterhead and the foot strip live in <thead>/<tfoot> of an outer
     table. That is the only mechanism a browser gives us for repeating a
     band on every printed page — `position:fixed` does not survive
     pagination in Chrome. On screen it is an ordinary one-row table.

     Because it IS a <table>, the app's bare `table {}` / `thead {}` rules
     land on it and are inherited by the whole document. Neutralise them here,
     or the address block silently renders at the app's .88rem and the
     letterhead picks up the canvas tint. */
  .page-frame { width:100%; border-collapse:collapse;
                font-size:var(--fs-sm); background:none; }
  .page-frame > thead,
  .page-frame > tfoot { background:none; border:none; }
  .page-frame > thead > tr > td,
  .page-frame > tfoot > tr > td,
  .page-frame > tbody > tr > td { padding:0; border:none; background:none; }

  /* ── Letterhead ───────────────────────────────────────────────────── */
  .lh { display:flex; justify-content:space-between; align-items:flex-end; gap:8mm; }
  /* Two-tone exactly as the signboard is painted: SAMRUDDHI red, FIRE navy. */
  .lh-name      { font-size:var(--fs-xl); font-weight:700; color:var(--brand); letter-spacing:.6px; line-height:1.1; }
  .lh-name-fire { color:var(--navy); }
  .lh-tag       { font-size:var(--fs-sm); color:var(--doc-soft); letter-spacing:.3px; margin-top:1px; }
  .lh-legal     { font-size:var(--fs-xs); color:var(--doc-faint); margin-top:1px; }
  .lh-mark      { flex-shrink:0; }
  .lh-rule      { border-top:var(--rule-box); margin-top:3px; }
  .lh-addr      { font-size:var(--fs-xs); color:var(--doc-soft); padding-top:3px; }
  .lh-contact   { font-size:var(--fs-sm); color:var(--navy); font-weight:700; padding-bottom:4px; }
  .lh-contact .sep { color:#9a9a9a; font-weight:400; padding:0 3px; }
  .lh-foot { border-top:var(--rule-hair); margin-top:4mm; padding-top:2px;
             font-size:var(--fs-xs); color:var(--doc-faint); }

  /* ── The framed document body ─────────────────────────────────────── */
  .doc-box   { border:var(--rule-box); }
  .doc-title { text-align:center; font-size:var(--fs-lg); font-weight:700;
               letter-spacing:1.2px; padding:3px 0; border-bottom:var(--rule-box); }

  .doc-header { display:grid; grid-template-columns:42% 29% 29%; border-bottom:var(--rule-box); }
  .dh-cell            { padding:4px 6px; min-width:0; }
  .dh-cell + .dh-cell { border-left:var(--rule); }

  .dh-lbl  { font-size:var(--fs-sm); color:var(--doc-soft); display:block; }
  .dh-name { font-weight:700; }
  .dh-body { font-size:var(--fs-sm); white-space:pre-wrap; overflow-wrap:break-word; }
  .dh-ship { margin-top:4px; padding-top:3px; border-top:var(--rule-hair); }

  .mrow  { margin-bottom:2px; }
  .m-lbl { display:block; font-size:var(--fs-sm); color:var(--doc-soft); line-height:1.25; }
  /* min-height keeps the two meta columns on the same rhythm when a value is
     blank. A blank prints as a blank — never as an em-dash. */
  .m-val { display:block; font-size:var(--fs-sm); font-weight:700; line-height:1.3; min-height:1.3em; }

  /* ── Items table ──────────────────────────────────────────────────── */
  /* NOTE: BASE_STYLES / PRODUCT_STYLES / QUOTATION_STYLES all ship bare
     `th`, `td` and `li` rules for the on-screen app, and they load either
     side of this sheet. A bare `th` beats nothing, so every property the
     document cares about is declared here explicitly rather than left to
     inherit — otherwise the column heads come out uppercase and grey. */
  .items-wrap { overflow-x:auto; }
  .q-table { width:100%; border-collapse:collapse; table-layout:fixed; font-size:var(--fs-sm); }
  .q-table th {
    background:#c9c9c9; border:var(--rule); padding:3px 4px;
    font-weight:700; text-align:center;      /* every head centred — one rule */
    font-family:inherit; font-size:var(--fs-sm); color:var(--doc-ink);
    text-transform:none; letter-spacing:normal; white-space:normal;
  }
  .q-table td {
    border:var(--rule); padding:3px 4px; vertical-align:top;
    font-family:inherit; font-size:var(--fs-sm); color:var(--doc-ink);
    text-transform:none; letter-spacing:normal;
  }

  /* Hierarchy by weight, not by fill — so it survives a printer with
     background graphics switched off. */
  .row-assembly .c-desc  { font-weight:700; }
  .row-assembly .c-price,
  .row-assembly .c-total { font-weight:700; }
  .indent-1 { padding-left:10px !important; }
  .indent-2 { padding-left:20px !important; }

  .c-sno    { width:9mm;  text-align:center; }
  .c-partno { width:24mm; text-align:center; font-size:var(--fs-xs); overflow-wrap:anywhere; }
  .c-desc   { text-align:left; overflow-wrap:break-word; }
  .c-hsn    { width:16mm; text-align:center; font-size:var(--fs-xs); }
  .c-qty    { width:12mm; text-align:right; }
  .c-unit   { width:11mm; text-align:center; }
  .c-price  { width:22mm; text-align:right; font-variant-numeric:tabular-nums; }
  .c-total  { width:24mm; text-align:right; font-variant-numeric:tabular-nums; }

  .row-sum .sum-lbl   { text-align:right; }
  .row-total td       { font-weight:700; font-size:var(--fs-md); border-top:var(--rule-box); }

  .amount-words { border-top:var(--rule-box); padding:3px 6px; font-weight:700; }

  /* ── Terms ────────────────────────────────────────────────────────── */
  .tnc-section { margin-top:5mm; }
  .tnc-title   { font-weight:700; font-size:var(--fs-md); margin-bottom:4px; }
  .tnc-ol      { list-style:none; margin:0; padding:0; }
  .tnc-ol li   { display:flex; gap:4px; margin-bottom:3px; line-height:1.35;
                 font-family:inherit; font-size:var(--fs-sm); color:var(--doc-ink); }
  .tnc-num     { flex-shrink:0; min-width:15px; }

  /* ── Signature ────────────────────────────────────────────────────── */
  .sig-block { display:flex; justify-content:space-between; align-items:flex-start;
               gap:10mm; margin-top:6mm; }
  .sig-kv    { display:grid; grid-template-columns:auto 1fr; gap:2px 4px; }
  .sig-kv b  { font-weight:700; }
  .sig-for   { font-weight:700; }
  /* Deliberate blank space for a wet signature, then the name. No rule above
     the name — the signature goes in the gap, not under a printed line. */
  .sig-name  { margin-top:15mm; text-align:center; }
  .sig-note  { margin-top:6mm; color:var(--doc-soft); }

  @media print {
    @page { size:A4 portrait; margin:10mm 9mm 9mm; }

    /* .deal-panel / .alert are internal sales tracking — never part of the
       document the customer receives. */
    nav,.page-top,.screen-acts,.deal-panel,.alert,footer { display:none !important; }
    html, body { background:#fff !important; margin:0 !important; padding:0 !important; }
    main       { background:none !important; margin:0 !important; padding:0 !important;
                 max-width:none !important; }
    .doc-outer { max-width:none; margin:0; padding:0; }
    .quotation-doc { border:none; box-shadow:none; padding:0; }
    /* A scroll container clips instead of reflowing when printed. */
    .items-wrap { overflow:visible !important; }

    /* Repeat the letterhead, the foot strip and the column heads on page 2+. */
    .page-frame > thead { display:table-header-group; }
    .page-frame > tfoot { display:table-footer-group; }
    .q-table    > thead { display:table-header-group; }

    /* The head band is the one fill that carries meaning, so force it through
       Chrome's default "don't print backgrounds". Everything else reads
       identically with backgrounds off. */
    .q-table th { -webkit-print-color-adjust:exact; print-color-adjust:exact; }

    .q-table tr, .tnc-ol li, .sig-block, .amount-words {
      break-inside:avoid; page-break-inside:avoid;
    }
    .tnc-title { break-after:avoid; page-break-after:avoid; }

    /* The blank-identity guard still has to be visible on the document — but a
       yellow dashed pill on a customer's quotation is worse than the gap it
       is warning about. Print it as bracketed italics instead. */
    .todo-chip {
      background:none !important; border:none !important; color:#555 !important;
      padding:0 !important; font-style:italic; font-weight:400 !important;
    }
    .todo-chip::before { content:"["; }
    .todo-chip::after  { content:"]"; }
  }

  /* MUST be scoped to `screen`. A4 at 96dpi is ~794px and the printable box is
     narrower still, so an unscoped max-width breakpoint fires *on paper* and
     prints the phone layout — stacked header, collapsed letterhead. */
  @media screen and (max-width:760px){
    .doc-outer     { max-width:100%; }
    .quotation-doc { padding:5mm 4mm; }
    .lh            { flex-direction:column; align-items:flex-start; }
    .doc-header    { grid-template-columns:1fr; }
    .dh-cell + .dh-cell { border-left:none; border-top:var(--rule); }
    .q-table { table-layout:auto; min-width:640px; }
  }
</style>
"""


# =============================================================================
# ROUTES
# =============================================================================

@quotation_bp.route("/")
def list_quotations():
    quotations = STORE["quotations"]
    create_url = url_for("quotation.create_quotation")
    dash_url   = url_for("dashboard.index")
    msg        = request.args.get("msg")
    msg_type   = request.args.get("type", "success")

    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {msg}</div>'

    # ── Pipeline summary + filtering (all logic lives in pipeline.py) ───
    summary   = P.summarize(quotations)
    rows      = P.filter_quotations(quotations, request.args)
    cur_view  = (request.args.get("view")  or P.DEFAULT_VIEW).strip().lower()
    cur_stage = (request.args.get("stage") or "").strip()
    cur_q     = (request.args.get("q")     or "").strip()

    def _rupees(v):
        return f"&#8377;&nbsp;{v:,.0f}"

    win_rate = (f'{summary["win_rate"]}% win rate' if summary["win_rate"] is not None
                else "no closed deals yet")
    won_po   = summary["won"]["po_value"]

    tiles_html = f"""
    <div class="pipe-tiles">
      <div class="pipe-tile t-open">
        <div class="pt-lbl">Open Pipeline</div>
        <div class="pt-val">{_rupees(summary['open']['value'])}</div>
        <div class="pt-sub">{summary['open']['count']} live quotation{"s" if summary['open']['count'] != 1 else ""}</div>
      </div>
      <div class="pipe-tile">
        <div class="pt-lbl">PO Expected</div>
        <div class="pt-val">{_rupees(summary['by_stage'].get('PO Expected', {}).get('value', 0))}</div>
        <div class="pt-sub">{summary['by_stage'].get('PO Expected', {}).get('count', 0)} awaiting customer PO</div>
      </div>
      <div class="pipe-tile t-won">
        <div class="pt-lbl">Won</div>
        <div class="pt-val">{_rupees(summary['won']['value'])}</div>
        <div class="pt-sub">{summary['won']['count']} won &middot; {win_rate}</div>
      </div>
      <div class="pipe-tile t-lost">
        <div class="pt-lbl">Lost</div>
        <div class="pt-val">{_rupees(summary['lost']['value'])}</div>
        <div class="pt-sub">{summary['lost']['count']} lost</div>
      </div>
    </div>"""

    # PO value only means something once at least one has been recorded.
    if won_po:
        tiles_html = tiles_html.replace(
            f'<div class="pt-sub">{summary["won"]["count"]} won &middot; {win_rate}</div>',
            f'<div class="pt-sub">{summary["won"]["count"]} won &middot; {win_rate}<br>'
            f'PO value {_rupees(won_po)}</div>')

    # ── Filter bar ─────────────────────────────────────────────────────
    view_counts = {
        "all":  summary["total"]["count"],
        "open": summary["open"]["count"],
        "won":  summary["won"]["count"],
        "lost": summary["lost"]["count"],
    }
    tabs_html = ""
    for key, (label, _pred) in P.VIEWS.items():
        active = " active" if key == cur_view else ""
        href   = url_for("quotation.list_quotations", view=key,
                         **({"stage": cur_stage} if cur_stage else {}),
                         **({"q": cur_q} if cur_q else {}))
        tabs_html += f'<a href="{href}" class="filter-tab{active}">{label} ({view_counts[key]})</a>'

    stage_opts = '<option value="">All stages</option>'
    for s in P.SALES_STAGES:
        n = summary["by_stage"].get(s, {}).get("count", 0)
        sel = " selected" if s == cur_stage else ""
        stage_opts += f'<option value="{P.esc(s)}"{sel}>{P.esc(s)} ({n})</option>'

    clear_html = ""
    if cur_stage or cur_q or cur_view != P.DEFAULT_VIEW:
        clear_html = (f'<a href="{url_for("quotation.list_quotations")}" '
                      f'class="fb-clear">clear filters</a>')

    filter_html = f"""
    <div class="filter-bar">
      <div class="filter-tabs">{tabs_html}</div>
      <form method="GET" action="{url_for("quotation.list_quotations")}">
        <input type="hidden" name="view" value="{P.esc(cur_view)}"/>
        <select name="stage" onchange="this.form.submit()">{stage_opts}</select>
        <input type="search" name="q" value="{P.esc(cur_q)}" placeholder="ref, customer or PO no."/>
        <button type="submit" class="filter-tab">Search</button>
        {clear_html}
      </form>
    </div>"""

    # ── Table ──────────────────────────────────────────────────────────
    if rows:
        rows_html = ""
        for qid, q in rows:
            view_url = url_for("quotation.view_quotation", id=qid)
            customer = (q.get("account_name") or q.get("to") or "").strip().splitlines()[0] or "—"
            n_root   = sum(1 for r in q["line_items"] if r["depth"] == 0)
            rows_html += f"""
            <tr>
              <td class="td-ref">{q['ref']}</td>
              <td class="td-muted">{q['date']}</td>
              <td class="td-cust">{customer}</td>
              <td>{P.stage_badge(P.stage_of(q))}</td>
              <td class="col-h">{P.po_cell(q)}</td>
              <td class="td-muted col-h">{n_root} line{"s" if n_root!=1 else ""}</td>
              <td style="font-weight:700;color:var(--brand);">&#8377;&nbsp;{q['grand_total']:,.0f}</td>
              <td><a href="{view_url}" class="btn-view">&#128269; View</a></td>
            </tr>"""
        table_html = f"""
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Ref No.</th><th>Date</th><th>Customer</th>
            <th>Stage</th><th class="col-h">Customer PO</th><th class="col-h">Lines</th>
            <th>Total</th><th></th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""
    elif quotations:
        # Store has records, but none survive the current filter.
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128269;</div><br>
          <strong>No quotations match this filter</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">Try a different stage, or clear the filters.</p>
          <a href="{url_for("quotation.list_quotations")}" class="btn"
             style="display:inline-block;margin-top:1.1rem;">Show all</a>
        </div>"""
    else:
        table_html = f"""
        <div class="empty-state">
          <div style="font-size:2rem;">&#128196;</div><br>
          <strong>No quotations yet</strong>
          <p style="margin-top:.4rem;font-size:.88rem;">Create your first quotation to get started.</p>
          <a href="{create_url}" class="btn" style="display:inline-block;margin-top:1.1rem;">+ Create Quotation</a>
        </div>"""

    template = f"""<!DOCTYPE html><html lang="en">
    <head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
    <title>{B.page_title("Quotations")}</title>{B.HEAD_ICON}{BASE_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}</head>
    <body>{_nav()}
    <main>
      {alert_html}
      <div class="page-top">
        <h1>Quotation <span>Register</span>
          <span style="font-size:.73rem;font-weight:500;color:var(--muted);margin-left:.5rem;">
            showing {len(rows)} of {len(quotations)}
          </span>
        </h1>
        <div style="display:flex;gap:.7rem;">
          <a href="{dash_url}" class="btn btn-ghost">&#8592; Dashboard</a>
          <a href="{create_url}" class="btn">+ Create Quotation</a>
        </div>
      </div>
      {tiles_html}
      {filter_html}
      {table_html}
      <footer><p>{COMPANY_NAME} · {B.APP_SUBTITLE} · quotation register</p></footer>
    </main></body></html>"""
    return render_template_string(template)


# ── Dropdown option lists ──────────────────────────────────────────────────────

# Stage vocabulary is owned by pipeline.py — add or rename stages there and the
# create form, edit panel and register filters all follow automatically.
_SALES_STAGES  = P.SALES_STAGES
_LEAD_SOURCES  = ["Cold Call", "Email Campaign", "Website Enquiry", "Referral",
                   "Exhibition / Trade Show", "Existing Customer", "Tender / Bid", "Walk-in"]
_LEAD_TYPES    = ["Builder / Developer", "PMC / Consultant", "Industrial", "Govt / PSU",
                   "Tender", "Housing Society", "Dealer / Sub-contractor"]
_LEAD_SUBTYPES = ["HYDRANT SYSTEM", "SPRINKLER SYSTEM", "FIRE PUMP ROOM", "FIRE ALARM & DETECTION",
                   "PORTABLE EXTINGUISHERS", "FIRE DOORS", "AMC / REFILLING",
                   "WATER SUPPLY", "PRESSURE BOOSTING", "OTHERS"]
_PAY_TERMS     = ["100% Against Proforma Invoice", "100% Advance",
                   "30% Advance with PO, Balance Against Proforma Invoice Prior to Delivery",
                   "30% Advance, Balance Before Dispatch",
                   "50% Advance, Balance Before Dispatch",
                   "90% Against Proforma, 10% After Installation",
                   "LC at Sight", "LC 30 Days", "45 Days Credit", "60 Days Credit",
                   "90 Days Credit", "Against Delivery (COD)"]
_DEL_TERMS     = ["Ex-Works", "Ex-Godown", "Ex-Stock", "FOR Destination",
                   "FOR Site", "Door Delivery", "FOB Mumbai", "CIF Destination"]
_DISPATCH      = ["In Clients Scope", "By Road Transport", "By Air Cargo",
                   "By Courier", "By Hand Delivery", "Self Pickup",
                   "VRL Logistics", "TCI Freight", "DTDC Cargo", "Blue Dart"]
_INCOTERMS     = ["FOR", "EXW", "FOB", "CIF", "CFR", "DAP", "DDP", "FCA"]
_VALIDITY      = ["7 Days", "10 Days", "15 Days", "30 Days", "45 Days", "60 Days", "90 Days"]
# Branch / region lists are placeholders until the client confirms where they
# actually operate from — see branding.py.
_BRANCHES      = [B.COMPANY_NAME]
_REGIONS       = ["Head Office"]
_TYPES         = ["Fire Fighting System", "Fire Pump Set", "Fire Alarm & Detection",
                   "Extinguishers", "Spares", "AMC / Refilling", "Others"]
_COUNTRIES     = ["India", "UAE", "Saudi Arabia", "Oman", "Qatar", "Kuwait", "Other"]
# Full state list is owned by address.py. Sharing it matters for the address-book
# picker: a saved address in, say, Kerala has to find a matching <option> here,
# and the old 10-state shortlist silently dropped most of India on the floor.
_STATES_IN     = list(INDIAN_STATES) + ["Other"]


def _sel_opts(name, options, default, form_val=None):
    cur = form_val if form_val is not None else default
    inner = "".join(
        f'<option{"  selected" if o == cur else ""}>{o}</option>'
        for o in options
    )
    return f'<select id="{name}" name="{name}">{inner}</select>'


@quotation_bp.route("/create", methods=["GET", "POST"])
def create_quotation():
    from product import ensure_demo_products
    ensure_demo_products()

    products = STORE["products"]
    error    = None
    form     = request.form

    # ── POST ───────────────────────────────────────────────────────────
    if request.method == "POST":
        qtn_date         = form.get("qtn_date",        str(_date.today()))
        rate_contract    = form.get("rate_contract", "") == "1"
        qtn_type         = form.get("qtn_type",       "").strip()
        validity_days    = form.get("validity_days",  "10").strip()
        buyer_ref        = form.get("buyer_ref",      "").strip()
        other_ref        = form.get("other_ref",      "").strip()
        sales_stage      = form.get("sales_stage",    "").strip()
        lead_source      = form.get("lead_source",    "").strip()
        lead_type        = form.get("lead_type",      "").strip()
        lead_subtype     = form.get("lead_subtype",   "").strip()
        lead_owner       = form.get("lead_owner",     "").strip()
        exp_closing      = form.get("exp_closing",    "").strip()
        delivery_date    = form.get("delivery_date",  "").strip()
        incoterms        = form.get("incoterms",      "").strip()
        payment_terms    = form.get("payment_terms",  "").strip()
        delivery_terms   = form.get("delivery_terms", "").strip()
        dispatch_through = form.get("dispatch_through","").strip()
        company_branch   = form.get("company_branch", "").strip()
        amend_no         = form.get("amend_no",       "Original").strip()
        auth_signatory   = form.get("auth_signatory", "").strip()
        region           = form.get("region",         "").strip()
        assigned_to      = form.get("assigned_to",    "").strip()

        account_name     = form.get("account_name",   "").strip()
        contact_person   = form.get("contact_person", "").strip()

        bill_addr        = form.get("bill_addr",  "").strip()
        bill_country     = form.get("bill_country","India").strip()
        bill_state       = form.get("bill_state", "").strip()
        bill_city        = form.get("bill_city",  "").strip()
        bill_pin         = form.get("bill_pin",   "").strip()
        bill_phone       = form.get("bill_phone", "").strip()
        bill_gstin       = form.get("bill_gstin", "").strip()

        ship_same        = form.get("ship_same",  "") == "1"
        ship_acct_name   = form.get("ship_acct_name","").strip()
        ship_addr        = form.get("ship_addr",  "").strip()
        ship_country     = form.get("ship_country","India").strip()
        ship_state       = form.get("ship_state", "").strip()
        ship_city        = form.get("ship_city",  "").strip()
        ship_pin         = form.get("ship_pin",   "").strip()
        ship_phone       = form.get("ship_phone", "").strip()
        ship_fax         = form.get("ship_fax",   "").strip()
        ship_email       = form.get("ship_email", "").strip()
        ship_gstin       = form.get("ship_gstin", "").strip()

        tax_type    = form.get("tax_type", "cgst_sgst")
        def _safe_float(key, default=0.0):
            try:    return float(form.get(key) or default)
            except: return default
        cgst_rate   = _safe_float("tax_cgst", 9)
        sgst_rate   = _safe_float("tax_sgst", 9)
        igst_rate   = _safe_float("tax_igst", 18)
        vat_rate    = _safe_float("tax_vat",  5)

        # Force SGST = CGST always
        sgst_rate = cgst_rate

        selections_raw = form.get("selections_json", "[]")

        if not account_name:
            error = "Account Name is required."

        sel_data = []
        if not error:
            try:
                sel_data = json.loads(selections_raw)
            except (json.JSONDecodeError, TypeError):
                error = "Invalid product selection data. Please re-add your products."

        if not error and not sel_data:
            error = "Please add at least one product to the quotation."

        if not error:
            for item in sel_data:
                if item.get("pid") not in products:
                    error = "Product no longer exists in catalog. Please re-add."
                    break

        if not error:
            line_items  = _process_selections(sel_data)
            subtotal    = sum(r["total"] for r in line_items)
            tax_info    = _tax_lines(subtotal, tax_type,
                                     cgst_rate=cgst_rate, sgst_rate=sgst_rate,
                                     igst_rate=igst_rate, vat_rate=vat_rate)
            grand_total = subtotal + tax_info["total"]
            total_qty   = sum(r["qty"] for r in line_items if r["depth"] == 0)

            to_parts = [account_name]
            if contact_person: to_parts.append(f"Attn: {contact_person}")
            if bill_addr:      to_parts.append(bill_addr)
            city_line = ", ".join(filter(None, [bill_city, bill_state]))
            if city_line or bill_pin:
                to_parts.append(f"{city_line} – {bill_pin}".strip(" –"))
            if bill_country and bill_country != "India":
                to_parts.append(bill_country)
            if bill_phone:  to_parts.append(f"Phone: {bill_phone}")
            if bill_gstin:  to_parts.append(f"GSTIN: {bill_gstin}")
            to_display = "\n".join(to_parts)

            qid = str(uuid.uuid4())
            STORE["quotations"][qid] = {
                "id": qid, "ref": _next_ref(),
                "date": qtn_date, "rate_contract": rate_contract,
                "qtn_type": qtn_type, "validity_days": validity_days,
                "buyer_ref": buyer_ref, "other_ref": other_ref,
                "sales_stage": sales_stage, "lead_source": lead_source,
                "lead_type": lead_type, "lead_subtype": lead_subtype,
                "lead_owner": lead_owner, "exp_closing": exp_closing,
                "delivery_date": delivery_date,
                "incoterms": incoterms, "payment_terms": payment_terms,
                "delivery_terms": delivery_terms, "dispatch_through": dispatch_through,
                "company_branch": company_branch, "amend_no": amend_no,
                "auth_signatory": auth_signatory, "region": region, "assigned_to": assigned_to,
                "account_name": account_name, "contact_person": contact_person,
                "bill_addr": bill_addr, "bill_country": bill_country,
                "bill_state": bill_state, "bill_city": bill_city,
                "bill_pin": bill_pin, "bill_phone": bill_phone, "bill_gstin": bill_gstin,
                "ship_same": ship_same, "ship_acct_name": ship_acct_name,
                "ship_addr": ship_addr, "ship_country": ship_country,
                "ship_state": ship_state, "ship_city": ship_city,
                "ship_pin": ship_pin, "ship_phone": ship_phone,
                "ship_fax": ship_fax, "ship_email": ship_email, "ship_gstin": ship_gstin,
                "tax_type": tax_type,
                "cgst_rate": cgst_rate, "sgst_rate": sgst_rate,
                "igst_rate": igst_rate, "vat_rate": vat_rate,
                "tax_info": tax_info,
                "subtotal": subtotal, "grand_total": grand_total, "total_qty": total_qty,
                "selections": sel_data, "line_items": line_items,
                "to": to_display,
            }
            # Pipeline fields (stage history, customer PO) — owned by pipeline.py.
            # ensure_fields() also backfills quotations made before that module
            # existed, so old and new records behave identically.
            P.ensure_fields(STORE["quotations"][qid])
            P.log_event(STORE["quotations"][qid], "Quotation created.")
            return redirect(url_for("quotation.view_quotation", id=qid))

    # ── GET / re-render with error ─────────────────────────────────────
    list_url     = url_for("quotation.list_quotations")
    error_html   = f'<div class="alert alert-error">&#10007; {error}</div>' if error else ""
    today_str    = str(_date.today())
    catalog_json = _product_catalog_json()

    prod_opts = '<option value="">— select product —</option>'
    for pid, p in products.items():
        tag       = p.get("type", "standalone")[:3].upper()
        safe_name = p["name"].replace('"', '&quot;')
        safe_pno  = p["part_no"].replace('"', '&quot;')
        prod_opts += (
            f'<option value="{pid}"'
            f' data-name="{safe_name}"'
            f' data-partno="{safe_pno}"'
            f' data-type="{p.get("type","standalone")}"'
            f' data-price="{p["base_price"]}">'
            f'[{tag}] {p["name"]} ({p["part_no"]})</option>'
        )

    comp_opts = '<option value="">— select component —</option>'
    for pid, p in products.items():
        tag       = p.get("type", "standalone")[:3].upper()
        safe_name = p["name"].replace('"', '&quot;')
        safe_pno  = p["part_no"].replace('"', '&quot;')
        comp_opts += (
            f'<option value="{pid}"'
            f' data-name="{safe_name}"'
            f' data-partno="{safe_pno}"'
            f' data-price="{p["base_price"]}"'
            f' data-unit="{p["unit"]}">'
            f'[{tag}] {p["name"]} ({p["part_no"]})</option>'
        )

    def _fv(k, d=""):
        v = form.get(k, d)
        return v if v is not None else d

    prev_selections  = form.get("selections_json", "[]")
    init_tax_type    = _fv("tax_type", "cgst_sgst")
    init_cgst        = _fv("tax_cgst", "9")
    init_sgst        = _fv("tax_sgst", "9")
    init_igst        = _fv("tax_igst", "18")
    init_vat         = _fv("tax_vat",  "5")

    # Pre-compute safe initial GST total for server-side render
    try:
        _init_gst_total = float(init_cgst) + float(init_sgst)
    except Exception:
        _init_gst_total = 18.0

    # ── Build the HTML template using a raw string to avoid f-string
    #    collisions with JS curly braces.  All Python values are
    #    interpolated BEFORE the JS block via .format().  The JS block
    #    uses {{ }} to produce literal { }.
    # ──────────────────────────────────────────────────────────────────

    # Safely JSON-encode Python strings for embedding in JS string literals
    def _js(s):
        return json.dumps(str(s))

    page = """<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{page_title}</title>
  {head_icon}
  {base_styles}
  {qtn_styles}
</head>
<body>
{nav}
<main>

<div class="page-top">
  <h1>Create <span>Quotation</span></h1>
  <div style="display:flex;gap:.7rem;align-items:center;">
    <button type="button" onclick="fillDemoData()"
            class="btn btn-ghost"
            style="border-color:#a5b4fc;color:var(--brand);"
            title="Fill all fields with realistic sample data">
      &#9881;&nbsp;Use Demo Data
    </button>
    <a href="{list_url}" class="btn btn-ghost">&#8592; Back</a>
  </div>
</div>

{error_html}

<!-- Embed catalog — parsed by JS below -->
<script type="application/json" id="catalog-data">{catalog_json}</script>

<!-- Embed prior selections as raw JSON — never put JSON in an HTML attribute -->
<script type="application/json" id="prev-sel-data">{prev_sel}</script>

<form method="POST" action="" id="qf">
<input type="hidden" id="selections_json" name="selections_json" value="[]"/>

<!-- ════════ SECTION 1: QUOTATION DETAILS ════════ -->
<div class="form-section">
  <div class="section-title">&#128196;&nbsp; Quotation Details</div>

  <div class="fg4" style="margin-bottom:.85rem;">
    <div class="form-group">
      <label>Qtn No.</label>
      <div class="readonly-field">{next_ref}&nbsp;<span style="font-size:.72rem;color:#888;">auto</span></div>
    </div>
    <div class="form-group">
      <label for="qtn_date">Qtn. Date *</label>
      <input type="date" id="qtn_date" name="qtn_date" value="{today}" required/>
    </div>
    <div class="form-group">
      <label for="qtn_type">Type</label>
      {sel_qtn_type}
    </div>
    <div class="form-group">
      <label for="validity_days">Validity (days)</label>
      <input type="number" id="validity_days" name="validity_days"
             value="{vdays}" min="1" placeholder="10"/>
    </div>
  </div>

  <div class="fg4" style="margin-bottom:.85rem;">
    <div class="form-group">
      <label for="buyer_ref">Buyer's Ref.</label>
      <input type="text" id="buyer_ref" name="buyer_ref" value="{buyer_ref}" placeholder="PO / SN"/>
    </div>
    <div class="form-group span2">
      <label for="other_ref">Other Ref.</label>
      <input type="text" id="other_ref" name="other_ref" value="{other_ref}"
             placeholder="e.g. fire hydrant system / main pump 2850 LPM @ 104M head"/>
    </div>
    <div class="form-group">
      <label style="visibility:hidden;">Rate Contract</label>
      <div class="check-row">
        <input type="checkbox" id="rate_contract" name="rate_contract" value="1" {rc_checked}/>
        <label for="rate_contract">Rate Contract</label>
      </div>
    </div>
  </div>

  <div class="fg4" style="margin-bottom:.85rem;">
    <div class="form-group">
      <label for="sales_stage">Sales Stage *</label>
      {sel_sales_stage}
    </div>
    <div class="form-group">
      <label for="lead_source">Lead Source</label>
      {sel_lead_source}
    </div>
    <div class="form-group">
      <label for="lead_type">Lead Type</label>
      {sel_lead_type}
    </div>
    <div class="form-group">
      <label for="lead_subtype">Lead Sub-Type</label>
      {sel_lead_subtype}
    </div>
  </div>

  <div class="fg4" style="margin-bottom:.85rem;">
    <div class="form-group">
      <label for="lead_owner">Lead Owner</label>
      <input type="text" id="lead_owner" name="lead_owner" value="{lead_owner}" placeholder="Name of the sales engineer"/>
    </div>
    <div class="form-group">
      <label for="exp_closing">Exp. Closing Date</label>
      <input type="date" id="exp_closing" name="exp_closing" value="{exp_closing}"/>
    </div>
    <div class="form-group">
      <label for="delivery_date">Delivery Date</label>
      <input type="date" id="delivery_date" name="delivery_date" value="{delivery_date}"/>
    </div>
    <div class="form-group">
      <label for="company_branch">Company / Branch</label>
      {sel_company_branch}
    </div>
  </div>

  <div class="fg4" style="margin-bottom:.85rem;">
    <div class="form-group">
      <label for="incoterms">Incoterms</label>
      {sel_incoterms}
    </div>
    <div class="form-group">
      <label for="payment_terms">Mode / Terms of Payment</label>
      {sel_payment_terms}
    </div>
    <div class="form-group">
      <label for="delivery_terms">Terms of Delivery</label>
      {sel_delivery_terms}
    </div>
    <div class="form-group">
      <label for="dispatch_through">Dispatch Through</label>
      {sel_dispatch_through}
    </div>
  </div>

  <div class="fg4">
    <div class="form-group">
      <label for="amend_no">Amend No.</label>
      <input type="text" id="amend_no" name="amend_no" value="{amend_no}" placeholder="Original"/>
    </div>
    <div class="form-group">
      <label for="auth_signatory">Auth. Signatory *</label>
      <input type="text" id="auth_signatory" name="auth_signatory" value="{auth_signatory}" placeholder="Name of the sales engineer"/>
    </div>
    <div class="form-group">
      <label for="region">Region</label>
      {sel_region}
    </div>
    <div class="form-group">
      <label for="assigned_to">Assigned To *</label>
      <input type="text" id="assigned_to" name="assigned_to" value="{assigned_to}" placeholder="Click to edit"/>
    </div>
  </div>
</div>

<!-- ════════ SECTION 2: ACCOUNT DETAILS ════════ -->
<div class="form-section">
  <div class="section-title">&#128100;&nbsp; Account Details</div>

  <div class="fg2" style="margin-bottom:.85rem;">
    <div class="form-group">
      <label for="account_name">Account Name *</label>
      <input type="text" id="account_name" name="account_name" value="{account_name}"
             placeholder="M/s. Company Name" required/>
    </div>
    <div class="form-group">
      <label for="contact_person">Contact Person</label>
      <input type="text" id="contact_person" name="contact_person" value="{contact_person}"
             placeholder="Mr. Name, Designation"/>
    </div>
  </div>

  <div class="addr-sub">
    <div class="addr-sub-title">&#128205; Billing Address</div>
    <div class="addr-pick">
      <select id="bill_pick" onchange="applyAddr('bill', this)">{addr_options_bill}</select>
      <a href="{address_url}" target="_blank" rel="noopener" class="addr-pick-link">
        &#128214; manage address book
      </a>
    </div>
    <div class="fg2" style="margin-bottom:.7rem;">
      <div class="form-group span-all">
        <label for="bill_addr">Address</label>
        <textarea id="bill_addr" name="bill_addr"
                  placeholder="Plot/Door No., Street, Area, Landmark">{bill_addr}</textarea>
      </div>
    </div>
    <div class="fg4">
      <div class="form-group">{sel_bill_country}</div>
      <div class="form-group">{sel_bill_state}</div>
      <div class="form-group">
        <label for="bill_city">City</label>
        <input type="text" id="bill_city" name="bill_city" value="{bill_city}" placeholder="Mumbai"/>
      </div>
      <div class="form-group">
        <label for="bill_pin">Pincode</label>
        <input type="text" id="bill_pin" name="bill_pin" value="{bill_pin}" placeholder="400001"/>
      </div>
    </div>
    <div class="fg2" style="margin-top:.7rem;">
      <div class="form-group">
        <label for="bill_phone">Phone</label>
        <input type="tel" id="bill_phone" name="bill_phone" value="{bill_phone}" placeholder="+91 XXXXX XXXXX"/>
      </div>
      <div class="form-group">
        <label for="bill_gstin">GSTIN</label>
        <input type="text" id="bill_gstin" name="bill_gstin" value="{bill_gstin}"
               placeholder="27AABCX1234A1ZX"
               style="font-family:'SFMono-Regular',Consolas,monospace;letter-spacing:.04em;"/>
      </div>
    </div>
  </div>

  <div class="addr-sub" style="margin-top:.85rem;">
    <div class="addr-sub-title">&#128666; Shipping Address</div>
    <div class="ship-opts">
      <label class="ship-opt" style="border-right:1px solid var(--border);padding-right:1rem;margin-right:.2rem;">
        <input type="checkbox" name="ship_same" value="1" id="ship_same_chk" {ship_same_checked}
               onchange="toggleShipSame(this.checked)"/>
        Same as Billing
      </label>
      <label class="ship-opt">
        <input type="radio" name="ship_type" value="modify" checked/> Modify Address
      </label>
      <label class="ship-opt">
        <input type="radio" name="ship_type" value="new_account"/> New Account
      </label>
      <label class="ship-opt">
        <input type="radio" name="ship_type" value="existing"/> Existing Account
      </label>
    </div>
    <div id="ship-fields">
      <div class="addr-pick">
        <select id="ship_pick" onchange="applyAddr('ship', this)">{addr_options_ship}</select>
        <a href="{address_url}" target="_blank" rel="noopener" class="addr-pick-link">
          &#128214; manage address book
        </a>
      </div>
      <div class="fg2" style="margin-bottom:.7rem;">
        <div class="form-group">
          <label for="ship_acct_name">Account Name</label>
          <input type="text" id="ship_acct_name" name="ship_acct_name" value="{ship_acct_name}"
                 placeholder="Shipping account name"/>
        </div>
        <div class="form-group">
          <label for="ship_email">Email</label>
          <input type="email" id="ship_email" name="ship_email" value="{ship_email}"
                 placeholder="contact@company.com"/>
        </div>
        <div class="form-group span-all">
          <label for="ship_addr">Address</label>
          <textarea id="ship_addr" name="ship_addr"
                    placeholder="Plot/Door No., Street, Area, Landmark">{ship_addr}</textarea>
        </div>
      </div>
      <div class="fg4">
        <div class="form-group">{sel_ship_country}</div>
        <div class="form-group">{sel_ship_state}</div>
        <div class="form-group">
          <label for="ship_city">City</label>
          <input type="text" id="ship_city" name="ship_city" value="{ship_city}" placeholder="Mumbai"/>
        </div>
        <div class="form-group">
          <label for="ship_pin">Pincode</label>
          <input type="text" id="ship_pin" name="ship_pin" value="{ship_pin}" placeholder="400001"/>
        </div>
      </div>
      <div class="fg3" style="margin-top:.7rem;">
        <div class="form-group">
          <label for="ship_phone">Phone</label>
          <input type="tel" id="ship_phone" name="ship_phone" value="{ship_phone}"
                 placeholder="+91 XXXXX XXXXX"/>
        </div>
        <div class="form-group">
          <label for="ship_fax">Fax</label>
          <input type="text" id="ship_fax" name="ship_fax" value="{ship_fax}" placeholder="Fax number"/>
        </div>
        <div class="form-group">
          <label for="ship_gstin">GSTIN</label>
          <input type="text" id="ship_gstin" name="ship_gstin" value="{ship_gstin}"
                 placeholder="27AABCX1234A1ZX"
                 style="font-family:'SFMono-Regular',Consolas,monospace;letter-spacing:.04em;"/>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ════════ SECTION 3: PRODUCTS ════════ -->
<div class="form-section">
  <div class="section-title">&#128230;&nbsp; Item Details</div>

  <div class="picker-bar">
    <div class="form-group" style="margin:0;">
      <label for="picker-prod">Product / Assembly</label>
      <select id="picker-prod">{prod_opts}</select>
    </div>
    <div class="form-group" style="margin:0;">
      <label for="picker-qty">Qty</label>
      <input type="number" id="picker-qty" value="1" min="1" step="1"/>
    </div>
    <div class="form-group" style="margin:0;">
      <label style="visibility:hidden;">Add</label>
      <button type="button" class="btn" onclick="addProduct()">+ Add</button>
    </div>
  </div>
  <div id="add-error" class="add-error"></div>
  <div id="sel-container"></div>
  <div id="empty-notice">
    No products added yet. Select a product above and click <strong>+ Add</strong>.
  </div>
  <template id="comp-opts-tpl">{comp_opts}</template>
</div>

<!-- ════════ SECTION 4: TAX / DUTY ════════ -->
<div class="form-section">
  <div class="section-title">&#128181;&nbsp; Tax / Duty</div>

  <!-- Hidden fields submitted with the form -->
  <input type="hidden" name="tax_cgst" id="hid_cgst" value="{init_cgst}"/>
  <input type="hidden" name="tax_sgst" id="hid_sgst" value="{init_sgst}"/>
  <input type="hidden" name="tax_igst" id="hid_igst" value="{init_igst}"/>
  <input type="hidden" name="tax_vat"  id="hid_vat"  value="{init_vat}"/>

  <div class="tax-options">
    <label class="tax-opt">
      <input type="radio" name="tax_type" value="cgst_sgst" id="tr_cgst"
             {cgst_checked} onchange="switchTax('cgst_sgst')"/>
      CGST + SGST (intra-state)
    </label>
    <label class="tax-opt">
      <input type="radio" name="tax_type" value="igst" id="tr_igst"
             {igst_checked} onchange="switchTax('igst')"/>
      IGST (inter-state)
    </label>
    <label class="tax-opt">
      <input type="radio" name="tax_type" value="vat" id="tr_vat"
             {vat_checked} onchange="switchTax('vat')"/>
      VAT
    </label>
    <label class="tax-opt">
      <input type="radio" name="tax_type" value="exempt" id="tr_exempt"
             {exempt_checked} onchange="switchTax('exempt')"/>
      Exempt / Not Applicable
    </label>
  </div>

  <!-- CGST + SGST panel — SGST is always locked to mirror CGST -->
  <div id="tp_cgst_sgst" class="tax-panel">
    <div class="tax-input-group">
      <div class="tax-field-lbl">CGST %</div>
      <input type="number" class="tax-field-inp" id="inp_cgst"
             value="{init_cgst}" min="0" max="50" step="0.5"
             oninput="onGstRateChange(this.value)"/>
    </div>
    <div class="tax-sep">+</div>
    <div class="tax-input-group">
      <div class="tax-field-lbl">SGST % (mirrors CGST)</div>
      <input type="number" class="tax-field-inp" id="inp_sgst"
             value="{init_sgst}" min="0" max="50" step="0.5" readonly
             style="background:#f0f0f0;cursor:not-allowed;opacity:.8;"/>
    </div>
    <div class="tax-sep">=</div>
    <div class="tax-input-group">
      <div class="tax-field-lbl">Total GST %</div>
      <div class="tax-total-display" id="gst_total">{gst_total_display}%</div>
    </div>
    <div class="tax-hint">CGST and SGST are always equal. Enter CGST and SGST mirrors it automatically.</div>
  </div>

  <!-- IGST panel -->
  <div id="tp_igst" class="tax-panel">
    <div class="tax-input-group">
      <div class="tax-field-lbl">IGST %</div>
      <input type="number" class="tax-field-inp" id="inp_igst"
             value="{init_igst}" min="0" max="100" step="0.5"
             oninput="document.getElementById('hid_igst').value=this.value"/>
    </div>
    <div class="tax-hint">Applied as a single integrated tax on inter-state supply.</div>
  </div>

  <!-- VAT panel -->
  <div id="tp_vat" class="tax-panel">
    <div class="tax-input-group">
      <div class="tax-field-lbl">VAT %</div>
      <input type="number" class="tax-field-inp" id="inp_vat"
             value="{init_vat}" min="0" max="100" step="0.5"
             oninput="document.getElementById('hid_vat').value=this.value"/>
    </div>
    <div class="tax-hint">Value Added Tax — for non-GST registered supply.</div>
  </div>

  <!-- Exempt panel -->
  <div id="tp_exempt" class="tax-panel">
    <span style="color:var(--muted);font-size:.86rem;">
      &#10003;&nbsp; No tax will be calculated or shown on the quotation document.
    </span>
  </div>
</div>

<div class="form-actions">
  <button type="submit" class="btn">&#10003;&nbsp; Generate Quotation</button>
  <a href="{list_url}" class="btn btn-ghost">Cancel</a>
</div>

</form>
<footer><p>{company_name} · {app_subtitle} · new quotation</p></footer>
</main>

<script>
/* ═══════════════════════════════════════════════════════════
   CATALOG — parsed from embedded JSON, never from f-string
═══════════════════════════════════════════════════════════ */
var CATALOG = {{}};
(function() {{
  try {{
    var el = document.getElementById('catalog-data');
    if (el) {{
      CATALOG = JSON.parse(el.textContent);
    }}
  }} catch(e) {{
    console.error('QMS: catalog parse error', e);
    var errEl = document.getElementById('add-error');
    if (errEl) {{
      errEl.textContent = 'Product catalog failed to load — please refresh.';
      errEl.style.display = 'block';
    }}
  }}
}})();

var _rid = 0;
var SEL  = [];

/* ═══ Initialise on load ════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', function() {{
  /* Restore selections if re-rendering after a validation error.
     We read from a <script type="application/json"> tag so the JSON
     is never HTML-entity-encoded (which would break JSON.parse). */
  try {{
    var prevEl = document.getElementById('prev-sel-data');
    if (prevEl) {{
      var prevJson = prevEl.textContent.trim();
      if (prevJson && prevJson !== '[]') {{
        SEL = JSON.parse(prevJson);
        /* Re-assign rids so _rid counter stays ahead of restored items */
        SEL.forEach(function(item) {{
          if (!item.rid) item.rid = ++_rid;
          else if (item.rid > _rid) _rid = item.rid;
          (item.components || []).forEach(function(c) {{
            if (!c.rid) c.rid = ++_rid;
            else if (c.rid > _rid) _rid = c.rid;
          }});
        }});
      }}
    }}
  }} catch(e) {{ console.warn('QMS: could not restore selections', e); }} 

  /* Activate the correct tax panel */
  var checked = document.querySelector('input[name="tax_type"]:checked');
  switchTax(checked ? checked.value : 'cgst_sgst');

  /* Shipping toggle */
  var sameChk = document.getElementById('ship_same_chk');
  if (sameChk && sameChk.checked) toggleShipSame(true);

  render();
}});

/* ═══ TAX PANEL SWITCHING ══════════════════════════════════ */
function switchTax(mode) {{
  ['cgst_sgst','igst','vat','exempt'].forEach(function(m) {{
    var el = document.getElementById('tp_' + m);
    if (!el) return;
    if (m === mode) {{
      el.classList.add('active');
    }} else {{
      el.classList.remove('active');
    }}
  }});
}}

/* CGST input → always mirror to SGST, update display */
function onGstRateChange(val) {{
  var v = parseFloat(val) || 0;
  document.getElementById('hid_cgst').value = v;
  document.getElementById('hid_sgst').value = v;
  var sgstEl = document.getElementById('inp_sgst');
  if (sgstEl) sgstEl.value = v;
  var totEl = document.getElementById('gst_total');
  if (totEl) totEl.textContent = (v * 2) + '%';
}}

/* ═══ SHIPPING SAME AS BILLING ═════════════════════════════ */
function toggleShipSame(checked) {{
  var sf = document.getElementById('ship-fields');
  if (sf) sf.style.display = checked ? 'none' : 'block';
}}

/* ═══ ADDRESS BOOK PICKER ═══════════════════════════════════ */
/* Saved addresses, embedded so selecting one fills the form with no round
   trip. Shape comes from address.PICKER_FIELDS. */
var ADDR_BOOK = {addr_book_json};

/* Set a <select> to a value, adding the option first if it is missing.
   Guards against a saved address holding a state or country the quotation
   form's own list does not offer. */
function setSelectValue(el, value) {{
  if (!el || !value) return;
  var found = Array.prototype.some.call(el.options, function(o) {{
    return o.value === value;
  }});
  if (!found) {{
    var opt = document.createElement('option');
    opt.value = value;
    opt.textContent = value;
    el.appendChild(opt);
  }}
  el.value = value;
}}

/* Fill the Bill To or Ship To block from a chosen address book entry.
   Every field the address supplies is overwritten — picking an address is an
   explicit act, so it wins over whatever was typed. Fields the address has no
   value for are left alone. */
function applyAddr(kind, sel) {{
  var a = ADDR_BOOK[sel.value];
  if (!a) return;

  var g   = function(id) {{ return document.getElementById(id); }};
  var set = function(id, v) {{ var el = g(id); if (el && v) el.value = v; }};

  /* line1 / line2 / landmark collapse into the one address textarea. */
  var street = [a.line1, a.line2, a.landmark].filter(Boolean).join('\\n');
  var addrEl = g(kind + '_addr');
  if (addrEl) addrEl.value = street;

  set(kind + '_city',  a.city);
  set(kind + '_pin',   a.pincode);
  set(kind + '_phone', a.phone);
  set(kind + '_gstin', a.gstin);
  setSelectValue(g(kind + '_state'),   a.state);
  setSelectValue(g(kind + '_country'), a.country || 'India');

  if (kind === 'bill') {{
    set('account_name',   a.company);
    set('contact_person', a.contact_name);
  }} else {{
    set('ship_acct_name', a.company);
    set('ship_email',     a.email);
    /* Choosing a delivery address contradicts "same as billing" — untick it
       so the fields the user just filled are not hidden from them. */
    var same = g('ship_same_chk');
    if (same && same.checked) {{
      same.checked = false;
      toggleShipSame(false);
    }}
  }}
}}

/* ═══ ADD ROOT PRODUCT ══════════════════════════════════════ */
function addProduct() {{
  var errEl  = document.getElementById('add-error');
  errEl.style.display = 'none';

  var selEl  = document.getElementById('picker-prod');
  var qtyEl  = document.getElementById('picker-qty');
  var pid    = selEl ? selEl.value : '';

  if (!pid) {{
    errEl.textContent = 'Please select a product.';
    errEl.style.display = 'block'; return;
  }}
  var qty = parseInt(qtyEl ? qtyEl.value : '1', 10);
  if (!qty || qty < 1) {{
    errEl.textContent = 'Quantity must be at least 1.';
    errEl.style.display = 'block'; return;
  }}
  var prod = CATALOG[pid];
  if (!prod) {{
    errEl.textContent = 'Product not found in catalog — try refreshing the page.';
    errEl.style.display = 'block'; return;
  }}

  SEL.push({{
    rid:        ++_rid,
    pid:        pid,
    name:       prod.name,
    part_no:    prod.part_no,
    unit:       prod.unit,
    qty:        qty,
    price:      prod.price,
    show_price: true,
    expanded:   false,
    components: []
  }});

  selEl.value = '';
  qtyEl.value = '1';
  render();
}}

/* ═══ RENDER ════════════════════════════════════════════════ */
function render() {{
  var container = document.getElementById('sel-container');
  var empty     = document.getElementById('empty-notice');
  if (!container) return;

  if (SEL.length === 0) {{
    container.innerHTML = '';
    if (empty) empty.style.display = 'block';
    saveJSON();
    return;
  }}
  if (empty) empty.style.display = 'none';

  container.innerHTML = SEL.map(function(item, idx) {{
    return renderRoot(item, idx);
  }}).join('');

  saveJSON();
}}

function renderRoot(item, idx) {{
  var prod    = CATALOG[item.pid] || {{}};
  var isAsm   = prod.type === 'assembly';
  var badge   = isAsm ? '<span class="badge-asm">Assembly</span>' : '';
  var expBtn  = isAsm
    ? '<button type="button" class="btn-expand" onclick="toggleExpand(' + idx + ')">'
        + (item.expanded ? '&#9660; Hide Components' : '&#9658; Components')
        + '</button>'
    : '';

  var compHtml = '';
  if (item.expanded) {{
    compHtml = '<div class="comp-area">';
    item.components.forEach(function(comp, cidx) {{
      compHtml += renderComp(comp, idx, cidx);
    }});
    compHtml += renderAddCompRow(idx);
    compHtml += '</div>';
  }}

  /* Use data-* attributes for field names — avoids all quote-escaping issues */
  return '<div class="sel-root" id="root-' + item.rid + '">'
    + '<div class="sel-root-head">'
    +   '<div class="sel-root-info">'
    +     '<div class="sel-name">' + escHtml(item.name) + badge + '</div>'
    +     '<div class="sel-pno">'  + escHtml(item.part_no) + '</div>'
    +   '</div>'
    +   '<div class="sel-root-ctrl">'
    +     ctrlBlock('Qty',
          '<input type="number" class="ctrl-input w-qty"'
          + ' data-sel="' + idx + '" data-field="qty"'
          + ' value="' + item.qty + '" min="1" step="1"'
          + ' onchange="onRootFieldChange(this)"/>')
    +     ctrlBlock('Price (&#8377;)',
          '<input type="number" class="ctrl-input w-price"'
          + ' data-sel="' + idx + '" data-field="price"'
          + ' value="' + item.price + '" min="0" step="1"'
          + ' onchange="onRootFieldChange(this)"/>')
    +     ctrlBlock('Show Price',
          '<input type="checkbox" class="ctrl-check"'
          + ' data-sel="' + idx + '" data-field="show_price"'
          + (item.show_price ? ' checked' : '')
          + ' onchange="onRootFieldChange(this)"/>')
    +     expBtn
    +     '<button type="button" class="btn-rm" onclick="removeRoot(' + idx + ')">&#215;</button>'
    +   '</div>'
    + '</div>'
    + compHtml
    + '</div>';
}}

function renderComp(comp, pidx, cidx) {{
  return '<div class="comp-row">'
    + '<div class="comp-info">'
    +   '<div class="comp-name">&#8627;&nbsp;' + escHtml(comp.name) + '</div>'
    +   '<div class="comp-pno">' + escHtml(comp.part_no) + ' &nbsp;|&nbsp; ' + escHtml(comp.unit) + '</div>'
    + '</div>'
    + '<div class="comp-ctrl">'
    +   ctrlBlock('Qty',
        '<input type="number" class="ctrl-input w-qty"'
        + ' data-pidx="' + pidx + '" data-cidx="' + cidx + '" data-field="qty"'
        + ' value="' + comp.qty + '" min="0.001" step="any"'
        + ' onchange="onCompFieldChange(this)"/>')
    +   ctrlBlock('Price (&#8377;)',
        '<input type="number" class="ctrl-input w-price"'
        + ' data-pidx="' + pidx + '" data-cidx="' + cidx + '" data-field="price"'
        + ' value="' + comp.price + '" min="0" step="1"'
        + ' onchange="onCompFieldChange(this)"/>')
    +   ctrlBlock('Show Price',
        '<input type="checkbox" class="ctrl-check"'
        + ' data-pidx="' + pidx + '" data-cidx="' + cidx + '" data-field="show_price"'
        + (comp.show_price ? ' checked' : '')
        + ' onchange="onCompFieldChange(this)"/>')
    +   '<button type="button" class="btn-rm" style="width:26px;height:26px;font-size:.8rem;"'
    +     ' onclick="removeComp(' + pidx + ',' + cidx + ')">&#215;</button>'
    + '</div>'
    + '</div>';
}}

function renderAddCompRow(pidx) {{
  var optHtml = document.getElementById('comp-opts-tpl').innerHTML;
  return '<div class="comp-picker">'
    + '<select id="cp-sel-' + pidx + '">' + optHtml + '</select>'
    + '<input type="number" id="cp-qty-' + pidx + '" value="1" min="0.001" step="any" placeholder="Qty"/>'
    + '<button type="button" class="btn-add-comp" onclick="addComp(' + pidx + ')">&#43; Add Component</button>'
    + '</div>';
}}

function ctrlBlock(label, inputHtml) {{
  return '<div class="ctrl-block"><div class="ctrl-lbl">' + label + '</div>' + inputHtml + '</div>';
}}

function escHtml(s) {{
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

/* ═══ FIELD-CHANGE DISPATCHERS (read data-* — no string quoting needed) ═ */
function onRootFieldChange(el) {{
  var idx   = parseInt(el.dataset.sel, 10);
  var field = el.dataset.field;
  var val   = (el.type === 'checkbox') ? el.checked : el.value;
  onRootChange(idx, field, val);
}}

function onCompFieldChange(el) {{
  var pidx  = parseInt(el.dataset.pidx, 10);
  var cidx  = parseInt(el.dataset.cidx, 10);
  var field = el.dataset.field;
  var val   = (el.type === 'checkbox') ? el.checked : el.value;
  onCompChange(pidx, cidx, field, val);
}}

/* ═══ MUTATIONS ═════════════════════════════════════════════ */
function onRootChange(idx, field, val) {{
  if (field === 'qty')        SEL[idx].qty        = parseFloat(val) || 1;
  else if (field === 'price') SEL[idx].price      = parseFloat(val) || 0;
  else if (field === 'show_price') SEL[idx].show_price = val;
  saveJSON();
}}

function onCompChange(pidx, cidx, field, val) {{
  var comp = SEL[pidx].components[cidx];
  if (field === 'qty')        comp.qty        = parseFloat(val) || 1;
  else if (field === 'price') comp.price      = parseFloat(val) || 0;
  else if (field === 'show_price') comp.show_price = val;
  saveJSON();
}}

function removeRoot(idx) {{ SEL.splice(idx, 1); render(); }}
function removeComp(pidx, cidx) {{ SEL[pidx].components.splice(cidx, 1); render(); }}

function toggleExpand(idx) {{
  var item = SEL[idx];
  item.expanded = !item.expanded;
  if (item.expanded && item.components.length === 0) {{
    var prod = CATALOG[item.pid];
    if (prod && prod.children) {{
      item.components = prod.children.map(function(ch) {{
        return {{
          rid:        ++_rid,
          pid:        ch.pid,
          name:       ch.name,
          part_no:    ch.part_no,
          unit:       ch.unit,
          qty:        ch.qty * item.qty,
          price:      ch.price,
          show_price: false
        }};
      }});
    }}
  }}
  render();
}}

function addComp(pidx) {{
  var selEl = document.getElementById('cp-sel-' + pidx);
  var qtyEl = document.getElementById('cp-qty-' + pidx);
  var pid   = selEl ? selEl.value : '';
  if (!pid) return;
  var prod  = CATALOG[pid];
  if (!prod) return;
  var qty   = parseFloat(qtyEl ? qtyEl.value : '1') || 1;

  SEL[pidx].components.push({{
    rid:        ++_rid,
    pid:        pid,
    name:       prod.name,
    part_no:    prod.part_no,
    unit:       prod.unit,
    qty:        qty,
    price:      prod.price,
    show_price: false
  }});
  render();
}}

/* ═══ SERIALISE ═════════════════════════════════════════════ */
function saveJSON() {{
  var el = document.getElementById('selections_json');
  if (el) el.value = JSON.stringify(SEL);
}}

/* ═══ DEMO DATA ═════════════════════════════════════════════ */
function fillDemoData() {{
  var today = new Date().toISOString().slice(0,10);
  var exp   = new Date(Date.now() + 30*24*3600*1000).toISOString().slice(0,10);

  function setVal(id, val) {{
    var el = document.getElementById(id);
    if (el) el.value = val;
  }}
  function setSel(id, val) {{
    var el = document.getElementById(id);
    if (!el) return;
    for (var i = 0; i < el.options.length; i++) {{
      if (el.options[i].value === val || el.options[i].text === val) {{
        el.selectedIndex = i; break;
      }}
    }}
  }}

  setVal('qtn_date',       today);
  setVal('buyer_ref',      'TEST-RFQ-001');
  setVal('other_ref',      'fire hydrant system / main pump 2850 LPM @ 104M HEAD');
  setVal('validity_days',  '15');
  setVal('lead_owner',     'Sales Engineer');
  setVal('exp_closing',    exp);
  setVal('auth_signatory', 'Authorised Signatory');
  setVal('assigned_to',    'Sales Engineer');

  setSel('sales_stage',     'Budgetary - Stage II');
  setSel('lead_source',     'Cold Call');
  setSel('lead_type',       'Builder / Developer');
  setSel('lead_subtype',    'HYDRANT SYSTEM');
  setSel('qtn_type',        'Fire Fighting System');
  setSel('company_branch',  '{company_name}');
  setSel('region',          'Head Office');
  setSel('incoterms',       'FOR');
  setSel('payment_terms',   '100% Against Proforma Invoice');
  setSel('delivery_terms',  'Ex-Works');
  setSel('dispatch_through','In Clients Scope');

  setVal('account_name',   'M/s. Sample Builders Pvt Ltd');
  setVal('contact_person', 'Mr. Sample Name, Purchase');
  /* Placeholder customer — deliberately not a real firm, address or GSTIN. */
  setVal('bill_addr',      'Unit 12, Sample Corporate Park,\\nPlot 5, Sector 18');
  setSel('bill_country',   'India');
  setSel('bill_state',     'Maharashtra');
  setVal('bill_city',      'Navi Mumbai');
  setVal('bill_pin',       '400703');
  setVal('bill_phone',     '00000 00000');
  setVal('bill_gstin',     '27XXXXX0000X1ZX');

  var sameChk = document.getElementById('ship_same_chk');
  if (sameChk) {{ sameChk.checked = true; toggleShipSame(true); }}

  /* Tax: CGST+SGST 9%+9% */
  var cgstRadio = document.getElementById('tr_cgst');
  if (cgstRadio) {{ cgstRadio.checked = true; switchTax('cgst_sgst'); }}
  setVal('inp_cgst', '9');
  onGstRateChange('9');

  /* Add first assembly (or any product) from catalog */
  var demoPid = null;
  var keys = Object.keys(CATALOG);
  for (var i = 0; i < keys.length; i++) {{
    if (CATALOG[keys[i]].type === 'assembly') {{ demoPid = keys[i]; break; }}
  }}
  if (!demoPid && keys.length) demoPid = keys[0];

  if (demoPid) {{
    /* Don't add duplicate */
    var already = SEL.some(function(s) {{ return s.pid === demoPid; }});
    if (!already) {{
      var prod = CATALOG[demoPid];
      SEL.push({{
        rid:        ++_rid,
        pid:        demoPid,
        name:       prod.name,
        part_no:    prod.part_no,
        unit:       prod.unit,
        qty:        2,
        price:      prod.price,
        show_price: true,
        expanded:   false,
        components: []
      }});
      render();
    }}
  }} else {{
    var ae = document.getElementById('add-error');
    ae.textContent = 'No products in catalog yet — go to Products and add some first.';
    ae.style.display = 'block';
  }}

  window.scrollTo({{ top: 0, behavior: 'smooth' }});
}}

/* ═══ FORM GUARD ════════════════════════════════════════════ */
document.getElementById('qf').addEventListener('submit', function(e) {{
  saveJSON();
  if (SEL.length === 0) {{
    e.preventDefault();
    var errEl = document.getElementById('add-error');
    errEl.textContent = 'Add at least one product before generating the quotation.';
    errEl.style.display = 'block';
    errEl.scrollIntoView({{ behavior:'smooth', block:'center' }});
  }}
}});
</script>
</body></html>"""

    # Map Python values into the template placeholders (no JS braces touched)
    html = page.format(
        base_styles         = BASE_STYLES,
        qtn_styles          = QUOTATION_STYLES,
        nav                 = _nav(),
        company_name        = COMPANY_NAME,
        app_subtitle        = B.APP_SUBTITLE,
        head_icon           = B.HEAD_ICON,
        page_title          = B.page_title("New Quotation"),
        list_url            = list_url,
        error_html          = error_html,
        catalog_json        = catalog_json,
        prev_sel            = prev_selections,   # goes into <script> tag, NOT an HTML attribute
        next_ref            = _next_ref(),
        today               = today_str,
        vdays               = _fv("validity_days", "10"),
        buyer_ref           = _fv("buyer_ref"),
        other_ref           = _fv("other_ref"),
        rc_checked          = "checked" if _fv("rate_contract") == "1" else "",
        exp_closing         = _fv("exp_closing"),
        delivery_date       = _fv("delivery_date"),
        lead_owner          = _fv("lead_owner"),
        auth_signatory      = _fv("auth_signatory"),
        assigned_to         = _fv("assigned_to"),
        amend_no            = _fv("amend_no", "Original"),
        account_name        = _fv("account_name"),
        contact_person      = _fv("contact_person"),
        addr_options_bill   = picker_options("— fill from address book —"),
        addr_options_ship   = picker_options("— fill from address book —"),
        addr_book_json      = json.dumps(picker_payload()),
        address_url         = url_for("address.list_addresses"),
        bill_addr           = _fv("bill_addr"),
        bill_city           = _fv("bill_city"),
        bill_pin            = _fv("bill_pin"),
        bill_phone          = _fv("bill_phone"),
        bill_gstin          = _fv("bill_gstin"),
        ship_same_checked   = "checked" if _fv("ship_same") == "1" else "",
        ship_acct_name      = _fv("ship_acct_name"),
        ship_email          = _fv("ship_email"),
        ship_addr           = _fv("ship_addr"),
        ship_city           = _fv("ship_city"),
        ship_pin            = _fv("ship_pin"),
        ship_phone          = _fv("ship_phone"),
        ship_fax            = _fv("ship_fax"),
        ship_gstin          = _fv("ship_gstin"),
        prod_opts           = prod_opts,
        comp_opts           = comp_opts,
        init_cgst           = init_cgst,
        init_sgst           = init_sgst,
        init_igst           = init_igst,
        init_vat            = init_vat,
        gst_total_display   = f"{_init_gst_total:g}",
        cgst_checked        = "checked" if init_tax_type == "cgst_sgst" else "",
        igst_checked        = "checked" if init_tax_type == "igst"      else "",
        vat_checked         = "checked" if init_tax_type == "vat"       else "",
        exempt_checked      = "checked" if init_tax_type == "exempt"    else "",
        # select dropdowns
        sel_qtn_type        = _sel_opts("qtn_type",        _TYPES,         "Fire Fighting System",               _fv("qtn_type")),
        sel_sales_stage     = _sel_opts("sales_stage",     _SALES_STAGES,  P.DEFAULT_STAGE,                      _fv("sales_stage")),
        sel_lead_source     = _sel_opts("lead_source",     _LEAD_SOURCES,  "Cold Call",                          _fv("lead_source")),
        sel_lead_type       = _sel_opts("lead_type",       _LEAD_TYPES,    "Builder / Developer",                _fv("lead_type")),
        sel_lead_subtype    = _sel_opts("lead_subtype",    _LEAD_SUBTYPES, "HYDRANT SYSTEM",                     _fv("lead_subtype")),
        sel_company_branch  = _sel_opts("company_branch",  _BRANCHES,      B.COMPANY_NAME,                       _fv("company_branch")),
        sel_incoterms       = _sel_opts("incoterms",       _INCOTERMS,     "FOR",                                _fv("incoterms")),
        sel_payment_terms   = _sel_opts("payment_terms",   _PAY_TERMS,     "100% Against Proforma Invoice",      _fv("payment_terms")),
        sel_delivery_terms  = _sel_opts("delivery_terms",  _DEL_TERMS,     "Ex-Works",                           _fv("delivery_terms")),
        sel_dispatch_through= _sel_opts("dispatch_through",_DISPATCH,      "In Clients Scope",                   _fv("dispatch_through")),
        sel_region          = _sel_opts("region",          _REGIONS,       "Head Office",                        _fv("region")),
        sel_bill_country    = _sel_opts("bill_country",    _COUNTRIES,     "India",                              _fv("bill_country", "India")),
        sel_bill_state      = _sel_opts("bill_state",      _STATES_IN,     "Maharashtra",                        _fv("bill_state",   "Maharashtra")),
        sel_ship_country    = _sel_opts("ship_country",    _COUNTRIES,     "India",                              _fv("ship_country", "India")),
        sel_ship_state      = _sel_opts("ship_state",      _STATES_IN,     "Maharashtra",                        _fv("ship_state",   "Maharashtra")),
    )
    return render_template_string(html)


# =============================================================================
# VIEW ROUTE
# =============================================================================

@quotation_bp.route("/<id>/update", methods=["POST"])
def update_quotation(id: str):
    """
    Update a quotation's commercial status — stage, customer PO, lost reason.

    Deliberately does NOT touch line items, pricing or addresses: those belong
    to the document, and a quotation that has already gone out should not have
    its numbers silently rewritten. All validation lives in pipeline.py.
    """
    q = STORE["quotations"].get(id)
    if not q:
        return redirect(url_for("quotation.list_quotations",
                                msg="Quotation not found.", type="error"))

    ok, message = P.apply_update(q, request.form)
    return redirect(url_for("quotation.view_quotation", id=id,
                            msg=message, type="success" if ok else "error"))


@quotation_bp.route("/view/<id>")
def view_quotation(id: str):
    q = STORE["quotations"].get(id)
    if not q:
        return redirect(url_for("quotation.list_quotations", msg="Quotation not found.", type="error"))

    list_url   = url_for("quotation.list_quotations")
    create_url = url_for("quotation.create_quotation")
    line_items = q["line_items"]

    # ── Proforma invoices raised against this quotation ─────────────────
    # Read STORE["proformas"] directly rather than importing proforma.py:
    # that module imports *this* one for the document formatters, so an import
    # the other way would be a cycle. url_for needs only the endpoint name.
    pi_url  = url_for("proforma.create_proforma", qid=id)
    pi_rows = sorted(
        ((p_id, p) for p_id, p in STORE["proformas"].items()
         if p.get("quotation_id") == id),
        key=lambda kv: kv[1].get("ref", ""),
    )
    pi_strip_html = ""
    if pi_rows:
        chips = "".join(
            f'<a class="pi-chip" href="{url_for("proforma.view_proforma", id=p_id)}">'
            f'{P.esc(p.get("ref"))} &middot; {p.get("date", "")} &middot; '
            f'&#8377;&nbsp;{float(p.get("amount_due") or 0):,.0f}</a>'
            for p_id, p in pi_rows
        )
        pi_strip_html = f"""
        <div class="pi-block">
          <span class="pi-lbl">Proforma invoices raised</span>
          <div class="pi-strip">{chips}</div>
        </div>"""

    # ── Deal panel (screen only — hidden by the @media print rule) ──────
    P.ensure_fields(q)
    update_url = url_for("quotation.update_quotation", id=id)
    stage_now  = P.stage_of(q)

    msg        = request.args.get("msg")
    msg_type   = request.args.get("type", "success")
    alert_html = ""
    if msg:
        icon = "&#10003;" if msg_type == "success" else "&#10007;"
        alert_html = f'<div class="alert alert-{msg_type}">{icon} {msg}</div>'

    # PO vs quoted — the gap between what we quoted and what they ordered.
    po_val, quoted = float(q.get("po_value") or 0.0), float(q.get("grand_total") or 0.0)
    variance_html = ""
    if po_val and quoted:
        diff = po_val - quoted
        cls  = "up" if diff >= 0 else "down"
        sign = "+" if diff >= 0 else "&minus;"
        variance_html = (
            '<span class="deal-variance">PO vs quoted: '
            f'<b class="{cls}">{sign}&#8377;&nbsp;{abs(diff):,.0f} '
            f'({sign}{abs(diff / quoted * 100.0):.1f}%)</b></span>'
        )

    # Quick actions sit in their own little forms so they stay siblings of the
    # main form — nesting <form> inside <form> is invalid HTML and silently
    # drops the inner one in most browsers.
    def _quick(stage: str, label: str, cls: str) -> str:
        if stage_now == stage:
            return ""
        return (f'<form method="POST" action="{update_url}">'
                f'<input type="hidden" name="sales_stage" value="{stage}"/>'
                f'<button type="submit" class="{cls}">{label}</button></form>')

    quick_html = (
        _quick(P.STAGE_WON,  "&#10003;&nbsp;Mark Won",  "qa-won") +
        _quick(P.STAGE_LOST, "&#10007;&nbsp;Mark Lost", "qa-lost")
    )

    # The lost-reason box is only meaningful on a lost deal.
    lost_html = ""
    if stage_now == P.STAGE_LOST:
        lost_html = (
            '<div class="form-group" style="grid-column:span 2;">'
            '<label for="lost_reason">Reason Lost</label>'
            f'<input type="text" id="lost_reason" name="lost_reason" '
            f'value="{P.esc(q.get("lost_reason"))}" placeholder="Price / timeline / competitor…"/>'
            '</div>'
        )

    deal_panel_html = f"""
<div class="deal-panel">
  <div class="deal-head">
    <div>
      <div class="dh-title">Deal Status</div>
      <div style="margin-top:.4rem;">{P.stage_badge(stage_now)}</div>
    </div>
    <div class="deal-quick">{quick_html}</div>
  </div>

  <form method="POST" action="{update_url}">
    <div class="deal-grid">
      <div class="form-group">
        <label for="sales_stage">Sales Stage</label>
        {_sel_opts("sales_stage", _SALES_STAGES, stage_now, stage_now)}
      </div>
      <div class="form-group">
        <label for="po_number">Customer PO No.</label>
        <input type="text" id="po_number" name="po_number"
               value="{P.esc(q.get('po_number'))}" placeholder="their PO number"/>
      </div>
      <div class="form-group">
        <label for="po_date">PO Date</label>
        <input type="date" id="po_date" name="po_date" value="{P.esc(q.get('po_date'))}"/>
      </div>
      <div class="form-group">
        <label for="po_value">PO Value (&#8377;)</label>
        <input type="text" id="po_value" name="po_value"
               value="{P.fmt_money(po_val) if po_val else ''}" placeholder="{quoted:,.0f}"/>
      </div>
      {lost_html}
      <div class="form-group" style="grid-column:span 2;">
        <label for="stage_note">Note <span style="font-weight:500;text-transform:none;">(optional)</span></label>
        <input type="text" id="stage_note" name="stage_note" placeholder="what changed, and why"/>
      </div>
    </div>
    <div class="deal-actions">
      <button type="submit" class="btn">Save Status</button>
      {variance_html}
    </div>
  </form>

  {pi_strip_html}
  {P.history_html(q)}
</div>
"""

    # ── Line-item rows ─────────────────────────────────────────────────
    sno        = 0
    total_qty  = 0.0
    table_rows = ""

    for row in line_items:
        sno    += 1
        depth   = row.get("depth", 0)
        row_cls = "row-assembly" if row["type"] == "assembly" else "row-item"
        indent  = "indent-1" if depth == 1 else ("indent-2" if depth >= 2 else "")
        if depth == 0:
            total_qty += row["qty"]

        # A row priced at 0.00 is the "included, no separate charge"
        # convention (show_price off) — it prints as 0.00 rather than being
        # blanked, which is how the trade reads a bundled sub-component.
        price_s = _inr(row["price"])
        total_s = _inr(row["total"])
        hsn     = row.get("hsn") or ""

        table_rows += f"""
        <tr class="{row_cls}">
          <td class="c-sno">{sno}</td>
          <td class="c-partno">{row['part_no']}</td>
          <td class="c-desc {indent}">{row['name']}</td>
          <td class="c-hsn">{hsn}</td>
          <td class="c-qty">{_fmt_qty(row['qty'])}</td>
          <td class="c-unit">{row['unit']}</td>
          <td class="c-price">{price_s}</td>
          <td class="c-total">{total_s}</td>
        </tr>"""

    # ── Subtotal / tax / grand total rows ──────────────────────────────
    subtotal  = q.get("subtotal", q["grand_total"])
    tax_info  = q.get("tax_info", {"total": 0.0})
    tax_type  = q.get("tax_type", "exempt")

    has_tax = tax_type != "exempt" and tax_info.get("total", 0) > 0

    if has_tax:
        # Subtotal carries no quantity — the qty total belongs on the closing
        # row only, and summing mixed units (Nos / Mtr / Set) twice on the
        # same document reads as a mistake.
        table_rows += f"""
        <tr class="row-sum">
          <td colspan="4" class="sum-lbl">Subtotal</td>
          <td class="c-qty"></td>
          <td class="c-unit"></td>
          <td class="c-price"></td>
          <td class="c-total">{_inr(subtotal)}</td>
        </tr>"""

        # Individual tax lines — pull rate from tax_info dict directly
        rate_keys  = {"CGST": "cgst_rate", "SGST": "sgst_rate",
                      "IGST": "igst_rate", "VAT":  "vat_rate"}
        skip_keys  = {"total", *rate_keys.values()}
        for tname, tamt in tax_info.items():
            if tname in skip_keys:
                continue
            r = tax_info.get(rate_keys.get(tname, ""), 0)
            rate_label = f" @ {r:g}%" if r else ""

            table_rows += f"""
            <tr class="row-sum">
              <td colspan="4" class="sum-lbl">{tname}{rate_label}</td>
              <td class="c-qty"></td><td class="c-unit"></td><td class="c-price"></td>
              <td class="c-total">{_inr(tamt)}</td>
            </tr>"""

    # Closing row
    table_rows += f"""
    <tr class="row-total row-sum">
      <td colspan="4" class="sum-lbl">{"Grand Total" if has_tax else "Total"}</td>
      <td class="c-qty">{_fmt_qty(total_qty)}</td>
      <td class="c-unit"></td>
      <td class="c-price"></td>
      <td class="c-total">{_inr(q['grand_total'])}</td>
    </tr>"""

    # ── Header meta, in two columns ────────────────────────────────────
    # Deal-desk fields (sales stage, lead type) are deliberately NOT here —
    # they are our internal pipeline data and have no business on a document
    # the customer reads. They stay on the deal panel above.
    validity = q.get("validity_days") or ""
    meta_col_1 = (
        _meta("Quotation No.",        q["ref"]) +
        _meta("Buyer Ref. No.",       q.get("buyer_ref")      or "") +
        _meta("Mode/Term of Payment", q.get("payment_terms")  or "") +
        _meta("Terms of Delivery",    q.get("delivery_terms") or "")
    )
    meta_col_2 = (
        _meta("Date",             q["date"]) +
        _meta("Other Ref.",       q.get("other_ref")        or "") +
        _meta("Dispatch Through", q.get("dispatch_through") or "") +
        _meta("Validity",         f"{validity} days" if validity else "") +
        _meta("Incoterms",        q.get("incoterms")        or "")
    )

    # First line of the address block is the customer's name — set it bold, the
    # way every quotation in the trade does.
    to_lines   = [ln for ln in (q.get("to") or "").strip().split("\n")]
    to_display = ""
    if to_lines and to_lines[0].strip():
        rest = "\n".join(to_lines[1:]).strip()
        to_display = f'<span class="dh-name">{to_lines[0]}</span>'
        if rest:
            to_display += f'\n{rest}'

    ship_parts = []
    if not q.get("ship_same"):
        sname = q.get("ship_acct_name") or q.get("account_name") or ""
        if sname:  ship_parts.append(sname)
        if q.get("ship_addr"):   ship_parts.append(q["ship_addr"])
        scity = ", ".join(filter(None, [q.get("ship_city", ""), q.get("ship_state", "")]))
        if scity or q.get("ship_pin"):
            ship_parts.append(f"{scity} – {q.get('ship_pin','')}".strip(" –"))
        if q.get("ship_phone"): ship_parts.append(f"Ph: {q['ship_phone']}")
        if q.get("ship_gstin"): ship_parts.append(f"GSTIN: {q['ship_gstin']}")

    # Ship To only earns space when it actually differs. "Same as Billing" in
    # its own column is a whole column of nothing.
    ship_html = ""
    if ship_parts:
        ship_html = (
            '<div class="dh-ship"><span class="dh-lbl">Ship To</span>'
            f'<div class="dh-body">{chr(10).join(ship_parts)}</div></div>'
        )

    tnc_terms = _build_tnc(q)
    tnc_html  = "".join(
        f'<li><span class="tnc-num">{i+1}.</span><span>{t}</span></li>'
        for i, t in enumerate(tnc_terms)
    )

    words     = _amount_in_words(q["grand_total"])
    comp_br   = q.get("company_branch") or COMPANY_NAME
    signatory = q.get("auth_signatory") or COMPANY_SIGNATORY

    template = f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(q['ref'] + " Quotation")}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}{VIEW_DOC_STYLES}{QUOTATION_STYLES}{P.PIPELINE_STYLES}
</head>
<body>
{_nav()}
<main>

<div class="screen-acts">
  <h1 style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px;">
    Quotation <span style="color:var(--brand);">{q['ref']}</span>
  </h1>
  <div style="display:flex;gap:.7rem;flex-wrap:wrap;">
    <a href="{list_url}"   class="btn btn-ghost">&#8592; All Quotations</a>
    <a href="{create_url}" class="btn btn-ghost">+ New</a>
    <a href="{pi_url}"     class="btn btn-ghost">&#129534;&nbsp;Raise Proforma</a>
    <button class="btn" onclick="window.print()">&#128438;&nbsp;Print</button>
  </div>
</div>

{alert_html}
{deal_panel_html}

<div class="doc-outer">
<div class="quotation-doc">

  <!-- thead/tfoot of .page-frame are the only way to repeat a band on every
       printed page; see the note in VIEW_DOC_STYLES. -->
  <table class="page-frame">
  <thead><tr><td>
    <div class="lh">
      <div>
        <div class="lh-name">{B.name_html("lh-name-fire")}</div>
        <div class="lh-tag">&#8212; {COMPANY_TAGLINE} &#8212;</div>
        {f'<div class="lh-legal">{COMPANY_LEGAL}</div>' if COMPANY_LEGAL else ''}
      </div>
      <div class="lh-mark">{B.logo_img(56, doc=True)}</div>
    </div>
    <div class="lh-rule"></div>
    <div class="lh-addr">Registered Address: {B.field(COMPANY_ADDR, "registered address")}</div>
    <div class="lh-contact">
      Phone: {B.field(COMPANY_PHONE, "phone")}<span class="sep">|</span>
      Email: {B.field(COMPANY_EMAIL, "e-mail")}
      {f'<span class="sep">|</span>Web: {COMPANY_WEB}' if COMPANY_WEB else ''}
      {f'<span class="sep">|</span>Branches: {COMPANY_BRANCHES}' if COMPANY_BRANCHES else ''}
    </div>
  </td></tr></thead>

  <tfoot><tr><td>
    <div class="lh-foot">{COMPANY_LEGAL or COMPANY_NAME} &middot; {COMPANY_TAGLINE}</div>
  </td></tr></tfoot>

  <tbody><tr><td>

  <div class="doc-box">
    <div class="doc-title">QUOTATION</div>

    <div class="doc-header">
      <div class="dh-cell">
        <span class="dh-lbl">To</span>
        <div class="dh-body">{to_display}</div>
        {ship_html}
      </div>
      <div class="dh-cell">{meta_col_1}</div>
      <div class="dh-cell">{meta_col_2}</div>
    </div>

    <div class="items-wrap">
      <table class="q-table">
        <thead><tr>
          <th class="c-sno">S.No</th>
          <th class="c-partno">Part No</th>
          <th class="c-desc">Description of Goods</th>
          <th class="c-hsn">HSN/SAC</th>
          <th class="c-qty">Qty</th>
          <th class="c-unit">Unit</th>
          <th class="c-price">Unit Price</th>
          <th class="c-total">Total Price</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>

    <div class="amount-words">Amount Chargeable (in words) : {words}</div>
  </div>

  <div class="tnc-section">
    <div class="tnc-title">{B.COMPANY_SHORT} Terms and Conditions</div>
    <ol class="tnc-ol">{tnc_html}</ol>
  </div>

  <div class="sig-block">
    <div class="sig-kv">
      <span>GSTIN</span><span>: <b>{B.field(COMPANY_GSTIN, "GSTIN")}</b></span>
      <span>PAN No.</span><span>: <b>{B.field(COMPANY_PAN, "PAN")}</b></span>
    </div>
    <div class="sig-right">
      <div class="sig-for">For {comp_br}</div>
      <div class="sig-name">{signatory}</div>
    </div>
  </div>
  <div class="sig-note">This is a Computer Generated Document, no signature required</div>

  </td></tr></tbody>
  </table>

</div>
</div>

<footer style="margin-top:1.75rem;">
  <p>{COMPANY_NAME} · {B.APP_SUBTITLE} · quotation document</p>
</footer>
</main>
</body></html>"""
    return render_template_string(template)