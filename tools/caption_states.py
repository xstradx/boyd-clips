"""Print a plan's kinetic caption timeline — display cleanup with its
source audit, phrases with their reveal chunks, the states around a speaker
switch, and the visual-change density — so phrasing can be judged BEFORE a
render.

    python tools/caption_states.py out/short_plans/flores_v2g.json
    python tools/caption_states.py out/short_plans/flores_v2g.json --switch 1 --before 6 --after 16 --all
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

from boydclips import captions  # noqa: E402


def mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_json")
    ap.add_argument("--switch", type=int, default=1)
    ap.add_argument("--before", type=int, default=6)
    ap.add_argument("--after", type=int, default=16)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    plan = json.loads(Path(a.plan_json).read_text(encoding="utf-8"))
    cards = plan["captions"]
    style = plan.get("caption_style") or {}
    audit = plan.get("caption_audit") or []
    display = [x for x in audit if x["kept"]]
    dens = plan.get("caption_density") or captions.density(cards)
    print(f"{plan['case_key']}  planner={plan.get('caption_planner')}  {len(audit)} kept words -> {len(display)} displayed "
          f"({len(audit) - len(display)} omitted for display) -> {len(cards)} one-line phrases, "
          f"{sum(len(c['events']) for c in cards)} reveals; widths {captions.width_source(style)}")
    print(f"density: {dens['changes']} visual changes over {dens['span_s']}s = {dens['per_second']} per second")

    print("\nDISPLAY CLEANUP (source index: word -> shown / omitted[reason]):")
    for x in audit:
        if x["kept"]:
            continue
        print(f"  src {x['i']:3d} {mmss(x['t'])} {x['speaker'] or '?':9s} {x['w']!r:14} OMITTED [{x['reason']}] {x['note']}")
    print("  (every other kept word is displayed verbatim, censored and cased)")

    print("\nSOURCE -> DISPLAY per speaker run (omitted source words in [brackets]):")
    runs: list[list[dict]] = []
    for x in audit:
        if runs and runs[-1][-1]["speaker"] == x["speaker"]:
            runs[-1].append(x)
        else:
            runs.append([x])
    for r in runs:
        spk = (r[0]["speaker"] or "?").upper()
        src_line = " ".join(x["w"] if x["kept"] else f"[{x['w']}]" for x in r)
        disp_line = " ".join(x["w"] for x in r if x["kept"])
        print(f"  {spk:9s} {mmss(r[0]['t'])}  source : {src_line}")
        print(f"  {'':9s} {'':8s}  display: {disp_line}")

    print("\nPHRASES (speaker | start-clear | width | chunks):")
    for k, c in enumerate(cards):
        srcs = [i for s in c["src"] for i in s]
        print(f"  {k:02d} {c['speaker'] or '?':9s} {mmss(c['start_s'])}-{mmss(c['clear_s'])} {c['width_px']:5.0f}px  "
              f"{' | '.join(c['chunks'])}    src {srcs[0]}..{srcs[-1]}")

    switches = [k for k in range(1, len(cards)) if cards[k]["speaker"] != cards[k - 1]["speaker"]]
    states = captions.kinetic_states(cards)
    if a.all or not switches:
        window = states
        print("\nSTATES (all):")
    else:
        k = switches[min(len(switches), max(1, a.switch)) - 1]
        pivot = next(i for i, s in enumerate(states) if s["card"] == k and s["kind"] == "REVEAL")
        window = states[max(0, pivot - a.before): pivot + a.after]
        print(f"\nSTATES around switch #{a.switch}: phrase {k - 1} ({cards[k - 1]['speaker']}) -> phrase {k} ({cards[k]['speaker']}):")
    for s in window:
        if s["kind"] == "REVEAL":
            print(f"  {mmss(s['t'])} {(s['speaker'] or '?').upper():9s} `{s['text']}`   new=`{s['new']}` (yellow, pop {s['pop'][0]:.2f}-{s['pop'][1]:.2f}s)  width {s['width_px']:.0f}px")
        else:
            print(f"  {mmss(s['t'])} {s['kind']}")

    gates = captions.kinetic_qc(cards, display, style, plan.get("caption_hard_breaks") or [], audit)
    print("\nQC: " + "  ".join(f"{g['gate']}={'PASS' if g['ok'] else 'FAIL'}" for g in gates))
    for g in gates:
        if not g["ok"]:
            print(f"   FAIL {g['gate']}: {g['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
