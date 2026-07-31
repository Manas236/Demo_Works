"""
build_assets.py — Brand asset pipeline
======================================
Rebuilds every file in assets/ from the two source photographs the client
supplied (../logo.jpg and ../card.png). Run it only if a source photo is
replaced; the generated PNGs are committed, so the app never needs this at
runtime.

    python assets/build_assets.py

Requires: pillow, numpy, scipy.

What it does
------------
logo.jpg   — a phone photo of the SF roundel on a blurred backdrop.
             The disc is cut out on an exact circle, JPEG speckle is median
             filtered away, and every pixel is snapped onto the three real
             ink colours (white / brand red / brand navy) with a soft
             weighting so anti-aliased edges survive. Emitted at 1024/256/64,
             plus a mark-only variant with the white disc knocked out and a
             multi-resolution .ico.

card.png   — a phone photo of the signboard, shot under cool light and
             clipped by a maroon band on the right edge. It is white
             balanced off the blank paper, levelled, denoised, upscaled 3x
             and unsharp masked. The band is removed by taking the inked
             blob connected to the bottom-right corner. The SAMRUDDHI /
             FIRE lettering and the Ganesh motif are then cut out onto
             transparency as flat single-colour art.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── Brand inks (sampled from the source photos) ───────────────────────────────
WHITE     = np.array([255, 255, 255], np.float32)
RED       = np.array([227,  20,  22], np.float32)   # roundel "S"
NAVY      = np.array([ 42,   8, 110], np.float32)   # roundel "F"
WORD_RED  = np.array([178,  36,  52], np.float32)   # "SAMRUDDHI" (matte paint)
WORD_NAVY = np.array([ 38,  34,  92], np.float32)   # "FIRE"
SAFFRON   = np.array([242, 148,  74], np.float32)   # Ganesh motif


def _cut(arr, flat_colour, alpha_gamma=0.85, knee=238.0, span=120.0):
    """Turn an ink-on-paper crop into a transparent, single-colour PNG."""
    alpha = np.clip((knee - arr.mean(2)) / span, 0, 1) ** alpha_gamma
    ink = np.broadcast_to(flat_colour, arr.shape)
    out = Image.fromarray(np.dstack([ink, alpha * 255]).astype(np.uint8), "RGBA")
    bbox = out.getchannel("A").point(lambda p: 255 if p > 28 else 0).getbbox()
    return out.crop(bbox) if bbox else out


# =============================================================================
# 1. THE ROUNDEL  (logo.jpg -> logo*.png, favicon.ico)
# =============================================================================
def build_logo():
    im = Image.open(ROOT / "logo.jpg").convert("RGB")

    SS = 3                                   # supersample: clean, then downscale
    big = im.resize((im.width * SS, im.height * SS), Image.LANCZOS)
    big = big.filter(ImageFilter.MedianFilter(3))          # kill JPEG speckle
    A = np.array(big).astype(np.float32)
    H, W, _ = A.shape

    # Soft nearest-ink classification: flattens colour and removes the purple
    # JPEG halo, but keeps sub-pixel edge coverage.
    refs = np.stack([WHITE, RED, NAVY])
    d = np.linalg.norm(A[:, :, None, :] - refs[None, None, :, :], axis=3)
    wgt = np.exp(-(d ** 2) / (2 * 46.0 ** 2))
    wgt /= wgt.sum(2, keepdims=True) + 1e-8
    flat = (wgt[..., None] * refs[None, None]).sum(2)

    # The white disc, measured off the source (centre 406.5,378.5 / r 355).
    cx, cy, r = 406.5 * SS, 378.5 * SS, 353.0 * SS   # r trimmed 2px of ragged edge
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.hypot(xx - cx, yy - cy)
    disc = np.clip((r - dist) / (1.5 * SS), 0, 1)

    # Force everything outside the disc to white before downscaling, so the
    # dark blurred backdrop cannot bleed a grey halo into the rim.
    flat = flat * disc[..., None] + WHITE * (1 - disc[..., None])

    pad = int(4 * SS)
    box = (int(cx - r - pad), int(cy - r - pad), int(cx + r + pad), int(cy + r + pad))

    clean = Image.fromarray(np.dstack([flat, disc * 255]).astype(np.uint8), "RGBA").crop(box)
    for size, name in ((1024, "logo.png"), (256, "logo-256.png"), (64, "logo-64.png"),
                       (32, "favicon-32.png")):   # 32px PNG is what the app inlines
        clean.resize((size, size), Image.LANCZOS).save(HERE / name)

    # Mark only — white disc knocked out, ink keeps its anti-aliased edge.
    ink_a = np.clip((1.0 - wgt[..., 0]) * 1.35, 0, 1) * disc
    ink_rgb = ((wgt[..., 1:2] * RED + wgt[..., 2:3] * NAVY)
               / (wgt[..., 1:2] + wgt[..., 2:3] + 1e-6))
    mark = Image.fromarray(np.dstack([ink_rgb, ink_a * 255]).astype(np.uint8), "RGBA").crop(box)
    mark.resize((1024, 1024), Image.LANCZOS).save(HERE / "logo-mark.png")
    mark.resize((256, 256), Image.LANCZOS).save(HERE / "logo-mark-256.png")

    # Opaque variant for print / PDF letterheads that dislike alpha.
    onwhite = Image.new("RGB", clean.size, "white")
    onwhite.paste(clean, (0, 0), clean)
    onwhite.resize((1024, 1024), Image.LANCZOS).save(HERE / "logo-white-bg.png")

    clean.resize((256, 256), Image.LANCZOS).save(
        HERE / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


# =============================================================================
# 2. THE SIGNBOARD  (card.png -> card-clean.png, wordmark.png, ganesh.png)
# =============================================================================
def build_card():
    im = Image.open(ROOT / "card.png").convert("RGB")
    a = np.array(im).astype(np.float32)

    # White balance off a blank strip of the board, then pull levels so the
    # paper is truly white while the paint stays saturated.
    patch = a[0:20, 120:300].reshape(-1, 3)
    a = np.clip(a * (255.0 / np.percentile(patch, 60, axis=0)), 0, 255)
    lo, hi = 30.0, 232.0
    a = np.clip((a - lo) * (255.0 / (hi - lo)), 0, 255)

    card = Image.fromarray(a.astype(np.uint8))
    card = card.filter(ImageFilter.MedianFilter(3))                   # photo grain
    card = card.resize((im.width * 3, im.height * 3), Image.LANCZOS)  # then upscale
    card = card.filter(ImageFilter.UnsharpMask(radius=3, percent=110, threshold=3))
    card = ImageEnhance.Color(card).enhance(1.15)

    A = np.array(card).astype(np.float32)
    H, W, _ = A.shape

    # Erase the maroon band clipped along the right edge: it is the inked blob
    # connected to the bottom-right corner, and no letter touches it.
    lbl, _ = ndimage.label(A.mean(2) < 225)
    band = ndimage.binary_dilation(lbl == lbl[H - 2, W - 2], iterations=4)
    A[band] = 255.0
    card = Image.fromarray(A.astype(np.uint8))

    # Trim to the artwork with an even margin.
    inked = A.mean(2) < 220
    cols, rows = np.nonzero(inked.any(0))[0], np.nonzero(inked.any(1))[0]
    m = 26
    card = card.crop((max(0, cols.min() - m), max(0, rows.min() - m),
                      min(W, cols.max() + m), min(H, rows.max() + m)))
    card.save(HERE / "card-clean.png")

    A = np.array(card).astype(np.float32)
    H, W, _ = A.shape

    # Wordmark. Colour is assigned per *line* (SAMRUDDHI red, FIRE navy) rather
    # than per pixel — the painted letters carry shadows that make per-pixel
    # classification speckle.
    word = A[int(H * 0.44):int(H * 0.99), int(W * 0.01):]
    ink_rows = (255.0 - word.mean(2)).sum(1)
    lo_i, hi_i = int(len(ink_rows) * 0.35), int(len(ink_rows) * 0.62)
    split = lo_i + int(np.argmin(ink_rows[lo_i:hi_i]))          # the gap between lines

    l1, l2 = _cut(word[:split], WORD_RED), _cut(word[split:], WORD_NAVY)
    pad, gap = 12, 10
    w = max(l1.width, l2.width) + pad * 2
    h = l1.height + gap + l2.height + pad * 2
    mark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mark.paste(l1, ((w - l1.width) // 2, pad), l1)
    mark.paste(l2, ((w - l2.width) // 2, pad + l1.height + gap), l2)
    mark.save(HERE / "wordmark.png")
    mark.resize((480, int(480 * h / w)), Image.LANCZOS).save(HERE / "wordmark-480.png")

    # Ganesh motif from the top-left corner.
    _cut(A[int(H * 0.02):int(H * 0.42), int(W * 0.01):int(W * 0.28)],
         SAFFRON, alpha_gamma=0.65, knee=252.0, span=64.0).save(HERE / "ganesh.png")


if __name__ == "__main__":
    build_logo()
    build_card()
    print(f"Rebuilt brand assets in {HERE}")
