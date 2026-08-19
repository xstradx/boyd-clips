"""Re-score the repeat-defendant shortlist on the CURRENT rubric.

WHY
---
Checked 2026-08-18: all 727 cases in state/pipeline.db were scored on the
RETIRED rubric — human_stakes / dramatic_turn / judge_moment / self_contained.
Zero were scored on the live one — pushback / boyd_register / receipt /
consequence / hook_strength.

That is not a cosmetic difference. The current rubric exists specifically to
stop rewarding what the old one rewarded; prompts/score_cases.md says outright
"do not reward how serious the charge is, how sad the story is, how long the
hearing runs". Arnold Pena's retired score was human_stakes 98 on a hearing
whose video feed is a black Zoom name card for all 51 minutes.

So every ranking built on those numbers — including the repeat shortlist —
is ordered by a rubric nobody uses any more.

WHAT THIS DOES
--------------
Re-scores ONLY the hearings belonging to qualifying repeat episodes, reusing
the existing case boundaries. No re-segmenting, no downloads. Transcripts come
from work/<video_id>/ if cached and are re-fetched from captions (free) if not.

NON-DESTRUCTIVE BY DESIGN. Results go to a NEW `rescores` table, stamped with
the prompt version. cases.total_score is left alone. If the new rubric turns
out to rank worse, the old numbers are still there to compare against — which
is the whole point, since nothing in this project has a measured outcome yet.

Resumable: each docket's result caches to work/<video_id>/rescore_repeats.json.

    python scripts/rescore_repeats.py --dry-run
    python scripts/rescore_repeats.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import repeats                       # noqa: E402
from boydclips.analyze import Analyzer, RefusalError  # noqa: E402
from boydclips.config import load_config, prompt_text  # noqa: E402
from boydclips.state import Store                   # noqa: E402
from boydclips.transcribe import get_transcript     # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("rescore")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rescores (
    case_key       TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    total_score    REAL,
    old_score      REAL,
    eligible       INTEGER,
    reason         TEXT,
    scores_json    TEXT,
    payload        TEXT,
    scored_at      TEXT NOT NULL,
    PRIMARY KEY (case_key, rubric_version)
);
"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    store.conn.executescript(SCHEMA)
    store.conn.commit()

    version, _, _ = prompt_text("score_cases")
    log.info("rubric: prompts/score_cases.md v%s", version)
    log.info("weights: %s", cfg.require("analysis.rubric_weights"))

    eps = repeats.qualifying(
        store.conn, dict(cfg.get("analysis.repeat_defendant", {}) or {}))
    hearings = [h for e in eps for h in e.hearings]
    by_docket: dict[str, list[dict]] = {}
    for h in hearings:
        by_docket.setdefault(h["video_id"], []).append(h)

    log.info("%d episodes, %d hearings, %d dockets",
             len(eps), len(hearings), len(by_docket))

    already = {r[0] for r in store.conn.execute(
        "SELECT case_key FROM rescores WHERE rubric_version = ?", (version,))}
    if already:
        log.info("%d hearings already re-scored on v%s — skipping",
                 len(already), version)

    if dry:
        for vid, hs in sorted(by_docket.items(), key=lambda kv: -len(kv[1])):
            todo = [h for h in hs if h["case_key"] not in already]
            log.info("  %s  %d hearing(s), %d to do", vid, len(hs), len(todo))
        return 0

    analyzer = Analyzer(cfg, log=log)
    work_root = cfg.path("paths.work")
    done = failed = 0
    t0 = time.time()

    for i, (vid, hs) in enumerate(sorted(by_docket.items()), 1):
        todo = [h for h in hs if h["case_key"] not in already]
        if not todo:
            continue
        row = store.get_docket_row(vid)
        title = (row["title"] if row else vid) or vid
        date = (row["docket_date"] if row else "unknown") or "unknown"
        log.info("[%d/%d] %s  %s  (%d hearing(s))", i, len(by_docket), date, vid,
                 len(todo))

        work = work_root / vid
        work.mkdir(parents=True, exist_ok=True)
        cache = work / "rescore_repeats.json"
        cached = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}

        try:
            transcript = get_transcript(
                vid, work,
                source=cfg.get("transcription.source", "auto_captions"),
                language=cfg.get("transcription.language", "en"),
                whisper_fallback=False)
        except Exception as exc:
            log.error("   transcript FAILED: %s", str(exc)[:120])
            failed += len(todo)
            continue

        # Rebuild the minimal case dicts score() needs. The stored payload
        # dropped segment fields like `charge` and `one_line`, but score()
        # only uses these for prompt context and for choosing the transcript
        # excerpt — the boundaries are what matter and they are intact.
        # find_episodes() selects named columns and does not carry `payload`,
        # so the old one-line summaries are fetched here for prompt context.
        summaries: dict[str, str] = {}
        for k, raw in store.conn.execute(
                "SELECT case_key, payload FROM cases WHERE video_id = ?", (vid,)):
            try:
                summaries[k] = (json.loads(raw) or {}).get("summary") or ""
            except Exception:
                summaries[k] = ""

        cases = []
        for h in todo:
            cases.append({
                "start_s": h["start_s"],
                "end_s": h["end_s"],
                "defendant_name": h["defendant"] or "unknown",
                "cause_number": h["cause_number"] or "",
                "proceeding_type": h["proceeding_type"] or "other",
                "one_line": summaries.get(h["case_key"], "")[:300],
            })

        try:
            scored = analyzer.score(transcript, cases,
                                    {"title": title, "docket_date": date,
                                     "url": f"https://www.youtube.com/watch?v={vid}"})
        except RefusalError as exc:
            log.warning("   refused: %s", str(exc)[:90])
            failed += len(todo)
            continue
        except Exception as exc:
            log.error("   FAILED: %s", str(exc)[:140])
            log.debug(traceback.format_exc())
            failed += len(todo)
            continue

        # Match results back to their case_key by start_s — score() returns
        # cases in rank order, not input order.
        by_start = {round(float(h["start_s"])): h for h in todo}
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with store.tx() as conn:
            for c in scored:
                h = by_start.get(round(float(c["start_s"])))
                if h is None:                       # nearest within 30s
                    near = [(abs(float(c["start_s"]) - float(x["start_s"])), x)
                            for x in todo]
                    near.sort()
                    if near and near[0][0] <= 30:
                        h = near[0][1]
                if h is None:
                    log.warning("   unmatched scored case at %.0fs", c["start_s"])
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO rescores VALUES (?,?,?,?,?,?,?,?,?)",
                    (h["case_key"], version, c["total_score"], h["total_score"],
                     1 if c.get("eligible") else 0, c.get("ineligible_reason") or "",
                     json.dumps(c.get("scores") or {}), json.dumps(c), now))
                cached[h["case_key"]] = c
                done += 1
                log.info("   %-24s %5.1f -> %5.1f  %s", h["case_key"],
                         h["total_score"] or 0, c["total_score"],
                         "eligible" if c.get("eligible") else
                         (c.get("ineligible_reason") or "not eligible")[:40])
        cache.write_text(json.dumps(cached, indent=2), encoding="utf-8")

    log.info("\nre-scored %d hearing(s), %d failed, %.1f min",
             done, failed, (time.time() - t0) / 60)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
