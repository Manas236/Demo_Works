"""
extraitems.py — EXTRA ITEMS on a document, and its optional project link
========================================================================

Lifted out of `challan.py` on 17 November 2026 (CLIENT_CHANGES.md §0
seventy-sixth block) at its SECOND consumer, the Product Inquiry
(`po_draft.py`) — the same move `boqpick.py` made for the BOQ line picker.

⚠ **Why a leaf and not "po_draft imports challan".** `po_draft.py` and
  `challan.py` may not know about each other —
  `tests/test_import_directions.py::test_the_two_consumers_of_the_picker_do_
  not_know_about_each_other`. Two BOQ-chain documents share COMPONENTS, never
  each other. So the extras repeater lives here and both render through it.

⚠ **The challan's output is byte-for-byte what it was.** Every default here
  is the challan's own string; `challan.py` keeps its function names as thin
  wrappers. The inquiry asks for three more cells — Make, Pcs and a picture —
  through flags that default off.

What an extra item IS (unchanged from the challan): a row the operator typed or
picked from the Specification library, stored with `line_id: None` and
`extra: True`. Every reader that keys on `line_id` already skips a row with no
id, which is the whole of why an extra is never tallied against a BOQ line. The
library is READ (`buypick.resolve()`), never written.

Imports: `pipeline`, `store`, and the leaves `buypick`, `units` and
`lineimage`. Nothing upstream.
"""

import buypick as BYP
import lineimage as LI
import pipeline as P
import units as UN
from store import STORE

# The challan's own figures, which are this module's defaults.
DEFAULT_EXTRA_ROWS = 1
MAX_EXTRA_ROWS = 100
EXTRA_DESC_MAX = 500
UNIT_MAX = 30
PCS_MAX = 16          # `po_draft.PCS_MAX`, the picker's


def is_extra(row) -> bool:
    """A row the operator added by hand — never a BOQ line."""
    return bool(isinstance(row, dict) and row.get("extra")
                and not str(row.get("line_id") or "").strip())


def project_link_from(form) -> tuple:
    """
    `({project_id, project_name}, error)` for a no-BOQ document's optional
    project. The name is SNAPSHOTTED, as on a charge, so the register still
    reads if the project is renamed or deleted later.
    """
    pid = (form.get("project_id") or "").strip()[:64]
    if not pid:
        return {"project_id": "", "project_name": ""}, ""
    proj = (STORE.get("projects") or {}).get(pid)
    if not proj:
        return {}, "That project no longer exists. Pick another, or leave it blank."
    return {"project_id": pid, "project_name": str(proj.get("name") or "")}, ""


def project_select_html(selected: str = "", noun: str = "challan") -> str:
    """A no-BOQ document's optional project — `charge.py`'s picker."""
    opts = '<option value="">No project</option>'
    for pid, p in sorted((STORE.get("projects") or {}).items(),
                         key=lambda kv: str(kv[1].get("name") or "")):
        sel = " selected" if pid == selected else ""
        opts += f'<option value="{P.esc(pid)}"{sel}>{P.esc(p.get("name"))}</option>'
    return (f'<div class="form-group"><label for="project_id">Project (optional)</label>'
            f'<select id="project_id" name="project_id">{opts}</select>'
            f'<div class="fld-hint">Shows this {noun} on that project&rsquo;s page.</div></div>')


def _allowed_for(row: dict, posted_id: str, stored: list) -> dict:
    """
    The line a posted picture is validated against: a stored extra already
    carrying that exact picture (so an edit never drops it), else the row
    itself — whose library is the one its description offers. A crafted id is
    in neither and `lineimage.apply_choice()` ignores it.
    """
    iid = LI.valid_id(posted_id)
    if iid:
        for s in stored or []:
            if LI.image_of(s) == iid:
                return s
    return row


def parse_extras(form, *, desc_max: int = EXTRA_DESC_MAX,
                 with_make: bool = False, make_max: int = 60,
                 with_pcs: bool = False, with_image: bool = False,
                 stored: list = None,
                 with_ref: bool = False, allowed_refs=None,
                 what_msg: str = "Say what is going out.",
                 cap_msg: str = "Raise more than one challan.") -> tuple:
    """
    `(rows, error)` — the extra items typed or picked on the form.

    Per row: a **description** (typed, or the Specification-library pick's
    name when the box is left blank), a **quantity above 0**, and a unit (the
    pick's unit when none is chosen). A row left wholly blank is skipped. The
    pick is re-read from the library NOW (`buypick.resolve()`); the browser's
    copy is never trusted, and the library is never written.

    `with_make` / `with_pcs` / `with_image` read `xi_make`, `xi_pcs` and
    `xi_image` positionally — every row the form draws posts exactly one of
    each, so the lists line up. `stored` is the document's extras as saved,
    for a picture already on one of them.
    """
    descs = form.getlist("xi_desc")
    qtys = form.getlist("xi_qty")
    units = form.getlist("xi_unit")
    picks = form.getlist("line_product_id")
    makes = form.getlist("xi_make") if with_make else []
    pcses = form.getlist("xi_pcs") if with_pcs else []
    images = form.getlist("xi_image") if with_image else []
    # `with_ref` (17 Nov 2026, §0 seventy-eighth block): a hidden `xi_ref`
    # per row carries the purchase-order line a challan row came from
    # (`po_key`) through an edit. Kept only when it is in `allowed_refs`, so a
    # crafted POST cannot point a row at another order's line.
    refs = form.getlist("xi_ref") if with_ref else []
    n_rows = max(len(descs), len(qtys), len(units), len(picks))

    def _at(seq, n):
        return str(seq[n] if n < len(seq) else "").strip()

    out = []
    for n in range(n_rows):
        desc = _at(descs, n)[:desc_max]
        qty_raw = _at(qtys, n)
        unit = _at(units, n)[:UNIT_MAX]
        pick = _at(picks, n)
        make = _at(makes, n)[:make_max]
        pcs = _at(pcses, n)[:PCS_MAX]
        if not (desc or qty_raw or pick or make or pcs):
            continue        # a unit alone is the dropdown's default, not a row
        ident = {}
        if pick:
            if not pick.startswith(BYP.SPEC_PREFIX):
                return [], f"Extra item {n + 1}: pick from the specification library, or type it."
            ident, err = BYP.resolve(pick)
            if err:
                return [], f"Extra item {n + 1}: {err}"
        desc = desc or str(ident.get("name") or "")[:desc_max]
        if not desc:
            return [], f"Extra item {n + 1} has no description. {what_msg}"
        try:
            qty = float(qty_raw)
        except ValueError:
            return [], f"Quantity for '{desc}' must be a number above 0."
        if not qty > 0:
            return [], f"Quantity for '{desc}' must be above 0."
        unit = unit or str(ident.get("unit") or "")[:UNIT_MAX]
        row = {"line_id": None, "extra": True, "is_header": False,
               "item_no": "", "description": desc, "unit": unit,
               "qty": float(qty),
               "source": "spec" if ident else "typed"}
        if with_pcs:
            row["pcs"] = pcs
        if make:
            row["make"] = make
        if ident:
            row["src_spec_id"] = ident.get("src_spec_id")
            row["src_vidx"] = ident.get("src_vidx")
        if with_image:
            posted = _at(images, n)
            LI.apply_choice(row, posted, _allowed_for(row, posted, stored))
        if with_ref:
            ref = _at(refs, n)
            if ref and ref in (allowed_refs or ()):
                row["po_key"] = ref
                row["source"] = "po"
        out.append(row)
    if len(out) > MAX_EXTRA_ROWS:
        return [], (f"{len(out)} extra items; the limit is {MAX_EXTRA_ROWS}. "
                    f"{cap_msg}")
    return out, ""


# Plain text, SINGLE braces: spliced into the page as a value, never re-parsed
# as an f-string. `dc` is the challan's prefix; another document passes its own.
_EXTRA_JS = """<script>
/* One more extra-item row, cloned from the template. */
function dcAddExtra() {
  var t = document.getElementById('dc-xi-tpl');
  var box = document.getElementById('dc-xi-rows');
  if (t && box) box.appendChild(t.content.cloneNode(true));
}
/* A library pick fills a BLANK description; a typed one is never replaced. */
function dcPick(sel) {
  var row = sel.closest('.line-row');
  var d = row ? row.querySelector('input[name="xi_desc"]') : null;
  var o = sel.options[sel.selectedIndex];
  if (d && o && o.value && !d.value) d.value = o.getAttribute('title') || o.textContent;
}
</script>"""


def _js(pfx: str) -> str:
    if pfx == "dc":
        return _EXTRA_JS
    return (_EXTRA_JS.replace("dcAddExtra", f"{pfx}AddExtra")
            .replace("dcPick", f"{pfx}Pick")
            .replace("'dc-xi-", f"'{pfx}-xi-"))


def extra_row_html(desc="", qty="", unit="", pick="", spec=None, *,
                   pfx: str = "dc", desc_max: int = EXTRA_DESC_MAX,
                   make=None, make_max: int = 60, pcs=None,
                   image_row: dict = None, ref=None) -> str:
    """
    One extra-item row. Styled on the element: the sheets are pinned.

    `make` / `pcs` not None add those boxes; `image_row` not None adds the
    picture cell — a select over that row's library, or a hidden box carrying
    the row's picture id so the positional lists stay the same length.
    """
    opts = ('<option value="">&mdash; or pick from the specification library &mdash;</option>'
            + BYP.groups_html(pick, with_spec=True, spec=spec, boq=[]))
    # `ref` not None (17 Nov 2026): the hidden purchase-order line key. ""
    # when None, so a row without one is byte-for-byte what it was.
    ref_box = ("" if ref is None else
               f'<input type="hidden" name="xi_ref" value="{P.esc(ref)}"/>')
    if make is None and pcs is None and image_row is None:
        return f"""
        <div class="line-row" style="display:grid;grid-template-columns:minmax(150px,1fr) minmax(180px,1.4fr) minmax(200px,2fr) 110px 90px 34px;gap:.5rem;align-items:center;margin-bottom:.45rem;">
          <input type="text" placeholder="{BYP.FIND_PLACEHOLDER}" oninput="findItem(this)" aria-label="Search the library"/>{ref_box}
          <select name="line_product_id" onchange="{pfx}Pick(this)" aria-label="Specification library">{opts}</select>
          <input type="text" name="xi_desc" value="{P.esc(desc)}" maxlength="{desc_max}"
                 placeholder="Description (required)" aria-label="Description"/>
          {UN.select_html("xi_unit", unit, blank="Unit")}
          <input type="number" name="xi_qty" value="{P.esc(qty)}" min="0" step="any"
                 placeholder="Qty" aria-label="Quantity"/>
          <button type="button" class="btn-remove-line" title="Remove this item"
                  onclick="this.closest('.line-row').remove();">&#215;</button>
        </div>"""
    pic = ""
    if image_row is not None:
        pic = LI.select_html(image_row, "xi_image", "Picture",
                             style="max-width:140px;font-size:.78rem;")
        if not pic:
            pic = (f'<input type="hidden" name="xi_image" '
                   f'value="{P.esc(LI.image_of(image_row))}"/>')
    make_box = ("" if make is None else
                f'\n          <input type="text" name="xi_make" value="{P.esc(make)}" '
                f'maxlength="{make_max}" placeholder="Make" aria-label="Make"/>')
    pcs_box = ("" if pcs is None else
               f'\n          <input type="text" name="xi_pcs" value="{P.esc(pcs)}" '
               f'maxlength="{PCS_MAX}" placeholder="Pcs" aria-label="Pieces"/>')
    return f"""
        <div class="line-row" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:.5rem;align-items:center;margin-bottom:.45rem;">
          <input type="text" placeholder="{BYP.FIND_PLACEHOLDER}" oninput="findItem(this)" aria-label="Search the library"/>{ref_box}
          <select name="line_product_id" onchange="{pfx}Pick(this)" aria-label="Specification library">{opts}</select>
          <input type="text" name="xi_desc" value="{P.esc(desc)}" maxlength="{desc_max}"
                 placeholder="Description (required)" aria-label="Description"/>{make_box}
          {UN.select_html("xi_unit", unit, blank="Unit")}
          <input type="number" name="xi_qty" value="{P.esc(qty)}" min="0" step="any"
                 placeholder="Qty" aria-label="Quantity"/>{pcs_box}
          {pic}
          <button type="button" class="btn-remove-line" title="Remove this item"
                  onclick="this.closest('.line-row').remove();">&#215;</button>
        </div>"""


DC_TITLE = "Extra items &mdash; not on the schedule"
DC_INTRO = """
        Anything going out that is not a BOQ line. Type it, or pick it from the
        specification library. <b>Description and a quantity above 0 are
        required.</b> Extra items print on the challan after the BOQ lines and
        are never billed on an RA bill.
      """


def extras_section_html(stored: list = None, posted=None, *,
                        pfx: str = "dc", title: str = DC_TITLE,
                        intro_html: str = DC_INTRO,
                        desc_max: int = EXTRA_DESC_MAX,
                        with_make: bool = False, make_max: int = 60,
                        with_pcs: bool = False, with_image: bool = False,
                        fmt_qty=None, with_ref: bool = False) -> str:
    """
    The *Extra items* section.

    `fmt_qty` formats a stored quantity for its box — the caller's own
    (`boq._fmt_qty()`); this leaf may not import `boq.py`.

    Filled from what was just posted (a refused POST comes back as typed),
    else from the document's stored extras, else one blank row.
    """
    BYP.ensure_seeded()
    spec = BYP.spec_entries()
    extra = with_make or with_pcs or with_image
    rows_data = []   # (desc, qty, unit, pick, make, pcs, image_id, ref)
    if posted is not None:
        descs, qtys = posted.getlist("xi_desc"), posted.getlist("xi_qty")
        units, picks = posted.getlist("xi_unit"), posted.getlist("line_product_id")
        makes, pcses = posted.getlist("xi_make"), posted.getlist("xi_pcs")
        imgs, refs = posted.getlist("xi_image"), posted.getlist("xi_ref")
        for n in range(max(len(descs), len(qtys), len(units), len(picks))):
            rows_data.append(tuple(seq[n] if n < len(seq) else ""
                                   for seq in (descs, qtys, units, picks,
                                               makes, pcses, imgs, refs)))
    else:
        for r in stored or []:
            pick = (f"{BYP.SPEC_PREFIX}{r.get('src_spec_id')}:{r.get('src_vidx')}"
                    if r.get("src_spec_id") else "")
            q = r.get("qty") or 0
            rows_data.append((str(r.get("description") or ""),
                              fmt_qty(q) if fmt_qty else f"{float(q):g}",
                              str(r.get("unit") or ""), pick,
                              str(r.get("make") or ""), str(r.get("pcs") or ""),
                              LI.image_of(r), str(r.get("po_key") or "")))
    while len(rows_data) < DEFAULT_EXTRA_ROWS:
        rows_data.append(("", "", "", "", "", "", "", ""))

    def _row(d=None):
        d = d or ("", "", "", "", "", "", "", "")
        if not extra:
            return extra_row_html(*d[:4], spec=spec, pfx=pfx, desc_max=desc_max,
                                  ref=d[7] if with_ref else None)
        img_row = None
        if with_image:
            img_row = {"description": d[0]}
            iid = LI.valid_id(d[6])
            if iid:
                own = next((s for s in stored or [] if LI.image_of(s) == iid), None)
                img_row = dict(own) if own else dict(img_row, **{LI.KEY: iid})
                img_row["description"] = d[0] or img_row.get("description", "")
        return extra_row_html(*d[:4], spec=spec, pfx=pfx, desc_max=desc_max,
                              make=d[4] if with_make else None, make_max=make_max,
                              pcs=d[5] if with_pcs else None, image_row=img_row)

    rows = "".join(_row(r) for r in rows_data)
    return f"""
    <div class="form-section">
      <div class="section-title">{title}</div>
      <p style="font-size:.82rem;color:var(--muted);margin:-.4rem 0 .9rem;">{intro_html}</p>
      <input type="hidden" name="xi_present" value="1"/>
      <div id="{pfx}-xi-rows">{rows}</div>
      <template id="{pfx}-xi-tpl">{_row()}</template>
      <button type="button" class="btn btn-ghost" onclick="{pfx}AddExtra()"
              style="margin-top:.3rem;">+ Add item</button>
    </div>
    {BYP.FIND_JS}{_js(pfx)}"""

