# Project page charts — before / after (6 November 2026)

CLIENT_CHANGES.md §0's **sixty-ninth** block. Screenshots of the P&L panel's
`.pnl-figs` region on `/projects/view`, made by
`tests/test_pnl_chart_layout.py` with `PNL_SHOT_DIR` set (headless Chromium,
device scale 2, 1280 px images halved, 64-colour PNG to keep the repo small).

| world | before (`5730b15`) | after |
|---|---|---|
| RIL Jamnagar-like, 360 px | [before-jamnagar-360](before-jamnagar-360.png) | [after-jamnagar-360](after-jamnagar-360.png) |
| RIL Jamnagar-like, 390 px | [before-jamnagar-390](before-jamnagar-390.png) | [after-jamnagar-390](after-jamnagar-390.png) |
| RIL Jamnagar-like, 768 px | [before-jamnagar-768](before-jamnagar-768.png) | [after-jamnagar-768](after-jamnagar-768.png) |
| RIL Jamnagar-like, 1280 px | [before-jamnagar-1280](before-jamnagar-1280.png) | [after-jamnagar-1280](after-jamnagar-1280.png) |
| all five heads, 360 px | [before-all-five-360](before-all-five-360.png) | [after-all-five-360](after-all-five-360.png) |
| all five heads, 390 px | [before-all-five-390](before-all-five-390.png) | [after-all-five-390](after-all-five-390.png) |
| all five heads, 768 px | [before-all-five-768](before-all-five-768.png) | [after-all-five-768](after-all-five-768.png) |
| all five heads, 1280 px | [before-all-five-1280](before-all-five-1280.png) | [after-all-five-1280](after-all-five-1280.png) |

The overlap check (text bounding boxes from the browser, pairwise), on the
same five worlds at 360 / 390 / 768 / 1280 px:

- **before (`5730b15`)** — 4 of 5 worlds FAIL at 768 and 1280 px:
  *Purchase orders* × *PO charges outside the tax base*, *PO charges outside
  the tax base* × *Work orders*; and in the close-plan world *planned margin
  10.50L* × the closing bar's *10.25L*. (Names are hidden below 560 px, so
  the phone widths did not show it.)
- **after** — all 5 worlds pass at all 4 widths.

The test data are fixtures, not the client's live Jamnagar figures — no live
database is reachable from where this was built.
