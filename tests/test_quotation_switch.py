"""
The quotation source FOLLOWS the catalogue switch — 12 September 2026.

CLIENT_CHANGES.md §0, the twenty-eighth block. The spec-library picker the
twenty-seventh block put on `/quotation/create` is temporary: while
`"product"` is in `auth.HIDDEN_BLUEPRINTS` a quotation is written from the
specification library through `specpick.py`; the moment the switch is emptied
the page is the **product picker exactly as it stood at `1d7725a`** — the
same bytes.

That last claim is the one that matters and it is measured, not asserted:
`OFF_WHOLE` / `OFF_LEN` below were captured by running this very fixture
against a `git worktree` of `1d7725a`, whose `quotation.py` predates both the
spec picker and the switch. Nothing in that checkout knows about
`HIDDEN_BLUEPRINTS`, `specpick.py` or the eight seams, so a match here says
the restored product path reproduces the old page byte for byte — including
the JavaScript, which is where a hand-restored template would have drifted.

Three further guarantees, each a test:

* a form opened in one mode and submitted after a flip is REFUSED with a
  message, never saved half-and-half — the payload's own shape (`pid` against
  `sid`) is the tell, because the page carries no mode field (it could not:
  the OFF page must stay byte-identical to `1d7725a`'s, which had none);
* a quotation created in either mode views, prints and raises a PI and a TI
  with the switch in either state — the line-item shape is one shape;
* `quotation.py` reads the switch through the one accessor and reaches
  `specpick.py` only inside the three unfrozen functions.
"""

import datetime as _dt
import hashlib
import json
import re

import pytest

import branding as B
import quotation as Q
import settings as settings_mod
from store import STORE

# Reused rather than copied: the specimen company identity, forced on and put
# back afterwards. It is in `test_print_golden.py` at `1d7725a` too, which is
# what lets the capture run there unchanged.
from test_print_golden import pinned_identity  # noqa: F401


# ── the fixed world ─────────────────────────────────────────────────────────

class _FixedToday:
    """`datetime.date` with today nailed down. Only `today()` is ever called."""

    @staticmethod
    def today():
        return _dt.date(2026, 9, 12)


def _set_hidden(names: set):
    """
    Put the switch in a known state and return what to restore.

    `getattr` because the capture runs this fixture at `1d7725a`, where the
    set does not exist — there the page IS the product picker and there is
    nothing to switch.
    """
    import auth
    current = getattr(auth, "HIDDEN_BLUEPRINTS", None)
    if current is None:
        return None
    saved = set(current)
    current.clear()
    current.update(names)
    return saved


def _restore_hidden(saved):
    import auth
    if saved is None:
        return
    auth.HIDDEN_BLUEPRINTS.clear()
    auth.HIDDEN_BLUEPRINTS.update(saved)


@pytest.fixture()
def fixed_world(client, pinned_identity, monkeypatch):
    """
    `/quotation/create` with everything that moves on its own held still:
    today's date, the catalogue (cleared and re-seeded so the twelve fixed
    UUIDs are all it holds), the address book, and the quotation counter
    (`client` already clears the register, so the next ref is `QT-0001`).
    """
    import address
    import product

    monkeypatch.setattr(Q, "_date", _FixedToday)

    saved_products = dict(STORE["products"])
    saved_seed = STORE.get("_seeded")
    STORE["products"].clear()
    STORE["_seeded"] = False
    product.ensure_demo_products()

    saved_addresses = dict(STORE["addresses"])
    saved_addr_seed = STORE.get("_addr_seeded")
    STORE["addresses"].clear()
    STORE["_addr_seeded"] = False
    address.ensure_demo_addresses()

    yield

    STORE["products"].clear()
    STORE["products"].update(saved_products)
    STORE["_seeded"] = saved_seed
    STORE["addresses"].clear()
    STORE["addresses"].update(saved_addresses)
    STORE["_addr_seeded"] = saved_addr_seed


@pytest.fixture()
def switch_off(fixed_world):
    """The catalogue un-hidden: the product picker."""
    saved = _set_hidden(set())
    try:
        yield
    finally:
        _restore_hidden(saved)


@pytest.fixture()
def switch_on(fixed_world):
    """The catalogue hidden: the library picker. The shipped state."""
    saved = _set_hidden({"product"})
    try:
        yield
    finally:
        _restore_hidden(saved)


# ── the golden ──────────────────────────────────────────────────────────────

# Captured 12 September 2026 by running `test_the_off_page_is_byte_identical_
# to_1d7725a` in a `git worktree` of `1d7725a`, with this fixture. The page
# there has no switch and no seams; it is the product picker and nothing else.
OFF_WHOLE = "b467ca97ab34d077"
OFF_LEN = 87068

# The page split on its structural markers, so a failure names which part
# moved: the chrome, the item section, the picker's script, or the demo fill.
OFF_MARKERS = [
    ("head",     "<head>"),
    ("form",     '<form method="POST" action="" id="qf">'),
    ("items",    "SECTION 3: PRODUCTS"),
    ("tax",      "SECTION 4: TAX / DUTY"),
    ("script",   "<script>\n/* ═══"),
    ("picker",   "function addProduct()"),
    ("render",   "function renderRoot(item, idx)"),
    ("mutation", "function onRootFieldChange(el)"),
    ("demo",     "function fillDemoData()"),
    ("guard",    "/* ═══ FORM GUARD"),
]
OFF_BLOCKS = {"head":     "a7fcb956a04f035f",
              "form":     "370e5e115dc4c883",
              "items":    "374b85b7f0fd495d",
              "tax":      "ddb32a58ad86df59",
              "script":   "03c7686e45d02118",
              "picker":   "2a8f31b81350107f",
              "render":   "3c15e438559e9795",
              "mutation": "488e37368cb2f88e",
              "demo":     "32d2683a459f9cc9",
              "guard":    "409c1741d8d0583c"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _blocks(html: str) -> dict:
    cuts = []
    for name, marker in OFF_MARKERS:
        at = html.find(marker)
        assert at >= 0, f"the page no longer carries the {name} marker {marker!r}"
        cuts.append((name, at))
    out = {}
    for i, (name, at) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else len(html)
        out[name] = _sha(html[at:end])
    return out


def test_the_off_page_is_byte_identical_to_1d7725a(client, switch_off):
    """
    With the switch emptied, `/quotation/create` is the page `1d7725a`
    rendered — measured against a digest taken from that commit's own code.
    """
    r = client.get("/quotation/create")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    got = _blocks(html)
    moved = [n for n in OFF_BLOCKS if got[n] != OFF_BLOCKS[n]]
    assert not moved, (
        f"the OFF-state quotation form moved in these blocks: {moved}. "
        f"Expected {OFF_BLOCKS}, got {got}. Whole page {OFF_WHOLE} -> "
        f"{_sha(html)}, {OFF_LEN} -> {len(html)} bytes.")
    assert (_sha(html), len(html)) == (OFF_WHOLE, OFF_LEN), (
        f"the OFF-state quotation form changed outside every block: "
        f"sha {OFF_WHOLE} -> {_sha(html)}, bytes {OFF_LEN} -> {len(html)}")


def test_the_golden_is_hashing_the_product_picker(client, switch_off):
    """The control: a digest passes just as well against a redirect."""
    html = client.get("/quotation/create").get_data(as_text=True)
    assert 'id="picker-prod"' in html and 'id="comp-opts-tpl"' in html
    assert "— select product —" in html
    assert 'id="picker-spec"' not in html
    assert 'value="2026-09-12"' in html, "today's date was not pinned"
    assert "QT-0001" in html, "the quotation counter was not pinned"
    embedded = json.loads(re.search(
        r'<script type="application/json" id="catalog-data">(.*?)</script>',
        html, re.S).group(1))
    assert set(embedded) == set(STORE["products"])
    assert "children" in next(iter(embedded.values()))


# ── the two modes ───────────────────────────────────────────────────────────

PRODUCT_PID = "a1000001-beef-4000-8000-000000000001"


def _product_pick(pid=PRODUCT_PID, qty=2):
    return {"pid": pid, "qty": qty, "price": 1000.0, "show_price": True,
            "expanded": False, "components": []}


def _library_pick(qty=2, price=500.0):
    import specpick
    specpick.ensure_seeded()
    sid, s = next((sid, s) for sid, s in STORE["specs"].items()
                  if s["variants"][0].get("default_supply_base_rate") is not None)
    return {"sid": sid, "vidx": 0, "leg": "supply", "qty": qty,
            "price": price, "show_price": True}


def _post(client, sel, **extra):
    data = {"account_name": "Switch Customer", "qtn_date": "2026-09-12",
            "tax_type": "cgst_sgst", "tax_cgst": "9", "tax_sgst": "9",
            "tax_igst": "18", "tax_vat": "5",
            "selections_json": json.dumps(sel)}
    data.update(extra)
    return client.post("/quotation/create", data=data)


def _error_of(response) -> str:
    m = re.search(r'alert-error">&#10007; (.*?)</div>',
                  response.get_data(as_text=True), re.S)
    assert m, "the POST did not re-render with an error"
    return m.group(1)


def test_the_shipped_state_is_the_library_picker(client, switch_on):
    html = client.get("/quotation/create").get_data(as_text=True)
    assert 'id="picker-spec"' in html
    assert 'id="picker-prod"' not in html and "comp-opts-tpl" not in html
    embedded = json.loads(re.search(
        r'<script type="application/json" id="catalog-data">(.*?)</script>',
        html, re.S).group(1))
    assert set(embedded) == set(STORE["specs"])


def test_off_a_product_pick_is_saved_as_it_was_at_1d7725a(client, switch_off):
    r = _post(client, [_product_pick()])
    assert r.status_code == 302, _error_of(r)
    q = list(STORE["quotations"].values())[-1]
    p = STORE["products"][PRODUCT_PID]
    row = q["line_items"][0]
    assert row["name"] == p["name"] and row["part_no"] == p["part_no"]
    assert row["qty"] == 2.0 and row["price"] == 1000.0 and row["total"] == 2000.0
    assert q["selections"][0]["pid"] == PRODUCT_PID


def test_off_the_product_path_returns_the_same_three_tuple(client, switch_off):
    lines, err, rates = Q._process_selections([_product_pick()])
    assert err == "" and rates == [] and len(lines) == 1
    assert lines[0]["part_no"] == STORE["products"][PRODUCT_PID]["part_no"]


def test_off_a_missing_product_is_refused_as_it_was(client, switch_off):
    before = len(STORE["quotations"])
    r = _post(client, [_product_pick(pid="not-a-product")])
    assert r.status_code == 200
    assert "Product no longer exists" in _error_of(r)
    assert len(STORE["quotations"]) == before


@pytest.mark.parametrize("raw", ["not json", "{}", '"str"', "[1, 2]"])
def test_off_a_malformed_payload_is_refused_in_the_product_words(client, switch_off, raw):
    before = len(STORE["quotations"])
    r = client.post("/quotation/create", data={
        "account_name": "X", "qtn_date": "2026-09-12", "tax_type": "cgst_sgst",
        "tax_cgst": "9", "tax_sgst": "9", "tax_igst": "18", "tax_vat": "5",
        "selections_json": raw})
    assert r.status_code == 200
    assert "product" in _error_of(r).lower()
    assert len(STORE["quotations"]) == before


# ── a form opened in one mode and submitted after a flip ───────────────────

def test_a_library_form_posted_after_the_switch_is_emptied_is_refused(client, switch_on):
    """Opened ON (library picks), flipped OFF, posted: refused, nothing saved."""
    sel = [_library_pick()]
    before = len(STORE["quotations"])
    saved = _set_hidden(set())
    try:
        r = _post(client, sel)
    finally:
        _restore_hidden(saved)
    assert r.status_code == 200
    err = _error_of(r)
    assert "opened while the quotation picker read the specification library" in err
    assert "Nothing was saved" in err
    assert len(STORE["quotations"]) == before


def test_a_product_form_posted_after_the_catalogue_is_hidden_is_refused(client, switch_off):
    """Opened OFF (product picks), flipped ON, posted: refused, nothing saved."""
    sel = [_product_pick()]
    before = len(STORE["quotations"])
    saved = _set_hidden({"product"})
    try:
        r = _post(client, sel)
    finally:
        _restore_hidden(saved)
    assert r.status_code == 200
    err = _error_of(r)
    assert "opened while the quotation picker read the product catalogue" in err
    assert "Nothing was saved" in err
    assert len(STORE["quotations"]) == before


def test_a_mixed_payload_is_refused_in_either_mode(client, switch_on):
    """Half-and-half is exactly what must never be saved."""
    mixed = [_library_pick(), _product_pick()]
    before = len(STORE["quotations"])
    assert _post(client, mixed).status_code == 200
    saved = _set_hidden(set())
    try:
        assert _post(client, mixed).status_code == 200
    finally:
        _restore_hidden(saved)
    assert len(STORE["quotations"]) == before


# ── both kinds of quotation, under both switch states ───────────────────────

def _raise_pi_and_ti(client, q):
    r = client.post(f"/proforma/from/{q['id']}",
                    data={"date": "2026-09-12", "advance_pct": "100",
                          "validity_days": "15"})
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    pi = list(STORE["proformas"].values())[-1]
    assert pi["line_items"] == q["line_items"]
    r = client.post(f"/invoice/from/{pi['id']}",
                    data={"date": "2026-09-12", "place_of_supply": "Maharashtra",
                          "advance_received": "0"})
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    ti = list(STORE["invoices"].values())[-1]
    assert ti["line_items"] == q["line_items"]
    return pi, ti


@pytest.mark.parametrize("view_state", ["off", "on"])
def test_quotations_from_either_mode_view_print_and_raise_pi_ti_under_either_state(
        client, fixed_world, view_state):
    # one written from the catalogue, one from the library
    _restore_hidden(_set_hidden(set()))
    saved = _set_hidden(set())
    try:
        assert _post(client, [_product_pick()]).status_code == 302
        q_product = list(STORE["quotations"].values())[-1]
    finally:
        _restore_hidden(saved)
    saved = _set_hidden({"product"})
    try:
        client.get("/quotation/create")   # seeds the library
        assert _post(client, [_library_pick()]).status_code == 302
        q_library = list(STORE["quotations"].values())[-1]
    finally:
        _restore_hidden(saved)

    saved = _set_hidden(set() if view_state == "off" else {"product"})
    try:
        for q in (q_product, q_library):
            html = client.get(f"/quotation/view/{q['id']}").get_data(as_text=True)
            assert q["ref"] in html
            for row in q["line_items"]:
                assert row["part_no"] in html
            pi, ti = _raise_pi_and_ti(client, q)
            assert client.get(f"/proforma/view/{pi['id']}").status_code == 200
            assert client.get(f"/invoice/view/{ti['id']}").status_code == 200
    finally:
        _restore_hidden(saved)


# ── the shape of the change ─────────────────────────────────────────────────

def test_quotation_reaches_specpick_only_inside_the_three_functions():
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "quotation.py").read_text(encoding="utf8")
    tree = ast.parse(src)
    # no module-level import of specpick or auth: the freeze permits none
    top = {n.names[0].name.split(".")[0] for n in tree.body if isinstance(n, ast.Import)}
    top |= {n.module.split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom) and n.module}
    assert "specpick" not in top and "auth" not in top
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name in ("_product_catalog_json", "_process_selections", "create_quotation")}
    assert len(funcs) == 3
    for name, node in funcs.items():
        body = ast.get_source_segment(src, node)
        assert 'auth.blueprint_hidden("product")' in body, f"{name} does not read the switch"
        assert "specpick" in body, f"{name} does not reach the leaf"
    # and nothing else in the file names the leaf
    outside = src
    for node in funcs.values():
        outside = outside.replace(ast.get_source_segment(src, node), "")
    assert "specpick" not in outside


def test_the_eight_seams_agree_between_the_leaf_and_the_template():
    import pathlib
    import specpick
    assert set(specpick.page_pieces({})) == set(specpick.SEAMS)
    src = (pathlib.Path(__file__).resolve().parent.parent / "quotation.py").read_text(encoding="utf8")
    for seam in specpick.SEAMS:
        assert src.count("{" + seam + "}") == 1, f"seam {seam} is not exactly one placeholder"
        assert f'"{seam}":' in src, f"the product mode does not fill seam {seam}"


def test_specpick_is_a_leaf():
    import ast
    import pathlib
    from test_import_directions import imports_of
    ours = {m.stem for m in (pathlib.Path(__file__).resolve().parent.parent).glob("*.py")}
    assert imports_of("specpick", top_level_only=True) & ours == {"store", "pipeline"}
    assert imports_of("specpick") & ours == {"store", "pipeline", "spec"}
