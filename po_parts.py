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

════════════════════════════════════════════════════════════════════════════
THE ALIAS RULE — READ THIS BEFORE ADDING ONE  (29 August 2026, third pass)
════════════════════════════════════════════════════════════════════════════

⚠ **AN ALIAS MAY EXIST ONLY IF THE CLIENT WROTE THAT EXACT STRING. Everything
else is deleted, and `tests/test_po_parts_aliases.py` enforces it.**

The one permitted derivation is mechanical and is written down rather than
inferred: a line whose **trailing quantity** was dropped may also be reached by
the line without it. `CLIENT_LINE_QUANTITIES` names both such lines and spells
out the stripped form; nothing parses a quantity out of anything.

`MISSPELLINGS` is the second half of the record and does **not** generate
aliases. It explains why a canonical name departs from the client's own
spelling — `Soket` → `Socket` — so that the departure is auditable. The
client's spelling is then an alias because **he wrote it**, not because a map
says it is allowed.

**Why the rule exists, and it is a defect and not a tidy-up.** This table
shipped on 29 August 2026 with 73 canonical parts and **172 aliases, 156 of
which nobody had written**. They were plausible-looking permutations — word
order reversed, a space added, `mm` swapped for `inch` — generated to widen the
prefill, and three classes of them were actively wrong:

1. **A live wrong number.** `200 mm elbow` reached `200mm elbow` at ₹3,400
   while `200 mm elbow 8 inch` reached `8" elbow` at ₹3,200. Same physical
   part, two placeholder rates, and **which figure landed on a purchase order
   depended on how somebody typed it.** `_norm()`'s own docstring names exactly
   this as the thing to avoid.
2. **An inch↔mm equivalence asserted as a spelling.** `25mm flange` →
   `1 inch flange`, `6 inch flange` → `150mm flange`, `25mm ms union` →
   `1 inch MS union`, `25mm gi saddle` → `1" GI saddle`. Whether two sizes are
   one part **is a pricing decision**, and dressing it as a spelling variant
   hides the decision inside a lookup table.
3. **A bare name silently choosing a size.** `grinding wheel` → the 4-inch one,
   `gp thinner` → the 20-litre one, `yellow primer` → the non-Asian one,
   `po red paint` → the non-Asian one. The operator gets a rate for a part they
   did not specify.

⚠ **One of the deleted aliases rested on a misreading and it is named here so
it is not put back.** The client's sheet carries a **dummy** flange —
`6 inch dummy flange 16mm (240 PCD)` — and, separately, `150mm flange`. The
alias `6 inch flange` → `150mm flange` folded a dummy flange into a plain one.
Those are different items at different rates.

⚠ **NO CANONICAL PART WAS MERGED OR SPLIT.** `200mm elbow` and `8" elbow` stay
two entries with **no alias between them**, so typing one can never fetch the
other's rate. This module does **not** assert they are the same part and does
**not** assert they are different — see the open questions below.

**The consequence, and it is the correct one:** the prefill misses more often.
`grinding wheel` no longer fills a rate; the line is accepted exactly as typed,
with a blank rate and no assumed flag. **A match this list misses costs one
typed rate. A match it gets wrong puts a figure on a purchase order that nobody
chose**, which is `_norm()`'s doctrine applied one level up.

────────────────────────────────────────────────────────────────────────────
⚠ WHAT `CLIENT_LINES` IS, AND THE PART OF IT NOT TO TRUST
────────────────────────────────────────────────────────────────────────────

**The client's own sheet is NOT in this repository** — not in `client_docs/`,
not in `fixtures/`, not in the history. It arrived as a message and was
transcribed straight into `PARTS` by the pass that built this file, and that
transcription is now the only record of it anywhere.

So `CLIENT_LINES` is a **reconstruction from this module's own evidence**, not
a transcription from the client's document. Three grades of evidence sit in it
and the difference matters:

* **Recorded verbatim** by the original docstring or commit message — the
  duplicate spellings, the two lines carrying a quantity, the five
  misspellings. These are as good as the sheet.
* **Derived mechanically** — a canonical name with a documented misspelling
  reversed (`Socket 15mm` → `Soket 15mm`). Sound, and marked below.
* **Taken as the canonical name**, because nothing records anything else. This
  is the weak grade: the one row where the sheet's own spelling *is* recorded
  (`4sq 2core Flexible Wire`) shows the canonical was rewritten into a house
  style, so for the rows with no record the canonical is probably **not**
  character-for-character what he wrote.

That last point cuts both ways and is left as it is deliberately: inventing a
house-style client spelling for the other wire rows would be doing again the
exact thing this pass is undoing. **When the client's sheet is available, add
its lines here and the aliases follow.** Do not add an alias any other way.

⚠ **The line count is 78 distinct strings**, of which `4sq 2core Flexible Wire`
and `20a 1ph 3way Ac Box` each appeared **twice** on the client's list, so **80
raw lines as this module records them**. A figure of 81 has been quoted
elsewhere and **cannot be reproduced from anything in this repository**; the
missing line, if there is one, is a line whose transcription left no trace.

────────────────────────────────────────────────────────────────────────────
OPEN QUESTIONS FOR THE CLIENT
────────────────────────────────────────────────────────────────────────────

⚠ **1. Is "PO red paint" red-oxide primer?** It is seeded VERBATIM and has
deliberately **not** been renamed. It is most likely `P.O. Red` or `R.O. Red`
on the sheet, transcribed as "PO"; on a purchase-order screen "PO" also reads
as "purchase order", which is exactly the collision that makes guessing
dangerous. **Renaming it silently would put a word in the client's mouth on a
document that goes to a vendor.** If the answer comes back "red oxide", change
the two canonical names here and add the old spellings to `CLIENT_LINES` — do
not do it before.

⚠ **2. Are `200mm elbow` and `8" elbow` the same part?** 200 mm is 8 inches, so
they may be one item written two ways at two placeholder rates — or two items
the client buys separately. **This module does not answer it in either
direction.** Until he does, they are two entries with no path between them,
which is the only arrangement that cannot put the wrong figure on an order.

────────────────────────────────────────────────────────────────────────────
THE CLIENT'S LIST HAD DUPLICATES, TYPOS AND QUANTITIES IN THE NAMES
────────────────────────────────────────────────────────────────────────────

Resolved into aliases rather than seeded twice, so that both spellings prefill
the same rate and the operator never has to know which one is the "real" one.
The substitutions applied, all of them from the client's own sheet:

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

⚠ **Two names carried a QUANTITY, and the quantity was dropped from the
canonical.** `Safety shoes 10no` is seeded as `Safety shoes` and
`M.S ANGEL 50 X 50 X 5 MM - 03 pcs` as `M.S. angle 50x50x5 mm`. A quantity is
something the operator types into the qty box on the order; baking "10no" into
a part name would make every future order for eleven pairs read as a typo. The
client's "10" and "03" are **not** recorded as part of any name — but both
lines are in `CLIENT_LINES` verbatim, because he wrote them, and
`CLIENT_LINE_QUANTITIES` is what lets the stripped form be an alias too.

⚠ **Brand variants are kept as separate parts, deliberately.** `Yellow primer`
and `Yellow primer Asian` are two rows, and so are `PO red paint` and `PO red
paint Asian`. They are different goods at different rates, and folding them
would lose the distinction the client drew himself. Note that **neither bare
name is an alias any more**: `yellow primer` used to reach the non-Asian
20-litre can, which is a size and a brand chosen for somebody who named
neither.
"""

# ══════════════════════════════════════════════════════════════════════════
# THE CLIENT'S LIST — the source of truth for the alias rule
# ══════════════════════════════════════════════════════════════════════════
#
# ⚠ Read the docstring section "WHAT `CLIENT_LINES` IS" before touching this.
# It is a reconstruction from this module's own evidence, because the client's
# sheet is not in this repository. Grades are marked per line:
#
#     (v)  verbatim — recorded by the original docstring or commit message
#     (m)  a canonical name with a documented misspelling reversed
#     (—)  taken as the canonical name, because nothing records anything else
#
# **AN ALIAS MAY ONLY BE A STRING THAT APPEARS HERE** (or the stripped form of
# one named in CLIENT_LINE_QUANTITIES). To add an alias you must first add a
# client line, and adding a client line is a claim about what he wrote.
CLIENT_LINES = (
    "Elbow 25x15 mm",                                    # (—)
    "Soket 15mm",                                        # (m) Soket -> Socket
    "End cap 65mm",                                      # (—)
    '8" blind flange (16mm)',                            # (—)
    '8" elbow',                                          # (—)
    '8" flange',                                         # (—)
    "100x80 reducer",                                    # (—)
    "6 inch dummy flange 16mm (240 PCD)",                # (—) a DUMMY flange
    "200mm elbow",                                       # (—)
    "3 inch flange (150 PCD)",                           # (—)
    "4 inch flange (180 PCD)",                           # (—)
    "1 inch flange",                                     # (—)
    "80mm elbow",                                        # (—)
    "150mm flange",                                      # (—)
    "200mm gasket",                                      # (—)
    "25x15 forged elbow",                                # (—)
    "25x15 forged coupling sw x threded",                # (v) carries `threded`
    "25x25 elbow (S/W)",                                 # (—)
    "25x25 tee (S/W)",                                   # (—)
    "32x25 reducer (B/W)",                               # (—)
    "50mm elbow (B/W)",                                  # (—)
    "8mm hex nipple",                                    # (—)
    "10mm barrel nipple (150mm long)",                   # (—)
    "32mm barrel nipple",                                # (—)
    "1 inch MS union",                                   # (—)
    "MS coupling 15mm threded",                          # (m) threded
    "32mm ball valve - SANT",                            # (—)
    "25mm U clamp patti",                                # (—)
    "32mm U clamp patti",                                # (—)
    "40mm U clamp patti",                                # (—)
    "50mm hitech clamp",                                 # (—)
    '1" GI saddle',                                      # (—)
    "8 mm Bullet Fastner",                               # (v) one of two
    "Bullet Fastner 8mm",                                # (v) spellings
    "Anchor Fastner 12x100",                             # (m) Fastner
    "35x8 screw",                                        # (—)
    "Washer for nutbolt 5/8",                            # (—)
    "M.S ANGEL 50 X 50 X 5 MM - 03 pcs",                 # (v) carries a qty
    "Earthing holder",                                   # (—)
    "PO red paint 20 ltr",                               # (—) open question 1
    "PO red paint Asian 20 ltr",                         # (—)
    "Yellow primer 20 ltr",                              # (—)
    "Yellow primer Asian 20 ltr",                        # (—)
    "GP Thinner 20 ltr",                                 # (v) one of two
    "GP Thinner 20ltr",                                  # (v) spellings
    "Black Japan oil paint",                             # (—)
    "Wrapping coating 4mm",                              # (—)
    "Paint roller",                                      # (—)
    '2" roller',                                         # (v) one of two
    "2 inch roller",                                     # (v) spellings
    "Roller brush",                                      # (—)
    "Brush 2 inch",                                      # (—)
    "3 inch brush",                                      # (—)
    "Cutting wheel",                                     # (v) one of three
    '4" Cutting wheel',                                  # (v) spellings
    "Cutting wheel 4 inch",                              # (v)
    "Grinding wheel 4 inch",                             # (—) NOT bare-named
    "Welding rod 10G Esab",                              # (—)
    "Welding cable 16 sqmm single core",                 # (—)
    "Butane gas",                                        # (—)
    "12mm drill bit (12 inch)",                          # (—)
    "Safety shoes 10no",                                 # (v) carries a qty
    "Welding gloves",                                    # (—)
    "Lather hand gloves",                                # (m) Lather -> Leather
    "White goggles",                                     # (—)
    "Welding glass (black & white)",                     # (—)
    "Red jacket",                                        # (—)
    "Green jacket",                                      # (—)
    "7.5 HP DOL starter",                                # (—)
    "2-way push button box",                             # (—)
    "20a 1ph 3way Ac Box",                               # (v) appeared TWICE
    "20A 1ph 2-way AC box",                              # (—)
    "16A 3-pin plug",                                    # (—)
    "1.5 sq mm 3-core flexible wire",                    # (—)
    "1.5 sq mm 2-core flexible wire",                    # (—)
    "2.5 sq mm 2-core flexible wire",                    # (—)
    "4sq 2core Flexible Wire",                           # (v) appeared TWICE
    "16 sq mm wire",                                     # (—)
)

# The two client lines whose trailing QUANTITY was dropped from the canonical
# name, with the stripped form written out. Nothing parses a quantity out of
# anything — this is the whole of the permitted derivation, and it is a table
# of two rows precisely so that it cannot quietly grow into a rule.
CLIENT_LINE_QUANTITIES = {
    "Safety shoes 10no":                  "Safety shoes",
    "M.S ANGEL 50 X 50 X 5 MM - 03 pcs":  "M.S ANGEL 50 X 50 X 5 MM",
}

# The client's own misspellings, and the corrections applied when the canonical
# name was written.
#
# ⚠ **This map does NOT license an alias.** It records why a canonical departs
# from the client's spelling, so the departure is auditable. The client's
# spelling is an alias because it is in `CLIENT_LINES` — because he wrote it —
# and for no other reason. Reading this map as "any string containing `soket`
# may be an alias" is how 156 of them got here in the first place.
MISSPELLINGS = {
    "soket":   "socket",
    "fastner": "fastener",
    "angel":   "angle",
    "lather":  "leather",
    "threded": "threaded",
}


# Every entry: canonical display name -> {unit, assumed_rate, aliases}.
#
# `unit` and `assumed_rate` are both a PREFILL. The form leaves each editable
# and the operator overwrites either without ceremony; nothing downstream reads
# this file, so a change here affects the next line typed and no order already
# raised.
#
# ⚠ `aliases` are the client's OWN spellings and nothing else — see the alias
# rule in the docstring. A row with no alias is the ordinary case: it means the
# canonical name is what he wrote. **Do not add a "plausible variant".**
PARTS = {
    "Elbow 25x15 mm":              {"unit": "Nos", "assumed_rate": 90.0,
                                    "aliases": []},
    "Socket 15mm":                 {"unit": "Nos", "assumed_rate": 35.0,
                                    "aliases": ["Soket 15mm"]},
    "End cap 65mm":                {"unit": "Nos", "assumed_rate": 180.0,
                                    "aliases": []},
    '8" blind flange (16mm)':      {"unit": "Nos", "assumed_rate": 2600.0,
                                    "aliases": []},
    # ⚠ No alias reaches this row from a millimetre spelling, and none may.
    #   `200 mm elbow 8 inch` used to, which put ₹3,200 on an order somebody
    #   had described as a 200 mm elbow. Open question 2.
    '8" elbow':                    {"unit": "Nos", "assumed_rate": 3200.0,
                                    "aliases": []},
    '8" flange':                   {"unit": "Nos", "assumed_rate": 2200.0,
                                    "aliases": []},
    "100x80 reducer":              {"unit": "Nos", "assumed_rate": 650.0,
                                    "aliases": []},
    # ⚠ A DUMMY flange — a distinct item from `150mm flange` below. The alias
    #   `6 inch flange` used to point at that one; it was a misreading of the
    #   client's sheet and it is not to be put back.
    "6 inch dummy flange 16mm (240 PCD)":
                                   {"unit": "Nos", "assumed_rate": 1600.0,
                                    "aliases": []},
    # ⚠ Two separate entries with no alias between them — see `8" elbow`.
    "200mm elbow":                 {"unit": "Nos", "assumed_rate": 3400.0,
                                    "aliases": []},
    "3 inch flange (150 PCD)":     {"unit": "Nos", "assumed_rate": 700.0,
                                    "aliases": []},
    "4 inch flange (180 PCD)":     {"unit": "Nos", "assumed_rate": 950.0,
                                    "aliases": []},
    "1 inch flange":               {"unit": "Nos", "assumed_rate": 220.0,
                                    "aliases": []},
    "80mm elbow":                  {"unit": "Nos", "assumed_rate": 520.0,
                                    "aliases": []},
    "150mm flange":                {"unit": "Nos", "assumed_rate": 1350.0,
                                    "aliases": []},
    "200mm gasket":                {"unit": "Nos", "assumed_rate": 320.0,
                                    "aliases": []},
    "25x15 forged elbow":          {"unit": "Nos", "assumed_rate": 260.0,
                                    "aliases": []},
    # `threded` is the client's spelling, and this alias is his line verbatim.
    "25x15 forged coupling (S/W x thread)":
                                   {"unit": "Nos", "assumed_rate": 240.0,
                                    "aliases": ["25x15 forged coupling sw x threded"]},
    "25x25 elbow (S/W)":           {"unit": "Nos", "assumed_rate": 210.0,
                                    "aliases": []},
    "25x25 tee (S/W)":             {"unit": "Nos", "assumed_rate": 280.0,
                                    "aliases": []},
    "32x25 reducer (B/W)":         {"unit": "Nos", "assumed_rate": 190.0,
                                    "aliases": []},
    "50mm elbow (B/W)":            {"unit": "Nos", "assumed_rate": 340.0,
                                    "aliases": []},
    "8mm hex nipple":              {"unit": "Nos", "assumed_rate": 45.0,
                                    "aliases": []},
    "10mm barrel nipple (150mm long)":
                                   {"unit": "Nos", "assumed_rate": 110.0,
                                    "aliases": []},
    "32mm barrel nipple":          {"unit": "Nos", "assumed_rate": 130.0,
                                    "aliases": []},
    "1 inch MS union":             {"unit": "Nos", "assumed_rate": 180.0,
                                    "aliases": []},
    "MS coupling 15mm threaded":   {"unit": "Nos", "assumed_rate": 55.0,
                                    # `threded` is the client's spelling.
                                    "aliases": ["MS coupling 15mm threded"]},
    "32mm ball valve - SANT":      {"unit": "Nos", "assumed_rate": 850.0,
                                    "aliases": []},
    "25mm U clamp patti":          {"unit": "Nos", "assumed_rate": 30.0,
                                    "aliases": []},
    "32mm U clamp patti":          {"unit": "Nos", "assumed_rate": 38.0,
                                    "aliases": []},
    "40mm U clamp patti":          {"unit": "Nos", "assumed_rate": 45.0,
                                    "aliases": []},
    "50mm hitech clamp":           {"unit": "Nos", "assumed_rate": 120.0,
                                    "aliases": []},
    '1" GI saddle':                {"unit": "Nos", "assumed_rate": 25.0,
                                    "aliases": []},
    # The client's sheet carried this twice — "8 mm Bullet Fastner" and
    # "Bullet Fastner 8mm". One part, both spellings, `Fastner` -> `Fastener`.
    "Bullet fastener 8mm":         {"unit": "Nos", "assumed_rate": 12.0,
                                    "aliases": ["8 mm Bullet Fastner",
                                                "Bullet Fastner 8mm"]},
    "Anchor fastener 12x100":      {"unit": "Nos", "assumed_rate": 38.0,
                                    "aliases": ["Anchor Fastner 12x100"]},
    "35x8 screw":                  {"unit": "Nos", "assumed_rate": 3.0,
                                    "aliases": []},
    "Washer for nutbolt 5/8":      {"unit": "Kg",  "assumed_rate": 140.0,
                                    "aliases": []},
    # The client wrote "M.S ANGEL 50 X 50 X 5 MM - 03 pcs". `ANGEL` -> `Angle`,
    # and the "- 03 pcs" is a QUANTITY, not part of the name. Dropped from the
    # canonical; it belongs in the qty box on the order. Both his line and its
    # stripped form are aliases — CLIENT_LINE_QUANTITIES is the permission.
    "M.S. angle 50x50x5 mm":       {"unit": "Nos", "assumed_rate": 1150.0,
                                    "aliases": ["M.S ANGEL 50 X 50 X 5 MM - 03 pcs",
                                                "M.S ANGEL 50 X 50 X 5 MM"]},
    "Earthing holder":             {"unit": "Nos", "assumed_rate": 180.0,
                                    "aliases": []},
    # ⚠ "PO red paint" is seeded VERBATIM. See the module docstring: it is most
    #   likely red-oxide primer and it has deliberately NOT been renamed. The
    #   bare `po red paint` alias is gone — it chose a brand and a size.
    "PO red paint 20 ltr":         {"unit": "Can", "assumed_rate": 4200.0,
                                    "aliases": []},
    "PO red paint Asian 20 ltr":   {"unit": "Can", "assumed_rate": 4800.0,
                                    "aliases": []},
    "Yellow primer 20 ltr":        {"unit": "Can", "assumed_rate": 4000.0,
                                    "aliases": []},
    "Yellow primer Asian 20 ltr":  {"unit": "Can", "assumed_rate": 4600.0,
                                    "aliases": []},
    # "GP Thinner 20 ltr" and "GP Thinner 20ltr" — one item, two spellings.
    # The bare `gp thinner` alias is gone: it chose the 20-litre can.
    "GP thinner 20 ltr":           {"unit": "Can", "assumed_rate": 2600.0,
                                    "aliases": ["GP Thinner 20ltr"]},
    "Black Japan oil paint":       {"unit": "Ltr", "assumed_rate": 320.0,
                                    "aliases": []},
    "Wrapping coating 4mm":        {"unit": "Roll", "assumed_rate": 900.0,
                                    "aliases": []},
    "Paint roller":                {"unit": "Nos", "assumed_rate": 90.0,
                                    "aliases": []},
    # '2" roller' and "2 inch roller" — one item.
    "2 inch roller":               {"unit": "Nos", "assumed_rate": 70.0,
                                    "aliases": ['2" roller']},
    "Roller brush":                {"unit": "Nos", "assumed_rate": 110.0,
                                    "aliases": []},
    "Brush 2 inch":                {"unit": "Nos", "assumed_rate": 60.0,
                                    "aliases": []},
    "3 inch brush":                {"unit": "Nos", "assumed_rate": 90.0,
                                    "aliases": []},
    # "Cutting wheel", '4" Cutting wheel' and "Cutting wheel 4 inch" — one
    # item. The bare `cutting wheel` IS one of the client's three spellings,
    # which is why it survives where `grinding wheel` does not.
    "Cutting wheel 4 inch":        {"unit": "Nos", "assumed_rate": 45.0,
                                    "aliases": ["Cutting wheel",
                                                '4" Cutting wheel']},
    # ⚠ `grinding wheel` is NOT an alias. He wrote the size; a bare name here
    #   would hand out the 4-inch rate to somebody who named no size.
    "Grinding wheel 4 inch":       {"unit": "Nos", "assumed_rate": 60.0,
                                    "aliases": []},
    "Welding rod 10G Esab":        {"unit": "Kg",  "assumed_rate": 190.0,
                                    "aliases": []},
    "Welding cable 16 sqmm single core":
                                   {"unit": "Mtr", "assumed_rate": 165.0,
                                    "aliases": []},
    "Butane gas":                  {"unit": "Nos", "assumed_rate": 130.0,
                                    "aliases": []},
    "12mm drill bit (12 inch)":    {"unit": "Nos", "assumed_rate": 420.0,
                                    "aliases": []},
    # The client wrote "Safety shoes 10no". The "10no" is a QUANTITY and is
    # dropped from the canonical — it belongs in the qty box, not in the part
    # name — but his line is still his line, so it is an alias.
    "Safety shoes":                {"unit": "Pair", "assumed_rate": 1150.0,
                                    "aliases": ["Safety shoes 10no"]},
    "Welding gloves":              {"unit": "Pair", "assumed_rate": 130.0,
                                    "aliases": []},
    # `Lather` -> `Leather`.
    "Leather hand gloves":         {"unit": "Pair", "assumed_rate": 95.0,
                                    "aliases": ["Lather hand gloves"]},
    "White goggles":               {"unit": "Nos", "assumed_rate": 70.0,
                                    "aliases": []},
    "Welding glass (black & white)":
                                   {"unit": "Nos", "assumed_rate": 25.0,
                                    "aliases": []},
    "Red jacket":                  {"unit": "Nos", "assumed_rate": 650.0,
                                    "aliases": []},
    "Green jacket":                {"unit": "Nos", "assumed_rate": 650.0,
                                    "aliases": []},
    "7.5 HP DOL starter":          {"unit": "Nos", "assumed_rate": 3800.0,
                                    "aliases": []},
    "2-way push button box":       {"unit": "Nos", "assumed_rate": 480.0,
                                    "aliases": []},
    # "20a 1ph 3way Ac Box" appeared twice on the client's list. Seeded once.
    "20A 1ph 3-way AC box":        {"unit": "Nos", "assumed_rate": 420.0,
                                    "aliases": ["20a 1ph 3way Ac Box"]},
    "20A 1ph 2-way AC box":        {"unit": "Nos", "assumed_rate": 360.0,
                                    "aliases": []},
    "16A 3-pin plug":              {"unit": "Nos", "assumed_rate": 130.0,
                                    "aliases": []},
    "1.5 sq mm 3-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 62.0,
                                    "aliases": []},
    "1.5 sq mm 2-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 45.0,
                                    "aliases": []},
    "2.5 sq mm 2-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 68.0,
                                    "aliases": []},
    # "4sq 2core Flexible Wire" appeared twice on the client's list. Seeded
    # once. ⚠ This is the ONE row where the client's own spelling is on record,
    # and it is the evidence that the other three wire rows' canonical names
    # are house style rather than his words. No alias was invented for them.
    "4 sq mm 2-core flexible wire":
                                   {"unit": "Mtr", "assumed_rate": 105.0,
                                    "aliases": ["4sq 2core Flexible Wire"]},
    "16 sq mm wire":               {"unit": "Mtr", "assumed_rate": 175.0,
                                    "aliases": []},
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


def permitted_alias_keys() -> set:
    """
    Every normalised string an alias is allowed to be.

    The client's own lines, plus the stripped form of the two that carried a
    trailing quantity. **Nothing else, ever** — this function is the alias rule
    expressed as code, and `tests/test_po_parts_aliases.py` is what enforces it
    against `PARTS`.

    It is exported rather than reimplemented in the test on purpose: a test
    carrying its own copy of the rule is a second definition that can drift,
    which is the same defect the `xlNorm()` removal closed one file along.
    """
    keys = {_norm(line) for line in CLIENT_LINES}
    keys |= {_norm(stripped) for stripped in CLIENT_LINE_QUANTITIES.values()}
    return keys


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

    ⚠ **It misses more than it used to, and that is the fix rather than a
    regression.** 156 invented aliases were deleted on 29 August 2026 — see the
    alias rule in the docstring. A miss costs one typed rate; the alternative
    was a table that answered confidently for strings nobody had written.

    ⚠ **A hit returns an ASSUMED rate.** The caller must mark the line so the
    figure is never mistaken for one a vendor gave us — `purchase.py` sets
    `rate_is_assumed` and clears it the moment the rate is edited.
    """
    canonical = INDEX.get(_norm(description))
    if not canonical:
        return None
    row = PARTS[canonical]
    return canonical, row["unit"], float(row["assumed_rate"])


def prefill_map() -> dict:
    """
    `{normalised name or alias: {"u": unit, "r": assumed_rate}}` — the whole
    seeded table, flattened for a **dictionary lookup and nothing more**.

    Built from `INDEX`, deliberately, rather than from `PARTS`. `INDEX` is the
    exact key set `lookup()` matches on, so this map and the server agree on
    what "matches" **by construction** — the same keys, the same aliases
    already resolved, the same normalisation applied once, here, in Python.

    ⚠ **This exists so that the browser never has to know any of that.** The
    page renders this map and does one lookup on it. It holds no alias table,
    no canonical names and no rule about what counts as a match, so there is no
    second implementation to drift from this one. Until 29 August 2026 the page
    carried its own `xlNorm()` reimplementing `_norm()` in JavaScript, with
    nothing checking that the two agreed; the map it fed also carried **only
    canonical names**, so not one of the client's own spellings ever prefilled.

    ⚠ **It is a convenience, not the mechanism.** `purchase._parse_extra_lines()`
    fills a blank rate from this same table on POST, so the feature works with
    JavaScript disabled, broken, or never executed. A miss here costs a live
    preview and nothing else.

    ⚠ Every `r` is an ASSUMED PLACEHOLDER — see the top of this file.
    """
    return {key: {"u": PARTS[canonical]["unit"],
                  "r": float(PARTS[canonical]["assumed_rate"])}
            for key, canonical in INDEX.items()}


def suggestions() -> list:
    """
    Canonical names, sorted, for the form's `<datalist>`.

    Canonical names only. The aliases are for *matching* what somebody typed,
    not for offering the client's own typos back to him as suggestions.
    """
    return sorted(PARTS)
