"""
po_parts.py — the seeded prefill list for extra purchase-order lines
====================================================================

⚠ **EVERY RATE IN THIS FILE IS AN ASSUMED PLACEHOLDER. NONE OF IT IS A QUOTED
OR VERIFIED MARKET PRICE. IT EXISTS SO A PURCHASE ORDER CAN BE RAISED BEFORE
THE VENDOR HAS PRICED THE LIST, AND EVERY FIGURE IS EXPECTED TO BE
OVERWRITTEN.**

That paragraph is the whole reason this file is allowed to exist, so it is the
first thing in it. A rate here has not been sourced, quoted, negotiated or
checked against a market. It is a number somebody put in so that the form has
something to put in the box, and the moment a vendor prices the line the figure
here is wrong. Nothing in this application may present one of these as a real
price — not in the UI, not in a report, not on a printed document.

────────────────────────────────────────────────────────────────────────────
WHAT THIS IS, AND THE FOUR THINGS IT IS NOT
────────────────────────────────────────────────────────────────────────────

The client asked to be able to put parts on a purchase order that appear
nowhere on the BOQ, and sent a list of them with **no prices and no units**.
The owner's decision — recorded in the 29 August 2026 override block in
`CLIENT_CHANGES.md` §0 — is that those lines are **free text typed onto each
order**, and that this list exists **only as a typeahead prefill** so a real
order can be raised today.

So this module is:

* **A flat module-level table.** Not a collection in `STORE`, not a document,
  not a record with an id, not persisted by `db.py`.
* **Not editable through the UI.** There is no parts-master page, no CRUD, no
  route. Changing a rate here is a code edit and a commit, which is the correct
  weight for changing a placeholder everybody is supposed to overwrite anyway.
* **Not a vocabulary.** Typing a description that matches nothing here is
  accepted exactly as typed, with a blank rate. The list narrows nothing.
* **Not a per-vendor rate table.** One assumed figure, not one per supplier.
  What a given vendor charges is what they quote, and that goes in the rate box.

`purchase.py` imports this module. This module imports **nothing** — not
`store`, not `pipeline`, not `branding` — which is what keeps that arrow
one-way and keeps this file at the bottom of the import graph beside
`demo_data.py`. Keep it that way.

────────────────────────────────────────────────────────────────────────────
THE CLIENT'S LIST HAD DUPLICATES, TYPOS AND QUANTITIES IN THE NAMES
────────────────────────────────────────────────────────────────────────────

Resolved into `aliases` rather than seeded twice, so that both spellings
prefill the same rate and the operator never has to know which one is the
"real" one. The substitutions applied, all of them from the client's own sheet:

    Soket    -> Socket        Fastner  -> Fastener
    ANGEL    -> Angle         Lather   -> Leather
    threded  -> threaded

and these were one item written several ways:

    "Cutting wheel" / '4" Cutting wheel' / "Cutting wheel 4 inch"
    "8 mm Bullet Fastner" / "Bullet Fastner 8mm"
    '2" roller' / "2 inch roller"
    "GP Thinner 20 ltr" / "GP Thinner 20ltr"

`4sq 2core Flexible Wire` and `20a 1ph 3way Ac Box` each appeared **twice** on
the client's list and are seeded once each.

⚠ **Two names carried a QUANTITY, and the quantity was dropped.** `Safety shoes
10no` is seeded as `Safety shoes` and `M.S ANGEL 50 X 50 X 5 MM - 03 pcs` as
`M.S. angle 50x50x5 mm`. A quantity is something the operator types into the
qty box on the order; baking "10no" into a part name would make every future
order for eleven pairs read as a typo. The client's "10" and "03" are **not**
recorded here — they were a one-off requirement on one list, not a property of
the part.

⚠ **Brand variants are kept as separate parts, deliberately.** `Yellow primer`
and `Yellow primer Asian` are two rows, and so are `PO red paint` and `PO red
paint Asian`. They are different goods at different rates, and folding them
would lose the distinction the client drew himself.

⚠ **OPEN QUESTION FOR THE CLIENT — "PO red paint" is seeded VERBATIM and has
NOT been renamed.** It is most likely red-oxide primer, written on the sheet as
`P.O. Red` or `R.O. Red` and transcribed as "PO"; on a purchase-order screen
"PO" also reads as "purchase order", which is exactly the collision that makes
guessing dangerous. **Renaming it silently would put a word in the client's
mouth on a document that goes to a vendor**, so it is left as written and
raised as a question. If the answer comes back "red oxide", change the two
canonical names here and add the old spellings as aliases — do not do it
before.
"""

# Every entry: canonical display name -> {unit, assumed_rate, aliases}.
#
# `unit` and `assumed_rate` are both a PREFILL. The form leaves each editable
# and the operator overwrites either without ceremony; nothing downstream reads
# this file, so a change here affects the next line typed and no order already
# raised.
#
# `aliases` are the client's own spellings, normalised by `_norm()` below. They
# exist so `Soket 15mm` and `Socket 15mm` reach the same row.
PARTS = {
    "Elbow 25x15 mm":              {"unit": "Nos", "assumed_rate": 90.0,
                                    "aliases": ["elbow 25x15", "25x15 elbow"]},
    "Socket 15mm":                 {"unit": "Nos", "assumed_rate": 35.0,
                                    "aliases": ["soket 15mm", "soket 15 mm",
                                                "socket 15 mm"]},
    "End cap 65mm":                {"unit": "Nos", "assumed_rate": 180.0,
                                    "aliases": ["end cap 65 mm", "endcap 65mm"]},
    '8" blind flange (16mm)':      {"unit": "Nos", "assumed_rate": 2600.0,
                                    "aliases": ["8 inch blind flange 16mm",
                                                "8 blind flange 16mm",
                                                "blind flange 8 inch"]},
    '8" elbow':                    {"unit": "Nos", "assumed_rate": 3200.0,
                                    "aliases": ["8 inch elbow", "200 mm elbow 8 inch"]},
    '8" flange':                   {"unit": "Nos", "assumed_rate": 2200.0,
                                    "aliases": ["8 inch flange"]},
    "100x80 reducer":              {"unit": "Nos", "assumed_rate": 650.0,
                                    "aliases": ["100 x 80 reducer", "reducer 100x80"]},
    "6 inch dummy flange 16mm (240 PCD)":
                                   {"unit": "Nos", "assumed_rate": 1600.0,
                                    "aliases": ["6 dummy flange 16mm 240 pcd",
                                                '6" dummy flange 16mm',
                                                "dummy flange 6 inch"]},
    "200mm elbow":                 {"unit": "Nos", "assumed_rate": 3400.0,
                                    "aliases": ["200 mm elbow"]},
    "3 inch flange (150 PCD)":     {"unit": "Nos", "assumed_rate": 700.0,
                                    "aliases": ['3" flange 150 pcd',
                                                "3 inch flange 150 pcd"]},
    "4 inch flange (180 PCD)":     {"unit": "Nos", "assumed_rate": 950.0,
                                    "aliases": ['4" flange 180 pcd',
                                                "4 inch flange 180 pcd"]},
    "1 inch flange":               {"unit": "Nos", "assumed_rate": 220.0,
                                    "aliases": ['1" flange', "25mm flange"]},
    "80mm elbow":                  {"unit": "Nos", "assumed_rate": 520.0,
                                    "aliases": ["80 mm elbow"]},
    "150mm flange":                {"unit": "Nos", "assumed_rate": 1350.0,
                                    "aliases": ["150 mm flange", "6 inch flange"]},
    "200mm gasket":                {"unit": "Nos", "assumed_rate": 320.0,
                                    "aliases": ["200 mm gasket", "gasket 200mm"]},
    "25x15 forged elbow":          {"unit": "Nos", "assumed_rate": 260.0,
                                    "aliases": ["forged elbow 25x15",
                                                "25 x 15 forged elbow"]},
    "25x15 forged coupling (S/W x thread)":
                                   {"unit": "Nos", "assumed_rate": 240.0,
                                    "aliases": ["25x15 forged coupling",
                                                "25x15 forged coupling sw x threded",
                                                "25x15 forged coupling sw x threaded"]},
    "25x25 elbow (S/W)":           {"unit": "Nos", "assumed_rate": 210.0,
                                    "aliases": ["25x25 elbow sw", "25 x 25 elbow"]},
    "25x25 tee (S/W)":             {"unit": "Nos", "assumed_rate": 280.0,
                                    "aliases": ["25x25 tee sw", "25 x 25 tee"]},
    "32x25 reducer (B/W)":         {"unit": "Nos", "assumed_rate": 190.0,
                                    "aliases": ["32x25 reducer bw", "32 x 25 reducer"]},
    "50mm elbow (B/W)":            {"unit": "Nos", "assumed_rate": 340.0,
                                    "aliases": ["50mm elbow bw", "50 mm elbow"]},
    "8mm hex nipple":              {"unit": "Nos", "assumed_rate": 45.0,
                                    "aliases": ["8 mm hex nipple", "hex nipple 8mm"]},
    "10mm barrel nipple (150mm long)":
                                   {"unit": "Nos", "assumed_rate": 110.0,
                                    "aliases": ["10mm barrel nipple",
                                                "barrel nipple 10mm 150mm long"]},
    "32mm barrel nipple":          {"unit": "Nos", "assumed_rate": 130.0,
                                    "aliases": ["32 mm barrel nipple",
                                                "barrel nipple 32mm"]},
    "1 inch MS union":             {"unit": "Nos", "assumed_rate": 180.0,
                                    "aliases": ['1" ms union', "ms union 1 inch",
                                                "25mm ms union"]},
    "MS coupling 15mm threaded":   {"unit": "Nos", "assumed_rate": 55.0,
                                    # `threded` is the client's spelling.
                                    "aliases": ["ms coupling 15mm threded",
                                                "ms coupling 15 mm threaded",
                                                "ms coupling 15mm"]},
    "32mm ball valve - SANT":      {"unit": "Nos", "assumed_rate": 850.0,
                                    "aliases": ["32mm ball valve sant",
                                                "32 mm ball valve sant",
                                                "ball valve 32mm sant"]},
    "25mm U clamp patti":          {"unit": "Nos", "assumed_rate": 30.0,
                                    "aliases": ["25mm u clamp patti",
                                                "u clamp patti 25mm"]},
    "32mm U clamp patti":          {"unit": "Nos", "assumed_rate": 38.0,
                                    "aliases": ["32mm u clamp patti",
                                                "u clamp patti 32mm"]},
    "40mm U clamp patti":          {"unit": "Nos", "assumed_rate": 45.0,
                                    "aliases": ["40mm u clamp patti",
                                                "u clamp patti 40mm"]},
    "50mm hitech clamp":           {"unit": "Nos", "assumed_rate": 120.0,
                                    "aliases": ["50 mm hitech clamp",
                                                "hitech clamp 50mm",
                                                "50mm hi-tech clamp"]},
    '1" GI saddle':                {"unit": "Nos", "assumed_rate": 25.0,
                                    "aliases": ["1 inch gi saddle", "gi saddle 1 inch",
                                                "25mm gi saddle"]},
    # The client's sheet carried this twice — "8 mm Bullet Fastner" and
    # "Bullet Fastner 8mm". One part, both spellings, `Fastner` -> `Fastener`.
    "Bullet fastener 8mm":         {"unit": "Nos", "assumed_rate": 12.0,
                                    "aliases": ["8 mm bullet fastner",
                                                "bullet fastner 8mm",
                                                "8mm bullet fastner",
                                                "bullet fastener 8 mm",
                                                "8mm bullet fastener"]},
    "Anchor fastener 12x100":      {"unit": "Nos", "assumed_rate": 38.0,
                                    "aliases": ["anchor fastner 12x100",
                                                "anchor fastner 12 x 100",
                                                "anchor fastener 12 x 100"]},
    "35x8 screw":                  {"unit": "Nos", "assumed_rate": 3.0,
                                    "aliases": ["35 x 8 screw", "screw 35x8"]},
    "Washer for nutbolt 5/8":      {"unit": "Kg",  "assumed_rate": 140.0,
                                    "aliases": ["washer for nut bolt 5/8",
                                                "washer nutbolt 5/8"]},
    # The client wrote "M.S ANGEL 50 X 50 X 5 MM - 03 pcs". `ANGEL` -> `Angle`,
    # and the "- 03 pcs" is a QUANTITY, not part of the name. Dropped; it
    # belongs in the qty box on the order.
    "M.S. angle 50x50x5 mm":       {"unit": "Nos", "assumed_rate": 1150.0,
                                    "aliases": ["m.s angel 50 x 50 x 5 mm",
                                                "ms angel 50x50x5 mm",
                                                "ms angle 50x50x5",
                                                "m.s. angle 50 x 50 x 5 mm"]},
    "Earthing holder":             {"unit": "Nos", "assumed_rate": 180.0,
                                    "aliases": ["earthing holder clamp"]},
    # ⚠ "PO red paint" is seeded VERBATIM. See the module docstring: it is most
    #   likely red-oxide primer and it has deliberately NOT been renamed.
    "PO red paint 20 ltr":         {"unit": "Can", "assumed_rate": 4200.0,
                                    "aliases": ["po red paint 20ltr",
                                                "po red paint"]},
    "PO red paint Asian 20 ltr":   {"unit": "Can", "assumed_rate": 4800.0,
                                    "aliases": ["po red paint asian 20ltr",
                                                "po red paint asian"]},
    "Yellow primer 20 ltr":        {"unit": "Can", "assumed_rate": 4000.0,
                                    "aliases": ["yellow primer 20ltr",
                                                "yellow primer"]},
    "Yellow primer Asian 20 ltr":  {"unit": "Can", "assumed_rate": 4600.0,
                                    "aliases": ["yellow primer asian 20ltr",
                                                "yellow primer asian"]},
    # "GP Thinner 20 ltr" and "GP Thinner 20ltr" — one item, two spellings.
    "GP thinner 20 ltr":           {"unit": "Can", "assumed_rate": 2600.0,
                                    "aliases": ["gp thinner 20ltr", "gp thinner"]},
    "Black Japan oil paint":       {"unit": "Ltr", "assumed_rate": 320.0,
                                    "aliases": ["black japan paint",
                                                "black japan oil paint 1 ltr"]},
    "Wrapping coating 4mm":        {"unit": "Roll", "assumed_rate": 900.0,
                                    "aliases": ["wrapping coating 4 mm",
                                                "wrapping coat 4mm"]},
    "Paint roller":                {"unit": "Nos", "assumed_rate": 90.0,
                                    "aliases": ["painting roller"]},
    # '2" roller' and "2 inch roller" — one item.
    "2 inch roller":               {"unit": "Nos", "assumed_rate": 70.0,
                                    "aliases": ['2" roller', "2inch roller",
                                                "roller 2 inch"]},
    "Roller brush":                {"unit": "Nos", "assumed_rate": 110.0,
                                    "aliases": ["roller brush set"]},
    "Brush 2 inch":                {"unit": "Nos", "assumed_rate": 60.0,
                                    "aliases": ['2" brush', "2 inch brush",
                                                "brush 2inch"]},
    "3 inch brush":                {"unit": "Nos", "assumed_rate": 90.0,
                                    "aliases": ['3" brush', "brush 3 inch"]},
    # "Cutting wheel", '4" Cutting wheel' and "Cutting wheel 4 inch" — one item.
    "Cutting wheel 4 inch":        {"unit": "Nos", "assumed_rate": 45.0,
                                    "aliases": ["cutting wheel", '4" cutting wheel',
                                                "4 inch cutting wheel",
                                                "cutting wheel 4inch"]},
    "Grinding wheel 4 inch":       {"unit": "Nos", "assumed_rate": 60.0,
                                    "aliases": ["grinding wheel", '4" grinding wheel',
                                                "4 inch grinding wheel"]},
    "Welding rod 10G Esab":        {"unit": "Kg",  "assumed_rate": 190.0,
                                    "aliases": ["welding rod 10g esab",
                                                "esab welding rod 10g",
                                                "welding rod 10 g"]},
    "Welding cable 16 sqmm single core":
                                   {"unit": "Mtr", "assumed_rate": 165.0,
                                    "aliases": ["welding cable 16 sq mm single core",
                                                "16 sqmm welding cable"]},
    "Butane gas":                  {"unit": "Nos", "assumed_rate": 130.0,
                                    "aliases": ["butane gas cylinder",
                                                "butane gas can"]},
    "12mm drill bit (12 inch)":    {"unit": "Nos", "assumed_rate": 420.0,
                                    "aliases": ["12mm drill bit 12 inch",
                                                "12 mm drill bit",
                                                'drill bit 12mm 12"']},
    # The client wrote "Safety shoes 10no". The "10no" is a QUANTITY and is
    # dropped — it belongs in the qty box, not in the part name.
    "Safety shoes":                {"unit": "Pair", "assumed_rate": 1150.0,
                                    "aliases": ["safety shoes 10no",
                                                "safety shoe", "safety shoes 10 no"]},
    "Welding gloves":              {"unit": "Pair", "assumed_rate": 130.0,
                                    "aliases": ["welding hand gloves",
                                                "welding glove"]},
    # `Lather` -> `Leather`.
    "Leather hand gloves":         {"unit": "Pair", "assumed_rate": 95.0,
                                    "aliases": ["lather hand gloves",
                                                "lather hand glove",
                                                "leather hand glove"]},
    "White goggles":               {"unit": "Nos", "assumed_rate": 70.0,
                                    "aliases": ["white goggle", "safety goggles white"]},
    "Welding glass (black & white)":
                                   {"unit": "Nos", "assumed_rate": 25.0,
                                    "aliases": ["welding glass black & white",
                                                "welding glass black and white",
                                                "welding glass"]},
    "Red jacket":                  {"unit": "Nos", "assumed_rate": 650.0,
                                    "aliases": ["red safety jacket"]},
    "Green jacket":                {"unit": "Nos", "assumed_rate": 650.0,
                                    "aliases": ["green safety jacket"]},
    "7.5 HP DOL starter":          {"unit": "Nos", "assumed_rate": 3800.0,
                                    "aliases": ["7.5hp dol starter",
                                                "dol starter 7.5 hp"]},
    "2-way push button box":       {"unit": "Nos", "assumed_rate": 480.0,
                                    "aliases": ["2 way push button box",
                                                "2way push button box",
                                                "push button box 2 way"]},
    # "20a 1ph 3way Ac Box" appeared twice on the client's list. Seeded once.
    "20A 1ph 3-way AC box":        {"unit": "Nos", "assumed_rate": 420.0,
                                    "aliases": ["20a 1ph 3way ac box",
                                                "20a 1ph 3 way ac box",
                                                "20amp 1ph 3way ac box"]},
    "20A 1ph 2-way AC box":        {"unit": "Nos", "assumed_rate": 360.0,
                                    "aliases": ["20a 1ph 2way ac box",
                                                "20a 1ph 2 way ac box",
                                                "20amp 1ph 2way ac box"]},
    "16A 3-pin plug":              {"unit": "Nos", "assumed_rate": 130.0,
                                    "aliases": ["16a 3 pin plug", "16a 3pin plug",
                                                "16amp 3 pin plug"]},
    "1.5 sq mm 3-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 62.0,
                                    "aliases": ["1.5sq 3core flexible wire",
                                                "1.5 sq 3 core flexible wire",
                                                "1.5sqmm 3core flexible wire"]},
    "1.5 sq mm 2-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 45.0,
                                    "aliases": ["1.5sq 2core flexible wire",
                                                "1.5 sq 2 core flexible wire",
                                                "1.5sqmm 2core flexible wire"]},
    "2.5 sq mm 2-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 68.0,
                                    "aliases": ["2.5sq 2core flexible wire",
                                                "2.5 sq 2 core flexible wire",
                                                "2.5sqmm 2core flexible wire"]},
    # "4sq 2core Flexible Wire" appeared twice on the client's list. Seeded once.
    "4 sq mm 2-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 105.0,
                                    "aliases": ["4sq 2core flexible wire",
                                                "4 sq 2 core flexible wire",
                                                "4sqmm 2core flexible wire"]},
    "16 sq mm wire":               {"unit": "Mtr", "assumed_rate": 175.0,
                                    "aliases": ["16sq wire", "16 sqmm wire",
                                                "16sqmm wire"]},
}


def _norm(text) -> str:
    """
    The matching key: lowercased, with every run of whitespace collapsed to one.

    Deliberately shallow. It folds the differences that are certainly noise — a
    stray double space, a capital letter — and folds nothing else. It does NOT
    strip punctuation, because `1.5 sq mm` and `15 sq mm` differ by a full stop
    and collapsing them would prefill the wrong rate on a wire size. A match
    this list misses costs one typed rate; a match it gets wrong puts a figure
    on a purchase order that nobody chose.
    """
    return " ".join(str(text or "").lower().split())


def _build_index() -> dict:
    """
    `{normalised name or alias: canonical name}`, built once at import.

    Both directions are indexed — the canonical name and every alias — so that
    `Socket 15mm` and `Soket 15mm` land on the same row. A duplicate key is a
    seeding mistake rather than a runtime condition, and
    `tests/test_po_extra_lines.py` asserts there are none; here the first
    definition simply wins, because a table that silently lost a part would be
    worse than one that ignored a redundant alias.
    """
    index = {}
    for canonical, row in PARTS.items():
        index.setdefault(_norm(canonical), canonical)
        for alias in row.get("aliases") or ():
            index.setdefault(_norm(alias), canonical)
    return index


INDEX = _build_index()


def lookup(description):
    """
    `(canonical_name, unit, assumed_rate)` for a typed description, or `None`.

    `None` is the ordinary answer, not a failure: an extra line is free text
    and most of what gets typed will not be on this list. The caller keeps what
    was typed and leaves the rate blank.

    ⚠ **A hit returns an ASSUMED rate.** The caller must mark the line so the
    figure is never mistaken for one a vendor gave us — `purchase.py` sets
    `rate_is_assumed` and clears it the moment the rate is edited.
    """
    canonical = INDEX.get(_norm(description))
    if not canonical:
        return None
    row = PARTS[canonical]
    return canonical, row["unit"], float(row["assumed_rate"])


def suggestions() -> list:
    """
    Canonical names, sorted, for the form's `<datalist>`.

    Canonical names only. The aliases are for *matching* what somebody typed,
    not for offering the client's own typos back to him as suggestions.
    """
    return sorted(PARTS)
