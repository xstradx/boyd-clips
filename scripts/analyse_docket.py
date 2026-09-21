"""Analyse ONE archived docket through the current pipeline (segment + score
under the current rubric) and print its scored cases. Analysis only.

    python scripts/analyse_docket.py dAKO7myCd-g

Targeted mode (2026-09-06): score ONE operator-bounded case through the same
production scorer and safety gate, with the full docket transcript as
context - the path run_case already uses for stale rows - and save it to the
store. Used when the docket-wide scorer loses a whole docket to one bad batch.

    python scripts/analyse_docket.py 8BpyYIAS6b8 --case 5145 6252 \
        --defendant "Raul Iglesias" --type plea --cause "2024 CR 3789; 2024 CR 3800"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import analyze, discover                   # noqa: E402
from boydclips.pipeline import Pipeline, get_transcript  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")


def _docket(pipe: Pipeline, vid: str) -> discover.Docket:
    row = pipe.store.get_docket_row(vid)
    if row is None:
        meta = discover.probe(vid)
        title = meta.get("title") or vid
        docket = discover.Docket(video_id=vid, title=title, duration_s=float(meta.get("duration") or 0.0),
                                 docket_date=discover.parse_docket_date(title), session=discover.parse_session(title))
        pipe.store.add_docket(docket.video_id, docket.title, docket.docket_date, docket.duration_s)
        return docket
    return discover.Docket(video_id=row["video_id"], title=row["title"], duration_s=row["duration_s"] or 0.0,
                           docket_date=row["docket_date"] or "", session="unknown")


def _print(vid: str, scored: list[dict]) -> None:
    print(f"\n{vid}: {len(scored)} scored case(s)")
    for c in scored:
        print(f"  {vid}:{int(round(c['start_s']))}  {int(c['start_s'])//60:3d}m-{int(c['end_s'])//60:3d}m  "
              f"{(c.get('defendant_name') or '?')[:34]:34s} {c.get('proceeding_type','')[:20]:20s} "
              f"score {c.get('total_score') or 0:5.1f} {'ELIGIBLE' if c.get('eligible') else 'no: ' + str(c.get('ineligible_reason'))[:50]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--case", nargs=2, type=float, metavar=("START_S", "END_S"),
                    help="score only this operator-bounded case (full-context scorer + safety gate)")
    ap.add_argument("--defendant", default="unknown")
    ap.add_argument("--cause", default="unknown")
    ap.add_argument("--charge", default="unknown")
    ap.add_argument("--type", default="other", help="proceeding_type")
    ap.add_argument("--outcome", default="unknown")
    ap.add_argument("--one-line", default="")
    a = ap.parse_args()

    vid = a.video_id
    pipe = Pipeline()
    docket = _docket(pipe, vid)
    if not a.case:
        scored = pipe.analyze_docket(docket)
        _print(vid, scored)
        pipe.close()
        return 0

    start_s, end_s = a.case
    work = pipe.work / vid
    work.mkdir(parents=True, exist_ok=True)
    transcript = get_transcript(
        vid, work,
        source=pipe.cfg.get("transcription.source", "auto_captions"),
        language=pipe.cfg.get("transcription.language", "en"),
        whisper_fallback=pipe.cfg.get("transcription.whisper_fallback", True),
        whisper_model=pipe.cfg.get("transcription.whisper_model", "medium"),
    )
    meta = {"title": docket.title, "docket_date": docket.docket_date, "url": docket.url}
    stage1 = analyze.stage1_view({
        "start_s": start_s, "end_s": end_s, "defendant_name": a.defendant, "cause_number": a.cause,
        "charge": a.charge, "proceeding_type": a.type, "outcome": a.outcome,
        "one_line": a.one_line or f"{a.defendant} - {a.type}", "extraction_confidence": "medium",
    })
    scored = pipe.analyzer.score(transcript, [stage1], meta, full_context=True)
    if not scored:
        print("scorer returned nothing")
        pipe.close()
        return 1
    case = scored[0]
    pipe.store.save_case(vid, case, case.get("rank"))
    (work / f"scored_case_{int(round(case['start_s']))}.json").write_text(
        json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
    _print(vid, scored)
    ed = case.get("editorial") or {}
    print(f"  editorial: decision={ed.get('decision')} money_moment_s={ed.get('money_moment_s')} "
          f"hook={str(case.get('hook_quote'))[:90]!r}")
    print(f"  safety: {case.get('safety')}")
    pipe.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
