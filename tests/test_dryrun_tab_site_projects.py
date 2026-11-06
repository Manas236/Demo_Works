"""
`tools/dryrun_tab_site_projects.py` — READ-ONLY, and held to it.

CLIENT_CHANGES.md §0 sixty-eighth block. The script is for samruddhi-prod and
the agent that wrote it never ran it there. These tests run it here on a fake
loader (no MySQL) and check two things: it says the right thing, and it can
write nothing — no write SQL, no `db.init`/`db.sync`, no `app`, no write mode.
"""

import ast
import pathlib
import sys

import pytest

from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "dryrun_tab_site_projects.py"
sys.path.insert(0, str(REPO / "tools"))
import dryrun_tab_site_projects as T  # noqa: E402

_OWNED = T.COLLECTIONS


def test_the_script_cannot_write():
    src = TOOL.read_text(encoding="utf8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    body = code.split('"""', 2)[2]          # past the module docstring
    for banned in ("INSERT", "UPDATE ", "DELETE", "REPLACE", "CREATE", "DROP",
                   "ALTER", "TRUNCATE", "db.sync", "db.init", "db.reset",
                   "load_into", "from app", "import app", ".commit(",
                   "--write"):
        assert banned not in body, f"{banned!r} in the read-only script"
    tree = ast.parse(src)
    sql = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and n.value.lstrip().startswith(("SELECT ", "SET ", "START "))]
    assert len(sql) == 3 and all(s.lstrip().startswith(
        ("SELECT", "SET SESSION TRANSACTION READ ONLY",
         "START TRANSACTION READ ONLY")) for s in sql)


def test_dry_run_is_required_and_the_only_mode():
    with pytest.raises(SystemExit):
        T.main([], loader=lambda s: None)
    with pytest.raises(SystemExit):
        T.main(["--dry-run", "--write"], loader=lambda s: None)


@pytest.fixture()
def world(client):
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["addresses"]["jam"] = {"id": "jam", "label": "JAMNAGAR REFINERY",
                                 "type": "site"}
    STORE["addresses"]["gov"] = {"id": "gov", "label": "GOVANDI", "type": "site"}
    for pid, name, aid in (("p-jam", "RIL Jamnagar", "jam"),
                           ("p-shed", "RIL Jamnagar Shed", "jam")):
        STORE["projects"][pid] = {"id": pid, "name": name,
                                  "site_address_id": aid}
    STORE["pay_imports"]["imp"] = {
        "id": "imp", "status": "committed", "month": "2026-10",
        "filename": "OCT.xlsx",
        "rows": [{"name": "PUSHKAR MISHRA", "site": "RIL JAMNAGAR SHED",
                  "days": [{"day": 1}, {"day": 2}]},
                 {"name": "NIRAJ", "site": "RIL JAMNAGAR",
                  "days": [{"day": 1}]}]}
    STORE["settings"]["pay_import_sites"] = {"sites": {
        "ril jamnagar shed": {"site": "jam", "project": "p-shed"}}}
    def mark(mid, name, eid, day, batch="imp", site="JAMNAGAR REFINERY"):
        STORE["attendance"][mid] = {
            "id": mid, "employee_id": eid, "employee_name": name,
            "date": f"2026-10-{day:02d}", "status": "present",
            "site": site, "site_address_id": "jam", "project_id": "",
            "import_batch": batch}
    mark("a", "PUSHKAR MISHRA", "pk", 1)
    mark("b", "PUSHKAR MISHRA", "pk", 2)
    mark("c", "NIRAJ", "nk", 1)
    mark("d", "GUDDU", "gk", 5, batch="")
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def test_it_reports_what_each_marking_would_get(world, capsys):
    before = {k: repr(STORE[k]) for k in _OWNED}
    assert T.main(["--dry-run", "--expect", "4"], loader=lambda s: None) == 0
    out = capsys.readouterr().out
    assert "DRY RUN — nothing is written" in out
    assert "found" not in out.split("SUMMARY")[0], "4 expected, 4 found"
    assert "SINGLE-TAB parser" in out, "an import from before the block is named"
    p = T.plan("2026-10", "jamnagar")
    got = {(ln["worker"], ln["date"]): (ln["outcome"].split(" (")[0], ln["project"])
           for ln in p["lines"]}
    assert got[("PUSHKAR MISHRA", "2026-10-01")] == ("SAVED MAPPING", "RIL Jamnagar Shed")
    assert got[("NIRAJ", "2026-10-01")] == (
        "ASK ONCE FOR THIS SITE NAME", "RIL Jamnagar | RIL Jamnagar Shed")
    assert got[("GUDDU", "2026-10-05")][0].startswith("NO SITE NAME")
    assert {k: repr(STORE[k]) for k in _OWNED} == before, "nothing changed"
