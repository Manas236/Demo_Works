"""
pnl_chart.py — the P&L's three pictures, as server-rendered inline SVG/HTML
==========================================================================
No routes, no blueprint, no arithmetic. CLIENT_CHANGES.md §0's
**fifty-eighth** block, item 5: the client asked to *see where the money
went*, not only to read it.

Three figures, and a **plain-text table under each one**:

    waterfall_html()   money    — billed to date, less each cost head, to margin
    cost_pie_html()    money    — the cost split to date, one slice per head
    progress_html()    progress — six steps, every one 0-100%, as bars

⚠ **THE SPIDER IS GONE** (6 November 2026, §0's **sixty-ninth** block, item 1).
  A radar of six percentages read as a shape nobody could name; a row per
  step — name, bar, figure — reads in one glance and cannot overlap itself.
  In its place: the **cost pie** (`cost_pie_html()`) and the **progress bars**
  (`progress_html()`). The six steps, their figures and their table are
  `pnl.progress_of()`'s exactly as they were.

⚠ **NO TEXT MAY OVERLAP, AT ANY WIDTH** (same block, items 2 and 3). The SVG
  cannot ask the browser how wide a word is, so every label is placed from a
  deliberately GENEROUS width estimate (`_text_w()`) and the placement keeps
  clear of every other label's estimated box. That is a promise this module
  cannot check by itself: `tests/test_pnl_chart_layout.py` lays the page out
  in headless Chromium at 360 / 390 / 768 / 1280 px and fails on any two text
  boxes that intersect. Change a font size, a label or a viewBox here and
  run it.

⚠ **SCREEN ONLY, AND THERE IS NO PRINT ROUTE TO LEAK ONTO.** `/projects/view`
has never had one and this pass does not give it one. No printed document
changes; every print golden holds byte-for-byte.

The three rules this file is built under
----------------------------------------
1. **No `/templates`, no `/static`, no JS, no CDN.** The SVG is a Python
   f-string with its geometry already computed — exactly what the rest of this
   application does with HTML. ⚠ Nothing here is a chart *library*: there is no
   axis engine and no scale object, because two fixed figures do not need one
   and a dependency that draws them would be the first CDN in the project.
2. **EVERY FIGURE ARRIVES COMPUTED.** `pnl.waterfall_of()` and
   `pnl.progress_of()` do the money; this module turns numbers into
   coordinates and nothing else. It does not add, subtract or compare a rupee
   — `projectview._pnl_panel()`'s rule, one layer further out, and what keeps
   the lift of that module's prohibition honest.
3. **A TABLE OF THE SAME NUMBERS SITS UNDER EVERY CHART, ALWAYS.** Not a
   fallback bolted on: an `<svg>` that fails to render, a screen reader, a
   forced-colours mode and a print stylesheet all leave the picture out, and
   the figures must not go with it. It is also the *relief* the palette's
   contrast WARN obligates — see the palette note below.

The palette, and why the categorical validator is the wrong test
----------------------------------------------------------------
Colours come from **`branding.CHART_*`** and nothing is minted here. Two
different jobs, each by its own rule:

- the cost heads are a **SEQUENTIAL** ramp (`CHART_NAVY`, light to dark), because
  they are steps down one quantity and their order is read as order;
- the result is a **STATUS** colour — `CHART_WON` when the margin is positive,
  `CHART_LOST` when it is not.

⚠ **Running the categorical validator over that set FAILS, and it is the wrong
  test.** Measured 29 October 2026 on the six hexes together: *lightness band*
  fails on the ramp's dark end (a sequential ramp's dark end is meant to sit
  below the categorical band), *CVD separation* fails on WON↔LOST (they are
  status colours, which the method says ship with a label and never as colour
  alone), and the *normal-vision floor* fails between two adjacent ramp steps
  (adjacent sequential steps are meant to be close). The checks that do apply
  were run and all pass:

      ORDINAL on CHART_NAVY   lightness monotone ✓  adjacent ΔL >= 0.06 ✓
                              light-end contrast 2.09:1 ✓  single hue, 0° ✓
      CONTRAST on white       CHART_WON  3.35:1 ✓   CHART_LOST 4.80:1 ✓

  ⚠ **`CHART_WARN` is 1.83:1 and is therefore NOT used as a fill here.** The
  amber band elsewhere on the page carries its own CSS and its own text.

⚠ **Sign is never colour alone.** A negative bar is drawn **below the axis**,
  carries its own sign in its label, and is named in the table. The method's
  rule for status colour is an icon or a label beside it, never the hue by
  itself, and position does that job here better than either.

⚠ **No hover layer, and that is the one place this departs from the method.**
  An interactive chart wants a tooltip, and a tooltip wants JavaScript, which
  this application does not have and will not grow a chart library to get.
  What stands in its place is stronger for this page: **every bar and every
  spoke is direct-labelled**, and the table underneath carries the exact
  figures. An SVG `<title>` is emitted per mark as well, which browsers show
  natively with no script at all.

Import direction — a LEAF
-------------------------
    pnl_chart.py ──► branding.py   the validated palette
    pnl_chart.py ──► pipeline.py   esc
    pnl_chart.py ──► quotation.py  _inr, the one Indian money format

`projectview.py` imports it; it imports neither, nor `pnl.py`
— the figures are handed in as the dicts `pnl.py` returns, which is
`lineimage.py`'s arrangement one register along. It knows nothing about a
project.
"""

import math

import branding as B
import pipeline as P
from quotation import _inr

# ── Geometry. Plain numbers rather than a scale object: there are two charts
#   and their shapes are fixed, and a scale abstraction over that is the sort
#   of library this file exists to not import.
# ⚠ **THE WATERFALL'S ASPECT IS WHAT MAKES IT LEGIBLE WHEN IT SHRINKS.** The
#   SVG is `width:100%; height:auto`, so at a 308 px column a 720-wide box is
#   drawn at 0.428x and a 10 px label renders at 4.3 px — unreadable.
#   Measured in headless Chromium at 390 px. Two things answer it, together:
#   a taller box (so the bars keep their height as the width falls), and the
#   narrow-width rules at the foot of this file, which **hide the bar NAMES
#   and the reference labels and enlarge the values**. The names are not lost
#   — the table directly underneath carries every one of them with its figure,
#   which is the whole reason that table is mandatory rather than a fallback.
W_WIDTH, W_HEIGHT = 720, 300          # waterfall viewBox
W_PAD_T, W_PAD_B = 30, 56             # room for the value labels and the names
W_GAP = 10                            # the 2px-surface-gap rule, at this scale
# ── The waterfall's NAMES wrap inside their own bar (6 November 2026). At
#   seven bars a slot is ~103 units and a bar ~93, and *"PO charges outside
#   the tax base"* is ~150 at 10 px — it ran into both neighbours. A name now
#   wraps onto at most TWO lines within its bar's width, and the one head too
#   long for that is drawn by its short name (`SHORT_HEADS`); the table keeps
#   every full name. Never rotated, never overlapping.
W_NAME_PX = 10                         # .wf-name
W_NAME_LEAD = 12                       # line to line
W_VAL_PX = 11                          # .wf-val (bold)
W_REF_PX = 9.5                         # .wf-ref (bold)
SHORT_HEADS = {"po_exempt": "PO charges (non-taxable)"}

# ── The cost pie (6 November 2026). Wider than tall for the same reason the
#   spider was: its labels sit OUTSIDE the rim, left and right, and need room.
#   With R = 76 in a 420 box each side has ~112 units of label column, which
#   the longest one-line head ("Purchase orders" at 12 px) fits inside.
P_W, P_H = 420, 250
P_CX, P_CY = P_W / 2, P_H / 2
P_R = 76
P_LABEL_GAP = 20                       # rim to the label column
P_NAME_PX = 12                         # .pie-name
P_LEAD = 14                            # line to line in a slice label
P_BLOCK_GAP = 6                        # between two slice labels, vertically
P_LABEL_MIN_PCT = 5.0                  # a thinner slice is named in the key only

# ── RECESSIVE CHROME — grid, axes and connectors ────────────────────────────
#
# ⚠ **These are NOT palette slots and no data mark ever wears one.** Every
#   colour that carries meaning comes from `branding.CHART_*`; these three are
#   the zero line, the dashed connector and the progress track — the
#   "recessive grid/axes" the method asks for, which must sit *under* the
#   data and are deliberately lighter than any step of the ramp. They are
#   named here, in one place, rather than written into the drawing code, so
#   `tests/test_pnl_charts_oct28.py` can assert that the DRAWING holds no hex
#   literal at all.
C_ZERO = "#B9B2CC"        # the zero line — the darkest of the three
C_CONNECT = "#CFC9DD"     # the dashed step-to-step connector, and the pie's
                          # leader lines
C_RING = "#E6E2EF"        # the empty track behind a progress bar (it was the
                          # spider's rings until 6 November 2026)


def _rs(v) -> str:
    """A money figure. Never escaped — a money format (ABOUT.md §9)."""
    return "&#8377;&nbsp;" + _inr(v) if v is not None else "&mdash;"


def _compact(v) -> str:
    """A short money label for inside a chart: 12.4L, 3.2Cr, 8,400."""
    if v is None:
        return "—"
    n = abs(float(v))
    sign = "-" if v < 0 else ""
    if n >= 1e7:
        return f"{sign}{n / 1e7:.2f}Cr"
    if n >= 1e5:
        return f"{sign}{n / 1e5:.2f}L"
    return f"{sign}{n:,.0f}"


def _ramp(i: int, n: int) -> str:
    """Step `i` of `n` down the sequential ramp — the darker end for the later
    heads, so the steps read as steps. Clamped, never cycled: a cycled ramp
    would give two different heads the same colour."""
    ramp = B.CHART_NAVY
    if n <= 1:
        return ramp[len(ramp) // 2]
    # Spread across the ramp's middle-to-dark half, which is where the four
    # ordinal checks were measured and where contrast on white is >= 3:1.
    lo, hi = 1, len(ramp) - 1
    return ramp[min(hi, lo + round(i * (hi - lo) / (n - 1)))]


def _colour_of(step: int, steps_n: int) -> str:
    """A cost head's colour, from its place in `pnl.waterfall_of()`'s steps.
    The ONE place both money pictures get a head's colour from, so the pie's
    slice and the waterfall's bar for one head can never disagree."""
    return _ramp(step, steps_n)


# ── TEXT WIDTH, ESTIMATED — and deliberately on the wide side ───────────────
#
# ⚠ An SVG drawn on the server cannot measure a word, and the face is the
#   reader's `system-ui` (Segoe UI on the client's Windows boxes, something
#   else in a test browser). These are per-character advances in em, rounded
#   UP from the wider of the faces measured, so a label placed clear of its
#   neighbours by this estimate is clear in the browser too. Over-estimating
#   costs a little white space; under-estimating is an overlap.
_NARROW = set("iljtfr.,:;'|!()[]- ·")
_WIDE = set("mwMW@%")


def _text_w(text: str, px: float, bold: bool = False) -> float:
    em = 0.0
    for ch in str(text):
        if ch == " ":
            em += 0.30
        elif ch in _NARROW:
            em += 0.36
        elif ch in _WIDE:
            em += 0.92
        elif ch.isupper():
            em += 0.70
        elif ch.isdigit():
            em += 0.62
        else:
            em += 0.58
    return em * px * (1.08 if bold else 1.0)


def _wrap(text: str, width: float, px: float, lines: int = 2):
    """`text` broken at spaces into at most `lines` lines no wider than
    `width`, or None when it cannot be — never a broken word, never a third
    line."""
    words = str(text).split()
    out, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if _text_w(trial, px) <= width:
            cur = trial
            continue
        if not cur:                 # one word wider than the line by itself
            return None
        out.append(cur)
        cur = w
        if _text_w(cur, px) > width:
            return None
    if cur:
        out.append(cur)
    return out if len(out) <= lines else None


def _hits(a, b, pad: float = 1.5) -> bool:
    """Two boxes `(x0, y0, x1, y1)` that overlap, with `pad` of clearance."""
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0]
                or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _pct_text(pct) -> str:
    """A share for a label: whole percent from 10 up, one place below it, so a
    thin head reads 0.4% rather than a misleading 0%."""
    if pct is None:
        return "—"
    return f"{pct:.0f}%" if pct >= 10 else f"{pct:.1f}%"


# =============================================================================
# 1. THE MONEY WATERFALL
# =============================================================================

def waterfall_html(wf: dict) -> str:
    """
    `pnl.waterfall_of()`'s dict as a waterfall, plus its table.

    ⚠ **The running total is walked here but NOT re-summed into the result.**
    The closing bar is `wf["result"]`, which is `pnl.py`'s own margin; walking
    the bars to a second figure would be a second arithmetic path to a number
    that already exists, and rounding would make the two disagree eventually.
    The chart therefore shows `result` as given and the bars as given, and the
    table prints both so a reader can see they agree.

    ⚠ **A NEGATIVE RESULT IS DRAWN BELOW THE AXIS.** The axis is placed where
    0 falls in the value range, so a loss crosses it rather than being clipped
    to nothing — a bar of height 0 for a real loss is the single most
    misleading thing this chart could do.
    """
    start_label, start_val = wf["start"]
    res_label, res_val = wf["result"]
    if start_val is None and res_val is None and not wf["steps"]:
        return ('<p class="pnl-note">There is nothing billed and nothing spent '
                'on this project yet, so there is no money to draw.</p>')

    # ── The bars, as (label, signed delta, running top, colour, kind) ───────
    bars = []
    run = float(start_val or 0.0)
    bars.append((start_label, run, 0.0, run, B.CHART_NAVY[0], "start"))
    n = len(wf["steps"])
    names = [start_label]
    for i, (key, label, amount) in enumerate(wf["steps"]):
        amt = float(amount or 0.0)
        bars.append((label, -amt, run - amt, run, _colour_of(i, n), "cost"))
        names.append(SHORT_HEADS.get(key, label))
        run -= amt
    final = float(res_val if res_val is not None else run)
    bars.append((res_label, final, 0.0, final,
                 B.CHART_WON if final >= 0 else B.CHART_LOST, "result"))
    names.append(res_label)

    # ── The value range, including every reference mark, so nothing is drawn
    #   outside the box.
    vals = [0.0]
    for _l, _d, lo, hi, _c, _k in bars:
        vals += [lo, hi]
    for ref in (wf.get("planned_revenue"), wf.get("planned_margin")):
        if ref is not None:
            vals.append(float(ref))
    vmin, vmax = min(vals), max(vals)
    if vmax - vmin < 1e-9:
        vmax = vmin + 1.0
    plot_h = W_HEIGHT - W_PAD_T - W_PAD_B

    def _y(v) -> float:
        return W_PAD_T + (vmax - float(v)) / (vmax - vmin) * plot_h

    slot = W_WIDTH / len(bars)
    bar_w = max(14.0, slot - W_GAP)
    zero_y = _y(0.0)

    # ── Every bar's geometry, and the boxes its two labels will occupy ─────
    #   Worked out BEFORE anything is drawn, so the plan labels below can be
    #   placed clear of all of them.
    geo, taken, bar_boxes = [], [], []
    name_y0 = W_HEIGHT - 30
    for i, (label, delta, lo, hi, colour, kind) in enumerate(bars):
        x = i * slot + (slot - bar_w) / 2
        top, bottom = _y(max(lo, hi)), _y(min(lo, hi))
        h = max(2.0, bottom - top)      # the 2px floor: a nil head stays visible
        shown = delta if kind == "cost" else (hi if kind == "start" else delta)
        cx = x + bar_w / 2
        vw = _text_w(_compact(shown), W_VAL_PX, bold=True)
        taken.append((cx - vw / 2, top - 6 - W_VAL_PX, cx + vw / 2, top - 6 + 3))
        # The NAME: its own words, wrapped to two lines inside its own bar; a
        # name that will not go into two is cut at the second line's end with
        # an ellipsis — the table under the chart carries every full name.
        lines = _wrap(names[i], bar_w, W_NAME_PX)
        if lines is None:
            lines, rest = [], names[i].split()
            while rest and len(lines) < 2:
                cur = rest.pop(0)
                while rest and _text_w(f"{cur} {rest[0]}…", W_NAME_PX) <= bar_w:
                    cur = f"{cur} {rest.pop(0)}"
                lines.append(cur)
            if rest:
                lines[-1] += "…"
        for j, ln in enumerate(lines):
            nw = _text_w(ln, W_NAME_PX)
            by = name_y0 + j * W_NAME_LEAD
            taken.append((cx - nw / 2, by - W_NAME_PX, cx + nw / 2, by + 3))
        bar_boxes.append((x, top, x + bar_w, top + h))
        geo.append((x, top, h, shown, lines))

    # ── Reference rules: the PLAN, drawn as a rule and never as a bar ──────
    #
    # ⚠ **THE TWO PLAN LABELS ARE PLACED, NOT PINNED** (6 November 2026). Both
    #   used to sit right-aligned just above their own rule, so when *BOQ
    #   value* and *planned margin* fell a few units apart one was printed on
    #   top of the other — and either could sit on the closing bar's value.
    #   Each now takes the FIRST of a fixed list of positions — above its rule
    #   at the right end, below it, then the left end, then over each bar's
    #   slot — whose estimated box is clear of every bar value, every bar
    #   name, the other plan label and (preferably) every bar. A label that
    #   finds no clear position at all is not drawn: the rule keeps its
    #   `<title>`, and the table names the figure. Never an overlap.
    refs = ""
    for ref, text in ((wf.get("planned_revenue"), "BOQ plan"),
                      (wf.get("planned_margin"), "Planned margin")):
        if ref is None:
            continue
        y = _y(ref)
        label = f"{text} {_compact(ref)}"
        lw = _text_w(label, W_REF_PX, bold=True)
        spots = []
        for yb in (y - 5, y + W_REF_PX + 4):
            spots.append((W_WIDTH - 4 - lw, yb))
            spots.append((4.0, yb))
            spots += [(i * slot + (slot - lw) / 2, yb) for i in range(len(bars))]
        place = None
        for avoid_bars in (True, False):
            for lx, yb in spots:
                box = (lx, yb - W_REF_PX, lx + lw, yb + 3)
                if box[0] < 0 or box[2] > W_WIDTH or box[1] < 1 \
                        or box[3] > W_HEIGHT - 1:
                    continue
                if any(_hits(box, t) for t in taken):
                    continue
                if avoid_bars and any(_hits(box, b, 0.0) for b in bar_boxes):
                    continue
                place = (lx, yb, box)
                break
            if place:
                break
        refs += (
            f'<line x1="0" y1="{y:.1f}" x2="{W_WIDTH}" y2="{y:.1f}" '
            f'stroke="{B.CHART_NAVY[2]}" stroke-width="1.5" '
            f'stroke-dasharray="6 4" opacity=".75"><title>{P.esc(label)}</title></line>')
        if place:
            lx, yb, box = place
            taken.append(box)
            refs += (f'<text x="{lx:.1f}" y="{yb:.1f}" '
                     f'class="wf-ref">{P.esc(label)}</text>')

    body = ""
    for i, (label, delta, lo, hi, colour, kind) in enumerate(bars):
        x, top, h, shown, lines = geo[i]
        # A connector from the previous bar's closing level, so the steps read
        # as one walk rather than five unrelated columns.
        if 0 < i < len(bars) - 1:
            prev_y = _y(bars[i - 1][3] if bars[i - 1][5] != "cost"
                        else bars[i - 1][2])
            body += (f'<line x1="{i * slot - W_GAP / 2:.1f}" y1="{prev_y:.1f}" '
                     f'x2="{x:.1f}" y2="{prev_y:.1f}" stroke="{C_CONNECT}" '
                     f'stroke-width="1" stroke-dasharray="3 3"/>')
        cx = x + bar_w / 2
        name = "".join(
            f'<tspan x="{cx:.1f}" y="{name_y0 + j * W_NAME_LEAD:.1f}">'
            f'{P.esc(ln)}</tspan>' for j, ln in enumerate(lines))
        body += (
            f'<g><title>{P.esc(label)}: {_compact(shown)}</title>'
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" '
            f'height="{h:.1f}" rx="4" fill="{colour}"/>'
            f'<text x="{cx:.1f}" y="{top - 6:.1f}" '
            f'text-anchor="middle" class="wf-val">{_compact(shown)}</text>'
            f'<text text-anchor="middle" class="wf-name">{name}</text></g>')

    # ── The table. Always, never conditionally. ────────────────────────────
    rows = (f'<tr><th>{P.esc(start_label)}</th><td>{_rs(start_val)}</td>'
            f'<td>billed to date, tax-exclusive</td></tr>')
    for _key, label, amount in wf["steps"]:
        # ⚠ **The labour bar says which part of it has been PAID** (5 November
        #   2026, CLIENT_CHANGES.md §0's sixty-sixth block, ruling 4). It is
        #   still one bar and one row; what changes is the sentence beside it,
        #   because "actual cost recorded" is only true of the paid part.
        why = "actual cost recorded"
        split = wf.get("labour_split") if _key == "labour" else None
        if split:
            if split["actual"]:
                why = (f'estimated {_rs(split["estimate"])}, actual '
                       f'{_rs(split["actual"])} from {split["slips"]} issued '
                       f'payslip{"" if split["slips"] == 1 else "s"}')
            else:
                why = "estimated from the muster — no payslip issued for it yet"
        rows += (f'<tr><th>less {P.esc(label)}</th><td>{_rs(amount)}</td>'
                 f'<td>{why}</td></tr>')
    rows += (f'<tr class="pnl-sum"><th>{P.esc(res_label)}</th>'
             f'<td>{_rs(res_val)}</td><td>billed less spent &mdash; timing, '
             f'not the final result</td></tr>')
    for ref, text in ((wf.get("planned_revenue"), "BOQ value (planned revenue)"),
                      (wf.get("planned_margin"), "Planned margin")):
        if ref is not None:
            rows += (f'<tr><th>{P.esc(text)}</th><td>{_rs(ref)}</td>'
                     f'<td>a reference mark on the chart, never one of its '
                     f'bars &mdash; a plan and an actual are not added</td></tr>')
    if wf.get("labour_withheld"):
        rows += ('<tr><th>Site labour</th><td>&mdash;</td><td>withheld: it '
                 'needs the View attendance permission, so the margin above '
                 'excludes it</td></tr>')

    return f"""
      <figure class="pnl-fig pnl-fig-wf">
        <svg viewBox="0 0 {W_WIDTH} {W_HEIGHT}" class="pnl-svg pnl-svg-wf" role="img"
             preserveAspectRatio="xMidYMid meet"
             aria-label="Waterfall: billed to date less each cost head, ending at the margin to date. The same figures are in the table below.">
          <line x1="0" y1="{zero_y:.1f}" x2="{W_WIDTH}" y2="{zero_y:.1f}"
                stroke="{C_ZERO}" stroke-width="1"/>
          {refs}{body}
        </svg>
        <figcaption>Where the money went &mdash; billed to date, less each cost
          head, ending at the margin to date. A bar below the line is a
          negative. The dashed rules are the <b>plan</b>, for reference: a
          planned figure is never one of these bars.</figcaption>
        <table class="pnl-rows pnl-fig-tbl">
          <caption>The same figures, as text</caption>
          <tbody>{rows}</tbody>
        </table>
      </figure>"""


# =============================================================================
# 2. THE COST PIE (6 November 2026 — replaces the spider)
# =============================================================================

def _slice_path(a0: float, a1: float) -> str:
    """One wedge from angle a0 to a1 (radians, clockwise from 12 o'clock)."""
    x0 = P_CX + P_R * math.sin(a0)
    y0 = P_CY - P_R * math.cos(a0)
    x1 = P_CX + P_R * math.sin(a1)
    y1 = P_CY - P_R * math.cos(a1)
    large = 1 if a1 - a0 > math.pi else 0
    return (f"M{P_CX:.1f},{P_CY:.1f} L{x0:.2f},{y0:.2f} "
            f"A{P_R},{P_R} 0 {large} 1 {x1:.2f},{y1:.2f} Z")


def _pie_labels(slices: list, angles: list) -> dict:
    """
    `{slice index: (side, block top, lines)}` for the slices that get a label
    beside the pie; every other slice is named in the key only.

    ⚠ **The label column is laid out like a list, not like a clock.** Each
      label wants to sit level with its slice's middle, on that slice's side;
      on each side they are then pushed apart, top to bottom, so no two blocks
      share a pixel, and pulled back up if the last one would leave the box.
      A side that cannot fit its labels even so gives up its SMALLEST slice's
      label to the key, and is laid out again — so a crowded pie loses a label
      (which the key and the table both still carry) rather than overlapping
      two.
    """
    room = P_W / 2 - P_R - P_LABEL_GAP - 4
    want = {}
    for i, s in enumerate(slices):
        if s["pct"] is None or s["pct"] < P_LABEL_MIN_PCT:
            continue
        lines = _wrap(s["name"], room, P_NAME_PX)
        value = f'{_compact(s["amount"])} · {_pct_text(s["pct"])}'
        if lines is None or _text_w(value, P_NAME_PX, bold=True) > room:
            continue
        mid = (angles[i][0] + angles[i][1]) / 2
        side = "r" if math.sin(mid) >= 0 else "l"
        y_mid = P_CY - (P_R + 10) * math.cos(mid)
        want[i] = (side, y_mid, lines + [value])

    def _lay(items):
        """[(i, y_mid, n_lines)] → {i: top}, or None when they cannot fit."""
        items = sorted(items, key=lambda t: t[1])
        tops, prev = {}, 2.0
        for i, y_mid, n in items:
            h = n * P_LEAD
            top = max(y_mid - h / 2, prev)
            tops[i] = top
            prev = top + h + P_BLOCK_GAP
        floor = P_H - 2.0
        for i, _y, n in reversed(items):
            h = n * P_LEAD
            if tops[i] + h > floor:
                tops[i] = floor - h
            floor = tops[i] - P_BLOCK_GAP
        if items and tops[items[0][0]] < 2.0:
            return None
        return tops

    out = {}
    for side in ("r", "l"):
        mine = [(i, y, len(ls)) for i, (sd, y, ls) in want.items() if sd == side]
        while mine:
            tops = _lay(mine)
            if tops is not None:
                out.update({i: (side, tops[i], want[i][2]) for i in tops})
                break
            smallest = min(mine, key=lambda t: slices[t[0]]["share"])
            mine.remove(smallest)
    return out


def cost_pie_html(split: dict) -> str:
    """
    `pnl.cost_split_of()`'s dict as a pie, a key and a table.

    ⚠ **Only the heads above zero get a slice** — a nil head is a fact
      (*"no work order yet"*) but it has no area, and the table says it. A
      negative head cannot be a slice at all; the table says that too.

    ⚠ **Same colours as the waterfall's bars**, from the same function
      (`_colour_of()`) on the same index, so a reader who learns *"the dark
      one is labour"* on one picture can read it on the other.

    ⚠ **Every slice is named in the key; a slice wide enough is also labelled
      beside the pie** with its head, amount and share, on a leader line.
      A slice under `P_LABEL_MIN_PCT` — or one the label column has no room
      for — is named in the key only. That is what keeps the labels from ever
      overlapping, which a label ON a thin slice always does.

    ⚠ **No cost, no circle.** An empty pie claims a shape; *"No costs yet"*
      claims nothing, which is the truth.
    """
    slices = [dict(s, name=SHORT_HEADS.get(s["key"], s["label"]))
              for s in split["slices"]]
    n = split["steps_n"]

    # ── The table. Always, never conditionally. ────────────────────────────
    rows = ""
    for s in slices:
        rows += (f'<tr><th>{P.esc(s["label"])}</th><td>{_rs(s["amount"])}</td>'
                 f'<td>{s["pct"]:.2f}% of the cost drawn</td></tr>')
    for _k, label in split["nil"]:
        rows += (f'<tr><th>{P.esc(label)}</th><td>{_rs(0)}</td>'
                 f'<td>nothing recorded yet &mdash; no slice</td></tr>')
    for _k, label, v in split["negative"]:
        rows += (f'<tr><th>{P.esc(label)}</th><td>{_rs(v)}</td>'
                 f'<td>a credit, below zero &mdash; it cannot be a slice, so '
                 f'the shares above are of the other heads</td></tr>')
    if split["labour_withheld"]:
        rows += ('<tr><th>Site labour</th><td>&mdash;</td><td>withheld: it '
                 'needs the View attendance permission, so it is not in '
                 'this split</td></tr>')
    rows += (f'<tr class="pnl-sum"><th>Spent to date</th>'
             f'<td>{_rs(split["total"])}</td><td>tax-exclusive, the same '
             f'figure as the panel above</td></tr>')
    table = (f'<table class="pnl-rows pnl-fig-tbl">'
             f'<caption>The same figures, as text</caption>'
             f'<tbody>{rows}</tbody></table>')
    caption = ('<figcaption>The cost so far, by head &mdash; each slice is '
               'its head&rsquo;s share of what has been spent to date, '
               'tax-exclusive. A thin slice is named in the key rather than '
               'on the picture.</figcaption>')

    if not slices:
        return (f'<figure class="pnl-fig pnl-fig-pie">'
                f'<p class="pie-empty">No costs yet</p>'
                f'{caption}{table}</figure>')

    # ── The wedges, clockwise from 12 o'clock, in the waterfall's order ────
    angles, a = [], 0.0
    for s in slices:
        b = a + s["share"] * 2 * math.pi
        angles.append((a, b))
        a = b
    wedges = ""
    for i, s in enumerate(slices):
        colour = _colour_of(s["step"], n)
        tip = f'{P.esc(s["label"])}: {_compact(s["amount"])}, {_pct_text(s["pct"])}'
        if len(slices) == 1:
            shape = (f'<circle cx="{P_CX:.1f}" cy="{P_CY:.1f}" r="{P_R}" '
                     f'fill="{colour}"/>')
        else:
            # The 2 px white edge is the surface gap between two touching
            # marks — adjacent ramp steps are close by design.
            shape = (f'<path d="{_slice_path(*angles[i])}" fill="{colour}" '
                     f'stroke="#fff" stroke-width="2" stroke-linejoin="round"/>')
        wedges += f'<g><title>{tip}</title>{shape}</g>'

    # ── The labels beside it, on leader lines ──────────────────────────────
    labels = ""
    for i, (side, top, lines) in sorted(_pie_labels(slices, angles).items()):
        mid = sum(angles[i]) / 2
        rx = P_CX + P_R * math.sin(mid)
        ry = P_CY - P_R * math.cos(mid)
        h = len(lines) * P_LEAD
        ly = top + h / 2
        sign = 1 if side == "r" else -1
        col_x = P_CX + sign * (P_R + P_LABEL_GAP - 4)
        tx = P_CX + sign * (P_R + P_LABEL_GAP)
        labels += (f'<polyline points="{rx:.1f},{ry:.1f} {col_x:.1f},{ly:.1f} '
                   f'{col_x + sign * 2:.1f},{ly:.1f}" fill="none" '
                   f'stroke="{C_CONNECT}" stroke-width="1"/>')
        spans = ""
        for j, ln in enumerate(lines):
            cls = ' class="pie-val"' if j == len(lines) - 1 else ""
            spans += (f'<tspan x="{tx:.1f}" y="{top + (j + 1) * P_LEAD - 3:.1f}"'
                      f'{cls}>{P.esc(ln)}</tspan>')
        labels += (f'<text text-anchor="{"start" if side == "r" else "end"}" '
                   f'class="pie-name">{spans}</text>')

    # ── The key: every slice, labelled or not ──────────────────────────────
    key = "".join(
        f'<li><span class="pie-sw" style="background:{_colour_of(s["step"], n)}">'
        f'</span><span class="pie-k">{P.esc(s["name"])}</span> '
        f'<span class="pie-kv">{_compact(s["amount"])} · {_pct_text(s["pct"])}'
        f'</span></li>' for s in slices)

    return f"""
      <figure class="pnl-fig pnl-fig-pie">
        <svg viewBox="0 0 {P_W} {P_H}" class="pnl-svg pnl-svg-pie" role="img"
             preserveAspectRatio="xMidYMid meet"
             aria-label="Pie: the cost to date split by head. The same figures are in the key and the table below.">
          {wedges}{labels}
        </svg>
        <ul class="pie-key">{key}</ul>
        {caption}{table}
      </figure>"""


# =============================================================================
# 3. THE PROGRESS BARS (6 November 2026 — replaces the spider)
# =============================================================================

def progress_html(axes: list) -> str:
    """
    `pnl.progress_of()`'s six steps as one row each — name, bar, figure —
    plus the table the spider carried, unchanged.

    ⚠ **A STEP WITH NO DENOMINATOR SHOWS A DASH AND AN EMPTY BAR, NEVER 0%.**
      *"Nothing has been dispatched"* and *"there is no supply on this
      schedule"* are different statements, and a 0% bar claims the first. The
      table says why each empty one is empty — the rule the spider held by
      drawing no point.

    ⚠ **The DRAWN bar stops at 100% and the printed figure does not**, so an
      over-collection reads as one (the table adds *over 100%*).

    HTML, not SVG: a row of text and a bar laid out by the browser cannot
    overlap itself at any width, which is the whole of what the spider's
    labels could not promise.
    """
    if not axes:
        return ""
    bars = ""
    for a in axes:
        pct = a["pct"]
        name = a.get("short") or a["label"]
        if pct is None:
            fill = ""
            fig = "&mdash;"
            tip = f'{a["label"]}: no figure — {a["note"]}' if a["note"] else a["label"]
            aria = 'aria-valuetext="no figure"'
        else:
            drawn = max(0.0, min(float(pct), 100.0))
            fill = (f'<span class="prog-fill" style="width:{drawn:.1f}%;'
                    f'background:{B.CHART_NAVY[4]}"></span>')
            fig = f"{pct:.0f}%"
            tip = f'{a["label"]}: {pct:.2f}%'
            aria = f'aria-valuenow="{drawn:.0f}"'
        bars += (f'<div class="prog-row" title="{P.esc(tip)}">'
                 f'<span class="prog-name">{P.esc(name)}</span>'
                 f'<span class="prog-bar" role="progressbar" aria-valuemin="0" '
                 f'aria-valuemax="100" {aria} aria-label="{P.esc(a["label"])}" '
                 f'style="background:{C_RING}">{fill}</span>'
                 f'<span class="prog-pct">{fig}</span></div>')

    rows = ""
    for a in axes:
        pct = a["pct"]
        if a["unit"] == "money":
            of = f"{_rs(a['numer'])} of {_rs(a['denom'])}"
        elif a["unit"] == "lines":
            of = (f"{a['numer']} of {a['denom']} lines"
                  if a["denom"] else "no lines")
        else:
            of = (f"{a['numer']:g} of {a['denom']:g}"
                  if a["denom"] else "no quantity")
        over = (' <b>over 100%</b>' if pct is not None and pct > 100 else '')
        rows += (f'<tr><th>{P.esc(a["label"])}</th>'
                 f'<td>{f"{pct:.2f}%" if pct is not None else "&mdash;"}{over}</td>'
                 f'<td>{of}{" &mdash; " + P.esc(a["note"]) if a["note"] else ""}</td>'
                 f'</tr>')

    return f"""
      <figure class="pnl-fig pnl-fig-prog">
        <div class="prog">{bars}</div>
        <figcaption>How far along &mdash; six steps, each as a percentage of
          its own total. A step with nothing to measure against shows a dash
          and an empty bar, never 0%; the table says which and
          why.</figcaption>
        <table class="pnl-rows pnl-fig-tbl">
          <caption>The same figures, as text</caption>
          <tbody>{rows}</tbody>
        </table>
      </figure>"""


# =============================================================================
# THE STYLESHEET — travels with the panel, never in the page's <head>
# =============================================================================
#
# ⚠ `PNL_CSS`'s arrangement and for its reason: a reader without `project.pnl`
#   receives not one byte of it. Written as a plain string so its CSS braces
#   are not doubled — this file renders no f-string HTML around it.

CHART_CSS = """
      <style>
        .pnl-figs { display:flex; flex-wrap:wrap; gap:1.5rem; margin:1rem 0 .5rem; }
        /* ⚠ `min-width:0` is what stops a flex item refusing to shrink below
           its content and pushing the page into a horizontal scrollbar at
           390px. `flex-basis` is a floor, not a width. */
        .pnl-fig { flex:1 1 320px; min-width:0; margin:0; }
        /* `overflow:hidden` is the default on an outermost <svg> and is
           written out anyway: a label that ran past the viewBox would
           otherwise be a horizontal scrollbar on the whole page, which is
           exactly what the 390 px measurement caught. */
        .pnl-svg { display:block; width:100%; height:auto; max-width:100%;
                   overflow:hidden; background:#fff; }
        /* The waterfall takes the whole row and the pie and the progress
           bars share the next (6 November 2026): at half a row the waterfall
           was drawn at ~0.6x and its names were 6 px of ink. */
        .pnl-fig-wf { flex-basis:100%; }
        .pnl-svg-wf { max-width:860px; margin:0 auto; }
        .pnl-svg-pie { max-width:460px; margin:0 auto; }
        .pie-empty { margin:2.5rem 0; text-align:center; font-size:1rem;
                     color:var(--muted); }
        .pie-key { list-style:none; margin:.4rem 0 0; padding:0;
                   display:flex; flex-wrap:wrap; gap:.3rem 1.1rem;
                   font-size:.8rem; line-height:1.4; }
        .pie-key li { display:flex; align-items:center; gap:.4rem; min-width:0; }
        .pie-sw { flex:0 0 auto; width:.8rem; height:.8rem; border-radius:2px; }
        .pie-kv { font-weight:700; color:var(--navy); white-space:nowrap; }
        .prog { display:flex; flex-direction:column; gap:.55rem; margin:.4rem 0 0; }
        .prog-row { display:grid; grid-template-columns:6.5rem minmax(0,1fr) 3rem;
                    align-items:center; gap:.6rem; font-size:.85rem; }
        .prog-name { color:#666; overflow-wrap:anywhere; }
        .prog-bar { display:block; height:.7rem; border-radius:4px;
                    overflow:hidden; }
        .prog-fill { display:block; height:100%; border-radius:4px; }
        .prog-pct { text-align:right; font-weight:700; color:#2A086E;
                    font-variant-numeric:tabular-nums; }
        .pnl-fig figcaption { font-size:.78rem; color:var(--muted);
                              line-height:1.55; margin:.5rem 0 .6rem; }
        .pnl-fig figcaption b { color:var(--navy); }
        .pnl-fig-tbl { font-size:.82rem; }
        .pnl-fig-tbl caption { text-align:left; font-size:.72rem;
                               text-transform:uppercase; letter-spacing:.05em;
                               color:var(--muted); padding:0 0 .3rem; }
        .pnl-fig-tbl th { font-weight:400; }
        .pnl-fig-tbl td:last-child { text-align:left; white-space:normal;
                                     color:var(--muted); font-size:.78rem; }
        /* Text wears TEXT tokens, never a series colour. */
        .wf-val { font:700 11px system-ui, sans-serif; fill:#2A086E; }
        .wf-name { font:400 10px system-ui, sans-serif; fill:#666; }
        .wf-ref { font:700 9.5px system-ui, sans-serif; fill:#594DA5; }
        .pie-name { font:400 12px system-ui, sans-serif; fill:#666; }
        .pie-val { font-weight:700; fill:#2A086E; }
        /* ⚠ **NARROW WIDTHS: the chart keeps its FIGURES and drops its
           NAMES, because the table underneath carries both.** At a ~308 px
           column the waterfall is drawn at 0.43x, where a 10 px label is
           4.3 px of ink. Enlarging every label instead would make the desktop
           chart shout; hiding the ones the table repeats, and enlarging only
           the values, keeps the picture a picture and loses no information.
           Measured at 390 px in headless Chromium. */
        @media (max-width:560px) {
          .pnl-figs { gap:1rem; }
          .wf-name, .wf-ref { display:none; }
          .wf-val { font-size:19px; }
        }
      </style>"""
