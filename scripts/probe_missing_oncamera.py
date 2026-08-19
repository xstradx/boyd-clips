"""Probe any re-scored hearing that the camera scan has not seen.

The first scan probed each episode's best hearing under the OLD rubric. The
re-score moved which hearing is best for several episodes, so a handful now
rank on a hearing whose camera was never checked. This closes that gap.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import oncamera, repeats
from boydclips.config import load_config, prompt_text
from boydclips.state import Store

cfg = load_config(); store = Store(cfg.path("paths.state_db"))
version, _, _ = prompt_text("score_cases")
new = {k: s for k, s in store.conn.execute(
    "SELECT case_key, total_score FROM rescores WHERE rubric_version = ?", (version,))}
cache_path = ROOT / "state" / "oncamera.json"
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

eps = repeats.qualifying(store.conn, dict(cfg.get("analysis.repeat_defendant", {}) or {}))
todo = []
for e in eps:
    scored = [(new[h["case_key"]], h) for h in e.hearings if h["case_key"] in new]
    if not scored:
        continue
    _, h = max(scored, key=lambda t: t[0])
    if h["case_key"] not in cache:
        todo.append((e, h))

print(f"{len(todo)} hearing(s) need a camera probe")
for e, h in todo:
    out = ROOT / "out" / "oncam" / h["case_key"].replace(":", "_")
    frames = sorted(out.glob("f*.png")) or oncamera.sample_frames(
        h["video_id"], h["start_s"], h["end_s"], n=6, out_dir=out)
    if len(frames) < 2:
        v = {"usable": None, "reason": "could not sample"}
    else:
        r = oncamera.analyse(frames, oncamera.detect_layout(frames))
        v = {"usable": r.usable, "live": r.live_tiles, "layout": r.layout,
             "reason": r.reason, "detail": [t.detail for t in r.tiles],
             "dark": [t.dark for t in r.tiles],
             "faces": max((t.faces for t in r.tiles), default=0)}
    cache[h["case_key"]] = v
    cache_path.write_text(json.dumps(cache, indent=2))
    print(f"  {e.defendant[:24]:26} {h['case_key']:22} "
          f"{'OK' if v['usable'] else 'DEAD'}  {v.get('reason','')[:60]}")
store.close()
