"""Analyse archived dockets to build the case library. Analysis only — no
downloads, no rendering, nothing published.

Resumable by construction: analyze_docket() short-circuits on work/<id>/scored.json,
so re-running skips completed dockets and costs nothing. A docket that dies
mid-analysis writes no cache and is simply retried next pass.

Usage:
    python scripts/backfill_analyse.py --limit 40           # 40 most recent
    python scripts/backfill_analyse.py --limit 40 --dry-run # show the plan only
"""
from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import discover                    # noqa: E402
from boydclips.analyze import RefusalError        # noqa: E402
from boydclips.pipeline import Pipeline           # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("backfill")

MIN_WORDS = 3000     # thin dockets yielded nothing; not worth the LLM time


def main() -> int:
    limit = 40
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    dry = "--dry-run" in sys.argv

    index = Path("state/archive_transcripts.json")
    if not index.exists():
        log.error("run scripts/backfill_transcripts.py first")
        return 1
    rows = json.load(open(index, encoding="utf-8"))

    pipe = Pipeline()
    done = {r["video_id"] for r in
            pipe.store._conn.execute(
                "SELECT video_id FROM dockets WHERE status IN "
                "('analyzed','no_eligible_cases','complete')")}

    todo = [r for r in rows
            if r["words"] >= MIN_WORDS
            and r["video_id"] not in done
            and not (Path("work") / r["video_id"] / "scored.json").exists()]
    todo.sort(key=lambda r: r["date"], reverse=True)
    todo = todo[:limit]

    words = sum(r["words"] for r in todo)
    log.info("%d dockets queued (%s words). Newest %s, oldest %s",
             len(todo), f"{words:,}",
             todo[0]["date"] if todo else "-", todo[-1]["date"] if todo else "-")
    if dry:
        for r in todo:
            log.info("   %s  %s  %6d words", r["date"], r["video_id"], r["words"])
        return 0

    eligible_total = cases_total = failed = 0
    t0 = time.time()

    for i, r in enumerate(todo, 1):
        d = discover.Docket(video_id=r["video_id"], title=r["title"],
                            duration_s=r["duration_s"], docket_date=r["date"],
                            session=r.get("session") or "unknown")
        log.info("[%d/%d] %s %s (%d words)", i, len(todo), r["date"],
                 r["video_id"], r["words"])
        try:
            scored = pipe.analyze_docket(d)
        except RefusalError as exc:
            log.warning("   refused: %s", str(exc)[:90])
            pipe.store.mark_docket(d.video_id, "refused", str(exc))
            failed += 1
            continue
        except Exception as exc:
            log.error("   FAILED: %s", str(exc)[:120])
            log.debug(traceback.format_exc())
            pipe.store.mark_docket(d.video_id, "error", str(exc))
            failed += 1
            continue

        elig = [c for c in scored if c.get("eligible")]
        cases_total += len(scored)
        eligible_total += len(elig)
        if not elig:
            pipe.store.mark_docket(d.video_id, "no_eligible_cases")
        log.info("   -> %d cases, %d eligible   [running: %d eligible, %.1f h]",
                 len(scored), len(elig), eligible_total, (time.time() - t0) / 3600)

    pipe.cleanup()
    pipe.close()
    log.info("\ndone: %d dockets, %d cases, %d eligible, %d failed, %.1f hours",
             len(todo), cases_total, eligible_total, failed,
             (time.time() - t0) / 3600)
    log.info("eligible per docket: %.1f",
             eligible_total / max(1, len(todo) - failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
