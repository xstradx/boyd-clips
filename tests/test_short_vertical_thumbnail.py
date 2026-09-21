import json
from pathlib import Path

import pytest
from PIL import Image

from boydclips import readiness, short_thumbnail
from boydclips.config import load_config


def configured_direction_model() -> str:
    """2026-09-16: read the configured model instead of pinning "gpt-5.6-sol",
    which is unreachable from this PC. A bundle naming anything else still
    refuses."""
    return str(load_config().require("packaging.thumbnail.direct.model"))


VALID_TOP_CROP = (180, 120, 900, 760)
VALID_BOTTOM_CROP = (180, 980, 900, 1620)


def source_frame(path: Path, size=(1080, 1920), color="navy") -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def build_thumbnail(tmp_path: Path, text="READ THE EVIDENCE"):
    top = source_frame(tmp_path / "top.jpg", color="navy")
    bottom = source_frame(tmp_path / "bottom.jpg", color="maroon")
    short = tmp_path / "short.mp4"
    short.write_bytes(b"current short bytes")
    output = tmp_path / "vertical.jpg"
    record = short_thumbnail.build(
        top,
        bottom,
        text,
        output,
        short_path=short,
        top_crop=VALID_TOP_CROP,
        bottom_crop=VALID_BOTTOM_CROP,
    )
    return short, output, record


def readiness_short(short: Path, record: dict) -> dict:
    return {
        "file_path": str(short),
        "vertical_thumbnail_required": True,
        "vertical_thumbnail": record,
    }


def test_builder_decodes_to_9x16_with_valid_geometry_and_phone_safe_text(tmp_path):
    _short, output, record = build_thumbnail(tmp_path)
    with Image.open(output) as image:
        assert image.size == (1080, 1920)
    assert record["width"] == 1080 and record["height"] == 1920
    assert record["hook_text"] == "READ THE EVIDENCE"
    assert record["approved_crops"] == {
        "top": list(VALID_TOP_CROP),
        "bottom": list(VALID_BOTTOM_CROP),
    }
    saved = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert saved["sha256"] == readiness.sha256_file(output)


def test_builder_marks_visual_review_pending_and_readiness_does_not_auto_pass_it(tmp_path):
    short, _output, record = build_thumbnail(tmp_path)
    assert record["visual_review"] == {
        "full_size": "pending",
        "phone_size": "pending",
        "faces_covered": None,
        "station_burn_in": None,
    }
    with pytest.raises(readiness.ReadinessError, match="visual review"):
        readiness._require_vertical_short_thumbnail(readiness_short(short, record))

    record["visual_review"]["full_size"] = "passed"
    record["visual_review"]["phone_size"] = "passed"
    readiness._require_vertical_short_thumbnail(readiness_short(short, record))


def test_readiness_requires_actual_decoded_1080x1920_dimensions(tmp_path):
    short = tmp_path / "short.mp4"
    short.write_bytes(b"short")
    landscape = source_frame(tmp_path / "landscape.jpg", size=(1920, 1080))
    record = {
        "file_path": str(landscape),
        "sha256": readiness.sha256_file(landscape),
        "short_sha256": readiness.sha256_file(short),
        "direction_model": configured_direction_model(),
        "visual_review": {"full_size": "passed", "phone_size": "passed"},
    }
    with pytest.raises(readiness.ReadinessError, match="decode at 1080x1920"):
        readiness._require_vertical_short_thumbnail(readiness_short(short, record))


@pytest.mark.parametrize(
    "top_crop, message",
    [
        ((-1, 120, 900, 760), "invalid approved"),
        ((180, 120, 900, 900), "9:8 tile ratio"),
    ],
)
def test_builder_rejects_invalid_or_wrong_ratio_crop_geometry(tmp_path, top_crop, message):
    top = source_frame(tmp_path / "top.jpg")
    bottom = source_frame(tmp_path / "bottom.jpg")
    short = tmp_path / "short.mp4"
    short.write_bytes(b"short")
    with pytest.raises(ValueError, match=message):
        short_thumbnail.build(
            top,
            bottom,
            "READ THE EVIDENCE",
            tmp_path / "out.jpg",
            short_path=short,
            top_crop=top_crop,
            bottom_crop=VALID_BOTTOM_CROP,
        )


def test_builder_rejects_landscape_source_frames_and_oversized_hook(tmp_path):
    landscape = source_frame(tmp_path / "top.jpg", size=(1920, 1080))
    bottom = source_frame(tmp_path / "bottom.jpg")
    short = tmp_path / "short.mp4"
    short.write_bytes(b"short")
    kwargs = {
        "short_path": short,
        "top_crop": VALID_TOP_CROP,
        "bottom_crop": VALID_BOTTOM_CROP,
    }
    with pytest.raises(ValueError, match="source frames must decode at 1080x1920"):
        short_thumbnail.build(
            landscape, bottom, "READ THE EVIDENCE", tmp_path / "landscape-output.jpg", **kwargs
        )

    top = source_frame(tmp_path / "top-vertical.jpg")
    with pytest.raises(ValueError, match="phone-safe width"):
        short_thumbnail.build(
            top,
            bottom,
            "SUPERCALIFRAGILISTICEXPIALIDOCIOUS WORDS",
            tmp_path / "wide-output.jpg",
            **kwargs,
        )


def test_pipeline_refuses_a_vertical_directive_from_another_model(tmp_path):
    """2026-09-16: the directive gate follows the configured brain.

    It used to compare against the literal "gpt-5.6-sol", so a recipe the
    configured brain actually produced was refused. The negative control below
    proves another model's name still refuses.
    """
    from boydclips.pipeline import validate_vertical_directive

    configured = configured_direction_model()
    recipe = {
        "hook_text": "ASKED FOR HELP?",
        "top_output_s": 36.5,
        "bottom_output_s": 36.5,
        "top_crop": [180, 60, 900, 700],
        "bottom_crop": [330, 1095, 1050, 1735],
        "direction_model": configured,
    }
    assert validate_vertical_directive(recipe, configured)["direction_model"] == configured

    other = "legacy-model" if configured != "legacy-model" else "gpt-5.6-sol"
    with pytest.raises(ValueError, match="not the configured"):
        validate_vertical_directive(dict(recipe, direction_model=other), configured)
    with pytest.raises(ValueError, match="missing="):
        validate_vertical_directive({"hook_text": "ASKED FOR HELP?"}, configured)


def test_builder_records_the_configured_model_when_none_is_given(tmp_path):
    """The record must name the configured brain, not a hard-coded Sol."""
    _short, _output, record = build_thumbnail(tmp_path)
    assert record["direction_model"] == configured_direction_model()
