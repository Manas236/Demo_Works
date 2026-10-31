"""
`tools/scan_paise.py` scans EVERY collection that holds money — §0
sixty-fourth block, Part 6 (31 Oct 2026). Before this pass it skipped the
product inquiry, the spec library, measurement sheets, challans, pay entries,
employees and the product catalogue.

The guard is a closed classification: every collection in `store.STORE` is
either scanned or named here as holding no money, so a NEW collection fails
this file until somebody decides which it is.
"""

import importlib.util
import pathlib

import store

NOT_MONEY = {
    "projects": "a name, a status and dates — every figure on the P&L is derived",
    "attendance": "statuses and hours; the cost is derived from the employee's day rate",
    "pay_imports": "cell values read from a workbook, staged",
    "attachments": "file metadata",
    "boq_imports": "staged cell values — nothing is a BOQ until saved",
    "wo_imports": "staged cell values",
    "import_layouts": "a column mapping",
    "doc_imports": "staged cell values",
    "doc_import_layouts": "a column mapping",
    "line_image_library": "a picture id and a name",
    "addresses": "an address book",
    "gst_cache": "registration details",
    "users": "accounts",
    "roles": "permission bundles",
    "settings": "company details and series floors",
}


def _tool():
    p = pathlib.Path(__file__).resolve().parent.parent / "tools" / "scan_paise.py"
    spec = importlib.util.spec_from_file_location("scan_paise_cov", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_collection_is_scanned_or_named_as_holding_no_money():
    scanned = {c for c, _l, _k in _tool().COLLECTIONS}
    # `_seeded`-style keys are seeder flags, not collections.
    every = {k for k in store.STORE if not k.startswith("_")}
    assert not (scanned & set(NOT_MONEY)), "a collection is listed both ways"
    missing = every - scanned - set(NOT_MONEY)
    assert not missing, f"classify these for scan_paise.py: {sorted(missing)}"


def test_the_collections_this_pass_added_are_actually_read():
    m = _tool()
    fake = {
        "purchase_orders": {"a": {"ref": "SF/PI/1", "items": [{"rate": 10.125}]}},
        "specs": {"b": {"code": "SP-1", "variants": [{"supply_rate": 1.005}]}},
        "measurements": {"c": {"ref": "MS-1", "rows": [{"amount": 2.333}]}},
        "delivery_challans": {"d": {"ref": "DC-1", "items": [{"rate": 3.001}]}},
        "pay_entries": {"e": {"id": "PE-1", "amount": 99.999}},
        "employees": {"f": {"name": "Ravi", "day_rate": 650.555}},
        "products": {"g": {"part_no": "P-1", "price": 1.111}},
    }
    found = {label for label, _n, _bad in m.scan(fake)}
    assert found == {"Product Inquiry", "Specification", "Measurement Sheet",
                     "Delivery Challan", "Pay Entry", "Employee", "Product"}


def test_a_percentage_is_not_money():
    m = _tool()
    fake = {"specs": {"b": {"code": "SP-1", "variants": [{"supply_gst_rate": 2.125}]}}}
    assert m.scan(fake) == []
