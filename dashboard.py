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

2. **The app's stylesheet.** `BASE_STYLES` and `_nav()` are imported by
   product.py, quotation.py and address.py. A change to `BASE_STYLES` changes
   every page in the app — dashboard-only rules belong in `DASH_STYLES`.

All HTML is built inline as f-strings — no /templates folder. The finished page
is returned to Flask directly and deliberately NOT re-parsed by Jinja; see the
note above `_page()`.

Import direction
----------------
This module may import `branding`, `store`, `pipeline` and `db` (none of them
import anything from the app, so there is no cycle). It must **never** import
`product`, `quotation` or `address` at module level — those import *us*. The
demo seeders are pulled in inside the view function for that reason.

`db` is on that list because `_nav()` renders the persistence-failure strip, and
`_nav()` is the only thing in this app that is on every page. db.py imports
pymysql, dotenv and the standard library and nothing of ours, so it sits at the
bottom of the graph beside branding.py and pipeline.py.

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
import db
import pipeline as P
from store import STORE

# ── Blueprint Declaration ─────────────────────────────────────────────────────
# name="dashboard" is the namespace used in url_for(), e.g. url_for("dashboard.index")
dashboard_bp = Blueprint("dashboard", __name__)


# ── Shared Styles (injected into every render_template_string call) ───────────
# Centralising the CSS here avoids duplication across routes while keeping
# everything inside Python — no external static files required.
# The colour tokens live in branding.py, so re-theming the whole app is a
# one-file change.
BASE_STYLES = """
<style>
  /* Google Font — DM Sans for a clean but not-generic feel.
     @import has to be the first rule in the sheet or the browser drops it. */
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

  /* ── Reset ───────────────────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
""" + B.CSS_TOKENS + """
  html, body {
    min-height: 100vh;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 16px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Nav ─────────────────────────────────────────────────────────── */
  nav {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 60px;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: var(--shadow-sm);
  }

  .nav-brand {
    display: flex;
    align-items: center;
    gap: .6rem;
    font-weight: 700;
    font-size: 1.05rem;
    text-decoration: none;
    letter-spacing: .02em;
  }

  /* Wordmark echoes the signboard: SAMRUDDHI in red, FIRE in navy. */
  .nav-brand .nb-word  { color: var(--brand); }
  .nav-brand .nb-fire  { color: var(--navy); }
  .nav-brand:hover .nb-word { opacity: .82; }

  .nav-pill {
    background: var(--navy-lt);
    color: var(--navy);
    font-size: .72rem;
    font-weight: 600;
    padding: .2rem .65rem;
    border-radius: 20px;
    letter-spacing: .04em;
    text-transform: uppercase;
  }

  .nav-right { display: flex; align-items: center; gap: .9rem; }
  .nav-link {
    display: flex; align-items: center; gap: .3rem;
    font-size: .8rem; font-weight: 600; color: var(--muted);
    text-decoration: none; white-space: nowrap;
  }
  .nav-link:hover { color: var(--brand); }
  .nav-link svg {
    width: 15px; height: 15px; fill: none; stroke: currentColor;
    stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  }
  /* Amber dot while any company/bank field is still blank — the documents are
     printing "add …" chips until it clears, so the nav should say so. */
  .nav-link .nl-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--saffron); flex-shrink: 0;
  }

  /* ── Persistence-down strip ──────────────────────────────────────── */
  /* Rendered by _nav(), so every page in the app carries it and no module has
     to remember to wire it up.

     Red, not the settings dot's amber, and a strip rather than a dot. Amber in
     this app means "incomplete but working" — a blank GSTIN prints a chip and
     the document still goes out. This means *nothing you type is being saved*,
     and a 7px dot cannot carry that. It clears itself the moment a retry
     succeeds, the same self-clearing contract the settings dot holds to. */
  .db-down {
    background: var(--brand);
    color: #fff;
    padding: .55rem 2rem;
    font-size: .82rem;
    line-height: 1.45;
    display: flex;
    align-items: baseline;
    gap: .6rem;
    position: sticky;
    top: 60px;          /* directly under the 60px nav, and sticky with it */
    z-index: 99;        /* below nav's 100, above the page */
  }
  .db-down-tag {
    flex-shrink: 0;
    font-size: .7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    border: 1px solid rgba(255,255,255,.55);
    border-radius: 3px;
    padding: .05rem .4rem;
  }
  .db-down code { font-size: .78rem; opacity: .92; }

  /* App chrome, never part of a printed document. The rule that hides `nav` on
     paper lives in quotation.py's VIEW_DOC_STYLES; this strip ships its own so
     it cannot print on a sheet whose page did not happen to load that one. */
  @media print { .db-down { display: none !important; } }

  @media (max-width: 580px) {
    .db-down { padding: .5rem 1rem; flex-direction: column; gap: .25rem; }
  }

  /* ── Main Layout ─────────────────────────────────────────────────── */
  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 3rem 1.5rem 5rem;
  }

  /* Contact strip under the footer rule */
  .foot-contact {
    margin-top: .35rem;
    font-size: .78rem;
    color: var(--muted);
  }
  .foot-contact b { color: var(--navy); font-weight: 600; }

  /* ── Card ────────────────────────────────────────────────────────── */
  /* Used by the dashboard's module strip (.mods in DASH_STYLES lays them out
     and overrides the padding). Kept here because a card is a general shape
     any future page can reach for. */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem 1.75rem;
    text-decoration: none;
    color: inherit;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
    box-shadow: var(--shadow-sm);
    position: relative;
    overflow: hidden;
  }

  /* Subtle top accent bar that reveals on hover */
  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--brand);
    transform: scaleX(0);
    transform-origin: left;
    transition: transform .25s ease;
  }

  .card:hover {
    transform: translateY(-5px);
    box-shadow: var(--shadow-md);
    border-color: var(--brand-lt);
  }

  .card:hover::before { transform: scaleX(1); }

  .card-icon {
    width: 48px;
    height: 48px;
    background: var(--brand-lt);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    flex-shrink: 0;
    transition: background .2s;
  }

  .card:hover .card-icon { background: var(--brand); }
  .card:hover .card-icon svg { stroke: #fff; }

  .card-icon svg {
    width: 24px;
    height: 24px;
    stroke: var(--brand);
    fill: none;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
    transition: stroke .2s;
  }

  .card-body { flex: 1; }

  .card-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--text);
    margin-bottom: .35rem;
  }

  .card-desc {
    font-size: .88rem;
    color: var(--muted);
    line-height: 1.55;
  }

  /* ── Button ──────────────────────────────────────────────────────── */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    background: var(--brand);
    color: #fff;
    font-family: var(--font);
    font-size: .88rem;
    font-weight: 600;
    padding: .65rem 1.4rem;
    border-radius: 8px;
    text-decoration: none;
    border: none;
    cursor: pointer;
    transition: background .15s, transform .15s;
  }

  .btn:hover { background: var(--brand-dk); transform: translateY(-1px); }
  .btn-ghost {
    background: transparent;
    color: var(--brand);
    border: 1.5px solid var(--brand);
  }
  .btn-ghost:hover { background: var(--brand-lt); transform: translateY(-1px); }

  /* ── Footer ──────────────────────────────────────────────────────── */
  footer {
    text-align: center;
    margin-top: 4rem;
    padding-top: 2rem;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: .8rem;
  }

  /* ── Responsive ──────────────────────────────────────────────────── */
  @media (max-width: 580px) {
    nav { padding: 0 1rem; }
    main { padding: 2rem 1rem 4rem; }
    /* The subtitle pill is decoration; the settings link is a control. On a
       narrow screen the control keeps the space. */
    .nav-pill { display: none; }
  }
</style>
"""

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
    gap: 1.25rem; flex-wrap: wrap; margin-bottom: 1.5rem;
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
  .band { display: grid; grid-template-columns: 1fr 1.85fr; gap: 1.1rem;
    margin-bottom: 1.1rem; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.1rem; }

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

  .kpi { padding: 1.05rem 1.15rem; display: flex; flex-direction: column;
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
  .cols     { display: grid; grid-template-columns: 1.1fr 1fr; gap: 1.1rem;
    margin-bottom: 1.1rem; align-items: stretch; }
  .cols-eq  { display: grid; grid-template-columns: 1fr 1fr; gap: 1.1rem;
    margin-bottom: 1.1rem; align-items: stretch; }

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
  .attn-more { font-size: .75rem; color: var(--muted); padding: .45rem .55rem 0; }

  /* ── Recent quotations ───────────────────────────────────────────── */
  .rq-row {
    display: grid; grid-template-columns: 1fr auto; gap: .7rem;
    align-items: center; padding: .55rem; border-radius: 9px;
    text-decoration: none; color: inherit;
  }
  .rq-row + .rq-row { border-top: 1px solid var(--border); border-radius: 0; }
  .rq-row:hover { background: var(--bg); }
  .rq-ref { font-size: .82rem; font-weight: 700; }
  .rq-row:hover .rq-ref { color: var(--brand); }
  .rq-acct { font-size: .78rem; color: var(--muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 22ch; }
  .rq-meta { display: flex; align-items: center; gap: .5rem; }
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

  /* ── Module strip (the launcher, demoted to the foot of the page) ── */
  .mods { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: .85rem; margin-top: .35rem; }
  .mods .card { flex-direction: row; align-items: center; gap: .85rem;
    padding: 1rem 1.1rem; }
  .mods .card-icon { width: 38px; height: 38px; border-radius: 10px; }
  .mods .card-icon svg { width: 19px; height: 19px; }
  .mods .card-title { font-size: .9rem; margin-bottom: .1rem; }
  .mods .card-desc { font-size: .74rem; }
  .mods-lbl { font-size: .74rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .09em; color: var(--muted); margin: 1.9rem 0 .8rem; }

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
  @media (max-width: 1000px) {
    .band { grid-template-columns: 1fr; }
    .cols, .cols-eq { grid-template-columns: 1fr; }
  }
  @media (max-width: 620px) {
    main.dash { padding: 1.5rem 1rem 3rem; }
    .kpis { grid-template-columns: 1fr; }
    .hero-fig .hf-val { font-size: 2.4rem; }
    .fn-row { grid-template-columns: 6.5rem 1fr 4.4rem; gap: .5rem; }
    .dash-head { align-items: flex-start; }
    .dash-actions { width: 100%; }
    .dash-actions .btn { flex: 1; justify-content: center; }
  }
</style>
"""


# ── SVG Icon Library ──────────────────────────────────────────────────────────
ICONS = {
    "product": """<svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>""",
    "quotation": """<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>""",
    "news": """<svg viewBox="0 0 24 24"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 0-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>""",
    "address": """<svg viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>""",
    "proforma": """<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 11v6"/><path d="M13.8 12.5h-2.6a1.4 1.4 0 0 0 0 2.8h1.6a1.4 1.4 0 0 1 0 2.8h-2.6"/></svg>""",
    # A tax invoice is the proforma's document with the statutory seal on it —
    # same sheet outline, a check mark instead of the rupee glyph, because what
    # distinguishes it is that the supply actually happened.
    "invoice": """<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><polyline points="9 15 11 17 15 12"/></svg>""",
    # Buy side: a carton, not a sheet of paper. The other document cards are
    # all page outlines; a purchase order is about material arriving, and it
    # reads as a different kind of thing at a glance because it is one.
    "purchase": """<svg viewBox="0 0 24 24"><path d="M21 8V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8"/><rect x="1" y="3" width="22" height="5" rx="1"/><line x1="10" y1="12" x2="14" y2="12"/></svg>""",
    # A BOQ is a schedule, not a letter: a clipboard with ruled lines, so it
    # does not read as another variant of the quotation sheet. It heads its own
    # chain and the icon says so at a glance.
    "boq": """<svg viewBox="0 0 24 24"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><line x1="8" y1="11" x2="16" y2="11"/><line x1="8" y1="15" x2="16" y2="15"/><line x1="8" y1="19" x2="12" y2="19"/></svg>""",
    "ra": """<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><polyline points="10 17 12 17 14 17"/></svg>""",
    # The library a BOQ is written from: stacked layers, because a spec is one
    # clause at several sizes. Deliberately not the BOQ clipboard — one is the
    # vocabulary, the other is the document.
    "spec": """<svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>""",
    "back": """<svg viewBox="0 0 24 24" width="16" height="16"><polyline points="15 18 9 12 15 6"/></svg>""",
    "settings": """<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>""",
    # Attention-queue reason icons. Status colour never carries meaning alone —
    # every row pairs its tone with one of these plus the reason in words.
    "overdue": """<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>""",
    "await":   """<svg viewBox="0 0 24 24"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>""",
    "stale":   """<svg viewBox="0 0 24 24"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>""",
    "nopo":    """<svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>""",
    "plus":    """<svg viewBox="0 0 24 24" width="16" height="16"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>""",
}


# ── Shared Nav Component ──────────────────────────────────────────────────────
def _persistence_strip() -> str:
    """
    A red strip under the nav while anything is failing to persist.

    Why this is in the chrome rather than on the dashboard: a user can work for
    an hour inside `/boq/create` without ever loading `/`. The only surface that
    is genuinely on every page is this nav, so the only honest place to say "the
    last twenty minutes of your work exists in RAM and nowhere else" is here.

    It is empty and costs nothing while persistence is healthy, and it clears
    itself the moment a retry lands — db.sync() drops the collection out of
    `_failures` on success, so no acknowledgement or dismissal is needed.

    **The visible text carries no exception.** The person reading this strip is
    office staff pricing a fire system, and a MySQL column error is noise they
    cannot act on. The raw error goes in `title=` instead, where it costs a
    hover to read and still lands in a screenshot — which is the form in which
    this will actually be reported.

    Both halves are escaped. MySQL quotes the offending value back in a
    truncation or duplicate-key message, so user input reaches both strings,
    and `P.esc` escapes quotes as well as angle brackets — which is what makes
    it safe in an attribute and not only in text.
    """
    note = db.failure_note()
    if not note:
        return ""
    # What to do about it differs by condition, and getting this wrong would be
    # worse than saying nothing. A failed *write* is retried on every request,
    # so the user should keep working and watch for the strip to clear. MySQL
    # unreachable at *boot* is never retried — sync() returns early — so the
    # only thing that fixes it is a restart, and telling that user to wait
    # would be a lie.
    tail = ("Every request retries." if db.is_live()
            else "Restart the app once MySQL is reachable.")
    detail = db.failure_detail()
    title = f' title="{P.esc(detail)}"' if detail else ""
    return (
        f'<div class="db-down" role="alert"{title}>'
        '<span class="db-down-tag">Not saving</span>'
        f'<span>{P.esc(note)} Changes are being kept in memory only and '
        f'will be lost on restart. {tail}</span>'
        '</div>'
    )


def _nav():
    """
    The shared nav. Rendered on every page, hidden by the print stylesheet.

    The settings link carries an amber dot while any company or bank field is
    still blank — those pages are printing visible "add …" chips until it
    clears, so the way to fix them should be one click away from wherever the
    user noticed.

    The persistence strip rides along underneath for the same reason, one
    severity up: see `_persistence_strip()`.
    """
    dashboard_url = url_for("dashboard.index")
    settings_url  = url_for("settings.edit_settings")

    incomplete = not B.has(*B.current_settings().values())
    dot = '<span class="nl-dot" title="Company details incomplete"></span>' if incomplete else ""

    return f"""
    <nav>
      <a href="{dashboard_url}" class="nav-brand">
        {B.logo_img(30)}
        <span class="nb-word">{B.name_html("nb-fire")}</span>
      </a>
      <div class="nav-right">
        <a href="{settings_url}" class="nav-link">{dot}{ICONS['settings']}Settings</a>
        <span class="nav-pill">{B.APP_SUBTITLE}</span>
      </div>
    </nav>
    {_persistence_strip()}
    """


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
    return (f'<p class="foot-contact">{B.COMPANY_ADDR} &nbsp;·&nbsp; '
            f'<b>{B.COMPANY_PHONE}</b> &nbsp;·&nbsp; {B.COMPANY_EMAIL}</p>')


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


def _metrics():
    """
    Everything the landing page draws, computed in one pass. Pure — no request
    state, no mutation beyond pipeline's own idempotent ensure_fields().
    """
    quotations = STORE["quotations"]
    products   = STORE["products"]
    today      = date.today()

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


def _attention_html(m) -> str:
    """The work queue. Empty is a good outcome, so say so rather than showing nothing."""
    rows = m["attention"]
    if not rows:
        return ('<div class="none">Nothing needs chasing — no overdue closings, '
                'no unanswered POs, nothing gone quiet.</div>')

    out = ""
    for _prio, tone, icon, qid, q, value, why in rows[:ATTENTION_LIMIT]:
        href = url_for("quotation.view_quotation", id=qid)
        out += f"""
          <a class="attn-row t-{tone}" href="{href}">
            <div class="attn-ico">{ICONS[icon]}</div>
            <div>
              <div class="attn-ref">{P.esc(q.get('ref') or '—')}
                <span class="attn-acct">· {P.esc(q.get('account_name') or 'Unnamed account')}</span></div>
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
        </section>"""


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

    product_url   = url_for("product.list_products")
    quotation_url = url_for("quotation.list_quotations")
    address_url   = url_for("address.list_addresses")
    proforma_url  = url_for("proforma.list_proformas")
    invoice_url   = url_for("invoice.list_invoices")
    purchase_url  = url_for("purchase.list_purchases")
    boq_url       = url_for("boq.list_boqs")
    ra_url        = url_for("ra.list_ras")
    spec_url      = url_for("spec.list_specs")
    extractor_url = url_for("extractor.index")   # Cross-blueprint url_for
    create_url    = url_for("quotation.create_quotation")

    today   = m["today"]
    datestr = f"{today.strftime('%A')}, {today.day} {today.strftime('%B %Y')}"

    std_count = m["p_total"] - m["p_assembly"] - m["p_support"]

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
          <div class="dash-actions">
            <a href="{create_url}" class="btn">{ICONS['plus']} New quotation</a>
            <a href="{quotation_url}" class="btn btn-ghost">Register</a>
          </div>
        </header>

        {_insight_html(m)}

        <div class="mods-lbl">Modules</div>
        <section class="mods">

          <a href="{product_url}" class="card">
            <div class="card-icon">{ICONS['product']}</div>
            <div class="card-body">
              <div class="card-title">Product Catalogue</div>
              <div class="card-desc">{m['p_total']} items · {m['p_assembly']} assemblies
                  · {std_count} standalone</div>
            </div>
          </a>

          <a href="{quotation_url}" class="card">
            <div class="card-icon">{ICONS['quotation']}</div>
            <div class="card-body">
              <div class="card-title">Quotations</div>
              <div class="card-desc">{m['q_count']} raised ·
                  {m['summary']['open']['count']} still live</div>
            </div>
          </a>

          <a href="{proforma_url}" class="card">
            <div class="card-icon">{ICONS['proforma']}</div>
            <div class="card-body">
              <div class="card-title">Proforma Invoices</div>
              <div class="card-desc">{m['pi_total']} issued{f" · {rupees(m['pi_due'])} requested" if m['pi_due'] else " · raised from a quotation"}</div>
            </div>
          </a>

          <a href="{invoice_url}" class="card">
            <div class="card-icon">{ICONS['invoice']}</div>
            <div class="card-body">
              <div class="card-title">Tax Invoices</div>
              <div class="card-desc">{m['ti_total']} issued{f" · {rupees(m['ti_due'])} outstanding" if m['ti_due'] else " · raised from a proforma"}</div>
            </div>
          </a>

          <a href="{spec_url}" class="card">
            <div class="card-icon">{ICONS['spec']}</div>
            <div class="card-body">
              <div class="card-title">Spec Library</div>
              <div class="card-desc">{m['spec_total']} clauses · what a BOQ line is written from</div>
            </div>
          </a>

          <a href="{boq_url}" class="card">
            <div class="card-icon">{ICONS['boq']}</div>
            <div class="card-body">
              <div class="card-title">Bills of Quantities</div>
              <div class="card-desc">{m['boq_total']} priced{f" · {rupees(m['boq_value'])} basic value" if m['boq_value'] else " · project schedules, billed by RA"}</div>
            </div>
          </a>

          <a href="{ra_url}" class="card">
            <div class="card-icon">{ICONS['ra']}</div>
            <div class="card-body">
              <div class="card-title">Running Account Bills</div>
              <div class="card-desc">{m['ra_total']} raised{f" · {rupees(m['ra_value'])} claimed" if m['ra_value'] else " · interim claims against BOQs"}</div>
            </div>
          </a>

          <a href="{purchase_url}" class="card">
            <div class="card-icon">{ICONS['purchase']}</div>
            <div class="card-body">
              <div class="card-title">Purchase Orders</div>
              <div class="card-desc">{m['po_total']} raised{f" · {rupees(m['po_committed'])} committed" if m['po_committed'] else " · what we buy, not what we sell"}</div>
            </div>
          </a>

          <a href="{address_url}" class="card">
            <div class="card-icon">{ICONS['address']}</div>
            <div class="card-body">
              <div class="card-title">Address Book</div>
              <div class="card-desc">{m['a_total']} saved · feeds the Bill To and
                  Ship To pickers</div>
            </div>
          </a>

          <a href="{extractor_url}" target="_blank" class="card">
            <div class="card-icon">{ICONS['news']}</div>
            <div class="card-body">
              <div class="card-title">Market News</div>
              <div class="card-desc">Pump, steel and fire-safety prices ↗</div>
            </div>
          </a>

        </section>

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


