# -*- coding: utf-8 -*-
"""R42 - variants he is asked to choose between must differ at feed size.

Nathan, 2026-08-29 21:26: "I don't see levels" (#41). I had offered three
background-darkening levels at -8 / -14 / -20%. Measured 2026-09-01 as the
mean absolute difference of the 168x94 sidebar downscale against the original
(this file's feed_diff, background darkened under the placed alphas):
4.4 / 7.5 / 10.5 code values - and he could not see any of them. Pairs he did
tell apart: the two CARTHIEF title variants 12.5, MONKEY A vs B 14.2, circle
vs arrow 46.8. A pair he called the same, MONKEY_B vs B2, is 9.9. A choice he
cannot perceive is not a choice, it is a delay.

    python tools/check_variants.py A.jpg B.jpg [C.jpg ...]
    python tools/check_variants.py --selftest

Every pair must differ by >= MIN_DIFF mean-abs code values at 168x94 (image
resized to 1280x720 INTER_AREA first, then to the sidebar, then gray).
VARIANTS_OK / VARIANTS_FAIL, exit 0/1. The margin between the largest
invisible level (10.5) and the smallest distinguished pair (12.5) is thin and
is printed with every result; a pair he calls identical above 12 moves the
threshold up.
"""
import glob
import itertools
import os
import sys

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SIDEBAR = (168, 94)
MIN_DIFF = 12.0
# the measured evidence, printed beside every verdict
EVIDENCE = "invisible: 4.4 / 7.5 / 10.5, same: 9.9  |  distinguished: 12.5 / 14.2 / 46.8"


def sidebar_gray(path_or_bgr):
    img = path_or_bgr if isinstance(path_or_bgr, np.ndarray) else cv2.imread(path_or_bgr)
    if img is None:
        raise FileNotFoundError(path_or_bgr)
    if img.shape[:2] != (720, 1280):
        img = cv2.resize(img, (1280, 720), interpolation=cv2.INTER_AREA)
    small = cv2.resize(img, SIDEBAR, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


def feed_diff(a, b):
    """Mean absolute difference at feed size, 0-255 code values."""
    return float(np.mean(np.abs(sidebar_gray(a) - sidebar_gray(b))))


def check(paths, min_diff=MIN_DIFF, verbose=True):
    if len(paths) < 2:
        raise ValueError("need at least two variants")
    names = [os.path.basename(p) if isinstance(p, str) else f"img{i}" for i, p in enumerate(paths)]
    pairs = []
    for (i, a), (j, b) in itertools.combinations(enumerate(paths), 2):
        pairs.append((names[i], names[j], feed_diff(a, b)))
    worst = min(pairs, key=lambda t: t[2])
    ok = worst[2] >= min_diff
    if verbose:
        for n1, n2, d in pairs:
            print(f"  {d:6.2f}  {'ok  ' if d >= min_diff else 'SAME'}  {n1}  vs  {n2}")
        print(f"  threshold {min_diff:.1f} mean-abs @ {SIDEBAR[0]}x{SIDEBAR[1]}  ({EVIDENCE})")
        print(("VARIANTS_OK    " if ok else "VARIANTS_FAIL  ")
              + f"closest pair {worst[0]} vs {worst[1]} = {worst[2]:.2f}")
    return ok, pairs


def _first(*globs):
    for g in globs:
        hits = sorted(glob.glob(g))
        if hits:
            return hits[0]
    return None


def selftest():
    """The invisible level must FAIL and a pair he told apart must PASS.
    Real controls when the thumbwork tree is mounted, synthetic otherwise."""
    ok = True
    base = _first("D:/Boyd Clips/thumbwork/CARTHIEF/CARTHIEF_NEW.jpg",
                  "D:/Boyd Clips/thumbwork/*/*_NEW.jpg")
    a = _first("D:/Boyd Clips/thumbwork/MONKEY/MONKEY_A.jpg")
    b = _first("D:/Boyd Clips/thumbwork/MONKEY/MONKEY_B.jpg")
    if base:
        img = cv2.imread(base)
        # the -20% "level" he could not see: background x0.80 under the placed
        # subject alphas, exactly what was offered on 2026-08-29
        wd = os.path.dirname(base)
        subj = np.zeros(img.shape[:2], np.float32)
        for nm in ("_placed_alpha_judge.png", "_placed_alpha_defendant.png"):
            m = cv2.imread(os.path.join(wd, nm), cv2.IMREAD_GRAYSCALE)
            if m is not None:
                if m.shape != subj.shape:
                    m = cv2.resize(m, (subj.shape[1], subj.shape[0]), interpolation=cv2.INTER_AREA)
                subj = np.maximum(subj, m.astype(np.float32) / 255.0)
        f = img.astype(np.float32)
        lvl = f * 0.80 * (1 - subj[..., None]) + f * subj[..., None]
        d = feed_diff(img, np.clip(lvl, 0, 255).astype(np.uint8))
        got = d >= MIN_DIFF
        print(f"  {'ok  ' if not got else 'FAIL'} invisible level (bg x0.80 on {os.path.basename(base)}) = {d:.2f} -> {'SAME' if not got else 'passes?!'}")
        ok = ok and not got
        # identical file must be 0 and fail
        d0 = feed_diff(img, img)
        print(f"  {'ok  ' if d0 == 0 else 'FAIL'} identical file = {d0:.2f}")
        ok = ok and d0 == 0
    else:
        print("  skip  no thumbwork tree mounted for the invisible-level control")
    if a and b:
        d = feed_diff(a, b)
        got = d >= MIN_DIFF
        print(f"  {'ok  ' if got else 'FAIL'} MONKEY_A vs MONKEY_B (he told these apart) = {d:.2f}")
        ok = ok and got
    else:
        print("  skip  MONKEY_A/B not mounted")
    # synthetic, so the arithmetic is proven even with no thumbwork mounted:
    # a 3-code shift is 3.00 exactly, a title band over the bottom third is ~55
    flat = np.full((720, 1280, 3), 90, np.uint8)
    shifted = np.full((720, 1280, 3), 93, np.uint8)
    titled = flat.copy()
    titled[480:, :] = 255
    d1, d2 = feed_diff(flat, shifted), feed_diff(flat, titled)
    print(f"  {'ok  ' if d1 < MIN_DIFF else 'FAIL'} synthetic 3-code shift = {d1:.2f} (SAME)")
    print(f"  {'ok  ' if d2 >= MIN_DIFF else 'FAIL'} synthetic title band = {d2:.2f} (differs)")
    ok = ok and d1 < MIN_DIFF and d2 >= MIN_DIFF
    print("SELFTEST_PASS check_variants" if ok else "SELFTEST_FAIL check_variants")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        sys.exit(0 if selftest() else 1)
    if len(a) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(0 if check(a)[0] else 1)
