# -*- coding: utf-8 -*-
"""Measure a cut-out the way Nathan judges one: does the hair survive, and is
there a halo.

Nathan, 2026-09-03: *"when you cut out the defendant and the judge ... whatever
your process is like it's not right"*, and the fix he named - cut out, THEN
upscale, THEN colour.

MEASURED on the current order (HYPIR -> colour -> matte), PACE judge: mean alpha
in the hair band 61 of 255, only 23% of hair pixels fully opaque. Three quarters
of her hair is being made transparent, because the matte is traced around what
the restorer invented at the hair edge rather than around the real hair.

The two numbers here are the ones that decide the ORDER, so they are proven
against a known-bad control first (`--selftest`): a hard 0/255 cut has no soft
hair band at all and must be rejected; the shipped matte must be accepted. A
metric that has never been seen to fail is not evidence.

    python tools/cutfirst_probe.py --selftest
    python tools/cutfirst_probe.py --alpha <surgical.png>
    python tools/cutfirst_probe.py --compare <A.png> <B.png>
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# A "soft" alpha pixel is one the matting model actually resolved a fraction
# for. 8..247 rather than 0..255 so the gentle ALPHA_FLOOR/CEIL contrast in
# thumb_pipeline does not read as hard by itself.
SOFT_LO, SOFT_HI = 8, 247


def _alpha_of(png):
    im = cv2.imread(png, cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.ndim == 3 and im.shape[2] == 4:
        return im[..., 3]
    if im.ndim == 2:
        return im
    return None


def hair_band(a, top_frac=0.42):
    """The band across the TOP of the subject, where hair lives.

    Taken from the alpha's own bounding box, not from a face box: the point is
    to measure the hair, and the face detector is not needed for that.
    """
    ys, xs = np.where(a > SOFT_LO)
    if len(ys) < 200:
        return None
    y0, y1 = ys.min(), ys.max()
    h = y1 - y0
    band = a[y0:y0 + max(int(h * top_frac), 4), :]
    return band


def measure(png):
    a = _alpha_of(png)
    if a is None:
        return None
    band = hair_band(a)
    if band is None:
        return None
    inside = band[band > SOFT_LO]
    if inside.size < 200:
        return None
    soft = np.logical_and(a > SOFT_LO, a < SOFT_HI)
    return dict(
        hair_mean=float(inside.mean()),
        hair_opaque_pct=100.0 * float((inside >= SOFT_HI).mean()),
        soft_edge_px=int(soft.sum()),
        soft_edge_pct=100.0 * float(soft.sum()) / float(max((a > SOFT_LO).sum(), 1)),
    )


def halo(rgb_png, alpha_png, ring=6):
    """Luminance of the ring just OUTSIDE the silhouette minus the ring just
    inside it. A bright fringe hugging the cut-out is the 'halo' complaint."""
    a = _alpha_of(alpha_png)
    im = cv2.imread(rgb_png)
    if a is None or im is None:
        return None
    if im.shape[:2] != a.shape[:2]:
        im = cv2.resize(im, (a.shape[1], a.shape[0]))
    solid = (a > 200).astype(np.uint8)
    k = np.ones((ring * 2 + 1, ring * 2 + 1), np.uint8)
    outer = cv2.dilate(solid, k) - solid
    inner = solid - cv2.erode(solid, k)
    L = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) * 100 / 255
    if outer.sum() < 200 or inner.sum() < 200:
        return None
    return float(L[outer > 0].mean() - L[inner > 0].mean())


def _report(png, label):
    m = measure(png)
    if not m:
        print(f"{label:34s} UNMEASURABLE")
        return None
    print(f"{label:34s} hair mean alpha {m['hair_mean']:6.1f}/255   "
          f"fully opaque {m['hair_opaque_pct']:5.1f}%   "
          f"soft edge {m['soft_edge_pct']:5.2f}% of the subject")
    return m


def selftest():
    """A hard 0/255 cut must be REJECTED by these metrics; the shipped matte
    must be accepted. Built as a synthetic control so it cannot drift."""
    import tempfile
    ok = True
    # a synthetic subject with a genuinely soft hair band
    h, w = 400, 300
    a = np.zeros((h, w), np.uint8)
    cv2.ellipse(a, (w // 2, h // 2), (90, 150), 0, 0, 360, 255, -1)
    soft = cv2.GaussianBlur(a, (0, 0), 9)
    good = np.maximum(a, (soft * 0.75).astype(np.uint8))
    hard = (a > 127).astype(np.uint8) * 255          # the known-bad control
    with tempfile.TemporaryDirectory() as d:
        pg = os.path.join(d, "good.png")
        ph = os.path.join(d, "hard.png")
        rgb = np.full((h, w, 3), 128, np.uint8)
        cv2.imwrite(pg, np.dstack([rgb, good]))
        cv2.imwrite(ph, np.dstack([rgb, hard]))
        mg, mh = measure(pg), measure(ph)
        if not mg or not mh:
            print("CUTFIRST_ORACLE_FAIL a control was unmeasurable")
            return False
        print(f"  control GOOD (soft hair)  soft edge {mg['soft_edge_pct']:5.2f}%  "
              f"hair mean {mg['hair_mean']:.1f}")
        print(f"  control HARD (0/255 cut)  soft edge {mh['soft_edge_pct']:5.2f}%  "
              f"hair mean {mh['hair_mean']:.1f}")
        # the decisive separation: a hard cut has essentially no soft edge
        if not (mh["soft_edge_pct"] < 1.0 < mg["soft_edge_pct"]):
            print("CUTFIRST_ORACLE_FAIL soft-edge % does not separate the controls")
            ok = False
        # HALO CONTROL. Measured against the HARD alpha, whose boundary is
        # exactly the drawn ellipse - against the soft one the >200 contour
        # sits outside the drawn axes, so a fringe painted at those axes lands
        # in the INNER band and the metric reads negative. That is how this
        # control failed twice before it measured anything real.
        ph2 = os.path.join(d, "halo.png")
        base = np.full((h, w, 3), 60, np.uint8)
        cv2.ellipse(base, (w // 2, h // 2), (93, 153), 0, 0, 360, (230, 230, 230), 6)
        cv2.imwrite(ph2, base)
        flat = os.path.join(d, "flat.png")
        cv2.imwrite(flat, np.full((h, w, 3), 60, np.uint8))
        hv, hf = halo(ph2, ph), halo(flat, ph)
        print(f"  control HALO present      halo_dL {hv:+.1f}")
        print(f"  control HALO absent       halo_dL {hf:+.1f}")
        if hv is None or hf is None or not (hv > hf + 5):
            print("CUTFIRST_ORACLE_FAIL halo_dL does not separate the controls")
            ok = False
    print("CUTFIRST_ORACLE_OK" if ok else "CUTFIRST_ORACLE_FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--compare" in sys.argv and len(args) >= 2:
        _report(args[0], "A  " + os.path.basename(args[0]))
        _report(args[1], "B  " + os.path.basename(args[1]))
        sys.exit(0)
    if args:
        _report(args[0], os.path.basename(args[0]))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
