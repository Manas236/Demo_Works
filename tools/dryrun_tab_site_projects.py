#!/usr/bin/env python
"""
dryrun_tab_site_projects.py — what the unassigned markings of one month would
get under the one-tab-per-site rule. READ-ONLY. There is no write mode.
=============================================================================

CLIENT_CHANGES.md §0 **sixty-eighth** block (6 November 2026). Written for
samruddhi-prod, for the question *"what would the 88 unassigned October
Jamnagar markings get?"* — and NOT run by the agent that wrote it.

    python tools/dryrun_tab_site_projects.py --dry-run
    python tools/dryrun_tab_site_projects.py --dry-run --month 2026-10 --site jamnagar

⚠ **IT WRITES NOTHING, ANYWHERE.** It opens its own MySQL connection, puts
  the session in a READ ONLY transaction, issues `SELECT` and nothing else,
  and rolls back. It never calls `db.init()` (which creates tables) or
  `db.sync()` (which writes), and never imports `app` (which boots
  persistence and seeds defaults). What it loads goes into this process's
  memory and dies with it. `--dry-run` is the ONLY mode; there is no
  `--write`, and `tests/test_dryrun_tab_site_projects.py` fails if a write
  statement or a write call ever appears in this file.

What it reads, and the rule it applies
--------------------------------------
For every marking in the month that is UNASSIGNED — no `project_id`, not
marked overhead — and whose site (the marking's label, or its address's label)
contains `--site` (case ignored):

1. **Its import.** The `pay_imports` record named by the marking's
   `import_batch`, and the sheet row(s) of that person (`payimport.norm()`,
   the import's exact name rule) carrying that day. The row's SITE string is
   the sheet's site name for that day.
2. **The new rule for a day WITH a site name**: the saved mapping for that
   name (`payimport.saved_for()`), if it answers for the marking's own
   address; else the projects at the marking's address
   (`attendance.projects_on_site()`): one → that project; two or more →
   **ASK**, once per site name, the candidates printed; none → stays
   Unassigned.
3. **A day with NO site name** (no import, no matching row, a blank SITE):
   the last-month default (`attendance.project_last_month()` — unanimous
   only), else stays Unassigned.

⚠ **An import staged before the sixty-eighth block was read by the
  SINGLE-TAB parser**: only the first tab carrying a NAME header was read, so
  its stored rows are that tab's rows and nothing else. The script says so for
  each such import. Days the client recorded on other tabs were never
  imported and are not among these markings at all.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from store import STORE                     # noqa: E402

# Only what the rule reads. Nothing else is loaded.
COLLECTIONS = ("attendance", "pay_imports", "projects", "addresses",
               "employees", "settings")


def load_readonly(store: dict) -> None:
    """
    Fill `store` from MySQL with SELECT only, in a READ ONLY transaction, then
    roll back. The connection settings are `db.CONFIG`'s (it reads .env);
    nothing in `db` that writes is called.
    """
    import pymysql
    import db

    cfg = db.CONFIG
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"],
                           charset="utf8mb4", autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("START TRANSACTION READ ONLY")
            for coll in COLLECTIONS:
                target = store.setdefault(coll, {})
                target.clear()
                cur.execute(f"SELECT `id`, `data` FROM `{coll}`")
                for rid, raw in cur.fetchall():
                    target[rid] = (json.loads(raw)
                                   if isinstance(raw, (str, bytes)) else raw)
    finally:
        conn.rollback()
        conn.close()


def _s(v) -> str:
    return str(v or "").strip()


def plan(month: str, site_word: str) -> dict:
    """Every unassigned marking in scope, with what the new rule would give it."""
    import attendance as AT
    import employee as EMP
    import payimport as PI

    addresses = STORE.get("addresses") or {}
    word = site_word.lower()

    def site_text(m):
        aid = _s(m.get(EMP.SITE_ADDRESS_FIELD))
        return " ".join([_s(m.get("site")),
                         _s((addresses.get(aid) or {}).get("label"))]).lower()

    scope = [m for m in (STORE.get("attendance") or {}).values()
             if _s(m.get("date")).startswith(month + "-")
             and not _s(m.get("project_id"))
             and not AT.is_overhead(m)
             and word in site_text(m)]
    scope.sort(key=lambda m: (_s(m.get("employee_name")).lower(), _s(m.get("date"))))

    imports = STORE.get("pay_imports") or {}
    out, single_tab = [], set()
    for m in scope:
        batch = _s(m.get("import_batch"))
        rec = imports.get(batch) or {}
        if rec and "tabs" not in rec:
            single_tab.add(batch)
        day = int(_s(m.get("date"))[8:10] or 0)
        key = PI.norm(m.get("employee_name"))
        rows = [r for r in (rec.get("rows") or [])
                if PI.norm(r.get("name")) == key
                and any(d.get("day") == day for d in r.get("days") or [])]
        sheet_site = _s(rows[0].get("site")) if len(rows) == 1 else ""
        tab = _s(rows[0].get("tab")) if len(rows) == 1 else ""
        aid = _s(m.get(EMP.SITE_ADDRESS_FIELD))
        line = {"date": _s(m.get("date")), "worker": _s(m.get("employee_name")),
                "batch": batch, "sheet_site": sheet_site, "tab": tab,
                "address": _s((addresses.get(aid) or {}).get("label")) or _s(m.get("site")),
                "rows_found": len(rows)}
        if sheet_site:
            saved = PI.saved_for(sheet_site)
            at = AT.projects_on_site(aid) if aid else []
            ids = {_s(p.get("id")): p for p in at}
            if saved.get("site") == aid and (saved.get("project") in ids
                                            or saved.get("project") == PI.OVERHEAD):
                pid = saved["project"]
                line.update(outcome="SAVED MAPPING",
                            project=("overhead" if pid == PI.OVERHEAD
                                     else _s(ids[pid].get("name"))))
            elif len(at) == 1:
                line.update(outcome="ONE PROJECT AT THE SITE",
                            project=_s(at[0].get("name")))
            elif len(at) > 1:
                line.update(outcome="ASK ONCE FOR THIS SITE NAME",
                            project=" | ".join(_s(p.get("name")) for p in at))
            else:
                line.update(outcome="STAYS UNASSIGNED (no project at the site)",
                            project="")
        else:
            last = AT.project_last_month(m.get("employee_id"), month)
            why = ("no import" if not rec else
                   "no sheet row for that day" if not rows else
                   "two sheet rows for that day" if len(rows) > 1 else
                   "blank SITE")
            if last.get(AT.OVERHEAD_FIELD):
                line.update(outcome=f"NO SITE NAME ({why}) → LAST MONTH",
                            project="overhead")
            elif last.get("project_id"):
                line.update(outcome=f"NO SITE NAME ({why}) → LAST MONTH",
                            project=_s(last.get("project_name")))
            else:
                line.update(outcome=f"NO SITE NAME ({why}) → STAYS UNASSIGNED",
                            project="")
        out.append(line)
    return {"lines": out, "single_tab_imports": sorted(single_tab)}


def report(p: dict, month: str, site_word: str, expect: int) -> None:
    lines = p["lines"]
    print(f"DRY RUN — nothing is written. Unassigned markings in {month} "
          f"whose site contains {site_word!r}: {len(lines)}")
    if expect and len(lines) != expect:
        print(f"  ⚠ expected {expect}; found {len(lines)} — check --month and "
              f"--site before reading the list")
    for b in p["single_tab_imports"]:
        rec = (STORE.get("pay_imports") or {}).get(b) or {}
        print(f"  ⚠ import {b} ({_s(rec.get('filename'))}) was read by the "
              f"SINGLE-TAB parser: only its first tab is stored")
    counts = {}
    for ln in lines:
        head = ln["outcome"].split(" (")[0]
        counts[head] = counts.get(head, 0) + 1
    print("\nSUMMARY")
    for k, n in sorted(counts.items()):
        print(f"  {n:>4}  {k}")
    asks = {}
    for ln in lines:
        if ln["outcome"].startswith("ASK"):
            asks.setdefault((ln["sheet_site"], ln["address"]), [0, ln["project"]])[0] += 1
    if asks:
        print("\nQUESTIONS THE NEXT IMPORT WOULD ASK — once per site name")
        for (name, addr), (n, cands) in sorted(asks.items()):
            print(f"  {name!r} at {addr!r}: {n} marking(s); candidates: {cands}")
    print("\nDATE        WORKER                SHEET SITE NAME        ADDRESS"
          "                OUTCOME → PROJECT")
    for ln in lines:
        print(f"  {ln['date']:<10} {ln['worker'][:20]:<21} "
              f"{(ln['sheet_site'] or '—')[:22]:<22} {ln['address'][:22]:<22} "
              f"{ln['outcome']} → {ln['project'] or '—'}")


def main(argv=None, loader=load_readonly) -> int:
    ap = argparse.ArgumentParser(
        description="READ-ONLY: what unassigned markings would get under the "
                    "one-tab-per-site rule. There is no write mode.")
    ap.add_argument("--dry-run", action="store_true", required=True,
                    help="required, and the only mode")
    ap.add_argument("--month", default="2026-10")
    ap.add_argument("--site", default="jamnagar",
                    help="a word the marking's site contains (case ignored)")
    ap.add_argument("--expect", type=int, default=88,
                    help="the count you expect; a different one is flagged")
    args = ap.parse_args(argv)
    loader(STORE)
    report(plan(args.month, args.site), args.month, args.site, args.expect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
