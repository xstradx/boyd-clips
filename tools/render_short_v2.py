"""Render ONE case's short through the production SHORTS_EDITOR_V2 path.

Exactly `Pipeline._short_v2` — the transcript-only plan, the tile probe and
judge recognition, diarisation, the final plan, the pre-cut captions, the
per-segment focus render, loudness mastering and the render QC — without the
rest of `produce()`: no long-form render, no thumbnail, no packaging model
call, no publish, and no clip row written to the state DB.

    python tools/render_short_v2.py eWsve0icYUk:2284 --money-moment 2846 --quote "..."

Writes out/review/<date>_<video>_<start>_v2short/:
    short.mp4            the mastered short
    short_raw.mp4        the render before loudness mastering
    captions.ass         the burned-in cards
    short_plan.txt/json  the edit plan the render followed (beats, ranges,
                         focus, punch-ins, captions, QC gates, alternatives)
    render_qc.json       file-level QC + loudness
    manifest_v2short.json  everything above in one place, with the source
                         span, the overrides used and the output.short config
    tile_probe.jpg       the frame the judge-tile recognition looked at

`--money-moment` / `--quote` supply the BOYD_EDITORIAL_V2 money moment for a
case row scored before V2 (the stored rows for the 2026-09-06 eval cases
carry none); the values used are recorded in the manifest.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import render  # noqa: E402
from boydclips.config import SPEC_VERSION, load_config  # noqa: E402
from boydclips.pipeline import Pipeline, setup_logging  # noqa: E402
from boydclips.transcribe import get_transcript  # noqa: E402

log = logging.getLogger("boydclips.render_short_v2")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_key")
    ap.add_argument("--money-moment", type=float, help="supply/override editorial.money_moment_s")
    ap.add_argument("--quote", help="supply/override editorial.money_moment (quote text)")
    ap.add_argument("--title", help="short title to stamp (default: defendant name + review tag)")
    a = ap.parse_args()

    cfg = load_config()
    setup_logging(cfg, verbose=True)
    pipe = Pipeline(cfg)
    # No clip rows for a review render: the file and its manifest are the
    # record. save_clip would also collide with the case's existing rows.
    pipe.store.save_clip = lambda *args, **kwargs: None  # type: ignore[assignment]

    vid, start = a.case_key.split(":")
    case = pipe.store.get_case(a.case_key)
    if not case:
        print(f"no case row for {a.case_key}")
        return 1
    overrides = {}
    if a.money_moment is not None:
        case.setdefault("editorial", {})["money_moment_s"] = a.money_moment
        overrides["money_moment_s"] = a.money_moment
    if a.quote:
        case.setdefault("editorial", {})["money_moment"] = a.quote
        overrides["money_moment"] = a.quote

    work = pipe.work / vid
    transcript = get_transcript(
        vid, work,
        source=cfg.get("transcription.source", "auto_captions"),
        language=cfg.get("transcription.language", "en"),
        whisper_fallback=cfg.get("transcription.whisper_fallback", True),
        whisper_model=cfg.get("transcription.whisper_model", "medium"),
    )

    lf_cfg = cfg.require("output.longform")
    sh_cfg = cfg.require("output.short")
    pad_before = lf_cfg.get("pad_before_s", 4.0)
    pad_after = lf_cfg.get("pad_after_s", 3.0)
    windows = pipe.store.case_windows(vid, case["start_s"]) or [(case["start_s"], case["end_s"])]
    lf_start = max(0.0, windows[0][0] - pad_before)
    lf_end = windows[-1][1] + pad_after

    stamp = f"{date.today().isoformat()}_{vid}_{int(round(case['start_s']))}_v2short"
    review_dir = pipe.out / "review" / stamp
    review_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    log.info("download: section %.0f-%.0f (%.1f min)", lf_start, lf_end, (lf_end - lf_start) / 60)
    source, offset = render.download_section(vid, lf_start, lf_end, work / f"{a.case_key.replace(':', '_')}.mp4")
    log.info("download: %s (offset %.1f) in %.0fs", source.name, offset, time.time() - t0)

    crop = None
    bg_crop = None
    if sh_cfg.get("autocrop", True):
        crop = render.detect_content_crop(source)
        log.info("framing: %s", f"letterbox stripped -> {crop}" if crop else "no baked-in letterbox detected")
        bg_crop = crop or render.detect_content_crop(source, min_agreement=0.25)

    pkg = {"short_title": a.title or f"{case.get('defendant_name') or a.case_key} — SHORTS_EDITOR_V2 review render"}
    result: dict = {"case_key": a.case_key, "short": None}
    t1 = time.time()
    pipe._short_v2(source, offset, case, a.case_key, pkg, review_dir, sh_cfg, crop, bg_crop, transcript, result)
    log.info("short path finished in %.0fs", time.time() - t1)

    se = result.get("short_editor") or {}
    (review_dir / "render_qc.json").write_text(json.dumps({
        "ruleset": se.get("ruleset"), "ok": se.get("ok"), "refusal": se.get("refusal"),
        "render_qc": se.get("render_qc"), "loudness": se.get("loudness"),
        "tile_map": se.get("tile_map"), "total": se.get("total"), "scores": se.get("scores"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "spec_version": SPEC_VERSION,
        "kind": "v2short_review_render",
        "case_key": a.case_key,
        "video_id": vid,
        "case_span_s": [case["start_s"], case["end_s"]],
        "downloaded_span_s": [lf_start, lf_end],
        "source_file": str(source),
        "source_offset_s": offset,
        "overrides": overrides,
        "short_title": pkg["short_title"],
        "short_editor": se,
        "short": result.get("short"),
        "output_short_config": sh_cfg,
        "not_done": ["long-form", "thumbnail", "packaging model call", "publish", "state-db clip row"],
    }
    (review_dir / "manifest_v2short.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"review dir: {review_dir}")
    print(f"planner: {'OK' if se.get('ok') else 'REFUSED'} {se.get('total')}/100 {se.get('scores')}")
    if se.get("refusal"):
        print(f"refusal: {se['refusal']}")
    for g in se.get("render_qc") or []:
        print(f"  render_qc {g['gate']:<24} {'ok  ' if g['ok'] else 'FAIL'} {g['detail']}")
    if se.get("loudness"):
        print(f"  loudness {se['loudness']}")
    sh = result.get("short")
    if sh:
        print(f"short: {sh['file_path']} ({sh['duration_s']:.2f}s)")
    pipe.close()
    return 0 if sh else 2


if __name__ == "__main__":
    sys.exit(main())
