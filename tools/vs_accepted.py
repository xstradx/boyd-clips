"""R52 - no thumbnail is judged, gated or shown to him until it has been laid
next to the accepted five and LOOKED AT.

2026-09-02. He rejected a batch of five, and I answered with five invented
scalar metrics in a row - skin chroma, micro-texture, hair alpha, face
luminance, skin a* - each measured on a handful of files, each failing to
separate his accepted builds from the ones he had just rejected. The a* one I
even reported to him as a clean separator off a 4-face sample; across all ten
it overlapped. His question was the right one: *"Fix the reason why you're not
able to see or detect that maybe and find and fix root cause"*.

Root cause: every gate in this repo reduces a thumbnail to ONE number and
compares it to a threshold. His judgement is a whole-image comparison against
the corpus he already approved. One number per build cannot carry that, and
inventing another number is the failure repeating.

What actually worked, in seconds, after hours of metrics: putting the build
beside SANCHEZ and looking. On the six-up sheet the answer was immediate -
the accepted five are dark, dense and contrasty; ours was the only high-key,
flat, pale tile in the set. Nothing in the numbers said that.

So this tool is not another metric. It builds the sheet and refuses to be
skipped: `check_thumb_grade` and the build ledger require the sheet to exist
and be newer than the thumbnail, and the reading is mine, out loud, at 100%.

Usage:
  python tools/vs_accepted.py OUT.jpg [--label NAME] [--sheet PATH]
  python tools/vs_accepted.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOOR = os.path.join(ROOT, "config", "quality_floor.json")
TILE_W = 440
GAP = 8


def accepted_paths() -> list[tuple[str, str]]:
    files = json.load(open(FLOOR, encoding="utf-8"))["files"]
    out = []
    for k, rel in files.items():
        p = rel if os.path.isabs(rel) else os.path.join("D:/Boyd Clips", rel)
        if os.path.exists(p):
            out.append((k, p))
    return out


def sheet_path_for(out_jpg: str) -> str:
    d, n = os.path.split(out_jpg)
    return os.path.join(d, "_vs_accepted_" + os.path.splitext(n)[0] + ".jpg")


def build(out_jpg: str, sheet: str | None = None, label: str | None = None) -> str:
    tiles = accepted_paths()
    if len(tiles) < 3:
        raise SystemExit("vs_accepted: fewer than 3 accepted builds on disk - nothing to compare against")
    tiles.append((label or ("NEW " + os.path.basename(out_jpg)), out_jpg))
    ims = []
    for _, p in tiles:
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((TILE_W, int(im.height * TILE_W / im.width))))
    cols = 3
    rows = (len(ims) + cols - 1) // cols
    h = ims[0].height
    canvas = Image.new("RGB", (cols * TILE_W + (cols - 1) * GAP, rows * h + (rows - 1) * GAP), (12, 12, 12))
    for i, im in enumerate(ims):
        canvas.paste(im, ((i % cols) * (TILE_W + GAP), (i // cols) * (h + GAP)))
    sheet = sheet or sheet_path_for(out_jpg)
    canvas.save(sheet, quality=94, subsampling=0)
    order = ", ".join(k for k, _ in tiles)
    print(f"VS_ACCEPTED_OK  {sheet}")
    print(f"  {len(ims)} tiles, reading order: {order}")
    print("  NOT AUTOMATED: the comparison itself. Read this sheet at 100% and say "
          "what is different about the new tile before showing him anything.")
    return sheet


def fresh_for(out_jpg: str) -> bool:
    """True when a sheet exists for this thumbnail and is not older than it."""
    s = sheet_path_for(out_jpg)
    return os.path.exists(s) and os.path.getmtime(s) >= os.path.getmtime(out_jpg)


def selftest() -> int:
    ok = True
    acc = accepted_paths()
    print(f"accepted builds found: {len(acc)}")
    if len(acc) < 3:
        ok = False
        print("  !! need at least 3")
    # the sheet must be REFUSED as stale when the thumbnail is newer than it
    import tempfile
    import time
    with tempfile.TemporaryDirectory() as td:
        fake = os.path.join(td, "FAKE_thumb.jpg")
        Image.new("RGB", (1280, 720), (30, 30, 30)).save(fake)
        print("  stale check, before any sheet:", "REFUSED" if not fresh_for(fake) else "!! ACCEPTED")
        ok &= not fresh_for(fake)
        build(fake, label="NEW control")
        print("  after building the sheet:", "fresh" if fresh_for(fake) else "!! still refused")
        ok &= fresh_for(fake)
        time.sleep(0.01)
        Image.new("RGB", (1280, 720), (40, 40, 40)).save(fake)   # rebuild the thumbnail
        stale = not fresh_for(fake)
        print("  thumbnail rebuilt after the sheet:", "REFUSED (stale)" if stale else "!! ACCEPTED a stale sheet")
        ok &= stale
    print("VS_ACCEPTED_SELFTEST_OK" if ok else "VS_ACCEPTED_SELFTEST_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--sheet")
    ap.add_argument("--label")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    build(a.out, a.sheet, a.label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
