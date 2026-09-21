from pathlib import Path
import hashlib

import pytest

from boydclips import narrated_short_intro as intro
from boydclips.narrated_short_intro import FreezeCircleCue, NarratedIntroSpec, Shot, SourceHookSpec


SCRIPT = (
    "This woman thought two years would make Judge Boyd go easy on her—"
    "then Boyd reads the evidence."
)
VOICE_DURATION = 5.407313


def approved_spec(tmp_path: Path) -> NarratedIntroSpec:
    voice = tmp_path / "perry_reads_the_evidence_selected_v3.mp3"
    voice.write_bytes(b"approved voice")
    return NarratedIntroSpec(
        voice_path=voice,
        text=SCRIPT,
        shots=(
            Shot(102.0, 1.38, "720:640:180:120"),
            Shot(106.0, 3.66, "720:640:220:160"),
            Shot(110.0, VOICE_DURATION, "720:640:260:180"),
        ),
        caption_cues=(
            (0.0, 1.38, "This woman thought two years"),
            (1.38, 3.26, "would make Judge Boyd go easy on her"),
            (3.66, VOICE_DURATION, "then Boyd reads the evidence"),
        ),
    )


def freeze_cue(tmp_path: Path, *, ding_at_s=0.366667) -> FreezeCircleCue:
    ding = tmp_path / "ding.wav"
    ding.write_bytes(b"approved ding")
    return FreezeCircleCue(
        source_frame_s=101.0,
        duration_s=0.6,
        crop="720:640:180:120",
        circle_box=(330, 430, 760, 1220),
        circle_start_s=0.08,
        circle_complete_s=0.35,
        ding_path=ding,
        ding_at_s=ding_at_s,
    )


def test_approved_narrator_cues_match_selected_script(tmp_path):
    approved_spec(tmp_path).validate(VOICE_DURATION)


def test_ordered_exact_source_hooks_keep_separate_text_across_source_gap(tmp_path, monkeypatch):
    clips = []
    for index, (start, end, text, speaker) in enumerate((
        (1338.02, 1340.60, "This is the bracelet. I need you to pawn it.", "boyd"),
        (1353.00, 1356.84, "Like I said, when I made them choices back then.", "defendant"),
    )):
        path = tmp_path / f"hook-{index}.mp4"
        path.write_bytes(f"hook-{index}".encode())
        clips.append(SourceHookSpec(path, start, end, text, speaker, hashlib.sha256(path.read_bytes()).hexdigest()))
    monkeypatch.setattr(intro.render, "probe_duration", lambda path: 2.58 if "hook-0" in str(path) else 3.84)
    intro.validate_source_hooks(tuple(clips))
    assert [clip.text for clip in clips] == [
        "This is the bracelet. I need you to pawn it.",
        "Like I said, when I made them choices back then.",
    ]


def test_source_hooks_reject_overlap_that_could_create_false_join(tmp_path, monkeypatch):
    path_a = tmp_path / "a.mp4"; path_a.write_bytes(b"a")
    path_b = tmp_path / "b.mp4"; path_b.write_bytes(b"b")
    monkeypatch.setattr(intro.render, "probe_duration", lambda _path: 2.0)
    hooks = (
        SourceHookSpec(path_a, 10.0, 12.0, "Complete first sentence.", "boyd", hashlib.sha256(b"a").hexdigest()),
        SourceHookSpec(path_b, 11.5, 13.5, "Complete second sentence.", "defendant", hashlib.sha256(b"b").hexdigest()),
    )
    with pytest.raises(ValueError, match="source order without overlap"):
        intro.validate_source_hooks(hooks)


def test_narrator_cues_reject_changed_spoken_words(tmp_path):
    good = approved_spec(tmp_path)
    changed = NarratedIntroSpec(
        good.voice_path,
        good.text,
        good.shots,
        good.caption_cues[:-1] + ((3.66, VOICE_DURATION, "then Boyd ignores the evidence"),),
    )
    with pytest.raises(ValueError, match="does not match"):
        changed.validate(VOICE_DURATION)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda s: {"shots": (s.shots[0], Shot(106.0, 1.0, s.shots[1].crop), s.shots[2])}, "shot timing"),
        (
            lambda s: {
                "caption_cues": (
                    s.caption_cues[0],
                    (1.0, 3.26, s.caption_cues[1][2]),
                    s.caption_cues[2],
                )
            },
            "overlap",
        ),
        (
            lambda s: {
                "caption_cues": s.caption_cues[:-1]
                + ((3.66, VOICE_DURATION + 0.25, s.caption_cues[-1][2]),)
            },
            "narrator captions|voice range",
        ),
    ],
)
def test_rejects_nonmonotonic_overlap_and_out_of_range_timing(tmp_path, mutate, message):
    good = approved_spec(tmp_path)
    values = {
        "voice_path": good.voice_path,
        "text": good.text,
        "shots": good.shots,
        "caption_cues": good.caption_cues,
    }
    values.update(mutate(good))
    with pytest.raises(ValueError, match=message):
        NarratedIntroSpec(**values).validate(VOICE_DURATION)


def test_missing_voice_and_source_assets_fail_closed(tmp_path, monkeypatch):
    good = approved_spec(tmp_path)
    good.voice_path.unlink()
    with pytest.raises(FileNotFoundError, match="narration missing"):
        good.validate(VOICE_DURATION)

    good = approved_spec(tmp_path)
    missing_source = tmp_path / "missing-source.mp4"
    monkeypatch.setattr(intro.render, "probe_duration", lambda _path: VOICE_DURATION)
    with pytest.raises(FileNotFoundError, match="source video missing"):
        intro.render_moving_broll(
            missing_source, 100.0, good, tmp_path / "out.mp4", {"watermark": None}
        )


@pytest.mark.parametrize("source_start", [99.9, 109.6])
def test_runtime_rejects_shots_outside_local_source_bounds(tmp_path, monkeypatch, source_start):
    good = approved_spec(tmp_path)
    bounded = NarratedIntroSpec(
        good.voice_path,
        good.text,
        (Shot(source_start, VOICE_DURATION, "720:640:180:120"),),
        good.caption_cues,
    )
    source = tmp_path / "local-source.mp4"
    source.write_bytes(b"source")

    def duration(path):
        return VOICE_DURATION if Path(path) == good.voice_path else 10.0

    monkeypatch.setattr(intro.render, "probe_duration", duration)
    monkeypatch.setattr(intro.render, "probe_dimensions", lambda _path: (1080, 1920))
    with pytest.raises(ValueError, match="outside the local source"):
        intro.render_moving_broll(
            source, 100.0, bounded, tmp_path / "out.mp4", {"watermark": None}
        )


def test_runtime_rejects_crop_outside_decoded_source_frame(tmp_path, monkeypatch):
    good = approved_spec(tmp_path)
    invalid = NarratedIntroSpec(
        good.voice_path,
        good.text,
        (Shot(102.0, VOICE_DURATION, "720:640:500:100"),),
        good.caption_cues,
    )
    source = tmp_path / "local-source.mp4"
    source.write_bytes(b"source")

    monkeypatch.setattr(
        intro.render,
        "probe_duration",
        lambda path: 30.0 if Path(path) == source else VOICE_DURATION,
    )
    monkeypatch.setattr(intro.render, "probe_dimensions", lambda _path: (1080, 1920))

    with pytest.raises(ValueError, match="source crop lies outside"):
        intro.render_moving_broll(
            source, 100.0, invalid, tmp_path / "out.mp4", {"watermark": None}
        )


def test_default_captions_have_no_on_screen_label_dialogue(tmp_path):
    captions = tmp_path / "captions.ass"
    intro._ass(approved_spec(tmp_path), captions)

    dialogue = [line for line in captions.read_text(encoding="utf-8").splitlines()
                if line.startswith("Dialogue:")]
    assert dialogue
    assert all(",Label," not in line for line in dialogue)


def test_freeze_circle_accepts_completed_circle_then_ding(tmp_path):
    good = approved_spec(tmp_path)
    spec = NarratedIntroSpec(
        good.voice_path,
        good.text,
        good.shots,
        good.caption_cues,
        freeze_circle=freeze_cue(tmp_path),
    )
    spec.validate(VOICE_DURATION)


def test_freeze_circle_rejects_ding_before_first_fully_drawn_output_frame(tmp_path):
    good = approved_spec(tmp_path)
    spec = NarratedIntroSpec(
        good.voice_path,
        good.text,
        good.shots,
        good.caption_cues,
        freeze_circle=freeze_cue(tmp_path, ding_at_s=0.36),
    )
    with pytest.raises(ValueError, match="ding cannot land before the circle is complete"):
        spec.validate(VOICE_DURATION)


def test_render_command_advances_real_source_and_maps_only_narrator_audio(tmp_path, monkeypatch):
    spec = approved_spec(tmp_path)
    source = tmp_path / "local-source.mp4"
    source.write_bytes(b"moving video")
    output = tmp_path / "narrated-intro.mp4"
    calls = []

    def duration(path):
        return 30.0 if Path(path) == source else VOICE_DURATION

    monkeypatch.setattr(intro.render, "probe_duration", duration)
    monkeypatch.setattr(intro.render, "probe_dimensions", lambda _path: (1080, 1920))
    monkeypatch.setattr(intro.subprocess, "run", lambda cmd, check: calls.append((cmd, check)))

    record = intro.render_moving_broll(
        source, 100.0, spec, output, {"watermark": None, "preset": "fast", "crf": 20}
    )

    assert len(calls) == 1 and calls[0][1] is True
    cmd = calls[0][0]
    assert "-loop" not in cmd
    assert cmd.count(str(source)) == 3
    assert [cmd[i + 1] for i, value in enumerate(cmd) if value == "-ss"] == ["2.000", "6.000", "10.000"]
    assert [cmd[i + 1] for i, value in enumerate(cmd) if value == "-t"] == ["1.380", "2.280", "1.747"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("setpts=PTS-STARTPTS") == 3
    assert "concat=n=3:v=1:a=0" in graph
    audio_maps = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-map"]
    assert audio_maps == ["[v]", "3:a"]
    assert "0:a" not in audio_maps and "1:a" not in audio_maps and "2:a" not in audio_maps
    assert record["moving_source"] is True
    assert record["court_dialogue_captions"] is False


def test_freeze_circle_is_brief_and_remaining_narration_uses_moving_video(tmp_path, monkeypatch):
    good = approved_spec(tmp_path)
    spec = NarratedIntroSpec(
        good.voice_path,
        good.text,
        good.shots,
        good.caption_cues,
        freeze_circle=freeze_cue(tmp_path),
    )
    source = tmp_path / "local-source.mp4"
    source.write_bytes(b"moving video")
    calls = []

    monkeypatch.setattr(
        intro.render,
        "probe_duration",
        lambda path: 30.0 if Path(path) == source else VOICE_DURATION,
    )
    monkeypatch.setattr(intro.render, "probe_dimensions", lambda _path: (1080, 1920))
    monkeypatch.setattr(intro, "_circle_frames", lambda *_args, **_kwargs: 18)
    monkeypatch.setattr(intro.subprocess, "run", lambda cmd, check: calls.append((cmd, check)))

    record = intro.render_moving_broll(
        source, 100.0, spec, tmp_path / "intro.mp4", {"watermark": None}
    )

    cmd = calls[0][0]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "tpad=stop_mode=clone:stop_duration=0.600" in graph
    assert graph.count("setpts=PTS-STARTPTS") >= 3
    assert "concat=n=4:v=1:a=0" in graph
    assert "adelay=367:all=1" in graph
    assert "volume=0.20" in graph
    assert "-loop" not in cmd
    assert record["freeze_circle"]["whole_narration_frozen"] is False
    assert record["freeze_circle"]["moving_broll_starts_s"] == pytest.approx(0.6)


def test_transition_whoosh_mix_uses_seam_timing_and_records_provenance(tmp_path, monkeypatch):
    video = tmp_path / "intro-and-body.mp4"
    video.write_bytes(b"video")
    whoosh = tmp_path / "whoosh.wav"
    whoosh.write_bytes(b"whoosh")
    output = tmp_path / "mixed.mp4"
    calls = []

    def duration(path):
        return 0.37 if Path(path) == whoosh else 12.0

    monkeypatch.setattr(intro.render, "probe_duration", duration)
    monkeypatch.setattr(intro.subprocess, "run", lambda cmd, check: calls.append((cmd, check)))

    record = intro.mix_transition_sfx(
        video, output, whoosh, at_s=VOICE_DURATION, gain_db=-24.0
    )

    cmd = calls[0][0]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "volume=-24.0dB" in graph
    assert "adelay=5407:all=1" in graph
    assert "amix=inputs=2:duration=first:normalize=0" in graph
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    assert [cmd[i + 1] for i, value in enumerate(cmd) if value == "-map"] == ["0:v", "[a]"]
    assert record == {
        "path": str(whoosh.resolve()),
        "at_s": VOICE_DURATION,
        "gain_db": -24.0,
        "duration_s": 0.37,
    }
