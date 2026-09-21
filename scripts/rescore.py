"""Re-score the whole bank against the rewritten rubric.

The 727 scored cases carry numbers from the OLD rubric — human_stakes,
dramatic_turn, judge_moment, self_contained — which rated abstractions and gave
a routine plea-deadline hearing a 92. spec/SPEC.md §2 replaced those with the
five beats that actually separated 8 winning videos from 6 losing ones on the
channel clipping this same judge, so every stored score is now measuring
something the pipeline no longer asks about.

Re-scoring does NOT re-segment. The case boundaries came from a separate model
call and are unaffected by the rubric change; re-running the segmenter would
churn start/end times, invalidate the cached section downloads keyed to those
timestamps, and cost a docket-length call each. This only re-runs stage 2.

Idempotent and resumable: a docket whose cases already carry the new dimensions
is skipped unless --force.

    python scripts/rescore.py --limit 3      # try a few first
    python scripts/rescore.py                # everything
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips.analyze import Analyzer                           # noqa: E402
from boydclips import analyze as analyze_mod                     # noqa: E402
from boydclips.config import RUBRIC_DIMENSIONS, load_config      # noqa: E402
from boydclips.state import Store                                # noqa: E402
from boydclips.transcribe import Transcript                      # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("rescore")

# The fields the segmenter produced. Stage 2 needs exactly these back; anything
# else in the stored payload is stage-2 output and must not be fed in as input,
# or the model is being shown its own previous answer.
SEGMENT_FIELDS = ("start_s", "end_s", "defendant_name", "cause_number",
                  "proceeding_type", "guilt_posture", "summary")


def already_new(payload: dict) -> bool:
    return set((payload.get("scores") or {}).keys()) == set(RUBRIC_DIMENSIONS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max dockets, 0 = all")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    analyzer = Analyzer(cfg, log=log)

    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    dockets = {r["video_id"]: r for r in db.execute("select * from dockets")}

    todo = []
    for vid, row in dockets.items():
        tp = ROOT / "work" / vid / f"{vid}.transcript.json"
        if not tp.is_file():
            continue
        cases = [json.loads(r["payload"]) for r in
                 db.execute("select payload from cases where video_id=?", (vid,))]
        if not cases:
            continue
        if not a.force and all(already_new(c) for c in cases):
            continue
        todo.append((vid, row, tp, cases))

    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} docket(s) to re-score\n")

    done = failed = 0
    for i, (vid, row, tp, cases) in enumerate(todo, 1):
        t0 = time.time()
        print(f"[{i}/{len(todo)}] {vid}  {row['docket_date']}  {len(cases)} cases")
        try:
            transcript = Transcript.from_json(tp.read_text(encoding="utf-8"))
            meta = {"title": row["title"], "docket_date": row["docket_date"],
                    "url": f"https://www.youtube.com/watch?v={vid}"}
            stripped = [{k: c[k] for k in SEGMENT_FIELDS if k in c} for c in cases]
            scored = analyzer.score(transcript, stripped, meta)
            for c in scored:
                store.save_case(vid, c, c.get("rank"))
            (ROOT / "work" / vid / "scored.json").write_text(
                json.dumps(analyze_mod.score_cache_dump(scored, analyze_mod.current_rubric_version()),
                           ensure_ascii=False, indent=2), encoding="utf-8")
            elig = sum(1 for c in scored if c["eligible"])
            best = max((c["total_score"] for c in scored), default=0)
            print(f"    {elig}/{len(scored)} eligible, best {best:.1f}"
                  f"  ({time.time() - t0:.0f}s)")
            done += 1
        except Exception as exc:
            print(f"    FAILED: {type(exc).__name__}: {str(exc)[:160]}")
            failed += 1

    store.close()
    print(f"\n{done} re-scored, {failed} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
