"""
dashboard.py — The UI Core
==========================
Blueprint: dashboard_bp
Mounted at: / (root)

Handles the main landing page and stub routes for Product and Quotation modules.
All HTML is rendered inline via render_template_string — no /templates folder needed.
"""

from flask import Blueprint, render_template_string, url_for

# ── Blueprint Declaration ─────────────────────────────────────────────────────
# name="dashboard" is the namespace used in url_for(), e.g. url_for("dashboard.index")
dashboard_bp = Blueprint("dashboard", __name__)


# ── Shared Styles (injected into every render_template_string call) ───────────
# Centralising the CSS here avoids duplication across routes while keeping
# everything inside Python — no external static files required.
BASE_STYLES = """
<style>
  /* ── Reset & Tokens ──────────────────────────────────────────────── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #f1f5f9;
    --surface:   #ffffff;
    --brand:     #4f46e5;
    --brand-dk:  #3730a3;
    --brand-lt:  #e0e7ff;
    --text:      #1e293b;
    --muted:     #64748b;
    --border:    #e2e8f0;
    --shadow-sm: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.06);
    --shadow-md: 0 4px 16px rgba(79,70,229,.14), 0 2px 6px rgba(0,0,0,.08);
    --radius:    14px;
    --font:      'DM Sans', 'Segoe UI', system-ui, sans-serif;
  }

  /* Google Font — DM Sans for a clean but not-generic feel */
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

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
    gap: .5rem;
    font-weight: 700;
    font-size: 1.05rem;
    color: var(--brand);
    text-decoration: none;
    letter-spacing: -.3px;
  }

  .nav-brand span { color: var(--text); }

  .nav-pill {
    background: var(--brand-lt);
    color: var(--brand);
    font-size: .72rem;
    font-weight: 600;
    padding: .2rem .65rem;
    border-radius: 20px;
    letter-spacing: .04em;
    text-transform: uppercase;
  }

  /* ── Main Layout ─────────────────────────────────────────────────── */
  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 3rem 1.5rem 5rem;
  }

  /* ── Hero ────────────────────────────────────────────────────────── */
  header.hero {
    text-align: center;
    margin-bottom: 3.5rem;
  }

  header.hero h1 {
    font-size: clamp(1.8rem, 4vw, 2.75rem);
    font-weight: 700;
    letter-spacing: -.6px;
    color: var(--text);
    line-height: 1.2;
  }

  header.hero h1 em {
    font-style: normal;
    color: var(--brand);
  }

  header.hero p {
    margin-top: .75rem;
    color: var(--muted);
    font-size: 1.05rem;
    max-width: 480px;
    margin-inline: auto;
  }

  /* ── Card Grid ───────────────────────────────────────────────────── */
  section.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.5rem;
  }

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

  .card-arrow {
    display: flex;
    align-items: center;
    gap: .3rem;
    font-size: .82rem;
    font-weight: 600;
    color: var(--brand);
    margin-top: .25rem;
  }

  /* ── Stub Page ───────────────────────────────────────────────────── */
  .stub-wrapper {
    min-height: 60vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .stub-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 3rem 3.5rem;
    text-align: center;
    box-shadow: var(--shadow-sm);
    max-width: 440px;
    width: 100%;
  }

  .stub-badge {
    display: inline-block;
    background: var(--brand-lt);
    color: var(--brand);
    font-size: .72rem;
    font-weight: 700;
    padding: .3rem .8rem;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom: 1rem;
  }

  .stub-card h2 {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -.4px;
    margin-bottom: .5rem;
  }

  .stub-card p {
    color: var(--muted);
    font-size: .92rem;
    margin-bottom: 1.75rem;
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
  @media (max-width: 900px) {
    section.grid { grid-template-columns: repeat(2, 1fr); }
  }

  @media (max-width: 580px) {
    nav { padding: 0 1rem; }
    main { padding: 2rem 1rem 4rem; }
    section.grid { grid-template-columns: 1fr; }
    .stub-card { padding: 2rem 1.5rem; }
    header.hero h1 { font-size: 1.6rem; }
  }
</style>
"""

# ── SVG Icon Library ──────────────────────────────────────────────────────────
ICONS = {
    "product": """<svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>""",
    "quotation": """<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>""",
    "news": """<svg viewBox="0 0 24 24"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 0-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>""",
    "back": """<svg viewBox="0 0 24 24" width="16" height="16"><polyline points="15 18 9 12 15 6"/></svg>""",
}


# ── Shared Nav Component ──────────────────────────────────────────────────────
def _nav():
    dashboard_url = url_for("dashboard.index")
    return f"""
    <nav>
      <a href="{dashboard_url}" class="nav-brand">
        ◆ QMS<span>&nbsp;Platform</span>
      </a>
      <span class="nav-pill">Demo v1.0</span>
    </nav>
    """


# ── Routes ────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/")
def index():
    """
    Landing dashboard — 3-card grid linking to all system modules.
    render_template_string is used here instead of a .html file so the entire
    UI lives in this single Python module; ideal for self-contained demos.
    """
    product_url   = url_for("product.list_products")
    quotation_url = url_for("quotation.list_quotations")
    extractor_url = url_for("extractor.index")  # Cross-blueprint url_for

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>QMS — Dashboard</title>
      {BASE_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        <header class="hero">
          <h1>Quotation <em>Management</em> System</h1>
          <p>A modular platform for managing products, quotations, and live intelligence.</p>
        </header>

        <section class="grid">

          <!-- Card 1: Product Module -->
          <a href="{product_url}" class="card">
            <div class="card-icon">{ICONS["product"]}</div>
            <div class="card-body">
              <div class="card-title">Product Catalog</div>
              <div class="card-desc">Browse, manage, and update your full inventory of products and SKUs in one place.</div>
            </div>
            <div class="card-arrow">Open module →</div>
          </a>

          <!-- Card 2: Quotation Module -->
          <a href="{quotation_url}" class="card">
            <div class="card-icon">{ICONS["quotation"]}</div>
            <div class="card-body">
              <div class="card-title">Quotations</div>
              <div class="card-desc">Generate, track, and export client quotations. Full PDF and email delivery built in.</div>
            </div>
            <div class="card-arrow">Open module →</div>
          </a>

          <!-- Card 3: News Extractor — opens in new tab to demo multi-tab UX -->
          <a href="{extractor_url}" target="_blank" class="card">
            <div class="card-icon">{ICONS["news"]}</div>
            <div class="card-body">
              <div class="card-title">News Extractor</div>
              <div class="card-desc">Pull and analyze live market news to keep your quotations priced against real-world data.</div>
            </div>
            <div class="card-arrow">Launch ↗</div>
          </a>

        </section>

        <footer>
          <p>Quotation Management System &nbsp;·&nbsp; Blueprint Demo &nbsp;·&nbsp; Flask 3.x</p>
        </footer>
      </main>
    </body>
    </html>
    """
    # render_template_string compiles the Jinja2 template from the string literal above.
    # No .html file is written to disk — everything is rendered in memory at request time.
    return render_template_string(template)


