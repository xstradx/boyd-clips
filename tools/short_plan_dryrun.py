"""Dry-run SHORTS_EDITOR_V2 on a stored case — no download, no render, no
model call, no credits.

Reads the case row from the state DB (or a scored.json) and the cached
transcript under work/<video_id>/, plans the short, prints the edit plan the
way a reviewer reads it, and optionally writes the plan JSON.

    python tools/short_plan_dryrun.py eWsve0icYUk:2284
    python tools/short_plan_dryrun.py k6O8Ev7XZjU:5773 --money-moment 6950
    python tools/short_plan_dryrun.py oL6lV6gCyOc:7163 --money-moment 7588 --json out/plan.json
    python tools/short_plan_dryrun.py JgvW7oCQxuI:8279 --money-moment 8372 --turns

The tile map defaults to the daily convention (defendant top / Boyd bottom);
pass --no-tiles to see the plan the planner makes when the tiles are unknown
(framing stays duo, no punch-ins).
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

from boydclips import shorts_editor  # noqa: E402
from boydclips.config import load_config  # noqa: E402
from boydclips.state import Store  # noqa: E402
from boydclips.transcribe import Word  # noqa: E402


def load_case(cfg, case_key: str) -> dict:
    vid, start = case_key.split(":")
    case = None
    try:
        st = Store(cfg.path("paths.state_db"))
        case = st.get_case(case_key)
        st.close()
    except Exception as exc:  # no DB is fine for a dry run
        print(f"(state db unavailable: {exc})")
    if not case:
        p = ROOT / "work" / vid / "scored.json"
        if p.exists():
            payload = json.loads(p.read_text(encoding="utf-8"))
            rows = payload.get("cases", payload) if isinstance(payload, dict) else payload
            for c in rows:
                if abs(float(c.get("start_s", -1)) - float(start)) < 2.0:
                    case = c
                    break
    if not case:
        raise SystemExit(f"no case row for {case_key} in the state db or work/{vid}/scored.json")
    return case


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_key")
    ap.add_argument("--money-moment", type=float, help="supply/override editorial.money_moment_s")
    ap.add_argument("--quote", help="supply/override editorial.money_moment (the quote text the payoff span is matched to)")
    ap.add_argument("--min-score", type=int, help="override planner.min_score")
    ap.add_argument("--no-tiles", action="store_true", help="plan as if the tiles could not be measured")
    ap.add_argument("--turns", action="store_true", help="print the labelled speaker turns of the case")
    ap.add_argument("--json", help="write the plan JSON here")
    a = ap.parse_args()

    cfg = load_config()
    sh = cfg.require("output.short")
    pcfg = dict(sh.get("planner") or {})
    pcfg.setdefault("max_duration_s", sh.get("max_duration_s", 59))
    if a.min_score is not None:
        pcfg["min_score"] = a.min_score
    case = load_case(cfg, a.case_key)
    if a.money_moment is not None:
        case.setdefault("editorial", {})["money_moment_s"] = a.money_moment
    if a.quote:
        case.setdefault("editorial", {})["money_moment"] = a.quote
    vid = a.case_key.split(":")[0]
    tpath = ROOT / "work" / vid / f"{vid}.transcript.json"
    words = [Word(t=w["t"], w=w["w"]) for w in json.loads(tpath.read_text(encoding="utf-8"))["words"]]

    cap = dict(sh.get("captions") or {})
    cap.update(dict(cap.pop("rail", {}) or {}))          # the V2 rail style overrides the shared keys
    pcfg["canvas_h"] = int(sh.get("resolution", [1080, 1920])[1])
    tile_map = None if a.no_tiles else {"boyd": "bottom", "defendant": "top", "source": "dry-run default"}

    print(f"{a.case_key}  {case.get('defendant_name', '')}  span {case['start_s']:.0f}-{case['end_s']:.0f}s  "
          f"scorer shortable={case.get('shortable')}  money_moment_s={(case.get('editorial') or {}).get('money_moment_s')}")
    if a.turns:
        tw = shorts_editor.timed_words(words, float(case["start_s"]), float(case["end_s"]))
        for tr in shorts_editor.label_speakers(shorts_editor.split_turns(tw)):
            print(f"  turn {tr.idx:3d} {shorts_editor.hhmmss(tr.start_s)} {tr.speaker:<9} "
                  f"{'PROC ' if tr.procedural else '     '}{tr.text[:110]}")
        print()
    plan = shorts_editor.plan_short(case, a.case_key, words, pcfg, cap, tile_map=tile_map)
    print(shorts_editor.describe(plan))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nplan written: {a.json}")
    return 0 if plan.ok else 2


if __name__ == "__main__":
    sys.exit(main())
