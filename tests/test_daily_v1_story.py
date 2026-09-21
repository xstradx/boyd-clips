import sqlite3
from unittest.mock import Mock

from boydclips import pipeline, render, shorts_editor
from boydclips.config import load_config
from boydclips.discover import Docket
from boydclips.transcribe import Transcript


def test_producer_alignment_rejects_replaced_hook_and_lost_payoff():
    brain = {
        "decision": "MAKE",
        "chronology_strategy": "chronological",
        "hook_start_s": 100.0,
        "sequence": [
            {"edit_order": 1, "role": "hook", "start_s": 100.0, "end_s": 104.0},
            {"edit_order": 2, "role": "payoff", "start_s": 120.0, "end_s": 126.0},
        ],
    }

    aligned = shorts_editor.producer_alignment(
        [render.Segment(99.9, 104.0), render.Segment(119.8, 125.8)], brain,
    )
    assert aligned["ok"] and aligned["hook_first"]

    replaced_hook = shorts_editor.producer_alignment(
        [render.Segment(90.0, 96.0), render.Segment(100.0, 104.0), render.Segment(120.0, 126.0)], brain,
    )
    assert not replaced_hook["ok"] and not replaced_hook["hook_first"]

    lost_payoff = shorts_editor.producer_alignment([render.Segment(100.0, 104.0)], brain)
    assert not lost_payoff["ok"]
    assert [row["role"] for row in lost_payoff["required_ranges"] if not row["ok"]] == ["payoff"]


def test_produce_gives_package_and_short_one_recalled_story(tmp_path, monkeypatch):
    (tmp_path / 'source.mp4').write_bytes(b'source fixture; rendering is mocked')
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = load_config()
    pipe.cfg._data["analysis"]["producer_brain"]["enabled"] = False
    pipe.cfg._data["output"]["longform"].update(intro_enabled=False, trim_dead_air=False)
    pipe.cfg._data["output"]["short"]["autocrop"] = False
    pipe.work = tmp_path / "work"
    pipe.out = tmp_path / "out"
    pipe.store = Mock()
    pipe.store.conn = sqlite3.connect(':memory:')   # the story ledger reads this
    pipe.store.case_key.return_value = "story:10"
    pipe.store.case_windows.return_value = [(10.0, 250.0), (300.0, 500.0)]
    pipe.store.next_case_start.return_value = 510.0
    pipe.store.save_clip.return_value = "story:10:longform"
    pipe._analyzer = Mock()
    seen = {}

    def package(_transcript, story_case, _meta, _version):
        seen["package_case"] = dict(story_case)
        return {
            "hook_verified": True,
            "hook_line": "hook",
            "summary": "summary",
            "longform_title": "title",
            "short_title": "short title",
            "thumbnail_quote": "REAL WORDS",
            "thumbnail_quote_yellow": "WORDS",
        }

    pipe._analyzer.package.side_effect = package
    monkeypatch.setattr(pipeline, "get_transcript", lambda *args, **kwargs: Transcript("story"))
    monkeypatch.setattr(render, "download_section", lambda *args, **kwargs: (tmp_path / "source.mp4", 0.0))
    monkeypatch.setattr(render, "render_longform", lambda *args, **kwargs: 160.0)
    pipe._produce_thumbnail = Mock(return_value={"file_path": str(tmp_path / "A.jpg"), "status": "candidate"})

    def short(_source, _offset, story_case, *_args):
        seen["short_case"] = dict(story_case)

    pipe._short_v2 = short
    pipe._write_manifest = Mock()
    docket = Docket("story", "Story docket", 3600, "2026-09-12", "morning")
    selected = {
        "eligible": True,
        "start_s": 10.0,
        "end_s": 80.0,
        "hook_start_s": 20.0,
        "proceeding_type": "plea",
        "shortable": True,
        "safety": {"safety_pass": True, "safety_reasoning": "fixture"},
        "scores": {},
        "total_score": 90.0,
    }

    pipe.produce(docket, selected)

    assert seen["package_case"]["start_s"] == 10.0
    assert seen["package_case"]["end_s"] == 509.0
    assert seen["short_case"]["start_s"] == 10.0
    assert seen["short_case"]["end_s"] == 509.0
    assert seen["short_case"]["story_windows"] == [[10.0, 250.0], [300.0, 509.0]]
    pipe._write_manifest.assert_called_once()


def test_producer_alignment_allows_silence_but_not_a_missing_negation_or_payoff():
    from boydclips.transcribe import Word
    brain = {"decision": "MAKE", "chronology_strategy": "chronological", "hook_start_s": 100.0,
             "sequence": [{"start_s": 100.0, "end_s": 139.0, "role": "hook_context_turn_payoff"}]}
    words = [Word(100, "I"), Word(101, "did"), Word(102, "not"), Word(103, "agree."),
             Word(134, ">>Then"), Word(135, "the"), Word(136, "plea"), Word(137, "is"), Word(138, "withdrawn.")]
    segments = [render.Segment(99.9, 103.7), render.Segment(133.9, 139)]
    assert shorts_editor.producer_alignment(segments, brain, words)["ok"]
    assert not shorts_editor.producer_alignment(segments, brain)["ok"]
    missing_not = [render.Segment(99.9, 101.7), render.Segment(102.9, 103.7), segments[1]]
    failure = shorts_editor.producer_alignment(missing_not, brain, words)
    assert not failure["ok"] and "not" in failure["required_ranges"][0]["missing_words"]
    assert not shorts_editor.producer_alignment(segments[:1], brain, words)["ok"]
    assert not shorts_editor.producer_alignment([segments[0], segments[1], segments[0]], brain, words)["ok"]


def test_transcript_gap_needs_audio_silence_evidence():
    brain = {"sequence": [{"start_s": 100, "end_s": 139}]}
    segments = [render.Segment(99.9, 103.7), render.Segment(133.9, 139)]
    assert all(c["ok"] for c in shorts_editor.producer_silence_checks(segments, brain, [(3.5, 34)], 100))
    assert not shorts_editor.producer_silence_checks(segments, brain, [], 100)[0]["ok"]
    assert not shorts_editor.producer_silence_checks(segments, brain, [(3.5, 15)], 100)[0]["ok"]


def test_producer_gap_is_preserved_until_audio_proves_silence():
    words = [shorts_editor.TWord(0, 100, 100.4, 'Before'),
             shorts_editor.TWord(1, 103, 103.4, 'after.')]
    cfg = {**shorts_editor.DEFAULTS, 'producer_preserve_ranges': [[99, 105]]}
    assert len(shorts_editor.ranges_for(words, cfg, words)) == 1
    proven = {**cfg, 'verified_audio_silences': [[100.4, 103]]}
    assert len(shorts_editor.ranges_for(words, proven, words)) == 2
    wrong = {**cfg, 'verified_audio_silences': [[101, 102]]}
    assert len(shorts_editor.ranges_for(words, wrong, words)) == 1
