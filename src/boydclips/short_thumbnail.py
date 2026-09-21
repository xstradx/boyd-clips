"""Build a 9:16 Short thumbnail from authentic, unaltered source frames."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _configured_direction_model() -> str:
    """The model this project is configured to direct a Short thumbnail.

    2026-09-16: this used to default to the literal "gpt-5.6-sol", a brain this
    PC can no longer reach. The record then claimed Sol even when the configured
    brain produced the recipe, and readiness refused the honest record.
    """
    from .config import load_config

    return str(load_config().require("packaging.thumbnail.direct.model"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(top_frame: Path, bottom_frame: Path, text: str, output: Path, *,
          short_path: Path, top_crop: tuple[int, int, int, int], bottom_crop: tuple[int, int, int, int],
          direction_model: str | None = None) -> dict:
    """Stack two real frames and add a seam-safe hook without altering faces."""
    direction_model = direction_model or _configured_direction_model()
    if not 2 <= len(text.split()) <= 5:
        raise ValueError("Short thumbnail hook must be 2-5 words")
    top_src = Image.open(top_frame).convert("RGB")
    bottom_src = Image.open(bottom_frame).convert("RGB")
    if top_src.size != (1080, 1920) or bottom_src.size != (1080, 1920):
        raise ValueError("vertical thumbnail source frames must decode at 1080x1920")
    # The supplied frames are production 9:16 plates. Crop away the source
    # station lower-third at the bottom of the upper tile, then restore 50/50.
    # 720x640 is the same 9:8 tile ratio as 1080x960. It removes unused
    # ceiling and most of counsel while keeping Perry's real expression.
    for box in (top_crop, bottom_crop):
        if len(box) != 4 or not (0 <= box[0] < box[2] <= 1080 and 0 <= box[1] < box[3] <= 1920):
            raise ValueError(f"invalid approved vertical thumbnail crop: {box}")
        if abs(((box[2]-box[0])/(box[3]-box[1])) - 1.125) > 0.03:
            raise ValueError("approved crop must match the 9:8 tile ratio")
    top = top_src.crop(top_crop).resize((1080, 960), Image.Resampling.LANCZOS)
    bottom = bottom_src.crop(bottom_crop).resize((1080, 960), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1080, 1920))
    canvas.paste(top, (0, 0)); canvas.paste(bottom, (0, 960))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 842, 1080, 1078), fill=(7, 9, 13, 188))
    font_path = Path(__file__).resolve().parents[2] / "assets/fonts/Anton-Regular.ttf"
    font = ImageFont.truetype(str(font_path), 126)
    label = text.upper()
    box = draw.textbbox((0, 0), label, font=font, stroke_width=7)
    if box[2] - box[0] > 960:
        raise ValueError("Short thumbnail hook exceeds the phone-safe width")
    x = (1080 - (box[2] - box[0])) // 2
    draw.text((x, 876), label, font=font, fill="#FFD23F", stroke_width=7, stroke_fill="#000000")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.stem + ".building.jpg")
    canvas.save(temp, quality=95, subsampling=0)
    temp.replace(output)
    record = {
        "file_path": str(output.resolve()), "sha256": sha256(output), "width": 1080, "height": 1920,
        "hook_text": text, "direction_model": direction_model,
        "source_frames": [{"path": str(top_frame.resolve()), "sha256": sha256(top_frame)},
                          {"path": str(bottom_frame.resolve()), "sha256": sha256(bottom_frame)}],
        "short_path": str(short_path.resolve()), "short_sha256": sha256(short_path),
        "approved_crops": {"top": list(top_crop), "bottom": list(bottom_crop)},
        "visual_review": {"full_size": "pending", "phone_size": "pending", "faces_covered": None,
                          "station_burn_in": None},
    }
    output.with_suffix(".json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
