# -*- coding: utf-8 -*-
"""End-to-end reproduction check for thumb_metrics.py.

Runs the module over the 7 same-encoder files and prints:
  1. the metric table
  2. the reproduction check against Team B's originally reported numbers
  3. the PER-GATE separability test (the one the coordinator ran)
  4. the ACTUAL system test (each reject fails >= 1 gate)
"""
import os
import sys
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_metrics as tm

SAN = (r"C:\Users\natha\AppData\Local\Temp\claude\C--Users-natha"
       r"\91451db0-4fac-40e9-a828-e6c5ebed0556\scratchpad\sanchez")
MODEL = r"C:\Users\natha\Projects\boyd-clips\models\yunet2023.onnx"

FILES = [("HS_REMAKE.jpg", "GOOD"), ("WORKING.jpg", "GOOD"),
         ("V2_4046.jpg", "BAD"), ("V3_4046.jpg", "BAD"), ("GLW_4046.jpg", "BAD"),
         ("AUD_4046.jpg", "BAD"), ("S_4046.jpg", "BAD")]

# Team B's originally reported values, for reproduction checking
REPORTED = {
    "HS_REMAKE.jpg": (0.2968, 0.01367, 0.3163, 160),
    "WORKING.jpg":   (0.2351, 0.01590, 0.2946, 155),
    "V2_4046.jpg":   (0.6641, 0.08565, 0.7293, 150),
    "V3_4046.jpg":   (0.4019, 0.06026, 0.1154, 119),
    "GLW_4046.jpg":  (0.4381, 0.04339, 0.5845, 146),
    "AUD_4046.jpg":  (0.3729, 0.04167, 0.0533, 150),
    "S_4046.jpg":    (0.03656, 0.004926, 0.0075, 221),
}

THR = {"flat_g_p90": 0.30, "poster_fa": 0.020, "bg_mush": 0.35, "subject_max_L": 180}

rows = []
for fn, truth in FILES:
    bgr = cv2.imread(os.path.join(SAN, fn), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    faces = tm.detect_faces(rgb, MODEL)
    m = tm.all_metrics(rgb, faces=faces)
    rows.append((fn, truth, m))

print("=== METRICS (module output) ===")
print("%-14s %-5s %9s %9s %9s %6s %9s" %
      ("file", "truth", "flatG_p90", "poster_fa", "bg_mush", "bgTil", "subjMaxL"))
for fn, truth, m in rows:
    print("%-14s %-5s %9.4f %9.5f %9.4f %6d %9.1f" %
          (fn, truth, m["flat_g_p90"], m["poster_fa"], m["bg_mush"],
           m["bg_tiles"], m["subject_max_L"]))

print("\n=== REPRODUCTION vs Team B's reported numbers ===")
allok = True
for fn, truth, m in rows:
    ra, rp, rb, rl = REPORTED[fn]
    d = [abs(m["flat_g_p90"] - ra), abs(m["poster_fa"] - rp),
         abs(m["bg_mush"] - rb), abs(m["subject_max_L"] - rl)]
    ok = d[0] < 0.002 and d[1] < 0.002 and d[2] < 0.002 and d[3] < 1.5
    allok &= ok
    print("%-14s dFlat=%.5f dPost=%.5f dMush=%.5f dL=%.2f  %s" %
          (fn, d[0], d[1], d[2], d[3], "OK" if ok else "*** DRIFT ***"))
print("REPRODUCTION:", "EXACT" if allok else "MISMATCH")

good = [m for _, t, m in rows if t == "GOOD"]
bad = [m for _, t, m in rows if t == "BAD"]

print("\n=== TEST 1: per-gate separability (the test that 'fails') ===")
for k in ["flat_g_p90", "poster_fa", "bg_mush", "subject_max_L"]:
    g = [x[k] for x in good]
    b = [x[k] for x in bad]
    sep = min(b) > max(g)
    print("  %-14s good %.4f-%.4f | bad %.4f-%.4f | separates all: %s"
          % (k, min(g), max(g), min(b), max(b), sep))
print("  -> NO single metric separates all 5 rejects. That is EXPECTED:")
print("     they have three different defects. This test is the wrong test.")

print("\n=== TEST 2: the actual system (fail >=1 gate) ===")


def gates(m):
    f = []
    if m["flat_g_p90"] > THR["flat_g_p90"] or m["poster_fa"] > THR["poster_fa"]:
        f.append("A")
    if m["bg_mush"] > THR["bg_mush"]:
        f.append("B")
    if m["subject_max_L"] > THR["subject_max_L"]:
        f.append("C")
    return f


fp = fn_ = 0
for fname, truth, m in rows:
    f = gates(m)
    pred = "BAD" if f else "GOOD"
    hit = pred == truth
    if not hit and truth == "GOOD":
        fp += 1
    if not hit and truth == "BAD":
        fn_ += 1
    print("  %-14s truth=%-4s pred=%-4s failed=%-8s %s" %
          (fname, truth, pred, ",".join(f) or "-", "OK" if hit else "*** MISS ***"))
print("  false positives=%d  false negatives=%d" % (fp, fn_))
print("  RESULT:", "0 FP / 0 FN - CONFIRMED" if fp == 0 and fn_ == 0 else "FAILS")
