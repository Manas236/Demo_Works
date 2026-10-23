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

W, H = 2400, 330
ROUNDEL_AT, ROUNDEL_PX = (148, 38), 200
TEXT_AXIS = 1262         # x of the shared centre line of name and tagline
NAME_PT, NAME_TOP = 206, 62
TAG_PT, TAG_TOP = 58, 268
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
