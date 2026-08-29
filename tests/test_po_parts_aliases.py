"""
tests/test_po_parts_aliases.py — the alias rule, enforced
=========================================================

⚠ **THIS FILE IS THE DELIVERABLE, not the cutback it accompanies.**

`po_parts.py` shipped on 29 August 2026 with 73 canonical parts and **172
aliases, 156 of which nobody had written.** They were plausible-looking
permutations — word order reversed, a space added, `mm` swapped for `inch` —
generated to widen the prefill. Deleting them is a one-off; **stopping the next
pass from regenerating them is not**, and that is what these tests are for.

The rule, from `po_parts.py`'s own docstring:

    An alias may exist only if the client wrote that exact string. The one
    permitted derivation is a line whose trailing QUANTITY was dropped, which
    may also be reached without it — and both such lines are named in
    `CLIENT_LINE_QUANTITIES` with the stripped form spelled out.

`po_parts.permitted_alias_keys()` is that rule as code and these tests call it
rather than carrying a copy. A test with its own copy of a rule is a second
definition that can drift from the first, which is the exact defect the
`xlNorm()` removal closed one file along.

⚠ **What these tests do NOT prove.** The client's own sheet is not in this
repository, so `CLIENT_LINES` is a reconstruction from `po_parts.py`'s own
evidence — see the docstring section "WHAT `CLIENT_LINES` IS". These tests hold
`PARTS` to `CLIENT_LINES`; they cannot hold `CLIENT_LINES` to the sheet. That
is a real limit and it is stated rather than papered over.
"""

import re

import po_parts as PP


# ══ 1. The rule itself ════════════════════════════════════════════════════

def test_every_alias_is_a_string_the_client_wrote():
    """
    **The load-bearing test in this file.**

    Every alias on every part must normalise to one of the client's own lines,
    or to the quantity-stripped form of one of the two lines that carried a
    quantity. There is no third category, and "it seems like something somebody
    might type" is not a reason.

    It fails on all 156 of the aliases deleted on 29 August 2026.
    """
    permitted = PP.permitted_alias_keys()

    offenders = []
    for canonical, row in PP.PARTS.items():
        for alias in row.get("aliases") or ():
            if PP._norm(alias) not in permitted:
                offenders.append((canonical, alias))

    assert not offenders, (
        "these aliases are not strings the client wrote — add the line to "
        "CLIENT_LINES if he did, and delete the alias if he did not: "
        + repr(offenders))


def test_every_client_line_still_prefills():
    """
    The other half of the rule, and the one that keeps the cutback honest.

    Deleting invented aliases must not cost the client a single one of his own
    spellings. Every line in `CLIENT_LINES` must resolve — through a canonical
    name or through an alias, it does not matter which.

    Measured across the cutback: **77 of 78 before, 78 of 78 after.** The one
    that did not resolve before was `M.S ANGEL 50 X 50 X 5 MM - 03 pcs`, the
    client's line verbatim, which had been indexed only without its quantity.
    """
    misses = [line for line in PP.CLIENT_LINES if PP.lookup(line) is None]
    assert not misses, f"the client's own spelling must prefill: {misses!r}"


def test_the_index_holds_nothing_but_canonical_names_and_client_lines():
    """
    Stated over the finished `INDEX` rather than over `PARTS`, because `INDEX`
    is what `lookup()` and `prefill_map()` actually answer from — an invented
    key reaching the browser is the failure, wherever it entered.

    Before the cutback this found **153** keys that were neither.
    """
    permitted = PP.permitted_alias_keys()
    canonical = {PP._norm(name) for name in PP.PARTS}

    invented = sorted(k for k in PP.INDEX
                      if k not in permitted and k not in canonical)
    assert not invented, (
        f"{len(invented)} keys match nothing anybody wrote: {invented!r}")


def test_the_quantity_derivation_is_a_table_of_two_and_not_a_rule():
    """
    `CLIENT_LINE_QUANTITIES` is the whole of the permitted derivation and it is
    written out rather than parsed. A regex that strips "a trailing quantity"
    would decide on its own what a quantity is, and `10G Esab`, `16 sq mm` and
    `12x100` are all trailing figures that are part of a part's name.

    So: both entries are client lines, and the stripped form is not.
    """
    lines = set(PP.CLIENT_LINES)
    for original, stripped in PP.CLIENT_LINE_QUANTITIES.items():
        assert original in lines, \
            f"{original!r} must be a client line — it is what he wrote"
        assert stripped not in lines, \
            f"{stripped!r} is our shortening of {original!r}, not his line"
        assert PP.lookup(original) == PP.lookup(stripped), \
            "both forms must reach the same part"


def test_the_misspelling_map_licenses_nothing_on_its_own():
    """
    ⚠ `MISSPELLINGS` records why a canonical name departs from the client's
    spelling. It does **not** mean "any string containing `soket` may be an
    alias" — reading it that way is how 156 aliases arrived.

    Two things are asserted: every entry is non-vacuous (the misspelling really
    does appear in a client line), and no alias is licensed by the map alone.
    """
    normalised_lines = " || ".join(PP._norm(l) for l in PP.CLIENT_LINES)
    for wrong, right in PP.MISSPELLINGS.items():
        assert wrong in normalised_lines, (
            f"{wrong!r} is recorded as the client's spelling but appears in no "
            f"client line — either the line is missing or the entry is dead")
        assert right != wrong

    # The map is documentation. The permitted set is built from CLIENT_LINES
    # and CLIENT_LINE_QUANTITIES and from nothing else.
    permitted = PP.permitted_alias_keys()
    expected = {PP._norm(l) for l in PP.CLIENT_LINES}
    expected |= {PP._norm(s) for s in PP.CLIENT_LINE_QUANTITIES.values()}
    assert permitted == expected, \
        "permitted_alias_keys() must be built from the client's lines alone"


# ══ 2. The three classes of invented alias, named ═════════════════════════

def test_a_millimetre_spelling_cannot_fetch_an_inch_parts_rate():
    """
    ⚠ **THE LIVE WRONG NUMBER, and the reason this pass happened.**

    `200 mm elbow` reached `200mm elbow` at ₹3,400 and `200 mm elbow 8 inch`
    reached `8" elbow` at ₹3,200 — the same physical part, two placeholder
    rates, and **which one landed on a purchase order depended on how somebody
    typed it.**

    Both spellings now match nothing. The two parts stay two parts with no
    alias between them: this module does not assert they are the same and does
    not assert they are different. That is `po_parts.py`'s open question 2 and
    it is the client's to answer.
    """
    assert PP.lookup("200 mm elbow 8 inch") is None
    assert PP.lookup("200 mm elbow") is None

    mm = PP.lookup("200mm elbow")
    inch = PP.lookup('8" elbow')
    assert mm is not None and inch is not None, "both parts still exist"
    assert mm[0] != inch[0] and mm[2] != inch[2], \
        "two entries, two rates — neither merged into the other"

    # And no key anywhere reaches one from the other's units.
    for key, canonical in PP.INDEX.items():
        if canonical == '8" elbow':
            assert "200" not in key, f"{key!r} reaches the inch part in mm"
        if canonical == "200mm elbow":
            assert "inch" not in key and '"' not in key, \
                f"{key!r} reaches the mm part in inches"


def test_no_alias_asserts_an_inch_to_millimetre_equivalence():
    """
    `25mm flange` → `1 inch flange`, `6 inch flange` → `150mm flange`,
    `25mm ms union` → `1 inch MS union`, `25mm gi saddle` → `1" GI saddle`.

    **Whether two sizes are one part is a pricing decision**, and each of those
    was one taken inside a lookup table where nobody would ever read it.
    """
    for typed in ["25mm flange", "6 inch flange", "25mm ms union",
                  "25mm gi saddle", "8 inch flange", "8 inch elbow"]:
        assert PP.lookup(typed) is None, \
            f"{typed!r} asserts a size equivalence nobody ruled on"


def test_the_dummy_flange_is_not_folded_into_a_plain_one():
    """
    ⚠ **A MISREADING OF THE CLIENT'S SHEET, named so it is not put back.**

    His sheet carries a **dummy** flange — `6 inch dummy flange 16mm (240 PCD)`
    — and, separately, `150mm flange`. The alias `6 inch flange` pointed the
    second at the first's size. They are different items at different rates.
    """
    assert PP.lookup("6 inch flange") is None
    dummy = PP.lookup("6 inch dummy flange 16mm (240 PCD)")
    plain = PP.lookup("150mm flange")
    assert dummy is not None and plain is not None
    assert dummy[0] != plain[0] and dummy[2] != plain[2]


def test_a_bare_name_does_not_silently_choose_a_size_or_a_brand():
    """
    `grinding wheel` used to fill the 4-inch rate, `gp thinner` the 20-litre
    one, and `yellow primer` / `po red paint` the non-Asian can. The operator
    got a figure for a part they had not specified.

    ⚠ **`cutting wheel` is the deliberate exception and proves the rule is
    about evidence rather than about bare names**: it is one of the three
    spellings the client himself used for that item, recorded verbatim.
    """
    for bare in ["grinding wheel", "gp thinner", "yellow primer",
                 "po red paint", "yellow primer asian", "safety shoe"]:
        assert PP.lookup(bare) is None, \
            f"{bare!r} chooses a size or a brand nobody named"

    assert PP.lookup("Cutting wheel") == PP.lookup("Cutting wheel 4 inch"), \
        "he wrote this one, so it stays"


# ══ 3. Shape, so the rule cannot be sidestepped ═══════════════════════════

def test_no_two_parts_share_a_key():
    """
    A duplicate normalised key means one part silently shadows another, and
    which one wins is dictionary order. Asserted over canonical names and
    aliases together, because a collision between the two is the same defect.
    """
    seen = {}
    for canonical, row in PP.PARTS.items():
        for key in [canonical] + list(row.get("aliases") or []):
            norm = PP._norm(key)
            assert norm not in seen or seen[norm] == canonical, (
                f"{key!r} maps to both {seen[norm]!r} and {canonical!r}")
            seen[norm] = canonical


def test_client_lines_carries_no_duplicate_string():
    """
    Two of the client's lines were exact repeats of another — `4sq 2core
    Flexible Wire` and `20a 1ph 3way Ac Box` each appeared twice on his sheet.
    They are recorded once here, with the repetition noted in the docstring
    rather than expressed as two identical tuple entries that read as a slip.
    """
    assert len(PP.CLIENT_LINES) == len(set(PP.CLIENT_LINES))


def test_the_alias_rule_is_written_down_where_somebody_will_read_it():
    """
    The rule lives in the module's own docstring, not only in this file. A test
    nobody opens does not stop the next pass; the file it guards might.
    """
    doc = PP.__doc__ or ""
    assert "AN ALIAS MAY EXIST ONLY IF THE CLIENT WROTE THAT EXACT STRING" in doc
    assert "CLIENT_LINES" in doc
    assert "NOT in this repository" in doc, \
        "the docstring must say the client's sheet is not here"


def test_the_prefill_still_carries_its_placeholder_warning():
    """
    Unchanged by the cutback and re-asserted here because this file rewrites
    the table around it. A smaller table of invented prices would be no better
    than a large one.
    """
    doc = (PP.__doc__ or "").upper()
    assert "ASSUMED PLACEHOLDER" in doc
    assert "NONE OF IT IS A QUOTED" in doc


def test_the_open_questions_are_pinned_open():
    """
    Two questions are carried forward to the client and neither may be closed
    by a later pass guessing. Delete the relevant half of this test in the
    commit that records his answer — not before.

    1. Is "PO red paint" red-oxide primer?
    2. Are `200mm elbow` and `8" elbow` the same part?
    """
    doc = PP.__doc__ or ""
    assert 'Is "PO red paint" red-oxide primer?' in doc
    assert "the same part?" in doc

    assert "PO red paint 20 ltr" in PP.PARTS
    assert not any("oxide" in name.lower() for name in PP.PARTS), \
        "nobody has answered question 1 yet; do not rename it silently"

    assert "200mm elbow" in PP.PARTS and '8" elbow' in PP.PARTS, \
        "question 2 is answered by the client, not by a merge"


def test_the_client_line_evidence_grade_is_recorded_on_every_line():
    """
    ⚠ **The weakest part of this work, asserted rather than left to prose.**

    `CLIENT_LINES` is a reconstruction, and the three grades of evidence behind
    it are not equally good. Every line carries a `(v)` / `(m)` / `(—)` mark in
    the source so a reader can tell which grade they are looking at, and this
    test fails if a line is added without one.
    """
    src = (__import__("pathlib").Path(PP.__file__)).read_text(encoding="utf8")
    block = src.split("CLIENT_LINES = (", 1)[1].split("\n)", 1)[0]

    entries = [ln for ln in block.splitlines() if ln.strip().startswith(('"', "'"))]
    assert len(entries) == len(PP.CLIENT_LINES), \
        "every client line must be one source line carrying its own mark"

    unmarked = [ln.strip() for ln in entries
                if not re.search(r"#\s*\((v|m|—)\)", ln)]
    assert not unmarked, (
        "every client line needs an evidence grade — (v) verbatim, "
        f"(m) misspelling reversed, (—) taken as the canonical: {unmarked!r}")
