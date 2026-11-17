"""
Print sweep — optional: eight pages to an image, in document order, so every
page can be looked at.

    python tools/print_sweep/contact_sheets.py <out_dir>/png <sheets_dir>
"""
import sys, pathlib, re
from PIL import Image, ImageDraw
src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
key = lambda p: (p.stem.rsplit("__p", 1)[0], int(p.stem.rsplit("__p", 1)[1]))
files = sorted(src.glob("*.png"), key=key)
per, cols, tw = 8, 4, 440
for n in range(0, len(files), per):
    chunk = files[n:n + per]
    th = []
    for f in chunk:
        im = Image.open(f).convert("RGB"); s = tw / im.width
        t = im.resize((tw, int(im.height * s)))
        ImageDraw.Draw(t).rectangle((0, 0, tw - 1, t.height - 1), outline=(200, 0, 0))
        ImageDraw.Draw(t).text((4, t.height - 12), f.stem, fill=(200, 0, 0))
        th.append(t)
    rows = (len(th) + cols - 1) // cols; h = max(t.height for t in th)
    sheet = Image.new("RGB", (cols * (tw + 6), rows * (h + 6)), (120, 120, 120))
    for i, t in enumerate(th):
        sheet.paste(t, ((i % cols) * (tw + 6), (i // cols) * (h + 6)))
    sheet.save(out / f"sheet_{n // per:02d}.png")
print(len(files))
