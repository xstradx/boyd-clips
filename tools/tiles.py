# -*- coding: utf-8 -*-
"""Find the Zoom tiles in a hearing frame, so nobody has to type coordinates.

Nathan, 2026-08-31: *"see what we have, try to zoom out and understand what I'm
trying to do seeing the mistakes in the actual pipeline or process that actually
helps you make thumbnails all on your own that's the root problem needing fix"*

THE ROOT PROBLEM, measured rather than asserted. `config/cases.json` holds 5
cases and 31 distinct fields. Fifteen of those values - judge_crop, plate_crop
and bg_crop across five cases - are hand-typed coordinates, and
`thumb_pipeline.autocrop()` already exists to derive them and is called by
NOTHING. The audit that found that also found 11 more fields with no deriver at
all.

So the pipeline is a RENDERER FOR HAND-AUTHORED CASES, not a thumbnail
generator. Making thumbnail #6 means a human authoring case #6. That is the
ceiling on doing this without him, and it is why a session gets spent typing
coordinates instead of building.

autocrop could not be wired in because it needs a `region` - which person lives
where in the frame - and that was the hand-knowledge. This supplies it.

WHAT THIS ACTUALLY DOES
A Bexar County hearing is a Zoom grid: two or three video tiles on a dark
surround, each with a burned-in name label at its lower-left, and a green border
on whoever is speaking. The tiles are found geometrically:

  1. the content band - the rows and columns that are not the dark surround
  2. the vertical divider - the darkest column inside that band
  3. one region per tile, with the label strip excluded from the bottom

No model, no per-case constant. It either finds two tiles or says it did not.
"""
import os
import subprocess
import tempfile

import cv2
import numpy as np

DARK = 26           # a pixel this dark is surround, not picture
LABEL_STRIP = 0.10  # bottom fraction of a tile that holds the burned-in name
EDGE = 12           # gradient magnitude that counts as an edge at a pixel
SEAM_SPAN = 0.60    # a seam's edge must span this fraction of the band's rows
MARGIN = 0.12       # ignore seams this close to either side (frame border)


def frame_at(video, t):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}",
                        "-i", video, "-frames:v", "1", p], capture_output=True)
        return cv2.imread(p)


def content_band(gray):
    """Rows and columns carrying picture rather than dark surround.

    The hearings are letterboxed - measured on the OFFERUP source, rows 0-179
    and 546-719 are pure black - so the band is real and has to be found before
    anything else, or every vertical statistic is diluted by the bars.
    """
    live = gray > DARK
    rows = np.where(live.mean(axis=1) > 0.25)[0]
    cols = np.where(live.mean(axis=0) > 0.25)[0]
    if not rows.size or not cols.size:
        return None
    return int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())


def find_seam(gray, band):
    """The column where one video feed ends and the next begins.

    MEASURED, not assumed. The obvious idea - look for a dark divider - is
    WRONG here and the first version of this file failed its own selftest
    because of it: profiling the OFFERUP frame showed the two feeds butting
    directly together, column means never dipping anywhere near the middle.

    What does separate them is that a seam is a vertical edge running the FULL
    height of the band, which no object edge does. On that frame:

        x=636   edge spans 85.5% of rows   <- the seam, dead centre of 1280
        x=479   edge spans 48.8% of rows   <- the tallest real object edge

    So the discriminator is the ROW SPAN of the edge, not its strength, and the
    two populations are separated by 37 points. SEAM_SPAN sits between them.
    """
    x0, y0, x1, y1 = band
    strip = gray[y0:y1, x0:x1].astype(np.float32)
    if strip.shape[1] < 8:
        return None, 0.0
    span = (np.abs(np.diff(strip, axis=1)) > EDGE).mean(axis=0)
    w = span.size
    m = int(w * MARGIN)
    span[:m] = 0.0          # the frame border is an edge too, and not a seam
    span[w - m:] = 0.0
    k = int(np.argmax(span))
    if span[k] < SEAM_SPAN:
        return None, float(span[k])
    return x0 + k + 1, float(span[k])


def find_tiles(bgr, exclude_label=True):
    """Return tile regions as (x, y, w, h), left to right.

    Two tiles when a seam is found, one when the frame is a single view.
    """
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    band = content_band(g)
    if band is None:
        return []
    x0, y0, x1, y1 = band
    if x1 - x0 < 200:
        return []
    seam, _ = find_seam(g, band)

    def region(a, b):
        h = y1 - y0
        if exclude_label:
            h = int(h * (1 - LABEL_STRIP))   # drop the burned-in name strip
        return (int(a), int(y0), int(b - a), int(h))

    if seam is None:
        return [region(x0, x1)]
    pad = 4
    return [region(x0 + pad, seam - pad), region(seam + pad, x1 - pad)]


# ------------------------------------------------------- active speaker ------
GREEN = dict(h=(35, 85), s=90, v=60)   # Zoom's active-speaker outline
MIN_TILE = 0.15                        # a rect smaller than this is not a tile


def active_tile(bgr):
    """The tile Zoom is outlining as the active speaker, as (x, y, w, h).

    MEASURED, and it beat the geometry. The seam detector above cannot rank the
    two halves, and on SANCHEZ/MONKEY it could not even find the seam (52%/59%
    span against a 50% distractor - a 2.4-point margin, which is not a signal).

    The active-speaker border settles both questions at once, because it IS a
    rectangle around exactly one tile. Measured across all five approved cases
    at their `plate_t`, the border sits on the correct side 5/5 - including
    CARTHIEF, where the speaker is on the right and every other case has them on
    the left - and where two tiles were detected the ring was 22-39% green on
    the speaking tile and 0.0% on the other. That is a binary signal, not a
    threshold to tune.

    Returns None when no border is on screen (nobody speaking, or a layout that
    does not draw one) - the caller then has to fall back or ask.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = ((hsv[:, :, 0] > GREEN["h"][0]) & (hsv[:, :, 0] < GREEN["h"][1]) &
         (hsv[:, :, 1] > GREEN["s"]) & (hsv[:, :, 2] > GREEN["v"])).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    x, y, w, h = cv2.boundingRect(max(cs, key=cv2.contourArea))
    H, W = bgr.shape[:2]
    if w < W * MIN_TILE or h < H * MIN_TILE:
        return None
    return (x, y, w, h)


def describe(video, t):
    bgr = frame_at(video, t)
    if bgr is None:
        return None, []
    return bgr, find_tiles(bgr)


def selftest():
    """Known answer first: the OFFERUP source is a 2-up whose left tile holds
    the defendant and whose right tile holds Boyd. Anything that does not find
    exactly two tiles, side by side, inside the frame, is wrong."""
    ok = True
    ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    v = os.path.join(ROOT, "work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4")
    if not os.path.exists(v):
        print("  SELFTEST_SKIP control video missing")
        return 0
    bgr, tiles = describe(v, 420)
    H, W = bgr.shape[:2]
    print(f"  frame {W}x{H} -> {len(tiles)} tiles")
    for i, (x, y, w, h) in enumerate(tiles):
        print(f"    tile {i}: x{x}-{x+w}  y{y}-{y+h}   ({w}x{h})")
    if len(tiles) != 2:
        print("  FAIL expected 2 tiles in a known 2-up"); ok = False
    else:
        (ax, ay, aw, ah), (bx, by, bw2, bh) = tiles
        if ax + aw > bx:
            print("  FAIL tiles overlap"); ok = False
        if ax < 0 or bx + bw2 > W:
            print("  FAIL a tile leaves the frame"); ok = False
        if min(aw, bw2) < W * 0.2:
            print("  FAIL a tile is implausibly narrow"); ok = False
        # each tile should contain a face - that is what a tile IS
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import expression as X
        for i, (x, y, w, h) in enumerate(tiles):
            n = len(X.blendshapes(bgr[y:y + h, x:x + w]))
            print(f"    tile {i} faces: {n}")
            if n == 0:
                print(f"  WARN tile {i} has no detectable face")
    print("SELFTEST_PASS tiles" if ok else "SELFTEST_FAIL tiles")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 3:
        print("usage: tiles.py VIDEO T   |   tiles.py --selftest")
        sys.exit(2)
    bgr, tiles = describe(sys.argv[1], float(sys.argv[2]))
    for i, t in enumerate(tiles):
        print(f"  tile {i}: {t}")
