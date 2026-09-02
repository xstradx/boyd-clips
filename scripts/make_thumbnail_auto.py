"""Thumbnail for any hearing: choose the frames, then build.

Nathan, 2026-08-29: "well enough to be applied to any set of defendants or pics
of judge boyd and whatever is in the video ... from start to finish can handle
everything from a routine".

WHY THIS WRAPPER EXISTS, and it is not a convenience. Three separate attempts to
fix the OFFERUP thumbnail inside the layout solver all failed — the attorney's
head sat at 0.55 coverage behind Judge Boyd, the exact half-peeking state, for
every candidate scale, defendant shift and horizontal offset the solver could
try. The frame simply had no room in it, and a solver cannot compose its way out
of that.

`pick_plate.py` then measured 55 candidate frames of the same hearing and found
five with a completely clear right side. So frame choice is not a preliminary a
human does by hand before the real work — it IS part of the work, and it belongs
inside the routine.

The same reasoning already applies to the other two frames:
  * the DEFENDANT's frame is picked for his reaction (`pick_reaction.py`), because
    the hammer line is a timestamp chosen for what the JUDGE said and there is no
    reason his face is doing anything at that instant
  * JUDGE BOYD's frame is picked for her eyes being level and directed — three
    automated gaze metrics all failed to reproduce Nathan's eye here, so this one
    stays a contact-sheet choice and is passed in

    python scripts/make_thumbnail_auto.py --case OFFERUP --auto-plate --out X.jpg
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def pick_plate_time(source: Path, offset: float, t0: float, t1: float,
                    crop: str, step: float = 10.0) -> list:
    """Return the plate times RANKED by how clear the right side is.

    A list, not a single time, because the builder can now REFUSE a frame -- it
    has a hard floor on Judge Boyd's face size and no fallback below it -- and
    the answer to a refusal is the next candidate, not a smaller judge."""
    js = ROOT / "work" / "q3" / "plate_candidates.json"
    p = subprocess.run(
        [PY, str(ROOT / "scripts" / "pick_plate.py"),
         "--source", str(source), "--offset", str(offset),
         "--from", str(t0), "--to", str(t1), "--crop", crop,
         "--step", str(step), "--json", str(js)],
        capture_output=True, text=True, timeout=5400)
    if not js.is_file():
        print(p.stdout[-800:] if p.stdout else p.stderr[-800:])
        return []
    cands = json.loads(js.read_text())["candidates"]
    print("  plate frames measured, ranked by how clear the right side is: "
          + ", ".join(f"src {c['t']:.0f} ({c['occ'] * 100:.1f}%)"
                      for c in cands[:5]))
    return [(float(c["t"]), float(c["occ"])) for c in cands]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="a key from config/cases.json")
    ap.add_argument("--cases", type=Path, default=ROOT / "config" / "cases.json")
    ap.add_argument("--auto-plate", action="store_true",
                    help="choose the plate frame by measuring which one has "
                         "room for the judge, instead of trusting a supplied "
                         "timestamp")
    ap.add_argument("--plate-step", type=float, default=10.0)
    ap.add_argument("--max-frames", type=int, default=5,
                    help="how many ranked plate frames to try before giving up")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()

    cfg = json.load(open(a.cases, encoding="utf-8"))
    if a.case not in cfg:
        print(f"unknown case '{a.case}'. known: {', '.join(cfg)}")
        return 2
    c = cfg[a.case]
    src = ROOT / c["video"]

    def build(plate_t):
        cmd = [PY, str(ROOT / "scripts" / "thumb_Q3_detail.py"),
               "--video", str(src), "--clip-start", str(c["offset"]),
               "--judge-t", str(c["judge_t"]), "--judge-crop", c["judge_crop"],
               "--plate-t", str(plate_t), "--plate-crop", c["plate_crop"],
               "--white", c["white"], "--yellow", c["yellow"],
               "--out", str(a.out)] + [x for x in a.extra if x != "--"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=5400)
        sys.stdout.write(p.stdout)
        if p.returncode != 0:
            sys.stderr.write((p.stderr or "")[-2000:])
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    # CANDIDATE ORDER. The configured plate_t is tried first -- for OFFERUP it is
    # itself a pick_plate result, recorded in cases.json with the sweep that
    # produced it -- and the sweep only runs when asked for, or when the
    # configured frame is REFUSED.
    order = [(float(c["plate_t"]), None)]
    if a.auto_plate:
        # Sweep only where the defendant is actually AT THE PODIUM.
        #
        # Sweeping the whole case range picked frames from before he was called
        # and after he had left: on SANCHEZ and OFFERUP that produced thumbnails
        # with a stranger in them and the arrow pointing at nobody. The short's
        # own span is the evidence for when he is present, because it was cut
        # from him speaking.
        t0 = c.get("plate_from", c["case_from"])
        t1 = c.get("plate_to", c["case_to"])
        order = pick_plate_time(src, c["offset"], t0, t1,
                                c["plate_crop"], a.plate_step) or order

    tried = []
    i = -1
    while True:
        i += 1
        if i >= min(len(order), a.max_frames):
            break
        plate_t, occ = order[i]
        if i:
            print(f"\n  the builder refused the previous frame. Trying the next "
                  f"candidate: src {plate_t:.1f}"
                  + (f", right side {occ * 100:.1f}% occupied" if occ else ""))
        rc, out = build(plate_t)
        tried.append(plate_t)
        if rc == 0:
            return 0
        # A REFUSAL IS A FRAME PROBLEM, and it is the only failure worth
        # retrying: the layout could not place her at full size, or her layer
        # would not sit in this plate. Anything else is a real error and is
        # reported as one rather than papered over with more attempts.
        # WHAT COUNTS AS "TRY ANOTHER FRAME".
        #
        # This list started as the two explicit REFUSED messages and SANCHEZ
        # then failed on a third the loop did not know about - "cannot identify
        # the defendant - pick another frame", which says in words that another
        # frame is the answer. Every message here means the FRAME is unusable,
        # not the code; anything else is a real error and is reported as one
        # rather than papered over with more attempts.
        retryable = ("LAYOUT REFUSED", "LAYER REFUSED",
                     "pick another frame",
                     "MERGED with another person",
                     "no scrubs found")
        if not any(m in out for m in retryable):
            return rc
        if i == 0 and not a.auto_plate:
            print("\n  REFUSED on the configured frame - measuring the hearing "
                  "for one with room, rather than shrinking her.")
            got = pick_plate_time(src, c["offset"],
                                  c.get("plate_from", c["case_from"]),
                                  c.get("plate_to", c["case_to"]),
                                  c["plate_crop"], a.plate_step)
            order = order + [g for g in got if g[0] not in tried]

    print(f"\n  REFUSED on every frame tried ({', '.join(f'{t:.0f}' for t in tried)}). "
          f"No thumbnail written that Nathan has not already rejected the shape of.")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
