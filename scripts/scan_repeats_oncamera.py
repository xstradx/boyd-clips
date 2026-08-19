"""Probe every qualifying repeat episode for whether anyone is actually on camera.

The rubric scores words. `oncamera` scores pictures. This runs the second check
over the shortlist the first one produced, so the "32 ready episodes" number
stops being a transcript claim and starts being a shootable one.

Costs about 6 x 0.5s of video per hearing. Writes state/oncamera.json so the
result is cached and the daily run never re-probes a case it has already seen.
"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import oncamera, repeats
from boydclips.config import load_config
from boydclips.state import Store

cfg = load_config()
store = Store(cfg.path("paths.state_db"))
eps = repeats.qualifying(store.conn, dict(cfg.get("analysis.repeat_defendant", {}) or {}))
cache_path = ROOT / "state" / "oncamera.json"
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
print(f"probing the best hearing of {min(limit, len(eps))} of {len(eps)} episodes\n")
print(f"{'defendant':26}{'hearings':>9}{'best':>7}{'min':>7}  camera")

for e in eps[:limit]:
    # Probe the hearing that earned the episode its place.
    h = max(e.hearings, key=lambda x: x["total_score"] or 0)
    key = h["case_key"]
    if key in cache:
        v = cache[key]
    else:
        out = ROOT / "out" / "oncam" / key.replace(":", "_")
        frames = sorted(out.glob("f*.png")) or oncamera.sample_frames(
            h["video_id"], h["start_s"], h["end_s"], n=6, out_dir=out)
        if len(frames) < 2:
            v = {"usable": None, "reason": "could not sample"}
        else:
            layout = oncamera.detect_layout(frames)
            r = oncamera.analyse(frames, layout)
            v = {"usable": r.usable, "live": r.live_tiles, "layout": r.layout,
                 "reason": r.reason,
                 "detail": [t.detail for t in r.tiles],
                 "dark": [t.dark for t in r.tiles],
                 "faces": max((t.faces for t in r.tiles), default=0)}
        cache[key] = v
        cache_path.write_text(json.dumps(cache, indent=2))
    mark = {True: "OK  ", False: "DEAD", None: "??  "}[v.get("usable")]
    extra = "" if v.get("usable") else f"  <- {v.get('reason','')}"
    faces = v.get("faces", 0)
    print(f"{e.defendant[:24]:26}{len(e.hearings):>9}{e.best_score:>7.1f}"
          f"{e.total_s/60:>7.1f}  {mark} faces={faces}{extra}")

ok = [k for k, v in cache.items() if v.get("usable")]
print(f"\n{len(ok)} of {len(cache)} probed hearings have someone on camera")
print(f"cache: {cache_path}")
store.close()
