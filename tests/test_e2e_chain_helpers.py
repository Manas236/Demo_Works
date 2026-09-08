"""
`tools/e2e_chain.py` — the pure helpers, offline.

The driver's whole value is that it talks to a **running** app over HTTP
against real MySQL, and that half of it deliberately stays out of this suite:
a network path inside pytest would either need a live server (making the suite
non-hermetic) or a mock (making it prove nothing the suite does not already
prove). What is covered here is the arithmetic, the form parser and the
teardown ordering — the three parts that can be wrong quietly.

⚠ **Why the arithmetic is worth pinning at all.** The driver asserts the
application's figures against a table of hand-computed expectations. If the
helper that computes those expectations is itself wrong, the driver agrees with
a mistake and reports PASS. These tests are what stop the expectations drifting
into agreement with whatever the app happens to do.

Authorised by the twenty-third §0 block of `CLIENT_CHANGES.md`, 6 September
2026. Not CC-2 scope; PROGRESS.md §4c.
"""

import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import e2e_chain as E  # noqa: E402


# =============================================================================
# THE DRIVER IS NOT PART OF THE APPLICATION
# =============================================================================

def test_no_application_module_imports_the_driver():
    """
    ⚠ It writes to the live database. Nothing the app serves may reach it.

    A route that could reach this module could be made to write a chain of test
    records into a customer's data by being visited.
    """
    offenders = []
    for py in REPO.glob("*.py"):
        text = py.read_text(encoding="utf-8", errors="replace")
        if "e2e_chain" in text:
            offenders.append(py.name)
    assert not offenders, (
        f"{offenders} reference tools/e2e_chain.py. It drives the LIVE dev "
        f"database and must stay unreachable from the application.")


def test_pytest_does_not_collect_the_driver_itself():
    """It is not named `test_*` and does not live in `tests/`."""
    assert E.__file__.replace("\\", "/").endswith("tools/e2e_chain.py")
    assert not pathlib.Path(E.__file__).name.startswith("test_")


# =============================================================================
# MONEY
# =============================================================================

@pytest.mark.parametrize("value,expected", [
    (0, 0), (1, 100), (1.5, 150), (0.01, 1), (1234.56, 123456),
    # The float that motivates the whole helper: 1000 * 1.1 is not 1100.0.
    (1000 * 1.1, 110000),
    (250 * 1.04, 26000),
    (-1.5, -150),
])
def test_paise_rounds_to_the_paisa(value, expected):
    assert E.paise(value) == expected


def test_paise_rounds_half_UP_and_not_bankers():
    """
    ⚠ `round()` is banker's rounding and would send 0.005 to 0.00 and 0.015 to
    0.02 — two different directions for the same half. Money on an invoice is
    rounded half-up, always.
    """
    assert E.paise(0.005) == 1
    assert E.paise(0.015) == 2
    assert E.paise(0.025) == 3


def test_paise_survives_rubbish_rather_than_raising():
    assert E.paise(None) == 0
    assert E.paise("") == 0
    assert E.paise("not a number") == 0


def test_rupees_round_trips_paise():
    for p in (0, 1, 99, 100, 123456, -150):
        assert E.paise(E.rupees(p)) == p


# =============================================================================
# THE ESCALATION
# =============================================================================

def test_escalated_rate_is_base_times_one_plus_pct():
    assert E.paise(E.escalated_rate(1000, 10)) == 110000
    assert E.paise(E.escalated_rate(800, 10)) == 88000
    assert E.paise(E.escalated_rate(250, 4)) == 26000
    assert E.paise(E.escalated_rate(2000, 0)) == 200000


def test_a_zero_or_absent_escalation_leaves_the_rate_alone():
    assert E.escalated_rate(1500, 0) == 1500.0
    assert E.escalated_rate(1500, None) == 1500.0


# =============================================================================
# THE SCHEDULE'S OWN ARITHMETIC — the numbers the driver asserts against
# =============================================================================

def test_the_expected_subtotals_are_the_hand_computed_ones():
    """
    ⚠ These five figures are worked out on paper in the driver's own comment
    block. If this test and that block ever disagree, the block is right and
    this is the bug — the whole point of the table is that a human checked it.
    """
    exp = E.expected_subtotals()
    assert exp["supply"] == E.paise(261000)
    assert exp["install"] == E.paise(46800)
    assert exp["total"] == E.paise(307800)


def test_the_sections_foot_to_the_document_total():
    rows = E.expected_lines()
    a = sum(E.paise(r["supply_amount"]) + E.paise(r["install_amount"])
            for r in rows if r["section"] == "A")
    b = sum(E.paise(r["supply_amount"]) + E.paise(r["install_amount"])
            for r in rows if r["section"] == "B")
    assert a == E.paise(229400)
    assert b == E.paise(78400)
    assert a + b == E.expected_subtotals()["total"]


def test_the_specification_header_carries_no_money():
    """A header is the clause its sub-items are described by, never a priced row."""
    assert len(E.expected_lines()) == 5
    assert len(E.LINES) == 6
    assert sum(1 for li in E.LINES if li.get("is_header")) == 1


def test_the_schedule_really_does_carry_two_gst_rates():
    """
    Assertion 3 pins the rate-wise slab column footing to the document total,
    and a single-rate schedule would exercise none of it.
    """
    rates = {r["supply_gst_rate"] for r in E.expected_lines()}
    assert rates == {18, 12}


def test_the_schedule_prices_both_tracks_with_an_escalation_on_each():
    for li in E.LINES:
        if li.get("is_header"):
            continue
        assert li["supply_base_rate"] > 0
        assert li["install_base_rate"] > 0
        assert "supply_escalation_pct" in li
        assert "install_escalation_pct" in li


def test_no_posted_line_carries_a_rate_so_the_app_must_derive_it():
    """
    ⚠ This is the precondition that makes assertion 2a legitimate at all.
    `boq._clean_lines()` keeps a posted `supply_rate` verbatim and only derives
    one when it is absent. If a rate were posted, 2a would be asserting that
    the driver's own input survived the round trip — which is true of any input
    and proves nothing about the escalation.
    """
    for li in E.LINES:
        assert "supply_rate" not in li
        assert "install_rate" not in li


def test_the_priced_lines_have_distinct_quantities():
    """
    `line_map()` matches an item number to a server-minted `line_id` through
    its quantity. Two lines sharing one would make that mapping ambiguous.
    """
    qtys = [r["qty"] for r in E.expected_lines()]
    assert len(qtys) == len(set(qtys))


# =============================================================================
# GST — rounded ONCE PER SLAB, then summed
# =============================================================================

def test_gst_is_rounded_per_slab_then_summed():
    """
    `ra.compute_tax_totals()`'s rule. The rate-wise column on the printed sheet
    has to foot to the document total exactly, because GSTR-1 is filed rate-wise
    and the sheet is what those lines are read off.
    """
    claims = [(E.paise(119000), 18), (E.paise(67000), 12)]
    assert E.expected_gst(claims) == E.paise(21420) + E.paise(8040)
    assert E.expected_gst(claims) == E.paise(29460)


def test_two_rows_at_the_same_rate_are_ONE_slab_not_two():
    """
    ⚠ The distinction is not cosmetic, and this input is chosen to PROVE it is
    not. Two rows of ₹2.75 at 18%: rounded per line the tax is 0.495 → 50 paise
    twice, so 100 paise. Rounded once over the slab it is 0.99 → 99 paise. The
    two schemes give different money on the same claim, and the old per-LINE
    rounding accumulated 87 such roundings on the seeded schedule.

    An input where the two happen to agree would make this test vacuous, which
    is exactly what the first draft of it was.
    """
    rows = [(275, 18), (275, 18)]          # 275 paise = ₹2.75
    one_slab = E.expected_gst(rows)
    per_line = E.paise(275 * 18 / 10000.0) * 2
    assert one_slab == 99, "the slab is rounded once, over the sum"
    assert per_line == 100
    assert one_slab != per_line, (
        "this input no longer distinguishes the two rounding schemes, so the "
        "assertion above proves nothing — choose another")


def test_gst_on_nothing_is_nothing():
    assert E.expected_gst([]) == 0


# =============================================================================
# THE FORM PARSER
# =============================================================================

SAMPLE = """
<form action="/thing/create" method="post">
  <input type="text" name="date" value="2026-09-06"/>
  <input type="hidden" name="csrf_token" value="SECRET"/>
  <input type="checkbox" name="ticked" value="yes" checked/>
  <input type="checkbox" name="unticked" value="no"/>
  <input type="submit" name="go" value="Save"/>
  <select name="mode">
    <option value="neft">NEFT</option>
    <option value="cheque" selected>Cheque</option>
  </select>
  <textarea name="notes">hello</textarea>
</form>
"""


def test_the_parser_collects_hidden_fields():
    """
    ⚠ The whole reason for parsing rather than hand-assembling a dict: a CSRF
    token, or any other hidden state, travels through without the driver having
    to know it exists.
    """
    fields = dict(E.parse_forms(SAMPLE)[0]["fields"])
    assert fields["csrf_token"] == "SECRET"


def test_the_parser_takes_the_SELECTED_option_not_the_first():
    assert dict(E.parse_forms(SAMPLE)[0]["fields"])["mode"] == "cheque"


def test_an_unselected_select_falls_back_to_its_first_option():
    html = '<form><select name="s"><option value="a">A</option>' \
           '<option value="b">B</option></select></form>'
    assert dict(E.parse_forms(html)[0]["fields"])["s"] == "a"


def test_a_bare_option_submits_its_own_text():
    html = '<form><select name="s"><option>Plain</option></select></form>'
    assert dict(E.parse_forms(html)[0]["fields"])["s"] == "Plain"


def test_the_parser_reads_a_textarea_body():
    assert dict(E.parse_forms(SAMPLE)[0]["fields"])["notes"] == "hello"


def test_an_unticked_checkbox_is_not_submitted_and_a_ticked_one_is():
    """Exactly what a browser does. A driver that posted both would lie."""
    fields = dict(E.parse_forms(SAMPLE)[0]["fields"])
    assert fields["ticked"] == "yes"
    assert "unticked" not in fields


def test_a_submit_button_is_not_a_field():
    assert "go" not in dict(E.parse_forms(SAMPLE)[0]["fields"])


def test_the_parser_keeps_the_action_and_method():
    form = E.parse_forms(SAMPLE)[0]
    assert form["action"] == "/thing/create"
    assert form["method"] == "post"


def test_pick_form_finds_the_form_by_a_control_it_carries():
    html = ('<form id="one"><input name="alpha"></form>'
            '<form id="two"><input name="beta"></form>')
    assert E.pick_form(html, contains="beta")["id"] == "two"


def test_pick_form_says_what_it_saw_when_the_control_is_absent():
    """A LookupError naming the forms beats a KeyError three frames down."""
    html = '<form><input name="alpha"></form>'
    with pytest.raises(LookupError) as e:
        E.pick_form(html, contains="missing")
    assert "alpha" in str(e.value)


def test_pick_form_on_a_page_with_no_form_at_all():
    with pytest.raises(LookupError):
        E.pick_form("<p>nothing here</p>")


# =============================================================================
# THE PAYLOAD — overrides REPLACE, never append
# =============================================================================

def test_an_override_replaces_in_place_and_does_not_duplicate():
    """
    ⚠ Appending instead would post the field twice, and Flask's
    `request.form.get()` takes the FIRST — silently the old value. The bug
    would look like "my override was ignored".
    """
    form = E.parse_forms(SAMPLE)[0]
    pairs = E.form_payload(form, {"date": "2026-01-01"})
    names = [n for n, _ in pairs]
    assert names.count("date") == 1
    assert dict(pairs)["date"] == "2026-01-01"


def test_an_override_keeps_the_fields_position():
    form = E.parse_forms(SAMPLE)[0]
    before = [n for n, _ in E.form_payload(form, {})]
    after = [n for n, _ in E.form_payload(form, {"date": "x"})]
    assert before == after


def test_a_field_the_form_lacks_is_appended():
    form = E.parse_forms(SAMPLE)[0]
    pairs = E.form_payload(form, {"brand_new": "1"})
    assert ("brand_new", "1") in pairs


def test_every_other_field_survives_untouched():
    """
    The second reason §2.4 posts the whole form: a field the form gained since
    this file was last read must travel through rather than be dropped.
    """
    form = E.parse_forms(SAMPLE)[0]
    pairs = dict(E.form_payload(form, {"date": "x"}))
    assert pairs["csrf_token"] == "SECRET"
    assert pairs["mode"] == "cheque"
    assert pairs["notes"] == "hello"


# =============================================================================
# TEARDOWN ORDERING — the safety property
# =============================================================================

def test_teardown_is_in_reverse_dependency_order():
    """
    ⚠ A project purge has already been REFUSED once on this database because
    deleting it would have stranded a delivery challan, a measurement sheet and
    a draft PO. Every dependant must be gone before the thing it points at.
    """
    order = list(E.TEARDOWN_ORDER)
    assert order.index("receipts") < order.index("ra_bills")
    assert order.index("ra_bills") < order.index("boqs")
    assert order.index("delivery_challans") < order.index("boqs")
    assert order.index("measurements") < order.index("boqs")
    assert order.index("po_drafts") < order.index("boqs")
    assert order.index("boqs") < order.index("projects")


def test_the_plan_follows_that_order_whatever_order_it_was_given():
    inv = {"projects": ["p1"], "boqs": ["b1"], "ra_bills": ["r1"],
           "receipts": ["rc1"], "measurements": ["m1"],
           "delivery_challans": ["d1"], "po_drafts": ["po1"]}
    kinds = [k for k, _ in E.teardown_plan(inv)]
    assert kinds == list(E.TEARDOWN_ORDER)


def test_an_unknown_kind_is_REFUSED_and_not_silently_dropped():
    """
    ⚠ A kind nobody has placed in the chain is a kind whose safe position
    nobody has decided. Deleting it at a guessed point is how a document gets
    orphaned; ignoring it is how one gets left behind. Both are refused.
    """
    with pytest.raises(ValueError) as e:
        E.teardown_plan({"invoices": ["i1"]})
    assert "invoices" in str(e.value)
    assert "TEARDOWN_ORDER" in str(e.value)


def test_an_empty_inventory_plans_nothing():
    assert E.teardown_plan({}) == []
    assert E.teardown_plan({k: [] for k in E.TEARDOWN_ORDER}) == []


def test_every_kind_in_the_order_has_a_delete_route():
    """A kind with no route would be planned and then silently skipped."""
    assert set(E.DELETE_ROUTES) == set(E.TEARDOWN_ORDER)
    for route in E.DELETE_ROUTES.values():
        assert "{id}" in route


# =============================================================================
# READING FIGURES OFF A PAGE
# =============================================================================

def test_money_after_finds_the_figure_following_its_label():
    html = "<tr><td>Subtotal</td><td>3,07,800.00</td></tr>"
    assert E.money_after(html, "Subtotal") == E.paise(307800)


def test_money_after_returns_None_rather_than_guessing():
    """
    ⚠ The driver records SKIP on a None. A helper that returned 0 instead would
    turn "I could not find the figure" into "the figure is zero", and an
    assertion comparing it against an expected 0 would report PASS.
    """
    assert E.money_after("<p>no money here</p>", "Subtotal") is None
    assert E.money_after("<td>Subtotal</td><td>—</td>", "Subtotal") is None


def test_money_after_can_take_a_later_occurrence():
    html = "<td>Total</td><td>1.00</td><td>Total</td><td>2.00</td>"
    assert E.money_after(html, "Total", 1) == 100
    assert E.money_after(html, "Total", 2) == 200


def test_text_of_strips_tags_and_decodes_the_house_entities():
    # A tag becomes a space, so adjacent inline elements do not run their words
    # together — "<td>Total</td><td>1.00</td>" has to read as two things.
    assert E.text_of("<b>A</b>&nbsp;&amp;<i>B</i>") == "A & B"
    assert E.text_of("<td>Subtotal</td><td>1.00</td>") == "Subtotal 1.00"


def test_all_money_reads_every_figure_in_order():
    assert E.all_money("<td>1.00</td><td>2,000.50</td>") == [100, 200050]


# =============================================================================
# THE TALLY
# =============================================================================

def test_a_failing_check_is_recorded_as_a_failure():
    t = E.Tally()
    t.check("x", 1, 2)
    assert len(t.failures) == 1


def test_a_passing_check_is_not():
    t = E.Tally()
    t.check("x", 1, 1)
    assert t.failures == []


def test_a_KNOWN_BAD_that_disagrees_as_predicted_does_not_fail_the_run():
    """Gap 31 is open. The line records it without turning the run red."""
    t = E.Tally()
    t.known_bad("gap 31", "100.00", "100.00")
    assert t.failures == []


def test_a_KNOWN_BAD_that_STOPS_disagreeing_as_predicted_DOES_fail():
    """
    ⚠ This is the whole mechanism: the day gap 31 is fixed the delta stops
    matching and the line flips to FAIL, which is the notification. A line that
    merely said "this is broken" would say it forever and tell us nothing.
    """
    t = E.Tally()
    t.known_bad("gap 31", "100.00", "0.00")
    assert len(t.failures) == 1


def test_a_SKIP_is_neither_a_pass_nor_a_failure():
    t = E.Tally()
    t.skip("x", "no figure on the page")
    assert t.failures == []
    assert "1 skipped" in t.summary()


def test_the_summary_counts_every_verdict():
    t = E.Tally()
    t.check("a", 1, 1)
    t.check("b", 1, 2)
    t.known_bad("c", "x", "x")
    t.skip("d", "why")
    assert t.summary() == "1 passed, 1 failed, 1 known-bad, 1 skipped"


# =============================================================================
# THE CLI'S OWN REFUSALS
# =============================================================================

def test_run_without_a_tag_is_refused():
    """
    ⚠ An untagged run writes records into the live database that nobody can
    find again. The tag is what makes the run recoverable by eye.
    """
    with pytest.raises(SystemExit) as e:
        E.main(["--run"])
    assert e.value.code != 0


def test_teardown_without_a_tag_is_refused():
    with pytest.raises(SystemExit) as e:
        E.main(["--teardown"])
    assert e.value.code != 0


def test_doing_nothing_at_all_is_refused():
    with pytest.raises(SystemExit) as e:
        E.main([])
    assert e.value.code != 0


def test_credentials_come_from_the_environment(monkeypatch):
    """
    ⚠ A password in a committed file is a password in the git history forever.
    `_creds()` is the only place they are read, and it reads `os.environ`.
    """
    monkeypatch.setenv("SF_E2E_USER_A", "someone")
    monkeypatch.setenv("SF_E2E_PASS_A", "from-the-environment")

    class Args:
        user_a = pass_a = ""
    assert E._creds(Args(), "a") == ("someone", "from-the-environment")


def test_a_cli_flag_beats_the_environment(monkeypatch):
    monkeypatch.setenv("SF_E2E_USER_A", "env")
    monkeypatch.setenv("SF_E2E_PASS_A", "envpass")

    class Args:
        user_a = "flag"
        pass_a = "flagpass"
    assert E._creds(Args(), "a") == ("flag", "flagpass")


def test_no_password_literal_is_written_into_the_module():
    """
    The env var NAMES are built with an f-string (`SF_E2E_PASS_{slot.upper()}`),
    so this greps for what must never appear rather than for what must.
    """
    src = pathlib.Path(E.__file__).read_text(encoding="utf-8")
    assert "SF_E2E_PASS" in src, "credentials must be read from the environment"
    for forbidden in ('SF_E2E_PASS_A=', 'SF_E2E_PASS_A ='
                      , 'password="', "password='", 'passwd=', 'pwd='):
        assert forbidden not in src, f"{forbidden!r} looks like a literal secret"


def test_the_driver_never_stores_a_password_on_the_session():
    """
    `Session.login()` takes the password as an argument and keeps no reference,
    so it cannot reach a traceback, a `repr`, or a log line by accident.
    """
    s = E.Session("http://127.0.0.1:5000", "A")
    assert not any("pass" in k.lower() for k in vars(s)), sorted(vars(s))


# =============================================================================
# THE BOQ LINE PICKER — the driver's one real defect, 8 September 2026
# =============================================================================
#
# `line_qty()` looked for `data-line-id`, an attribute this application has
# never emitted anywhere. It found nothing, fell through to a positional zip
# over an empty id list, posted `{"lines": []}`, and `boqpick.picked_lines()`
# refused it with "Nothing is ticked" — which the driver then reported as the
# measurement sheet having failed to create. It was never caught because the
# driver had never been run.
#
# The markup below is copied from a real `/measurement/create?boq=…` response.

PICKER_HTML = """
<table><tbody>
<tr class="pk-head is-spec" id="head_a9080e547722" data-open="0"
    onclick="toggleFamily('a9080e547722')">
  <td class="pk-tick"></td>
  <td class="pk-no"><span class="pk-chev" id="chev_a9080e547722">&#9656;</span>1</td>
  <td colspan="4"><span class="pk-tag">spec &middot; 2 items</span></td>
</tr>
<tr class="pk-row is-child" id="row_853039176f2f" style="display:none;">
  <td class="pk-tick"><input type="checkbox" id="c_853039176f2f" checked
      onchange="tick('853039176f2f')" aria-label="Include this line"/></td>
  <td class="pk-no">1.1</td>
  <td class="pk-desc"><span class="pk-clamp">100 NB MS pipe, ISI</span></td>
  <td class="pk-unit">Mtrs</td>
  <td class="pk-avail">100</td>
  <td class="pk-in"><input type="text" inputmode="decimal" id="q_853039176f2f"
      value="100" aria-label="Measured quantity"/></td>
</tr>
<tr class="pk-row" id="row_a54fd531586d">
  <td class="pk-tick"><input type="checkbox" id="c_a54fd531586d"
      onchange="tick('a54fd531586d')" aria-label="Include this line"/></td>
  <td class="pk-no">2</td>
  <td class="pk-desc"><span class="pk-clamp">Hydrant valve, 63 mm</span></td>
  <td class="pk-unit">Nos</td>
  <td class="pk-avail">20</td>
  <td class="pk-in"><input type="text" inputmode="decimal" id="q_a54fd531586d"
      value="20" aria-label="Measured quantity"/></td>
</tr>
</tbody></table>
"""


def test_picker_rows_reads_the_ids_the_app_actually_emits():
    rows = E.picker_rows(PICKER_HTML)
    assert [r["line_id"] for r in rows] == ["853039176f2f", "a54fd531586d"]
    assert [r["item_no"] for r in rows] == ["1.1", "2"]
    assert [r["qty"] for r in rows] == ["100", "20"]
    assert [r["avail"] for r in rows] == ["100", "20"]


def test_picker_rows_drops_the_specification_HEADER():
    """
    ⚠ The header carries a line id too, and claiming against it is meaningless
    — it has no quantity and `boqpick` never counts it toward a line total. It
    is excluded by having no quantity box, not by its item number, so a header
    numbered like a priced line cannot slip through.
    """
    rows = E.picker_rows(PICKER_HTML)
    assert "a9080e547722" not in [r["line_id"] for r in rows]
    assert len(rows) == 2, "the spec header was returned as a claimable line"


def test_picker_rows_reports_the_tick_state_per_row():
    """Row 1.1 is checked and row 2 is not; a parser that assumed all-ticked
    would post a claim against a line the operator had cleared."""
    rows = E.picker_rows(PICKER_HTML)
    assert [r["checked"] for r in rows] == [True, False]


def test_picker_rows_on_a_page_with_no_grid_is_empty_not_an_error():
    assert E.picker_rows("<p>no picker here</p>") == []
    assert E.picker_rows("") == []


def test_the_dead_attribute_is_gone_from_the_driver():
    """
    ⚠ **The regression guard, and the point of the whole entry.**
    `data-line-id` is emitted by no module in this application. A driver
    reaching for it again would silently claim nothing at all.

    Read from the **AST**, not by string search, for the reason
    `tests/test_auth.py` gives about the demo secret key: the comment above
    `picker_rows()` names the dead attribute while explaining where it went,
    and that comment is the fix rather than the defect. A comment is not in the
    AST, so this asks the only question that matters — is the string live code
    in this module.
    """
    import ast

    src = (REPO / "tools" / "e2e_chain.py").read_text(encoding="utf8")
    offenders = [
        node.lineno for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "data-line-id" in node.value
    ]
    assert not offenders, (
        f"data-line-id is a live string literal at line(s) {offenders}; no "
        f"module in this application emits that attribute")


# =============================================================================
# THE RA CHIP STRIP — gap 31's assertion, after the fix
# =============================================================================

CHIP_HTML = """
<div class="bp-cell"><div class="bp-lbl">Total Basic Value</div>
  <div class="bp-val">&#8377;&nbsp;9,585</div><div class="bp-sub">taxes extra</div></div>
<div class="ra-block"><span class="ra-lbl">Running Account bills raised</span>
<div class="ra-strip"><a class="ra-chip" href="/ra/view/x">RA1 &middot; SF/RA/26-27/0006
&middot; &#8377;&nbsp;750</a><a class="ra-chip" href="/ra/view/y">RA2 &middot;
SF/RA/26-27/0007 &middot; &#8377;&nbsp;8,835</a></div></div>
"""


def test_chip_total_sums_only_the_strip_not_the_whole_panel():
    """
    ⚠ The *Total Basic Value* tile is in this fixture ON PURPOSE. A reader that
    matched money across the panel would add ₹9,585 of schedule to ₹9,585 of
    claims and report ₹19,170 — and, on a BOQ claimed to completion, would do
    it while looking exactly like a correct answer.
    """
    assert E._chip_total(CHIP_HTML) == E.paise(9585)


def test_chip_total_is_None_when_there_is_no_strip():
    """A SKIP, never a zero — a zero would compare equal to an empty claim."""
    assert E._chip_total("<p>no bills raised</p>") is None
    assert E._chip_total("") is None


# =============================================================================
# WHOLE-RUPEE FIGURES — what the screens actually print
# =============================================================================

def test_money_after_reads_a_figure_with_no_paise_on_it():
    """
    `/boq/view` renders `{:,.0f}` — "₹ 307,800", no decimals — so the original
    pattern, which required `.dd`, could not see the one figure assertions 1
    and 7 are about.
    """
    html = '<div class="bp-lbl">Total Basic Value</div><div>&#8377;&nbsp;307,800</div>'
    assert E.money_after(html, "Total Basic Value") == E.paise(307800)


def test_money_after_still_reads_the_printed_documents_paise():
    """The sheets DO carry paise, and that path is unchanged."""
    assert E.money_after("<td>Subtotal</td><td>3,07,800.00</td>",
                         "Subtotal") == E.paise(307800)
    assert E.money_after("<td>Total</td><td>&#8377;&nbsp;1,234.56</td>",
                         "Total") == E.paise(1234.56)


def test_money_after_does_not_read_a_stylesheet_as_money():
    """
    ⚠ **THE FIRST RUN OF THIS DRIVER REPORTED ₹2,55,25,525.55 AS A BOQ
    SUBTOTAL.** `money_after` found nothing, the caller fell back to
    `max(all_money(...))`, and the largest "money" on the page was the `.55` of
    an `rgba(255,255,255,.55)`. The fallback is deleted; this pins the reason.
    """
    css = "<style>.x { background: rgba(255,255,255,.55); }</style>"
    assert E.money_after(css, "Total Basic Value") is None


def test_money_after_takes_the_nearer_figure_when_both_forms_are_present():
    """
    Both patterns are searched and the EARLIER match wins. A rupee-signed
    figure further down the page must not beat a plain one beside the label.
    """
    html = "<td>Total</td><td>12.00</td><td>&#8377;&nbsp;999</td>"
    assert E.money_after(html, "Total") == E.paise(12)


def test_records_of_one_kind_are_torn_down_NEWEST_FIRST():
    """
    ⚠ **Measured against the live app, 8 September 2026.** Deleting RA3 while
    RA4 existed was refused in terms: *"Only the latest bill can be deleted,
    and RA3 is not it — RA4 sits after it. RA bills are cumulative, so removing
    RA3 now would leave a gap in the sequence and change every later bill's
    balance."*

    `chain.made` appends in creation order, so walking it forward stalls on the
    first record something later depends on. This is the same reverse-dependency
    rule `TEARDOWN_ORDER` encodes between kinds, applied within one.
    """
    inv = {k: [] for k in E.TEARDOWN_ORDER}
    inv["ra_bills"] = ["ra1", "ra2", "ra3", "ra4"]
    plan = E.teardown_plan(inv)

    assert [rid for _, rid in plan] == ["ra4", "ra3", "ra2", "ra1"], (
        "RA bills must be deleted newest first; only the latest may go")


def test_the_kind_order_still_wins_over_the_within_kind_order():
    """Reversing inside a kind must not disturb the ordering between kinds."""
    inv = {k: [] for k in E.TEARDOWN_ORDER}
    inv["ra_bills"] = ["ra1", "ra2"]
    inv["boqs"] = ["b1", "b2"]
    plan = E.teardown_plan(inv)

    assert plan == [("ra_bills", "ra2"), ("ra_bills", "ra1"),
                    ("boqs", "b2"), ("boqs", "b1")]


def test_every_kind_has_a_route_that_can_confirm_the_delete():
    """
    ⚠ A delete counted from the ABSENCE of an error is not a delete. Two runs'
    BOQs were reported torn down and were in the register the whole time,
    because `/boq/delete/<id>` does not exist and the closed-app gate answers
    an unrouted address with a redirect to the dashboard rather than a 404.
    """
    assert set(E.VERIFY_ROUTES) == set(E.TEARDOWN_ORDER), (
        "a kind with no verification route would be reported deleted on trust")


# =============================================================================
# THE RECEIPT CHOOSER — where the outstanding figure actually lives
# =============================================================================

CHOOSER_HTML = """
<table><thead><tr><th>Bill</th><th>Reference</th><th>Project</th>
<th>Billed</th><th>Outstanding</th></tr></thead><tbody>
<tr><td>RA1</td><td>SF/RA/26-27/0001</td><td>Sify Bangalore</td>
    <td>9,35,336.00</td><td>9,35,336.00</td>
    <td><a href="/receipt/new?ra=other-bill">Record</a></td></tr>
<tr><td>RA1</td><td>SF/RA/26-27/0008</td><td>E2E Chain</td>
    <td>88,500.00</td><td>44,250.00</td>
    <td><a href="/receipt/new?ra=our-bill">Record</a></td></tr>
</tbody></table>
"""


def test_chooser_row_reads_billed_and_outstanding_for_ONE_bill():
    assert E.chooser_row(CHOOSER_HTML, "our-bill") == (
        E.paise(88500), E.paise(44250))


def test_chooser_row_does_not_return_a_different_bills_figures():
    """
    ⚠ Every bill in the install is on this page. A reader that matched the
    first row would report ₹9,35,336 of somebody else's schedule as this
    chain's outstanding, and it would look entirely plausible.
    """
    assert E.chooser_row(CHOOSER_HTML, "other-bill") == (
        E.paise(935336), E.paise(935336))


def test_chooser_row_is_None_for_a_bill_that_is_not_listed():
    """A SKIP, never a zero — zero is a fully-settled bill, a real state."""
    assert E.chooser_row(CHOOSER_HTML, "no-such-bill") is None
    assert E.chooser_row("", "our-bill") is None


# =============================================================================
# THE DASHBOARD'S PROGRESS BAND — scoped, because the name appears twice
# =============================================================================

DASH_HTML = """
<div class="panel"><h3>Recent BOQ &amp; RA activity</h3>
  <div>E2E Chain E2E-1 &middot; Supply &#8377;&nbsp;1.86 L 09 Sep 2026 SF/RA/26-27/0009</div>
  <div>Sify Bangalore &middot; Supply &#8377;&nbsp;8.45 L</div>
</div>
<div class="panel"><h3>Claimed against approved</h3>
  <div class="pp-row"><div class="pp-hd"><span class="pp-name">Unassigned</span>
    <span class="pp-fig">&#8377;&nbsp;3.08 L of &#8377;&nbsp;94.99 L</span></div>
    <div class="bar"></div><div class="pp-note">3% claimed</div></div>
  <div class="pp-row"><div class="pp-hd"><span class="pp-name">Work2</span>
    <span class="pp-fig">&#8377;&nbsp;9,585 of &#8377;&nbsp;9,585</span></div>
    <div class="bar"></div><div class="pp-note">100% claimed</div></div>
</div>
"""


def test_progress_rows_reads_the_band_and_only_the_band():
    rows = E.progress_rows(DASH_HTML)
    assert [r["name"] for r in rows] == ["Unassigned", "Work2"]
    assert rows[1]["note"] == "100% claimed"


def test_each_project_is_paired_with_its_OWN_share():
    """
    ⚠ **The load-bearing property, and the one worth mutating.** Reading the
    right names and the right notes is not enough if a row can end up carrying
    a neighbour's figure: this band is where "is this project fully claimed"
    gets answered, and *Unassigned* sits directly above the project whose
    claims it has absorbed. Pairing each name with the note from its own row is
    the whole of the helper.
    """
    rows = E.progress_rows(DASH_HTML)
    paired = {r["name"]: r["note"] for r in rows}

    assert paired == {"Unassigned": "3% claimed", "Work2": "100% claimed"}
    assert len(rows) == 2, "rows were collapsed or split"
    assert paired["Unassigned"] != paired["Work2"], (
        "both rows carry the same share; the pairing has collapsed")


def test_a_project_only_in_the_activity_list_is_not_on_the_band():
    """
    ⚠ **This is the bug the helper exists to stop.** "E2E Chain E2E-1" appears
    on the page — in the activity list — and the next "% claimed" after it
    belongs to *Unassigned*. Reading the page as flat text reported 3% for a
    project that has no row at all, which is a wrong answer rather than a
    missing one.
    """
    rows = E.progress_rows(DASH_HTML)
    assert not [r for r in rows if r["name"] == "E2E Chain E2E-1"]


def test_progress_rows_on_a_page_with_no_band_is_empty():
    assert E.progress_rows("<p>nothing here</p>") == []
