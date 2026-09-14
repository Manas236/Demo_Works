"""
dashboard.py — The UI Core
==========================
Blueprint: dashboard_bp
Mounted at: / (root)

Two jobs, and they are unrelated to each other:

1. **The landing page** (`index`) — an operations dashboard. Not a menu. It
   answers "what is my pipeline worth, what is stuck, and what moved" before it
   offers a link anywhere. The module launcher sits at the *bottom*, because
   after the first week nobody needs to be told the app has a catalogue.

2. ~~**The app's stylesheet.**~~ ✅ **Moved to `chrome.py` on 14 September
   2026.** `BASE_STYLES`, `ICONS` and `_nav()` live in that leaf now, verbatim,
   and every page imports them from there. This module imports them back
   because the landing page draws them, and **re-exports `BASE_STYLES` and
   `_nav`** because `product.py` and `quotation.py` — both frozen — still read
   them from here, and `docsheet.py` reads `BASE_STYLES` here by design (the
   printed sheet may not import the shell). Dashboard-only rules belong in
   `DASH_STYLES`; the register-screen pattern `REGISTER_STYLES` stays here too,
   because it is a page pattern and not the chrome.

All HTML is built inline as f-strings — no /templates folder. The finished page
is returned to Flask directly and deliberately NOT re-parsed by Jinja; see the
note above `_page()`.

Import direction
----------------
This module may import `branding`, `store`, `pipeline` and `chrome` (none of
them import anything of ours at module level that imports us back, so there is
no cycle). It must **never** import `product`, `quotation` or `address` at
module level — those import *us*. The demo seeders are pulled in inside the
view function for that reason.

`db` is no longer imported here (14 September 2026): the persistence-failure
strip moved to `chrome.py` with `_nav()`, and `chrome.py` is what imports
`db.py` now, for the reason this docstring used to give.

Charts
------
Colours come from `branding.CHART_*` and are validated, not chosen by eye — see
the note above `CHART_NAVY` in branding.py. The funnel is an *ordinal* ramp (one
hue, light→dark, because stage order carries meaning); won/open/lost wear
reserved *status* colours and always ship with a text label beside the swatch.
"""

from datetime import date, datetime

from flask import Blueprint, url_for

import branding as B
import pipeline as P
from store import STORE

# ── The app chrome lives in chrome.py (14 September 2026) ────────────────────
# `BASE_STYLES`, `ICONS` and `_nav()` moved out of this module verbatim into
# the leaf `chrome.py`, so a page reaches its navigation without importing a
# module that computes dashboard metrics. They are imported back here because
# this page draws them, and `BASE_STYLES` and `_nav` are **re-exported** on
# purpose: `product.py` and `quotation.py` — both frozen — still read them from
# `dashboard`, and `docsheet.py` reads `BASE_STYLES` here by design, because
# the printed sheet may not import the shell (ABOUT.md §2k).
import chrome
from chrome import BASE_STYLES, ICONS, _nav  # noqa: F401  (re-exported)

# ── Blueprint Declaration ─────────────────────────────────────────────────────
# name="dashboard" is the namespace used in url_for(), e.g. url_for("dashboard.index")
dashboard_bp = Blueprint("dashboard", __name__)


# ── Dashboard-only styles ─────────────────────────────────────────────────────
# Layered AFTER BASE_STYLES and only on the landing page. Nothing in here is
# allowed to leak into product / quotation / address — if a rule belongs to more
# than one page it goes in BASE_STYLES instead.
#
# This is a plain string, not an f-string, so CSS braces are written once. Only
# the HTML below (which *is* an f-string) needs them doubled.
PLOT_H = 150   # px — column-chart plot height; segment heights are computed against it

DASH_STYLES = """
<style>
""" + B.CHART_TOKENS + """
  /* Wider than the app default: a dashboard is columns, a form is a column. */
  main.dash { max-width: 1240px; padding: 2rem 1.5rem 3.5rem; }

  /* ── Page head ───────────────────────────────────────────────────── */
  .dash-head {
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 1.25rem; flex-wrap: wrap;
    margin-bottom: 1.9rem; padding-bottom: 1.15rem;
    border-bottom: 1px solid var(--border);
  }
  .dash-head h1 {
    font-size: 1.6rem; font-weight: 700; letter-spacing: -.5px; line-height: 1.2;
  }
  .dash-head h1 em { font-style: normal; color: var(--brand); }
  .dash-head .dh-date {
    font-size: .8rem; color: var(--muted); margin-top: .2rem;
  }
  .dash-actions { display: flex; gap: .55rem; flex-wrap: wrap; }
  .dash-actions .btn { font-size: .84rem; padding: .58rem 1.15rem; }
  .dash-actions .btn svg { width: 15px; height: 15px; stroke: currentColor;
    fill: none; stroke-width: 2; stroke-linecap: round; }

  /* ── The BOQ call-to-action ──────────────────────────────────────── */
  /* The schedule is what this software exists to produce — measurement, RA
     bills and challans are all raised against one — so it is the first block
     under the page head and the largest control on the page. Navy, not brand
     red: the button is the red thing, and it must be the only red thing here. */
  .boq-cta {
    display: flex; align-items: center; gap: 1.6rem; flex-wrap: wrap;
    margin-bottom: 2.25rem; padding: 1.75rem 2rem;
    border-radius: var(--radius); color: #fff;
    background: linear-gradient(135deg, var(--navy-dk) 0%, var(--navy) 100%);
    box-shadow: var(--shadow-md);
  }
  .boq-cta .bc-icon {
    flex: 0 0 auto; width: 72px; height: 72px; border-radius: 18px;
    display: flex; align-items: center; justify-content: center;
    background: rgba(255,255,255,.12);
  }
  .boq-cta .bc-icon svg {
    width: 38px; height: 38px; stroke: #fff; fill: none;
    stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round;
  }
  .boq-cta .bc-text { flex: 1 1 320px; min-width: 0; }
  .boq-cta .bc-eyebrow {
    font-size: .72rem; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: rgba(255,255,255,.7); margin-bottom: .3rem;
  }
  .boq-cta h2 {
    font-size: 1.75rem; font-weight: 700; letter-spacing: -.5px;
    line-height: 1.15; color: #fff;
  }
  .boq-cta p {
    margin-top: .5rem; font-size: .92rem; line-height: 1.5;
    color: rgba(255,255,255,.82); max-width: 58ch;
  }
  .boq-cta .bc-stats { margin-top: .6rem; font-size: .8rem; color: rgba(255,255,255,.65); }
  .boq-cta .bc-act {
    flex: 0 0 auto; display: flex; flex-direction: column;
    align-items: stretch; gap: .6rem;
  }
  .boq-cta .bc-btn {
    font-size: 1.08rem; padding: 1rem 2.2rem; border-radius: 12px;
    justify-content: center; box-shadow: 0 8px 22px rgba(0,0,0,.28);
  }
  .boq-cta .bc-btn svg {
    width: 20px; height: 20px; stroke: currentColor; fill: none;
    stroke-width: 2.4; stroke-linecap: round;
  }
  .boq-cta .bc-link {
    font-size: .82rem; color: rgba(255,255,255,.8);
    text-decoration: none; text-align: center;
  }
  .boq-cta .bc-link:hover { color: #fff; text-decoration: underline; }

  /* ── Panel (the one container every block sits in) ───────────────── */
  .panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); box-shadow: var(--shadow-sm);
    display: flex; flex-direction: column;
  }
  /* Title, then an optional subtitle, then an optional link pinned right —
     works whether a panel head carries two children or three. */
  .panel-hd {
    display: flex; align-items: baseline; gap: .55rem;
    padding: 1.05rem 1.25rem .35rem;
  }
  .panel-hd a, .panel-hd .pn-sub:last-child { margin-left: auto; }
  .panel-hd h2 {
    font-size: .74rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .09em; color: var(--muted);
  }
  .panel-hd .pn-sub { font-size: .74rem; color: var(--muted); }
  .panel-hd a { font-size: .76rem; font-weight: 600; color: var(--brand);
    text-decoration: none; white-space: nowrap; }
  .panel-hd a:hover { text-decoration: underline; }
  /* Flex column so a panel stretched to match its neighbour distributes the
     slack instead of pooling it all at the bottom. */
  .panel-bd { padding: .85rem 1.25rem 1.25rem; flex: 1;
    display: flex; flex-direction: column; }
  .bd-funnel { justify-content: space-around; }

  /* ── Band: hero figure + supporting tiles ────────────────────────── */
  .band { display: grid; grid-template-columns: 1fr 1.85fr; gap: 1.15rem;
    margin-bottom: 0; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.1rem; }

  /* The project-billing tile row. `.kpi` and its three colour variants are
     reused verbatim — this rule changes the TRACK COUNT and nothing else, so
     the tiles are the same shape and the same colours as the quotation band's.
     auto-fit rather than a fixed three because this row is drawn per-permission
     and can legitimately hold one tile, two or three. */
  .kpis-chain { display: grid; gap: 1.1rem;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }

  /* The one hero number on the page. Proportional figures, not tabular —
     tabular digits make a large standalone number look loose. */
  .hero-fig {
    padding: 1.25rem 1.35rem 1.35rem;
    display: flex; flex-direction: column; justify-content: center; height: 100%;
  }
  .hero-fig .hf-lbl {
    font-size: .74rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .09em; color: var(--muted);
  }
  .hero-fig .hf-val {
    font-size: 3rem; font-weight: 700; line-height: 1.08; letter-spacing: -1.5px;
    color: var(--navy); margin: .35rem 0 .2rem;
  }
  .hero-fig .hf-sub { font-size: .84rem; color: var(--muted); }
  .hero-fig .hf-sub b { color: var(--text); font-weight: 600; }

  .kpi { padding: 1.05rem 1.25rem; display: flex; flex-direction: column;
    justify-content: center; }
  .kpi .k-lbl {
    font-size: .7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; color: var(--muted); margin-bottom: .4rem;
  }
  .kpi .k-val { font-size: 1.55rem; font-weight: 700; letter-spacing: -.7px;
    line-height: 1.1; }
  .kpi .k-sub { font-size: .75rem; color: var(--muted); margin-top: .25rem; }
  .kpi.k-won  .k-val { color: var(--c-won); }
  .kpi.k-hot  .k-val { color: var(--c-serious); }
  .kpi.k-rate .k-val { color: var(--navy); }

  /* The chain row has no hero to centre against, so its tiles are only as
     tall as the tallest of them — which is whichever one carries a meter.
     Centred, that tile's extra 14px lifted its label, figure and note ~7px
     above its neighbours': three tiles side by side reading at three
     different heights, which is what the row is for. Top-aligned, the
     labels sit on one line and the figures on one baseline, and the slack
     collects under the tiles that have no bar. The quotation band keeps
     centring — there the tiles are stretched to the hero beside them and
     there is real slack to centre in. */
  .kpis-chain .kpi { justify-content: flex-start; }

  /* Meter under the win-rate tile — the track is a lighter step of the same
     ramp, so the state reads across the whole bar rather than only the fill. */
  .meter { height: 5px; border-radius: 3px; background: var(--c-track);
    margin-top: .55rem; overflow: hidden; }
  .meter i { display: block; height: 100%; border-radius: 3px;
    background: var(--c-won); }

  /* ── Column layouts ──────────────────────────────────────────────── */
  /* stretch, not start: two panels of different content lengths still read as
     one row. .panel is a flex column with .panel-bd on flex:1, so the shorter
     one grows rather than leaving a ragged step down the page. */
  .cols     { display: grid; grid-template-columns: 1.1fr 1fr; gap: 1.15rem;
    margin-bottom: 0; align-items: stretch; }
  .cols-eq  { display: grid; grid-template-columns: 1fr 1fr; gap: 1.15rem;
    margin-bottom: 0; align-items: stretch; }

  /* ── Funnel (ordinal bars) ───────────────────────────────────────── */
  .fn-row {
    display: grid; grid-template-columns: 8.5rem 1fr 5.2rem;
    align-items: center; gap: .7rem; padding: .3rem 0;
    text-decoration: none; color: inherit; border-radius: 7px;
  }
  .fn-row:hover { background: var(--bg); }
  .fn-name { font-size: .8rem; color: var(--text); }
  .fn-row:hover .fn-name { color: var(--brand); }
  .fn-track { background: var(--c-track); border-radius: 0 4px 4px 0; height: 14px; }
  /* Square at the baseline, 4px rounded at the data end. */
  .fn-bar { height: 100%; border-radius: 0 4px 4px 0; min-width: 2px;
    transition: filter .15s; }
  .fn-row:hover .fn-bar { filter: brightness(1.08); }
  .fn-val { text-align: right; font-size: .8rem; font-weight: 600;
    font-variant-numeric: tabular-nums; }
  .fn-n { display: block; font-size: .68rem; color: var(--muted); font-weight: 500;
    letter-spacing: .01em; }
  .fn-empty .fn-val, .fn-empty .fn-name { color: var(--muted); font-weight: 500; }

  /* ── Monthly activity (stacked columns) ──────────────────────────── */
  .mc-plot {
    display: flex; align-items: flex-end; justify-content: space-around;
    gap: .5rem; padding-top: 1.6rem;
  }
  .mc-col { flex: 1; display: flex; flex-direction: column; align-items: center;
    position: relative; cursor: default; border-radius: 8px; }
  /* Columns are keyboard-reachable so the tooltip is not mouse-only — which
     means they need a visible ring, not outline:none. */
  .mc-col:focus-visible { outline: 2px solid var(--navy); outline-offset: 2px; }
  .mc-cap { font-size: .7rem; font-weight: 600; color: var(--muted);
    margin-bottom: .35rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
  /* column-reverse so the first segment in the DOM sits on the baseline;
     the 2px gap is the surface doing the separating, never a border. */
  .mc-stack { display: flex; flex-direction: column-reverse; gap: 2px;
    width: 100%; max-width: 34px; }
  .mc-seg { flex: 0 0 auto; width: 100%; }
  .mc-seg:last-child { border-radius: 4px 4px 0 0; }
  .mc-seg.s-won  { background: var(--c-won); }
  .mc-seg.s-open { background: var(--c-open); }
  .mc-seg.s-lost { background: var(--c-lost); }
  .mc-base { width: 100%; max-width: 34px; height: 1px; background: var(--c-grid); }
  .mc-x { font-size: .72rem; color: var(--muted); margin-top: .45rem;
    text-align: center; }
  .mc-x span { display: block; font-size: .62rem; opacity: .7; }

  .mc-tip {
    position: absolute; bottom: 100%; left: 50%;
    transform: translateX(-50%) translateY(-4px);
    background: var(--navy); color: #fff; border-radius: 8px;
    padding: .5rem .7rem; font-size: .72rem; line-height: 1.5;
    white-space: nowrap; opacity: 0; pointer-events: none;
    transition: opacity .12s; z-index: 20;
    box-shadow: 0 6px 18px rgba(26,22,38,.22);
  }
  .mc-col:hover .mc-tip, .mc-col:focus .mc-tip { opacity: 1; }
  .mc-col:first-child .mc-tip { left: 0; transform: translateX(0) translateY(-4px); }
  .mc-col:last-child  .mc-tip { left: auto; right: 0;
    transform: translateX(0) translateY(-4px); }
  .mc-tip b { font-weight: 700; }
  .mc-tip .tp-row { display: flex; gap: .5rem; justify-content: space-between; }
  .mc-tip .tp-row span:first-child { opacity: .78; }

  /* Legend — always present for two or more series, and it carries the
     period totals so no value is reachable only by hovering. */
  /* margin-top:auto pins the legend to the foot of the panel, so a stretched
     chart card reads as padded rather than half-empty. */
  .lg { display: flex; gap: 1.05rem; flex-wrap: wrap; padding-top: .95rem;
    margin-top: auto; border-top: 1px solid var(--border); }
  .lg-item { display: flex; align-items: center; gap: .4rem; font-size: .76rem;
    color: var(--muted); }
  .lg-dot { width: 9px; height: 9px; border-radius: 3px; flex-shrink: 0; }
  .lg-item b { color: var(--text); font-weight: 600;
    font-variant-numeric: tabular-nums; }

  /* ── Attention queue ─────────────────────────────────────────────── */
  .attn-row {
    display: grid; grid-template-columns: 22px 1fr auto; gap: .65rem;
    align-items: start; padding: .6rem .55rem; border-radius: 9px;
    text-decoration: none; color: inherit;
    border-left: 3px solid var(--border); margin-bottom: .3rem;
  }
  .attn-row:hover { background: var(--bg); }
  .attn-row.t-lost    { border-left-color: var(--c-lost); }
  .attn-row.t-serious { border-left-color: var(--c-serious); }
  .attn-row.t-warn    { border-left-color: var(--c-warn); }
  .attn-ico svg { width: 16px; height: 16px; fill: none; stroke-width: 1.9;
    stroke-linecap: round; stroke-linejoin: round; margin-top: 2px; }
  .t-lost    .attn-ico svg { stroke: var(--c-lost); }
  .t-serious .attn-ico svg { stroke: #B4571F; }
  .t-warn    .attn-ico svg { stroke: #8A5A00; }
  .attn-ref { font-size: .82rem; font-weight: 700; }
  .attn-row:hover .attn-ref { color: var(--brand); }
  .attn-acct { font-size: .78rem; color: var(--muted); }
  .attn-why { font-size: .74rem; color: var(--text); margin-top: .15rem; }
  .attn-val { font-size: .8rem; font-weight: 600; text-align: right;
    white-space: nowrap; font-variant-numeric: tabular-nums; }
  .attn-more { font-size: .75rem; color: var(--muted); padding: .55rem 0 0; }

  /* ── Recent quotations ───────────────────────────────────────────── */
  .rq-row {
    display: grid; grid-template-columns: 1fr auto; gap: .7rem;
    align-items: center; padding: .55rem; border-radius: 9px;
    text-decoration: none; color: inherit;
    /* Pulled back out by its own padding, so the hover background bleeds
       into the panel's inner margin while the TEXT still starts on the
       same line as the panel head. */
    margin: 0 -.55rem;
  }
  .rq-row + .rq-row { border-top: 1px solid var(--border); border-radius: 0; }
  .rq-row:hover { background: var(--bg); }
  .rq-ref { font-size: .82rem; font-weight: 700; }
  .rq-row:hover .rq-ref { color: var(--brand); }
  .rq-acct { font-size: .78rem; color: var(--muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 22ch; }
  .rq-meta { display: flex; align-items: center; gap: .5rem; }
  /* The activity feed's type badge. Deliberately quieter than
     `P.stage_badge()` beside it in the recent-quotations panel: this one
     separates two document kinds, it does not carry a status. */
  .act-kind { font-size: .62rem; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; padding: 1px 6px; border-radius: 9px;
    border: 1px solid var(--border); color: var(--muted); }
  .act-kind.ak-boq { color: var(--navy); border-color: var(--navy); }
  .act-kind.ak-ra  { color: var(--c-won); border-color: var(--c-won); }

  /* Per-project progress. The bar is `.meter`, reused verbatim from the
     win-rate tile — same track, same fill, same 5px height. The row is padded
     and pulled back by the same .55rem as `.rq-row`, which leaves the text
     where it was but starts and ends the separator where the activity panel
     beside it starts and ends its own. */
  .pp-row { padding: .7rem .55rem; margin: 0 -.55rem; }
  .pp-row + .pp-row { border-top: 1px solid var(--border); }
  .pp-hd { display: flex; justify-content: space-between; align-items: baseline;
    gap: .8rem; margin-bottom: .35rem; }
  .pp-name { font-size: .82rem; font-weight: 700; }
  .pp-name a { color: inherit; text-decoration: none; }
  .pp-name a:hover { color: var(--brand); }
  .pp-fig { font-size: .76rem; color: var(--muted); white-space: nowrap; }
  .pp-note { font-size: .7rem; color: var(--muted); margin-top: .3rem; }

  .rq-right { text-align: right; }
  .rq-val { font-size: .84rem; font-weight: 600;
    font-variant-numeric: tabular-nums; }
  .rq-date { font-size: .7rem; color: var(--muted); }

  /* ── Catalogue mini-stats ────────────────────────────────────────── */
  .mini { display: grid; grid-template-columns: repeat(2, 1fr); gap: .8rem; }
  .mini div { background: var(--bg); border-radius: 10px; padding: .7rem .85rem; }
  .mini .mn-val { font-size: 1.3rem; font-weight: 700; letter-spacing: -.5px;
    color: var(--navy); }
  .mini .mn-lbl { font-size: .72rem; color: var(--muted); }

  /* ── Module zones (the launcher, redrawn 14 September 2026) ─────────── */
  /* Four zones, one per group in `chrome.GROUPS`, each on its group's own
     zone tint with the group's accent on the header dot, the rule and the
     roll-up pill. The cards inside are auto-filled at a 238px floor: a zone
     is one group, so the column-count drift that made a fixed four-column
     grid necessary across groups no longer has anything to drift against. */
  .mods { display: grid; grid-template-columns: repeat(auto-fill, minmax(238px, 1fr));
    gap: 12px; align-items: stretch; }
  .mods .card {
    min-height: 146px; padding: 15px 16px 16px; gap: .5rem;
    flex-direction: column; align-items: stretch;
    border-radius: 14px; border-color: var(--border);
  }
  /* The red hover bar belongs to the generic card; a zone card's hover is the
     group accent on its border, a 2px lift and the chevron sliding right. */
  .mods .card::before { display: none; }
  .mods .card:hover { transform: translateY(-2px); border-color: var(--ga);
    box-shadow: var(--shadow-md); }
  .mods .card-icon { width: 38px; height: 38px; border-radius: 10px;
    background: var(--gt); }
  .mods .card-icon svg { width: 19px; height: 19px; stroke: var(--ga); }
  .mods .card:hover .card-icon { background: var(--gt); }
  .mods .card:hover .card-icon svg { stroke: var(--ga); }
  .mods .card-body { display: flex; flex-direction: column; gap: .3rem; }
  .mods .card-title { font-size: 14.5px; font-weight: 600; margin-bottom: 0; }
  .mc-fig { display: flex; align-items: baseline; gap: .4rem; }
  .mc-fig b { font-size: 25px; font-weight: 700; line-height: 1.1;
    letter-spacing: -.5px; color: var(--ga); font-variant-numeric: tabular-nums; }
  .mc-unit { font-size: 13px; font-weight: 600; color: var(--muted); }
  /* Pinned to the foot of the card, whatever the figure row above it did. */
  .mods .card-desc { font-size: 12px; line-height: 1.45; margin-top: auto;
    padding-top: .35rem; }
  .mc-chev { position: absolute; right: 14px; top: 17px; width: 16px; height: 16px;
    color: var(--muted); transition: transform .15s ease; }
  .mc-chev svg { width: 16px; height: 16px; stroke: currentColor; fill: none;
    stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .mods .card:hover .mc-chev { transform: translateX(2px); }

  /* ── Status chips — an icon AND a word, always ──────────────────────── */
  /* Amber and red are ~ΔE 2.2 apart under deuteranopia, effectively one
     colour; the word is what carries the meaning, the colour reinforces it. */
  .chip { display: inline-flex; align-items: center; gap: .3rem;
    font-size: .66rem; font-weight: 700; letter-spacing: .03em;
    padding: .12rem .5rem .12rem .4rem; border-radius: 999px; white-space: nowrap;
    vertical-align: middle; }
  .chip svg { width: 12px; height: 12px; stroke: currentColor; fill: none;
    stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
  .chip-good { color: var(--st-good); background: var(--st-good-bg); }
  .chip-warn { color: var(--st-warn); background: var(--st-warn-bg); }
  .chip-crit { color: var(--st-crit); background: var(--st-crit-bg); }
  .attn-ref .chip { margin-left: .35rem; }

  /* ── Zones — the page reads as bands, not as one wall ────────────── */
  /* Every block used to carry the same weight and the same 1.1rem gap, so the
     hero, four analysis panels and a fifteen-card launcher ran together as one
     undifferentiated mass. A labelled hairline every few blocks gives the eye
     somewhere to stop and tells it what it is about to read. Presentation
     only — no figure, link or metric changes. */
  .zone { margin-top: 2.75rem; }
  .zone-hd { display: flex; align-items: center; gap: .8rem; margin-bottom: 1rem; }
  .zone-hd h2 {
    font-size: .72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .12em; color: var(--muted); white-space: nowrap;
  }
  .zone-hd .zn-sub { font-size: .76rem; color: var(--muted); white-space: nowrap; }
  /* The rule takes whatever width is left, so the label sits flush left and the
     line always reaches the right edge at any viewport. */
  .zone-hd::after { content: ''; flex: 1; height: 1px; background: var(--border); }
  /* A zone that stacks two blocks — the project zone puts a tile row on a
     panel row — had nothing between them at all: every grid here sets its
     gutter ACROSS and none of them set one DOWN, so the tiles sat flush on
     the panels beneath while holding 1.1rem from each other. One gutter,
     both directions. The head is exempt: it is a label for the block under
     it, not another block, and keeps its own tighter gap. */
  .zone > * + * { margin-top: 1.15rem; }
  .zone-hd + * { margin-top: 0; }

  /* ── Module zones' headers ───────────────────────────────────────── */
  /* The launcher is split by which pipeline a register belongs to (§1). The
     group colours are `chrome.GROUPS`' four — carried as custom properties by
     the `g-*` class the zone wears, so the rail and this page cannot disagree
     about which colour the buy side is. They are identity tokens, never
     CHART_*: a status colour must not be spent on decoration (§6). */
  .mod-group {
    border-radius: 16px; padding: 16px;
    background: var(--gz, var(--surface)); border: 1px solid #EFECF4;
  }
  .mod-group + .mod-group { margin-top: 1.1rem; }
  .mg-hd { display: flex; align-items: center; gap: .6rem; margin-bottom: .9rem; }
  .mg-dot { width: 9px; height: 9px; border-radius: 3px; background: var(--ga);
    flex-shrink: 0; }
  .mg-hd h3 { font-size: 15px; font-weight: 700; color: var(--text); white-space: nowrap; }
  .mg-hd .mg-note { font-size: 12px; color: var(--muted); }
  .mg-rule { flex: 1; height: 1px; background: var(--ga); opacity: .22; }
  .mg-pill { font-size: 12px; font-weight: 600; color: var(--ga); background: var(--gt);
    border-radius: 999px; padding: .22rem .7rem; white-space: nowrap;
    font-variant-numeric: tabular-nums; }

  /* ── Empty state ─────────────────────────────────────────────────── */
  .empty { text-align: center; padding: 2.6rem 1.5rem; }
  .empty h3 { font-size: 1.05rem; font-weight: 700; margin-bottom: .35rem; }
  .empty p { font-size: .86rem; color: var(--muted); max-width: 42ch;
    margin: 0 auto 1.3rem; }
  /* margin:auto centres the "nothing to chase" message in a panel that has
     been stretched to match a taller neighbour. */
  .panel-bd .none { font-size: .82rem; color: var(--muted); padding: 1.1rem 0;
    text-align: center; margin: auto; max-width: 34ch; }

  /* ── Responsive ──────────────────────────────────────────────────── */
  /* The zone grid auto-fills, so it needs no column rules of its own; the
     rail's one breakpoint (chrome.CHROME_STYLES) is what reflows the page. */
  @media (max-width: 1000px) {
    .band { grid-template-columns: 1fr; }
    .cols, .cols-eq { grid-template-columns: 1fr; }
  }
  @media (max-width: 620px) {
    main.dash { padding: 1.5rem 1rem 3rem; }
    .zone { margin-top: 2.1rem; }
    .kpis, .kpis-chain { grid-template-columns: 1fr; }
    /* The group note and the roll-up pill are context, not content — together
       they double the header height on a phone, and the coloured dot already
       separates the zones. */
    .mg-hd .mg-note, .mg-pill { display: none; }
    .hero-fig .hf-val { font-size: 2.4rem; }
    .fn-row { grid-template-columns: 6.5rem 1fr 4.4rem; gap: .5rem; }
    .dash-head { align-items: flex-start; }
    .dash-actions { width: 100%; }
    .dash-actions .btn { flex: 1; justify-content: center; }
    .boq-cta { padding: 1.4rem 1.25rem; gap: 1.1rem; }
    .boq-cta .bc-icon { display: none; }
    .boq-cta h2 { font-size: 1.4rem; }
    .boq-cta .bc-act { width: 100%; }
  }
</style>
"""


# =============================================================================
# REGISTER_STYLES — one affordance pattern for the register SCREENS
# =============================================================================
#
# Added 30 August 2026, under the third override block of that date, after the
# owner opened `/attendance/` and `/dc/` — **the only two pages in this
# application that have ever been rendered to a human eye** — and reported that
# they are confusing, that the attendance table is misaligned, and that on
# Delivery Challans he cannot tell what to click.
#
# ⚠ **IT IS A SEPARATE CONSTANT AND IS DELIBERATELY NOT IN `BASE_STYLES`.**
#   `BASE_STYLES` is on every page in this app **including every printed one**,
#   so a rule added there moves five pinned print goldens for a change that has
#   nothing to do with paper (ABOUT.md §7's first gap). `USER_CHIP_STYLES` above
#   is the precedent: a constant that lives here and is emitted only where it is
#   wanted. This one is loaded by `/attendance/` and `/dc/` and by nothing else,
#   so **no golden moves and none could.**
#
# ⚠ **It lives HERE rather than being written twice**, and that is the whole
#   point of it. `attendance.py` and `challan.py` share no ancestor except this
#   module, so two copies of "what a register row looks like" is two copies that
#   drift — which is the defect `docsheet.py` was extracted to end, four
#   letterheads along. The brief for this pass required the two registers to
#   match each other; one definition is how that stays true after the next edit.
#
# ⚠ **The other thirteen registers do NOT load it, and must not be given it
#   without somebody looking at them.** The owner has not seen them. Restyling a
#   page nobody has opened is how a pass ships a regression that only surfaces
#   months later, and the pass report names every register now inconsistent with
#   these two so the next one can take them deliberately.
#
# Four rules, and each answers something the owner actually said:
#
#   1. **Numeric columns are right-aligned WITH THEIR HEADERS.** `.num` on the
#      `<th>` as well as the `<td>`. The attendance table had the class on both
#      and still came out ragged, because `.att-table th { text-align:left }`
#      (specificity 0,1,1) beat `.att-amt` (0,1,0) — so every money header sat
#      left over a right-aligned column. `.reg-table th.num` is 0,2,1 and wins.
#   2. **One primary action per row**, `.reg-open`: a bordered pill with a word
#      in it. A bare number rendered as a link is a reference, not a target.
#   3. **Secondary links are visibly secondary** (`.reg-sub`), and the
#      destructive one is de-weighted (`.reg-danger`) rather than carrying the
#      same weight as Edit.
#   4. **Actions live inside a real column** with a real header. Buttons hanging
#      off the right edge are what pushed the TOTAL column out of the table.
REGISTER_STYLES = """
<style>
  /* One card per table, so two tables on one page are one visual language
     rather than one bare and one boxed. */
  .reg-card {
    background: #fff; border: 1px solid var(--border);
    border-radius: var(--radius); margin-bottom: 1.2rem; overflow: hidden;
  }
  .reg-head {
    display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
    padding: .85rem 1.1rem; border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .reg-title {
    font-size: .78rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .06em; color: var(--navy);
  }
  .reg-note { font-size: .8rem; color: var(--muted); }
  .reg-scroll { overflow-x: auto; }

  .reg-table { width: 100%; border-collapse: collapse; }
  .reg-table th {
    text-align: left; padding: .55rem .8rem;
    border-bottom: 1px solid var(--border);
    font-size: .7rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .05em; white-space: nowrap;
  }
  .reg-table td {
    padding: .6rem .8rem; border-bottom: 1px solid var(--border);
    font-size: .86rem; vertical-align: middle;
  }
  .reg-table tbody tr:last-child td { border-bottom: none; }
  .reg-table tbody tr:hover { background: var(--surface); }

  /* ⚠ RULE 1. The header carries `.num` too, and this selector is what makes
     that stick against the bare `th` rule above. */
  .reg-table th.num, .reg-table td.num {
    text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap;
  }
  .reg-table tfoot td {
    padding: .6rem .8rem; border-top: 2px solid var(--border);
    font-size: .86rem; background: var(--surface);
  }
  .reg-sub-line { display: block; font-size: .76rem; color: var(--muted); }

  /* A reference code must never break mid-code — `SF/BOQ/26-27/` on one line
     and `0001` on the next makes the row taller and reads as broken. */
  .reg-ref { white-space: nowrap; font-variant-numeric: tabular-nums; }

  /* ⚠ RULE 4. A real column with a real header, and its contents on one line. */
  .reg-acts { text-align: right; white-space: nowrap; }
  .reg-acts > * + * { margin-left: .45rem; }

  /* ⚠ RULE 2. THE primary action. A bordered pill with a word in it, because a
     bare number rendered as a link reads as a reference and not as a target. */
  .reg-open {
    display: inline-block; text-decoration: none;
    font-size: .78rem; font-weight: 700; white-space: nowrap;
    color: var(--brand); background: #fff;
    border: 1px solid var(--brand); border-radius: 6px;
    padding: .28rem .7rem;
  }
  .reg-open:hover { background: var(--brand); color: #fff; }
  .reg-open .ro-arrow { opacity: .65; margin-left: .25rem; }

  /* ⚠ RULE 3. Secondary, and visibly so: no border, muted until hovered. */
  .reg-sub {
    display: inline-block; text-decoration: none;
    font-size: .78rem; font-weight: 600; white-space: nowrap;
    color: var(--muted); border: 1px solid transparent; border-radius: 6px;
    padding: .28rem .5rem;
  }
  .reg-sub:hover { color: var(--navy); border-color: var(--border); }

  /* ⚠ RULE 3, the destructive half. Quieter than Edit until it is hovered,
     because it destroys a record and Edit does not. */
  .reg-danger {
    display: inline-block; text-decoration: none;
    font-size: .78rem; font-weight: 600; white-space: nowrap;
    color: var(--muted); border: 1px solid transparent; border-radius: 6px;
    padding: .28rem .5rem;
  }
  .reg-danger:hover { color: var(--brand); border-color: var(--brand); }

  .reg-empty {
    padding: 2rem 1.1rem; text-align: center; color: var(--muted);
    font-size: .88rem;
  }

  /* Registers are screens. Nothing here prints, and this rule is what keeps a
     future printed page that happens to load this sheet from carrying it. */
  @media print { .reg-card { display: none !important; } }
</style>
"""


# The same idea one level in, for the dashboard's own action bar.
ACTION_SEP = "\n            "


def _footer_contact() -> str:
    """
    Contact strip for the dashboard footer.

    Until the client's real address / phone / email are entered there is
    nothing honest to print, so we show a setup nudge instead of a half-empty
    contact line — and the nudge links to the page that fixes it.
    """
    if not B.has(B.COMPANY_ADDR, B.COMPANY_PHONE, B.COMPANY_EMAIL):
        return (f'<p class="foot-contact">Company details are not filled in yet — '
                f'add address, phone, e-mail, GSTIN and PAN in '
                f'<a href="{url_for("settings.edit_settings")}"><b>Settings</b></a> '
                f'before issuing a quotation.</p>')
    return (f'<p class="foot-contact">{P.esc(B.COMPANY_ADDR)} &nbsp;·&nbsp; '
            f'<b>{P.esc(B.COMPANY_PHONE)}</b> &nbsp;·&nbsp; {P.esc(B.COMPANY_EMAIL)}</p>')


# =============================================================================
# MONEY & DATE HELPERS
# =============================================================================
# Indian digit grouping lives here rather than being imported, because
# quotation._inr() belongs to the printed document (no symbol, always 2dp) and
# quotation.py imports *us* — pulling it the other way would be a cycle.

def inr(v) -> str:
    """
    Indian digit grouping, no decimals: 13150000 -> '1,31,50,000'.
    Screen money only. The printed quotation has its own _inr() in quotation.py.
    """
    n = int(round(float(v or 0)))
    sign, s = ("-", str(-n)) if n < 0 else ("", str(n))
    if len(s) > 3:
        last3, rest = s[-3:], s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        s = ",".join(groups + [last3])
    return sign + s


def compact(v) -> str:
    """
    Dashboard-scale money in the units the trade actually speaks: crore and
    lakh. 13150000 -> '1.32 Cr'. Below a lakh it falls back to full grouping,
    because '0.45 L' is not how anyone says forty-five thousand.
    """
    n = float(v or 0)
    a = abs(n)
    if a >= 1e7:
        return f"{n / 1e7:.2f}".rstrip("0").rstrip(".") + " Cr"
    if a >= 1e5:
        return f"{n / 1e5:.2f}".rstrip("0").rstrip(".") + " L"
    return inr(n)


def rupees(v) -> str:
    """Compact money with the rupee sign, for tiles and chart labels."""
    return f"&#8377;&nbsp;{compact(v)}"


def _pdate(raw):
    """
    Parse a stored date leniently. Handles both the ISO dates the forms write
    ('2026-07-31') and pipeline's history stamps ('2026-07-31 14:22'), and
    returns None for anything else rather than raising — a hand-edited record
    must not be able to 500 the landing page.
    """
    s = str(raw or "").strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _last_touch(q):
    """Date this deal last moved — newest history stamp, else its issue date."""
    stamps = [d for d in (_pdate(h.get("at")) for h in (q.get("stage_history") or [])) if d]
    return max(stamps) if stamps else _pdate(q.get("date"))


# =============================================================================
# DASHBOARD METRICS
# =============================================================================
# Business rules that might change, kept as named constants rather than buried
# in a branch (see pipeline.REQUIRE_PO_FOR_WON for the same convention).

STALE_DAYS      = 21   # an open deal untouched this long is flagged as drifting
TREND_MONTHS    = 6    # columns in the monthly activity chart
ATTENTION_LIMIT = 6    # rows shown in the work queue before "+N more"
RECENT_LIMIT    = 6    # rows shown in the recent-quotations panel

# The BOQ/RA panels below follow the two caps above rather than picking their
# own. Six is not arbitrary here: the activity feed and the progress list sit in
# the same `.cols` grid as the work queue and the recent-quotations panel, and a
# panel of ten beside a panel of six makes the row ragged for no gain. If these
# ever need to differ from `RECENT_LIMIT`, they are separate names so that they
# can — they are not aliases.
ACTIVITY_LIMIT  = 6    # rows in the BOQ/RA activity feed before "+N more"
PROGRESS_LIMIT  = 6    # projects shown in the claimed-vs-approved list


def _month_sequence(today, n=TREND_MONTHS):
    """The last `n` calendar months, oldest first, as (year, month) pairs."""
    seq = []
    y, m = today.year, today.month
    for _ in range(n):
        seq.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(seq))


def _attention(quotations, today):
    """
    The work queue: open deals that need a human today, newest problem first.

    Four rules, in priority order. A deal is only ever flagged once — the most
    urgent reason wins, so the list stays a list of *deals*, not of warnings.
    """
    rows = []
    for qid, q in quotations.items():
        stage    = P.stage_of(q)
        value    = float(q.get("grand_total") or 0.0)
        exp      = _pdate(q.get("exp_closing"))
        touched  = _last_touch(q)
        idle     = (today - touched).days if touched else None

        if P.is_open(q):
            if exp and exp < today:
                days = (today - exp).days
                rows.append((0, "lost", "overdue", qid, q, value,
                             f"{days} day{'s' if days != 1 else ''} past expected close "
                             f"({exp.strftime('%d %b')})"))
            elif stage == "PO Expected":
                rows.append((1, "serious", "await", qid, q, value,
                             "Quoted and agreed — chase the customer's PO"))
            elif idle is not None and idle >= STALE_DAYS:
                rows.append((2, "warn", "stale", qid, q, value,
                             f"No movement in {idle} days"))
        elif P.is_won(q) and not (q.get("po_number") or "").strip():
            rows.append((1, "warn", "nopo", qid, q, value,
                         "Marked won, but no customer PO number is on file"))

    # Most urgent first, then biggest money first inside a tier.
    rows.sort(key=lambda r: (r[0], -r[5]))
    return rows


# ── The BOQ/RA chain, read the way `_metrics()` already reads the PO chain ────
#
# ⚠ **Every predicate below matches a string LITERALLY rather than importing the
# module that owns it**, and that is the same one-way trick `_metrics()` already
# runs for `purchase.PO_STATUSES` and for `ra.STATUSES` under
# `client_outstanding`. dashboard.py is imported BY boq.py and ra.py for
# `BASE_STYLES` and `_nav()`, so an import back is a cycle at boot — and
# `boq.py` may not import `ra.py` either (ABOUT.md §2b). There is no arrangement
# of imports that lets this file call the canonical helpers.
#
# **The equivalences are asserted rather than commented.**
# `tests/test_dashboard_boq_ra.py` sweeps every value of `ra.STATUSES` and every
# value of `approval.STATUSES` against these predicates and fails on any
# disagreement, which is the shape `tests/test_approval_b7.py` already uses to
# hold `print_exempt_states` against `ra.status_of()`. A comment claiming two
# functions agree is worth nothing; a test that fails when they stop agreeing is
# worth what this depends on.


def _boq_is_open(bid: str, superseded: set) -> bool:
    """
    Is this BOQ the live schedule rather than one a revision has replaced?

    ⚠ **"Open" is NOT a status field, and inventing one would have been the
    wrong answer.** `boq.py` has no BOQ status at all: the only thing that
    distinguishes a live schedule from a dead one is whether some *other* BOQ
    names it in `supersedes`, which is exactly what `boq.superseded_ids()`
    computes and what `view_boq()` calls `is_tip`. This mirrors that set rather
    than adding a second notion of open-ness for the dashboard to disagree with.
    """
    return bid not in superseded


def _superseded_boq_ids() -> set:
    """`boq.superseded_ids()`, computed here for the import reason above."""
    return {str(b.get("supersedes") or "")
            for b in (STORE.get("boqs") or {}).values()
            if str(b.get("supersedes") or "")}


def _ra_is_cancelled(bill) -> bool:
    """
    `ra.is_cancelled()`, literally.

    ⚠ **A literal match is exactly equivalent here, and the reason is worth
    stating.** `ra.status_of()` returns the normalised value unchanged when it
    is one of `ra.STATUSES` and returns `"issued"` for everything else —
    `"cancelled"` is in `STATUSES`, so a raw value normalising to it is the only
    way `is_cancelled()` is true. **An unrecognised status reads as issued, not
    as cancelled**, which is the safe direction: it counts a hand-edited record
    toward the claimed total rather than silently dropping money out of it.
    """
    return str((bill or {}).get("status") or "").strip().lower() == "cancelled"


def _ms_counts(sheet) -> bool:
    """`measurement.feeds_ceiling()`, through the predicate it reads."""
    import approval as _AP
    return _AP.accepted(sheet)


def _ra_awaits_approval(bill) -> bool:
    """
    Is this bill actually waiting on somebody's approval?

    Three exclusions, and **the grandfather one is the whole reason this is a
    function rather than an inline `== "pending"`:**

    * ⚠ **A GRANDFATHERED bill is not pending.** `approval.status_of()` reads a
      record carrying no `approval_status` as `pending`, which is the right
      default for a *gate* — it is the state that grants nothing. It is the
      wrong answer for a *count*: every bill written before the B6 ladder
      existed carries `pre_approval_system`, reads as `pending` forever, and
      will never be approved by anybody because `approval.can_print()` exempts
      it from the ladder entirely. On the live database on 5 September 2026
      **all seven RA bills are grandfathered**, so a naive count reports "7
      awaiting approval" when the true figure — the number of bills a Director
      or Operation Head could actually action — is **0**. A work-queue tile that
      is permanently wrong by the size of the historical set is worse than no
      tile.
    * **A cancelled bill is not pending.** A withdrawn claim is waiting on
      nobody, exactly as `claimed_by_line()` releases its quantity.
    * **A rejected bill is not pending.** It is waiting on its author, not on an
      approver, and `approval.status_of()` already tells the two apart.

    A **draft** bill DOES count, and that half is deliberate: the ladder applies
    to it, `approval.can_approve()` will act on it, and its claim is committed
    against the schedule the moment it is saved — the same reasoning that makes
    `claimed_by_line()` count drafts.
    """
    if bill is None:
        return False
    # ⚠ Nothing awaits an approver while the ladder is OFF, and a bill raised
    #   while it was off never will (12 September 2026). `approval.gated()` is
    #   that answer; imported in the function body because this module sits
    #   at the bottom of the graph and approval.py reads it back through the
    #   same hatch.
    import approval as _AP
    if not _AP.gated(bill):
        return False
    if bill.get("pre_approval_system"):
        return False
    if _ra_is_cancelled(bill):
        return False
    status = str(bill.get("approval_status") or "").strip().lower()
    # `approval.status_of()`: anything unrecognised — including absent — is
    # `pending`. Mirrored exactly, minus the grandfathered set removed above.
    return status not in ("approved", "rejected")


def _pct_label(pct: float) -> str:
    """
    A percentage for display, where **a non-zero share never reads as `0%`**.

    `f"{0.104:.0f}%"` is `"0%"`, and "₹9,585 claimed · 0% of open schedules" reads
    as a figure that failed to load rather than as a portfolio barely started —
    which is what a small claim against a ₹92 lakh book of schedules actually is.
    `<1%` says the true thing in the same width. The reverse case matters for the
    same reason: 99.6% must not round to `100%` on a schedule that is not
    finished, so anything short of complete rounds DOWN to `>99%`.
    """
    if pct > 0.0 and pct < 1.0:
        return "&lt;1%"
    if 99.0 < pct < 100.0:
        return "&gt;99%"
    return f"{pct:.0f}%"


def _boq_ra() -> dict:
    """
    The project-billing figures, in one pass over `boqs` and `ra_bills`.

    Split out of `_metrics()` rather than inlined because it is the one block on
    this page whose correctness depends on a *unit* — every amount it returns is
    tax-exclusive — and a function boundary is where that can be stated once and
    tested.
    """
    boqs      = STORE.get("boqs") or {}
    bills     = STORE.get("ra_bills") or {}
    supersede = _superseded_boq_ids()

    open_ids = [bid for bid in boqs if _boq_is_open(bid, supersede)]

    # ── The money, and the ONE rule that governs all of it ────────────────
    #
    # ⚠ **EVERY FIGURE BELOW IS TAX-EXCLUSIVE, AND `grand_total` APPEARS
    # NOWHERE.** This is ABOUT.md §7 gap 31, which is a live display bug on
    # `/boq/view` and has already cost one real over-claim investigation: that
    # panel puts a *Total Basic Value* tile (tax-exclusive, labelled "taxes
    # extra") inches from RA chips rendering `grand_total` (tax-inclusive,
    # labelled nothing). BOQ `SF/BOQ/26-27/0006` was reported as ~18% over-
    # claimed on 3 September 2026 and was not over-claimed at all — the
    # ₹1,725 "overage" was the GST.
    #
    # So the two sides here are the same KIND of number and can legitimately be
    # compared: `subtotal` is the BOQ's stored basic value (the field behind the
    # sheet's "Total Basic Value" label) and `claim_subtotal` is the bill's
    # claim before tax and before deductions.
    #
    # ⚠ **`net_payable` is NOT the figure either**, though it is also tax-
    # exclusive. It is `claim_subtotal - deduction_total`, and retention
    # withheld against a claim does not reduce what was *claimed* against the
    # schedule — it is money held back from a claim that still stands at its
    # full value. The existing `ra_value` key above uses `net_payable` and is
    # left exactly as it is: it answers a different question on a different
    # card, and changing it is not this pass's to do.
    claimed = sum(float(b.get("claim_subtotal") or 0.0)
                  for b in bills.values() if not _ra_is_cancelled(b))

    return {
        # Open BOQs — the live schedules. A superseded revision is not a second
        # schedule, it is the same one before it was corrected, so counting both
        # would report two jobs where the client has one.
        "boq_open_count":   len(open_ids),
        "boq_revised_count": len(boqs) - len(open_ids),

        # Bills genuinely waiting on an approver. See `_ra_awaits_approval()` —
        # the grandfathered set is excluded and that exclusion is load-bearing.
        "ra_pending_count": sum(1 for b in bills.values()
                                if _ra_awaits_approval(b)),

        # ── What has actually been claimed, and against what ──────────────
        #
        # ⚠ **`claimed_by_line()`'s SEMANTICS, in money.** That helper is the
        # single place anything asks how much has been claimed, and it answers
        # in QUANTITY keyed by `(line_id, leg)` — there is no money in it to
        # reuse, so what is borrowed here is its rule rather than its return
        # value: **drafts and issued bills both count, cancelled ones do not.**
        # A draft's claim is committed against the schedule the moment it is
        # saved; a cancelled bill released its claim, which is the entire point
        # of having a cancel. `claims_by_line_id()` is the wrong helper to
        # follow — it deliberately keeps cancelled bills because it answers
        # "has this line ever been billed", which is a different question.
        #
        # ⚠ **`merged_ras` is deliberately NOT summed in.** `claimed_by_line()`
        # walks it as a *guard*, because a claim row appearing there would be a
        # quantity claimable twice — and `merged_ra.py` never writes one, so on
        # correct data that walk finds nothing. A merged document's MONEY is a
        # different matter: it is built from two RA bills that are already in
        # this sum, so adding its `claim_subtotal` would double-count every
        # merged claim. The legs are the source of truth; the merged document
        # re-presents them.
        "ra_claimed_value": claimed,

        # The denominator. Open schedules only — a superseded revision's value
        # was replaced rather than added to, so summing the whole chain would
        # inflate the approved side and make the claimed share look smaller
        # than it is.
        "boq_open_value": sum(float(boqs[bid].get("subtotal") or 0.0)
                              for bid in open_ids),

        # The activity feed's raw rows, NOT yet permission-filtered — that
        # happens at render, where the request context exists. See
        # `_activity_html()`.
        "activity": _activity_rows(boqs, bills),

        # Claimed against approved, per project. See `_project_progress()`.
        "proj_progress": _project_progress(boqs, bills, open_ids),
    }


def _project_progress(boqs: dict, bills: dict, open_ids: list) -> list:
    """
    `[{name, approved, claimed, pct, ...}]` — claimed against approved, per
    project, most recently active first.

    ⚠ **THERE WAS NOTHING IN `projectview.py` TO REUSE, and that was checked
    rather than assumed.** That module rolls up BOQs, proformas, tax invoices,
    purchase orders and labour for one project — and it **never reads
    `STORE["ra_bills"]` at all**, so no claimed-versus-approved figure exists
    anywhere in this application for this to duplicate. What IS reused is its
    rule for reading a total: `_total_of()` takes a document's own stored figure
    and never recomputes one from line items, because a second arithmetic path
    is how two copies of one number start to disagree. `subtotal` off the BOQ
    and `claim_subtotal` off the bill are those stored figures.

    Two different sets of BOQs are walked, and the asymmetry is the point:

    * **The approved side counts OPEN schedules only.** A superseded revision
      was replaced, not added to; summing the chain would inflate the
      denominator and make every revised project look under-claimed.
    * **The claimed side counts bills against EVERY revision.** A bill names the
      specific revision it was measured against (`boq_id`), and an old claim
      against RA2's schedule is still money claimed on that project after RA3
      supersedes it. Dropping those would under-count the numerator — the
      opposite error, in the same project.

    ⚠ **A BOQ with no project gets an "Unassigned" row rather than being
    dropped**, and on the live database that is not hypothetical: three of the
    eight schedules carry no `project_id` and one of them is worth ₹91.9 lakh.
    Omitting them would silently remove more approved value from this panel than
    every assigned project on the box put together. The row is labelled, not
    disguised as a project, and it links nowhere because there is no project
    page to link to.
    """
    # Which project each BOQ belongs to — over ALL revisions, for the claimed
    # side. `""` is the Unassigned bucket.
    project_of = {bid: str(b.get("project_id") or "") for bid, b in boqs.items()}
    projects   = STORE.get("projects") or {}

    rows = {}

    def _row(pid):
        if pid not in rows:
            rows[pid] = {"pid": pid,
                         "name": (str((projects.get(pid) or {}).get("name") or "").strip()
                                  or "Unassigned"),
                         "approved": 0.0, "claimed": 0.0, "last": ""}
        return rows[pid]

    # The approved side: open schedules only.
    for bid in open_ids:
        b = boqs[bid]
        r = _row(project_of.get(bid, ""))
        r["approved"] += float(b.get("subtotal") or 0.0)
        r["last"] = max(r["last"], str(b.get("date") or ""))

    # The claimed side: every revision, cancelled bills excluded — the money
    # counterpart of `claimed_by_line()`'s rule, exactly as `ra_claimed_value`
    # above. Tax-exclusive throughout (gap 31).
    for b in bills.values():
        bid = str(b.get("boq_id") or "")
        if bid not in project_of:
            # A bill whose schedule has been deleted. It is real money and is
            # not silently dropped — it lands in Unassigned, where the total
            # still reconciles against `ra_claimed_value`.
            r = _row("")
        else:
            r = _row(project_of[bid])
        r["last"] = max(r["last"], str(b.get("date") or ""))
        if _ra_is_cancelled(b):
            continue
        r["claimed"] += float(b.get("claim_subtotal") or 0.0)

    out = []
    for r in rows.values():
        approved = r["approved"]
        # ⚠ **`pct` is None rather than 0.0 when there is nothing approved.** A
        # project carrying claims against a schedule that has been deleted or
        # superseded away has claimed something against nothing, and "0%" would
        # state the opposite of what happened. `_progress_html()` draws no bar
        # for it. This is `projectview._total_of()`'s rule — None is not 0.0.
        r["pct"] = (r["claimed"] / approved * 100.0) if approved else None
        out.append(r)

    # Most recently active first, by the latest document date on the project.
    out.sort(key=lambda r: (r["last"], r["name"]), reverse=True)
    return out


def _activity_rows(boqs: dict, bills: dict) -> list:
    """
    BOQs and RA bills interleaved, newest first.

    ⚠ **Ordered by the document's own `date`, because there is no `created_at`
    on either record and inventing one is not this pass's to do.** Neither
    `boq.py` nor `ra.py` has ever written a creation timestamp; what both carry
    is the document date the operator typed. The sort key is `(date, ref)`
    descending, which is exactly the key `projectview.py` already uses to order
    the same two collections — so the feed agrees with the project page rather
    than inventing a second order. `ref` breaks the tie deterministically, since
    both series are zero-padded and sort lexically in mint order.

    ⚠ **A cancelled RA bill still appears.** The feed answers "what moved", and
    a withdrawn claim moved — it is excluded from the *money* totals, where its
    claim genuinely is nothing, but suppressing it here would make a bill vanish
    from the record of what happened. Its status is on the row.

    Returns rows as dicts rather than rendered HTML so that the permission
    filter can drop them before any of them reaches a page.
    """
    rows = []

    for bid, b in boqs.items():
        rows.append({
            "kind":     "BOQ",
            "endpoint": "boq.view_boq",
            "id":       bid,
            "ref":      str(b.get("ref") or "—"),
            "party":    str(b.get("project_name") or b.get("account_name") or ""),
            # Tax-exclusive, the field behind the sheet's "Total Basic Value".
            "amount":   float(b.get("subtotal") or 0.0),
            "date":     str(b.get("date") or ""),
            "note":     "",
        })

    for rid, r in bills.items():
        # `ra_no` is the client's own sequence and is what they will say on the
        # phone; the ref is ours. Show the ref and carry the leg, which is the
        # one thing that distinguishes two bills of the same date on one job.
        leg = str(r.get("leg") or "").strip()
        note = leg.capitalize() if leg else ""
        if _ra_is_cancelled(r):
            note = f"{note} · cancelled".strip(" ·")
        rows.append({
            "kind":     "RA",
            "endpoint": "ra.view_ra",
            "id":       rid,
            "ref":      str(r.get("ref") or "—"),
            "party":    str(r.get("project_name") or r.get("account_name") or ""),
            # Tax-exclusive. Gap 31 — never `grand_total`.
            "amount":   float(r.get("claim_subtotal") or 0.0),
            "date":     str(r.get("date") or ""),
            "note":     note,
        })

    rows.sort(key=lambda x: (x["date"], x["ref"]), reverse=True)
    return rows


def _metrics():
    """
    Everything the landing page draws, computed in one pass. Pure — no request
    state, no mutation beyond pipeline's own idempotent ensure_fields().
    """
    quotations = STORE["quotations"]
    today      = date.today()

    # The product catalogue reads `auth.HIDDEN_BLUEPRINTS` (11 September 2026):
    # while it is hidden nothing on this page counts a catalogue item, so the
    # `p_*` figures are nil rather than a tally of records nobody can open.
    # The card itself is already dropped by `_card()` through `can_reach()`;
    # this is the same toggle read at the figure rather than at the link.
    # Imported here, not at module level — auth.py is the bottom of the graph
    # and this module is imported by every other, but the function-body import
    # is the escape hatch `_card()` and `index()` already use.
    import auth
    products = {} if auth.blueprint_hidden("product") else STORE["products"]

    s = P.summarize(quotations)          # ensure_fields() runs inside

    # ── Funnel: open stages only, in the order pipeline.py declares them ──
    funnel = [{"stage": st,
               "count": s["by_stage"].get(st, {}).get("count", 0),
               "value": s["by_stage"].get(st, {}).get("value", 0.0)}
              for st in P.OPEN_STAGES]

    # Scale by money when there is money to scale by; a brand-new install has
    # counts but no totals, and a chart of six empty tracks says nothing.
    max_value = max((f["value"] for f in funnel), default=0.0)
    max_count = max((f["count"] for f in funnel), default=0)
    funnel_basis = "value" if max_value > 0 else "count"
    denom = max_value if funnel_basis == "value" else (max_count or 1)
    for f in funnel:
        f["pct"] = (f[funnel_basis] / denom * 100.0) if denom else 0.0

    # ── Monthly activity: quoted value split by outcome ───────────────────
    buckets = {ym: {"won": 0.0, "open": 0.0, "lost": 0.0} for ym in _month_sequence(today)}
    for q in quotations.values():
        d = _pdate(q.get("date"))
        if d is None or (d.year, d.month) not in buckets:
            continue
        key = "won" if P.is_won(q) else "lost" if P.is_lost(q) else "open"
        buckets[(d.year, d.month)][key] += float(q.get("grand_total") or 0.0)

    months = []
    for i, ((y, m), b) in enumerate(buckets.items()):
        total = b["won"] + b["open"] + b["lost"]
        # The year is printed under the first column and under every January,
        # so a six-month window that straddles a year-end says so on the axis.
        months.append({"label": date(y, m, 1).strftime("%b"),
                       "year": str(y)[2:], "show_year": i == 0 or m == 1,
                       "total": total, **b})
    month_max = max((mo["total"] for mo in months), default=0.0)
    for mo in months:
        mo["pct"] = {k: (mo[k] / month_max * 100.0) if month_max else 0.0
                     for k in ("won", "open", "lost")}
    month_totals = {k: sum(mo[k] for mo in months) for k in ("won", "open", "lost")}

    # ── Recent quotations, newest first (STORE preserves insertion order) ──
    recent = list(reversed(list(quotations.items())))[:RECENT_LIMIT]

    attention = _attention(quotations, today)

    return {
        "today":        today,
        "summary":      s,
        "q_count":      len(quotations),
        "po_expected":  s["by_stage"].get("PO Expected", {"count": 0, "value": 0.0}),
        "funnel":       funnel,
        "funnel_basis": funnel_basis,
        "months":       months,
        "month_max":    month_max,
        "month_totals": month_totals,
        "recent":       recent,
        "attention":    attention,
        "proj_total":   len(STORE.get("projects", {})),
        # The employee master (CC-2 C4). Active only, because that is the
        # accessor the module itself exposes and an inactive person is not
        # somebody the office is currently paying. ⚠ **No salary total on the
        # card.** The register is restricted to Owner, Director and HR, and a
        # payroll figure on the landing page would state to anybody holding
        # `dashboard.view` the one number B4 keeps from Sales, Purchase and
        # Accounts. ABOUT.md §7 gap 27 is the standing form of that risk; this
        # is one place not to walk into it.
        "emp_total":    sum(1 for e in STORE.get("employees", {}).values()
                            if e.get("active", True)),
        # Receipts — money actually received against an RA bill. A count and a
        # value; `amount` is always positive by construction (ABOUT.md §3), so
        # this is a straight sum and needs no status filter. Written off is
        # deliberately NOT added in: it is money given up, not money that
        # arrived, and A5's whole point is that the two are separate facts.
        "rcpt_total":   len(STORE.get("receipts", {})),
        "rcpt_value":   sum(float(r.get("amount") or 0.0)
                            for r in STORE.get("receipts", {}).values()),
        # Attendance (CC-2 C5). A count of markings and how many of them are
        # TODAY, because a muster is a daily thing and "is today done" is the
        # only question this card can usefully answer at a glance.
        #
        # ⚠ **No labour-cost figure here, and that is a rule rather than a
        # choice.** The site-wise cost is displayed inside `/attendance/` and
        # nowhere else: C6 is BLOCKED on whether attendance wages or the BOQ
        # installation rate is authoritative, and a cost total on the landing
        # page is the first half of the P&L that question governs. It would
        # also put payroll-derived money in front of every holder of
        # `dashboard.view`, which is the §7 gap 27 trap B4 keeps HR data out
        # of. Counts only.
        "att_total":    len(STORE.get("attendance", {})),
        "att_today":    sum(1 for a in STORE.get("attendance", {}).values()
                            if str(a.get("date") or "") == today.isoformat()),
        "ch_total":     len(STORE.get("charges", {})),
        "ch_spend":     sum(float(c.get("taxable_amount") or 0.0) + float(c.get("gst_amount") or 0.0)
                            for c in STORE.get("charges", {}).values()),
        "p_total":      len(products),
        "p_assembly":   sum(1 for p in products.values() if p.get("type") == "assembly"),
        "p_support":    sum(1 for p in products.values() if p.get("type") == "support"),
        "a_total":      len(STORE["addresses"]),
        "pi_total":     len(STORE["proformas"]),
        "pi_due":       sum(float(p.get("amount_due") or 0.0)
                            for p in STORE["proformas"].values()),
        "ti_total":     len(STORE["invoices"]),
        # Net of advances already adjusted — the figure that is genuinely still
        # owed, not the headline invoiced value.
        "ti_due":       sum(float(t.get("net_payable") or 0.0)
                            for t in STORE["invoices"].values()),
        # Buy side. Committed spend counts OPEN orders only: a received order is
        # a cost already landed, a cancelled one was never a cost at all.
        # Status strings are matched literally rather than importing
        # purchase.py — dashboard.py is imported BY every module and must stay
        # at the bottom of the import graph (§2).
        "po_total":     len(STORE["purchases"]),
        "po_committed": sum(float(p.get("grand_total") or 0.0)
                            for p in STORE["purchases"].values()
                            if (p.get("status") or "Draft")
                            not in ("Received", "Cancelled")),

        # BOQ — the head of the second sell-side chain. `subtotal` is the stored
        # basic value; the printed sheet recomputes it from the lines, but the
        # card only needs the headline. Read off the record rather than
        # importing boq.py, for the same reason as the PO statuses above.
        "spec_total": len(STORE["specs"]),
        "boq_total": len(STORE["boqs"]),
        "boq_value": sum(float(b.get("subtotal") or 0.0)
                         for b in STORE["boqs"].values()),
        "ra_total":  len(STORE.get("ra_bills", {})),
        "ra_value":  sum(float(r.get("net_payable") or 0.0)
                         for r in STORE.get("ra_bills", {}).values()),

        # ── The BOQ/RA visual cues ────────────────────────────────────────
        # Counts and money for the project-billing band. Every figure here is
        # TAX-EXCLUSIVE and the two sides are the same kind of number, which is
        # the whole point — see `_boq_ra()` for why `grand_total` appears
        # nowhere in it (ABOUT.md §7 gap 31).
        **_boq_ra(),

        # Draft POs — the BOQ chain's procurement document. A count only: its
        # rates are blank by design (ABOUT.md §5, `/po`), so there is no value
        # to report and a money figure here would be zero on every card.
        "dpo_total": len(STORE.get("purchase_orders", {})),

        # Delivery challans — the BOQ chain's goods-movement note. A count
        # only, and for a stronger reason than the draft PO's: a challan
        # carries no money at all, by design (ABOUT.md §5, `/dc`). Lines
        # dispatched would be the honest second figure, but it is a sum over
        # every challan's rows on a card that renders on every page load, and
        # a count answers "is anything moving" already.
        "dc_total": len(STORE.get("delivery_challans", {})),

        # C2 — measurement sheets. A count and how many COUNT — approved, in
        # `measurement.feeds_ceiling()`'s sense — because the second figure is
        # the one that matters: only a sheet that counts feeds an installation
        # claim, so "4 raised" with none counting is a project that cannot
        # bill installation and the card should say so. `approval.accepted()`
        # is that predicate; while the ladder is off every saved sheet counts
        # and the card says "raised" rather than "approved" (12 Sep 2026).
        # A sum of measured quantity would be meaningless across units.
        "ms_total": len(STORE.get("measurements", {})),
        "ms_approved": sum(
            1 for m in (STORE.get("measurements") or {}).values()
            if _ms_counts(m)),

        # Client register. **Issued bills only, less receipts** — a draft has
        # not been sent and a cancelled one was withdrawn, and the same two
        # exclusions hold on `/client/` itself. Status strings are matched
        # literally rather than importing `ra.py`, exactly as the PO statuses
        # above are: dashboard.py is imported BY every module and must stay at
        # the bottom of the import graph (§2). **If `ra.STATUSES` is ever
        # renamed, this is the third place to change.**
        "client_total": len({P.norm_name(b.get("account_name"))
                             for b in STORE["boqs"].values()
                             if str(b.get("account_name") or "").strip()}),
        "client_outstanding": (
            sum(float(r.get("grand_total") or 0.0)
                for r in STORE.get("ra_bills", {}).values()
                if str(r.get("status") or "issued").strip().lower() == "issued")
            - sum(float(r.get("amount") or 0.0)
                  for r in STORE.get("receipts", {}).values())),
    }


# =============================================================================
# RENDER FRAGMENTS
# =============================================================================
# Each returns a block of HTML. They are plain f-strings with no CSS or JS in
# them, so there are no braces to double — that is deliberate.

def _funnel_html(m) -> str:
    """
    Open pipeline by stage: an ordinal bar chart.

    Stage order carries meaning, so colour steps light→dark down the funnel from
    a single hue. Each row links through to the register filtered to that stage.
    The value is direct-labelled at the bar tip, so nothing is hover-only.
    """
    out = ""
    for i, f in enumerate(m["funnel"]):
        colour = B.CHART_NAVY[min(i, len(B.CHART_NAVY) - 1)]
        href   = url_for("quotation.list_quotations", stage=f["stage"])
        klass  = "fn-row" if f["count"] else "fn-row fn-empty"
        count  = f["count"]
        noun   = "deal" if count == 1 else "deals"
        # An empty stage draws no mark at all. .fn-bar carries a 2px min-width so
        # a real-but-tiny stage stays visible, and that floor would otherwise put
        # an identical tick on stages holding nothing.
        bar = (f'<div class="fn-bar" style="width:{f["pct"]:.1f}%;background:{colour}"></div>'
               if f["pct"] > 0 else "")
        out += f"""
          <a class="{klass}" href="{href}">
            <div class="fn-name">{f['stage']}</div>
            <div class="fn-track">{bar}</div>
            <div class="fn-val">{rupees(f['value'])}<span class="fn-n">{count} {noun}</span></div>
          </a>"""
    return out


def _months_html(m) -> str:
    """
    Quoted value by month, stacked by outcome.

    Won / open / lost *mean* good / neutral / bad, so they wear reserved status
    colours rather than a series palette — and the legend spells each one out in
    words with its period total, so colour never carries the meaning alone and
    no figure is reachable only by hovering.
    """
    cols = ""
    for mo in m["months"]:
        segs = ""
        for key, cls in (("won", "s-won"), ("open", "s-open"), ("lost", "s-lost")):
            if mo[key] <= 0:
                continue
            # Heights are absolute px against PLOT_H so the 2px surface gaps
            # cannot compress a segment and misstate its value. A non-zero
            # segment gets a 3px floor rather than rounding away to nothing.
            h = max(3, round(mo["pct"][key] / 100.0 * PLOT_H))
            segs += f'<div class="mc-seg {cls}" style="height:{h}px"></div>'

        cap  = rupees(mo["total"]) if mo["total"] else "&nbsp;"
        year = f"<span>{mo['year']}</span>" if mo["show_year"] else ""
        tip  = "".join(
            f'<div class="tp-row"><span>{lbl}</span><b>{rupees(mo[k])}</b></div>'
            for k, lbl in (("won", "Won"), ("open", "Open"), ("lost", "Lost"))
            if mo[k] > 0
        ) or '<div class="tp-row"><span>Nothing quoted</span></div>'

        cols += f"""
          <div class="mc-col" tabindex="0">
            <div class="mc-tip">
              <div class="tp-row"><span>{mo['label']} {mo['year']}</span><b>{rupees(mo['total'])}</b></div>
              {tip}
            </div>
            <div class="mc-cap">{cap}</div>
            <div class="mc-stack">{segs}</div>
            <div class="mc-base"></div>
            <div class="mc-x">{mo['label']}{year}</div>
          </div>"""

    t = m["month_totals"]
    legend = "".join(
        f'<span class="lg-item"><i class="lg-dot" style="background:{colour}"></i>'
        f'{label} <b>{rupees(t[key])}</b></span>'
        for key, label, colour in (("won",  "Won",  B.CHART_WON),
                                   ("open", "Open", B.CHART_OPEN),
                                   ("lost", "Lost", B.CHART_LOST))
    )
    return f'<div class="mc-plot">{cols}</div><div class="lg">{legend}</div>'


# The status chip each attention reason wears: a tone, an icon and a WORD.
# Until 14 September 2026 the four reasons were told apart by the colour of
# their row icon alone, and amber against red is ~ΔE 2.2 under deuteranopia —
# effectively one colour. The word is what carries the meaning now; the two
# reasons that used to share amber (`stale`, `nopo`) and the one that was
# orange (`await`) all read as WARNING, because none of them is a breach the
# way an overdue closing is, and each says which warning it is.
ATTENTION_CHIPS = {
    "overdue": ("crit", "crit", "Overdue"),
    "await":   ("warn", "warn", "PO awaited"),
    "stale":   ("warn", "warn", "Gone quiet"),
    "nopo":    ("warn", "warn", "No PO on file"),
}


def status_chip(tone: str, icon: str, word: str) -> str:
    """One status chip — tone class, its icon, and the word. Never colour alone."""
    return f'<span class="chip chip-{tone}">{ICONS[icon]}{word}</span>'


def _attention_html(m) -> str:
    """The work queue. Empty is a good outcome, so say so rather than showing nothing."""
    rows = m["attention"]
    if not rows:
        return ('<div class="none">Nothing needs chasing — no overdue closings, '
                'no unanswered POs, nothing gone quiet.</div>')

    out = ""
    for _prio, tone, icon, qid, q, value, why in rows[:ATTENTION_LIMIT]:
        href = url_for("quotation.view_quotation", id=qid)
        chip = status_chip(*ATTENTION_CHIPS[icon])
        out += f"""
          <a class="attn-row t-{tone}" href="{href}">
            <div class="attn-ico">{ICONS[icon]}</div>
            <div>
              <div class="attn-ref">{P.esc(q.get('ref') or '—')}
                <span class="attn-acct">· {P.esc(q.get('account_name') or 'Unnamed account')}</span>{chip}</div>
              <div class="attn-why">{why}</div>
            </div>
            <div class="attn-val">{rupees(value)}</div>
          </a>"""

    extra = len(rows) - ATTENTION_LIMIT
    if extra > 0:
        href = url_for("quotation.list_quotations", view="open")
        out += (f'<div class="attn-more">+ {extra} more in the register — '
                f'<a href="{href}">open all live deals</a></div>')
    return out


def _recent_html(m) -> str:
    """Last few quotations raised, newest first."""
    if not m["recent"]:
        return '<div class="none">No quotations raised yet.</div>'

    out = ""
    for qid, q in m["recent"]:
        href = url_for("quotation.view_quotation", id=qid)
        d    = _pdate(q.get("date"))
        when = d.strftime("%d %b %Y") if d else "—"
        out += f"""
          <a class="rq-row" href="{href}">
            <div>
              <div class="rq-ref">{P.esc(q.get('ref') or '—')}</div>
              <div class="rq-meta">
                <span class="rq-acct">{P.esc(q.get('account_name') or 'Unnamed account')}</span>
                {P.stage_badge(P.stage_of(q))}
              </div>
            </div>
            <div class="rq-right">
              <div class="rq-val">{rupees(q.get('grand_total'))}</div>
              <div class="rq-date">{when}</div>
            </div>
          </a>"""
    return out


def _ms_card_sub(m) -> str:
    """
    The measurement card's second figure. With the ladder on: how many are
    approved. With it off there is nothing to approve — every saved sheet
    counts and saying "N approved" would name a rung nobody can climb — so
    the card counts the sheets that are not rejected instead.
    """
    if not m["ms_total"]:
        return " · what was found on site, and the ceiling for installation claims"
    import approval as _AP
    if _AP.ladder_on():
        return f" · {m['ms_approved']} approved"
    return f" · {m['ms_approved']} counting toward installation claims"


def _chain_tiles_html(m) -> str:
    """
    The project-billing tile row: open schedules and bills awaiting approval.

    ⚠ **Each tile is drawn only when `auth.can_reach()` says this user could
    open the register it counts**, which is the rule `_card()` already applies
    to the module launcher. That is *not* a fix for ABOUT.md §7 gap 27 and must
    not be recorded as one — gap 27 is about aggregate figures summarising
    records the reader may not open ONE BY ONE, and these two tiles still do
    exactly that for anybody holding `boq.view`. What this gating buys is
    narrower and worth having anyway: a role that cannot reach the BOQ register
    at all is not shown a count of it.
    """
    import auth

    tiles = []
    if auth.can_reach("boq.list_boqs"):
        revised = m["boq_revised_count"]
        # A revised schedule is not a second schedule. Say how many are out of
        # the count when there are any, and say nothing when there are none —
        # "0 superseded" is noise on the overwhelming majority of installs.
        sub = (f"{revised} superseded by a revision" if revised
               else "live schedules, none revised")
        tiles.append(f"""
            <div class="panel kpi k-rate">
              <div class="k-lbl">Open BOQs</div>
              <div class="k-val">{m['boq_open_count']}</div>
              <div class="k-sub">{sub}</div>
            </div>""")

    # ⚠ No approval tile while the ladder is OFF (12 September 2026): there is
    #   no queue for it to count, and a tile reading "0 pending approval" would
    #   describe a rung nobody can climb. The count itself is already 0 then —
    #   `_ra_awaits_approval()` reads the switch — so this is the tile's
    #   absence rather than its figure.
    import approval as _AP
    if auth.can_reach("ra.list_ras") and _AP.ladder_on():
        pending = m["ra_pending_count"]
        # Empty is a good outcome and is said so, exactly as the work queue
        # says it — a bare "0" reads as a figure that failed to load.
        sub = ("waiting on an approver" if pending
               else "nothing waiting on an approver")
        tiles.append(f"""
            <div class="panel kpi k-hot">
              <div class="k-lbl">RAs pending approval</div>
              <div class="k-val">{pending}</div>
              <div class="k-sub">{sub}</div>
            </div>""")

    # ── Claimed value, and never as a bare number ────────────────────────
    #
    # ⚠ **The denominator is on the face of the tile.** "₹10.3 L claimed" says
    # almost nothing on its own — against ₹2.1 Cr of live schedules it is an
    # early-stage portfolio, against ₹11 L it is one nearly finished. Both
    # figures are tax-exclusive and are therefore the same kind of number, which
    # is the only reason they may be shown as a share at all (gap 31).
    #
    # It needs BOTH registers: the numerator is RA data and the denominator is
    # BOQ data, so a user holding only one of the two permissions would be shown
    # a ratio half of which they cannot see. That is a stronger reason than
    # tidiness — it is the one place on this band where hiding a figure is about
    # what the reader is entitled to rather than about what would look empty.
    if auth.can_reach("boq.list_boqs") and auth.can_reach("ra.list_ras"):
        approved = m["boq_open_value"]
        claimed  = m["ra_claimed_value"]
        pct      = (claimed / approved * 100.0) if approved else 0.0
        if approved:
            sub = (f"of {rupees(approved)} approved &middot; "
                   f"{_pct_label(pct)} of open schedules")
            meter = f'<div class="meter"><i style="width:{min(pct, 100.0):.1f}%"></i></div>'
        else:
            # No open schedule to claim against. A percentage of nothing is not
            # 0% and must not be drawn as one.
            sub = "no open schedule to claim against"
            meter = ""
        tiles.append(f"""
            <div class="panel kpi k-won">
              <div class="k-lbl">Claimed to date</div>
              <div class="k-val">{rupees(claimed)}</div>
              <div class="k-sub">{sub}</div>
              {meter}
            </div>""")

    if not tiles:
        return ""
    return f"""
          <div class="kpis-chain">{"".join(tiles)}
          </div>"""


def _activity_html(m) -> str:
    """
    What moved on the BOQ/RA chain — newest first, and PERMISSION-FILTERED.

    ⚠ **THIS IS THE ONE PANEL ON THIS PAGE THAT FILTERS PER RECORD, AND THE
    DEPARTURE IS DELIBERATE.** ABOUT.md §7 gap 27 is the standing position that
    dashboard *figures* are not permission-filtered — counts and totals still
    summarise records the reader may not open one by one, and the pass that
    closed gaps 28 and 29 was explicitly instructed to leave that open. This
    panel does not extend that precedent, because it is not an aggregate: it
    names a document, its client or project, and its value. **Naming a specific
    document and its amount to somebody who cannot open it is a materially
    bigger disclosure than telling them how many exist**, and it is the exact
    thing an aggregate count protects against. So the feed is filtered and the
    tiles above it are not, and that inconsistency is the intended outcome
    rather than an oversight.

    ⚠ **THE FILTER IS ENDPOINT-LEVEL, BECAUSE THERE IS NO PER-RECORD CHECK IN
    THIS APPLICATION TO REUSE.** ABOUT.md §7 gap 24 is explicit: `ROUTE_PERMISSIONS`
    maps an endpoint to a permission, so it answers *"may this user view RA
    bills"* and **cannot** answer *"may this user view THIS RA bill"*. There is
    no object-level gate on `/boq/view/<id>` or `/ra/view/<id>` — a holder of
    `ra.view` may open every bill in the store. `auth.can_reach()` is therefore
    not an approximation of the real gate here, it **is** the real gate, and
    filtering on it delivers exactly the property this panel needs: a row is
    shown only when its own link would open. **If object-level access is ever
    built, this function is one of the places that must learn about it** — and
    until then it must not be described as doing more than it does.

    The two kinds are filtered independently: a role holding `boq.view` and not
    `ra.view` gets a feed of schedules with the claims removed, rather than the
    whole panel.
    """
    import auth

    rows = [r for r in m["activity"] if auth.can_reach(r["endpoint"])]
    if not rows:
        # Silent when this user reaches neither register — the caller drops the
        # panel entirely rather than showing an empty one.
        if not (auth.can_reach("boq.view_boq") or auth.can_reach("ra.view_ra")):
            return ""
        return '<div class="none">Nothing raised on the BOQ chain yet.</div>'

    out = ""
    for r in rows[:ACTIVITY_LIMIT]:
        href = url_for(r["endpoint"], id=r["id"])
        d    = _pdate(r["date"])
        when = d.strftime("%d %b %Y") if d else "—"
        # `party` and `ref` are operator-typed and reach HTML here, so both are
        # escaped at the interpolation site (ABOUT.md §9). `kind`, `when` and
        # the amount are ours and are not user text.
        party = P.esc(r["party"] or "Unnamed")
        note  = f' · {P.esc(r["note"])}' if r["note"] else ""
        out += f"""
          <a class="rq-row" href="{href}">
            <div>
              <div class="rq-ref">{P.esc(r['ref'])}</div>
              <div class="rq-meta">
                <span class="act-kind ak-{r['kind'].lower()}">{r['kind']}</span>
                <span class="rq-acct">{party}{note}</span>
              </div>
            </div>
            <div class="rq-right">
              <div class="rq-val">{rupees(r['amount'])}</div>
              <div class="rq-date">{when}</div>
            </div>
          </a>"""

    extra = len(rows) - ACTIVITY_LIMIT
    if extra > 0:
        # The "+N more" link goes to whichever register this user can actually
        # open, and is omitted rather than dangling when neither is reachable.
        #
        # ⚠ **Written as literal `url_for()` branches rather than
        # `url_for(target)`.** A computed endpoint is invisible to the AST walk
        # in `tests/test_page_reachability.py`, so the branchier form is the one
        # that actually contributes edges to the link graph — see the tripwire
        # `test_the_link_graph_is_built_from_literal_endpoints_almost_everywhere`.
        tail = ""
        if auth.can_reach("boq.list_boqs"):
            tail = f' — <a href="{url_for("boq.list_boqs")}">open the BOQ register</a>'
        elif auth.can_reach("ra.list_ras"):
            tail = f' — <a href="{url_for("ra.list_ras")}">open the RA register</a>'
        out += f'<div class="attn-more">+ {extra} more{tail}</div>'
    return out


def _progress_html(m) -> str:
    """
    Claimed against approved, per project — a bar each, most recent first.

    ⚠ **Gated on BOTH registers, for `_chain_tiles_html()`'s reason.** Every row
    is a ratio of BOQ value to RA value, so a user holding one permission and
    not the other would be reading a bar half of which they cannot see.

    ⚠ **This panel names projects and their values, so the same reasoning as the
    activity feed applies** — but the gate available is coarser. A project is not
    a BOQ or an RA bill, `project.view` is its own permission, and there is no
    per-record check on any of the three (ABOUT.md §7 gap 24). Requiring all
    three permissions is the honest reading of "could this user open the things
    this row is built from".
    """
    import auth

    if not (auth.can_reach("boq.list_boqs") and auth.can_reach("ra.list_ras")):
        return ""

    rows = m["proj_progress"]
    if not rows:
        return '<div class="none">No schedules on any project yet.</div>'

    can_open = auth.can_reach("projectview.view_project")

    out = ""
    for r in rows[:PROGRESS_LIMIT]:
        pct = r["pct"]
        # A project with claims and no live schedule has claimed against
        # nothing. It gets no bar and says so — "0%" would state the opposite.
        if pct is None:
            bar  = ""
            note = "no open schedule"
        else:
            # The fill is clamped at 100% so an over-claim cannot run the bar
            # off its track, and the FIGURE beside it is not clamped — an
            # over-claim must still be readable as one.
            bar  = (f'<div class="meter"><i style="width:{min(pct, 100.0):.1f}%">'
                    f'</i></div>')
            note = f"{_pct_label(pct)} claimed"

        # `name` is operator-typed and reaches HTML here (ABOUT.md §9).
        label = P.esc(r["name"])
        if r["pid"] and can_open:
            href  = url_for("projectview.view_project", id=r["pid"])
            label = f'<a href="{href}">{label}</a>'

        out += f"""
          <div class="pp-row">
            <div class="pp-hd">
              <span class="pp-name">{label}</span>
              <span class="pp-fig">{rupees(r['claimed'])} of {rupees(r['approved'])}</span>
            </div>
            {bar}
            <div class="pp-note">{note}</div>
          </div>"""

    extra = len(rows) - PROGRESS_LIMIT
    if extra > 0 and auth.can_reach("project.list_projects"):
        href = url_for("project.list_projects")
        out += (f'<div class="attn-more">+ {extra} more — '
                f'<a href="{href}">all projects</a></div>')
    elif extra > 0:
        out += f'<div class="attn-more">+ {extra} more</div>'
    return out


def _boq_cta_html(m) -> str:
    """
    The BOQ call-to-action, or "" for a user who could not open `/boq/create`.

    Gated on the create endpoint, not the register: a role holding `boq.view`
    alone would otherwise be handed the biggest button on the page and refused
    the moment they pressed it. The count line and the register link each ask
    for the register separately, the way `_chain_tiles_html()` does.
    """
    import auth

    if not auth.can_reach("boq.create_boq"):
        return ""

    stats = link = ""
    if auth.can_reach("boq.list_boqs"):
        total = m["boq_total"]
        if total:
            value = (f" &middot; {rupees(m['boq_value'])} basic value"
                     if m["boq_value"] else "")
            stats = (f'<div class="bc-stats">{m["boq_open_count"]} open &middot; '
                     f'{total} priced{value}</div>')
        link = (f'<a href="{url_for("boq.list_boqs")}" class="bc-link">'
                f'Open the BOQ register &rarr;</a>')

    return f"""
        <section class="boq-cta">
          <div class="bc-icon">{ICONS['boq']}</div>
          <div class="bc-text">
            <div class="bc-eyebrow">Start here</div>
            <h2>Create a Bill of Quantities</h2>
            <p>Price a project schedule from the spec library. Measurement
               sheets, RA bills and delivery challans are all raised against it.</p>
            {stats}
          </div>
          <div class="bc-act">
            <a href="{url_for('boq.create_boq')}" class="btn bc-btn">
              {ICONS['plus']} New BOQ</a>
            {link}
          </div>
        </section>"""


def _chain_html(m) -> str:
    """
    The whole project-billing band, or "" when this user reaches none of it.

    A zone whose every panel is hidden goes with its last panel, for the reason
    `_module_group()` drops an empty heading: a heading over nothing tells a
    Sales Manager there is a section they are missing rather than not mentioning
    one.
    """
    import auth

    tiles    = _chain_tiles_html(m)
    activity = _activity_html(m)
    progress = _progress_html(m)
    if not (tiles or activity or progress):
        return ""

    panels = ""
    if activity or progress:
        # The register link in the header follows the same rule as the "+N
        # more" tail: it points at a register this user can open, or is absent,
        # and it names its endpoint as a literal for the reachability walk.
        #
        # ⚠ **The label says WHICH register, and that is not cosmetic.** It read
        # "Register" until `tests/test_nav_visibility.py` caught the collision:
        # that file asserts an Operation Head is shown no `>Register<` anywhere,
        # because until now the only register linked from this page was the
        # quotation one. There are two on this page now, and an unqualified
        # "Register" beside a BOQ panel is ambiguous to a reader as well as to
        # that test.
        link = ""
        if auth.can_reach("boq.list_boqs"):
            link = f'<a href="{url_for("boq.list_boqs")}">BOQ register</a>'
        elif auth.can_reach("ra.list_ras"):
            link = f'<a href="{url_for("ra.list_ras")}">RA register</a>'

        # Each panel goes with its own content, so a role reaching one and not
        # the other gets one panel rather than an empty half — `_module_group()`
        # drops an empty heading for the same reason.
        blocks = ""
        if activity:
            blocks += f"""
          <div class="panel">
            <div class="panel-hd">
              <h2>Recent BOQ &amp; RA activity</h2>
              {link}
            </div>
            <div class="panel-bd">{activity}</div>
          </div>"""
        if progress:
            proj_link = (f'<a href="{url_for("project.list_projects")}">All projects</a>'
                         if auth.can_reach("project.list_projects") else "")
            blocks += f"""
          <div class="panel">
            <div class="panel-hd">
              <h2>Claimed against approved</h2>
              {proj_link}
            </div>
            <div class="panel-bd">{progress}</div>
          </div>"""
        panels = f"""
        <section class="cols-eq">{blocks}
        </section>"""

    return f"""
        <div class="zone">
          <div class="zone-hd">
            <h2>Projects &amp; site billing</h2>
            <span class="zn-sub">basic value, taxes extra</span>
          </div>
{tiles}
{panels}
        </div>"""


def _insight_html(m) -> str:
    """
    The analytical half of the page. Suppressed entirely on an empty store —
    six charts of zero teach nothing and make a working app look broken.
    """
    if not m["q_count"]:
        create_url = url_for("quotation.create_quotation")
        return f"""
        <section class="panel">
          <div class="empty">
            <h3>No quotations yet</h3>
            <p>Raise the first one and this page fills in — pipeline value by
               stage, what is overdue or awaiting a PO, and month-on-month
               activity.</p>
            <a href="{create_url}" class="btn">{ICONS['plus']} Raise a quotation</a>
          </div>
        </section>"""

    s        = m["summary"]
    won      = s["won"]
    lost     = s["lost"]
    op       = m["po_expected"]
    rate     = s["win_rate"]
    decided  = won["count"] + lost["count"]
    open_ct  = s["open"]["count"]

    rate_val = f"{rate}%" if rate is not None else "—"
    rate_sub = (f"{won['count']} won of {decided} decided" if decided
                else "No deal has closed yet")
    meter    = f'<div class="meter"><i style="width:{rate or 0}%"></i></div>' if decided else ""

    # PO value is what the customer actually committed; it is not always what we
    # quoted, and that gap is the number worth surfacing.
    po_recorded = won["po_value"]
    won_sub = (f"POs on file {rupees(po_recorded)}" if po_recorded
               else "No PO value recorded yet")

    basis = ("scaled by value" if m["funnel_basis"] == "value"
             else "scaled by deal count — nothing valued yet")

    reg_url  = url_for("quotation.list_quotations")
    open_url = url_for("quotation.list_quotations", view="open")

    return f"""
        <section class="band">
          <div class="panel hero-fig">
            <div class="hf-lbl">Open pipeline</div>
            <div class="hf-val">{rupees(s['open']['value'])}</div>
            <div class="hf-sub">across <b>{open_ct}</b>
              live {'deal' if open_ct == 1 else 'deals'} ·
              <b>{s['total']['count']}</b> quotations all-time</div>
          </div>

          <div class="kpis">
            <div class="panel kpi k-hot">
              <div class="k-lbl">PO expected</div>
              <div class="k-val">{rupees(op['value'])}</div>
              <div class="k-sub">{op['count']} awaiting the customer's PO</div>
            </div>
            <div class="panel kpi k-won">
              <div class="k-lbl">Won</div>
              <div class="k-val">{rupees(won['value'])}</div>
              <div class="k-sub">{won_sub}</div>
            </div>
            <div class="panel kpi k-rate">
              <div class="k-lbl">Win rate</div>
              <div class="k-val">{rate_val}</div>
              <div class="k-sub">{rate_sub}</div>
              {meter}
            </div>
          </div>
        </section>

        <div class="zone">
          <div class="zone-hd">
            <h2>Where the pipeline stands</h2>
            <span class="zn-sub">live deals only</span>
          </div>
        <section class="cols">
          <div class="panel">
            <div class="panel-hd">
              <h2>Open pipeline by stage</h2>
              <span class="pn-sub">{basis}</span>
            </div>
            <div class="panel-bd bd-funnel">{_funnel_html(m)}</div>
          </div>

          <div class="panel">
            <div class="panel-hd">
              <h2>Needs attention</h2>
              <a href="{open_url}">All live deals</a>
            </div>
            <div class="panel-bd">{_attention_html(m)}</div>
          </div>
        </section>
        </div>

        <div class="zone">
          <div class="zone-hd">
            <h2>What moved</h2>
            <span class="zn-sub">recent activity</span>
          </div>
        <section class="cols-eq">
          <div class="panel">
            <div class="panel-hd">
              <h2>Quoted value by month</h2>
              <span class="pn-sub">last {TREND_MONTHS} months</span>
              <!-- The register is this chart's table view: the per-month split
                   is on hover, but every underlying row is one click away. -->
              <a href="{reg_url}">Table view</a>
            </div>
            <div class="panel-bd">{_months_html(m)}</div>
          </div>

          <div class="panel">
            <div class="panel-hd">
              <h2>Recent quotations</h2>
              <a href="{reg_url}">Register</a>
            </div>
            <div class="panel-bd">{_recent_html(m)}</div>
          </div>
        </section>
        </div>"""


# ── Rendering — why this view does not call render_template_string() ──────────
#
# The page is a fully interpolated HTML string by the time the view returns it.
# Nothing is passed as Jinja context — ABOUT.md §1 says so explicitly — so
# handing the finished string back to Jinja parses it a second time for no
# benefit and one large cost: any `{{ … }}` or `{% … %}` that reached the output
# from USER INPUT is then executed as a template.
#
# That is not theoretical. `pipeline.esc()` escapes `< > & " '` and deliberately
# not braces, so a quotation whose `account_name` reads `{{ config }}` renders
# the Flask config — including SECRET_KEY — in the "Needs attention" and "Recent
# quotations" panels, and one reading `{% for x in y %}` raises a
# TemplateSyntaxError. This is the landing page and the 404/500 handlers both
# redirect here (ABOUT.md §7.6), so a 500 here is a loop with no way out of it.
#
# Returning the string directly is what Flask does with any `str` a view
# returns. It removes the second parse, and with it the injection. HTML
# escaping still does its own job — this changes nothing about XSS.
#
# ⚠ Still open in `quotation.py` and `product.py`, and this one-liner does not
#   reach either: quotation.py builds its pages with `.format()` and has
#   attribute, <script> and option-text sinks besides; product.py does not
#   escape at all. Each wants its own pass — ABOUT.md §7.9d.

def _page(html: str) -> str:
    """A finished page. See the note above — deliberately not Jinja-rendered."""
    return html


# ── The module zones, rendered from chrome.REGISTERS ─────────────────────────
#
# The strip used to be fifteen cards written out longhand in `index()`, in
# four hand-written groups — and a second hand-written list of the same
# registers drew the nav. Both now render from **one** table, `chrome.REGISTERS`
# (14 September 2026), so a register added there appears on the rail and in
# its zone in the same commit, and `tests/test_sidebar.py` asserts the two
# name the same set for the same user.
#
# **Visibility is derived from `auth.ROUTE_PERMISSIONS`** through
# `auth.can_reach()` — the same dict `_gate()` answers from. Nothing here holds
# a permission id, because a second list of "what to show" drifts from the list
# of "what to allow", and every drift is either a dead link or a hidden route
# that is quietly open. **The gate still runs on every request regardless of
# what was drawn.**
#
# What this module adds to the registry's figure is the CAPTION under it — the
# money and the second count that only `_metrics()` knows — keyed by the
# register's key. A register with no caption here gets its generic line, so a
# new entry cannot break the page; it can only be terser than it should be.


def _card_caption(reg, m) -> str:
    """The 12px line pinned to the foot of a zone card, from the metrics dict."""
    k = reg.key
    if k == "quotation":
        return f"{m['summary']['open']['count']} still live"
    if k == "proforma":
        return (f"{rupees(m['pi_due'])} requested" if m["pi_due"]
                else "raised from a quotation")
    if k == "invoice":
        # Net of advances already adjusted — the figure genuinely still owed.
        return (f"{rupees(m['ti_due'])} outstanding" if m["ti_due"]
                else "raised from a proforma")
    if k == "project":
        return "groups BOQs, purchase orders and site labour"
    if k == "boq":
        return (f"{rupees(m['boq_value'])} basic value" if m["boq_value"]
                else "project schedules, billed by RA")
    if k == "ra":
        return (f"{rupees(m['ra_value'])} claimed" if m["ra_value"]
                else "interim claims against BOQs")
    if k == "receipt":
        return (f"{rupees(m['rcpt_value'])} received" if m["rcpt_value"]
                else "payments against RA bills")
    if k == "challan":
        return "goods leaving the yard against a schedule, no rates and no tax"
    if k == "measurement":
        return _ms_card_sub(m).lstrip(" ·")
    if k == "purchase":
        # Open orders only — see `_metrics()`.
        return (f"{rupees(m['po_committed'])} committed" if m["po_committed"]
                else "what we buy, not what we sell")
    if k == "po_draft":
        return "sent to a supplier to be priced, no rates and no GST"
    if k == "charge":
        return f"{rupees(m['ch_spend'])} spent"
    if k == "attendance":
        # ⚠ Counts only, never a labour cost — see `_metrics()` and C6.
        return f"{m['att_today']} marked today"
    if k == "product":
        std = m["p_total"] - m["p_assembly"] - m["p_support"]
        return f"{m['p_assembly']} assemblies · {std} standalone"
    if k == "spec":
        return "what a BOQ line is written from"
    if k == "client":
        return (f"{rupees(m['client_outstanding'])} outstanding" if m["client_outstanding"]
                else "schedules grouped by billed-to party")
    if k == "employee":
        # ⚠ No salary total — B4 keeps that figure from Sales, Purchase and
        #   Accounts, and the landing page reaches all of them.
        return "details and day rate"
    if k == "address":
        return "feeds the Bill To and Ship To pickers"
    if k == "news":
        return "pump, steel and fire-safety prices &#8599;"
    if k == "users":
        import auth
        n = len(auth.roles())
        return f"{n} role{'' if n == 1 else 's'} · who may do what"
    return _group_caption(reg)


def _group_caption(reg) -> str:
    """The generic caption: the register's group, for an entry with no caption above."""
    return chrome.GROUP_OF[reg.group].sub


def _zone_card(reg, m) -> str:
    """One zone card, or "" when this user could not open the register."""
    import auth

    if not auth.can_reach(reg.endpoint):
        return ""
    tab = ' target="_blank" rel="noopener"' if reg.new_tab else ""
    n = chrome.summary_count(reg)
    fig = ("" if n is None else
           f'<div class="mc-fig"><b>{n}</b><span class="mc-unit">{reg.unit}</span></div>')
    return f"""
          <a href="{url_for(reg.endpoint)}"{tab} class="card">
            <div class="card-icon">{ICONS[reg.icon]}</div>
            <div class="card-body">
              <div class="card-title">{reg.name}</div>
              {fig}
              <div class="card-desc">{_card_caption(reg, m)}</div>
            </div>
            <span class="mc-chev">{ICONS['chevron']}</span>
          </a>"""


def _rollup(group, m) -> str:
    """
    The zone's roll-up pill — two live figures, never hardcoded, each drawn
    only when this user could open the register it is summed from. Both halves
    hidden means no pill at all rather than an empty one.
    """
    import auth

    parts = []
    if group.key == "sell":
        if auth.can_reach("quotation.list_quotations"):
            parts.append(f"{rupees(m['summary']['open']['value'])} live pipeline")
        if auth.can_reach("invoice.list_invoices"):
            parts.append(f"{rupees(m['ti_due'])} outstanding")
    elif group.key == "proj":
        # Tax-exclusive on both sides, the same kind of number — gap 31's rule.
        if auth.can_reach("boq.list_boqs"):
            parts.append(f"{rupees(m['boq_open_value'])} approved")
        if auth.can_reach("ra.list_ras"):
            parts.append(f"{rupees(m['ra_claimed_value'])} claimed")
    elif group.key == "buy":
        if auth.can_reach("purchase.list_purchases"):
            parts.append(f"{rupees(m['po_committed'])} committed")
        if auth.can_reach("charge.list_charges"):
            parts.append(f"{rupees(m['ch_spend'])} spent")
    elif group.key == "lib":
        if auth.can_reach("client.list_clients"):
            n = m["client_total"]
            parts.append(f"{n} client{'' if n == 1 else 's'}")
        if auth.can_reach("spec.list_specs"):
            parts.append(f"{m['spec_total']} clauses")
    if not parts:
        return ""
    return f'<span class="mg-pill">{" &middot; ".join(parts)}</span>'


def _zone(group, m) -> str:
    """
    One group's zone, or "" when every register in it is hidden from this
    user. A heading with nothing under it is worse than no heading: it tells a
    Sales Manager there is a "Buy side" they are missing rather than simply
    not mentioning one. So the zone goes when its last card does.
    """
    cards = [_zone_card(r, m) for r in chrome.registers_in(group.key)]
    live = [c for c in cards if c]
    if not live:
        return ""
    return f"""
        <section class="mod-group g-{group.key}">
          <div class="mg-hd">
            <span class="mg-dot"></span>
            <h3>{group.title}</h3>
            <span class="mg-note">{group.sub}</span>
            <span class="mg-rule"></span>
            {_rollup(group, m)}
          </div>
          <div class="mods">
{"".join(live)}

          </div>
        </section>"""


def _zones(m) -> list:
    """Every zone this user gets, in `chrome.GROUPS` order; empty ones are ""."""
    return [_zone(g, m) for g in chrome.GROUPS]



def too_large_page() -> str:
    """
    The body of the 413 handler. Wired in app.py, which only ever wires.

    A 413 is different from the 404 and 500 handlers next to it, and must not
    copy them. Those redirect to the dashboard, which is right for a demo: a
    mistyped URL is nobody's work. A 413 is somebody's work — a form they spent
    an afternoon on — and a silent redirect to the landing page would look
    exactly like the app throwing it away without comment.

    It cannot give the work back. Werkzeug rejects the body *before* the form is
    parsed, so `request.form` is empty by construction and there is nothing left
    to re-render; this is precisely why the 600-line cap in `boq._clean_lines()`
    is the primary defence and this is only the backstop. What the page can do
    is say what happened, say plainly that the input is gone, and say what to do
    differently — and keep the browser's Back button useful, which is the one
    thing that may still hold the user's data.

    Status stays 413. Redirecting with a 302 would tell the browser, the logs
    and any future API client that the request succeeded.

    `boq` is imported **inside the function**, the same escape hatch `index()`
    uses for the seeders and for the same reason: boq.py imports this module, so
    a top-level import would be a cycle. The alternative was hardcoding 600 in a
    second place, where it would drift from the constant that enforces it.
    """
    from boq import MAX_LINES as BOQ_MAX_LINES

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Too large to accept")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        <div class="alert alert-error">
          &#10007; That form was too large for the server to accept.
        </div>
        <div class="card" style="margin-top:1.25rem">
          <div class="card-body">
            <div class="card-title">The page was not saved</div>
            <p class="card-desc">
              The request was rejected before the server read it, so what you
              typed could not be recovered here.
              <b>Use your browser's Back button</b> — the form is usually still
              filled in behind this page, and you can save it in smaller pieces
              from there.
            </p>
            <p class="card-desc" style="margin-top:.75rem">
              A bill of quantities is limited to {BOQ_MAX_LINES} lines. A
              schedule larger than that belongs in a second BOQ — the register
              lists them side by side.
            </p>
          </div>
        </div>
        <p style="margin-top:1.5rem">
          <a href="{url_for('dashboard.index')}" class="btn btn-ghost">Back to dashboard</a>
        </p>
      </main>
    </body>
    </html>
    """


# ── Routes ────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/")
def index():
    """
    Operations dashboard.

    Reads the store, computes the pipeline picture, and renders it. The module
    launcher is the *last* section on the page — a landing page whose only
    content is four buttons tells you nothing you did not already know.

    The demo seeders are imported here rather than at module level: product.py
    and address.py both import this module, so a top-level import would be a
    cycle. They run for the same reason the product routes run them — so the
    figures on this page match what the user sees after clicking through.
    """
    from product import ensure_demo_products
    from address import ensure_demo_addresses
    ensure_demo_products()
    ensure_demo_addresses()

    m = _metrics()

    import auth

    quotation_url = url_for("quotation.list_quotations")
    create_url    = url_for("quotation.create_quotation")

    today   = m["today"]
    datestr = f"{today.strftime('%A')}, {today.day} {today.strftime('%B %Y')}"

    # ── The launcher, as data ────────────────────────────────────────────────
    # Every zone renders from `chrome.REGISTERS` — the same table the rail
    # draws from — filtered by `can_reach()` card by card; `_zone()` drops a
    # heading whose cards have all gone. See the zone builders above.
    groups = _zones(m)
    # The zone itself goes when every group in it has gone — a "Modules"
    # heading over nothing at all is the same lie as an empty group heading.
    modules_zone = f"""
        <div class="zone">
          <div class="zone-hd">
            <h2>Modules</h2>
            <span class="zn-sub">every register in the app</span>
          </div>
{"".join(g for g in groups if g)}

        </div>""" if any(groups) else ""

    # Header actions and the whole pipeline band are quotation surfaces. An
    # Operation Head or an HR user holds no `quotation.view`, so offering them
    # "New quotation", "Register" and a panel of links into the register would
    # be fifteen refusals in a row.
    actions = []
    if auth.can_reach("quotation.create_quotation"):
        actions.append(f'<a href="{create_url}" class="btn">'
                       f'{ICONS["plus"]} New quotation</a>')
    if auth.can_reach("quotation.list_quotations"):
        actions.append(f'<a href="{quotation_url}" class="btn btn-ghost">Register</a>')
    # The bar goes with its last button, for the reason an empty group heading
    # goes with its last card: an empty toolbar reads as a page that failed to
    # load rather than as a page with nothing to offer you.
    dash_actions = ('<div class="dash-actions">' + ACTION_SEP
                    + ACTION_SEP.join(actions)
                    + '\n          </div>') if actions else ""

    # The BOQ is the head of the chain this software exists to run, so its
    # call-to-action is the first block under the page head — above the
    # quotation band, and gated on its own endpoint.
    boq_cta = _boq_cta_html(m)

    insight = (_insight_html(m) if auth.can_reach("quotation.list_quotations")
               else "")

    # ⚠ **The project-billing band is NOT inside `insight`**, and that is the
    # point of it being a separate call. `insight` is suppressed wholesale for
    # anybody without `quotation.view` — an Operation Head holds `boq.view` and
    # `ra.view` and none of the quotation permissions, so folding these panels
    # into the quotation band would hide the BOQ chain from precisely the role
    # whose job it is. Each panel gates on its own register instead.
    chain = _chain_html(m)

    # Somebody whose roles reach no register at all would otherwise get a title
    # and an empty page, which looks broken rather than restricted. Say which
    # it is, and say who fixes it.
    nothing_here = "" if (any(groups) or chain or boq_cta) else """
        <div class="zone">
          <div class="card" style="padding:1.5rem;">
            <div class="card-title">Nothing to show here yet</div>
            <div class="card-desc">None of your roles reaches a register in this
              application. If that is wrong, an administrator can add the
              permission you need to one of them.</div>
          </div>
        </div>"""

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Dashboard")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
      {P.PIPELINE_STYLES}
      {DASH_STYLES}
    </head>
    <body>
      {_nav()}
      <main class="dash">

        <header class="dash-head">
          <div>
            <h1>Quotation <em>Desk</em></h1>
            <div class="dh-date">{datestr}</div>
          </div>
          {dash_actions}
        </header>
{boq_cta}
        {insight}
{chain}
{modules_zone}{nothing_here}

        <footer>
          <p>{B.COMPANY_NAME} &nbsp;·&nbsp; {B.APP_SUBTITLE} &nbsp;·&nbsp; internal use</p>
          {_footer_contact()}
        </footer>
      </main>
    </body>
    </html>
    """
    # No .html file is written to disk — everything is built in memory at
    # request time. The string is finished here and goes back to Flask as-is;
    # see the note above `_page()` for why it is not handed to Jinja.
    return _page(template)


