from pathlib import Path
from types import SimpleNamespace

from boydclips import captions, diarize, layout, pipeline, render, shorts_editor


def test_short_v2_translates_cut_break_to_source_index(tmp_path, monkeypatch):
    """The daily handoff must not confuse output positions with source indices."""
    segments = [
        SimpleNamespace(start_s=10.0, end_s=10.6, duration=0.6),
        SimpleNamespace(start_s=20.0, end_s=20.6, duration=0.6),
    ]
    stream = [
        {"i": 100, "t": 0.0, "w": "one", "speaker": "boyd"},
        {"i": 101, "t": 0.3, "w": "two", "speaker": "boyd"},
        {"i": 102, "t": 0.6, "w": "three", "speaker": "boyd"},
        {"i": 103, "t": 0.9, "w": "four", "speaker": "boyd"},
    ]
    plan = SimpleNamespace(
        ok=True,
        refusal="",
        mismatch_with_scorer="",
        total=90,
        scores={},
        anchor={"kind": "exchange", "t": 10.0},
        beats=[],
        duration_s=1.2,
        nonlinear=False,
        segments=segments,
        word_stream=stream,
        focus_plan=[],
        punch_plan=[],
    )
    plan.as_dict = lambda: {"segments": [[10.0, 10.6], [20.0, 20.6]]}

    monkeypatch.setattr(shorts_editor, "plan_short", lambda *args, **kwargs: plan)
    monkeypatch.setattr(shorts_editor, "describe", lambda value: "fixture plan")
    monkeypatch.setattr(shorts_editor, "verify_same_case", lambda *args: None)
    monkeypatch.setattr(shorts_editor, "verify_chronology", lambda *args: None)
    monkeypatch.setattr(shorts_editor, "verify_continuity", lambda *args: [])
    monkeypatch.setattr(render, "detect_tile_crops", lambda source: ("10:10:0:0", "10:10:10:0"))
    monkeypatch.setattr(render, "map_words_to_timeline", lambda *args, **kwargs: [])
    monkeypatch.setattr(diarize, "diarize", lambda source: [])
    monkeypatch.setattr(layout, "compose", lambda *args: {
        "divider_y": 960,
        "base": {"top": {"subject_x": 5}, "bottom": {"subject_x": 5}},
        "anchors": {"top": {"source": "fixture"}, "bottom": {"source": "fixture"}},
        "punch_zoom": 1.0,
        "segments": [],
        "_segments": [],
    })
    monkeypatch.setattr(layout, "overlay_layout", lambda *args, **kwargs: {
        "ok": True, "caption_center": [540, 960], "boxes": [], "overlay_collision": False,
    })
    monkeypatch.setattr(layout, "composition_checks", lambda *args: [])
    monkeypatch.setattr(captions, "kinetic_qc", lambda *args: [
        {"gate": "fixture_stop_before_render", "ok": False},
    ])

    original_plan_captions = captions.plan_captions
    assert original_plan_captions(stream, {}, [2], None)["hard_breaks"] == []  # wrong index is discarded
    assert original_plan_captions(stream, {}, [102], None)["hard_breaks"] == [2]  # source index survives
    received = {}

    def capture_plan_captions(words, style, hard_breaks, provider):
        received["hard_breaks"] = list(hard_breaks)
        return original_plan_captions(words, style, hard_breaks, provider)

    monkeypatch.setattr(captions, "plan_captions", capture_plan_captions)

    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe._judge_tile_map = lambda *args: {"boyd": "top", "defendant": "bottom", "source": "fixture"}
    pipe._subject_anchors = lambda *args: {}
    pipe._plan_cta = lambda *args: None
    result = {}
    transcript = SimpleNamespace(words=[])
    case = {"start_s": 10.0, "end_s": 20.6, "shortable": True}

    pipe._short_v2(
        Path("fixture.mp4"), 0.0, case, "fixture:10", {}, tmp_path,
        {"resolution": [1080, 1920], "captions": {}},
        None, None, transcript, result,
    )

    assert shorts_editor.caption_hard_breaks(plan, stream) == {2}  # output-position control
    assert received["hard_breaks"] == [102]  # source index required by plan_captions
    assert plan.caption_hard_breaks == [2]  # mapped position retained in the plan
