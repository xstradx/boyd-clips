"""Rebuild the saved Perry Short without model, thumbnail, or download stages.

The reusable intro recipe is data-driven in ``INTRO_SPEC``: a verbatim source
teaser, a brief measured freeze/callout, moving local source shots, then
the strongest saved source exchange.  Change the spec for another case; no
editorial selection or external generation happens here.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from boydclips import captions, cta, layout, render, narrated_short_intro
from boydclips.config import load_config
from boydclips.render import Segment
from boydclips.transcribe import get_transcript

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "out" / "review" / "2026-04-30_oL6lV6gCyOc_736"
HOTFIX = ROOT / ".unlazy" / "short-hotfix-2026-09-12"
SOURCE = ROOT / "work" / "oL6lV6gCyOc" / "oL6lV6gCyOc_736_712-1639.mp4"
OFFSET = 712.0
VOICE = ROOT / "assets/narration/user_2026-09-12_selected_v3/perry_reads_the_evidence_selected_v3.mp3"
RISER = ROOT / "assets/sfx/user_2P6QerHOCGE/riser.wav"
DING = ROOT / "assets/sfx/user_2P6QerHOCGE/ding.wav"
WHOOSH = ROOT / "assets/sfx/user_2P6QerHOCGE/whoosh.wav"
INTRO_SPEC = {
    "video_id": "oL6lV6gCyOc",
    "source_hooks": [
        {"source": [1338.02, 1340.60], "speaker": "boyd",
         "text": "This is the bracelet. I need you to pawn it."},
        {"source": [1353.0, 1356.84], "speaker": "defendant",
         "text": "Like I said, when I made them choices back then, it ain't nothin' like now."},
    ],
    "source_quote": [1353.0, 1356.84],
    "quote": "Like I said, when I made them choices back then, it ain't nothin' like now.",
    "buildup_ends_at_quote_seam": True,
    "voice_text": "This woman thought two years would make Judge Boyd go easy on her—then Boyd reads the evidence.",
    "voice_asset": str(VOICE),
    "voice_shots": [
        {"source_start_s": 1357.0, "voice_end_s": 1.38, "crop": "220:244:105:280"},
        {"source_start_s": 1362.7, "voice_end_s": 3.66, "crop": "240:266:100:236"},
        {"source_start_s": 1368.0, "voice_end_s": 5.407313, "crop": "314:348:908:186"},
    ],
    "voice_caption_cues": [[0.0, 1.38, r"This woman thought\Ntwo years"],
                            [1.38, 3.66, r"would make Judge Boyd\Ngo easy on her"],
                            [3.66, 5.407313, r"then Boyd reads\Nthe evidence."]],
    "freeze_circle": {
        "source_frame_s": 1356.80,
        "duration_s": 0.666667,
        "crop": "220:244:105:280",
        "circle_box": [145, 320, 890, 1290],
        "circle_start_s": 0.10,
        "circle_complete_s": 0.333333,
        "ding_at_s": 0.366667,
        "ding_path": str(DING),
    },
    "transition_sfx": {"path": str(WHOOSH), "gain_db": -24.0, "cue": "narration_body_seam"},
    "body_segments": [[1370.0, 1378.64], [1378.64, 1380.4], [1380.4, 1383.96], [1383.96, 1396.36],
                      [1396.36, 1398.72], [1398.72, 1402.28], [1402.28, 1405.2]],
}


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError("command failed\n" + "\n".join(proc.stderr.splitlines()[-20:]))


def stream_for(words, ranges, speaker_by_index, forced_speaker=None):
    out, elapsed = [], 0.0
    for start, end in ranges:
        for i, word in enumerate(words):
            if start <= float(word.t) < end and word.w.strip():
                out.append({"i": i, "t": round(elapsed + float(word.t) - start, 3), "w": word.w,
                            "speaker": forced_speaker or speaker_by_index.get(i)})
        elapsed += end - start
    return out


def main() -> None:
    HOTFIX.mkdir(parents=True, exist_ok=True)
    if not all(path.is_file() for path in (SOURCE, VOICE, RISER, DING, WHOOSH)):
        raise FileNotFoundError("original source, selected narration, riser, ding, and whoosh are required")
    manifest = json.loads((REVIEW / "manifest.json").read_text(encoding="utf-8"))
    cfg = load_config()
    sh_cfg = dict(cfg.require("output.short"))
    # Saved V2 composition already contains measured top/bottom crop windows.
    # The daily pipeline sets this before calling render_short; the rebuild must
    # do the same or render_short falls back to a letterboxed auto layout.
    sh_cfg["vertical_mode"] = "duo_fill"
    cap_cfg = dict(sh_cfg["captions"])
    cap_cfg.update(dict(cap_cfg.pop("rail", {}) or {}))
    cap_cfg = captions.resolve_style(cap_cfg)
    transcript = get_transcript("oL6lV6gCyOc", ROOT / "work" / "oL6lV6gCyOc")
    old_stream = manifest["outputs"]["short"]["edit_plan"]["word_stream"]
    speakers = {int(x["i"]): x.get("speaker") for x in old_stream}
    speakers.update({i: "boyd" for i in range(1671, 1682)})
    speakers.update({i: "defendant" for i in range(1682, 1688)})
    speakers.update({i: "boyd" for i in range(1688, 1700)})
    speakers.update({i: "defendant" for i in range(1700, 1716)})
    comp = manifest["short_editor"]["composition"]

    previous = REVIEW / "short_before_2026-09-12_hotfix.mp4"
    if not previous.exists():
        shutil.copy2(REVIEW / "short.mp4", previous)

    quote_ranges = [INTRO_SPEC["source_quote"]]
    quote_stream = stream_for(transcript.words, quote_ranges, speakers, "defendant")
    qres = captions.plan_captions(quote_stream, cap_cfg)
    quote_ass = HOTFIX / "quote_captions.ass"
    render.build_rail_ass(qres["cards"], cap_cfg, INTRO_SPEC["source_quote"][1]-INTRO_SPEC["source_quote"][0], quote_ass)
    base = comp["base"]
    # Crop just above the court's burned-in lower-third while preserving the
    # same Perry framing ratio. Applies to quote and every body window.
    clean_defendant_crop = "crop=362:322:37:186"
    base_windows = [(clean_defendant_crop, base["bottom"]["crop"])]
    punched_window = (clean_defendant_crop, comp["segments"][0]["bottom"]["crop"])
    tile_filters = (render.camera_grade_filter(sh_cfg.get("color") or {}, "defendant"),
                    render.camera_grade_filter(sh_cfg.get("color") or {}, "boyd"))
    tile_post = (render.camera_clarity_filter(sh_cfg["clarity"], "defendant"),
                 render.camera_clarity_filter(sh_cfg["clarity"], "boyd"))
    boyd_hook_range = INTRO_SPEC["source_hooks"][0]["source"]
    boyd_hook_stream = stream_for(transcript.words, [boyd_hook_range], speakers, "boyd")
    boyd_hook_caps = captions.plan_captions(boyd_hook_stream, cap_cfg)
    boyd_hook_ass = HOTFIX / "boyd_hook_captions.ass"
    render.build_rail_ass(boyd_hook_caps["cards"], cap_cfg, boyd_hook_range[1] - boyd_hook_range[0], boyd_hook_ass)
    boyd_hook = HOTFIX / "boyd_hook_v6.mp4"
    render.render_short(SOURCE, OFFSET, [Segment(*boyd_hook_range)], sh_cfg, boyd_hook_ass, boyd_hook,
                        tile_crops=punched_window, duo_punch=[punched_window],
                        duo_punch_filters=tile_filters, duo_punch_post=tile_post)
    boyd_hook_norm = HOTFIX / "boyd_hook_v6_48k.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(boyd_hook), "-c:v", "copy", "-c:a", "aac",
         "-b:a", "160k", "-ar", "48000", "-ac", "2", str(boyd_hook_norm)])
    boyd_hook_duration = render.probe_duration(boyd_hook_norm)
    quote_base = HOTFIX / "quote_base.mp4"
    render.render_short(SOURCE, OFFSET, [Segment(*INTRO_SPEC["source_quote"])], sh_cfg, quote_ass, quote_base,
                        tile_crops=base_windows[0], duo_punch=base_windows,
                        duo_punch_filters=tile_filters, duo_punch_post=tile_post)
    qdur = render.probe_duration(quote_base)
    quote = HOTFIX / "quote.mp4"
    riser_delay = max(0, round((qdur - 1.79) * 1000))
    run(["ffmpeg", "-y", "-v", "error", "-i", str(quote_base), "-i", str(RISER),
         "-filter_complex", f"[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];"
         f"[1:a]volume=0.18,adelay={riser_delay}|{riser_delay}[rise];"
         "[a0][rise]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(quote)])

    voice_visual = HOTFIX / "voice_visual.mp4"
    voice_spec = narrated_short_intro.NarratedIntroSpec(
        voice_path=VOICE, text=INTRO_SPEC["voice_text"],
        shots=tuple(narrated_short_intro.Shot(**row) for row in INTRO_SPEC["voice_shots"]),
        caption_cues=tuple(tuple(row) for row in INTRO_SPEC["voice_caption_cues"]),
        freeze_circle=narrated_short_intro.FreezeCircleCue(
            source_frame_s=INTRO_SPEC["freeze_circle"]["source_frame_s"],
            duration_s=INTRO_SPEC["freeze_circle"]["duration_s"],
            crop=INTRO_SPEC["freeze_circle"]["crop"],
            circle_box=tuple(INTRO_SPEC["freeze_circle"]["circle_box"]),
            circle_start_s=INTRO_SPEC["freeze_circle"]["circle_start_s"],
            circle_complete_s=INTRO_SPEC["freeze_circle"]["circle_complete_s"],
            ding_path=DING,
            ding_at_s=INTRO_SPEC["freeze_circle"]["ding_at_s"],
        ),
        transition_sfx_path=WHOOSH,
        transition_sfx_gain_db=INTRO_SPEC["transition_sfx"]["gain_db"],
    )
    voice_rec = narrated_short_intro.render_moving_broll(
        SOURCE, OFFSET, voice_spec, voice_visual, sh_cfg, HOTFIX / "voice_broll_evidence.json")
    vdur = voice_rec["duration_s"]

    body_ranges = INTRO_SPEC["body_segments"]
    body_segments = [Segment(*x) for x in body_ranges]
    body_stream = stream_for(transcript.words, body_ranges, speakers)
    hard_breaks = []
    for start, end in body_ranges[1:]:
        first = next((i for i, word in enumerate(transcript.words)
                      if start <= float(word.t) < end and word.w.strip()), None)
        if first is not None:
            hard_breaks.append(first)
    bres = captions.plan_captions(body_stream, cap_cfg, hard_breaks=hard_breaks)
    body_ass = HOTFIX / "body_captions.ass"
    bdur = sum(b-a for a,b in body_ranges)
    render.build_rail_ass(bres["cards"], cap_cfg, bdur, body_ass)
    base_window = (clean_defendant_crop, base["bottom"]["crop"])
    # Editorially motivated Boyd emphasis: hook, contradiction, final $20
    # correction. Base framing on the connective defendant response.
    windows = [punched_window, base_window, punched_window, punched_window, base_window, punched_window, base_window]
    wm_box = layout.watermark_box(sh_cfg, 119.0, 47.1)
    cap_box = layout.caption_box(cap_cfg, sh_cfg)
    place = cta.plan_cta(sh_cfg["cta"], bdur, comp, cap_box, wm_box, None, 30)
    body_norm = HOTFIX / "body_v5_48k.mp4"
    if not body_norm.is_file():
        cta_rec = cta.build_assets(place, sh_cfg["cta"], HOTFIX / "cta_v5", 30, SOURCE, OFFSET, body_segments)
        body = HOTFIX / "body_v5.mp4"
        render.render_short(SOURCE, OFFSET, body_segments, sh_cfg, body_ass, body,
                            tile_crops=windows[0], duo_punch=windows,
                            duo_punch_filters=tile_filters, duo_punch_post=tile_post, cta=cta_rec)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(body), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-ar", "48000", "-ac", "2", str(body_norm)])

    concat = HOTFIX / "concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in (boyd_hook_norm, quote, voice_visual, body_norm)) + "\n", encoding="utf-8")
    concat_video = HOTFIX / "v6_concat_before_whoosh.mp4"
    final = REVIEW / "perry_short_review_v6_2026-09-12.mp4"
    title = str(manifest["outputs"]["short"].get("title") or "")
    tags = ", ".join(manifest["outputs"]["longform"].get("tags") or [])
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
         "-metadata", f"title={title}", "-metadata", f"comment={title}", "-metadata", f"keywords={tags}",
         "-movflags", "+faststart", str(concat_video)])
    handoff = narrated_short_intro.mix_transition_sfx(
        concat_video, final, WHOOSH, boyd_hook_duration + qdur + vdur, INTRO_SPEC["transition_sfx"]["gain_db"])
    evidence = {
        "intro_spec": INTRO_SPEC, "caption_preset": cap_cfg["preset"],
        "source_hook_cards": [{"source": boyd_hook_range, "speaker": "boyd", "cards": boyd_hook_caps["cards"]},
                              {"source": INTRO_SPEC["source_quote"], "speaker": "defendant", "cards": qres["cards"]}],
        "quote_cards": qres["cards"],
        "body_cards": bres["cards"], "body_caption_hard_breaks": bres["hard_breaks"],
        "cta": place.as_dict(), "watermark_opacity": sh_cfg["watermark_opacity"],
        "encode": sh_cfg["encode"], "parts_s": {"boyd_hook": boyd_hook_duration, "quote": qdur, "voice": vdur, "body": render.probe_duration(body_norm)},
        "sfx_timeline": {"riser_ends_s": boyd_hook_duration + qdur,
                         "circle_complete_s": boyd_hook_duration + qdur + 0.333333,
                         "ding_at_s": boyd_hook_duration + qdur + 0.366667, "handoff": handoff},
        "output": str(final), "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
    }
    (HOTFIX / "render_evidence_v6.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(final)


if __name__ == "__main__":
    main()
