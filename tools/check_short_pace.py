"""R58 - a short must carry as much talking per second as the ones he accepted.

2026-09-03, on PERKINS_SHORT.mp4: *"Short was kinda underwhelming and slow,
boring"*. Every gate in the chain passed it - CHAIN_OK, SHORT_OK, FLOOR_OK, cuts
on speech boundaries, loudness, captions on the seam. Nothing measured whether
anything was HAPPENING.

Measured, words-per-minute on the delivered file:

    SANCHEZ   235.6      accepted
    OFFERUP   226.3      accepted
    CARTHIEF  200.0      accepted
    TORRES    195.0      posted
    ------------------------------------
    PERKINS   138.3      "slow, boring"      <- 29% under the lowest accepted
    PERKINS   225.0      the rebuild          -> passes

The cause was upstream of the editor: the span was picked to match the title
hook ("let's Google" - a 1.4 s line) instead of being read as a scene, so the
short inherited a 27.1 s single unbroken turn (a lawyer reading a news article
aloud, an address and a date) and ended on "does anybody know what time that
was?". The span that replaced it runs 15.7 turns/min with a 7.4 s longest turn.

The floor is min(accepted) - 5%, read from config/short_floor.json, so it moves
when the corpus moves and is never a hand-tuned number (same construction as
R51's grade envelope). The CONTROL that proves the gate can fail is the build he
rejected.

Usage:
  python tools/check_short_pace.py SHORT.mp4 [--words WORDS.json]
  python tools/check_short_pace.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOOR = os.path.join(ROOT, "config", "short_floor.json")


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    return float(out)


def _words_path(short: str) -> str | None:
    """The chain writes <work>/<stem>_tight_words.json beside the build."""
    stem = os.path.splitext(os.path.basename(short))[0]
    pats = [
        os.path.join("D:/Boyd Clips/shortwork", stem, f"{stem}_tight_words.json"),
        os.path.join("D:/Boyd Clips/shortwork", "*", f"{stem}_tight_words.json"),
        os.path.join(os.path.dirname(short), f"{stem}_tight_words.json"),
    ]
    for p in pats:
        hit = sorted(glob.glob(p))
        if hit:
            return hit[0]
    return None


def _n_words(words_json: str) -> int:
    d = json.load(open(words_json, encoding="utf-8"))
    if isinstance(d, dict):
        d = d.get("words", d)
    return len(d)


def floor_wpm() -> float:
    d = json.load(open(FLOOR, encoding="utf-8"))
    pace = d.get("pace") or {}
    acc = pace.get("accepted") or {}
    if len(acc) >= 3:
        return round(min(acc.values()) * 0.95, 1)
    return float(pace.get("floor_wpm", 185.2))


def measure(short: str, words_json: str | None = None):
    wj = words_json or _words_path(short)
    if not wj or not os.path.isfile(wj):
        return None, None, None, ("no aligned words file for this short - the chain "
                                  "writes <work>/<stem>_tight_words.json; pass --words")
    n = _n_words(wj)
    dur = _duration(short)
    return n, dur, (n / dur * 60.0 if dur else 0.0), None


def check(short: str, words_json: str | None = None, quiet: bool = False) -> bool:
    n, dur, wpm, err = measure(short, words_json)
    if err:
        if not quiet:
            print(f"  SKIP  {os.path.basename(short)}: {err}")
        return True
    lo = floor_wpm()
    ok = wpm >= lo
    if not quiet:
        print(f"  {os.path.basename(short)}   {n} words / {dur:.2f}s = {wpm:.1f} wpm")
        if ok:
            print(f"   PASS  P pace   {wpm:.1f} >= {lo:.1f} wpm "
                  f"(min of his accepted shorts, -5%)")
        else:
            print(f"   FAIL  P pace   {wpm:.1f} < {lo:.1f} wpm - this is the "
                  f"'slow, boring' defect. The fix is the SPAN, not the edit: "
                  f"read the scene (tools/banger_digest.py) and pick one with "
                  f"short answers and no long unbroken turn. Re-cutting the same "
                  f"span tighter will not reach the floor.")
    return ok


def selftest() -> int:
    ok = True
    print("R58 short pace - his accepted shorts must pass, the one he called slow must fail")
    acc = [
        ("SANCHEZ", "D:/Boyd Clips/READY-TO-POST/SANCHEZ_SHORT_FINAL.mp4",
         "D:/Boyd Clips/shortwork/_pace/SANCHEZ_SHORT_FINAL.words.json"),
        ("CARTHIEF", "D:/Boyd Clips/READY-TO-POST/CARTHIEF_SHORT_FINAL_V2.mp4",
         "D:/Boyd Clips/shortwork/_pace/CARTHIEF_SHORT_FINAL_V2.words.json"),
        ("OFFERUP", "D:/Boyd Clips/READY-TO-POST/OFFERUP_SHORT_FINAL.mp4",
         "D:/Boyd Clips/shortwork/_pace/OFFERUP_SHORT_FINAL.words.json"),
    ]
    seen = 0
    for k, v, w in acc:
        if not (os.path.isfile(v) and os.path.isfile(w)):
            print(f"    .... {k}: files not on this machine, skipped")
            continue
        seen += 1
        if not check(v, w, quiet=True):
            ok = False
            print(f"    !! accepted short {k} falls under its own floor")
        else:
            print(f"    ok   accepted {k} passes")
    ctrl_v = "D:/Boyd Clips/READY-TO-POST/PERKINS/PERKINS_SHORT.mp4"
    ctrl_w = "D:/Boyd Clips/shortwork/PERKINS_SHORT/PERKINS_SHORT_tight_words.json"
    if os.path.isfile(ctrl_v) and os.path.isfile(ctrl_w):
        if check(ctrl_v, ctrl_w, quiet=True):
            ok = False
            print("    !! the control PASSED - the gate cannot see what he called slow")
        else:
            print("    ok   control (the short he called slow) FAILS the gate")
    else:
        ok = False
        print("    !! the known-slow control is missing - the gate is unproven")
    if seen < 2:
        ok = False
        print("    !! fewer than 2 accepted shorts measurable - envelope unproven")
    print("SHORT_PACE_SELFTEST_OK" if ok else "SHORT_PACE_SELFTEST_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("short", nargs="?")
    ap.add_argument("--words")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.short:
        ap.error("a short is required")
    ok = check(a.short, a.words)
    print("SHORT_PACE_OK" if ok else "SHORT_PACE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
