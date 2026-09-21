"""R51 - a thumbnail's GRADE must sit inside the envelope his accepted builds
define, measured with the project's own floor metric.

2026-09-02, on the five thumbnails built in the batch: *"I don't like the way
the judge and defendant look. Looks very cheap and colored/brightness wrong
and don't have that professional hd look"*. A/C/D passed and shipped them
anyway - nothing measured the grade of the subjects or the plate they sit on.

Measured with tools/floor_measure.py (the same code that derived
config/quality_floor.json) on the five he accepted vs the five he rejected
the same day (tools/fixtures/rejected_2026_09_02):

                    accepted envelope      rejected 2026-09-02
  grain_hf          0.87 - 1.72            4.04 - 4.65 (4 of 5)  oversharpened
  background_L      107.2 - 149.1          91.1 - 102.8 (5 of 5) plate too dark
  contrast_sd       78.2 - 82.8            72.4 - 77.9 (5 of 5)  flat
  separation_dL    -57.8 - 18.9            17.0 - 18.3           all at the edge

The gate is the envelope itself with a 5% slack on each end, so it moves when
the floor moves and never needs a hand-tuned number. Accepted builds pass by
construction - the CONTROL that proves the gate can fail is the rejected five.

  I  every envelope metric inside [min - 5% span, max + 5% span]
  H  two builds must not share the same background plate
     (thumbwork/<case>/bg_raw.png SHA differs from every peer)

Usage:
  python tools/check_thumb_grade.py CASE OUT.jpg [--peers A.jpg B.jpg ...]
  python tools/check_thumb_grade.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import hashlib

import cv2  # noqa: F401
import numpy as np  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import floor_measure as fm  # noqa: E402

FIX = os.path.join(ROOT, "tools", "fixtures", "rejected_2026_09_02")
FLOOR = os.path.join(ROOT, "config", "quality_floor.json")
KEYS = ("grain_hf", "background_L", "contrast_sd", "subject_L", "separation_dL")
SLACK = 0.05
THUMBWORK = "D:/Boyd Clips/thumbwork"


def envelope() -> dict:
    return json.load(open(FLOOR, encoding="utf-8"))["envelope"]


def bg_sha(case: str) -> str | None:
    """SHA of the plate the build actually used. The first version of H
    compared a centre band of the finished JPEG and did NOT fire on five
    builds that share one plate - the arrow and the subjects move enough to
    swamp it. The source file is decisive: measured 2026-09-02, all five
    rejected builds carry bg_raw.png 9e01114e2875.
    """
    p = os.path.join(THUMBWORK, case, "bg_raw.png")
    if not os.path.exists(p):
        return None
    return hashlib.sha1(open(p, "rb").read()).hexdigest()


def check(case: str, path: str, peers: list[str] | None = None, verbose: bool = True) -> list[str]:
    env = envelope()
    m, prov = fm.measure_case(case, path)
    probs: list[str] = []
    shown = []
    for k in KEYS:
        v = m.get(k)
        e = env.get(k)
        if v is None or e is None:
            probs.append(f"I {k} not measured (mask_source={prov.get('mask_source')})")
            continue
        span = max(e["max"] - e["min"], 1e-6)
        lo, hi = e["min"] - SLACK * span, e["max"] + SLACK * span
        shown.append(f"{k}={v:.2f}")
        if not (lo <= v <= hi):
            probs.append(f"I {k} {v:.2f} outside the accepted envelope "
                         f"[{e['min']:.2f}, {e['max']:.2f}] (+-5% -> [{lo:.2f}, {hi:.2f}])")
    mine = bg_sha(case)
    for peer in peers or []:
        if peer == case:
            continue
        theirs = bg_sha(peer)
        if mine and theirs and mine == theirs:
            probs.append(f"H background plate is byte-identical to {peer} "
                         f"(bg_raw.png {mine[:12]}) - five videos would post as one wall of the same image")
    if verbose:
        print(f"  {case:14} {'  '.join(shown)}  [{prov.get('mask_source')}]")
        for p in probs:
            print("    FAIL ", p)
        if not probs:
            print("    PASS  I" + ("/H" if peers else ""))
    return probs


def selftest() -> int:
    ok = True
    floor = json.load(open(FLOOR, encoding="utf-8"))
    print("ACCEPTED - they define the envelope, so passing is expected, not proof:")
    if not floor.get("files"):
        ok = False
        print("    !! the known-good controls are missing - the gate is unproven")
    for k, rel in floor["files"].items():
        p = rel if os.path.isabs(rel) else os.path.join("D:/Boyd Clips", rel)
        if not os.path.exists(p):
            ok = False
            print(f"    !! accepted build {k} is missing: {p}")
            continue
        if check(k, p):
            ok = False
            print(f"    !! accepted build {k} falls outside its own envelope")
    rejected = []
    if os.path.isdir(FIX):
        rejected = [(f[:-len("_thumb.jpg")], os.path.join(FIX, f))
                    for f in sorted(os.listdir(FIX)) if f.endswith("_thumb.jpg")]
    print(f"CONTROL - the {len(rejected)} builds he rejected 2026-09-02; every one MUST fail:")
    peers = [k for k, _ in rejected]
    for k, p in rejected:
        if not check(k, p, peers=peers):
            ok = False
            print(f"    !! rejected build {k} passed - the gate cannot see what he rejected")
    if len(rejected) < 3:
        ok = False
        print("    !! the known-bad control is missing - the gate is unproven")
    print("THUMB_GRADE_SELFTEST_OK" if ok else "THUMB_GRADE_SELFTEST_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case", nargs="?")
    ap.add_argument("path", nargs="?")
    ap.add_argument("--peers", nargs="*", default=[])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    probs = check(a.case, a.path, peers=a.peers)
    print(f"THUMB_GRADE_FAIL {len(probs)}" if probs else "THUMB_GRADE_OK")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
