"""
tests/test_demo_data_flag.py — demo data is OFF by default, 25 September 2026
=============================================================================

ABOUT.md §7 gap 35: *"A brand new install fills itself with 84 demo records —
including another company's ₹91.9 lakh BOQ — and deleting them does not make
them stay deleted."* This file is the OFF state, and `tests/conftest.py` forces
the flag ON for every other file in the suite, exactly as `catalogue_unhidden`
and `ladder_on` do for the other two switches.

Two separate claims, and they fail for different reasons:

1. **Nothing demo is seeded** when `SAMRUDDHI_DEMO_DATA` is off — products,
   addresses, the Sify BOQ and the specimen company identity.
2. **Everything GENUINE is still seeded** — the spec library (56 clauses; the
   quotation picker has been written from it since 12 September 2026), the
   charge heads, the measurement grid columns.

⚠ **The flag is set with `monkeypatch`, which undoes it per test.**
  `auth.demo_data_on()` re-reads `os.getenv` on every call and caches nothing,
  which is what makes that work — the same property `attachment.root()` and
  `auth.session_cookie_config()` are written for and for the same reason.

⚠ **`_reset()` clears the seed flags as well as the collections.** The guards
  are `if STORE["_seeded"]: return`, so a test that cleared `products` without
  clearing `_seeded` would prove nothing: the seeder would decline to run for
  the wrong reason and the test would pass with the flag ON.
"""

import pathlib
import re

import pytest

import address
import auth
import boq as BQ
import branding as B
import settings as ST
import spec
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

# The four DEMO seeders, and the store key each one fills. `product` is reached
# through its guard rather than its function, because `product.py` is frozen
# and is disarmed from `app._boot_persistence()` instead — see `app.py`.
DEMO_FLAGS = ("_seeded", "_addr_seeded", "_boq_seeded", "_settings_seeded")


def _reset():
    """An empty store, with every seed flag down. A brand new install."""
    for key in ("products", "addresses", "boqs", "specs", "settings"):
        STORE[key].clear()
    for flag in DEMO_FLAGS + ("_spec_seeded",):
        STORE[flag] = False


def _boot_and_seed():
    """
    Every seeder a fresh install reaches, in the order the application does.

    ⚠ **`app.disarm_frozen_demo_seeder()` is the FIRST call and it has to be.**
      `product.py` is frozen, so its seeder has no flag check of its own —
      `_boot_persistence()` pre-sets the guard it already carries. A test that
      skipped this step would be asking the seeder a question the running
      application never asks it.
    """
    import app as app_module
    import product

    app_module.disarm_frozen_demo_seeder()
    ST.ensure_demo_settings()
    product.ensure_demo_products()
    address.ensure_demo_addresses()
    spec.ensure_demo_specs()
    BQ.ensure_demo_boq()


@pytest.fixture()
def demo_off(monkeypatch):
    monkeypatch.setenv("SAMRUDDHI_DEMO_DATA", "false")
    _reset()
    yield
    _reset()


@pytest.fixture()
def demo_on(monkeypatch):
    monkeypatch.setenv("SAMRUDDHI_DEMO_DATA", "true")
    _reset()
    yield
    _reset()


# ── 1. The default, which is the whole point ───────────────────────────────

def test_the_default_is_OFF_and_that_is_the_deliberate_asymmetry(monkeypatch):
    """
    ⚠ **The headline.** Every other flag in `auth.py` defaults to the local-dev
    value because a default that breaks `python app.py` gets deleted. This one
    is the other way round: the failure that matters is a client box nobody
    configured, and the safe side of that failure is the side that grows no
    data.
    """
    monkeypatch.delenv("SAMRUDDHI_DEMO_DATA", raising=False)
    assert auth.DEMO_DATA_DEFAULT is False
    assert auth.demo_data_on() is False


def test_a_blank_value_means_unset_rather_than_false(monkeypatch):
    """`SAMRUDDHI_DEMO_DATA=` is an operator who left the line in, not one who
    set it to false — and both answer the same way here, which is why this is
    asserted rather than assumed."""
    monkeypatch.setenv("SAMRUDDHI_DEMO_DATA", "   ")
    on, problems = auth.demo_data_config()
    assert on is False
    assert problems == []


@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
    ("false", False), ("FALSE", False), ("0", False), ("no", False), ("off", False),
])
def test_the_usual_spellings_of_a_boolean_are_read(monkeypatch, raw, expected):
    monkeypatch.setenv("SAMRUDDHI_DEMO_DATA", raw)
    assert auth.demo_data_on() is expected


def test_an_unparseable_value_is_REPORTED_and_never_silently_true(monkeypatch):
    """
    ⚠ **The one misconfiguration with no symptom at all.**
    `SAMRUDDHI_DEMO_DATA=ture` resolved by truthiness would seed another
    company's ₹91.9 lakh BOQ onto a client's server and say nothing. It falls
    back to the default — which is OFF — and names the value.
    """
    monkeypatch.setenv("SAMRUDDHI_DEMO_DATA", "ture")
    on, problems = auth.demo_data_config()
    assert on is False, "an unparseable value must never resolve to True"
    assert len(problems) == 1
    assert "SAMRUDDHI_DEMO_DATA" in problems[0] and "ture" in problems[0]


def test_the_config_form_has_no_side_effect_so_it_can_be_read_twice(monkeypatch):
    """`demo_data_config()` is the form the tests read, precisely because
    `demo_data_on()` prints a warning once per process and a once-only side
    effect cannot be asserted twice."""
    monkeypatch.setenv("SAMRUDDHI_DEMO_DATA", "nonsense")
    assert auth.demo_data_config() == auth.demo_data_config()


# ── 2. With the flag OFF, nothing demo is seeded ───────────────────────────

def test_nothing_demo_is_seeded_with_the_flag_off(demo_off):
    """
    The four page visits gap 35 reproduces with, measured against the figures
    that entry states: 12 products, 6 addresses, 1 BOQ, 84 records in total.
    """
    _boot_and_seed()
    assert STORE["products"] == {}, "12 demo products seeded with the flag off"
    assert STORE["addresses"] == {}, "6 demo addresses seeded with the flag off"
    assert STORE["boqs"] == {}, "the Sify BOQ was seeded with the flag off"


def test_the_specimen_company_identity_is_not_seeded_with_the_flag_off(demo_off):
    """
    ⚠ The GSTIN `27AAAAA0000A1Z5`, `SPECIMEN BANK LTD.` and account
    `50200000000000` print on a customer's tax invoice. DEPLOY.md §6.3 is the
    operational consequence.
    """
    ST.ensure_demo_settings()
    assert ST.RECORD_ID not in STORE["settings"]
    assert ST.load_saved() == {}


def test_the_demo_seeders_are_all_reachable_and_this_test_is_not_vacuous(demo_on):
    """
    ⚠ **The non-vacuity guard for every test above it.** If `_boot_and_seed()`
    stopped calling a seeder, or a seeder stopped writing, the OFF tests would
    pass for the wrong reason. This asserts the same calls DO fill the store
    when the flag is on, with gap 35's own figures.
    """
    _boot_and_seed()
    assert len(STORE["products"]) == 12, "gap 35 measured 12 demo products"
    assert len(STORE["addresses"]) == 6, "gap 35 measured 6 demo addresses"
    assert len(STORE["boqs"]) == 1, "gap 35 measured 1 demo BOQ"
    assert ST.RECORD_ID in STORE["settings"], "the specimen identity"
    assert STORE["settings"][ST.RECORD_ID]["COMPANY_GSTIN"] == "27AAAAA0000A1Z5"


# ── 3. With the flag OFF, every GENUINE DEFAULT is still seeded ────────────

def test_the_spec_library_is_a_genuine_default_and_is_still_seeded(demo_off):
    """
    ⚠ **56 clauses, and they are not optional.** The BOQ picker has always been
    written from the library, and since 12 September 2026 so has the quotation
    picker (`specpick.py`, while the catalogue is hidden). An empty library on
    a fresh install is an empty picker on both.
    """
    _boot_and_seed()
    assert len(STORE["specs"]) == 56, "the spec library must seed with demo off"


def test_the_boq_seeder_still_seeds_the_library_even_though_it_seeds_no_boq(demo_off):
    """
    ⚠ **The ordering bug this catches is a one-line mistake.** Five `boq.py`
    routes reach the library ONLY through `ensure_demo_boq()`. Putting the flag
    check above `ensure_demo_specs()` would leave the picker empty on exactly
    the install this flag exists for.
    """
    STORE["specs"].clear()
    STORE["_spec_seeded"] = False
    BQ.ensure_demo_boq()
    assert len(STORE["specs"]) == 56, (
        "ensure_demo_boq() must still seed the library with demo data off — "
        "ensure_demo_specs() belongs ABOVE the flag check")
    assert STORE["boqs"] == {}, "...and must still seed no BOQ"


def test_the_charge_heads_are_a_genuine_default_and_are_still_seeded(demo_off):
    """`/charge/new` renders a dropdown from these. An empty list is an
    unusable page, and there is nothing of anybody else's in a list of expense
    categories."""
    ST.ensure_demo_settings()
    assert ST.CHARGE_HEADS_RECORD in STORE["settings"]
    assert ST.charge_heads() == list(ST.DEFAULT_CHARGE_HEADS)
    assert ST.charge_heads(), "the charge heads must not be empty"


def test_the_measurement_grid_columns_are_a_genuine_default(demo_off):
    """They are a module constant with a settings override, not a seeded row,
    so the flag cannot reach them — asserted rather than assumed, because the
    joint measurement sheet is unrenderable without them."""
    assert len(ST.measurement_columns()) == len(ST.DEFAULT_MEASUREMENT_COLUMNS)
    assert ST.measurement_columns(), "the grid columns must not be empty"


# ── 4. A delete stays deleted across a restart ─────────────────────────────

def test_a_deleted_record_stays_deleted_across_a_restart(demo_off):
    """
    ⚠ **The half of gap 35 that made deleting pointless.** The seed flags are
    deliberately not persisted (`db.py`), so `STORE["_seeded"]` went with the
    process and the seeders re-ran: *"Delete the 12 demo products, restart,
    visit `/`, and they are back."*

    A restart is simulated the way one actually behaves — the collections
    survive (they came out of MySQL), the seed flags do not.
    """
    import app as app_module
    import product

    # A box that booted once with the demo on.
    STORE["_seeded"] = False
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SAMRUDDHI_DEMO_DATA", "true")
        app_module.disarm_frozen_demo_seeder()
        product.ensure_demo_products()
    assert len(STORE["products"]) == 12

    # The operator deletes them at go-live.
    STORE["products"].clear()

    # RESTART: the collections reload from MySQL, the seed flags do not persist.
    for flag in DEMO_FLAGS:
        STORE[flag] = False
    app_module.disarm_frozen_demo_seeder()
    product.ensure_demo_products()

    assert STORE["products"] == {}, (
        "the demo products came back after a restart — this is exactly the "
        "behaviour gap 35 reports, and the flag is what stops it")


def test_the_same_delete_does_NOT_stay_deleted_with_the_flag_on(demo_on):
    """
    ⚠ **The mutation proof for the test above, kept as a test.** With the flag
    ON the records come straight back, which is the documented pre-25-September
    behaviour. If this ever goes green the guard above has stopped guarding.
    """
    import app as app_module
    import product

    app_module.disarm_frozen_demo_seeder()
    product.ensure_demo_products()
    STORE["products"].clear()
    for flag in DEMO_FLAGS:
        STORE[flag] = False
    app_module.disarm_frozen_demo_seeder()
    product.ensure_demo_products()
    assert len(STORE["products"]) == 12, (
        "with demo data ON a delete must still be undone by a restart — "
        "if this fails, the OFF test above proves nothing")


# ── 5. product.py is frozen, and is disarmed from outside ──────────────────

def test_product_py_is_not_edited_and_the_disarm_lives_in_app_py():
    """
    ⚠ **`product.py` is frozen (INTRODUCTION.md §7) and this pass did not touch
    it.** The seeder is disarmed by pre-setting the flag it already guards
    itself with, from `app._boot_persistence()` — the same trick the catalogue
    hide used on 11 September 2026.
    """
    src = (REPO / "product.py").read_text(encoding="utf8")
    assert "SAMRUDDHI_DEMO_DATA" not in src
    assert "demo_data_on" not in src, "product.py is frozen and must not be edited"

    app_src = (REPO / "app.py").read_text(encoding="utf8")
    assert re.search(r'if not auth\.demo_data_on\(\):\s*\n\s*STORE\["_seeded"\] = True',
                     app_src), (
        "app.disarm_frozen_demo_seeder() must pre-set STORE['_seeded'] when "
        "demo data is off — it is the only way to reach the frozen seeder")


def test_the_boot_sequence_actually_calls_the_disarm():
    """
    ⚠ **Without this the two tests either side of it prove nothing on a real
      boot.** They call `disarm_frozen_demo_seeder()` themselves, so they stay
      green even if `_boot_persistence()` never calls it — which is a client
      box seeding twelve demo products at boot with a green suite behind it.
      Found by mutation on 25 September 2026: deleting the call from
      `_boot_persistence()` was MISSED until this was written.

    Read from `inspect.getsource` of the function rather than by searching the
    whole file, because the name appears in the definition above it and a
    file-wide search matches that instead — which is precisely how the first
    version of this check passed against the mutation.
    """
    import inspect

    import app as app_module

    # Statements only. Both names appear in this function's comments too, and
    # a raw index into the source finds the comment rather than the call.
    calls = [ln.strip() for ln in
             inspect.getsource(app_module._boot_persistence).splitlines()
             if ln.strip() and not ln.strip().startswith("#")]

    assert "disarm_frozen_demo_seeder()" in calls, (
        "_boot_persistence() does not call disarm_frozen_demo_seeder(). "
        "Nothing else runs before the first request, so the frozen "
        "product seeder is live on a client box with demo data off.")
    # ...and before the identity seeder, which is the only ordering it has.
    assert calls.index("disarm_frozen_demo_seeder()") < calls.index("ensure_demo_settings()"), (
        "the disarm must run before ensure_demo_settings(), which is the "
        "first thing at boot that can reach a seeder")


def test_the_disarm_actually_stops_every_frozen_call_site(demo_off):
    """
    The trick only works because the guard is the FIRST statement of
    `ensure_demo_products()`. Asserted against the real function rather than
    against `app.py`'s source, so a change to the guard is caught here.
    """
    import app as app_module
    import product

    app_module.disarm_frozen_demo_seeder()
    assert STORE["_seeded"] is True, "the disarm did not set the guard"
    product.ensure_demo_products()
    assert STORE["products"] == {}


# ── 6. Blank identity renders — no crash, no leftover SPECIMEN string ──────

SPECIMEN_STRINGS = ("27AAAAA0000A1Z5", "SPECIMEN BANK LTD", "50200000000000",
                    "SPEC0000000", "AAAAA0000A", "Ganesh Industrial Estate")


def test_branding_defaults_are_blank_so_a_cleared_field_does_not_fall_back_to_specimen():
    """
    ⚠ **DEPLOY.md §6.3 asserted the opposite and was wrong.** It said a blank
    field *"falls back to the DEFAULTS snapshot (branding.py:104-111) — which
    is the specimen value, not nothing."* `branding.DEFAULTS` is snapshotted
    from the module's own import-time values, and those are `""` for every
    statutory field. The specimen values only ever lived in
    `settings.DEMO_COMPANY` and in the stored record.
    """
    for key in ("COMPANY_LEGAL", "COMPANY_ADDR", "COMPANY_WEB", "COMPANY_GSTIN",
                "COMPANY_PAN", "COMPANY_BRANCHES", "BANK_NAME",
                "BANK_ACCOUNT_NAME", "BANK_ACCOUNT_NO", "BANK_IFSC",
                "BANK_BRANCH"):
        assert B.DEFAULTS[key] == "", (
            f"branding.DEFAULTS[{key!r}] is {B.DEFAULTS[key]!r} — a cleared "
            f"field would fall back to it and print on a customer's invoice")


def test_a_blank_identity_renders_the_amber_todo_chip_and_not_an_empty_string():
    """Blank means the existing amber marker — the thing that stops a document
    going out silently empty — rather than nothing at all."""
    assert "todo-chip" in B.field("", "GSTIN")
    assert "todo-chip" not in B.field("27AAAAA0000A1Z5", "GSTIN")
