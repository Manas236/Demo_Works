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
#
# ⚠ **`/boq/delete/<id>` DOES NOT EXIST IN THIS APPLICATION.** Every other kind
#   here has one; the BOQ has none, and `app.url_map` is the authority on that.
#   Worse, the URL does not 404: the closed-app gate answers an unrouted
#   address with a **302 to the dashboard**, so the teardown saw status 200 and
#   no error flash and counted the BOQ as deleted. Two runs' schedules were
#   reported torn down and were sitting in the register the whole time.
#
#   It is left in the table, marked, rather than removed — the entry is what
#   makes the failure visible in the summary instead of silently skipping the
#   kind. `_still_there()` below is what actually catches it.
BOQ_HAS_NO_DELETE_ROUTE = "boqs"

DELETE_ROUTES = {
    "receipts":          "/receipt/delete/{id}",
    "ra_bills":          "/ra/delete/{id}",
    "delivery_challans": "/dc/delete/{id}",
    "measurements":      "/measurement/delete/{id}",
    "po_drafts":         "/po/delete/{id}",
    "boqs":              "/boq/delete/{id}",      # ⚠ no such route — see above
    "projects":          "/projects/delete/{id}",
}

# ⚠ **A DELETE IS CONFIRMED BY LOOKING, NEVER BY THE ABSENCE OF AN ERROR.**
#   The old teardown counted a record deleted whenever the flash was not an
#   error, which is true of a successful delete, of a route that does not
#   exist, and of any redirect that happens to carry no message. These are the
#   pages that answer "is it still there".
VERIFY_ROUTES = {
    "receipts":          "/receipt/edit/{id}",
    "ra_bills":          "/ra/view/{id}",
    "delivery_challans": "/dc/view/{id}",
    "measurements":      "/measurement/view/{id}",
    "po_drafts":         "/po/view/{id}",
    "boqs":              "/boq/view/{id}",
    "projects":          "/projects/view/{id}",
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
    # ⚠ **NEWEST FIRST WITHIN A KIND, and this is not a refinement of the rule
    #   above — it is the same rule one level down.** `chain.made` appends in
    #   creation order, and an RA bill may only be deleted while it is the
    #   LATEST on its chain: "Only the latest bill can be deleted, and RA3 is
    #   not it — RA4 sits after it. RA bills are cumulative, so removing RA3 now
    #   would leave a gap in the sequence and change every later bill's
    #   balance." Walking the list forward therefore stalls on the first record
    #   that something later depends on. Reversed, each is the latest by the
    #   time its turn comes.
    plan = []
    for kind in TEARDOWN_ORDER:
        for rid in reversed(list(inventory.get(kind, []))):
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

# ⚠ **THE APP PRINTS WHOLE RUPEES ON SCREEN, AND `_MONEY_RE` CANNOT SEE THEM.**
#   `/boq/view`'s panel renders `&#8377;&nbsp;307,800` — `{:,.0f}`, no paise —
#   so a pattern requiring `.dd` finds nothing on the one page assertions 1, 7
#   and 8 read. The first run of this driver reported "255255255.55" for a BOQ
#   subtotal: `money_after` found no figure, the caller fell back to
#   `max(all_money(...))`, and the largest "money" on the page was the `.55` of
#   an `rgba(255,255,255,.55)` in the stylesheet.
#
#   So a second pattern, anchored on the rupee sign, which `text_of()` has
#   already decoded from `&#8377;`. It admits a figure with or without paise and
#   cannot match a CSS colour, because CSS has no ₹ in it. `_MONEY_RE` is left
#   exactly as it was — `all_money()` and three offline tests depend on it, and
#   the printed documents it reads DO carry paise.
_RUPEE_RE = re.compile(r"₹\s*(-?[\d,]+(?:\.\d{2})?)")


def money_after(html: str, label: str, occurrence: int = 1):
    """
    The first rupee figure printed after `label`. `None` when absent.

    Deliberately forgiving about the markup between the two — the label and its
    amount are in different cells of a table on every sheet in this app, and a
    parser that insisted on a structure would break on the next layout change
    while telling us nothing about the money.

    Both patterns are tried and the **earlier** match wins, never whichever
    happens to be looked for first: "the first figure after the label" is the
    contract, and a rupee-signed figure further down the page must not beat a
    plain one sitting immediately beside it.
    """
    txt = text_of(html)
    start = 0
    for _ in range(max(1, occurrence)):
        idx = txt.find(label, start)
        if idx < 0:
            return None
        start = idx + len(label)

    plain = _MONEY_RE.search(txt, start)
    signed = _RUPEE_RE.search(txt, start)
    if plain and signed:
        best = plain if plain.start() <= signed.start() else signed
    else:
        best = plain or signed
    if not best:
        return None
    # group(1) on the signed pattern, group(0) on the plain one.
    raw = best.group(1) if best.re is _RUPEE_RE else best.group(0)
    return paise(raw.replace(",", ""))


def all_money(html: str) -> list:
    """Every rupee figure on the page, in order, as paise."""
    return [paise(m.replace(",", "")) for m in _MONEY_RE.findall(text_of(html))]


# ── The BOQ line picker ──────────────────────────────────────────
#
# ⚠ **THE DRIVER USED TO LOOK FOR `data-line-id`, WHICH THIS APPLICATION HAS
#   NEVER EMITTED ANYWHERE.** Written against an attribute that exists nowhere
#   but in this file, it found nothing on `/boq/view`, fell through to a
#   positional `zip()` over an empty id list, and posted `{"lines": []}` — which
#   `boqpick.picked_lines()` correctly refused with "Nothing is ticked". The
#   driver then reported that as the *measurement* having failed to create. It
#   was never caught because the driver had never been run.
#
#   The ids are on the **picker grid** (`boqpick.grid_html`), the markup every
#   document raised from a BOQ is built on, and they are on it three times
#   over: `id="row_<lid>"` on the row, `id="c_<lid>"` on the tick box and
#   `id="q_<lid>"` on the quantity box. A **priced** row is the one carrying a
#   quantity box; a specification header is `id="head_<lid>"` with no box at
#   all, which is what keeps headers out of a claim without needing to know
#   their item numbers.

_PICK_ROW_RE = re.compile(
    r'<tr class="pk-row[^"]*"\s+id="row_([0-9a-f]{12})"(.*?)</tr>', re.S)
_PICK_NO_RE = re.compile(r'class="pk-no"[^>]*>(.*?)</td>', re.S)
_PICK_AVAIL_RE = re.compile(r'class="pk-avail"[^>]*>(.*?)</td>', re.S)


_CHIP_STRIP_RE = re.compile(r'<div class="ra-strip">(.*?)</div>', re.S)
_CHIP_MONEY_RE = re.compile(r"&#8377;&nbsp;([\d,]+(?:\.\d{2})?)")


def _chip_total(html: str):
    """
    The RA chip strip on `/boq/view`, summed, in paise. `None` if absent.

    ⚠ **Scoped to the strip, never to the page.** The same panel carries the
      *Total Basic Value* tile, and a reader that matched money anywhere on
      `/boq/view` would happily add the schedule to the claims and call the
      result a claim total. A cancelled bill shows the word "cancelled" and no
      figure, so it contributes nothing here — which is the register's own
      rule and the reason this sums what is printed rather than what is stored.
    """
    m = _CHIP_STRIP_RE.search(html or "")
    if not m:
        return None
    figs = _CHIP_MONEY_RE.findall(m.group(1))
    return sum(paise(f.replace(",", "")) for f in figs) if figs else None


_PP_ROW_RE = re.compile(r'<div class="pp-row">(.*?)<div class="pp-note">(.*?)</div>', re.S)
_PP_NAME_RE = re.compile(r'<span class="pp-name">(.*?)</span>', re.S)
_PP_FIG_RE = re.compile(r'<span class="pp-fig">(.*?)</span>', re.S)


def progress_rows(html: str) -> list:
    """
    The dashboard's *Claimed against approved* band: `[{name, fig, note}, ...]`.

    ⚠ **Scoped to the band, and that is the whole point of the helper.** A
      project name appears twice on `/` — once in *Recent BOQ & RA activity*,
      once here — and the activity list comes first. Searching the page text
      for the name and reading the next "N% claimed" found a **different
      project's** share, which is how assertion 8 reported 3% and then 4% for a
      project that was not on the band at all.
    """
    out = []
    for body, note in _PP_ROW_RE.findall(html or ""):
        nm = _PP_NAME_RE.search(body)
        fig = _PP_FIG_RE.search(body)
        out.append({
            "name": text_of(nm.group(1)) if nm else "",
            "fig": text_of(fig.group(1)) if fig else "",
            "note": text_of(note),
        })
    return out


def chooser_row(html: str, bill_id: str):
    """
    `(billed, outstanding)` in paise for one bill, off `/receipt/new`. `None`
    if the bill is not listed.

    ⚠ **`/receipt/` DOES NOT CARRY AN OUTSTANDING FIGURE.** That register lists
      receipts — Receipt, Date, Project, Bill, Mode, Instrument, Amount,
      Written off, and a *Total received* — so `money_after(…, "Outstanding")`
      on it returned None and assertion 11 skipped. The per-bill Billed and
      Outstanding columns are on the **chooser**, which is what `/receipt/new`
      renders when it is not given a bill, and they are the two figures sitting
      immediately before that row's "Record" link.
    """
    for row in re.split(r"<tr[ >]", html or ""):
        if f"/receipt/new?ra={bill_id}" not in row:
            continue
        figs = _MONEY_RE.findall(text_of(row))
        if len(figs) < 2:
            return None
        return (paise(figs[-2].replace(",", "")),
                paise(figs[-1].replace(",", "")))
    return None


def picker_rows(html: str) -> list:
    """
    The priced rows of a `boqpick` grid, in page order.

    `[{"line_id", "item_no", "avail", "qty", "checked"}, ...]`, where `qty` is
    the **prefilled** quantity box — what the operator was shown — and `avail`
    is the "In BOQ" cell beside it. A row with no quantity box is a
    specification header and is not returned.
    """
    out = []
    for lid, body in _PICK_ROW_RE.findall(html or ""):
        qty_m = re.search(r'id="q_%s"[^>]*\svalue="([^"]*)"' % lid, body)
        if qty_m is None:
            continue          # a header carries no quantity box
        no_m = _PICK_NO_RE.search(body)
        av_m = _PICK_AVAIL_RE.search(body)
        tick = re.search(r'id="c_%s"([^>]*)>' % lid, body)
        out.append({
            "line_id": lid,
            "item_no": text_of(no_m.group(1)) if no_m else "",
            "avail": text_of(av_m.group(1)) if av_m else "",
            "qty": qty_m.group(1).strip(),
            "checked": bool(tick and "checked" in tick.group(1)),
        })
    return out


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
        # The body of the last response, so a refusal rendered as a band on the
        # page can be read after the fact without the caller holding the html.
        self.last_html = ""

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
                self.last_html = r.read().decode("utf-8", "replace")
                return self.last_html
        except urllib.error.HTTPError as e:
            self.last_url = e.geturl() if hasattr(e, "geturl") else req.full_url
            self.last_status = e.code
            self.last_html = e.read().decode("utf-8", "replace")
            return self.last_html

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

    # ⚠ **A REFUSAL IS NOT ALWAYS A FLASH, AND THE INTERESTING ONES NEVER ARE.**
    #   A route that redirects says why in the query string; a route that
    #   re-renders its own form says why in an `<div class="alert error">` band
    #   on the page, and keeps the operator's input. Every *validation* refusal
    #   in this app is the second kind — the over-claim block, the
    #   over-measurement block, "Nothing is ticked".
    #
    #   The driver read only `flash()`, so assertions 5b and 10c compared an
    #   empty string and reported UNNAMED and DOES NOT CAP against an
    #   application that had named the line and had capped: the real sentence
    #   was "Item 1.1 (installation): 100 measured and approved, ... 0.01 over
    #   the measurement." That is exactly the evidence 10c is looking for, and
    #   it was on the page the whole time.
    _ALERT_RE = re.compile(r'<div class="alert[^"]*error[^"]*">(.*?)</div>', re.S)

    def refusal_text(self, html: str = "") -> str:
        """The refusal message — the flash if there is one, else the page band."""
        msg = self.flash()[1]
        if msg:
            return msg
        m = self._ALERT_RE.search(html or self.last_html or "")
        return text_of(m.group(1)) if m else ""

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
        # The refusal message from the last create_ra, captured at POST time.
        self.last_refusal = ""
        # A bill that is never approved and never issued — assertion 12.
        self.draft_id = ""

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
        # ⚠ **`?project_id=` IS WHAT ATTACHES THE SCHEDULE TO THE PROJECT, and
        #   the driver used to omit it.** The create form carries `project_name`
        #   as free text and no project field of any kind; the link is a hidden
        #   `project_id` the route prefills from this query parameter, and the
        #   form parser then carries it back untouched — which is exactly the
        #   case §2.4 says parsing the form whole exists to handle.
        #
        #   Without it the BOQ is created with `project_id: ""`, which is a
        #   perfectly legitimate state — the dashboard files its claims under
        #   **Unassigned** — but it means the chain's project is not the one the
        #   money lands against. Assertion 8 read "3% claimed" off the
        #   Unassigned row (₹3.08 L of ₹94.99 L, most of it other people's
        #   schedules) while the project the driver had just made sat at 0.
        path = f"/boq/create?project_id={self.project_id}" if self.project_id \
            else "/boq/create"
        html = self.a.get(path)
        form = pick_form(html, contains="boq_json")
        names = sorted({n for n, _ in form["fields"]})
        print(f"    /boq/create posts: {names}")
        if self.dry:
            return
        payload = json.dumps({"sections": SECTIONS, "lines": LINES})
        before = set(_ids_from_register(self.a.get("/boq/"), "/boq/view/"))
        self.a.post(form["action"] or path, form_payload(form, {
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
    def picker(self) -> list:
        """
        `picker_rows()` for this BOQ, read off the measurement entry grid.

        ⚠ **`/boq/view` is NOT the source, and assuming it was is the one real
          defect this driver shipped with.** That page renders the schedule for
          a human and carries no line id in any attribute. The ids have to come
          from a page built on `boqpick.grid_html`; every document raised from a
          BOQ uses one, and the measurement grid is the first in this walk. They
          are still minted server-side and still learned rather than chosen,
          which is what keeps the claims this driver posts honest.
        """
        return picker_rows(self.a.get(f"/measurement/create?boq={self.boq_id}"))

    def line_qty(self) -> dict:
        """`{line_id: qty}` for the priced lines, from the picker."""
        out = {}
        for row in self.picker():
            try:
                out[row["line_id"]] = float(row["qty"])
            except (TypeError, ValueError):
                continue
        return out

    def line_map(self) -> dict:
        """
        `{item_no: line_id}` — for claims.

        Read from each row's own `pk-no` cell. It used to be reconstructed by
        matching quantities, which silently needed a schedule with no two lines
        alike; the picker prints the item number, so the guess is not needed.
        """
        return {row["item_no"]: row["line_id"]
                for row in self.picker() if row["item_no"]}

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
        posted = self.a.post(form["action"] or path, form_payload(form, {
            "ra_json": json.dumps({"lines": rows}),
            "date": _today(),
            "notes": f"e2e chain run {self.tag}",
        }))
        # ⚠ **READ THE REFUSAL NOW.** The register GET below replaces
        #   `last_html`, so asking for the message afterwards returns the
        #   register page and the assertion sees an empty string — which is
        #   how 5b reported UNNAMED and 10c reported DOES NOT CAP against an
        #   application that had named the line and had capped.
        self.last_refusal = self.a.refusal_text(posted)
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
        # ⚠ **THE PARAMETER IS `ra`, NOT `bill`.** With an unrecognised one the
        #   route does not refuse — it renders the *chooser*, "Which bill was
        #   this paid against?", a table of every bill with a Record link. So
        #   the failure looked like a refusal (no `amount` field on the page)
        #   while the page was actually a 200 with no error on it at all, and
        #   assertion 11 skipped for the whole of the first run.
        path = f"/receipt/new?ra={bill_id}"
        html = self.a.get(path)
        if self.a.refused() or 'name="amount"' not in html:
            raise SystemExit(f"/receipt/new?ra= gave no amount form: "
                             f"{self.a.flash()}")
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
            # `expected_gst()` takes PAISE; `claim_rows` holds rupees.
            gross = (sum(paise(a) for a, _ in rows)
                     + expected_gst([(paise(a), r) for a, r in rows]))
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
                # The leg-2 bills are never approved and never issued, so one of
                # them is a genuine DRAFT for assertion 12 — unlike the leg-1
                # bill the old code held, which step 7 had already approved.
                self.draft_id = self.draft_id or rid2
                print(f"     {leg} #2 claims {rest}")
            else:
                print(f"     {leg} #2 refused: {self.a.flash()[1][:80]}")

        print("  10. over-claim of +0.01 on one line — must be refused")
        blocked = self.create_ra("supply", {"1.1": 0.01}, expect_refusal=True)
        self.overclaim_refused = (blocked == "")
        self.overclaim_msg = self.last_refusal
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
        self.cap_msg = self.last_refusal
        msg = self.cap_msg.lower()
        self.cap_bites = ("measurement" in msg or "measured" in msg)
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
    #
    # ⚠ **THE LABEL IS "Total Basic Value" AND THE PAGE IS `/boq/view`.** There
    #   is no "Subtotal" on either sheet; the panel tile is what carries the
    #   BOQ's tax-exclusive total, and it says "taxes extra" under itself. The
    #   `max(all_money(...))` fallback that used to stand here is DELETED
    #   rather than kept: on the first run it returned ₹2,55,25,525.55, scraped
    #   out of an `rgba(255,255,255,.55)` in the stylesheet, and reported it as
    #   a BOQ subtotal. A fallback that can invent a figure from a colour is
    #   worse than a SKIP, because a SKIP says it did not find one.
    boq_html = ch.a.get(f"/boq/view/{ch.boq_id}")
    got = money_after(boq_html, "Total Basic Value")
    if got is None:
        t.skip("1. BOQ subtotal == Σ supply + Σ installation",
               "no 'Total Basic Value' figure on /boq/view")
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
        # ⚠ **`expected_gst()` TAKES PAISE, and `claim_rows` holds RUPEES.**
        #   Passing the rows straight in divided by 100 a second time and made
        #   the expected tax 0.18% instead of 18% — on the first run that
        #   reported all four RA bills as failing when the application had the
        #   tax exactly right (₹75,000 + ₹13,500 = ₹88,500, and the mixed-slab
        #   bill to the paisa). The helper's own contract is paise, its offline
        #   tests pass paise, and it is the call sites that were wrong.
        gst = expected_gst([(paise(a), r) for a, r in claims])
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

    # -- 7. unit discipline — GAP 31, NOW CLOSED ----------------------------
    #
    # ⚠ **THIS LINE USED TO BE `known_bad` AND IS NOW AN ORDINARY ASSERTION,
    #   BECAUSE THE DEFECT IT PINNED WAS FIXED ON 8 SEPTEMBER 2026.** The old
    #   assertion is kept verbatim so the change is legible rather than silent:
    #
    #       t.known_bad("7. /boq/view claimed - tax-exclusive == GST delta",
    #                   rupees(gst_total),
    #                   rupees(claimed_on_bv - (tot_s + tot_i)),
    #                   "gap 31: tax-inclusive vs tax-exclusive")
    #
    #   It asserted that `/boq/view`'s chips **disagreed** with the claim total
    #   by exactly the GST, and it was written to flip the day somebody fixed
    #   that. Somebody did: the chips now render `claim_subtotal`, the same
    #   field `dashboard._boq_ra()` sums. So the assertion is now the one the
    #   fix makes true — the chips foot to the claims, tax-exclusive, and the
    #   GST delta is **zero**. A `known_bad` left standing here would be
    #   recording a defect that no longer exists.
    gst_total = sum(expected_gst([(paise(a), r) for a, r in rows])
                    for rows in ch.claim_rows.values())
    bv = ch.a.get(f"/boq/view/{ch.boq_id}")
    chips = _chip_total(bv)
    if chips is None:
        t.skip("7. /boq/view RA chips foot to the claims, tax-exclusive",
               "no RA chip strip on /boq/view")
    else:
        t.check_money("7. /boq/view RA chips foot to the claims (gap 31 closed)",
                      tot_s + tot_i, chips,
                      f"tax-exclusive; GST of {rupees(gst_total)} excluded")

    # -- 8. project rollup ---------------------------------------------------
    #
    # ⚠ **THE DASHBOARD ROUNDS ON PURPOSE, so an exact-money assertion against
    #   it can never pass and never could.** `dashboard.compact()` renders
    #   anything over a lakh as "3.08 L" — ₹3,08,000 for a ₹3,07,800 claim — so
    #   the old `check_money` against the scraped figure was comparing paise
    #   against a two-decimal lakh. It reported ₹1.86 on the first run, which
    #   was not even the project's figure: `_MONEY_RE` matched the next
    #   decimal-bearing number after the project name.
    #
    #   What the dashboard says EXACTLY, and what this chain is actually about,
    #   is the share: after step 9 every line is claimed in full, so the band
    #   must read **100% claimed** for this project. That is a precise
    #   assertion about the same agreement gap 31 was concerned with, taken at
    #   the precision the screen actually offers.
    #   ⚠⚠ **A NEW GAP, FOUND BY RUNNING THIS DRIVER ON 8 SEPTEMBER
    #     2026: `/boq/create` CANNOT ATTACH A BOQ TO A PROJECT.** The route
    #     accepts `?project_id=` and puts it in its prefill, and the POST branch
    #     reads `form.get("project_id")` — but the rendered form contains no
    #     `project_id` control of any kind, so the two halves never meet and
    #     every BOQ raised through the UI is stored with `project_id: ""`.
    #
    #     The linkage on the live database is real but was written by
    #     `tools/backfill_projects.py`, not by the form: `SF/BOQ/26-27/0004`,
    #     `0005` and `0008` carry no project either, for the same reason.
    #     The consequence is that this chain's claims roll up under
    #     **Unassigned** rather than the project the driver just created, and
    #     the project sits on the band at 0% or is not on it at all.
    #
    #     So this is recorded as KNOWN-BAD rather than fixed from here: adding
    #     a project picker to the BOQ form changes what a screen shows and is
    #     new scope, which a verification pass has no authority to take.
    rows = progress_rows(ch.a.get("/"))
    name = f"E2E Chain {ch.tag}"
    mine = next((r for r in rows if r["name"] == name), None)
    share = None
    if mine:
        got = re.search(r"(\d+(?:\.\d+)?)% claimed", mine["note"])
        share = got.group(1) if got else None

    if share == "100":
        t.check("8. dashboard shows this project claimed in full",
                "100% claimed", "100% claimed",
                "the BOQ is attached to its project")
    else:
        t.known_bad(
            "8. dashboard shows this project claimed in full",
            "not on the band (/boq/create cannot attach a BOQ to a project)",
            ("not on the band (/boq/create cannot attach a BOQ to a project)"
             if mine is None else f"{share}% claimed"),
            "NEW GAP 8 Sep 2026 — flips the day the BOQ form gains the field")

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
    #   ⚠ The figure is on the CHOOSER, not on `/receipt/`. See
    #     `chooser_row()` — the register lists receipts and a total received;
    #     the per-bill Billed and Outstanding columns are on `/receipt/new`.
    paid_bill = ch.bills.get(("supply", 1))
    if ch.outstanding_expected is None or not paid_bill:
        t.skip("11. outstanding == Σ issued (incl tax) - Σ receipts",
               "no receipt was recorded")
    else:
        row = chooser_row(ch.a.get("/receipt/new"), paid_bill)
        if row is None:
            t.skip("11. outstanding == Σ issued (incl tax) - Σ receipts",
                   "this bill is not listed on /receipt/new")
        else:
            billed, outstanding = row
            t.check_money("11. outstanding == bill total - receipt recorded",
                          ch.outstanding_expected, outstanding,
                          f"billed {rupees(billed)}, tax-inclusive")

    # -- 12. approval ladder: B7, as this application actually defines it ----
    #
    # ⚠⚠ **12b USED TO ASSERT THE OPPOSITE OF WHAT B7 SAYS, AND IT ASSERTED IT
    #     ABOUT A BILL THIS DRIVER HAD ALREADY APPROVED.** The old line was:
    #
    #         t.check("12b. an unapproved document cannot be PRINTED", "refused",
    #                 "refused" if not printable else "PRINTED",
    #                 "CC-2 B7 — draft RA is a named exception")
    #
    #     Two things were wrong with it. First, `walk()` captures
    #     `unapproved_id` before step 7 and then step 7 approves and issues
    #     that very bill, so by the time this ran the document was approved and
    #     printing it was correct. Second — and this is why the line could
    #     never have been right — `approval.can_print()` names `("draft",
    #     "cancelled")` as `print_exempt_states` on the RA bill, so **a draft
    #     prints by design**, carrying its DRAFT overprint. B7 on an RA bill
    #     reduces to *"an ISSUED bill prints only once it is approved"*, and
    #     this chain cannot produce an issued-but-unapproved bill because
    #     issuing runs after the ladder.
    #
    #     So 12b now asserts the exemption AND its safeguard, which is the
    #     condition the narrowing of 29 August 2026 was taken under: the draft
    #     prints, and it prints stamped DRAFT. A draft that printed clean is
    #     the thing B7 exists to prevent.
    draft_id = ch.draft_id or ch.unapproved_id
    if not draft_id:
        t.skip("12. unapproved document views, and prints only stamped DRAFT",
               "no draft bill held back")
    else:
        ch.a.get(f"/ra/view/{draft_id}")
        viewable = ch.a.last_status == 200 and not ch.a.refused()
        printed = ch.a.get(f"/ra/print/{draft_id}")
        printable = not ch.a.refused()
        stamped = '<div class="lc-mark lc-draft">DRAFT</div>' in printed
        banded = "This is a DRAFT and has not been issued" in printed

        t.check("12a. an unapproved document can be VIEWED", "viewable",
                "viewable" if viewable else "REFUSED", "CC-2 B7")
        t.check("12b. a DRAFT bill prints — the named exemption", "prints",
                "prints" if printable else "REFUSED",
                "approval.can_print print_exempt_states")
        t.check("12c. and it prints stamped DRAFT — the safeguard", "stamped",
                "stamped" if (stamped and banded) else "CLEAN",
                "a draft printing clean is what B7 guards against")


# =============================================================================
# TEARDOWN
# =============================================================================

def _still_there(sess: Session, kind: str, rid: str) -> bool:
    """
    Is the record still readable? The only honest test of a delete.

    Every view route in this app answers a missing id the same way — a redirect
    carrying an error flash ("BOQ not found.", "That document no longer
    exists.") — so a refusal here means gone and a clean 200 means present.
    A 404 is gone too, for the routes that answer that way.
    """
    route = VERIFY_ROUTES.get(kind)
    if not route:
        return True          # unverifiable is never reported as deleted
    html = sess.get(route.format(id=rid))
    if sess.last_status == 404 or sess.refused():
        return False
    if "no longer exists" in text_of(html).lower():
        return False
    return sess.last_status == 200


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
        if not _still_there(sess, kind, rid):
            missing += 1
            continue

        route = DELETE_ROUTES[kind].format(id=rid)
        html = sess.get(route)
        forms = parse_forms(html)
        if forms:
            sess.post(forms[0]["action"] or route, form_payload(forms[0], {}))
        else:
            sess.post(route, [])
        msg = sess.refusal_text()

        # ⚠ **THE RECORD IS RE-READ. The flash is not evidence.**
        if _still_there(sess, kind, rid):
            blocked.append(f"{kind}/{rid}: "
                           f"{msg or 'the route reported no error and the record is still there'}")
        else:
            deleted += 1

    print(f"\nteardown: {deleted} deleted, {missing} already gone, "
          f"{len(blocked)} still present")
    for b in blocked:
        print(f"  STILL PRESENT {b}")
    if blocked:
        print("\n  ⚠ These records are LIVE and this run did not remove them.\n"
              "    An issued RA bill and an approved measurement sheet are\n"
              "    refused deletion BY DESIGN, and a BOQ has no delete route at\n"
              "    all, so a chain that issues and approves cannot fully tear\n"
              "    itself down over HTTP. Remove them deliberately, or the next\n"
              "    run raises its documents alongside these.")
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
        # ⚠ **THE INVENTORY IS WRITTEN THE MOMENT THE WALK ENDS, BEFORE A
        #   SINGLE ASSERTION RUNS.** It used to be written after `t.summary()`,
        #   so anything raising inside `run_assertions` stranded every record
        #   the walk had just created with no inventory to tear them down from.
        #   That is not hypothetical: on the first run this driver ever made, a
        #   `UnicodeEncodeError` from printing "Σ" to a cp1252 console did
        #   exactly that. The teardown file IS the containment, so it is written
        #   as soon as there is anything to contain, and again afterwards
        #   whether the assertions pass, fail or raise.
        inv_path = REPO / "backups" / f"e2e-inventory-{args.tag}.json"
        inv_path.parent.mkdir(exist_ok=True)

        def _save_inventory():
            inv_path.write_text(json.dumps(chain.made, indent=2), encoding="utf-8")

        chain.walk()
        _save_inventory()
        print(f"inventory written: {inv_path}")
        try:
            print("\n--- TALLY -------------------------------------------------")
            run_assertions(chain, t)
            print("\n" + t.summary())
        finally:
            _save_inventory()

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
