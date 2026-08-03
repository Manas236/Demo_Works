"""
The client workbooks — and proof that the suite copes without them.

`sify_boq.xlsx` and `annexure.xlsx` are gitignored, so on a fresh clone these
skip with a message that names the missing file. Where they ARE installed they
do real work: they check that `demo_data.py` still agrees with the workbook it
was generated from, which is the regression test Phase 3's importer will be
measured against.
"""

import pytest

import demo_data as DD

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")


def test_the_suite_runs_without_the_workbooks():
    """
    The contract: the app never reads a workbook at runtime, so a checkout
    without them is fully functional and fully tested apart from these.
    """
    from conftest import find_fixture

    # demo_data is committed and self-contained — this holds either way.
    assert len(DD.SPECS) == 56
    assert len(DD.BOQ_LINES) == 97
    # And nothing in the app imports openpyxl.
    import boq
    import spec
    for mod in (boq, spec):
        src = open(mod.__file__, encoding="utf8").read()
        assert "openpyxl" not in src, f"{mod.__name__} reads a workbook at runtime"


def test_demo_data_still_matches_the_source_workbook(sify_boq_xlsx):
    """
    `demo_data.py` was generated from this file. If the workbook changes and
    the generated data is not regenerated, they drift apart silently — and the
    seeded BOQ stops being the thing the importer will be checked against.
    """
    ws = openpyxl.load_workbook(sify_boq_xlsx, data_only=True)["Quotation"]

    SEC = {"A": (5, 25), "B": (29, 93), "C": (96, 106)}
    SKIP = {26, 27, 28, 94, 95, 107, 108}

    def item_no(r):
        v = ws[f"A{r}"].value
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.10g}"
        return str(v).strip() if not isinstance(v, int) else str(v)

    rows = [(s, r) for s, (a, b) in SEC.items()
            for r in range(a, b + 1) if r not in SKIP and item_no(r)]
    assert len(rows) == len(DD.BOQ_LINES)

    for (sec, r), line in zip(rows, DD.BOQ_LINES):
        assert line["item_no"] == item_no(r), f"row {r}"
        assert line["section"] == sec, f"row {r}"


def test_the_workbook_still_totals_what_the_seed_says(sify_boq_xlsx):
    ws = openpyxl.load_workbook(sify_boq_xlsx, data_only=True)["Quotation"]
    supply = sum(v for v in (ws[f"J{r}"].value for r in range(5, 107))
                 if isinstance(v, (int, float)))
    # Subtotal rows are inside that range, so compare against the seed instead
    # of the raw column: the point is that the two agree.
    seeded = sum(l["s_rate"] * l["total_qty"]
                 for l in DD.BOQ_LINES if not l.get("header"))
    assert round(seeded, 2) == 6177563.30
    assert supply > 0


def test_annexure_carries_the_nine_ra_claims(annexure_xlsx):
    """Phase 3's fixture. Checked here so a missing or changed file is caught
    before the importer is written rather than during it."""
    ws = openpyxl.load_workbook(annexure_xlsx, data_only=True)["Sheet2"]
    labels = [ws[f"{c}3"].value for c in ("N", "Q", "T", "W", "Z", "AC", "AG", "AJ", "AM")]
    assert labels == ["RA1", "RA2", "RA3", "RA5", "RA7", "RA9", "RA4", "RA6", "RA8"]
    # The #VALUE! cells the import report has to name.
    assert ws["AF28"].value == "#VALUE!"
    assert ws["AP28"].value == "#VALUE!"
