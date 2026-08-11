"""Fetch transcripts for the whole channel archive. Free, and it triages.

Captions cost nothing — no video is downloaded. Segmentation and scoring are
what cost time and tokens, so pulling every transcript first tells us which
dockets are worth analysing at all before a single LLM call is made.

Usage:  python scripts/backfill_transcripts.py [--limit N]
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import discover                     # noqa: E402
from boydclips.config import load_config           # noqa: E402
from boydclips.transcribe import get_transcript    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("backfill")


def main() -> int:
    limit = 400
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    cfg = load_config()
    url = (cfg.get("source.channel_url")
           or "https://www.youtube.com/@judgestephanieboyd4233/streams")
    work = Path("work")

    dockets = [d for d in discover.list_recent(url, limit) if d.docket_date]
    dockets.sort(key=lambda d: d.docket_date, reverse=True)
    log.info("channel archive: %d streams", len(dockets))

    rows, cached, fetched, failed = [], 0, 0, 0
    for i, d in enumerate(dockets, 1):
        wd = work / d.video_id
        was_cached = (wd / f"{d.video_id}.transcript.json").exists()
        try:
            t = get_transcript(d.video_id, wd)
        except Exception as exc:
            failed += 1
            log.warning("  [%3d/%d] %s FAILED %s", i, len(dockets),
                        d.video_id, str(exc)[:60])
            continue
        cached += was_cached
        fetched += (not was_cached)
        dur = t.words[-1].t if t.words else 0.0
        rows.append({
            "video_id": d.video_id, "date": d.docket_date, "session": d.session,
            "title": d.title, "words": len(t.words), "duration_s": round(dur, 1),
        })
        if i % 20 == 0 or not was_cached:
            log.info("  [%3d/%d] %s %s  %6d words  %4.0f min",
                     i, len(dockets), d.date if hasattr(d, "date") else d.docket_date,
                     d.video_id, len(t.words), dur / 60)
        if not was_cached:
            time.sleep(0.4)          # be polite to YouTube on a 100+ item sweep

    out = Path("state/archive_transcripts.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    total_words = sum(r["words"] for r in rows)
    total_hours = sum(r["duration_s"] for r in rows) / 3600
    log.info("\n%d transcripts (%d cached, %d fetched, %d failed)",
             len(rows), cached, fetched, failed)
    log.info("corpus: %.1f hours of court, %s words", total_hours, f"{total_words:,}")
    log.info("index -> %s", out)

    thin = [r for r in rows if r["words"] < 3000]
    log.info("\n%d dockets under 3k words (likely thin/short sessions — skip these"
             " when analysing)", len(thin))
    log.info("%d dockets worth analysing", len(rows) - len(thin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
