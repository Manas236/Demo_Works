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
