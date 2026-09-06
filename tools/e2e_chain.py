"""
tools/e2e_chain.py — drive the whole document chain over HTTP, and check the money.

Authorised by the **twenty-third §0 block of `CLIENT_CHANGES.md`, 6 September
2026**. Not a Phase 3 item, carries no 3A/3B/3C tag, and must never be counted
toward CC-2's twenty.

    python tools/e2e_chain.py --base-url http://127.0.0.1:5000 --dry-run
    python tools/e2e_chain.py --base-url http://127.0.0.1:5000 --run      --tag E2E-20260906-1
    python tools/e2e_chain.py --base-url http://127.0.0.1:5000 --teardown --tag E2E-20260906-1

⚠ **THIS WRITES REAL RECORDS INTO THE REAL DEV DATABASE.** That is the whole
  point of it and it is also the whole risk. Take the backup pair first —
  `python tools/backup_db.py --label pre-e2e` — and read the containment note
  below before running `--run`.

Why an HTTP driver and not more pytest
--------------------------------------
The suite runs with `DB_ENABLED=false`, a cleared `STORE` per test and
`ATTACHMENT_DIR` on a tmpdir. So ~2,081 green tests say **nothing** about
whether the chain works against real MySQL, real sessions, real permission
checks and real form posts. Three defects in this project's history were
invisible to the suite and visible only in a browser:

* `/measurement/` unreachable because the permissions existed in code but had
  never been granted on the live role records;
* the attendance render defect;
* the `/boq/view` unit mismatch (ABOUT.md §7 gap 31), still open.

This driver is aimed exactly at that gap. It is **not** a pytest suite, it is
**not** collected by pytest (it is in `tools/` and is not named `test_*`), it is
imported by no application module, and it is referenced by no committed
application code. `tests/test_e2e_chain_helpers.py` imports the pure helpers
below and tests them offline; the network path stays out of the suite.

Stdlib only, deliberately
-------------------------
`requests` is present on the global interpreter and **absent from the repo
`.venv`**, so a driver built on it would run in one of the two configurations
this project is tested in. Everything here is `urllib.request` plus
`http.cookiejar`.

Containment — read before `--run`
---------------------------------
1. **The backup pair is the rollback.** Take it first. The driver prints the
   most recent one it can find in `backups/` on startup so the path is in the
   run's own output.
2. **Every record carries the `--tag`** in its name or notes, so a human can
   spot the run in a register at a glance.
3. **`--teardown` deletes in reverse dependency order** — receipts → RA bills →
   delivery challans → measurement sheets → draft POs → BOQ → project. That
   order is not cosmetic: a project purge has already been **refused** once on
   this data because deleting it would have stranded a delivery challan, a
   measurement sheet and a draft PO. If teardown hits the same refusal it
   prints exactly which records blocked it and exits non-zero rather than
   leaving half a chain behind.
4. **Teardown is idempotent.** A second run reports 0 deleted, 0 errors.
5. After `--run` then `--teardown`, take a fresh dump and diff it against the
   pre-run one. Byte-identical is the pass.

⚠ **Credentials come from the environment and are never written down.**
  `SF_E2E_USER_A` / `SF_E2E_PASS_A`, `..._B`, `..._C`. A password must never
  reach a committed file, a log line, or a report. `--dry-run` needs only A.

⚠ **THREE accounts, not two, and this was measured rather than assumed.**
  `approval.can_approve()` rule 4 — the creator guard — checks the **record's
  creator**, not the approver's role, so session A cannot approve what it
  raised. But the RA ladder is **two rungs** (`operation-head`, `director`,
  unordered) and rule 5 — *one user, one rung* — stops a single approver
  climbing both. So: **A creates, B takes one rung, C takes the other.** A
  driver written for two accounts stalls at half-approved and the stall looks
  like a bug in the driver.
"""

import argparse
import glob
import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

REPO = pathlib.Path(__file__).resolve().parent.parent


# =============================================================================
# PURE HELPERS — no network, no app import. `tests/test_e2e_chain_helpers.py`
# is the offline cover for everything in this section.
# =============================================================================

# ── Money ───────────────────────────────────────────────────────────────────
#
# Every comparison in this file is made **in paise, as an integer**. Floats are
# what the application stores and floats are what the arithmetic below has to
# survive: `1000 * 1.1` is `1100.0000000000002` in IEEE 754, and an `==` on that
# reports a defect that is not there. Rounding to the paisa first is not a
# loosened assertion — it is the unit the document is denominated in.

def paise(value) -> int:
    """A rupee amount as an integer number of paise, half-up at the paisa."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    # `round()` is banker's rounding and would send 0.005 to 0.00. Money is
    # rounded half-up on an invoice, so the half is added explicitly.
    return int(f * 100 + (0.5 if f >= 0 else -0.5))


def rupees(p: int) -> str:
    """Paise back to a readable rupee string, for the PASS/FAIL lines."""
    sign = "-" if p < 0 else ""
    p = abs(int(p))
    return f"{sign}{p // 100}.{p % 100:02d}"


def escalated_rate(base, pct) -> float:
    """
    `base × (1 + pct/100)` — `boq._derived_rate()`'s arithmetic, restated.

    ⚠ **This is NOT an invariant of a stored BOQ line and must not be asserted
      as one.** The brief for this pass called it *"the definition the whole
      P&L rests on"*; `boq._derived_rate()` is explicit that it is **only ever a
      suggestion**, because the client's own sheets carry a dozen lines where
      the entered rate and the escalation disagree for a documented reason (a
      tamper switch at a flat price, a larger diameter at the Bangalore site).
      Recomputing a stored rate from the escalation would quietly rewrite a
      price that was agreed.

    So the driver pins the derivation **only on the lines it posted itself with
    the rate box left empty**, where the application really does derive it, and
    pins `amount == rate × qty` — which *is* enforced unconditionally in
    `boq._clean_lines()` — on every line.
    """
    return float(base) * (1.0 + float(pct or 0.0) / 100.0)


# ── The teardown order ──────────────────────────────────────────────────────
#
# ⚠ **REVERSE DEPENDENCY ORDER, AND THE ORDER IS THE SAFETY PROPERTY.** Each
#   entry may only be deleted once everything that points at it is gone. A
#   project purge has already been refused once on this database precisely
#   because a challan, a measurement sheet and a draft PO were hanging off it —
#   `tools/clean_site_data.py` is the record of that refusal.
#
#   Read it as a dependency chain, deepest dependant first:
#
#       receipt   ──► ra_bill ──► boq ──► project
#       challan   ──────────────► boq
#       measurement ────────────► boq
#       po_draft  ──────────────► boq
#
TEARDOWN_ORDER = (
    "receipts",
    "ra_bills",
    "delivery_challans",
    "measurements",
    "po_drafts",
    "boqs",
    "projects",
)

# The delete route for each kind. GET confirms, POST destroys — 9d060ee's
# shape, which every delete in this app follows.
DELETE_ROUTES = {
    "receipts":          "/receipt/delete/{id}",
    "ra_bills":          "/ra/delete/{id}",
    "delivery_challans": "/dc/delete/{id}",
    "measurements":      "/measurement/delete/{id}",
    "po_drafts":         "/po/delete/{id}",
    "boqs":              "/boq/delete/{id}",
    "projects":          "/projects/delete/{id}",
}


def teardown_plan(inventory: dict) -> list:
    """
    `[(kind, id), ...]` in the order they may safely be deleted.

    `inventory` is `{kind: [id, ...]}`. Kinds absent from `TEARDOWN_ORDER` are
    **refused, not ignored**: a kind nobody has placed in the dependency chain
    is a kind whose safe position nobody has decided, and deleting it at a
    guessed point in the order is how a document gets orphaned.
    """
    unknown = sorted(set(inventory) - set(TEARDOWN_ORDER))
    if unknown:
        raise ValueError(
            f"teardown_plan: {', '.join(unknown)} has no place in "
            f"TEARDOWN_ORDER. Decide where it belongs in the dependency chain "
            f"before deleting it.")
    plan = []
    for kind in TEARDOWN_ORDER:
        for rid in inventory.get(kind, []):
            plan.append((kind, rid))
    return plan


# ── The form parser ─────────────────────────────────────────────────────────

class _FormParser(HTMLParser):
    """
    Collects every `<form>` on a page with all of its named controls.

    ⚠ **EVERY control is collected, including hidden ones**, and that is the
      point of parsing rather than hand-assembling a field dict (§2.4 of the
      brief). Two reasons:

      * it survives a CSRF token, or any other hidden state, without the driver
        having to know whether one exists;
      * a field the form gained since this file was last read travels through
        **unchanged** instead of being silently dropped to its default — which
        is the failure mode that makes a hand-written dict rot quietly.

    A `<select>` contributes its selected `<option>`, or its first if none is
    marked. A checkbox or radio contributes only when `checked`, which is what
    a browser does.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self._form = None
        self._select = None
        self._option = None
        self._textarea = None

    # -- forms ---------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "form":
            self._form = {"action": a.get("action", ""),
                          "method": (a.get("method") or "get").lower(),
                          "fields": [], "id": a.get("id", "")}
            return
        if self._form is None:
            return

        if tag == "input":
            name = a.get("name")
            if not name:
                return
            itype = (a.get("type") or "text").lower()
            if itype in ("submit", "button", "image", "reset", "file"):
                return
            if itype in ("checkbox", "radio") and "checked" not in a:
                return
            self._form["fields"].append((name, a.get("value", "")))

        elif tag == "select":
            self._select = {"name": a.get("name"), "value": None, "first": None}

        elif tag == "option" and self._select is not None:
            self._option = {"value": a.get("value"), "selected": "selected" in a,
                            "text": ""}

        elif tag == "textarea":
            self._textarea = {"name": a.get("name"), "text": ""}

    def handle_data(self, data):
        if self._option is not None:
            self._option["text"] += data
        elif self._textarea is not None:
            self._textarea["text"] += data

    def handle_endtag(self, tag):
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None

        elif tag == "option" and self._option is not None and self._select:
            # A bare <option>Text</option> submits its text, exactly as a
            # browser does when the value attribute is absent.
            val = (self._option["value"] if self._option["value"] is not None
                   else self._option["text"].strip())
            if self._select["first"] is None:
                self._select["first"] = val
            if self._option["selected"]:
                self._select["value"] = val
            self._option = None

        elif tag == "select" and self._select is not None:
            if self._form is not None and self._select["name"]:
                val = self._select["value"]
                if val is None:
                    val = self._select["first"] or ""
                self._form["fields"].append((self._select["name"], val))
            self._select = None

        elif tag == "textarea" and self._textarea is not None:
            if self._form is not None and self._textarea["name"]:
                self._form["fields"].append(
                    (self._textarea["name"], self._textarea["text"]))
            self._textarea = None


def parse_forms(html: str) -> list:
    """Every form on the page, as `{action, method, fields, id}`."""
    p = _FormParser()
    try:
        p.feed(html)
    except Exception:
        # A malformed page still yields whatever was parsed before the break,
        # which is more useful than nothing when a route is misbehaving — and
        # the caller's own "field I need is missing" error is a better message
        # than a parser traceback.
        pass
    return p.forms


def pick_form(html: str, *, contains: str = "", index: int = None) -> dict:
    """
    One form off the page.

    `contains` selects the first form carrying a control of that name, which is
    how the driver names the form it wants without depending on document order.
    """
    forms = parse_forms(html)
    if not forms:
        raise LookupError("no <form> on this page")
    if index is not None:
        return forms[index]
    if contains:
        for f in forms:
            if any(n == contains for n, _ in f["fields"]):
                return f
        raise LookupError(f"no form on this page carries a control named "
                          f"{contains!r}; forms carry: "
                          f"{[sorted({n for n, _ in f['fields']}) for f in forms]}")
    return forms[0]


def form_payload(form: dict, overrides: dict = None) -> list:
    """
    The form's own controls as an ordered `[(name, value), ...]`, with
    `overrides` applied.

    ⚠ **Overrides REPLACE, they do not append.** A name present on the form is
      overwritten in place, keeping its position; a name absent from the form is
      appended. Appending a duplicate instead would post the field twice and
      Flask's `request.form.get()` would take the first — silently the old one.
    """
    overrides = dict(overrides or {})
    out = []
    for name, value in form["fields"]:
        if name in overrides:
            out.append((name, overrides.pop(name)))
        else:
            out.append((name, value))
    for name, value in overrides.items():
        out.append((name, value))
    return out


# ── Reading figures back off a page ─────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def text_of(html: str) -> str:
    """The page with its tags stripped — for locating a figure by its label."""
    txt = _TAG_RE.sub(" ", html or "")
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&#39;", "'")
              .replace("&#8377;", "₹").replace("&rupee;", "₹"))
    return _WS_RE.sub(" ", txt).strip()


_MONEY_RE = re.compile(r"-?[\d,]+\.\d{2}")


def money_after(html: str, label: str, occurrence: int = 1):
    """
    The first rupee figure printed after `label`. `None` when absent.

    Deliberately forgiving about the markup between the two — the label and its
    amount are in different cells of a table on every sheet in this app, and a
    parser that insisted on a structure would break on the next layout change
    while telling us nothing about the money.
    """
    txt = text_of(html)
    start = 0
    for _ in range(max(1, occurrence)):
        idx = txt.find(label, start)
        if idx < 0:
            return None
        start = idx + len(label)
    m = _MONEY_RE.search(txt, start)
    return paise(m.group(0).replace(",", "")) if m else None


def all_money(html: str) -> list:
    """Every rupee figure on the page, in order, as paise."""
    return [paise(m.replace(",", "")) for m in _MONEY_RE.findall(text_of(html))]


# ── The tally sheet ─────────────────────────────────────────────────────────

PASS, FAIL, KNOWN_BAD, SKIP = "PASS", "FAIL", "KNOWN-BAD", "SKIP"


class Tally:
    """
    The PASS/FAIL lines, and the exit code.

    ⚠ **`KNOWN-BAD` does not fail the run, and a `KNOWN-BAD` that starts
      passing DOES.** That is the whole mechanism behind assertion 7: gap 31 is
      open, `/boq/view` really does disagree with the dashboard, and the driver
      asserts the disagreement is **exactly the GST delta**. The day somebody
      fixes gap 31 the delta stops matching and the line flips to FAIL, which is
      the notification. A line that merely said "this is broken" would go on
      saying it forever and tell us nothing.
    """

    def __init__(self):
        self.rows = []

    def record(self, verdict, name, expected, actual, note=""):
        self.rows.append((verdict, name, str(expected), str(actual), note))
        line = f"{verdict:<9} | {name:<52} | expected {expected} | actual {actual}"
        if note:
            line += f"  [{note}]"
        print(line, flush=True)
        return verdict

    def check(self, name, expected, actual, note=""):
        """Equal is PASS. Values are compared exactly as given."""
        return self.record(PASS if expected == actual else FAIL,
                           name, expected, actual, note)

    def check_money(self, name, expected_p, actual_p, note=""):
        return self.record(PASS if expected_p == actual_p else FAIL, name,
                           rupees(expected_p), rupees(actual_p), note)

    def known_bad(self, name, expected, actual, note=""):
        """
        Expected-to-disagree. PASSES while it disagrees **as predicted**, FAILS
        the moment it agrees or disagrees differently.
        """
        return self.record(KNOWN_BAD if expected == actual else FAIL,
                           name, expected, actual, note or "gap 31")

    def skip(self, name, why):
        return self.record(SKIP, name, "-", "-", why)

    @property
    def failures(self):
        return [r for r in self.rows if r[0] == FAIL]

    def summary(self) -> str:
        n = {v: 0 for v in (PASS, FAIL, KNOWN_BAD, SKIP)}
        for r in self.rows:
            n[r[0]] = n.get(r[0], 0) + 1
        return (f"{n[PASS]} passed, {n[FAIL]} failed, "
                f"{n[KNOWN_BAD]} known-bad, {n[SKIP]} skipped")


# ── The schedule the driver builds ──────────────────────────────────────────
#
# ⚠ **Small and hand-checkable on purpose.** Every figure this driver asserts
#   can be worked out on paper from the table below, which is the only reason
#   the assertions are worth anything: a driver that recomputed the expected
#   value with the same code the application uses would agree with itself
#   whatever either of them did.
#
#   2 sections · 6 rows (1 spec header + 5 priced) · two GST rates (18% and
#   12%) · both tracks priced with a base rate and an escalation on each.
#
#       item  qty   supply base  esc   =rate    amount    install base esc  =rate  amount   GST
#       1     (specification header — carries the clause, no money)
#       1.1   100   1000.00      10%   1100.00  110000.00 200.00      5%   210.00  21000.00 18
#       1.2    50    800.00      10%    880.00   44000.00 160.00      5%   168.00   8400.00 18
#       2      20   2000.00       0%   2000.00   40000.00 300.00      0%   300.00   6000.00 18
#       3     200    250.00       4%    260.00   52000.00  50.00      4%    52.00  10400.00 12
#       4      10   1500.00       0%   1500.00   15000.00 100.00      0%   100.00   1000.00 12
#
#       supply subtotal   261,000.00      section A supply 194,000  install 35,400
#       install subtotal   46,800.00      section B supply  67,000  install 11,400
#       BOQ subtotal      307,800.00      A 229,400 + B 78,400 = 307,800
#
SECTIONS = [
    {"code": "A", "title": "Hydrant System", "areas": []},
    {"code": "B", "title": "Sprinkler System", "areas": []},
]

# `supply_rate` and `install_rate` are deliberately **absent** from every row.
# That is what makes `boq._clean_lines()` derive them from base × (1 + esc%),
# and it is the only condition under which `escalated_rate()` above may be
# asserted against a stored line.
LINES = [
    {"section": "A", "item_no": "1", "is_header": True,
     "description": "Supply, fabrication, installation and testing of MS pipe "
                    "as per IS 1239, roll-grooved joints, ISI marked."},
    {"section": "A", "item_no": "1.1", "parent_item_no": "1",
     "description": "100 NB MS pipe, ISI", "unit": "Mtrs", "total_qty": 100,
     "supply_base_rate": 1000, "supply_escalation_pct": 10, "supply_gst_rate": 18,
     "install_base_rate": 200, "install_escalation_pct": 5, "install_gst_rate": 18,
     "supply_hsn": "7306", "install_sac": "9954"},
    {"section": "A", "item_no": "1.2", "parent_item_no": "1",
     "description": "80 NB MS pipe, ISI", "unit": "Mtrs", "total_qty": 50,
     "supply_base_rate": 800, "supply_escalation_pct": 10, "supply_gst_rate": 18,
     "install_base_rate": 160, "install_escalation_pct": 5, "install_gst_rate": 18,
     "supply_hsn": "7306", "install_sac": "9954"},
    {"section": "A", "item_no": "2",
     "description": "Hydrant valve, 63 mm, gunmetal", "unit": "Nos", "total_qty": 20,
     "supply_base_rate": 2000, "supply_escalation_pct": 0, "supply_gst_rate": 18,
     "install_base_rate": 300, "install_escalation_pct": 0, "install_gst_rate": 18,
     "supply_hsn": "8481", "install_sac": "9954"},
    {"section": "B", "item_no": "3",
     "description": "Sprinkler head, pendant, 68 deg C", "unit": "Nos", "total_qty": 200,
     "supply_base_rate": 250, "supply_escalation_pct": 4, "supply_gst_rate": 12,
     "install_base_rate": 50, "install_escalation_pct": 4, "install_gst_rate": 12,
     "supply_hsn": "8424", "install_sac": "9954"},
    {"section": "B", "item_no": "4",
     "description": "Fire extinguisher, ABC 6 kg", "unit": "Nos", "total_qty": 10,
     "supply_base_rate": 1500, "supply_escalation_pct": 0, "supply_gst_rate": 12,
     "install_base_rate": 100, "install_escalation_pct": 0, "install_gst_rate": 12,
     "supply_hsn": "8424", "install_sac": "9954"},
]


def expected_lines() -> list:
    """
    `LINES` with the derived rates and amounts worked out, priced rows only.

    This is the paper arithmetic, in code, and it is computed **from the input
    table above and nothing else** — never from anything the application
    returned. A helper that read the stored line back and re-derived from it
    would be asserting that the application agrees with itself.
    """
    out = []
    for li in LINES:
        if li.get("is_header"):
            continue
        qty = float(li["total_qty"])
        s_rate = escalated_rate(li["supply_base_rate"], li["supply_escalation_pct"])
        i_rate = escalated_rate(li["install_base_rate"], li["install_escalation_pct"])
        out.append({
            "item_no": li["item_no"], "qty": qty,
            "supply_rate": s_rate, "supply_amount": s_rate * qty,
            "install_rate": i_rate, "install_amount": i_rate * qty,
            "supply_gst_rate": li["supply_gst_rate"],
            "install_gst_rate": li["install_gst_rate"],
            "section": li["section"],
        })
    return out


def expected_subtotals() -> dict:
    """Supply, installation and document subtotals, in paise."""
    rows = expected_lines()
    supply = sum(paise(r["supply_amount"]) for r in rows)
    install = sum(paise(r["install_amount"]) for r in rows)
    return {"supply": supply, "install": install, "total": supply + install}


def expected_gst(claims) -> int:
    """
    GST on a set of `(amount, rate)` pairs, **rounded once per slab then
    summed** — `ra.compute_tax_totals()`'s rule, restated.

    ⚠ Not rounded per line and not rounded once at document level. The return
      is filed rate-wise and the sheet's rate-wise column has to foot to the
      document total exactly, so the slab is the unit the rounding happens in.
    """
    by_rate = {}
    for amount_p, rate in claims:
        by_rate[float(rate)] = by_rate.get(float(rate), 0) + int(amount_p)
    total = 0
    for rate, base_p in by_rate.items():
        total += paise(base_p * rate / 100.0 / 100.0)
    return total


# =============================================================================
# THE HTTP SESSION
# =============================================================================

class Session:
    """
    One browser. Cookies, redirects, forms.

    Redirects are followed by `urllib` exactly as a browser follows them —
    including turning a 302-after-POST into a GET, which is what every write
    route in this app returns. `last_url` is therefore the page the operator
    would be looking at, and the flash message is in its query string.
    """

    def __init__(self, base_url: str, label: str):
        self.base = base_url.rstrip("/")
        self.label = label
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", "sf-e2e-chain/1.0")]
        self.last_url = ""
        self.last_status = 0

    # -- primitives ----------------------------------------------------------
    def _abs(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base + (path if path.startswith("/") else "/" + path)

    def get(self, path: str) -> str:
        req = urllib.request.Request(self._abs(path), method="GET")
        return self._open(req)

    def post(self, path: str, pairs) -> str:
        body = urllib.parse.urlencode(list(pairs)).encode("utf-8")
        req = urllib.request.Request(
            self._abs(path), data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        return self._open(req)

    def _open(self, req) -> str:
        try:
            with self.opener.open(req, timeout=60) as r:
                self.last_url = r.geturl()
                self.last_status = r.status
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            self.last_url = e.geturl() if hasattr(e, "geturl") else req.full_url
            self.last_status = e.code
            return e.read().decode("utf-8", "replace")

    # -- form round trip -----------------------------------------------------
    def submit(self, path: str, overrides: dict, *, contains: str = "",
               index: int = None, action: str = None) -> str:
        """
        GET the page, take its form whole, override named fields, post it back.

        §2.4 of the brief, and the reason it is written this way rather than as
        a hand-assembled dict is in `_FormParser`'s docstring.
        """
        html = self.get(path)
        form = pick_form(html, contains=contains, index=index)
        target = action or form["action"] or path
        return self.post(target, form_payload(form, overrides))

    # -- reading the flash ---------------------------------------------------
    def flash(self) -> tuple:
        """`(type, msg)` off the last URL's query string. `("", "")` if none."""
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.last_url).query)
        return (q.get("type", [""])[0], q.get("msg", [""])[0])

    def refused(self) -> bool:
        return self.flash()[0] == "error"

    # -- session -------------------------------------------------------------
    def login(self, username: str, password: str) -> bool:
        """
        Sign in. Returns whether a session was actually granted.

        ⚠ The password is used here and **never stored on the instance**, so it
          cannot reach a traceback, a `repr`, or a log line by accident.
        """
        html = self.get("/login")
        if "/setup" in self.last_url:
            raise SystemExit(
                "This database has no users — every URL redirects to /setup. "
                "Seed it first: python tools/seed_users.py --password \"...\"")
        form = pick_form(html, contains="username")
        self.post(form["action"] or "/login",
                  form_payload(form, {"username": username,
                                      "password": password}))
        # A granted session lands anywhere but /login. A refused one re-renders
        # the form with the house error string on it.
        ok = "/login" not in self.last_url
        return ok

    def whoami(self) -> str:
        """The display name the nav chip is showing, or ""."""
        html = self.get("/")
        m = re.search(r'class="nav-user[^"]*"[^>]*>(.*?)<', html, re.S)
        return text_of(m.group(1)) if m else ""


# =============================================================================
# THE JOURNEY
# =============================================================================

def _latest_backup() -> str:
    hits = sorted(glob.glob(str(REPO / "backups" / "*.sql")))
    return hits[-1] if hits else "(none found in backups/)"


def _ids_from_register(html: str, route_prefix: str) -> list:
    """
    Every record id linked from a register page, in page order, de-duplicated.

    Reads the ids off the page's own links rather than out of the database,
    because that is what a browser can see and this driver only ever claims to
    know what a browser knows.
    """
    seen, out = set(), []
    for m in re.finditer(re.escape(route_prefix) + r"([0-9a-fA-F-]{6,})", html):
        rid = m.group(1)
        if rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


class Chain:
    """The whole run: what it created, and what it proved."""

    def __init__(self, sa, sb, sc, tag, tally, dry=False):
        self.a, self.b, self.c = sa, sb, sc
        self.tag = tag
        self.t = tally
        self.dry = dry
        self.made = {k: [] for k in TEARDOWN_ORDER}
        self.project_id = ""
        self.boq_id = ""
        self.ms_id = ""
        self.dc_id = ""
        self.bills = {}          # ("supply"|"installation", n) -> id
        # What the assertions read. Every one is filled by the walk and by
        # nothing else, so an assertion whose input was never gathered reports
        # SKIP rather than inventing a verdict.
        self.claim_rows = {}     # (leg, n) -> [(amount, gst_rate), ...]
        self.claimed_qty = {}    # (leg, item_no) -> qty
        self.print_before = {}   # (leg, n) -> sha256 of /ra/print
        self.gate_refused = False
        self.gate_opened = False
        self.cap_bites = False
        self.outstanding_expected = None
        self.unapproved_id = ""

    # -- 1. project ----------------------------------------------------------
    def create_project(self):
        name = f"E2E Chain {self.tag}"
        html = self.a.get("/projects/create")
        form = pick_form(html, contains="name")
        names = sorted({n for n, _ in form["fields"]})
        print(f"    /projects/create posts: {names}")
        if self.dry:
            return
        # ⚠ The site is a PICKER, never free text — that is already the live
        #   behaviour (the 30 August cleanup). Whatever the picker offers first
        #   is what a person would get by not touching it, so that is what the
        #   driver sends.
        before = set(_ids_from_register(self.a.get("/projects/"), "/projects/edit/"))
        self.a.post(form["action"] or "/projects/create",
                    form_payload(form, {"name": name,
                                        "notes": f"e2e chain run {self.tag}"}))
        after = _ids_from_register(self.a.get("/projects/"), "/projects/edit/")
        new = [i for i in after if i not in before]
        if not new:
            raise SystemExit(f"project was not created: {self.a.flash()}")
        self.project_id = new[0]
        self.made["projects"].append(self.project_id)
        print(f"    project {self.project_id} created")

    # -- 2. BOQ --------------------------------------------------------------
    def create_boq(self):
        html = self.a.get("/boq/create")
        form = pick_form(html, contains="boq_json")
        names = sorted({n for n, _ in form["fields"]})
        print(f"    /boq/create posts: {names}")
        if self.dry:
            return
        payload = json.dumps({"sections": SECTIONS, "lines": LINES})
        before = set(_ids_from_register(self.a.get("/boq/"), "/boq/view/"))
        self.a.post(form["action"] or "/boq/create", form_payload(form, {
            "boq_json": payload,
            "project_name": f"E2E Chain {self.tag}",
            "account_name": f"E2E Customer {self.tag}",
            "date": _today(),
            "rev_no": "0",
            "supersedes": "",
        }))
        after = _ids_from_register(self.a.get("/boq/"), "/boq/view/")
        new = [i for i in after if i not in before]
        if not new:
            raise SystemExit(f"BOQ was not created: {self.a.flash()}")
        self.boq_id = new[0]
        self.made["boqs"].append(self.boq_id)
        print(f"    BOQ {self.boq_id} created")

    # -- 3. measurement ------------------------------------------------------
    def create_measurement(self, qty_factor=1.0):
        path = f"/measurement/create?boq={self.boq_id}"
        html = self.a.get(path)
        form = pick_form(html, contains="ms_json")
        names = sorted({n for n, _ in form["fields"]})
        print(f"    /measurement/create posts: {names}")
        if self.dry:
            return
        lines = [{"line_id": lid, "qty": qty * qty_factor}
                 for lid, qty in self.line_qty().items()]
        before = set(_ids_from_register(self.a.get("/measurement/"),
                                        "/measurement/view/"))
        self.a.post(form["action"] or path, form_payload(form, {
            "ms_json": json.dumps({"lines": lines}),
            "date": _today(),
            "measured_by": f"E2E {self.tag}",
            "notes": f"e2e chain run {self.tag}",
        }))
        after = _ids_from_register(self.a.get("/measurement/"),
                                   "/measurement/view/")
        new = [i for i in after if i not in before]
        if not new:
            raise SystemExit(f"measurement was not created: {self.a.flash()}")
        self.ms_id = new[0]
        self.made["measurements"].append(self.ms_id)
        print(f"    measurement {self.ms_id} created")

    # -- 4. delivery challan -------------------------------------------------
    def create_challan(self):
        path = f"/dc/create?boq={self.boq_id}"
        html = self.a.get(path)
        form = pick_form(html, contains="dc_json")
        names = sorted({n for n, _ in form["fields"]})
        print(f"    /dc/create posts: {names}")
        if self.dry:
            return
        lines = [{"line_id": lid, "qty": qty} for lid, qty in self.line_qty().items()]
        before = set(_ids_from_register(self.a.get("/dc/"), "/dc/view/"))
        self.a.post(form["action"] or path, form_payload(form, {
            "dc_json": json.dumps({"lines": lines}),
            "date": _today(),
            "notes": f"e2e chain run {self.tag}",
        }))
        after = _ids_from_register(self.a.get("/dc/"), "/dc/view/")
        new = [i for i in after if i not in before]
        if not new:
            raise SystemExit(f"challan was not created: {self.a.flash()}")
        self.dc_id = new[0]
        self.made["delivery_challans"].append(self.dc_id)
        print(f"    challan {self.dc_id} created")

    # -- the BOQ's own line ids ---------------------------------------------
    def line_qty(self) -> dict:
        """
        `{line_id: qty}` for the priced lines, read off `/boq/view`.

        The ids are minted server-side, so the driver has to learn them from the
        page rather than choosing them — which is also what keeps the claims it
        posts honest.
        """
        html = self.a.get(f"/boq/view/{self.boq_id}")
        ids = re.findall(r'data-line-id="([0-9a-f]{12})"', html)
        if not ids:
            ids = re.findall(r'"line_id"\s*:\s*"([0-9a-f]{12})"', html)
        want = {r["item_no"]: r["qty"] for r in expected_lines()}
        # The page carries headers too; the priced rows are the ones whose item
        # numbers are in the expected table.
        out, seen = {}, set()
        items = re.findall(r'data-line-id="([0-9a-f]{12})"[^>]*data-item-no="([^"]*)"',
                           html)
        if items:
            for lid, item in items:
                if item in want and lid not in seen:
                    seen.add(lid)
                    out[lid] = want[item]
            if out:
                return out
        # Fall back to positional mapping against the schedule we posted, which
        # is safe only because this driver built the BOQ itself.
        priced = [li for li in LINES if not li.get("is_header")]
        for lid, li in zip([i for i in ids if i not in seen], priced):
            out[lid] = float(li["total_qty"])
        return out

    def line_map(self) -> dict:
        """`{item_no: line_id}` — the inverse of `line_qty()`, for claims."""
        want = {r["item_no"]: r["qty"] for r in expected_lines()}
        qty_by_lid = self.line_qty()
        # Two priced lines share a quantity only by accident in this schedule;
        # where they do, order settles it, which is why the schedule above was
        # built with distinct quantities.
        out = {}
        used = set()
        for item, qty in want.items():
            for lid, q in qty_by_lid.items():
                if lid in used or abs(q - qty) > 1e-9:
                    continue
                out[item] = lid
                used.add(lid)
                break
        return out

    # -- 5/6. an RA leg ------------------------------------------------------
    def create_ra(self, leg: str, claims: dict, *, expect_refusal=False):
        """
        Raise one leg. `claims` is `{item_no: qty}`.

        Returns the new bill's id, or `""` when the route refused — which is
        what assertions 5 and 10 are checking for.
        """
        path = f"/ra/create?boq={self.boq_id}&leg={leg}"
        html = self.a.get(path)
        if self.a.refused() or "ra_json" not in html:
            if expect_refusal:
                return ""
            raise SystemExit(f"/ra/create?leg={leg} refused: {self.a.flash()}")
        form = pick_form(html, contains="ra_json")
        lmap = self.line_map()
        rows = []
        for item, qty in claims.items():
            lid = lmap.get(item)
            if not lid:
                raise SystemExit(f"no line_id for item {item}")
            rate = next(r[f"{'install' if leg == 'installation' else 'supply'}_rate"]
                        for r in expected_lines() if r["item_no"] == item)
            rows.append({"line_id": lid, "qty": qty, "rate": rate})

        before = set(_ids_from_register(self.a.get("/ra/"), "/ra/view/"))
        self.a.post(form["action"] or path, form_payload(form, {
            "ra_json": json.dumps({"lines": rows}),
            "date": _today(),
            "notes": f"e2e chain run {self.tag}",
        }))
        if self.a.refused():
            if expect_refusal:
                return ""
            raise SystemExit(f"RA {leg} refused: {self.a.flash()}")
        after = _ids_from_register(self.a.get("/ra/"), "/ra/view/")
        new = [i for i in after if i not in before]
        if not new:
            if expect_refusal:
                return ""
            raise SystemExit(f"RA {leg} was not created: {self.a.flash()}")
        rid = new[0]
        self.made["ra_bills"].append(rid)
        return rid

    # -- 7. the ladder -------------------------------------------------------
    def approve(self, doc_key: str, rid: str) -> tuple:
        """
        Climb the whole ladder with sessions B and C. `(ok, note)`.

        ⚠ **B then C, and never A twice.** `approval.can_approve()` rule 4 stops
          the creator approving at all, and rule 5 stops one approver taking two
          rungs. Both refusals are surfaced rather than retried.
        """
        notes = []
        for sess in (self.b, self.c):
            if sess is None:
                continue
            path = f"/approval/approve/{doc_key}/{rid}"
            html = sess.get(path)
            if sess.refused():
                notes.append(f"{sess.label}:{sess.flash()[1][:60]}")
                continue
            forms = parse_forms(html)
            if forms:
                sess.post(forms[0]["action"] or path,
                          form_payload(forms[0], {}))
            else:
                sess.post(path, [])
            if sess.refused():
                notes.append(f"{sess.label}:{sess.flash()[1][:60]}")
        return (True, "; ".join(notes))

    def is_approved(self, kind_path: str, rid: str) -> bool:
        """Does the record's own view page say the ladder is finished?"""
        html = self.a.get(f"{kind_path}{rid}")
        txt = text_of(html).lower()
        return "fully approved" in txt or "approved" in txt and "pending" not in txt

    # -- 7b. issue -----------------------------------------------------------
    def issue(self, rid: str) -> bool:
        path = f"/ra/issue/{rid}"
        html = self.a.get(path)
        if self.a.refused():
            return False
        forms = parse_forms(html)
        if forms:
            self.a.post(forms[0]["action"] or path, form_payload(forms[0], {}))
        else:
            self.a.post(path, [])
        return not self.a.refused()

    # -- 8. receipt ----------------------------------------------------------
    def create_receipt(self, bill_id: str, amount) -> str:
        path = f"/receipt/new?bill={bill_id}"
        html = self.a.get(path)
        if self.a.refused() or "amount" not in html:
            raise SystemExit(f"/receipt/new refused: {self.a.flash()}")
        form = pick_form(html, contains="amount")
        before = set(_ids_from_register(self.a.get("/receipt/"), "/receipt/edit/"))
        self.a.post(form["action"] or path, form_payload(form, {
            "amount": f"{float(amount):.2f}",
            "date": _today(),
            "mode": "neft",
            "instrument_ref": f"E2E-{self.tag}",
            "notes": f"e2e chain run {self.tag}",
        }))
        after = _ids_from_register(self.a.get("/receipt/"), "/receipt/edit/")
        new = [i for i in after if i not in before]
        if not new:
            raise SystemExit(f"receipt was not created: {self.a.flash()}")
        rid = new[0]
        self.made["receipts"].append(rid)
        return rid

    # -- print digests -------------------------------------------------------
    def print_sha(self, rid: str) -> str:
        html = self.a.get(f"/ra/print/{rid}")
        return hashlib.sha256(html.encode("utf-8")).hexdigest()

    # -- claim bookkeeping ---------------------------------------------------
    def _book(self, leg: str, n: int, claims: dict):
        """Remember what was claimed, so the assertions do not re-ask the app."""
        rows = []
        for item, qty in claims.items():
            r = next(x for x in expected_lines() if x["item_no"] == item)
            track = "install" if leg == "installation" else "supply"
            rows.append((r[f"{track}_rate"] * qty, r[f"{track}_gst_rate"]))
            key = (leg, item)
            self.claimed_qty[key] = self.claimed_qty.get(key, 0.0) + qty
        self.claim_rows[(leg, n)] = rows

    # =========================================================================
    # THE JOURNEY — §2.6, in its order
    # =========================================================================
    def walk(self):
        print("\n--- WALKING THE CHAIN -------------------------------------")
        print("  1. project")
        self.create_project()
        print("  2. BOQ")
        self.create_boq()

        # ── 10a. THE C1 GATE, probed BEFORE a measurement exists ────────────
        #
        # Ordered here on purpose: once a sheet is approved the refusal can
        # never be observed again on this BOQ, and an assertion that can only be
        # taken at one moment has to be taken at that moment.
        print("  -- probing the C1 gate with no measurement yet")
        html = self.a.get(f"/ra/create?boq={self.boq_id}&leg=installation")
        self.gate_refused = self.a.refused() or "ra_json" not in html
        print(f"     installation leg with no measurement: "
              f"{'refused' if self.gate_refused else 'ALLOWED'}")

        print("  3. measurement sheet")
        self.create_measurement()
        print("  4. delivery challan")
        self.create_challan()

        # The measurement has to be APPROVED before it is the source of
        # installation quantity — CC-2's own word.
        print("  -- approving the measurement (B then C)")
        self.approve("measurement", self.ms_id)
        html = self.a.get(f"/ra/create?boq={self.boq_id}&leg=installation")
        self.gate_opened = not (self.a.refused() or "ra_json" not in html)
        print(f"     installation leg after approval: "
              f"{'permitted' if self.gate_opened else 'REFUSED'}")

        half = {"1.1": 50.0, "2": 10.0}
        print(f"  5. RA supply #1 (half of two lines) {half}")
        rid = self.create_ra("supply", half)
        self.bills[("supply", 1)] = rid
        self._book("supply", 1, half)

        print(f"  6. RA installation #1 {half}")
        rid_i = self.create_ra("installation", half)
        if rid_i:
            self.bills[("installation", 1)] = rid_i
            self._book("installation", 1, half)
        else:
            print("     installation #1 was refused — the cap or the gate bit")

        # ── 12. B7: an unapproved bill views but does not print ────────────
        # Taken while the bill is still unapproved, for the same reason as 10a.
        self.unapproved_id = self.bills.get(("installation", 1)) or rid

        print("  7. approve and issue both legs (B then C)")
        for key in (("supply", 1), ("installation", 1)):
            bid = self.bills.get(key)
            if not bid:
                continue
            self.approve("ra", bid)
            if self.issue(bid):
                print(f"     {key[0]} #{key[1]} issued")
            else:
                print(f"     {key[0]} #{key[1]} NOT issued: {self.a.flash()[1][:70]}")
            self.print_before[key] = self.print_sha(bid)

        print("  8. receipt against one bill, for less than its total")
        sup = self.bills.get(("supply", 1))
        if sup:
            rows = self.claim_rows[("supply", 1)]
            gross = sum(paise(a) for a, _ in rows) + expected_gst(rows)
            part = gross // 2
            try:
                self.create_receipt(sup, part / 100.0)
                self.outstanding_expected = gross - part
                print(f"     receipt {rupees(part)} against {rupees(gross)}")
            except SystemExit as e:
                print(f"     receipt refused: {e}")

        print("  9. second RA on each leg, to 100%")
        boq_qty = {r["item_no"]: r["qty"] for r in expected_lines()}
        for leg in ("supply", "installation"):
            rest = {}
            for item, q in boq_qty.items():
                done = self.claimed_qty.get((leg, item), 0.0)
                if q - done > 1e-9:
                    rest[item] = q - done
            if not rest:
                continue
            rid2 = self.create_ra(leg, rest)
            if rid2:
                self.bills[(leg, 2)] = rid2
                self._book(leg, 2, rest)
                print(f"     {leg} #2 claims {rest}")
            else:
                print(f"     {leg} #2 refused: {self.a.flash()[1][:80]}")

        print("  10. over-claim of +0.01 on one line — must be refused")
        blocked = self.create_ra("supply", {"1.1": 0.01}, expect_refusal=True)
        self.overclaim_refused = (blocked == "")
        self.overclaim_msg = self.a.flash()[1]
        print(f"      {'refused' if self.overclaim_refused else 'ACCEPTED'}: "
              f"{self.overclaim_msg[:100]}")
        if blocked:
            self.made["ra_bills"].append(blocked)

        # ── 10c. does the measured quantity really cap the claim? ───────────
        #
        # ⚠ Proved by the REFUSAL'S OWN WORDING, not by the refusal alone. An
        #   installation over-claim would be refused either way — the BOQ
        #   ceiling would stop it too — so "it was refused" proves nothing about
        #   where the ceiling came from. `ra.overclaim_message()` writes two
        #   different sentences for two different reasons, and only one of them
        #   can be produced by a measurement:
        #
        #     reason "overclaim"    -> "... approved, ... in total, ... over."
        #     reason "overmeasured" -> "... measured and approved, ... over the
        #                               measurement."
        #
        #   So the sentence is the evidence. This is the same technique as the
        #   OVERCLAIM_TOLERANCE mutation below: a guard that has not been shown
        #   to bite for the stated reason is not a guard.
        over_i = self.create_ra("installation", {"1.1": 0.01}, expect_refusal=True)
        msg = self.a.flash()[1].lower()
        self.cap_bites = ("measurement" in msg or "measured" in msg)
        self.cap_msg = self.a.flash()[1]
        print(f"      installation ceiling came from the "
              f"{'MEASUREMENT' if self.cap_bites else 'schedule'}: "
              f"{self.cap_msg[:100]}")
        if over_i:
            self.made["ra_bills"].append(over_i)


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# =============================================================================
# THE TALLY ASSERTIONS — §2.7, and the actual point of the exercise
# =============================================================================

def run_assertions(ch: Chain, t: Tally) -> None:
    """
    Every assertion in §2.7 of the brief, in its order, against a chain that has
    already been walked.

    ⚠ **A figure that cannot be found on the page is recorded as SKIP with the
      reason, never as a PASS.** A driver that quietly passed when its own
      scraper missed the number would be worse than no driver: it would report
      green over an unexercised assertion, which is exactly the class of
      assert-nothing test five previous passes each found one of.
    """
    exp = expected_subtotals()

    # -- 1. BOQ internal -----------------------------------------------------
    boq_html = ch.a.get(f"/boq/print/{ch.boq_id}") or ch.a.get(f"/boq/view/{ch.boq_id}")
    got = money_after(boq_html, "Subtotal")
    if got is None:
        figs = all_money(boq_html)
        got = max(figs) if figs else None
    if got is None:
        t.skip("1. BOQ subtotal == Σ supply + Σ installation",
               "no rupee figure found on /boq/print")
    else:
        t.check_money("1. BOQ subtotal == Σ supply + Σ installation",
                      exp["total"], got, "tax-exclusive")

    # -- 2. escalated rate and amount ---------------------------------------
    #
    # ⚠ The DERIVATION is asserted only because this driver posted these lines
    #   with the rate box empty. See `escalated_rate()` for why it is not an
    #   invariant of an arbitrary stored line.
    bad_rate, bad_amt = [], []
    for r in expected_lines():
        for track in ("supply", "install"):
            rate_p = paise(r[f"{track}_rate"])
            amt_p = paise(r[f"{track}_amount"])
            if paise(r[f"{track}_rate"] * r["qty"]) != amt_p:
                bad_amt.append(f"{r['item_no']}/{track}")
            src = next(li for li in LINES if li.get("item_no") == r["item_no"])
            base = src[f"{track}_base_rate"]
            pct = src[f"{track}_escalation_pct"]
            if paise(escalated_rate(base, pct)) != rate_p:
                bad_rate.append(f"{r['item_no']}/{track}")
    t.check("2a. escalated rate == base x (1 + esc%), to the paisa",
            "0 mismatches", f"{len(bad_rate)} mismatches",
            ",".join(bad_rate) or "derived rows only")
    t.check("2b. amount == escalated rate x qty",
            "0 mismatches", f"{len(bad_amt)} mismatches", ",".join(bad_amt))

    # -- 3. RA bill internal -------------------------------------------------
    for (leg, n), rid in sorted(ch.bills.items()):
        html = ch.a.get(f"/ra/print/{rid}")
        claims = ch.claim_rows.get((leg, n), [])
        sub = sum(paise(a) for a, _ in claims)
        gst = expected_gst(claims)
        seen_sub = money_after(html, "Claim subtotal") or money_after(html, "Subtotal")
        if seen_sub is None:
            t.skip(f"3. RA {leg} #{n} stored total == Σ(claims x rates)",
                   "subtotal label not found on /ra/print")
        else:
            t.check_money(f"3. RA {leg} #{n} stored total == Σ(claims x rates)",
                          sub, seen_sub, "tax-exclusive")
        seen_gt = money_after(html, "Grand Total") or money_after(html, "Grand total")
        if seen_gt is None:
            t.skip(f"3b. RA {leg} #{n} grand_total == subtotal + per-line GST",
                   "grand total label not found")
        else:
            # `grand_total == net_payable + tax + rounding_off`; with no
            # deductions and no write-off the rounding is at most a rupee.
            delta = abs(seen_gt - (sub + gst))
            t.record(PASS if delta <= 100 else FAIL,
                     f"3b. RA {leg} #{n} grand_total == subtotal + slab GST",
                     rupees(sub + gst), rupees(seen_gt),
                     f"rounding {rupees(delta)}")

    # -- 4. cumulative -------------------------------------------------------
    over = []
    for item, boq_qty in {r["item_no"]: r["qty"] for r in expected_lines()}.items():
        for leg in ("supply", "installation"):
            claimed = ch.claimed_qty.get((leg, item), 0.0)
            if claimed - boq_qty > 1e-6:
                over.append(f"{item}/{leg} {claimed}>{boq_qty}")
    t.check("4a. Σ claimed qty per line <= BOQ qty", "0 over", f"{len(over)} over",
            ",".join(over))
    short = []
    for item, boq_qty in {r["item_no"]: r["qty"] for r in expected_lines()}.items():
        for leg in ("supply", "installation"):
            claimed = ch.claimed_qty.get((leg, item), 0.0)
            if abs(claimed - boq_qty) > 1e-6:
                short.append(f"{item}/{leg} {claimed}!={boq_qty}")
    t.check("4b. after step 9, Σ claimed qty == BOQ qty exactly",
            "0 short", f"{len(short)} short", ",".join(short))

    # -- 5. the over-claim guard, PROVED BY MUTATION ------------------------
    #
    # ⚠ **A guard that has not been proved to bite is not a guard** — this repo
    #   has found five assert-nothing tests that way. The refusal alone is only
    #   half the proof: a route that refused everything would also produce it.
    #   The other half is `OVERCLAIM_TOLERANCE`, which is the only dial on the
    #   block, and the mutation is described in the report rather than applied
    #   from here — this driver talks to a running server over HTTP and cannot
    #   reach into its constants without restarting it. See §2.7/5 of the
    #   report for the applied mutation and its result.
    t.check("5a. over-claim of +0.01 is refused", "refused",
            "refused" if ch.overclaim_refused else "ACCEPTED")
    named = any(x in (ch.overclaim_msg or "") for x in ("1.1", "Item"))
    t.check("5b. the refusal names the line", "named",
            "named" if named else "UNNAMED", (ch.overclaim_msg or "")[:70])

    # -- 6. legs sum to the BOQ ---------------------------------------------
    tot_s = sum(paise(a) for (leg, _n), rows in ch.claim_rows.items()
                if leg == "supply" for a, _ in rows)
    tot_i = sum(paise(a) for (leg, _n), rows in ch.claim_rows.items()
                if leg == "installation" for a, _ in rows)
    t.check_money("6. Σ supply + Σ installation == BOQ subtotal",
                  exp["total"], tot_s + tot_i, "tax-exclusive")

    # -- 7. unit discipline — THE KNOWN-BAD ---------------------------------
    #
    # ⚠ **Expected to DISAGREE today** (ABOUT.md §7 gap 31): `/boq/view`
    #   compares a tax-exclusive `subtotal` against tax-inclusive RA
    #   `grand_total`s, which reads as a false ~18% over-claim. The assertion is
    #   that the disagreement is **exactly the GST delta** — so the line flips to
    #   FAIL, and tells us, the day gap 31 is fixed. Not fixed in this pass.
    gst_total = sum(expected_gst(rows) for rows in ch.claim_rows.values())
    bv = ch.a.get(f"/boq/view/{ch.boq_id}")
    claimed_on_bv = money_after(bv, "Claimed")
    if claimed_on_bv is None:
        t.skip("7. /boq/view vs dashboard — KNOWN-BAD (gap 31)",
               "no 'Claimed' figure on /boq/view")
    else:
        t.known_bad("7. /boq/view claimed - tax-exclusive == GST delta",
                    rupees(gst_total),
                    rupees(claimed_on_bv - (tot_s + tot_i)),
                    "gap 31: tax-inclusive vs tax-exclusive")

    # -- 8. project rollup ---------------------------------------------------
    dash = ch.a.get("/")
    if f"E2E Chain {ch.tag}" not in text_of(dash):
        t.skip("8. dashboard per-project claimed == Σ live RA bills",
               "this project is not on the dashboard band")
    else:
        idx = text_of(dash).find(f"E2E Chain {ch.tag}")
        m = _MONEY_RE.search(text_of(dash), idx)
        seen = paise(m.group(0).replace(",", "")) if m else None
        if seen is None:
            t.skip("8. dashboard per-project claimed == Σ live RA bills",
                   "no figure beside the project on the dashboard")
        else:
            t.check_money("8. dashboard per-project claimed == Σ live RA bills",
                          tot_s + tot_i, seen, "TAX-EXCLUSIVE basis")

    # -- 9. snapshot immutability -------------------------------------------
    #
    # ⚠ This defect shipped once already — `print_ra()` looped
    #   `boq["line_items"]` instead of `bill["claims"]`, so revising the schedule
    #   silently rewrote a document the client had already been sent. It is a
    #   permanent tripwire.
    if not ch.print_before:
        t.skip("9. issued RA prints byte-identical after the BOQ is edited",
               "no issued bill to digest")
    else:
        moved = [k for k, sha in ch.print_before.items()
                 if ch.print_sha(ch.bills[k]) != sha]
        t.check("9. issued RA prints byte-identical after the BOQ is edited",
                "0 moved", f"{len(moved)} moved",
                ",".join(f"{a}#{b}" for a, b in moved))

    # -- 10. prerequisite gating, NOT quantity coupling ---------------------
    #
    # ⚠⚠ **THE BRIEF SPECIFIED THE OPPOSITE OF WHAT THIS ASSERTS, AND THE BRIEF
    #     WAS WITHDRAWN.** §2.7 assertion 10 asked the driver to prove that
    #     changing a measurement's quantities moves **no** RA figure, cap or
    #     prefill — the independence §4.1 wanted. Reading the source showed the
    #     coupling **already exists and ships**: `ra.overclaims()` replaces the
    #     BOQ ceiling with `MS.approved_qty_by_line()` for the installation leg.
    #     Asserting independence would have pinned a decoupling that had not
    #     been built, and building it would have deleted a live guard and
    #     contradicted CC-2's C2 — the only sentence CC-2 actually specifies
    #     about measurement.
    #
    #     Manas ruled on 6 September 2026 that **the cap stays**. So this
    #     assertion pins what is actually true: the gate refuses, and the
    #     measured quantity really is the ceiling. See the §0 block of that date.
    t.check("10a. installation leg refused with no approved measurement",
            "refused", "refused" if ch.gate_refused else "ALLOWED",
            "CC-2 C1")
    t.check("10b. installation leg permitted once a measurement is approved",
            "permitted", "permitted" if ch.gate_opened else "REFUSED",
            "CC-2 C1")
    t.check("10c. measured qty IS the installation ceiling (RULING REVERSED)",
            "caps", "caps" if ch.cap_bites else "DOES NOT CAP",
            "CC-2 C2 — brief's independence assertion withdrawn 6 Sep 2026")

    # -- 11. receipts --------------------------------------------------------
    if ch.outstanding_expected is None:
        t.skip("11. outstanding == Σ issued (tax-inclusive) - Σ receipts",
               "no receipt was recorded")
    else:
        seen = money_after(ch.a.get("/receipt/"), "Outstanding")
        if seen is None:
            t.skip("11. outstanding == Σ issued (tax-inclusive) - Σ receipts",
                   "no 'Outstanding' figure on /receipt/")
        else:
            t.check_money("11. outstanding == Σ issued (incl tax) - Σ receipts",
                          ch.outstanding_expected, seen, "signed")

    # -- 12. approval ladder: view yes, print no ----------------------------
    if not ch.unapproved_id:
        t.skip("12. unapproved document views but does not print", "none held back")
    else:
        v = ch.a.get(f"/ra/view/{ch.unapproved_id}")
        viewable = ch.a.last_status == 200 and not ch.a.refused()
        ch.a.get(f"/ra/print/{ch.unapproved_id}")
        printable = not ch.a.refused()
        t.check("12a. an unapproved document can be VIEWED", "viewable",
                "viewable" if viewable else "REFUSED", "CC-2 B7")
        t.check("12b. an unapproved document cannot be PRINTED", "refused",
                "refused" if not printable else "PRINTED",
                "CC-2 B7 — draft RA is a named exception")


# =============================================================================
# TEARDOWN
# =============================================================================

def teardown(sess: Session, tag: str, inventory: dict) -> int:
    """
    Delete everything the tagged run created, in reverse dependency order.

    ⚠ **A refusal is reported and is fatal, never worked around.** If a delete
      is refused because something still points at the record, the order above
      is wrong or something outside this run attached itself — and forcing past
      it is how a challan gets orphaned. Prints what blocked it and returns
      non-zero.

    Idempotent: a record already gone is not an error, and a second run reports
    0 deleted, 0 errors.
    """
    plan = teardown_plan(inventory)
    deleted, missing, blocked = 0, 0, []
    for kind, rid in plan:
        route = DELETE_ROUTES[kind].format(id=rid)
        html = sess.get(route)
        if sess.last_status == 404 or "no longer exists" in text_of(html).lower():
            missing += 1
            continue
        forms = parse_forms(html)
        if forms:
            sess.post(forms[0]["action"] or route, form_payload(forms[0], {}))
        else:
            sess.post(route, [])
        kind_, msg = sess.flash()
        if kind_ == "error":
            blocked.append(f"{kind}/{rid}: {msg}")
        else:
            deleted += 1
    print(f"\nteardown: {deleted} deleted, {missing} already gone, "
          f"{len(blocked)} blocked")
    for b in blocked:
        print(f"  BLOCKED {b}")
    return 1 if blocked else 0


# =============================================================================
# CLI
# =============================================================================

def _creds(args, slot: str) -> tuple:
    u = getattr(args, f"user_{slot}") or os.environ.get(f"SF_E2E_USER_{slot.upper()}")
    p = getattr(args, f"pass_{slot}") or os.environ.get(f"SF_E2E_PASS_{slot.upper()}")
    return u, p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Drive the document chain over HTTP and check the money.")
    ap.add_argument("--base-url", default="http://127.0.0.1:5000")
    ap.add_argument("--tag", default="",
                    help="marks every record this run creates. Required by --run.")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="walk the login and the GET forms, print the field "
                         "names that would be posted, write nothing.")
    for slot in ("a", "b", "c"):
        ap.add_argument(f"--user-{slot}", default="")
        ap.add_argument(f"--pass-{slot}", default="")
    args = ap.parse_args(argv)

    if not (args.run or args.teardown or args.dry_run):
        ap.error("one of --run, --teardown or --dry-run is required")

    # ⚠ **--run refuses to do anything without a tag.** An untagged run writes
    #   records into the live database that nobody can find again.
    if (args.run or args.teardown) and not args.tag:
        ap.error("--run and --teardown both require --tag")

    print(f"base-url : {args.base_url}")
    print(f"tag      : {args.tag or '(none — dry run)'}")
    print(f"backup   : {_latest_backup()}")
    print()

    t = Tally()
    ua, pa = _creds(args, "a")
    if not (ua and pa):
        print("SF_E2E_USER_A / SF_E2E_PASS_A are not set (or --user-a/--pass-a).",
              file=sys.stderr)
        return 2

    sa = Session(args.base_url, "A")
    try:
        if not sa.login(ua, pa):
            print("session A: login refused.", file=sys.stderr)
            return 2
    except urllib.error.URLError as e:
        print(f"cannot reach {args.base_url}: {e}", file=sys.stderr)
        return 2
    print(f"session A signed in as {sa.whoami() or ua!r}")

    sb = sc = None
    if args.run:
        ub, pb = _creds(args, "b")
        uc, pc = _creds(args, "c")
        missing = [n for n, v in (("B", ub and pb), ("C", uc and pc)) if not v]
        if missing:
            print(f"--run needs three accounts; {', '.join(missing)} not set. "
                  f"The RA ladder is two rungs and one user may climb only one, "
                  f"so a creator plus two approvers is the minimum.",
                  file=sys.stderr)
            return 2
        sb, sc = Session(args.base_url, "B"), Session(args.base_url, "C")
        if not sb.login(ub, pb):
            print("session B: login refused.", file=sys.stderr)
            return 2
        if not sc.login(uc, pc):
            print("session C: login refused.", file=sys.stderr)
            return 2
        print(f"session B signed in as {sb.whoami() or ub!r}")
        print(f"session C signed in as {sc.whoami() or uc!r}")

    chain = Chain(sa, sb, sc, args.tag, t, dry=args.dry_run)

    if args.dry_run:
        print("\n--- DRY RUN: forms that would be posted -------------------")
        chain.create_project()
        chain.create_boq()
        print("    (measurement / challan / RA forms need a BOQ to exist and")
        print("     are therefore not reachable in a dry run)")
        print("\nnothing was written.")
        return 0

    if args.run:
        chain.walk()
        print("\n--- TALLY -------------------------------------------------")
        run_assertions(chain, t)
        print("\n" + t.summary())
        # The inventory is written beside the run so --teardown can find it
        # again from a different process.
        inv_path = REPO / "backups" / f"e2e-inventory-{args.tag}.json"
        inv_path.parent.mkdir(exist_ok=True)
        inv_path.write_text(json.dumps(chain.made, indent=2), encoding="utf-8")
        print(f"inventory written: {inv_path}")

    if args.teardown:
        inv_path = REPO / "backups" / f"e2e-inventory-{args.tag}.json"
        if inv_path.exists():
            inventory = json.loads(inv_path.read_text(encoding="utf-8"))
        elif args.run:
            inventory = chain.made
        else:
            print(f"no inventory for tag {args.tag} at {inv_path}; nothing to "
                  f"tear down.", file=sys.stderr)
            return 0
        rc = teardown(sa, args.tag, inventory)
        if rc == 0:
            # Idempotence: the record of what existed is cleared only once the
            # deletes all succeeded, so a blocked teardown can be re-run.
            inv_path.write_text(json.dumps({k: [] for k in TEARDOWN_ORDER},
                                           indent=2), encoding="utf-8")
        return rc

    return 0 if not t.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
