"""
build_banner.py — the client's own letterhead banner
====================================================
Rebuilds `assets/letterhead-banner.png`, the band at the top of every printed
document (`branding.letterhead_top()`). Run it only if the banner has to
change; the PNG is committed, so the app never needs this at runtime.

    python assets/build_banner.py

Requires: pillow, plus the two Windows fonts named below.

Where it comes from
-------------------
Manas sent a screenshot of the banner on 21 October 2026 and asked for it to
replace the text letterhead on every document. The screenshot was not used
as-is: it was taken from an Excel sheet, so it carries the sheet's gridlines —
one of them runs full width between the name and the tagline, and would have
printed as a grey rule across every page — and at 1186 px it is ~160 dpi across
an A4 band.

So the banner is rebuilt from the same three ingredients the client's own
workbooks use (`client_docs/Kalyan_Site.xlsx`, `Skyline.xlsx`, `DC-SF.xlsx`,
`Measurement_Sheet_updated.xlsx` — read with openpyxl):

* **SAMRUDDHI FIRE** — cell text in **Algerian**, colour `FFFF0000`. Algerian
  ships with Microsoft Office, which is why this is an image and not a web
  font: no phone and no browser has it.
* **FIRE PROTECTION AND SAFETY ENGINEERS** — the client's own tagline. The
  screenshot draws it in plain Arial; its ink measured ≈ #2D5567 off the
  darkest pixels, and `TAG_INK` is the Office palette swatch nearest that (a
  thin stroke in a screenshot never reaches its full ink). Two of the
  workbooks set the same words in Arial Black #002060 instead — the screenshot
  is what was asked for, so it is what is followed.
* **The SF roundel** — `assets/logo.png`, the 1024 px cut `build_assets.py`
  already makes from `../logo.jpg`. The workbooks embed the same mark at
  ≤ 201 px.

The layout is the screenshot's, scaled ×2.02: roundel at the left, name and
tagline centred on one axis to its right. It is drawn on a 2400 × 330 canvas
and then **cropped to its own ink** plus `PAD` — the white around the artwork
is the page's business, not the picture's. Drawn uncropped across a full
190 mm band it stood 26 mm tall and pushed a three-line quotation onto a second
page carrying one line; `branding.letterhead_top()` draws the cropped artwork
130 mm wide instead, 18.5 mm tall, against the ~15 mm of the text letterhead it
replaced. 1928 px across 130 mm is ~375 dpi, and a 64-colour palette keeps it
at ~27 KB — about the weight of the 256 px roundel it replaces.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent

FONTS = Path(r"C:\Windows\Fonts")
NAME_FONT = FONTS / "ALGER.TTF"          # Algerian — Microsoft Office
TAG_FONT = FONTS / "arial.ttf"

NAME = "SAMRUDDHI FIRE"
TAGLINE = "FIRE PROTECTION AND SAFETY ENGINEERS"
NAME_INK = "#FF0000"     # the workbooks' own cell colour, FFFF0000
TAG_INK = "#215967"      # see the docstring

W, H = 2400, 330         # superseded below, 14 November 2026
# ⚠ 29 October 2026 (CLIENT_CHANGES.md §0 fifty-sixth block): the client
#   found the SF mark too small. It was (148, 38) at 200 px; it is now 1.5×,
#   centred on the banner's height in the white the old mark left, so the
#   banner's SIZE did not change — the 130 mm / page-count decision in
#   `branding.letterhead_top()` is untouched. The committed PNG was produced by
#   compositing logo.png at these exact figures onto the previous banner,
#   because the Algerian font is not on a Linux box; the crop is unchanged
#   (the NAME sets the top, the ROUNDEL sets the left), so a run of this
#   builder on Windows should reproduce it to the pixel — check before
#   committing one.
#
# ⚠ 8 November 2026 (Yogesh's call, CLIENT_CHANGES.md §0): the mark was
#   TOP-ALIGNED to the lettering. It was (140, 36), which centred it on the
#   banner's height — the name's caps begin at the very top of the ink while
#   the mark's centre sat on the centre of the name-plus-tagline block, so the
#   mark printed 17 px (1.15 mm on paper) BELOW the cap line. That centring is
#   the whole cause; there is no corrective offset anywhere. y goes 36 -> 19,
#   which is -17 px, and the mark's ink top now equals the name's at 12 px in
#   the cropped artwork. Nothing else moved: same ROUNDEL_PX, same TEXT_AXIS,
#   same NAME_*/TAG_* , so the name, the tagline and the 1928 x 274 crop are
#   untouched and the 130 mm page-count decision still holds.
#   The committed PNG was again produced on Linux, by translating the existing
#   mark up 17 px inside the palette (the name/tagline band is byte-identical
#   and the 64-colour palette is unchanged) rather than by running this file,
#   which needs the Windows fonts.
#   ⚠ The mark and the name now set the crop's top TOGETHER. If a Windows
#     rebuild lands the mark's ink one pixel above the name's, `getbbox()`
#     takes the mark's row and the canvas grows a pixel taller — which would
#     rescale every printed banner. Check the output is 1928 x 274 and that
#     the two ink tops agree before committing a rebuild.
#
# ⚠ 14 November 2026 (Yogesh, option A, CLIENT_CHANGES.md §0 seventy-fourth
#   block, no charge): the mark moves 15 mm LEFT and 3 mm HIGHER on paper than
#   8 November left it — 222 px and 44 px at 1928 px = 130 mm. Its size does
#   not change and the name and tagline do not move ON PAPER.
#   A canvas "extended to the left and the top" is not something this builder
#   draws directly — it crops to ink, so the crop's origin follows the
#   leftmost/topmost ink. It is expressed the equivalent way instead: the
#   ROUNDEL stays at (140, 19), the TEXT moves 222 px right and 44 px down
#   (TEXT_AXIS 1262 -> 1484, NAME_TOP 62 -> 106, TAG_TOP 268 -> 312), and the
#   canvas grows by the same amounts (2400 x 330 -> 2622 x 374) so nothing is
#   clipped. The mark now sets the crop's left AND top alone; the text sets
#   its right and bottom. Output: 2150 x 318, mark ink at (12, 13), name ink
#   at (529, 56) — 222 / 44 px from the mark, where they were 307 / 12.
#   The committed PNG was again produced on LINUX, without the Algerian font,
#   by moving pixels: the old 1928 x 274 artwork pasted at (222, 44) byte for
#   byte, then its columns 0..288 (the mark and its white) moved back to
#   (0, 0) byte for byte. Same 64-colour palette, no resample.
#   `branding.letterhead_top()` draws it at 130 mm x 2150 / 1928 with a left
#   offset of -222 px and a top margin of -44 px in the same scale, so the
#   NAME prints where it did. Its size and those figures go together.
#   ⚠ CHECK THE OUTPUT SIZE AND INK TOPS BEFORE COMMITTING A REBUILD: it must
#     be 2150 x 318, the mark's ink top must be row 13 (12 with the builder's
#     own RGB threshold) and the name's ink top exactly 44 rows below it, the
#     name's ink left exactly 222 + 307 columns from the mark's ink left 12.
#     A pixel's difference rescales or shifts every printed banner — and
#     changes the numbers in letterhead_top() with it.
W, H = 2622, 374
ROUNDEL_AT, ROUNDEL_PX = (140, 19), 300
TEXT_AXIS = 1484         # x of the shared centre line of name and tagline
NAME_PT, NAME_TOP = 206, 106
TAG_PT, TAG_TOP = 58, 312
PAD = 12                 # white kept round the ink after the crop, in px
INK = 20                 # how far from white a pixel must be to count as ink

OUT = HERE / "letterhead-banner.png"


def _centred(draw, text, font, top, ink):
    left, upper, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text((TEXT_AXIS - (right - left) // 2 - left, top - upper), text,
              font=font, fill=ink)


def build() -> Path:
    missing = [str(f) for f in (NAME_FONT, TAG_FONT) if not f.exists()]
    if missing:
        raise SystemExit(f"font not found: {missing} — this needs the Windows "
                         f"fonts the client's workbooks use")
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    roundel = Image.open(HERE / "logo.png").convert("RGBA")
    roundel = roundel.resize((ROUNDEL_PX, ROUNDEL_PX), Image.LANCZOS)
    img.paste(roundel, ROUNDEL_AT, roundel)

    _centred(draw, NAME, ImageFont.truetype(str(NAME_FONT), NAME_PT),
             NAME_TOP, NAME_INK)
    _centred(draw, TAGLINE, ImageFont.truetype(str(TAG_FONT), TAG_PT),
             TAG_TOP, TAG_INK)

    ink = ImageOps.invert(img.convert("L")).point(lambda p: 255 if p > INK else 0)
    left, top, right, bottom = ink.getbbox()
    img = img.crop((left - PAD, top - PAD, right + PAD, bottom + PAD))

    img.quantize(colors=64, method=Image.MEDIANCUT).save(OUT, optimize=True)
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"wrote {out.relative_to(HERE.parent)} ({out.stat().st_size:,} bytes)")
