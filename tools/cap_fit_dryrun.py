"""Dry-run the story-preserving cap on a stored case — no download, no render,
no model call.

Pieces are approximated from the transcript: the case span is split at word
gaps >= output.longform.dead_air_s (the same rule plan_silence_trim applies to
the audio; measured on this footage the two agree to within 0.1 s) and padded
by pad_before_s / pad_after_s. The money moment comes from the stored case's
editorial block, or --money-moment when the row predates BOYD_EDITORIAL_V2.

    python tools/cap_fit_dryrun.py k6O8Ev7XZjU:5773 --money-moment 6924
    python tools/cap_fit_dryrun.py k6O8Ev7XZjU:5773 --money-moment 6924 --cap 900 --no-trim
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import capfit  # noqa: E402
from boydclips.config import load_config  # noqa: E402
from boydclips.render import Segment  # noqa: E402
from boydclips.state import Store  # noqa: E402


def proxy_pieces(words, lo: float, hi: float, dead_air_s: float, pad_before: float, pad_after: float) -> list[Segment]:
    ws = [w for w in words if lo <= w["t"] <= hi]
    if not ws:
        return [Segment(lo, hi)]
    runs, start = [], lo
    for a, b in zip(ws, ws[1:]):
        if b["t"] - a["t"] >= dead_air_s:
            runs.append((start, a["t"] + 0.35))
            start = b["t"] - 0.35
    runs.append((start, hi))
    return [Segment(max(0.0, s - (pad_before if i == 0 else 0)), e + (pad_after if i == len(runs) - 1 else 0))
            for i, (s, e) in enumerate(runs)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_key")
    ap.add_argument("--cap", type=float, help="override output.longform.max_duration_s")
    ap.add_argument("--money-moment", type=float, help="override/supply editorial.money_moment_s")
    ap.add_argument("--no-trim", action="store_true", help="do not remove dead air first (shows the cap on the raw span)")
    a = ap.parse_args()

    cfg = load_config()
    lf = cfg.require("output.longform")
    cap = a.cap or float(lf.get("max_duration_s", 1200))
    st = Store(cfg.path("paths.state_db"))
    case = st.get_case(a.case_key)
    if not case:
        print("no such case"); return 1
    vid = a.case_key.split(":")[0]
    windows = st.case_windows(vid, case["start_s"]) or [(case["start_s"], case["end_s"])]
    st.close()
    words = json.loads((ROOT / "work" / vid / f"{vid}.transcript.json").read_text(encoding="utf-8"))["words"]

    if a.money_moment is not None:
        case.setdefault("editorial", {})["money_moment_s"] = a.money_moment
    pieces: list[Segment] = []
    for lo, hi in windows:
        if a.no_trim:
            pieces.append(Segment(max(0.0, lo - lf.get("pad_before_s", 4.0)), hi + lf.get("pad_after_s", 3.0)))
        else:
            pieces += proxy_pieces(words, lo, hi, float(lf.get("dead_air_s", 25.0)),
                                   float(lf.get("pad_before_s", 4.0)), float(lf.get("pad_after_s", 3.0)))
    before = sum(p.duration for p in pieces)
    print(f"{a.case_key}  {case.get('defendant_name')}  windows {windows}")
    print(f"pieces after dead-air proxy ({'none' if a.no_trim else lf.get('dead_air_s')}s): {len(pieces)}  total {before:.0f}s  cap {cap:.0f}s")
    for p in pieces:
        print(f"   {p.start_s:8.1f}–{p.end_s:8.1f}  {p.duration:6.1f}s")
    print()
    print("OLD behaviour (walk in order, cut at the budget):")
    budget, old = cap, []
    for p in pieces:
        if budget <= 0: break
        if p.duration <= budget: old.append(p); budget -= p.duration
        else: old.append(Segment(p.start_s, p.start_s + budget)); budget = 0
    print(f"   kept {sum(p.duration for p in old):.0f}s, ends at {old[-1].end_s:.1f}s; case ends {pieces[-1].end_s:.1f}s -> "
          f"{'TAIL CUT by %.0fs' % (pieces[-1].end_s - old[-1].end_s) if pieces[-1].end_s - old[-1].end_s > 1 else 'intact'}")
    print()
    try:
        plan = capfit.plan_cap_fit(pieces, cap, case, lf.get("cap_fit") or {})
        print("NEW behaviour:")
        print(capfit.describe(plan))
    except capfit.CapFitError as exc:
        print(f"NEW behaviour: REFUSED — {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
