#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_stamp.py - check computed sync offsets against the BURNED-IN clock.

WHY THIS FILE EXISTS
--------------------
`bwc_sync.py` solved a real Denver incident, reported five cameras VERIFIED
with a 3-clique loop-closure residual of 0.010 s, and every offset was
BACKWARDS. Magnitudes exact, direction reversed.

Loop closure could not catch it, and that is the lesson worth keeping: it tests
whether the offsets are mutually CONSISTENT, and a set of offsets that is
uniformly sign-flipped is perfectly consistent with itself. The synthetic
selftest could not catch it either, because the fixture created a "delay" by
prepending silence - which actually models a camera that started EARLIER - so
the code and its test shared one backwards convention and agreed with each
other.

Two oracles agreeing means nothing when they share an assumption. Only an
INDEPENDENT measurement breaks the tie, and Axon burns one into the picture:
`2025-08-23 22:06:30 -0600`. Reading it with OCR gives a wall clock per camera
that owes nothing to the audio, the metadata, or the correlation maths.

Note this is the one timestamp worth trusting for ORDERING. `creation_time` on
these same files reads 2025-10-08 to 2025-10-16 - the redaction/export dates,
seven weeks after the 2025-08-23 incident and spread over eight days.

    python tools/verify_stamp.py --selftest
    python tools/verify_stamp.py --dir "D:/Boyd Clips/bodycam/<incident>"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TOL = 3.0          # seconds; the burned-in clock has 1 s resolution
SAMPLE_AT = 5.0    # read the stamp this far into each clip, past any fade-in

_TS = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T]+(\d{2}):(\d{2}):(\d{2})")


def read_stamp(path, at=SAMPLE_AT, tess=TESS, tmp=None):
    """-> (epoch_seconds_within_day, raw_text) or (None, raw_text).

    The stamp sits in the top-right. It is cropped, upscaled 3x, greyscaled and
    inverted before OCR: Axon draws white text over bright night-time highlights
    and Tesseract reads dark-on-light far better than the reverse.
    """
    tmp = tmp or os.path.join(os.path.dirname(path), "_stamp_ocr.png")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "%.3f" % at, "-i", path, "-frames:v", "1",
         "-vf", "crop=iw*0.42:ih*0.075:iw*0.55:0,scale=iw*3:ih*3,format=gray,negate",
         "-y", tmp], capture_output=True)
    if not os.path.exists(tmp):
        return None, ""
    r = subprocess.run([tess, tmp, "stdout", "--psm", "7"],
                       capture_output=True, text=True)
    txt = (r.stdout or "").strip()
    m = _TS.search(txt)
    if not m:
        return None, txt
    h, mi, s = int(m.group(4)), int(m.group(5)), int(m.group(6))
    return h * 3600 + mi * 60 + s - at, txt


def verify(d, tol=TOL):
    off_path = os.path.join(d, "offsets.json")
    if not os.path.exists(off_path):
        print("no offsets.json in %s - run bwc_sync.py --json first" % d)
        return 2
    with open(off_path, encoding="utf-8") as fh:
        data = json.load(fh)
    groups = [g for g in data.get("groups", []) if len(g.get("offsets", {})) >= 2]
    if not groups:
        print("no multi-camera group to verify")
        return 2
    rc = 0
    for gi, g in enumerate(groups, 1):
        rows = []
        for fname, computed in g["offsets"].items():
            secs, raw = read_stamp(os.path.join(d, fname))
            rows.append((fname, computed, secs, raw))
        good = [r for r in rows if r[2] is not None]
        print("GROUP %d - computed offset vs burned-in clock" % gi)
        if len(good) < 2:
            print("   OCR read %d of %d stamps - cannot verify" % (len(good), len(rows)))
            for f, c, s, raw in rows:
                print("      %-44s ocr='%s'" % (f[:44], raw[:40]))
            rc = 3
            continue
        base_true = min(r[2] for r in good)
        base_calc = min(r[1] for r in good)
        worst = 0.0
        print("   %-40s %10s %10s %8s" % ("camera", "TRUE", "COMPUTED", "err"))
        for f, c, s, raw in sorted(good, key=lambda r: r[2]):
            true = s - base_true
            calc = c - base_calc
            err = abs(true - calc)
            worst = max(worst, err)
            print("   %-40s %10.1f %10.2f %8.2f%s"
                  % (f[:40], true, calc, err, "" if err <= tol else "  ** OFF **"))
        for f, c, s, raw in rows:
            if s is None:
                print("   %-40s OCR FAILED  '%s'" % (f[:40], raw[:34]))
        print("   worst error %.2fs (tolerance %.1fs)" % (worst, tol))
        if worst > tol:
            # The specific failure this file was written for: a uniform sign
            # flip is self-consistent and passes loop closure, so name it.
            flip = max(abs((s - base_true) - ((max(r[1] for r in good) - c) -
                                              (max(r[1] for r in good) - max(r[1] for r in good))))
                       for f, c, s, raw in good)
            print("   STAMP_MISMATCH%s" % (" - looks like a SIGN INVERSION"
                                           if flip <= tol else ""))
            rc = 3
        else:
            print("   STAMP_OK")
        print()
    return rc


def selftest():
    fails = []

    def t(cond, what):
        if not cond:
            fails.append(what)
        print("  %-4s %s" % ("ok" if cond else "FAIL", what))

    print("timestamp parsing")
    m = _TS.search("2025-08-23 22:06:30 -0600 (A")
    t(bool(m), "parses a clean Axon stamp")
    t(m and m.group(4) == "22" and m.group(6) == "30", "hours and seconds correct")
    t(bool(_TS.search("2025-08-23 22:04:15 -c60e (i")),
      "parses a stamp whose TIMEZONE is garbled by OCR (real case)")
    t(_TS.search("AXON BODY 4 D01AC570M") is None,
      "KNOWN-BAD CONTROL: the camera serial is not read as a timestamp")
    t(_TS.search("") is None, "empty OCR output yields no false stamp")

    print("tesseract is present")
    t(os.path.exists(TESS), "tesseract at %s" % TESS)

    print("the sign-inversion case this file was written to catch")
    # Real measured numbers from the Denver incident, before the fix.
    true = {"Stop_9": 0.0, "Stop_6": 84.0, "Stop_4": 490.0,
            "Stop_11": 584.0, "Stop_12": 719.0}
    bad = {"Stop_12": 0.0, "Stop_11": 134.66, "Stop_4": 228.40,
           "Stop_6": 635.61, "Stop_9": 719.53}
    worst = max(abs(true[k] - bad[k]) for k in true)
    t(worst > TOL, "the inverted offsets are rejected (worst %.1fs > %.1f)" % (worst, TOL))
    fixed = {k: max(bad.values()) - v for k, v in bad.items()}
    b = min(fixed.values())
    worst2 = max(abs(true[k] - (fixed[k] - b)) for k in true)
    t(worst2 <= TOL,
      "POSITIVE CONTROL: the corrected offsets pass (worst %.2fs)" % worst2)

    print()
    if fails:
        print("SELFTEST FAILED: %d" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("VERIFY_STAMP_SELFTEST_OK")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir")
    ap.add_argument("--tol", type=float, default=TOL)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.dir:
        return verify(a.dir, a.tol)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
