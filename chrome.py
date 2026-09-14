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

    chrome.py ──► branding, db, pipeline, flask      and nothing else of ours
                  at module level. `auth` is reached INSIDE `_nav_links()` and
                  `_user_chip()` only — `auth.py` imports this module at module
                  level for `_shell()`, so a top-level import back is a cycle.

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

from flask import has_request_context, request, url_for

import branding as B
import db
import pipeline as P


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
#   suppression below is moot: there is no nav for a chip to be on. The set is
#   kept because the chip test still derives it from the golden file, and
#   `/po/create` — a form, not a printed document — still renders the nav with
#   the chip suppressed on it.
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

    Empty in three cases, each on purpose:

    * **no request context** — nothing to read a session from;
    * **no signed-in user** — `/login` and `/setup` do not layer this chrome at
      all, but the 404 and 413 handlers can render before anybody has signed
      in, and a chip saying nothing is worse than no chip;
    * **a page a golden pins** — see `PINNED_PAGES`.

    The control is a **link to `GET /logout`**, not a POST button. `/logout`
    already confirms on GET and destroys on POST, the delete-route convention
    from `9d060ee`, and putting the form in the nav would both bypass that
    confirmation and put a `<form>` on every page in the application.
    """
    import auth

    if not has_request_context() or request.endpoint in PINNED_PAGES:
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


# The nav's own entries, as data rather than as markup.
#
# `endpoint` is the key into `auth.ROUTE_PERMISSIONS` — the **same** dict
# `_gate()` answers from — so what the nav offers and what the gate allows
# cannot drift apart. There is deliberately no permission id here: writing one
# would be the second list, and the second list is how a hidden entry becomes an
# open route (or a visible one becomes a dead link).
#
# ⚠ **The nav is not the launcher and must not become it.** Fifteen registers
# live on the dashboard's module strip; what belongs *here* is what somebody
# needs from wherever they already are. Every entry also carries a card, which
# is the Projects pattern rather than a duplication introduced here.
#
# ⚠ **THE RULE WAS AMENDED ON 30 AUGUST 2026, and the amendment is the point.**
#   It used to name three kinds of page — the entity that groups the documents
#   (Projects), the register the workforce pages hang off (Employees), and
#   configuration (Settings) — and a measurement sheet is none of the three. The
#   entry added the day before was correctly flagged as breaking the rule rather
#   than argued into it, and the note below is that flag, kept verbatim.
#
#   Removing the entry would have moved five print goldens to make a document
#   HARDER to find, against an owner who had just reported that he could not
#   reach most of what had been built. So the entry stays and the rule is
#   restated as a test rather than as a list of three kinds:
#
#       An entry belongs here when somebody, MID-TASK and unable to finish,
#       has to go and use it — not when it is merely important.
#
#   Projects, Employees and Settings all still pass it. Measurements passes it
#   for a reason C1 makes concrete: `/ra/create` on the installation leg is
#   REFUSED until an approved measurement exists, so the person who discovers
#   they need one discovers it while raising a claim somewhere else entirely.
#
#   ⚠ The BOQ is the nearest miss and stays off, deliberately. C1 gates the
#     measurement on a BOQ exactly as it gates the claim on the measurement, so
#     "another document needs it first" does NOT separate them — the honest
#     separation is that a BOQ is where the work starts and you are already
#     there, while a measurement is the step you find missing on your way to
#     something else. That is a finer distinction than the old rule carried, and
#     it is written down so the next pass argues with it instead of rediscovering
#     it. **A fifth entry still needs a reason of this shape, and still moves
#     five goldens.**
#
# ABOUT.md §5 (`/` — Dashboard) records the amendment and its date.
#
# ⚠ ~~**Adding an entry moves every print golden in this repository.** `_nav()` is
# embedded in every printed page and hidden by CSS at print, so the bytes move
# while the paper does not. That is why `employee.py` shipped with no link on
# 29 August 2026 and why the link arrived in a pass authorised to re-baseline —
# ABOUT.md §7, "Global Nav vs Print Goldens". Do not add one casually.~~
# ✅ **Closed 14 September 2026.** No print route calls `_nav()` any more; an
#   entry added here moves the `/po/create` picker's golden — a form — and no
#   printed document. ABOUT.md §7's first gap carries the measurement.
# ⚠ **A FOURTH ENTRY ARRIVED 29 August 2026 (fifth pass) — the measurement
#   register — and it is the FIRST DOCUMENT REGISTER in this nav.** Read the
#   rule above before adding a fifth: Projects is the entity that groups the
#   documents, Employees is the register the workforce pages hang off, Settings
#   is configuration, and a measurement sheet is none of those three. It is here
#   because the pass brief that authorised C2 required it, and that is recorded
#   plainly rather than argued into the rule — this entry is the one that makes
#   "the nav is not the launcher" harder to hold, not an example of it.
#
#   ⚠ **Kept verbatim, and superseded by the amendment above (30 August 2026).**
#     It is left standing rather than rewritten because it is the honest record
#     of an entry that broke the rule as it then stood, and because the case
#     against, two paragraphs down, is still the strongest argument anybody has
#     made here. The rule changed to fit the application; this note is why.
#
#   The case for it, such as it is: an installation claim is refused until an
#   approved sheet exists, so the measurement register is the page somebody is
#   sent to from wherever they already are. The case against it is that the
#   same is true of the BOQ, which has a card and no nav entry.
#
#   It moved four print goldens, in the `_nav()` block and nowhere else, in a
#   commit that did nothing but this.
NAV_ITEMS = (
    ("project.list_projects",     "project",  "Projects"),
    ("measurement.list_ms",       "boq",      "Measurements"),
    ("employee.list_employees",   "employee", "Employees"),
    ("settings.edit_settings",    "settings", "Settings"),
)

# The indent each nav entry sits on. A constant so the joined output is
# byte-for-byte what the hand-written markup produced before it was filtered —
# five print goldens hash this nav, and an Owner (who may reach every entry)
# must render exactly the bytes they did on 26 August.
NAV_LINK_SEP = "\n        "

def _nav_links() -> str:
    """
    The nav entries this user may actually reach, in order.

    Empty for somebody who may reach neither, which leaves the brand, the pill
    and the user chip — a nav with no dead ends rather than a nav with none.
    """
    import auth

    out = []
    for endpoint, icon, label in NAV_ITEMS:
        if not auth.can_reach(endpoint):
            continue
        dot = ""
        if endpoint == "settings.edit_settings" and not B.has(*B.current_settings().values()):
            dot = '<span class="nl-dot" title="Company details incomplete"></span>'
        out.append(f'<a href="{url_for(endpoint)}" class="nav-link">'
                   f'{dot}{ICONS[icon]}{label}</a>')
    return "".join(NAV_LINK_SEP + link for link in out)


def _nav():
    """
    The shared nav. Rendered on every SCREEN page. ⚠ **Not on a print route**
    (14 September 2026): `/invoice/view`, `/proforma/view`, `/purchase/view`,
    `/ra/print` and `/merged/print` stopped calling it, joining `/dc/print`,
    `/boq/print`, `/po/print` and `/measurement/print`, so that a nav change
    can never again move a printed document's golden. `/quotation/view` is the
    one document page that still calls it, because `quotation.py` is frozen.

    Its entries are filtered by what the signed-in user may reach — see
    `_nav_links()` and `auth.can_reach()`. **That is presentation only.** Every
    route is still gated by `_gate()` on the request itself; a link that is not
    drawn is not a route that is closed.

    The signed-in user chip rides at the right-hand end, and it is the only
    sign-out control in the application. It lives in `_user_chip()` with its own
    style constant rather than in `BASE_STYLES`, so the block the print goldens
    hash is untouched; it renders empty on the six endpoints a golden pins. See
    `PINNED_PAGES`.

    The settings link carries an amber dot while any company or bank field is
    still blank — those pages are printing visible "add …" chips until it
    clears, so the way to fix them should be one click away from wherever the
    user noticed.

    The persistence strip rides along underneath for the same reason, one
    severity up: see `_persistence_strip()`.
    """
    dashboard_url = url_for("dashboard.index")

    return f"""
    <nav>
      <a href="{dashboard_url}" class="nav-brand">
        {B.logo_img(30)}
        <span class="nb-word">{B.name_html("nb-fire")}</span>
      </a>
      <div class="nav-right">{_nav_links()}
        <span class="nav-pill">{B.APP_SUBTITLE}</span>{_user_chip()}
      </div>
    </nav>
    {_persistence_strip()}
    """

