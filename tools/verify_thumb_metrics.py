# -*- coding: utf-8 -*-
"""Deterministic end-to-end controls for ``thumb_metrics.py``.

The former test depended on seven JPEGs in a deleted Claude scratch folder.
These generated controls are stable across machines and isolate the three
behaviours the gates must distinguish: texture, background mush, and an
over-bright subject. They exercise the public metric functions without a face
detector or external media dependency.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_metrics as tm

H, W = 720, 1280
THR = {"flat_g_p90": 0.30, "poster_fa": 0.020,
       "bg_mush": 0.35, "subject_max_L": 180}
FACES = [
    {"cx": 0.30, "cy": 0.48, "bw": 260, "bh": 320},
    {"cx": 0.70, "cy": 0.48, "bw": 260, "bh": 320},
]


def textured(subject_level=155):
    """A deterministic detailed background with two midtone subjects."""
    y, x = np.mgrid[0:H, 0:W]
    noise = ((x * 17 + y * 29 + (x * y) % 31) % 25) - 12
    image = np.stack([
        72 + x * 45 / W + noise,
        82 + y * 35 / H - noise,
        96 + (x + y) * 18 / (W + H) + noise // 2,
    ], axis=2)
    image = np.clip(image, 0, 255).astype(np.uint8)
    for i, face in enumerate(FACES):
        cx, cy = int(face["cx"] * W), int(face["cy"] * H)
        bw, bh = int(face["bw"] * 0.4), int(face["bh"] * 0.4)
        yy, xx = np.mgrid[0:2 * bh, 0:2 * bw]
        detail = ((xx * 13 + yy * 7 + i * 3) % 11) - 5
        patch = np.stack([
            np.full_like(detail, subject_level + 18) + detail,
            np.full_like(detail, subject_level) - detail,
            np.full_like(detail, subject_level - 12) + detail // 2,
        ], axis=2)
        image[cy-bh:cy+bh, cx-bw:cx+bw] = np.clip(
            patch, 0, 255).astype(np.uint8)
    return image


def mush_control():
    """Smooth plate plus detailed subjects: background gate must catch it."""
    image = np.full((H, W, 3), (75, 90, 105), np.uint8)
    for i, face in enumerate(FACES):
        cx, cy = int(face["cx"] * W), int(face["cy"] * H)
        bw, bh = 105, 125
        yy, xx = np.mgrid[0:2 * bh, 0:2 * bw]
        detail = ((xx * 11 + yy * 5 + i) % 15) - 7
        image[cy-bh:cy+bh, cx-bw:cx+bw] = np.stack([
            170 + detail, 145 - detail, 125 + detail // 2,
        ], axis=2).astype(np.uint8)
    return image


def failed_gates(metrics):
    failed = []
    if (metrics["flat_g_p90"] > THR["flat_g_p90"]
            or metrics["poster_fa"] > THR["poster_fa"]):
        failed.append("A")
    if metrics["bg_mush"] > THR["bg_mush"]:
        failed.append("B")
    if metrics["subject_max_L"] > THR["subject_max_L"]:
        failed.append("C")
    return failed


def main():
    cases = [
        ("textured", "GOOD", textured()),
        ("flat", "BAD", np.full((H, W, 3), (90, 110, 130), np.uint8)),
        ("mush", "BAD", mush_control()),
        ("bright", "BAD", textured(subject_level=230)),
    ]
    expected = {
        "textured": (0.000625, 0.0, 0.0, 166.0, 100),
        "flat": (1.0, 1.0, 1.0, 116.0, 100),
        "mush": (1.0, 0.861111, 1.0, 158.0, 100),
        "bright": (0.000625, 0.0, 0.0, 236.0, 100),
    }
    ok = True
    print("THUMB METRIC CONTROLS")
    for name, truth, image in cases:
        metrics = tm.all_metrics(image, faces=FACES)
        actual = (metrics["flat_g_p90"], metrics["poster_fa"],
                  metrics["bg_mush"], metrics["subject_max_L"],
                  metrics["bg_tiles"])
        reproducible = all(abs(float(a) - float(b)) < 0.002
                           for a, b in zip(actual, expected[name]))
        failed = failed_gates(metrics)
        prediction = "BAD" if failed else "GOOD"
        passed = reproducible and prediction == truth
        ok &= passed
        print(f"  {name:8} truth={truth:4} pred={prediction:4} "
              f"failed={','.join(failed) or '-':5} "
              f"fingerprint={'OK' if reproducible else 'DRIFT'}")
    print("REPRO_OK" if ok else "SELFTEST_FAIL thumb_metrics")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
