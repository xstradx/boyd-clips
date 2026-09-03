# -*- coding: utf-8 -*-
"""Measure the colour target from Nathan's own reference (2026-09-03).

He sent a 3-pair before/after sheet from a thumbnail designer and said "when I
said fix the colors this is what i meant". So the target is not invented here -
it is READ OFF the right-hand column of that sheet: skin L*a*b*, face contrast
and face chroma. Left column is measured too, so the DIRECTION of the correction
is measured rather than assumed.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identity as I  # noqa: E402

REF = (r"C:\Users\natha\.claude\uploads"
       r"\0da3f094-7d8f-4589-b594-27df76db4609\4619badd-image.jpg")


def skin_mask(bgr):
    """YCrCb skin range - the standard one, not a hand-tuned constant."""
    y = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    return cv2.inRange(y, (0, 133, 77), (255, 173, 127)) > 0


def face_stats(bgr, box):
    x, y, w, h = [int(v) for v in box[:4]]
    x, y = max(x, 0), max(y, 0)
    face = bgr[y:y + h, x:x + w]
    if face.size == 0:
        return None
    m = skin_mask(face)
    if m.sum() < 200:
        m = np.ones(face.shape[:2], bool)
    lab = cv2.cvtColor(face, cv2.COLOR_BGR2LAB).astype(float)
    L, a, b = lab[..., 0][m], lab[..., 1][m], lab[..., 2][m]
    Lall = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)[..., 0].astype(float)
    return dict(
        n=int(m.sum()),
        skinL=float(np.median(L)) * 100 / 255,
        skin_a=float(np.median(a)) - 128,
        skin_b=float(np.median(b)) - 128,
        chroma=float(np.median(np.hypot(a - 128, b - 128))),
        faceL_p5=float(np.percentile(Lall, 5)) * 100 / 255,
        faceL_p95=float(np.percentile(Lall, 95)) * 100 / 255,
        blown=float(100 * (face.max(axis=2) > 250).mean()),
    )


def report(path, label, side=None):
    bgr = cv2.imread(path)
    if bgr is None:
        print(f"{label}: UNREADABLE {path}")
        return
    H, W = bgr.shape[:2]
    rows = I.faces_in(bgr, score=0.5)
    rows = sorted(rows, key=lambda r: (r[1], r[0]))
    for r in rows:
        cx = r[0] + r[2] / 2
        if side == "L" and cx > W / 2:
            continue
        if side == "R" and cx < W / 2:
            continue
        s = face_stats(bgr, r)
        if not s or s["n"] < 200:
            continue
        print(f"{label:22s} box=({int(r[0])},{int(r[1])},{int(r[2])},{int(r[3])}) "
              f"skinL={s['skinL']:5.1f} a={s['skin_a']:+5.1f} b={s['skin_b']:+5.1f} "
              f"chroma={s['chroma']:5.1f} faceL p5={s['faceL_p5']:5.1f} "
              f"p95={s['faceL_p95']:5.1f} blown={s['blown']:5.2f}%")


if __name__ == "__main__":
    print("=== Nathan's reference sheet: BEFORE (left column) ===")
    report(REF, "ref BEFORE", side="L")
    print("=== Nathan's reference sheet: AFTER (right column) ===")
    report(REF, "ref AFTER", side="R")
    print("=== our crops ===")
    for p, lab in [("D:/Boyd Clips/thumbwork/PACE_v/defendant_hypir.png", "PACE defendant"),
                   ("D:/Boyd Clips/thumbwork/PACE_v/judge_hypir.png", "PACE judge")]:
        report(p, lab)
    print("=== his five ACCEPTED thumbnails ===")
    for c in ["SANCHEZ", "CARTHIEF", "MONKEY", "THOMPSON", "TORRES"]:
        d = f"D:/Boyd Clips/thumbwork/{c}"
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".jpg", ".png")) and "thumb" in f.lower() \
                    and "photo" not in f.lower():
                report(os.path.join(d, f), f"ok:{c}")
                break
