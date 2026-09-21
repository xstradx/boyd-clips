from pathlib import Path
from types import SimpleNamespace
import hashlib

import pytest

from boydclips import pipeline
from boydclips.narrated_short_intro import FreezeCircleCue, Shot


def test_competitor_match_path_has_no_narration_local_dependency():
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = SimpleNamespace(get=lambda _key, default=None: default)
    # Non-empty leads enters the real competitor branch. With no candidates it
    # must return without touching Short render locals such as source/body_path.
    pipe._attach_competitor_matches([], [(object(), object())])


def test_approved_narration_helper_consumes_local_spec_and_records_voice_hash(tmp_path, monkeypatch):
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = SimpleNamespace(root=tmp_path)
    voice = tmp_path / "voice.mp3"; voice.write_bytes(b"approved voice")
    source = tmp_path / "source.mp4"; source.write_bytes(b"source")
    ding = tmp_path / "ding.wav"; ding.write_bytes(b"ding")
    whoosh = tmp_path / "whoosh.wav"; whoosh.write_bytes(b"whoosh")
    seen = {}

    def fake_render(src, offset, spec, target, cfg, evidence):
        seen.update(src=src, offset=offset, spec=spec, target=target, evidence=evidence)
        return {"output": str(target), "duration_s": 5.0, "moving_source": True}

    monkeypatch.setattr(pipeline.narrated_short_intro, "render_moving_broll", fake_render)
    directive = {
        "voice_path": "voice.mp3",
        "text": "approved words",
        "shots": [{"source_start_s": 12.0, "voice_end_s": 5.0, "crop": "720:640:0:0"}],
        "caption_cues": [[0.0, 5.0, "approved words"]],
        "narrator_label": "",
        "freeze_circle": {
            "source_frame_s": 11.0,
            "duration_s": 0.6,
            "crop": "720:640:0:0",
            "circle_box": [330, 430, 760, 1220],
            "circle_start_s": 0.08,
            "circle_complete_s": 0.35,
            "ding_path": "ding.wav",
            "ding_at_s": 0.36,
        },
        "transition_sfx_path": "whoosh.wav",
        "transition_sfx_gain_db": -24.0,
    }
    target, record = pipe._render_approved_narrated_intro(source, 10.0, directive, tmp_path, {})
    assert target == tmp_path / "approved_narrated_intro.mp4"
    spec = seen["spec"]
    assert spec.voice_path == voice and seen["offset"] == 10.0
    assert spec.shots == (Shot(12.0, 5.0, "720:640:0:0"),)
    assert spec.caption_cues == ((0.0, 5.0, "approved words"),)
    assert spec.narrator_label == ""
    assert isinstance(spec.freeze_circle, FreezeCircleCue)
    assert spec.freeze_circle.circle_box == (330, 430, 760, 1220)
    assert spec.freeze_circle.ding_path == ding
    assert spec.transition_sfx_path == whoosh
    assert spec.transition_sfx_gain_db == -24.0
    assert record["voice_sha256"] == pipeline.readiness.sha256_file(voice)


def test_approved_narration_helper_preserves_all_ordered_source_hooks(tmp_path, monkeypatch):
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = SimpleNamespace(root=tmp_path)
    voice = tmp_path / "voice.mp3"; voice.write_bytes(b"voice")
    source = tmp_path / "source.mp4"; source.write_bytes(b"source")
    hooks = []
    for index, (start, end, text) in enumerate(((20.0, 22.0, "First complete line."),
                                                (30.0, 32.0, "Second complete line."))):
        path = tmp_path / f"hook-{index}.mp4"; path.write_bytes(f"hook-{index}".encode())
        hooks.append({"path": path.name, "source_start_s": start, "source_end_s": end,
                      "text": text, "speaker": "boyd" if index == 0 else "defendant",
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    monkeypatch.setattr(pipeline.render, "probe_duration", lambda _path: 2.0)
    monkeypatch.setattr(pipeline.narrated_short_intro, "render_moving_broll",
                        lambda *_args: {"duration_s": 5.0, "moving_source": True})
    calls = []
    monkeypatch.setattr(pipeline.subprocess, "run", lambda cmd, check: calls.append(cmd))
    directive = {"voice_path": "voice.mp3", "text": "approved words",
                 "shots": [{"source_start_s": 12.0, "voice_end_s": 5.0, "crop": "720:640:0:0"}],
                 "caption_cues": [[0.0, 5.0, "approved words"]], "source_hooks": hooks}
    _target, record = pipe._render_approved_narrated_intro(source, 10.0, directive, tmp_path, {})
    assert [row["text"] for row in record["source_hooks"]] == ["First complete line.", "Second complete line."]
    assert [row["source_start_s"] for row in record["source_hooks"]] == [20.0, 30.0]
    assert len(calls) == 2 and all("48000" in cmd for cmd in calls)


@pytest.mark.parametrize("missing", ["voice_path", "text", "shots", "caption_cues"])
def test_approved_narration_helper_rejects_missing_required_directive_fields(
    tmp_path, missing
):
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = SimpleNamespace(root=tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    directive = {
        "voice_path": "voice.mp3",
        "text": "approved words",
        "shots": [{"source_start_s": 12.0, "voice_end_s": 5.0, "crop": "720:640:0:0"}],
        "caption_cues": [[0.0, 5.0, "approved words"]],
    }
    directive.pop(missing)

    with pytest.raises(ValueError, match=rf"approved narrated intro missing.*{missing}"):
        pipe._render_approved_narrated_intro(source, 10.0, directive, tmp_path, {})
