"""
pnl_chart.py — the P&L's two pictures, as server-rendered inline SVG
====================================================================
No routes, no blueprint, no arithmetic. CLIENT_CHANGES.md §0's
**fifty-eighth** block, item 5: the client asked to *see where the money
went*, not only to read it.

Two figures, and a **plain-text table under each one**:

    waterfall_html()   money   — billed to date, less each cost head, to margin
    spider_html()      progress — five axes, every one 0-100%

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

`projectview.py` and `dashboard.py` import it; it imports neither, nor `pnl.py`
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
# ⚠ **THE SPIDER'S viewBox IS WIDER THAN IT IS TALL, ON PURPOSE.** A radar's
#   left and right axis labels run OUTWARD from the rim, so a square box the
#   size of the plot puts them outside it. Measured in headless Chromium at
#   390 px with a square 300x300 box and the full axis names: the page carried
#   **156 px of horizontal overflow** and two labels painted off the edge.
#   The box is now 400 wide for a 98 px radius — ~100 px of label room each
#   side, which the short names fit inside (`pnl.progress_of()`'s `short`).
#   Re-measure if either number changes.
S_W, S_H = 400, 300                   # spider viewBox
S_CX, S_CY = S_W / 2, S_H / 2
S_R = 98                              # outer radius
S_RINGS = (25, 50, 75, 100)

# ── RECESSIVE CHROME — grid, axes and connectors ────────────────────────────
#
# ⚠ **These are NOT palette slots and no data mark ever wears one.** Every
#   colour that carries meaning comes from `branding.CHART_*`; these four are
#   the grid, the rings, the zero line and the dashed connector — the
#   "recessive grid/axes" the method asks for, which must sit *under* the
#   data and are deliberately lighter than any step of the ramp. They are
#   named here, in one place, rather than written into the drawing code, so
#   `tests/test_pnl_charts_oct28.py` can assert that the DRAWING holds no hex
#   literal at all.
C_ZERO = "#B9B2CC"        # the zero line — the darkest of the four
C_CONNECT = "#CFC9DD"     # the dashed step-to-step connector
C_AXIS = "#DDD8E8"        # the spider's spokes
C_RING = "#E6E2EF"        # the spider's 25/50/75/100 rings


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
    for i, (_key, label, amount) in enumerate(wf["steps"]):
        amt = float(amount or 0.0)
        bars.append((label, -amt, run - amt, run, _ramp(i, n), "cost"))
        run -= amt
    final = float(res_val if res_val is not None else run)
    bars.append((res_label, final, 0.0, final,
                 B.CHART_WON if final >= 0 else B.CHART_LOST, "result"))

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

    # ── Reference rules: the PLAN, drawn as a rule and never as a bar ──────
    refs = ""
    for ref, text in ((wf.get("planned_revenue"), "BOQ value (planned)"),
                      (wf.get("planned_margin"), "planned margin")):
        if ref is None:
            continue
        y = _y(ref)
        refs += (
            f'<line x1="0" y1="{y:.1f}" x2="{W_WIDTH}" y2="{y:.1f}" '
            f'stroke="{B.CHART_NAVY[2]}" stroke-width="1.5" '
            f'stroke-dasharray="6 4" opacity=".75"/>'
            f'<text x="{W_WIDTH - 4}" y="{y - 5:.1f}" text-anchor="end" '
            f'class="wf-ref">{P.esc(text)} {_compact(ref)}</text>')

    body = ""
    for i, (label, delta, lo, hi, colour, kind) in enumerate(bars):
        x = i * slot + (slot - bar_w) / 2
        top, bottom = _y(max(lo, hi)), _y(min(lo, hi))
        h = max(2.0, bottom - top)      # the 2px floor: a nil head stays visible
        # A connector from the previous bar's closing level, so the steps read
        # as one walk rather than five unrelated columns.
        if 0 < i < len(bars) - 1:
            prev_y = _y(bars[i - 1][3] if bars[i - 1][5] != "cost"
                        else bars[i - 1][2])
            body += (f'<line x1="{i * slot - W_GAP / 2:.1f}" y1="{prev_y:.1f}" '
                     f'x2="{x:.1f}" y2="{prev_y:.1f}" stroke="{C_CONNECT}" '
                     f'stroke-width="1" stroke-dasharray="3 3"/>')
        shown = delta if kind == "cost" else (hi if kind == "start" else delta)
        body += (
            f'<g><title>{P.esc(label)}: {_compact(shown)}</title>'
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" '
            f'height="{h:.1f}" rx="4" fill="{colour}"/>'
            f'<text x="{x + bar_w / 2:.1f}" y="{top - 6:.1f}" '
            f'text-anchor="middle" class="wf-val">{_compact(shown)}</text>'
            f'<text x="{x + bar_w / 2:.1f}" y="{W_HEIGHT - 26:.1f}" '
            f'text-anchor="middle" class="wf-name">{P.esc(label)}</text></g>')

    # ── The table. Always, never conditionally. ────────────────────────────
    rows = (f'<tr><th>{P.esc(start_label)}</th><td>{_rs(start_val)}</td>'
            f'<td>billed to date, tax-exclusive</td></tr>')
    for _key, label, amount in wf["steps"]:
        rows += (f'<tr><th>less {P.esc(label)}</th><td>{_rs(amount)}</td>'
                 f'<td>actual cost recorded</td></tr>')
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
      <figure class="pnl-fig">
        <svg viewBox="0 0 {W_WIDTH} {W_HEIGHT}" class="pnl-svg" role="img"
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
# 2. THE PROGRESS SPIDER
# =============================================================================

def spider_html(axes: list) -> str:
    """
    `pnl.progress_of()`'s five axes as a radar, plus its table.

    ⚠ **A RADAR IS ONLY HONEST WHEN EVERY AXIS SHARES A SCALE, and these do**:
    all five are a percentage of their own denominator, 0 at the centre and
    100% at the rim. That is the one case the form is right for; five axes of
    different units on one radar is the anti-pattern.

    ⚠ **AN AXIS WITH NO DENOMINATOR DRAWS NO POINT.** It is not plotted at 0:
    *"nothing has been dispatched"* and *"there is no supply on this schedule"*
    are different statements and a 0% spoke claims the first. The polygon is
    drawn over the axes that have a figure, the empty spokes are drawn as bare
    axis lines, and the table says why each one is empty.

    ⚠ **The DRAWN radius is clamped at 100% and the printed figure is not**, so
    an over-collection or an over-dispatch stays readable as one in the table
    and in the label instead of being flattened into "complete".
    """
    n = len(axes)
    if not n:
        return ""

    def _ang(i):
        return -math.pi / 2 + i * 2 * math.pi / n

    def _pt(i, pct):
        a = _ang(i)
        rr = S_R * max(0.0, min(float(pct), 100.0)) / 100.0
        return S_CX + rr * math.cos(a), S_CY + rr * math.sin(a)

    grid = ""
    for ring in S_RINGS:
        pts = " ".join(f"{x:.1f},{y:.1f}"
                       for x, y in (_pt(i, ring) for i in range(n)))
        grid += (f'<polygon points="{pts}" fill="none" stroke="{C_RING}" '
                 f'stroke-width="1"/>')
    for i in range(n):
        x, y = _pt(i, 100)
        grid += (f'<line x1="{S_CX}" y1="{S_CY}" x2="{x:.1f}" y2="{y:.1f}" '
                 f'stroke="{C_AXIS}" stroke-width="1"/>')

    # The filled shape, over the axes that HAVE a figure.
    have = [(i, a) for i, a in enumerate(axes) if a["pct"] is not None]
    shape = ""
    if len(have) >= 3:
        pts = " ".join(f"{x:.1f},{y:.1f}"
                       for x, y in (_pt(i, a["pct"]) for i, a in have))
        shape = (f'<polygon points="{pts}" fill="{B.CHART_NAVY[2]}" '
                 f'fill-opacity=".28" stroke="{B.CHART_NAVY[4]}" '
                 f'stroke-width="2" stroke-linejoin="round"/>')
    elif len(have) == 2:
        (i0, a0), (i1, a1) = have
        x0, y0 = _pt(i0, a0["pct"])
        x1, y1 = _pt(i1, a1["pct"])
        shape = (f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" '
                 f'y2="{y1:.1f}" stroke="{B.CHART_NAVY[4]}" stroke-width="2"/>')

    marks = labels = ""
    for i, a in enumerate(axes):
        ax, ay = _pt(i, 108)
        anchor = ("middle" if abs(ax - S_CX) < 12 else
                  "start" if ax > S_CX else "end")
        dy = 4 if abs(ay - S_CY) < 12 else (-4 if ay < S_CY else 12)
        pct = a["pct"]
        val = f"{pct:.0f}%" if pct is not None else "—"
        # ⚠ The SHORT name here; the full one is in the table. See the viewBox
        #   note at the top of this file for the measurement that forced it.
        labels += (f'<text x="{ax:.1f}" y="{ay + dy:.1f}" '
                   f'text-anchor="{anchor}" class="sp-name">'
                   f'{P.esc(a.get("short") or a["label"])} '
                   f'<tspan class="sp-val">{val}</tspan></text>')
        if pct is None:
            continue
        mx, my = _pt(i, pct)
        # >= 8px marker with a 2px surface ring — the overlapping-mark rule.
        marks += (f'<g><title>{P.esc(a["label"])}: {pct:.2f}%</title>'
                  f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="4.5" '
                  f'fill="{B.CHART_NAVY[5]}" stroke="#fff" '
                  f'stroke-width="2"/></g>')

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
      <figure class="pnl-fig">
        <svg viewBox="0 0 {S_W} {S_H}" class="pnl-svg pnl-svg-sq" role="img"
             preserveAspectRatio="xMidYMid meet"
             aria-label="Progress on five axes, each a percentage of its own total. The same figures are in the table below.">
          {grid}{shape}{marks}{labels}
        </svg>
        <figcaption>How far along &mdash; five measures, each as a percentage of
          its own total, 0 at the centre and 100% at the rim. An axis with
          nothing to measure against draws no point; the table says which and
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
        .pnl-svg-sq { max-width:400px; margin:0 auto; }
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
        .sp-name { font:400 10px system-ui, sans-serif; fill:#666; }
        .sp-val { font-weight:700; fill:#2A086E; }
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
          .sp-name { font-size:12px; }
        }
      </style>"""
