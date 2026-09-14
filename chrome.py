"""
chrome.py — the app shell every screen page renders
====================================================

The shared stylesheet (`BASE_STYLES`), the icon library, the signed-in user
chip, the persistence-failure strip and the navigation bar (`_nav()`), lifted
out of `dashboard.py` on 14 September 2026 — **verbatim, and measured**:
`tests/test_page_golden.py` pins twenty-two screen pages byte-for-byte and was
committed before this module existed, so the move is an observation and not
an intention.

Why it moved
------------
Every page in the application reaches its navigation by importing the module
that draws it. Until this file existed that module was `dashboard.py`, which
also computes the landing page's metrics and imports most of the app inside
its view functions — so the nav's dependencies were the dashboard's, and a
chrome that grew would have grown a known cycle with it. This is the same
extraction as `docsheet.py` (the printed sheet) and `boqpick.py` (the line
picker), done for the same reason and gated the same way.

Import direction
----------------
A LEAF, held to `docsheet.py`'s standard in `tests/test_import_directions.py`:

    chrome.py ──► branding, db, pipeline, store, flask   and nothing else of ours
                  at module level. `auth` is reached INSIDE `_rail()`,
                  `_primary_action()`, `reachable_registers()` and
                  `_user_chip()` only — `auth.py` imports this module at
                  module level for `_shell()`, so a top-level import back is
                  a cycle. `store` arrived with the registry (14 Sep 2026):
                  the rail's live counts read the collections directly.

It may not import any module that prints, and the printed sheet
(`docsheet.py`) may not import it: a printed document must not depend on the
shell. `docsheet.py` reads `BASE_STYLES` through `dashboard.py`'s re-export
for exactly that reason. `dashboard.py` imports this module and re-exports
`BASE_STYLES` and `_nav` because `product.py` and `quotation.py` — both
frozen — still read them from there.

`db` is on the list because `_persistence_strip()` renders the
persistence-failure strip and `_nav()` is the only thing in this app that is
on every screen page; `db.py` imports pymysql, dotenv and the standard
library and nothing of ours, so it sits at the bottom of the graph.

⚠ **Not on any print route** (14 September 2026). `/invoice/view`,
`/proforma/view`, `/purchase/view`, `/ra/print` and `/merged/print` stopped
calling `_nav()`, joining `/dc/print`, `/boq/print`, `/po/print` and
`/measurement/print`; `tests/test_print_golden.py::test_no_print_route_renders_the_nav`
holds it. `/quotation/view` is the one document page that still calls it,
because `quotation.py` is frozen.
"""

from collections import namedtuple

from flask import has_request_context, request, url_for

import branding as B
import db
import pipeline as P
from store import STORE


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
    "users":   """<svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>""",
    "project": """<svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>""",
    # One person with a card, not the `users` pair: `users` opens the *accounts*
    # register (who may sign in), and this opens the *employee* master (who
    # works here and what they are paid). Two registers that both say "people"
    # need telling apart at a glance, and they are the two an auditor most often
    # confuses — PROGRESS.md §6-E is that confusion in words.
    "employee": """<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/><line x1="17" y1="3" x2="21" y2="3"/><line x1="19" y1="1" x2="19" y2="5"/></svg>""",
}


# ── The signed-in user chip ───────────────────────────────────────────────────
#
# Its own constant, emitted **inside the body next to the chip itself**, and
# deliberately NOT folded into `BASE_STYLES`.
#
# `BASE_STYLES` is the block five print goldens hash. Adding four rules to it
# would move all five for a control that `@media print` hides anyway — see
# ABOUT.md §7, "Global Nav vs Print Goldens". A `<style>` element in the body
# is valid HTML5 and is the one shape that lets this ship without touching that
# block or any page's `<head>`.

USER_CHIP_STYLES = """
<style>
  .nav-user {
    display: flex; align-items: center; gap: .5rem;
    padding-left: .85rem; border-left: 1px solid var(--border);
  }
  .nu-who {
    display: flex; align-items: center; gap: .45rem;
    text-decoration: none; color: var(--text);
    font-size: .8rem; font-weight: 600; white-space: nowrap;
  }
  .nu-who:hover { color: var(--brand); }
  .nu-avatar {
    width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
    background: var(--navy-lt); color: var(--navy);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: .68rem; font-weight: 700; letter-spacing: .02em;
  }
  .nu-out {
    font-size: .76rem; font-weight: 600; color: var(--muted);
    text-decoration: none; white-space: nowrap;
    border: 1px solid var(--border); border-radius: 6px; padding: .22rem .55rem;
  }
  .nu-out:hover { color: var(--brand); border-color: var(--brand); }

  /* The name goes first on a narrow screen; the avatar and Sign out stay. */
  @media (max-width: 820px) { .nu-name { display: none; } }
</style>
"""

# The endpoints whose exact response bytes `tests/test_print_golden.py` hashes.
#
# ⚠ **This is not a list of print routes.** `/invoice/view`, `/proforma/view`
# and `/purchase/view` are screen pages that happen to carry an A4 sheet, and
# `/po/create` is a form. What the six have in common is only that a golden
# pins them byte-for-byte, so **anything** added to their chrome moves a
# digest — and a nav change has no business re-baselining a printed document.
#
# The chip is therefore suppressed on exactly these, and nowhere else. The set
# is checked against the golden file itself by
# `tests/test_nav_user_chip.py::test_the_suppression_set_is_exactly_what_the_goldens_pin`,
# so it cannot quietly drift out of step with what is actually hashed — add a
# golden without adding its endpoint here and that test fails, which is the
# only reason a hand-written set is acceptable at all.
#
# 📌 The cost is stated plainly rather than hidden: **six pages carry no sign-out
# control**, and the way to fix that is to break the nav/golden coupling
# (ABOUT.md §7, "Global Nav vs Print Goldens"), not to re-baseline anything.
#
# ✅ **14 September 2026 — the coupling is broken, and the set means something
#   simpler now.** Every print route renders NO nav at all (the challan's shape,
#   given to the other five), so for every member but `po_draft.create_po` the
#   suppression was moot: there is no nav for a chip to be on. **And with the
#   sidebar, the suppression itself is gone** — `_user_chip()` no longer reads
#   this set, so `/po/create` (a form) carries the chip like every screen page
#   and its golden was re-baselined for it in the same commit. The set is kept
#   as the one place that says which endpoints a golden hashes, and the chip
#   test still derives it from the golden file and holds it in step.
PINNED_PAGES = frozenset({
    "invoice.view_invoice",
    "proforma.view_proforma",
    "purchase.view_purchase",
    "ra.print_ra",
    "challan.print_dc",
    "po_draft.create_po",
    # 6 September 2026 — the JOINT MEASUREMENT SHEET gained a print golden, so
    # its page joins the set for the reason every other member is here: a nav
    # change must not be able to move a document's recorded digest.
    # `tests/test_nav_user_chip.py` derives this set from the URLs the golden
    # file actually requests and fails if the two disagree, which is how this
    # entry came to be needed rather than remembered.
    "measurement.print_ms",
    # 14 September 2026 — the three print routes that had no golden are pinned
    # before the nav is stripped out of every print route, so the strip can be
    # measured rather than trusted. Same reason as the entry above.
    "boq.print_boq",
    "po_draft.print_po",
    "merged_ra.print_merged",
})


def _user_chip() -> str:
    """
    Who is signed in, their account, and the way out.

    `auth` is imported **inside the function body** — the escape hatch
    `_access_card()` and `index()` already use, and for the same reason:
    `auth._shell()` imports `_nav` from this module, so a module-level import
    here would be a cycle (ABOUT.md §2g).

    Empty in two cases, each on purpose:

    * **no request context** — nothing to read a session from;
    * **no signed-in user** — `/login` and `/setup` do not layer this chrome at
      all, but the 404 and 413 handlers can render before anybody has signed
      in, and a chip saying nothing is worse than no chip.

    ⚠ A third case — *a page a golden pins* — was removed on 14 September
      2026 with the sidebar. No print route renders the chrome at all any
      more, and the one pinned form (`/po/create`) carries the chip like every
      other screen page; its golden moved for it, in that commit, on purpose.

    The control is a **link to `GET /logout`**, not a POST button. `/logout`
    already confirms on GET and destroys on POST, the delete-route convention
    from `9d060ee`, and putting the form in the nav would both bypass that
    confirmation and put a `<form>` on every page in the application.
    """
    import auth

    if not has_request_context():
        return ""

    user = auth.current_user()
    if user is None:
        return ""

    name = (user.get("display_name") or user.get("username") or "").strip()
    initials = "".join(word[0] for word in name.split()[:2]).upper() or "?"

    return f"""{USER_CHIP_STYLES}
        <div class="nav-user">
          <a class="nu-who" href="{url_for('auth.account')}"
             title="My account &mdash; {P.esc(name)}">
            <span class="nu-avatar">{P.esc(initials)}</span>
            <span class="nu-name">{P.esc(name)}</span>
          </a>
          <a class="nu-out" href="{url_for('auth.logout')}">Sign out</a>
        </div>"""


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


# =============================================================================
# THE REGISTRY — one data structure describing every register (14 Sep 2026)
# =============================================================================
#
# **Both the rail and the dashboard's module zones render from this.** Two
# hand-written lists — one for the nav, one for the launcher — drift the first
# time a register is added, and `tests/test_sidebar.py` asserts the rail and
# the dashboard name the same set for the same user.
#
# `endpoint` is the key into `auth.ROUTE_PERMISSIONS` — the **same** dict
# `_gate()` answers from — so what the rail offers and what the gate allows
# cannot drift apart. There is deliberately no permission id anywhere in this
# table: writing one would be the second list, and the second list is how a
# hidden entry becomes an open route (or a visible one becomes a dead link).
# **Hiding is presentation; the gate is the gate.** Every route is still
# refused on the request itself whether or not it was drawn, and the filter is
# endpoint-level because that is the only guarantee this application can make
# (ABOUT.md §7 gap 24 — there is no per-record access control anywhere).
#
# `count` is the callable that produces the register's summary figure — the
# live count on the rail, and the primary figure on its dashboard card. It
# reads `STORE` directly and imports nothing, so the shell can draw it on every
# page without reaching into the module that owns the register. `unit` is the
# word printed beside that figure. `None` for a count means "no figure" —
# Market News is four hard-coded articles and a figure would be a lie.
#
# ⚠ **Action labels are WRITTEN OUT, never derived.** Stripping a trailing `s`
#   off a register name produces "New market new" and "New spec librar", which
#   is why each entry carries its own `action_label` beside `action_endpoint`.
#   A register whose create route needs a schedule behind it (`/dc/create`,
#   `/po/create`, `/measurement/create` all redirect without `?boq=`) carries
#   no action here; those are raised from `/boq/view`, which is where the
#   button belongs.
#
# `Product Catalogue` stays in the table while `auth.HIDDEN_BLUEPRINTS` hides
# the module (ABOUT.md §2g): `can_reach()` answers False for it, so it is
# drawn nowhere, and un-hiding the module is still one line in `auth.py`.

Group = namedtuple("Group", "key label title sub accent tint zone")
Register = namedtuple(
    "Register",
    "group key name icon endpoint count unit action_endpoint action_label new_tab")


def _reg(group, key, name, icon, endpoint, count, unit,
         action_endpoint="", action_label="", new_tab=False):
    return Register(group, key, name, icon, endpoint, count, unit,
                    action_endpoint, action_label, new_tab)


# ── The four groups, in the order the rail and the dashboard draw them ──────
#
# The colours were checked for colour-blind separation and are used exactly:
# a magenta variant for the buy side failed against the teal. Library is
# achromatic on purpose — it is reference data, not a money chain, and it must
# not shout beside the three chains that move money.
GROUPS = (
    Group("sell", "Sell side &mdash; money in", "Sell side",
          "money in &middot; quotation &rarr; proforma &rarr; tax invoice",
          "#5B4BC4", "#EDEBFA", "#FAFAFE"),
    Group("proj", "Projects &amp; site billing", "Projects &amp; site billing",
          "schedules, interim claims and despatch",
          "#0A8F78", "#E1F3EF", "#F8FDFC"),
    Group("buy", "Buy side &mdash; money out", "Buy side",
          "money out &middot; never linked to a proforma or a tax invoice",
          "#B8600C", "#FAEEE1", "#FFFCF8"),
    Group("lib", "Library &amp; records", "Library &amp; records",
          "what the documents above are written from",
          "#5A5468", "#EEECF2", "#FBFAFC"),
)


def _n(key):
    """A count of one collection, read live."""
    return lambda: len(STORE.get(key) or {})


def _clients():
    """Distinct billed-to parties over every BOQ — `client.py`'s own grouping key."""
    return len({P.norm_name(b.get("account_name"))
                for b in (STORE.get("boqs") or {}).values()
                if str(b.get("account_name") or "").strip()})


def _active(key):
    """Records whose `active` flag is on — absent means active, as both masters read it."""
    return lambda: sum(1 for r in (STORE.get(key) or {}).values()
                       if r.get("active", True))


REGISTERS = (
    # ── Sell side — money in ─────────────────────────────────────────────
    _reg("sell", "quotation", "Quotations", "quotation",
         "quotation.list_quotations", _n("quotations"), "raised",
         "quotation.create_quotation", "New quotation"),
    _reg("sell", "proforma", "Proforma Invoices", "proforma",
         "proforma.list_proformas", _n("proformas"), "issued"),
    _reg("sell", "invoice", "Tax Invoices", "invoice",
         "invoice.list_invoices", _n("invoices"), "issued"),
    # ── Projects & site billing ──────────────────────────────────────────
    _reg("proj", "project", "Projects", "project",
         "project.list_projects", _n("projects"), "created",
         "project.create_project", "New project"),
    _reg("proj", "boq", "Bills of Quantities", "boq",
         "boq.list_boqs", _n("boqs"), "priced",
         "boq.create_boq", "New BOQ"),
    _reg("proj", "ra", "Running Account Bills", "ra",
         "ra.list_ras", _n("ra_bills"), "raised",
         "ra.create_ra", "New RA bill"),
    _reg("proj", "receipt", "Receipts", "receipt",
         "receipt.list_receipts", _n("receipts"), "recorded",
         "receipt.new_receipt", "Record a payment"),
    _reg("proj", "challan", "Delivery Challans", "challan",
         "challan.list_dcs", _n("delivery_challans"), "raised"),
    _reg("proj", "measurement", "Measurement Sheets", "measurement",
         "measurement.list_ms", _n("measurements"), "raised"),
    # ── Buy side — money out ─────────────────────────────────────────────
    _reg("buy", "purchase", "Purchase Orders", "purchase",
         "purchase.list_purchases", _n("purchases"), "raised",
         "purchase.create_purchase", "New purchase order"),
    _reg("buy", "po_draft", "Draft Purchase Orders", "draft",
         "po_draft.list_pos", _n("purchase_orders"), "raised"),
    _reg("buy", "charge", "Expenses &amp; Charges", "charge",
         "charge.list_charges", _n("charges"), "entries",
         "charge.new_charge", "New expense"),
    _reg("buy", "attendance", "Attendance", "attendance",
         "attendance.list_attendance", _n("attendance"), "marked",
         "attendance.mark_attendance", "Mark attendance"),
    # ── Library & records ────────────────────────────────────────────────
    _reg("lib", "product", "Product Catalogue", "product",
         "product.list_products", _n("products"), "items",
         "product.add_product", "New product"),
    _reg("lib", "spec", "Spec Library", "spec",
         "spec.list_specs", _n("specs"), "clauses",
         "spec.add_spec", "New spec clause"),
    _reg("lib", "client", "Client Register", "client",
         "client.list_clients", _clients, "clients"),
    _reg("lib", "employee", "Employees", "employee",
         "employee.list_employees", _active("employees"), "active",
         "employee.new_employee", "New employee"),
    _reg("lib", "address", "Address Book", "address",
         "address.list_addresses", _n("addresses"), "saved",
         "address.add_address", "New address"),
    _reg("lib", "news", "Market News", "news",
         "extractor.index", None, "", new_tab=True),
    _reg("lib", "users", "Users &amp; Access", "users",
         "auth.list_users", _active("users"), "active users",
         "auth.create_user", "New user"),
)

GROUP_OF = {g.key: g for g in GROUPS}

# The endpoint prefix each register answers for when the rail decides which
# entry is the current page. A blueprint that is a sub-register of another
# highlights its parent: the project DETAIL page is `projectview`, the merged
# tax invoice is a sub-register of the RA register (CC-2 C3), and the four
# `auth` pages are the Users & Access register's own.
_BLUEPRINT_ALIAS = {
    "projectview": "project",
    "merged_ra": "ra",
}


def registers_in(group_key: str):
    """The registry's entries for one group, in the order they are drawn."""
    return [r for r in REGISTERS if r.group == group_key]


def reachable_registers():
    """
    The registry filtered by what the signed-in user may reach, in order.

    `auth.can_reach()` reads `ROUTE_PERMISSIONS` — the dict the gate answers
    from — so a register that would refuse this user is not drawn. It is
    imported inside the function body because `auth.py` imports this module
    at module level for `_shell()`.
    """
    import auth

    return [r for r in REGISTERS if auth.can_reach(r.endpoint)]


def summary_count(reg):
    """The register's live figure, or None where it carries none."""
    return None if reg.count is None else int(reg.count())


def current_register():
    """The registry entry the request's endpoint belongs to, or None."""
    if not has_request_context() or not request.endpoint:
        return None
    bp = request.endpoint.split(".", 1)[0]
    bp = _BLUEPRINT_ALIAS.get(bp, bp)
    for r in REGISTERS:
        if r.endpoint.split(".", 1)[0] == bp:
            return r
    return None


# ── Icons the registry and the chrome need that the launcher never had ─────
#
# Hand-written inline SVG, 24×24 stroke paths like every entry above. Each
# register now has a glyph of its own where four used to share `purchase` and
# two shared `proforma`; a rail of twenty entries collapsed to icons alone is
# unreadable if six of them are the same carton.
ICONS.update({
    # A grid of four — the landing page.
    "dashboard": """<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>""",
    # Money received: a banknote with a rupee mark, not another sheet of paper.
    "receipt": """<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 12h.01M18 12h.01"/></svg>""",
    # Goods leaving the yard: a truck.
    "challan": """<svg viewBox="0 0 24 24"><path d="M1 3h13v13H1z"/><path d="M14 8h4l4 4v4h-8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>""",
    # What was found on site: a ruler.
    "measurement": """<svg viewBox="0 0 24 24"><path d="M2 17 17 2l5 5L7 22z"/><path d="m7.5 11.5 2 2M11 8l2 2M14.5 4.5l2 2"/></svg>""",
    # A draft order: the carton outline with a dashed lid — asked for, not yet priced.
    "draft": """<svg viewBox="0 0 24 24"><path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8"/><path d="M1 3h22v5H1z" stroke-dasharray="3 2"/><line x1="10" y1="12" x2="14" y2="12"/></svg>""",
    # An expense: a wallet.
    "charge": """<svg viewBox="0 0 24 24"><path d="M20 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M16 3H6a2 2 0 0 0-2 2v2"/><circle cx="17" cy="14" r="1.2"/></svg>""",
    # A day marked: a calendar with a tick.
    "attendance": """<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="17" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><polyline points="9 15 11 17 15 13"/></svg>""",
    # A client: a building, not the pair of people that opens the accounts register.
    "client": """<svg viewBox="0 0 24 24"><path d="M3 21h18"/><path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/><path d="M10 21v-3h4v3"/></svg>""",
    # The rail's own controls.
    "menu": """<svg viewBox="0 0 24 24"><line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/></svg>""",
    "collapse": """<svg viewBox="0 0 24 24"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>""",
    "chevron": """<svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>""",
    # Status chip icons — one per tone, always beside a word (ABOUT.md §6).
    "ok": """<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>""",
    "warn": """<svg viewBox="0 0 24 24"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>""",
    "crit": """<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>""",
})


# =============================================================================
# THE SHELL'S OWN STYLESHEET — emitted by _nav(), in the body, on screen pages
# =============================================================================
#
# ⚠ **Deliberately NOT folded into `BASE_STYLES`.** `docsheet.SHEET_STYLES`
#   opens with `BASE_STYLES`, so every printed document carries that constant in
#   the `head` block nine print goldens hash — a rule added there re-baselines
#   documents that go to a client for a change that never reaches paper. So the
#   sidebar's rules live here and ride out with `_nav()`, which no print route
#   calls (14 September 2026). `USER_CHIP_STYLES` set the precedent: a `<style>`
#   element in the body is valid HTML5, and it is the one shape that leaves the
#   shared `<head>` stack untouched.
#
#   The cost is stated rather than hidden: `BASE_STYLES` still carries the
#   retired top-bar rules (`nav {…}`, `.nav-link`, `.nav-pill`), dead on every
#   page now. `nav.rail` below overrides every property the old `nav {}` rule
#   sets, by class specificity. Removing them from `BASE_STYLES` moves nine
#   printed documents' `head` digests for no visible change and is a print
#   re-baseline of its own — ABOUT.md §7 gap 39.
#
# A plain string, not an f-string, so the CSS braces are written once.
CHROME_STYLES = """
<style>
  :root {
    --rail-w: 248px; --rail-c: 68px; --tb-h: 56px;
    --ground: #F6F4F9; --ink: #1A1626; --ink-muted: #6B6478; --hair: #E4E0EC;
    --g-sell: #5B4BC4; --g-sell-t: #EDEBFA; --g-sell-z: #FAFAFE;
    --g-proj: #0A8F78; --g-proj-t: #E1F3EF; --g-proj-z: #F8FDFC;
    --g-buy:  #B8600C; --g-buy-t:  #FAEEE1; --g-buy-z:  #FFFCF8;
    --g-lib:  #5A5468; --g-lib-t:  #EEECF2; --g-lib-z:  #FBFAFC;
    --st-good: #0F7A52; --st-good-bg: #E2F2EB;
    --st-warn: #9A6B00; --st-warn-bg: #F7EFDC;
    --st-crit: #D5121A; --st-crit-bg: #FCE9E9;
  }
  /* One class per group carries its three colours as custom properties, so the
     rail, the top bar and the dashboard zones all read the same four values. */
  .g-sell { --ga: var(--g-sell); --gt: var(--g-sell-t); --gz: var(--g-sell-z); }
  .g-proj { --ga: var(--g-proj); --gt: var(--g-proj-t); --gz: var(--g-proj-z); }
  .g-buy  { --ga: var(--g-buy);  --gt: var(--g-buy-t);  --gz: var(--g-buy-z);  }
  .g-lib  { --ga: var(--g-lib);  --gt: var(--g-lib-t);  --gz: var(--g-lib-z);  }

  /* The content column sits to the right of the rail. `main`'s own max-width
     and auto margins centre it in what is left. */
  body { padding-left: var(--rail-w); }
  html.rail-collapsed body { padding-left: var(--rail-c); }

  /* ── The rail ─────────────────────────────────────────────────────── */
  /* Every property the retired `nav {}` rule in BASE_STYLES sets is restated
     here, because that rule still lands on this element. */
  nav.rail {
    position: fixed; top: 0; left: 0; bottom: 0; height: 100vh;
    width: var(--rail-w);
    display: flex; flex-direction: column; align-items: stretch;
    justify-content: flex-start;
    padding: 0; border: 0; box-shadow: none; z-index: 200;
    background: linear-gradient(168deg, #1C0449 0%, #2A086E 100%);
    color: #CFC7EA; overflow: hidden;
    transition: width .18s ease, transform .18s ease;
  }
  html.rail-collapsed nav.rail { width: var(--rail-c); }

  .rail-hd {
    display: flex; align-items: center; gap: .5rem; flex-shrink: 0;
    height: var(--tb-h); padding: 0 .85rem;
    border-bottom: 1px solid rgba(255,255,255,.08);
  }
  .rail-toggle, .tb-toggle {
    width: 34px; height: 34px; border: 0; border-radius: 8px; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0; font: inherit;
  }
  .rail-toggle { background: rgba(255,255,255,.08); color: #CFC7EA; }
  .rail-toggle:hover { background: rgba(255,255,255,.16); color: #fff; }
  .rail-toggle svg, .tb-toggle svg {
    width: 18px; height: 18px; stroke: currentColor; fill: none;
    stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  }
  .rail-brand { display: inline-flex; align-items: center; margin-left: auto; }
  .rail-brand img { width: 28px; height: 28px; border-radius: 7px; display: block; }

  .rail-scroll {
    flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden;
    padding: .65rem .6rem 1rem;
    scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.22) transparent;
  }
  .rail-scroll::-webkit-scrollbar { width: 6px; }
  .rail-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.22); border-radius: 3px; }

  .rail-grp { margin-top: 1.05rem; }
  .rail-lbl {
    display: flex; align-items: center; gap: .5rem;
    padding: 0 .6rem .4rem;
    font-size: 10.5px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #8E82BE; white-space: nowrap;
  }
  .rail-dot { display: block; width: 6px; height: 6px; background: var(--ga); flex-shrink: 0; }

  .rl {
    display: flex; align-items: center; gap: .6rem; position: relative;
    padding: .46rem .6rem; border-radius: 8px;
    font-size: 13.5px; font-weight: 500; line-height: 1.3;
    color: #CFC7EA; text-decoration: none; white-space: nowrap;
  }
  .rl svg {
    width: 16px; height: 16px; flex-shrink: 0;
    stroke: currentColor; fill: none; stroke-width: 1.9;
    stroke-linecap: round; stroke-linejoin: round;
  }
  .rl:hover { background: rgba(255,255,255,.09); color: #fff; }
  .rl.is-active { background: rgba(255,255,255,.14); color: #fff; font-weight: 600; }
  .rl.is-active::before {
    content: ''; position: absolute; left: 0; top: 6px; bottom: 6px;
    width: 3px; border-radius: 0 2px 2px 0; background: var(--ga, #fff);
  }
  .rl-txt { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .rl-n { margin-left: auto; font-size: 12px; color: #8E82BE; font-variant-numeric: tabular-nums; }
  /* Amber dot on Settings while a company or bank field is blank — the same
     signal the old bar carried, one severity below the persistence strip. */
  .rl-warn { width: 7px; height: 7px; border-radius: 50%; background: var(--saffron); flex-shrink: 0; }

  .rail-ft { flex-shrink: 0; padding: .5rem .6rem .8rem; border-top: 1px solid rgba(255,255,255,.08); }

  /* Collapsed: icons only, and the group dot becomes an 18×3 rule so the
     grouping survives without its label. */
  html.rail-collapsed .rl-txt, html.rail-collapsed .rl-n,
  html.rail-collapsed .rail-lbl span, html.rail-collapsed .rail-brand { display: none; }
  html.rail-collapsed .rail-lbl { padding: 0 0 .45rem; justify-content: center; }
  html.rail-collapsed .rail-dot { width: 18px; height: 3px; border-radius: 2px; }
  html.rail-collapsed .rl { justify-content: center; padding: .55rem 0; gap: 0; }
  html.rail-collapsed .rl .rl-warn { position: absolute; top: 6px; right: 10px; }
  html.rail-collapsed .rail-hd { justify-content: center; padding: 0; }
  html.rail-collapsed .rail-scroll, html.rail-collapsed .rail-ft { padding-left: .5rem; padding-right: .5rem; }

  /* ── The top stack: the persistence strip, then the bar, sticky together ── */
  .topstack { position: sticky; top: 0; z-index: 150; }
  .topstack .db-down { position: static; top: auto; }
  .topbar {
    min-height: var(--tb-h);
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
    padding: .4rem 1.5rem;
    background: rgba(255,255,255,.88);
    -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
    border-bottom: 1px solid #E4E0EC;
  }
  .tb-left { display: flex; align-items: center; gap: .8rem; min-width: 0; }
  .tb-toggle { display: none; background: transparent; color: var(--ink-muted); }
  .tb-toggle:hover { background: var(--ground); color: var(--ink); }
  .topbar .nav-brand { font-size: .95rem; flex-shrink: 0; }
  .topbar .nav-brand img { width: 26px; height: 26px; }
  .tb-div { width: 1px; height: 26px; background: #E4E0EC; flex-shrink: 0; }
  .tb-title { min-width: 0; }
  .tb-name {
    font-size: 16px; font-weight: 700; color: #1A1626; line-height: 1.2;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .tb-sub {
    font-size: 12.5px; color: #8A8398; line-height: 1.3;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .tb-right { display: flex; align-items: center; gap: .8rem; flex-shrink: 0; }
  .tb-act { font-size: .82rem; padding: .5rem 1rem; }
  .tb-act svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2.2; stroke-linecap: round; }

  /* The scrim behind an off-canvas rail on a phone. */
  .rail-scrim { display: none; position: fixed; inset: 0; background: rgba(26,22,38,.45); z-index: 190; }

  /* ── One breakpoint. Below 1000px the rail is its icon form whatever is
        stored; below 620px it is off-canvas behind the toggle. ─────────── */
  @media (max-width: 1000px) {
    body, html.rail-collapsed body { padding-left: var(--rail-c); }
    nav.rail, html.rail-collapsed nav.rail { width: var(--rail-c); }
    nav.rail .rl-txt, nav.rail .rl-n, nav.rail .rail-lbl span, nav.rail .rail-brand { display: none; }
    nav.rail .rail-lbl { padding: 0 0 .45rem; justify-content: center; }
    nav.rail .rail-dot { width: 18px; height: 3px; border-radius: 2px; }
    nav.rail .rl { justify-content: center; padding: .55rem 0; gap: 0; }
    nav.rail .rl .rl-warn { position: absolute; top: 6px; right: 10px; }
    nav.rail .rail-hd { justify-content: center; padding: 0; }
    nav.rail .rail-scroll, nav.rail .rail-ft { padding-left: .5rem; padding-right: .5rem; }
  }
  @media (max-width: 620px) {
    body, html.rail-collapsed body { padding-left: 0; }
    nav.rail, html.rail-collapsed nav.rail { width: var(--rail-w); transform: translateX(-100%); }
    html.rail-open nav.rail { transform: none; }
    html.rail-open .rail-scrim { display: block; }
    /* Open on a phone, the rail is its full expanded self. */
    nav.rail .rl-txt, nav.rail .rl-n, nav.rail .rail-lbl span { display: initial; }
    nav.rail .rail-lbl { padding: 0 .6rem .4rem; justify-content: flex-start; }
    nav.rail .rail-dot { width: 6px; height: 6px; border-radius: 0; }
    nav.rail .rl { justify-content: flex-start; padding: .46rem .6rem; gap: .6rem; }
    nav.rail .rl .rl-warn { position: static; }
    nav.rail .rail-hd { justify-content: flex-start; padding: 0 .85rem; }
    nav.rail .rail-brand { display: inline-flex; }
    nav.rail .rail-scroll, nav.rail .rail-ft { padding-left: .6rem; padding-right: .6rem; }
    .tb-toggle { display: inline-flex; }
    .rail-toggle { display: none; }
    .topbar { padding: .4rem 1rem; }
    .topbar .nav-brand .nb-word { display: none; }
    .tb-div { display: none; }
  }

  /* App chrome, never part of a printed page. `/quotation/view` still draws
     the rail (quotation.py is frozen) and its sheet hides `nav` at print; the
     top stack and the padding are this sheet's to hide. */
  @media print {
    nav.rail, .topstack, .rail-scrim { display: none !important; }
    body { padding-left: 0 !important; }
  }
</style>
"""

# The collapse toggle's state, remembered per browser. **No server round-trip,
# no cookie, no route**: `localStorage`, read and written inside `try/catch`
# because a private window or a blocked store throws on access, and a rail
# that fails to draw because a preference could not be read is worse than a
# rail that forgets. It runs BEFORE the rail's markup so a stored "collapsed"
# never flashes the wide rail first. A plain string: the braces are JS's.
CHROME_SCRIPT = """
<script>
(function () {
  var KEY = 'sf.rail', H = document.documentElement;
  try { if (localStorage.getItem(KEY) === 'collapsed') H.classList.add('rail-collapsed'); } catch (e) {}
  window.railToggle = function () {
    if (window.matchMedia && window.matchMedia('(max-width: 620px)').matches) {
      H.classList.toggle('rail-open');
      return;
    }
    var collapsed = H.classList.toggle('rail-collapsed');
    try { localStorage.setItem(KEY, collapsed ? 'collapsed' : 'expanded'); } catch (e) {}
  };
  window.railClose = function () { H.classList.remove('rail-open'); };
})();
</script>
"""


# =============================================================================
# THE RAIL, THE TOP BAR, AND _nav()
# =============================================================================

def _settings_dot() -> str:
    """The amber dot the Settings entry carries while a company or bank field is blank."""
    if B.has(*B.current_settings().values()):
        return ""
    return '<span class="rl-warn" title="Company details incomplete"></span>'


def _rail_link(href: str, icon: str, label: str, active: bool,
               count=None, extra: str = "", new_tab: bool = False) -> str:
    n = "" if count is None else f'<span class="rl-n">{count}</span>'
    tab = ' target="_blank" rel="noopener"' if new_tab else ""
    cls = "rl is-active" if active else "rl"
    return (f'<a class="{cls}" href="{href}"{tab} title="{label}">'
            f'{ICONS[icon]}{extra}<span class="rl-txt">{label}</span>{n}</a>')


def _rail() -> str:
    """
    The left rail: the collapse toggle and the brand glyph, then Dashboard,
    then the four groups of registers this user may reach, then Settings.

    **The wordmark, the user chip and Sign out are deliberately NOT here** —
    they stay in the top bar. The rail is where you go; the bar is who you are
    and what you can do on this page.

    Every entry is drawn only when `auth.can_reach()` says the gate would let
    this user through, and a group whose every entry is hidden goes with its
    last entry. That is presentation and never the access check: the route
    still refuses on the request itself.
    """
    import auth

    here = current_register()
    at_dashboard = has_request_context() and request.endpoint == "dashboard.index"

    body = _rail_link(url_for("dashboard.index"), "dashboard", "Dashboard",
                      at_dashboard)
    for g in GROUPS:
        links = ""
        for r in registers_in(g.key):
            if not auth.can_reach(r.endpoint):
                continue
            links += "\n      " + _rail_link(
                url_for(r.endpoint), r.icon, r.name,
                here is not None and here.key == r.key,
                summary_count(r), new_tab=r.new_tab)
        if not links:
            continue
        body += (f'\n    <div class="rail-grp g-{g.key}">'
                 f'\n      <div class="rail-lbl"><i class="rail-dot"></i><span>{g.label}</span></div>'
                 f'{links}\n    </div>')

    foot = ""
    if auth.can_reach("settings.edit_settings"):
        foot = _rail_link(
            url_for("settings.edit_settings"), "settings", "Settings",
            has_request_context() and (request.endpoint or "").startswith("settings."),
            extra=_settings_dot())
        foot = f'\n  <div class="rail-ft">{foot}</div>'

    return f"""<nav class="rail" id="rail" aria-label="Registers">
  <div class="rail-hd">
    <button class="rail-toggle" type="button" onclick="railToggle()"
            aria-label="Collapse or expand the navigation" title="Collapse / expand">{ICONS['collapse']}</button>
    <a class="rail-brand" href="{url_for('dashboard.index')}" title="Dashboard">{B.logo_img(28)}</a>
  </div>
  <div class="rail-scroll">
    {body}
  </div>{foot}
</nav>
<div class="rail-scrim" onclick="railClose()"></div>"""


# The top bar's title and subtitle, by the blueprint the request belongs to.
# A register's pages take the register's name over its group; the pages that
# are not registers are named here, and anything else gets the app's subtitle.
_TITLES = {
    "dashboard":   ("Dashboard", "pipeline, projects and what needs chasing"),
    "settings":    ("Settings", "company identity, bank details and number series"),
    "merged_ra":   ("Merged Tax Invoices", "Projects &amp; site billing"),
    "projectview": ("Projects", "Projects &amp; site billing"),
    "approval":    ("Approvals", "the ladder, and what it refused"),
}
_AUTH_TITLES = {
    "auth.account":    ("My account", "your details, roles and password"),
    "auth.logout":     ("Sign out", "confirm to end the session"),
    "auth.access_log": ("Access log", "the last 500 refusals"),
    "auth.list_roles": ("Roles", "who may do what"),
    "auth.create_role": ("Roles", "who may do what"),
    "auth.edit_role":  ("Roles", "who may do what"),
}


def page_title() -> tuple:
    """`(title, subtitle)` for the top bar, both already HTML-safe."""
    if not has_request_context() or not request.endpoint:
        return (B.APP_SUBTITLE, "")
    ep = request.endpoint
    if ep in _AUTH_TITLES:
        return _AUTH_TITLES[ep]
    bp = ep.split(".", 1)[0]
    if bp in _TITLES:
        return _TITLES[bp]
    reg = current_register()
    if reg is not None:
        return (reg.name, GROUP_OF[reg.group].label)
    return (B.APP_SUBTITLE, "")


def _primary_action() -> str:
    """
    The current register's own action — `+ New BOQ` on the BOQ pages — drawn
    only when the gate would allow it, and not on the action's own page.
    """
    import auth

    reg = current_register()
    if reg is None or not reg.action_endpoint:
        return ""
    if request.endpoint == reg.action_endpoint or not auth.can_reach(reg.action_endpoint):
        return ""
    return (f'<a class="btn tb-act" href="{url_for(reg.action_endpoint)}">'
            f'{ICONS["plus"]} {reg.action_label}</a>')


def _topbar() -> str:
    """
    Sticky, above the page. Left: the phone toggle, the wordmark, a hairline,
    the page title and its subtitle. Right: the page's primary action, then the
    signed-in user chip and Sign out — the one sign-out control in the app.
    """
    title, sub = page_title()
    sub_html = f'<div class="tb-sub">{sub}</div>' if sub else ""
    return f"""<header class="topbar">
  <div class="tb-left">
    <button class="tb-toggle" type="button" onclick="railToggle()"
            aria-label="Open the navigation" title="Menu">{ICONS['menu']}</button>
    <a href="{url_for('dashboard.index')}" class="nav-brand">
      {B.logo_img(26)}
      <span class="nb-word">{B.name_html("nb-fire")}</span>
    </a>
    <span class="tb-div"></span>
    <div class="tb-title"><div class="tb-name">{title}</div>{sub_html}</div>
  </div>
  <div class="tb-right">{_primary_action()}{_user_chip()}
  </div>
</header>"""


def _nav():
    """
    The app shell, rendered on every SCREEN page: the stylesheet and the
    script the shell needs, the left rail, then — in one sticky stack — the
    red persistence strip and the top bar.

    ⚠ **Not on a print route** (14 September 2026): `/invoice/view`,
    `/proforma/view`, `/purchase/view`, `/ra/print` and `/merged/print`
    stopped calling it, joining `/dc/print`, `/boq/print`, `/po/print` and
    `/measurement/print`, so that a chrome change can never again move a
    printed document's golden. `/quotation/view` is the one document page
    that still calls it, because `quotation.py` is frozen.

    Its entries render from `REGISTERS` filtered by what the signed-in user
    may reach — see `_rail()` and `auth.can_reach()`. **That is presentation
    only.** Every route is still gated by `_gate()` on the request itself; a
    link that is not drawn is not a route that is closed.

    The two app-wide warnings ride here for the same reason they always did —
    this is the only surface genuinely on every page. The settings entry
    carries an amber dot while a company or bank field is blank; the
    persistence strip sits above the top bar, one severity up, and keeps
    working exactly as it did under the old bar: see `_persistence_strip()`.

    The styles and the script are emitted here, in the body, and not in any
    page's `<head>` — `CHROME_STYLES` says why.
    """
    return f"""{CHROME_STYLES}{CHROME_SCRIPT}
{_rail()}
<div class="topstack">{_persistence_strip()}
{_topbar()}
</div>
"""
