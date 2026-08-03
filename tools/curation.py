"""
Curated identity for each of the 56 specs, keyed by the row in
sify_boq.xlsx!Quotation that defines the clause.

The clause text, the variants, the units and the rates are all read
mechanically from the sheet. Only these three things are a human judgement —
the short title that appears in a picker, the code, and the category — because
auto-deriving them from a 1300-character clause produces titles like
"And commissioning of 50-150 NB" and files MS pipe under Sprinklers.
"""

# row: (code, title, category)
CURATION = {
    # ── Section A ──────────────────────────────────────────────────────────
    5:  ("PIPE-MS-C-1239-SPR",  "MS 'C' class pipe, IS 1239, roll-grooved — sprinkler network", "Piping"),
    14: ("SPR-UPR-QR-INT-RED",  "Upright sprinkler, quick response intermediate, red, 15 NB K-80", "Sprinklers"),
    15: ("SPR-UPR-QR-INT-YEL",  "Upright sprinkler, quick response intermediate, yellow, 15 NB", "Sprinklers"),
    16: ("SPR-PEN-STD-15NB",    "Pendent sprinkler, standard response, 15 NB", "Sprinklers"),
    17: ("SPR-FLEX-DROP-1500",  "SS braided flexible drop pipe, 1500 mm", "Sprinklers"),
    18: ("VLV-BFLY-CI-150-TS",  "Cast iron butterfly valve 150 NB, gear operated, tamper switch", "Valves"),
    19: ("VLV-FLOW-SWITCH-A",   "Flow switch, 50-150 NB, pedal type, dual contact", "Valves"),
    20: ("VLV-GATE-50-TS-A",    "Gate valve 50 mm with tamper switch, IS 778 — sprinkler drain", "Valves"),
    21: ("VLV-BALL-50-TS",      "Ball valve 50 mm with tamper switch — sprinkler drain", "Valves"),
    22: ("VLV-TEST-DRAIN-25-A", "Test valve drain kit 25 mm with sight glass", "Valves"),
    23: ("VLV-AIR-VENT-25-A",   "Air vent valve 25 mm at sprinkler tap-offs", "Valves"),
    24: ("INS-PR-GAUGE-20-A",   "Pressure gauge, 0-20 kg/cm², with mounting", "Other"),
    25: ("PIPE-SUP-C-CHANNEL",  "MS C-channel (100 x 50) support assembly, compound wall", "Piping"),

    # ── Section B ──────────────────────────────────────────────────────────
    29: ("HYD-VALVE-SINGLE",    "Single outlet hydrant valve, SS, IS 5290", "Hydrant"),
    30: ("HYD-VALVE-DOUBLE",    "Double outlet hydrant valve, SS 304, IS 5290 Type B", "Hydrant"),
    31: ("VLV-AIR-REL-25-BR",   "Auto air release valve 25 NB, forged brass, chrome plated", "Valves"),
    32: ("HYD-HOSE-REEL-MS",    "Swinging type hose reel, mild steel IS 513 / IS 884", "Hydrant"),
    33: ("HYD-HOSE-RRL-63",     "Fire hose, non-percolating rubber reinforced lined, IS 636", "Hydrant"),
    34: ("HYD-HOSE-HP-63",      "High pressure fire hose, IS 14933 Type B, 63 mm", "Hydrant"),
    35: ("HYD-CABINET-900",     "Hose cabinet, non-metallic, 900 x 600 x 250 mm", "Hydrant"),
    36: ("HYD-CABINET-600",     "Hose cabinet, non-metallic, 600 x 450 x 250 mm", "Hydrant"),
    37: ("HYD-FB-CONNECTION",   "Fire brigade connection, gun-metal suction collecting head", "Hydrant"),
    38: ("HYD-FB-DRAWOUT",      "Fire brigade suction hose coupling, gun-metal draw-out", "Hydrant"),
    39: ("HYD-MONITOR-POST",    "Water monitor, stand post type with jet nozzle, IS 8442", "Hydrant"),
    40: ("HYD-BRANCH-PIPE-63",  "Branch pipe 63 mm instantaneous, gun-metal, 20 mm nozzle", "Hydrant"),
    41: ("HYD-FIREMANS-AXE",    "Fireman's axe, standard, rubber handle", "Hydrant"),
    42: ("SPR-UPR-15NB-B",      "Upright sprinkler, 15 NB, quartzoid bulb 68°C", "Sprinklers"),
    43: ("SPR-PEN-15NB-B",      "Pendent sprinkler, 15 NB, quartzoid bulb 68°C", "Sprinklers"),
    44: ("SPR-SIDEWALL-15NB",   "Sidewall sprinkler, 15 NB, quartzoid bulb 68°C", "Sprinklers"),
    46: ("VLV-ALARM-150NB",     "Alarm valve assembly 150 NB, pre-assembled vertical trim", "Valves"),
    47: ("VLV-BFLY-80-MOT",     "Motorised butterfly valve 80 NB with electrical actuator", "Valves"),
    48: ("VLV-TEST-DRAIN-25-B", "Test valve drain kit 25 mm with sight glass (hydrant)", "Valves"),
    49: ("VLV-FLOW-SWITCH-B",   "Flow switch, 50-150 NB, pedal type (hydrant)", "Valves"),
    50: ("VLV-AIR-VENT-25-B",   "Air vent valve 25 mm at sprinkler tap-offs (hydrant)", "Valves"),
    51: ("INS-PR-GAUGE-20-B",   "Pressure gauge, 0-20 kg/cm², with mounting (hydrant)", "Other"),
    52: ("PIPE-MS-C-1239-AG",   "MS heavy duty 'C' class pipe, IS 1239 / 3589 — above ground", "Piping"),
    62: ("PIPE-MS-C-1239-UG",   "MS heavy duty 'C' class pipe — below ground, welded & wrapped", "Piping"),
    66: ("VLV-OSY-SLUICE",      "OS&Y sluice valve, flanged ends, rising spindle, PN 2.0", "Valves"),
    71: ("VLV-BFLY-CI-GEAR",    "Cast iron butterfly valve, gear operated, with tamper switch", "Valves"),
    74: ("VLV-GATE-50-TS-B",    "Gate valve 50 mm with tamper switch — providing and fixing", "Valves"),
    75: ("VLV-NRV-SWING-DI",    "Swing type non-return valve, ductile iron, flanged or grooved", "Valves"),
    78: ("PIPE-FLEX-COUPLING",  "Heavy duty flexible coupling at pump outlet", "Piping"),
    83: ("PIPE-STRAINER-200",   "Y-type strainer 200 mm, ductile iron body", "Piping"),
    84: ("OTH-AIR-VESSEL-450",  "Precharged air vessel, 450 mm dia x 2000 mm height", "Other"),
    85: ("PIPE-MS-EXHAUST",     "MS 'C' class exhaust pipe, IS 1239 Pt 1 — diesel engine, clad", "Piping"),
    86: ("OTH-FLOW-METER",      "Venturi type fire pump test flow meter, flanged", "Other"),
    87: ("CIV-PEDESTAL-KG",     "RCC pedestal and pipe support, 300 x 300 x 300 (by weight)", "Civil"),
    88: ("CIV-PEDESTAL-NOS",    "RCC pedestal with MS channel support (by number)", "Civil"),
    89: ("CIV-TRENCH-1500",     "Excavation of trenches up to 1.5 m depth, up to 150 mm dia", "Civil"),
    90: ("CIV-RCC-PIPE-300",    "RCC pipe 300 mm dia, NP3 class — supply and laying", "Civil"),
    91: ("OTH-CFO-LIAISON",     "Liaisoning with statutory CFO for approval", "Other"),
    92: ("PIPE-SS316-50-HP",    "Stainless steel AISI 316 seamless pipe 50 mm, high pressure", "Piping"),
    93: ("VLV-SS316-50-ISO",    "Stainless steel 316 isolation valve 50 mm, high pressure", "Valves"),

    # ── Section C ──────────────────────────────────────────────────────────
    96:  ("PMP-ELEC-END-SUCT",  "Electric motor driven horizontal end suction fire pump", "Pumps"),
    101: ("PMP-DIESEL-END-SUCT", "Diesel engine driven horizontal end suction fire pump", "Pumps"),
    104: ("PNL-LT-FIRE-BOARD",  "LT fire panel board, IS 8623 — pump control", "Panels"),
}

# HSN (goods) and SAC (services) by category.
#
# ⚠ PLACEHOLDERS. The source workbook carries neither. These are plausible
#   chapter headings, not a classification anybody's CA has signed off, and a
#   wrong one costs the customer their input tax credit. Same caveat as
#   product._seed()'s twelve rows — and it matters more here, because a BOQ
#   line carries two of them.
#
#   7306 other tubes and pipes of iron or steel      8481 taps, cocks, valves
#   8424 mechanical spray appliances                 8413 pumps for liquids
#   8537 boards and panels for electrical control    6810 articles of concrete
#   9954 construction services: 995461 electrical installation,
#        995462 water plumbing and drain laying, 995468 other installation,
#        995429 other construction
CAT_CODES = {
    "Piping":     ("73063090", "995462"),
    "Valves":     ("84818090", "995462"),
    "Sprinklers": ("84248990", "995462"),
    "Hydrant":    ("84241000", "995462"),
    "Pumps":      ("84137010", "995468"),
    "Panels":     ("85371000", "995461"),
    "Civil":      ("68109990", "995429"),
    "Other":      ("",         "995468"),
}
