"""
Print sweep — step 3 of 3 (see render_variants.py for the whole run).

    python tools/print_sweep/pdf_check.py <out_dir>

Needs PyMuPDF (`pip install pymupdf`; a tool dependency, not in
requirements.txt). Rasterises every page of <out_dir>/pdf/*.pdf to
<out_dir>/png/ at 150 dpi and checks each PAGE, which is where the repeated
letterhead and page breaks happen:

    near-edge          text within 5 mm of the paper's edge (the margin is 10)
    text-on-text       two text runs overlapping
    text-under-image   text under a picture (the stamp over "For SAMRUDDHI
                       FIRE" is by design — docsheet._sig_art)

and prints, per document, the page count and text runs per page: a last page
with ~18 runs is the letterhead, the foot and a signature panel on its own.
Writes <out_dir>/pdf.json.
"""
import json
import pathlib
import sys

import pymupdf

MM = 72 / 25.4
root = pathlib.Path(sys.argv[1])
png = root / "png"
png.mkdir(exist_ok=True)
report, pages_total = {}, 0


def inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, x1 - x0) * max(0, y1 - y0)


for pdf in sorted((root / "pdf").glob("*.pdf")):
    doc = pymupdf.open(pdf)
    issues, counts = [], []
    for pno, page in enumerate(doc):
        pages_total += 1
        page.get_pixmap(dpi=150).save(png / f"{pdf.stem}__p{pno + 1}.png")
        W, H = page.rect.width, page.rect.height
        spans = []
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    t = s["text"].strip()
                    if not t:
                        continue
                    # watermark: rotated line
                    rot = ln["dir"] != (1.0, 0.0)
                    spans.append((t, pymupdf.Rect(s["bbox"]), rot, s["size"]))
        imgs = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
        body = [s for s in spans if not s[2]]
        counts.append(len(body))
        for t, r, rot, sz in body:
            if r.x0 < 5 * MM or r.x1 > W - 5 * MM or r.y0 < 5 * MM or r.y1 > H - 5 * MM:
                issues.append({"p": pno + 1, "kind": "near-edge", "text": t[:50],
                               "bbox_mm": [round(v / MM, 1) for v in r]})
        for i, (t, r, rot, sz) in enumerate(body):
            for t2, r2, _, sz2 in body[i + 1:]:
                a = inter(r, r2)
                if a > 0.25 * min(r.get_area(), r2.get_area()) and a > 4:
                    issues.append({"p": pno + 1, "kind": "text-on-text", "a": t[:40], "b": t2[:40],
                                   "y_mm": round(r.y0 / MM, 1)})
            for ir in imgs:
                a = inter(r, ir)
                if a > 0.15 * r.get_area():
                    issues.append({"p": pno + 1, "kind": "text-under-image", "text": t[:50],
                                   "img_mm": [round(v / MM, 1) for v in ir],
                                   "text_mm": [round(v / MM, 1) for v in r]})
    report[pdf.stem] = {"pages": len(doc), "spans_per_page": counts, "issues": issues}

json.dump(report, open(root / "pdf.json", "w"), indent=1)
print("pages", pages_total)
for k, v in report.items():
    kinds = {}
    for i in v["issues"]:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    print(f"{k:38s} pages={v['pages']:2d} spans={v['spans_per_page']} {kinds or ''}")
