"""Pull down the courtroom's blown light fixtures, locally.

Nathan, 2026-08-29: "i cant tell much of a difference i just think the super
bright white spots need to be fixed some how".

He is right and the previous attempt was the wrong shape. A global highlight
knee moves EVERY bright pixel a little, so a 5-point mean shift gets spread
across the whole frame and is invisible, while the actual defect - a dozen
discrete ceiling fixtures sitting at a flat 255 - stays a white hole. Measured
on the finished thumbnails, blobs over 300px above 246:

    CARTHIEF  23 blobs, largest 4023px, the top ones at a flat mean L of 255
    SANCHEZ   27 blobs, largest 7467px
    OFFERUP    9 blobs, largest 2654px

A pixel at a flat 255 has no detail left to recover, so this does not pretend to
restore any. It DIMS each blob and feathers the edge, which is what makes a light
read as a light rather than as a hole punched in the picture.

TWO THINGS IT MUST NOT TOUCH, both white by design:
  * the TYPE - white and yellow headline, identified by its black stroke: a
    bright core with a very dark pixel within 17px. Nothing photographic in a
    courtroom does that, which is the same signature used to verify caption
    placement after a brightness threshold measured the ceiling instead.
  * the ARROW - pure red #FD0101, deliberately outside the grade entirely.

Used two ways:
    python scripts/kill_hotspots.py --image X.jpg --out Y.jpg
    python scripts/kill_hotspots.py --check <dir>     # gate G11
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import scipy.ndimage as nd
from PIL import Image

HOT = 246          # a fixture reads as blown from about here up
MIN_BLOB = 250     # px; below this it is a specular fleck and looks natural
TARGET = 232       # what a dimmed fixture is pulled toward
FEATHER = 7.0      # sigma; a hard edge would read as a grey patch


def protected(a: np.ndarray) -> np.ndarray:
    """Type and arrow: white or red on purpose, never dimmed."""
    L = np.asarray(Image.fromarray(a).convert("L"), dtype=np.uint8)
    near_dark = nd.maximum_filter((L < 45).astype(np.uint8), size=17) > 0
    type_ink = (L > 200) & near_dark
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    arrow = (r > 150) & (g < 70) & (b < 70)
    # grow a little so the stroke's own anti-aliasing is covered too
    return nd.binary_dilation(type_ink | arrow, iterations=4)


def hotspots(a: np.ndarray, hot: int = HOT, min_blob: int = MIN_BLOB):
    L = np.asarray(Image.fromarray(a).convert("L"), dtype=np.float32)
    keep_out = protected(a)
    blown = (L > hot) & ~keep_out
    lbl, k = nd.label(blown)
    if not k:
        return np.zeros_like(blown), 0
    sizes = nd.sum(blown, lbl, range(1, k + 1))
    big = np.zeros_like(blown)
    n = 0
    for i, s in enumerate(sizes):
        if s >= min_blob:
            big |= (lbl == i + 1)
            n += 1
    return big, n


def kill(img: Image.Image, hot: int = HOT, min_blob: int = MIN_BLOB,
         target: int = TARGET, feather: float = FEATHER):
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    mask, n = hotspots(a, hot, min_blob)
    if n == 0:
        return img, 0
    # feather so the correction has no visible boundary
    w = nd.gaussian_filter(mask.astype(np.float32), sigma=feather)
    w = np.clip(w / max(w.max(), 1e-6), 0, 1)[:, :, None]

    f = a.astype(np.float32)
    L = np.asarray(img.convert("L"), dtype=np.float32)[:, :, None]
    # scale each blown pixel toward `target` while keeping its colour ratio, so
    # a warm ceiling light stays warm instead of going neutral grey
    scale = np.clip(target / np.maximum(L, 1.0), 0.0, 1.0)
    dimmed = f * scale
    out = f * (1 - w) + dimmed * w
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", type=Path,
                    help="a directory: report how many blown blobs remain")
    ap.add_argument("--hot", type=int, default=HOT)
    ap.add_argument("--min-blob", type=int, default=MIN_BLOB)
    ap.add_argument("--target", type=int, default=TARGET)
    a = ap.parse_args()

    if a.check:
        d = a.check if a.check.is_absolute() else (Path.cwd() / a.check)
        files = sorted(p for p in d.glob("*.jpg") if not p.name.startswith("_"))
        fails = 0
        for p in files:
            arr = np.asarray(Image.open(p).convert("RGB"), dtype=np.uint8)
            _, n = hotspots(arr, a.hot, a.min_blob)
            print(f"  {p.name:22} {n} blown blob(s) over {a.min_blob}px")
            if n:
                fails += 1
        print(f"HOTSPOTS: {fails} failures")
        return 0 if fails == 0 else 1

    if not (a.image and a.out):
        print("give --image and --out, or --check <dir>")
        return 2

    img = Image.open(a.image).convert("RGB")
    before = np.asarray(img.convert("L"), dtype=float)
    _, nb = hotspots(np.asarray(img, dtype=np.uint8), a.hot, a.min_blob)
    out, n = kill(img, a.hot, a.min_blob, a.target)
    after = np.asarray(out.convert("L"), dtype=float)
    _, na = hotspots(np.asarray(out, dtype=np.uint8), a.hot, a.min_blob)
    print(f"  {nb} blown blob(s) -> {na}   "
          f">246 {(before > 246).mean() * 100:.2f}% -> {(after > 246).mean() * 100:.2f}%   "
          f"mean {before.mean():.1f} -> {after.mean():.1f}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out, "JPEG", quality=95, subsampling=0)
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
