"""
extractor.py — The Feature Module
==================================
Blueprint: extractor_bp
Mounted at: /extractor (url_prefix defined on the Blueprint)

Provides the "News Extractor Analyzer" page — a standalone, visually isolated
module that can be opened in a new tab from the main dashboard.
"""

from flask import Blueprint, render_template_string, url_for

# ── Blueprint Declaration ─────────────────────────────────────────────────────
# url_prefix='/extractor' means all routes inside are automatically prefixed.
# e.g. @extractor_bp.route('/') becomes accessible at /extractor/
extractor_bp = Blueprint("extractor", __name__, url_prefix="/extractor")


# ── Dummy news data ───────────────────────────────────────────────────────────
# In production, this would be fetched from an RSS feed or a news API.
# Hardcoded here to keep the demo self-contained and dependency-free.
SAMPLE_ARTICLES = [
    {
        "tag": "Markets",
        "tag_color": "#10b981",
        "title": "Fed holds rates steady as inflation cools to 2.4%",
        "source": "Reuters",
        "time": "2h ago",
        "summary": "The Federal Reserve left its benchmark rate unchanged, citing easing price pressures and a resilient labour market.",
    },
    {
        "tag": "Supply Chain",
        "tag_color": "#f59e0b",
        "title": "Semiconductor shortage eases — lead times drop to 14 weeks",
        "source": "Bloomberg",
        "time": "5h ago",
        "summary": "Global chip inventory is recovering faster than expected, offering relief to manufacturers that have struggled to fill orders.",
    },
    {
        "tag": "Commodities",
        "tag_color": "#ef4444",
        "title": "Brent crude rises 3% on Middle East supply concerns",
        "source": "FT",
        "time": "7h ago",
        "summary": "Oil futures climbed after reports of disruptions to a key shipping corridor, prompting traders to reprice near-term supply risk.",
    },
    {
        "tag": "Trade",
        "tag_color": "#6366f1",
        "title": "US–EU tariff truce extended by 12 months",
        "source": "WSJ",
        "time": "1d ago",
        "summary": "Negotiators agreed to maintain zero tariffs on steel and aluminium exports while broader talks continue into next year.",
    },
]


# ── Route ─────────────────────────────────────────────────────────────────────

@extractor_bp.route("/")
def index():
    """
    Main page for the News Extractor Analyzer.
    url_for('dashboard.index') is used for the return link — this is the correct
    cross-blueprint reference pattern: 'blueprint_name.view_function_name'.
    """
    dashboard_url = url_for("dashboard.index")

    # Build article cards dynamically from SAMPLE_ARTICLES
    article_cards_html = ""
    for article in SAMPLE_ARTICLES:
        article_cards_html += f"""
        <article class="article-card">
          <div class="article-meta">
            <span class="article-tag" style="background:{article['tag_color']}22; color:{article['tag_color']};">
              {article['tag']}
            </span>
            <span class="article-time">{article['source']} &nbsp;·&nbsp; {article['time']}</span>
          </div>
          <h3 class="article-title">{article['title']}</h3>
          <p class="article-summary">{article['summary']}</p>
          <div class="article-actions">
            <button class="chip-btn" onclick="this.textContent = this.textContent === '+ Add to Quotation' ? '✓ Added' : '+ Add to Quotation'; this.classList.toggle('added');">
              + Add to Quotation
            </button>
          </div>
        </article>
        """

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>News Extractor — QMS</title>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        :root {{
          --bg:       #0f172a;
          --surface:  #1e293b;
          --surface2: #273449;
          --brand:    #818cf8;
          --brand-dk: #6366f1;
          --brand-lt: #1e1b4b;
          --text:     #e2e8f0;
          --muted:    #94a3b8;
          --border:   #334155;
          --radius:   14px;
          --font:     'DM Sans', system-ui, sans-serif;
          --shadow:   0 4px 24px rgba(0,0,0,.35);
        }}

        html, body {{
          min-height: 100vh;
          background: var(--bg);
          color: var(--text);
          font-family: var(--font);
          -webkit-font-smoothing: antialiased;
        }}

        /* ── Nav ──────────────────────────────────────────────────── */
        nav {{
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
        }}

        .nav-left {{
          display: flex;
          align-items: center;
          gap: 1rem;
        }}

        .nav-brand {{
          font-weight: 700;
          font-size: 1rem;
          color: var(--brand);
          letter-spacing: -.3px;
        }}

        .nav-divider {{
          width: 1px;
          height: 20px;
          background: var(--border);
        }}

        .nav-title {{
          font-size: .92rem;
          color: var(--muted);
          font-weight: 500;
        }}

        /* url_for cross-blueprint link: url_for('dashboard.index') */
        .return-link {{
          display: inline-flex;
          align-items: center;
          gap: .35rem;
          font-size: .82rem;
          font-weight: 600;
          color: var(--brand);
          text-decoration: none;
          padding: .4rem .9rem;
          border: 1px solid var(--border);
          border-radius: 8px;
          transition: background .15s, border-color .15s;
        }}

        .return-link:hover {{
          background: var(--brand-lt);
          border-color: var(--brand);
        }}

        /* ── Layout ───────────────────────────────────────────────── */
        main {{
          max-width: 820px;
          margin: 0 auto;
          padding: 2.5rem 1.5rem 5rem;
        }}

        /* ── Page Header ──────────────────────────────────────────── */
        header.page-header {{
          margin-bottom: 2.5rem;
        }}

        .module-badge {{
          display: inline-flex;
          align-items: center;
          gap: .4rem;
          background: var(--brand-lt);
          color: var(--brand);
          font-size: .72rem;
          font-weight: 700;
          padding: .3rem .8rem;
          border-radius: 20px;
          text-transform: uppercase;
          letter-spacing: .06em;
          margin-bottom: 1rem;
        }}

        header.page-header h1 {{
          font-size: clamp(1.5rem, 3.5vw, 2.25rem);
          font-weight: 700;
          letter-spacing: -.5px;
          line-height: 1.2;
        }}

        header.page-header h1 span {{ color: var(--brand); }}

        header.page-header p {{
          color: var(--muted);
          margin-top: .6rem;
          font-size: .95rem;
          max-width: 480px;
        }}

        /* ── Filter Bar ───────────────────────────────────────────── */
        .filter-bar {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1.5rem;
          flex-wrap: wrap;
          gap: .75rem;
        }}

        .filter-label {{
          font-size: .82rem;
          color: var(--muted);
          font-weight: 500;
        }}

        .live-badge {{
          display: flex;
          align-items: center;
          gap: .45rem;
          font-size: .78rem;
          color: #34d399;
          font-weight: 600;
        }}

        .live-dot {{
          width: 7px;
          height: 7px;
          background: #34d399;
          border-radius: 50%;
          animation: pulse 1.6s infinite;
        }}

        @keyframes pulse {{
          0%, 100% {{ opacity: 1; transform: scale(1); }}
          50%  {{ opacity: .4; transform: scale(.8); }}
        }}

        /* ── Article Cards ────────────────────────────────────────── */
        .articles-feed {{
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }}

        .article-card {{
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 1.5rem 1.75rem;
          transition: border-color .2s, transform .2s;
        }}

        .article-card:hover {{
          border-color: var(--brand);
          transform: translateX(4px);
        }}

        .article-meta {{
          display: flex;
          align-items: center;
          gap: .75rem;
          margin-bottom: .75rem;
        }}

        .article-tag {{
          font-size: .7rem;
          font-weight: 700;
          padding: .2rem .6rem;
          border-radius: 20px;
          text-transform: uppercase;
          letter-spacing: .05em;
        }}

        .article-time {{
          font-size: .78rem;
          color: var(--muted);
        }}

        .article-title {{
          font-size: 1rem;
          font-weight: 700;
          color: var(--text);
          margin-bottom: .5rem;
          line-height: 1.4;
        }}

        .article-summary {{
          font-size: .87rem;
          color: var(--muted);
          line-height: 1.6;
          margin-bottom: 1rem;
        }}

        .chip-btn {{
          font-family: var(--font);
          font-size: .78rem;
          font-weight: 600;
          color: var(--brand);
          background: var(--brand-lt);
          border: 1px solid transparent;
          border-radius: 6px;
          padding: .35rem .85rem;
          cursor: pointer;
          transition: background .15s, color .15s, border-color .15s;
        }}

        .chip-btn:hover {{ border-color: var(--brand); }}

        .chip-btn.added {{
          background: #14532d22;
          color: #34d399;
        }}

        /* ── Footer ───────────────────────────────────────────────── */
        footer {{
          text-align: center;
          margin-top: 3.5rem;
          padding-top: 2rem;
          border-top: 1px solid var(--border);
          color: var(--muted);
          font-size: .78rem;
        }}

        /* ── Responsive ───────────────────────────────────────────── */
        @media (max-width: 580px) {{
          nav {{ padding: 0 1rem; }}
          main {{ padding: 1.75rem 1rem 4rem; }}
          .article-card {{ padding: 1.2rem 1.25rem; }}
        }}
      </style>
    </head>
    <body>
      <nav>
        <div class="nav-left">
          <span class="nav-brand">◆ QMS</span>
          <div class="nav-divider"></div>
          <span class="nav-title">News Extractor</span>
        </div>

        <!--
          url_for('dashboard.index') resolves to '/' at runtime.
          This is the correct cross-blueprint reference syntax:
          'blueprint_name.view_function_name'
        -->
        <a href="{dashboard_url}" class="return-link">
          ← Return to System Dashboard
        </a>
      </nav>

      <main>
        <header class="page-header">
          <div class="module-badge">📡 Live Feed</div>
          <h1>News Extractor <span>Analyzer</span></h1>
          <p>Real-time market signals surfaced and tagged for direct integration into your quotation workflow.</p>
        </header>

        <div class="filter-bar">
          <span class="filter-label">{len(SAMPLE_ARTICLES)} articles retrieved</span>
          <span class="live-badge">
            <span class="live-dot"></span>
            Live — updated every 15 min
          </span>
        </div>

        <section class="articles-feed">
          {article_cards_html}
        </section>

        <footer>
          <p>News Extractor Module &nbsp;·&nbsp; QMS Platform &nbsp;·&nbsp; Prices and data are simulated</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return render_template_string(template)