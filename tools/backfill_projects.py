#!/usr/bin/env python
"""
backfill_projects.py — Create project records from existing BOQ project_names
=============================================================================

Reads every BOQ's `project_name`, groups them by `pipeline.norm_name()`, and
for each distinct normalised name proposes (or creates) a project record in
STORE["projects"].  Each BOQ in the group gets its `project_id` set to point
at that project.

**Dry-run is the default** — it prints the proposal and writes nothing.
The `--write` flag enables the real backfill, and `--write` still prints
everything it did.

**Idempotent:**  any BOQ that already has a non-empty `project_id` is left
alone.  Running the script twice with `--write` changes nothing the second
time.

**Reversible:**  the script records what it did to stdout (which project ids
were created, which BOQs were linked).  The dated backup taken before the
write run is the revert point.

Usage
-----
    python tools/backfill_projects.py            # dry-run (default)
    python tools/backfill_projects.py --write    # actually write
"""

import sys
import os
import uuid
from datetime import datetime

# ── Bootstrap the app so STORE and pipeline are available ───────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app          # noqa: E402 — boots persistence, loads STORE
import pipeline as P         # noqa: E402
from store import STORE      # noqa: E402


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def backfill(write: bool = False):
    """
    Group BOQs by normalised project_name.  For each group:
      - propose a project record (name, norm_name, client from first BOQ)
      - if --write, create the project and set project_id on every BOQ in the group
    """
    approved_names = {"Sify Bangalore", "Sify 2", "Sify3"}
    boqs = STORE.get("boqs", {})
    if not boqs:
        print("No BOQs in the store — nothing to backfill.")
        return

    # ── Separate BOQs that already have a project_id ────────────────────────
    already = []
    remaining = []
    for bid, boq in boqs.items():
        if str(boq.get("project_id", "")).strip():
            already.append((bid, boq))
        else:
            remaining.append((bid, boq))

    if already:
        print(f"\n{len(already)} BOQ(s) already have a project_id (skipped):")
        for bid, boq in already:
            print(f"  {boq.get('ref', bid):25s}  project_id={boq.get('project_id')}")

    # ── Group remaining BOQs by normalised project_name ─────────────────────
    groups: dict[str, list] = {}  # norm_name -> [(bid, boq), ...]
    blanks = []

    for bid, boq in remaining:
        pn = str(boq.get("project_name", "") or "").strip()
        if not pn:
            blanks.append((bid, boq))
            continue
        norm = P.norm_name(pn)
        groups.setdefault(norm, []).append((bid, boq))

    # ── Report blanks ───────────────────────────────────────────────────────
    if blanks:
        print(f"\n{len(blanks)} BOQ(s) with blank or missing project_name:")
        for bid, boq in blanks:
            print(f"  id={bid}  ref={boq.get('ref', '?')}")
    else:
        print("\nNo BOQs with blank or missing project_name.")

    # ── Report / create groups ──────────────────────────────────────────────
    if not groups:
        print("\nNo groups to backfill.")
        return

    print(f"\n{'=' * 70}")
    print(f"{'DRY RUN' if not write else 'WRITING'}: {len(groups)} distinct normalised project name(s)")
    print(f"{'=' * 70}")

    created_projects = []

    for norm, members in sorted(groups.items()):
        # Use the first member's spelling as the display name
        first_boq = members[0][1]
        display_name = first_boq.get("project_name", "")
        client = first_boq.get("account_name", "")
        site = first_boq.get("site_location", "")

        # Check if a project with this norm_name already exists
        existing_pid = None
        for pid, proj in STORE.get("projects", {}).items():
            if proj.get("norm_name") == norm:
                existing_pid = pid
                break

        if existing_pid:
            print(f"\n  norm_name: {repr(norm)}")
            print(f"  Project already exists: {existing_pid}")
            print(f"  BOQs ({len(members)}):")
            for bid, boq in members:
                print(f"    {boq.get('ref', bid):25s}  project_name={repr(boq.get('project_name'))}")
            if write:
                for bid, boq in members:
                    boq["project_id"] = existing_pid
                    print(f"    -> set project_id={existing_pid}")
        else:
            if write and display_name not in approved_names:
                continue
            pid = str(uuid.uuid4())
            now = _now()
            print(f"\n  norm_name: {repr(norm)}")
            print(f"  Proposed project:")
            print(f"    id:           {pid}")
            print(f"    name:         {repr(display_name)}")
            print(f"    norm_name:    {repr(norm)}")
            print(f"    client:       {repr(client)}")
            print(f"    site_address: {repr(site)}")
            print(f"  BOQs ({len(members)}):")
            for bid, boq in members:
                print(f"    {boq.get('ref', bid):25s}  project_name={repr(boq.get('project_name'))}")

            if write:
                STORE["projects"][pid] = {
                    "id":           pid,
                    "name":         display_name,
                    "norm_name":    norm,
                    "client":       client,
                    "site_address": site,
                    "notes":        f"Auto-created by backfill on {now}",
                    "created_at":   now,
                    "updated_at":   now,
                }
                created_projects.append(pid)
                print(f"    -> created project {pid}")
                for bid, boq in members:
                    boq["project_id"] = pid
                    print(f"    -> set project_id={pid} on BOQ {boq.get('ref', bid)}")

    if write and created_projects:
        import db
        db.sync(STORE)
        print(f"\n{'=' * 70}")
        print(f"DONE: {len(created_projects)} project(s) created, "
              f"{sum(len(v) for v in groups.values())} BOQ(s) linked.")
        print(f"{'=' * 70}")


if __name__ == "__main__":
    write = "--write" in sys.argv
    with app.app_context():
        backfill(write=write)
