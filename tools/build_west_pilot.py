"""Build the first local Raquel West pilot from a court-owned source.

This is an explicit review build, not a daily-production route. It does not
upload, publish, schedule, call a model, or promote Raquel West's judge profile.
The fixed source ranges are transcript-backed and recorded in the receipt.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from boydclips import captions, render
from boydclips.config import ROOT, load_config
from boydclips.transcribe import Transcript


VIDEO_ID = "R14bev_wRBc"
SOURCE_DATE = "2026-09-18"
SOURCE_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
SOURCE = ROOT / "work" / VIDEO_ID / f"{VIDEO_ID}_full.mp4"
TRANSCRIPT = ROOT / "work" / VIDEO_ID / f"{VIDEO_ID}.transcript.json"
OUT = ROOT / "out" / "review" / f"{SOURCE_DATE}_{VIDEO_ID}_west_pilot"

LONGFORM_RANGE = (4228.0, 5082.0)
SHORT_SEGMENTS = [
    render.Segment(4995.20, 5001.20),  # declared teaser: immediate 12-year sentence
    render.Segment(4925.84, 4946.70),  # lies and responsibility for three years
    render.Segment(4963.58, 4970.90),  # she says he had to know after the airbag fired
    render.Segment(4975.36, 4979.90),  # complete question; omit the garbled restart
    render.Segment(4987.28, 5001.20),  # verdict and complete sentence, in source order
]

LONGFORM_TITLE = "Judge Raquel West Gives 12 Years After Three Years of Lies"
SHORT_TITLE = "Judge Raquel West Says Three Years of Lies Changed the Sentence"
THUMBNAIL_TEXT = "YOU HAD TO HAVE KNOWN"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _caption_stream(transcript: Transcript) -> tuple[list[dict], list[int]]:
    stream: list[dict] = []
    hard_breaks: list[int] = []
    elapsed = 0.0
    occurrence = 0
    for segment_index, segment in enumerate(SHORT_SEGMENTS):
        if segment_index:
            hard_breaks.append(len(stream))
        for source_index, word in enumerate(transcript.words):
            if segment.start_s <= word.t < segment.end_s:
                stream.append(
                    {
                        "i": occurrence,
                        "src": [source_index],
                        "src_t": round(word.t, 3),
                        "t": round(elapsed + word.t - segment.start_s, 3),
                        "w": word.w,
                        "speaker": "judge",
                    }
                )
                occurrence += 1
        elapsed += segment.duration
    return stream, hard_breaks


def _thumbnail(frame_path: Path, out_path: Path) -> None:
    source = Image.open(frame_path).convert("RGB")
    # Source is a 2x2 1280x720 Zoom layout. The top-left tile is Judge West;
    # the top-right tile is the courtroom with defendant and counsel.
    judge = source.crop((0, 0, 320, 360)).resize((640, 720), Image.Resampling.LANCZOS)
    # Tight defendant crop removes the gallery and keeps the thumbnail at two
    # true subjects instead of turning the courtroom audience into face clutter.
    courtroom = source.crop((970, 110, 1170, 335)).resize((640, 720), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1280, 720))
    canvas.paste(judge, (0, 0))
    canvas.paste(courtroom, (640, 0))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 470, 1280, 720), fill=(0, 0, 0, 180))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(canvas)
    font_path = ROOT / "assets" / "fonts" / "Anton-Regular.ttf"
    font = ImageFont.truetype(str(font_path), 116)
    lines = (("YOU HAD TO", "white"), ("HAVE KNOWN", "#FFD23F"))
    y = 475
    for text, color in lines:
        box = draw.textbbox((0, 0), text, font=font, stroke_width=7)
        width = box[2] - box[0]
        x = (1280 - width) // 2
        draw.text((x, y), text, font=font, fill=color, stroke_width=7, stroke_fill="black")
        y += 112
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=94, subsampling=0)


def _extract_frame(at_s: float, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{at_s:.3f}", "-i", str(SOURCE), "-frames:v", "1", str(out_path),
        ],
        check=True,
    )


def main() -> None:
    if not SOURCE.is_file() or not TRANSCRIPT.is_file():
        raise SystemExit("source video and transcript must already exist")
    OUT.mkdir(parents=True, exist_ok=True)
    transcript = Transcript.from_json(TRANSCRIPT.read_text(encoding="utf-8"))
    cfg = load_config()

    stream, hard_breaks = _caption_stream(transcript)
    short_cfg = dict(cfg.require("output.short"))
    cap_cfg = dict(short_cfg["captions"])
    cap_cfg.update(cap_cfg.pop("rail"))
    cap_result = captions.plan_captions(stream, cap_cfg, hard_breaks, None)
    ass_path = OUT / "west_short.ass"
    short_duration = sum(segment.duration for segment in SHORT_SEGMENTS)
    render.build_rail_ass(cap_result["cards"], cap_cfg, short_duration, ass_path)

    short_cfg["vertical_mode"] = "duo_fill"
    short_path = OUT / "west_short.mp4"
    render.render_short(
        SOURCE,
        0.0,
        SHORT_SEGMENTS,
        short_cfg,
        ass_path,
        short_path,
        tile_crops=("crop=405:360:757:0", "crop=405:360:0:0"),
        cta=None,
    )

    long_cfg = dict(cfg.require("output.longform"))
    long_path = OUT / "west_longform.mp4"
    if not long_path.is_file():
        render.render_longform(
            SOURCE,
            0.0,
            [render.Segment(*LONGFORM_RANGE)],
            long_cfg,
            long_path,
            intro=None,
            coldopen=None,
        )

    frame = OUT / "thumbnail_source.png"
    thumb = OUT / "west_thumbnail.jpg"
    _extract_frame(4935.0, frame)
    _thumbnail(frame, thumb)

    plan = {
        "status": "LOCAL_PILOT_HOLD",
        "judge_id": "raquel_west",
        "judge_name": "Judge Raquel West",
        "court": "252nd District Court, Jefferson County, Texas",
        "source": {"video_id": VIDEO_ID, "url": SOURCE_URL, "date": SOURCE_DATE, "owner": "court"},
        "longform": {"range": list(LONGFORM_RANGE), "title": LONGFORM_TITLE},
        "short": {
            "segments": [[segment.start_s, segment.end_s] for segment in SHORT_SEGMENTS],
            "duration_s": round(short_duration, 3),
            "title": SHORT_TITLE,
            "teaser_repeats_in_chronological_position": True,
        },
        "thumbnail": {"text": THUMBNAIL_TEXT, "source_frame_s": 4935.0},
        "holds": [
            "No upload, schedule or publication authorization.",
            "Raquel West identity reference and profile-aware visual gates are not approved.",
            "The long-form pilot has no branded intro or cold open.",
            "Whole-video listening and editorial approval remain required.",
        ],
    }
    (OUT / "pilot_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    description = (
        "After a jury found the defendant guilty of collision involving death, "
        "Judge Raquel West heard victim-impact testimony and arguments at punishment.\n\n"
        "Judge West said the lies and continuing lack of responsibility made the case "
        "more serious before imposing a 12-year sentence. The video preserves the court's "
        "legal posture: the guilty verdict came from the jury, and sentencing came from the judge.\n\n"
        "Court footage: 252nd District Court, Jefferson County, Texas."
    )
    metadata = (
        f"LONG-FORM TITLE\n{LONGFORM_TITLE}\n\nSHORT TITLE\n{SHORT_TITLE}\n\n"
        f"THUMBNAIL\n{THUMBNAIL_TEXT}\n\nDESCRIPTION\n{description}\n\n"
        "TAGS\nJudge Raquel West, 252nd District Court, Jefferson County court, "
        "collision involving death, sentencing hearing, Texas courtroom\n"
    )
    (OUT / "METADATA.txt").write_text(metadata, encoding="utf-8")

    artifacts = {path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
                 for path in (long_path, short_path, thumb, ass_path, TRANSCRIPT)}
    receipt = {
        "status": "LOCAL_PILOT_HOLD",
        "artifacts": artifacts,
        "technical_claim": "Files were rendered locally; decoding and visual checks run separately.",
        "editorial_claim": "Not approved.",
        "delivery_claim": "Not delivered to phone.",
        "platform_claim": "Not uploaded or published.",
    }
    (OUT / "DELIVERY.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "short_s": short_duration, "artifacts": artifacts}, indent=2))


if __name__ == "__main__":
    main()
