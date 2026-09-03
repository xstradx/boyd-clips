# -*- coding: utf-8 -*-
"""What "bright white effect" is, measured against the five he ACCEPTED.

RETRACTION THIS FILE EXISTS TO REPAIR (2026-09-03): the first oracle compared
each face in the finished frame to the same face in its crop by resizing one
detector box onto the other and differencing per pixel. It reported 12.2% /
35.8% of the face "lifted more than +8 L*". That number was misalignment, not
light: measured alignment-free, every luminance percentile of both faces goes
DOWN from crop to composite (judge p50 49.4 -> 45.1, p90 67.5 -> 63.9, p99 80.8
-> 78.4). Two boxes from two detections are not the same pixel selection.

So the white patch is not a lift. It is a LOCAL bright area on the face, and
the honest way to size it is against the corpus: how big is the biggest bright
blob on a face in a thumbnail he accepted, versus one he rejected.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identity as I  # noqa: E402

TW = "D:/Boyd Clips/thumbwork"
ACCEPTED = [("SANCHEZ", None), ("CARTHIEF", None), ("MONKEY", None),
            ("THOMPSON", None), ("TORRES", None)]


def face_metrics(bgr, box):
    x, y, w, h = [int(v) for v in box[:4]]
    r = bgr[max(y, 0):y + h, max(x, 0):x + w]
    if r.size == 0:
        return None
    lab = cv2.cvtColor(r, cv2.COLOR_BGR2LAB)
    L = lab[..., 0].astype(np.float32) * 100.0 / 255.0
    ycc = cv2.cvtColor(r, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(ycc, (0, 133, 77), (255, 173, 127)) > 0
    if skin.sum() < 300:
        return None
    med = float(np.median(L[skin]))
    # a "white patch" is skin well above that face's OWN midtone - this is
    # scale- and skin-tone independent, which matters across two very
    # different faces in the same frame
    hot = (L > med + 22.0) & skin
    hot = cv2.morphologyEx(hot.astype(np.uint8), cv2.MORPH_OPEN,
                           np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(hot, 8)
    biggest = 0 if n <= 1 else int(stats[1:, cv2.CC_STAT_AREA].max())
    return dict(skin_px=int(skin.sum()),
                med=med,
                hot_frac=100.0 * float(hot.sum()) / float(skin.sum()),
                blob_frac=100.0 * biggest / float(skin.sum()))


def report(path, label):
    bgr = cv2.imread(path)
    if bgr is None:
        return []
    rows = sorted(I.faces_in(bgr, score=0.5), key=lambda r: -r[2] * r[3])[:2]
    out = []
    for r in rows:
        m = face_metrics(bgr, r)
        if not m:
            continue
        out.append(m)
        print(f"{label:26s} skin_med {m['med']:5.1f}  hot {m['hot_frac']:5.2f}%  "
              f"biggest blob {m['blob_frac']:5.2f}% of the face")
    return out


if __name__ == "__main__":
    acc = []
    print("=== the five he ACCEPTED ===")
    for c, _ in ACCEPTED:
        d = os.path.join(TW, c)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".jpg", ".png")) and "thumb" in f.lower() \
                    and "photo" not in f.lower():
                acc += report(os.path.join(d, f), f"ok:{c}")
                break
    if acc:
        hb = [a["blob_frac"] for a in acc]
        hf = [a["hot_frac"] for a in acc]
        print(f"\nACCEPTED BAND  biggest blob {min(hb):.2f}-{max(hb):.2f}% "
              f"(median {np.median(hb):.2f})   hot {min(hf):.2f}-{max(hf):.2f}%")
    print("\n=== the PACE builds he rejected / the new one ===")
    for p, lab in [("PACE_v/PACE_v_noarrow.jpg", "rejected PACE_v"),
                   ("PACE_colour/PACE_SIMPLE.jpg", "rejected SIMPLE"),
                   ("PACE_colour/PACE_R57.jpg", "new R57")]:
        report(os.path.join(TW, p), lab)
    print("\n=== the crops he said he LIKED (left) ===")
    for p, lab in [("PACE_colour/defendant_colour.png", "crop defendant"),
                   ("PACE_colour/judge_colour.png", "crop judge")]:
        report(os.path.join(TW, p), lab)
