"""Score mined moments with the model, then camera-check the winners.

scripts/mine_moments.py is recall - it narrows 352 transcripts to a few hundred
candidates using vocabulary novelty, address density and her documented tells.
It cannot tell the spearmint-gum riff from a competent lecture, and it cannot
reliably tell her voice from a lawyer's when the caption stream drops a '>>'.

This is the precision pass. One model call per candidate against
prompts/judge_moments.md, which returns:
  is_boyd              - kills the passage if it is counsel or a witness
  out_of_pocket 0-100  - how far outside normal judicial register
  hook_quote           - the line that works at second 0
  clip offsets         - the tightest run containing setup and payoff

Then the survivors get a camera probe, because a perfect line over a black Zoom
name card is not a video - see oncamera.py and Arnold Pena.

    python scripts/judge_moments.py --top 40      # judge the best 40 candidates
    python scripts/judge_moments.py --best 5      # then show the best 5
"""
from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import oncamera                       # noqa: E402
from boydclips.analyze import Analyzer               # noqa: E402
from boydclips.config import load_config, prompt_text  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {
        "is_boyd": {"type": "boolean"},
        "speaker_note": {"type": "string"},
        "out_of_pocket": {"type": "number"},
        "hook_quote": {"type": "string"},
        "why": {"type": "string"},
        "clip_start_offset_s": {"type": "number"},
        "clip_end_offset_s": {"type": "number"},
        "context_needed": {"type": "string"},
        "safe_to_publish": {"type": "boolean"},
    },
    "required": ["is_boyd", "speaker_note", "out_of_pocket", "hook_quote", "why",
                 "clip_start_offset_s", "clip_end_offset_s", "context_needed",
                 "safe_to_publish"],
    "additionalProperties": False,
}


def arg(name, default=None, cast=str):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main() -> int:
    top = arg("--top", 40, int)
    best = arg("--best", 5, int)
    src = ROOT / "state" / "moments.json"
    if not src.exists():
        print("run scripts/mine_moments.py --json state/moments.json first")
        return 1
    cands = json.loads(src.read_text(encoding="utf-8"))[:top]
    print(f"judging {len(cands)} candidates against prompts/judge_moments.md")

    cfg = load_config()
    version, _, template = prompt_text("judge_moments")
    analyzer = Analyzer(cfg)
    cache_path = ROOT / "state" / "moments_judged.json"
    judged = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    t0 = time.time()
    for i, c in enumerate(cands, 1):
        key = f"{c['video_id']}:{int(c['start_s'])}"
        if key in judged:
            continue
        mins = int(c["start_s"] // 60)
        user = template.format(
            n=i, total=len(cands), video_id=c["video_id"],
            clock=f"{mins // 60}:{mins % 60:02d}",
            labels=", ".join(c.get("labels") or []) or "none",
            text=c["text"])
        try:
            r = analyzer._call("judge_moments", user, SCHEMA)
        except Exception as exc:
            print(f"  [{i}/{len(cands)}] {key} FAILED: {str(exc)[:90]}")
            continue
        r["_c"] = c
        judged[key] = r
        cache_path.write_text(json.dumps(judged, indent=2), encoding="utf-8")
        flag = "" if r["is_boyd"] else "  (not Boyd)"
        print(f"  [{i}/{len(cands)}] {key:24} {r['out_of_pocket']:5.0f}{flag}")
    print(f"judged in {(time.time() - t0) / 60:.1f} min\n")

    keep = [r for r in judged.values()
            if r.get("is_boyd") and r.get("safe_to_publish")]
    keep.sort(key=lambda r: -r["out_of_pocket"])

    print("camera-checking the leaders...")
    final = []
    cam_path = ROOT / "state" / "oncamera.json"
    cam = json.loads(cam_path.read_text()) if cam_path.exists() else {}
    for r in keep:
        if len(final) >= best:
            break
        c = r["_c"]
        a = c["start_s"] + r["clip_start_offset_s"]
        b = c["start_s"] + r["clip_end_offset_s"]
        key = f"{c['video_id']}:{int(a)}"
        v = cam.get(key)
        if v is None:
            out = ROOT / "out" / "oncam" / key.replace(":", "_")
            frames = sorted(out.glob("f*.png")) or oncamera.sample_frames(
                c["video_id"], a, max(b, a + 20), n=5, out_dir=out)
            if len(frames) >= 2:
                res = oncamera.analyse(frames, oncamera.detect_layout(frames))
                v = {"usable": res.usable, "reason": res.reason,
                     "faces": max((t.faces for t in res.tiles), default=0)}
            else:
                v = {"usable": None, "reason": "could not sample"}
            cam[key] = v
            cam_path.write_text(json.dumps(cam, indent=2), encoding="utf-8")
        if not v.get("usable"):
            print(f"  dropped {key}: {v.get('reason', '')[:60]}")
            continue
        r["_clip"] = (a, b)
        final.append(r)

    print("\n" + "=" * 94)
    for i, r in enumerate(final, 1):
        c = r["_c"]
        a, b = r["_clip"]
        mins = int(a // 60)
        print(f"\n{i}. out-of-pocket {r['out_of_pocket']:.0f}   "
              f"{c['video_id']} @{mins // 60}:{mins % 60:02d}:{int(a % 60):02d}   "
              f"clip {int(b - a)}s")
        print(f'   HOOK: "{r["hook_quote"]}"')
        print(textwrap.fill(f"WHY: {r['why']}", 92, initial_indent="   ",
                            subsequent_indent="        "))
        if r.get("context_needed"):
            print(textwrap.fill(f"CONTEXT: {r['context_needed']}", 92,
                                initial_indent="   ", subsequent_indent="            "))
        print(f"   https://www.youtube.com/watch?v={c['video_id']}&t={int(a) - 3}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
