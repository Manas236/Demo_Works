"""
=============================================================================
ADDITIONS TO product.py — Assembly View Feature
=============================================================================

HOW TO APPLY
------------
This file contains four self-contained additions. Apply them in order:

  [A]  Paste VIEW_STYLES  anywhere after PRODUCT_STYLES (new constant)
  [B]  Paste _render_tree() anywhere after _build_child_select_options()
  [C]  Paste view_product() route anywhere before or after delete_product()
  [D]  In list_products(), replace the existing <td> that holds the Delete
       button with the patched version that adds the View button for assemblies.

=============================================================================
[A]  VIEW_STYLES  — paste after PRODUCT_STYLES block
=============================================================================
"""

VIEW_STYLES = """
<style>
  /* ── Product detail header ─────────────────────────────────────────── */
  .detail-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem 2.25rem;
    box-shadow: var(--shadow-sm);
    margin-bottom: 2rem;
  }
  .detail-card h2 {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -.3px;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: .75rem;
    flex-wrap: wrap;
  }
  .detail-meta {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 1rem 2rem;
    font-size: .88rem;
    color: var(--muted);
  }
  .detail-meta-item strong {
    display: block;
    font-size: .72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--muted);
    margin-bottom: .25rem;
  }
  .detail-meta-item span {
    color: var(--text);
    font-weight: 500;
  }
  .detail-meta-item span.price {
    color: var(--brand);
    font-weight: 700;
  }
  .detail-desc {
    margin-top: 1.25rem;
    padding-top: 1.25rem;
    border-top: 1px solid var(--border);
    font-size: .9rem;
    color: var(--muted);
    line-height: 1.65;
    white-space: pre-wrap;
  }

  /* ── BOM section header ─────────────────────────────────────────────── */
  .bom-header {
    font-size: .8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: var(--brand);
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: .5rem;
  }
  .bom-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.75rem 2rem;
    box-shadow: var(--shadow-sm);
  }

  /* ── Tree nodes ─────────────────────────────────────────────────────── */
  .tree-root { display: flex; flex-direction: column; gap: 0; }

  .tree-node {
    display: flex;
    align-items: center;
    gap: .6rem;
    padding: .6rem .75rem;
    border-radius: 7px;
    transition: background .13s;
    font-size: .9rem;
    flex-wrap: wrap;
  }
  .tree-node:hover { background: #f4f4f8; }

  /* Depth-tinted left border to show hierarchy level */
  .tree-node { border-left: 3px solid transparent; }
  .tree-depth-0 { border-left-color: var(--brand); background: #f5f3ff; font-weight: 600; }
  .tree-depth-1 { border-left-color: #a5b4fc; margin-left: 1.5rem; }
  .tree-depth-2 { border-left-color: #c7d2fe; margin-left: 3rem; }
  .tree-depth-3 { border-left-color: #e0e7ff; margin-left: 4.5rem; }
  .tree-depth-deep { border-left-color: #e0e7ff; margin-left: 6rem; }

  .tree-connector {
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: .78rem;
    color: #a5b4fc;
    flex-shrink: 0;
    min-width: 1.4rem;
  }
  .tree-name { font-weight: 600; color: var(--text); flex: 1; min-width: 140px; }
  .tree-partno {
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: .78rem;
    color: var(--muted);
    flex-shrink: 0;
  }
  .tree-qty {
    font-size: .82rem;
    font-weight: 700;
    color: #4f46e5;
    background: #ede9fe;
    border-radius: 4px;
    padding: .1rem .4rem;
    flex-shrink: 0;
  }
  .tree-price {
    font-size: .82rem;
    color: var(--brand);
    font-weight: 600;
    flex-shrink: 0;
    margin-left: auto;
  }

  .tree-divider {
    height: 1px;
    background: var(--border);
    margin: .25rem 0;
  }

  /* Missing / cycle warning nodes */
  .tree-warning {
    background: #fef9c3;
    border-left-color: #ca8a04 !important;
    color: #854d0e;
    font-size: .85rem;
  }

  /* Non-assembly message box */
  .no-bom-box {
    text-align: center;
    padding: 2.5rem 1.5rem;
    color: var(--muted);
    font-size: .92rem;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    background: var(--bg);
  }
  .no-bom-box p { margin-top: .4rem; font-size: .85rem; }

  /* ── Responsive ─────────────────────────────────────────────────────── */
  @media (max-width: 640px) {
    .detail-meta { grid-template-columns: 1fr 1fr; }
    .tree-depth-1 { margin-left: .75rem; }
    .tree-depth-2 { margin-left: 1.5rem; }
    .tree-depth-3, .tree-depth-deep { margin-left: 2.25rem; }
    .tree-price { margin-left: 0; }
  }
</style>
"""


# =============================================================================
# [B]  _render_tree() — paste after _build_child_select_options()
# =============================================================================

def _render_tree(product_id: str, qty: int, depth: int, visited: frozenset) -> str:
    """
    Recursively renders a product node and all its children as indented HTML.

    Parameters
    ----------
    product_id : str   — ID of the product to render at this level
    qty        : int   — how many of this product appear in the parent
    depth      : int   — current nesting depth (0 = direct child of root)
    visited    : frozenset[str]  — IDs already on the current path (cycle guard)

    Returns
    -------
    str  — raw HTML string for this node + all descendants

    Design notes
    ------------
    * frozenset (not set) so each recursive branch gets its own snapshot;
      a sibling's path cannot accidentally "block" a cousin.
    * depth > 3 collapses to a single CSS class to keep indentation sane.
    * Missing products show a yellow ⚠ warning node; they do not crash the view.
    """
    # ── Cycle guard ──────────────────────────────────────────────────────
    if product_id in visited:
        depth_cls = f"tree-depth-{depth}" if depth <= 3 else "tree-depth-deep"
        return (
            f'<div class="tree-node {depth_cls} tree-warning">'
            f'  <span class="tree-connector">&#8627;</span>'
            f'  &#9888; Circular reference — <code>{product_id[:8]}…</code>'
            f'</div>'
        )

    # ── Missing product guard ────────────────────────────────────────────
    p = STORE["products"].get(product_id)
    if p is None:
        depth_cls = f"tree-depth-{depth}" if depth <= 3 else "tree-depth-deep"
        return (
            f'<div class="tree-node {depth_cls} tree-warning">'
            f'  <span class="tree-connector">&#8627;</span>'
            f'  &#9888; Missing product — <code>{product_id[:8]}…</code>'
            f'</div>'
        )

    # ── Render this node ─────────────────────────────────────────────────
    depth_cls = f"tree-depth-{depth}" if depth <= 3 else "tree-depth-deep"
    connector = "&#8627;" if depth > 0 else "&#9998;"   # ↳ or ✎
    ptype     = p.get("type", "standalone")
    children  = p.get("children", [])

    qty_html  = f'<span class="tree-qty">&#215;&nbsp;{qty}</span>' if qty > 0 else ""
    node_html = (
        f'<div class="tree-node {depth_cls}">'
        f'  <span class="tree-connector">{connector}</span>'
        f'  <span class="tree-name">{p["name"]}</span>'
        f'  <span class="tree-partno">{p["part_no"]}</span>'
        f'  {_badge(ptype)}'
        f'  {qty_html}'
        f'  <span class="tree-price">&#8377;&nbsp;{p["base_price"]:,.0f}</span>'
        f'</div>'
    )

    # ── Recurse into children ────────────────────────────────────────────
    new_visited = visited | {product_id}
    for child in children:
        node_html += _render_tree(
            child["product_id"],
            child["qty"],
            depth + 1,
            new_visited,
        )

    return node_html


# =============================================================================
# [C]  view_product() route — paste before or after delete_product()
# =============================================================================

# (Import is already in scope; route registered on product_bp)

# @product_bp.route("/view/<id>")           # ← uncomment when pasting into product.py
def view_product(id: str):                   # ← keep this line as-is
    """
    GET /product/view/<id>

    Renders a full-detail page for any product.
    For assemblies, shows a recursive indented BOM tree.
    Non-assemblies get a polite "no components" notice.
    Redirects with an error if the product ID is unknown.
    """
    ensure_demo_products()

    product = STORE["products"].get(id)
    if not product:
        return redirect(url_for(
            "product.list_products",
            msg="Product not found.",
            type="error",
        ))

    list_url = url_for("product.list_products")
    ptype    = product.get("type", "standalone")
    children = product.get("children", [])

    # ── Build BOM section ─────────────────────────────────────────────
    if ptype == "assembly" and children:
        tree_nodes = ""
        for child in children:
            tree_nodes += _render_tree(
                child["product_id"],
                child["qty"],
                depth=0,
                visited=frozenset([id]),  # seed with root so root can't appear as child
            )
            tree_nodes += '<div class="tree-divider"></div>'

        # Trim the trailing divider
        last_div = '<div class="tree-divider"></div>'
        if tree_nodes.endswith(last_div):
            tree_nodes = tree_nodes[: -len(last_div)]

        child_count = len(children)
        bom_html = f"""
        <div class="bom-section">
          <div class="bom-header">
            &#9881;&nbsp; Bill of Materials
            <span style="font-weight:500;color:var(--muted);font-size:.78rem;margin-left:.25rem;">
              — {child_count} direct component{"s" if child_count != 1 else ""}
            </span>
          </div>
          <div class="tree-root">
            {tree_nodes}
          </div>
        </div>
        """

    elif ptype == "assembly" and not children:
        # Assembly exists but has no children yet
        bom_html = """
        <div class="no-bom-box">
          <div style="font-size:1.8rem;">&#128230;</div>
          <strong>Empty Assembly</strong>
          <p>This assembly has no child components defined yet.</p>
        </div>
        """
    else:
        type_label = ptype.capitalize()
        bom_html = f"""
        <div class="no-bom-box">
          <div style="font-size:1.8rem;">&#128269;</div>
          <strong>{type_label} product — no sub-components</strong>
          <p>Only <em>Assembly</em> products have a Bill of Materials.
             This product is a leaf node and can be used as a component in assemblies.</p>
        </div>
        """

    # ── Description block ─────────────────────────────────────────────
    desc = (product.get("description") or "").strip()
    desc_html = f'<div class="detail-desc">{desc}</div>' if desc else ""

    template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{product['name']} &#8212; QMS</title>
      {BASE_STYLES}
      {PRODUCT_STYLES}
      {VIEW_STYLES}
    </head>
    <body>
      {_nav()}
      <main>
        <!-- Page header -->
        <div class="page-top">
          <h1>Product <span>Detail</span></h1>
          <a href="{list_url}" class="btn btn-ghost">&#8592; Back to Catalog</a>
        </div>

        <!-- Product header card -->
        <div class="detail-card">
          <h2>
            {product['name']}
            {_badge(ptype)}
          </h2>
          <div class="detail-meta">
            <div class="detail-meta-item">
              <strong>Part No.</strong>
              <span style="font-family:'SFMono-Regular',Consolas,monospace;font-size:.88rem;">
                {product['part_no']}
              </span>
            </div>
            <div class="detail-meta-item">
              <strong>Unit</strong>
              <span>{product['unit']}</span>
            </div>
            <div class="detail-meta-item">
              <strong>Base Price</strong>
              <span class="price">&#8377; {product['base_price']:,.0f}</span>
            </div>
            <div class="detail-meta-item">
              <strong>Type</strong>
              <span>{ptype.capitalize()}</span>
            </div>
          </div>
          {desc_html}
        </div>

        <!-- BOM / tree section -->
        {bom_html}

        <footer style="margin-top:2.5rem;">
          <p>QMS Platform &nbsp;&#183;&nbsp; Product Module &nbsp;&#183;&nbsp; In-memory store</p>
        </footer>
      </main>
    </body>
    </html>
    """
    return render_template_string(template)


# =============================================================================
# [D]  list_products() — PATCH the action <td> cell only
#
# In the existing list_products() route, find this block inside the `rows +=`
# f-string (the last <td> of each row):
#
#   <td>
#     <a href="{delete_url}"
#        class="btn-delete"
#        onclick="return confirm('Delete {p['name']}? This cannot be undone.')">
#       Delete
#     </a>
#   </td>
#
# Replace it with the version below. The only additions are:
#   • view_url computed from url_for("product.view_product", id=pid)
#   • a [ View ] anchor shown only for assembly rows
# =============================================================================

# ── Compute view_url alongside delete_url (add this line near delete_url) ──
# view_url   = url_for("product.view_product", id=pid)   # ← ADD THIS

# ── Replacement <td> (paste in place of the old action <td>) ──────────────
_PATCH_ACTION_TD = '''
              <td style="white-space:nowrap;display:flex;gap:.4rem;align-items:center;">
                {view_btn}
                <a href="{delete_url}"
                   class="btn-delete"
                   onclick="return confirm('Delete {product_name}? This cannot be undone.')">
                  Delete
                </a>
              </td>
'''

# view_btn is conditionally rendered:
#   if ptype == "assembly":
#       view_btn = f'<a href="{view_url}" class="btn btn-ghost" ..>View</a>'
#   else:
#       view_btn = ""
#
# Full replacement snippet ready to paste:

_PATCH_TBODY_SNIPPET = r"""
            view_url   = url_for("product.view_product", id=pid)   # NEW

            view_btn = (
                f'<a href="{view_url}" '
                f'   class="btn btn-ghost" '
                f'   style="font-size:.78rem;padding:.28rem .65rem;" '
                f'   title="Inspect assembly BOM">'
                f'  &#128269; View'
                f'</a>'
            ) if ptype == "assembly" else ""

            # Then in the rows += f-string, replace the last <td> with:
            #
            # <td style="white-space:nowrap;display:flex;gap:.4rem;align-items:center;">
            #   {view_btn}
            #   <a href="{delete_url}"
            #      class="btn-delete"
            #      onclick="return confirm('Delete {p['name']}? This cannot be undone.')">
            #     Delete
            #   </a>
            # </td>
"""

"""
=============================================================================
ROUTE REGISTRATION  (in product_bp, already at top of file — no change needed
                      other than decorating view_product)
=============================================================================

In the view_product function above, uncomment:

    @product_bp.route("/view/<id>")

That single decorator is all that is needed. Flask auto-registers it on
product_bp, which is already mounted at /product in app.py.

Final URL:   GET /product/view/<product-id>
=============================================================================
"""