"""Verification suite for the paths that don't need an API key.

Written because the pipeline's riskiest failures are silent ones that only
surface at 3am inside a scheduled run: a template that raises on .format(),
a JSON schema the API rejects, a segment plan that reorders courtroom speech.

Run:  python tests/test_pipeline.py       (no pytest needed)
      pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import json
import re
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import analyze, discover, render  # noqa: E402
from boydclips.config import load_config, prompt_text  # noqa: E402
from boydclips.state import Store  # noqa: E402
from boydclips.transcribe import Transcript, Word, parse_json3  # noqa: E402

CFG = load_config()

# JSON Schema keywords the structured-outputs API does not support. A schema
# carrying any of these is a 400 at request time, not a validation warning.
UNSUPPORTED_SCHEMA_KEYS = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "patternProperties",
}


# ---------------------------------------------------------------- prompts


def test_prompts_parse_and_version():
    for name in ("segment_cases", "score_cases", "package_post"):
        version, system, user = prompt_text(name)
        assert version != "unknown", f"{name} has no version in front matter"
        assert len(system) > 500, f"{name} system section suspiciously short"
        assert len(user) > 50, f"{name} user section suspiciously short"


def test_prompt_templates_format_without_raising():
    """A stray brace in a prompt raises KeyError/IndexError mid-run."""
    fields = {
        "segment_cases": dict(
            video_id="x", video_title="t", docket_date="2026-08-06",
            duration_s=100, transcript="[00:00:00] hello",
        ),
        "score_cases": dict(
            video_title="t", docket_date="2026-08-06", source_url="u",
            cases_json="[]", transcript="[00:00:00] hello",
        ),
        "package_post": dict(
            spec_version="1.0.0", court="c", docket_date="2026-08-06",
            source_url="u", start_timestamp="00:01:00",
            case_json="{}", case_transcript="hello",
        ),
    }
    for name, kwargs in fields.items():
        _, _, template = prompt_text(name)
        out = template.format(**kwargs)
        assert "{" not in out.replace("{}", ""), f"{name} left an unfilled placeholder"


def test_description_templates_format():
    lf = CFG.require("packaging.longform.description_template").format(
        summary="s", proceeding_type="Plea", court="c",
        docket_date="2026-08-06", source_url="u", start_timestamp="00:01:00",
    )
    assert "presumed innocent" in lf, "long-form description dropped the R1 disclaimer"

    sh = CFG.require("packaging.short.description_template").format(
        hook_line="h", longform_url="https://x", court="c", hashtags="#a",
    )
    assert "https://x" in sh, "short description must carry the long-form URL"


def test_rubric_weights_match_prompt():
    """BOYD_EDITORIAL_V2: the maxima live in editorial.DIMENSIONS, are mirrored
    in config, and are described in the prompt. Drift = silent mis-scoring."""
    from boydclips import editorial
    _, system, _ = prompt_text("score_cases")
    weights = CFG.require("analysis.rubric_weights")
    assert dict(weights) == dict(editorial.DIMENSIONS), "config rubric_weights != editorial.DIMENSIONS"
    for dim, mx in editorial.DIMENSIONS.items():
        assert f"### {dim} — max {mx}" in system, (
            f"{dim} max {mx} not stated as '### {dim} — max {mx}' in prompts/score_cases.md"
        )
    for thr in (editorial.TIER_A, editorial.TIER_MAKE, editorial.TIER_HOLD):
        assert str(thr) in system, f"tier threshold {thr} missing from the prompt"
    assert editorial.RULESET in prompt_text("score_cases")[0]
    assert editorial.RULESET in prompt_text("package_post")[0]
    assert editorial.RULESET in prompt_text("judge_moments")[0]
    for reason in editorial.GATE_REASONS:
        assert f"`{reason}`" in system, f"gate reason {reason} missing from the prompt"


# ---------------------------------------------------------------- schemas


def _walk(node, path="$"):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_schemas_use_only_supported_keywords():
    for name, schema in (
        ("SEGMENT", analyze.SEGMENT_SCHEMA),
        ("SCORE", analyze.SCORE_SCHEMA),
        ("PACKAGE", analyze.PACKAGE_SCHEMA),
    ):
        for path, node in _walk(schema):
            bad = UNSUPPORTED_SCHEMA_KEYS & set(node.keys())
            assert not bad, f"{name} schema uses unsupported keyword(s) {bad} at {path}"


def test_schema_objects_are_strict():
    """Structured outputs require additionalProperties:false plus a `required`
    listing every property on every object."""
    for name, schema in (
        ("SEGMENT", analyze.SEGMENT_SCHEMA),
        ("SCORE", analyze.SCORE_SCHEMA),
        ("PACKAGE", analyze.PACKAGE_SCHEMA),
    ):
        for path, node in _walk(schema):
            if node.get("type") != "object":
                continue
            assert node.get("additionalProperties") is False, (
                f"{name}: object at {path} missing additionalProperties:false"
            )
            props = set(node.get("properties", {}))
            required = set(node.get("required", []))
            assert props == required, (
                f"{name}: object at {path} has properties {props - required} "
                f"not listed in required"
            )


def test_schemas_are_json_serializable():
    for schema in (analyze.SEGMENT_SCHEMA, analyze.SCORE_SCHEMA, analyze.PACKAGE_SCHEMA):
        json.loads(json.dumps(schema))


# ---------------------------------------------------------------- gating


def _case(**over):
    from boydclips import editorial
    base = {
        "start_s": 10.0, "end_s": 200.0, "audio_quality": 5,
        "safety": {"safety_pass": True, "safety_rule_violations": [], "safety_reasoning": ""},
        "scores": {d: {"score": mx, "justification": "j"} for d, mx in editorial.DIMENSIONS.items()},
        "editorial": {"gate_pass": True, "gate_failures": [], "story_angle": "a", "money_moment": "m",
                      "money_moment_s": 20.0, "why_viewer_cares": "w", "title_angles": ["1", "2", "3"],
                      "weakness": "none", "decision": "MAKE"},
        "total_score": 80.0,
        "shortable": True,
    }
    base.update(over)
    return base


def test_safety_failure_always_blocks():
    gates = CFG.require("analysis.gates")
    case = _case(total_score=100.0)
    case["safety"] = {"safety_pass": False, "safety_rule_violations": ["R2"],
                      "safety_reasoning": "juvenile"}
    ok, reason = analyze._check_gates(case, gates)
    assert not ok and "R2" in reason, "a perfect score must not override the safety gate"


def test_low_score_blocked():
    ok, _ = analyze._check_gates(_case(total_score=10.0), CFG.require("analysis.gates"))
    assert not ok


def test_unshortable_case_is_banked_not_published():
    """The short is the whole distribution mechanism; a long-form without one
    is banked rather than spent on a publishing day."""
    gates = CFG.require("analysis.gates")
    case = _case(total_score=95.0, shortable=False)
    ok, reason = analyze._check_gates(case, gates)
    assert not ok and "banked" in reason

    case = _case(total_score=95.0, shortable=True)
    ok, _ = analyze._check_gates(case, gates)
    assert ok


def test_thresholds_are_the_ruleset_tiers():
    """BOYD_EDITORIAL_V2: MAKE at 78, HOLD at 70. The old 'must be <= 57'
    calibration guard belonged to the retired 0-100-weighted rubric."""
    from boydclips import editorial
    gates = CFG.require("analysis.gates")
    assert gates["min_total_score"] == editorial.TIER_MAKE == 78
    assert gates["hold_threshold"] == editorial.TIER_HOLD == 70
    assert gates.get("requires_editorial_gate") is True
    assert not gates.get("requires_pushback"), "requires_pushback is retired and must stay inert"


def test_editorial_gate_blocks_before_score():
    """A routine / no-story / charge-severity verdict is a SKIP whatever the number."""
    case = _case(total_score=95.0)
    case["editorial"]["gate_pass"] = False
    case["editorial"]["gate_failures"] = ["charge_severity", "no_payoff"]
    ok, reason = analyze._check_gates(case, CFG.require("analysis.gates"))
    assert not ok and "editorial gate" in reason and "charge_severity" in reason


def test_hold_band_is_named_not_silently_skipped():
    case = _case(total_score=73.0)
    case["editorial"]["weakness"] = "payoff is off camera"
    ok, reason = analyze._check_gates(case, CFG.require("analysis.gates"))
    assert not ok and reason.startswith("HOLD") and "off camera" in reason
    ok, reason = analyze._check_gates(_case(total_score=61.0), CFG.require("analysis.gates"))
    assert not ok and reason.startswith("SKIP")


def test_total_is_the_clamped_sum_of_dimension_points():
    from boydclips import editorial
    scores = {d: {"score": v, "justification": "j"} for d, v in
              {"story_engine": 17, "payoff": 15, "boyd_factor": 12, "stakes": 9,
               "clarity": 8, "packaging": 11, "thumbnail": 3}.items()}
    assert editorial.total_score(scores) == 75.0
    scores["story_engine"]["score"] = 40          # over its max of 20 -> clamped
    assert editorial.total_score(scores) == 78.0
    assert editorial.decision(78.0, True) == "MAKE"
    assert editorial.decision(78.0, False) == "SKIP"
    assert editorial.decision(72.0, True) == "HOLD"


def test_repeat_defendant_is_only_a_tie_breaker():
    from boydclips import editorial
    assert not editorial.prefer_repeat(88, 79), "an 88 one-off must beat a 79 repeat"
    assert editorial.prefer_repeat(80, 78)


def test_title_trimming():
    assert len(analyze._trim_title("word " * 60, 90)) <= 90
    assert analyze._trim_title("short title", 90) == "short title"
    assert not analyze._trim_title("a" * 50 + " bbbb", 52).endswith(",")


def test_quote_verification_ignores_punctuation():
    body = "well thats just trifling and why are eight"
    # Auto-captions drop apostrophes inconsistently; both spellings must match.
    assert analyze._quote_appears("That's just trifling!", body)
    assert analyze._quote_appears("thats just trifling", body)
    assert analyze._quote_appears("That’s just trifling", body), "curly apostrophe"
    # And the reverse: apostrophe in the transcript, none in the quote.
    assert analyze._quote_appears("dont do that", "you dont do that again")
    assert analyze._quote_appears("don't do that", "you don't do that again")
    # A hallucinated quote must still be caught.
    assert not analyze._quote_appears("I sentence you to ten years", body)


# ---------------------------------------------------------------- segments


def test_short_plan_rejects_reordered_segments():
    """SAFETY_RULES R8 — reordering can manufacture an exchange that never
    happened. This must reject, not silently sort."""
    case = {"start_s": 0, "end_s": 300, "short_segments": [
        {"beat": "hook", "start_s": 100, "end_s": 120, "quote": ""},
        {"beat": "stakes", "start_s": 20, "end_s": 40, "quote": ""},
    ]}
    assert render.plan_short_segments(case, CFG.require("output.short")) is None


def test_short_plan_rejects_segments_outside_case():
    case = {"start_s": 100, "end_s": 200, "short_segments": [
        {"beat": "hook", "start_s": 10, "end_s": 60, "quote": ""},
    ]}
    assert render.plan_short_segments(case, CFG.require("output.short")) is None


def test_short_plan_rejects_too_short():
    case = {"start_s": 0, "end_s": 300, "short_segments": [
        {"beat": "hook", "start_s": 10, "end_s": 14, "quote": ""},
    ]}
    assert render.plan_short_segments(case, CFG.require("output.short")) is None


def test_short_plan_trims_to_ceiling():
    cfg = CFG.require("output.short")
    case = {"start_s": 0, "end_s": 600, "short_segments": [
        {"beat": "hook", "start_s": 0, "end_s": 40, "quote": ""},
        {"beat": "turn", "start_s": 100, "end_s": 160, "quote": ""},
    ]}
    segs = render.plan_short_segments(case, cfg)
    assert segs is not None
    total = sum(s.duration for s in segs)
    assert total <= cfg["max_duration_s"], f"{total}s exceeds the 60s platform limit"
    assert segs[0].start_s == 0, "trimming must come off the tail, not the hook"


def test_single_moment_short_is_accepted():
    """CONTENT_SPEC v1.1 Form B — one contiguous stretch, no arc. The four-beat
    form fitted 0/10 real cases, so this path is the common one."""
    case = {"start_s": 0, "end_s": 600, "short_form": "single_moment",
            "short_segments": [
                {"beat": "moment", "start_s": 100, "end_s": 145, "quote": ""},
            ]}
    segs = render.plan_short_segments(case, CFG.require("output.short"))
    assert segs is not None and len(segs) == 1
    assert 25 <= segs[0].duration <= 59


def test_moment_beat_is_in_the_schema():
    beat = analyze._SEGMENT_REF["properties"]["beat"]["enum"]
    assert "moment" in beat, "Form B shorts cannot be expressed without it"


def test_short_form_is_required_and_enumerated():
    case_schema = analyze.SCORE_SCHEMA["properties"]["cases"]["items"]
    assert "short_form" in case_schema["required"]
    assert set(case_schema["properties"]["short_form"]["enum"]) == {
        "four_beat", "single_moment", "none"
    }


def test_short_plan_accepts_valid_four_beats():
    case = {"start_s": 0, "end_s": 600, "short_segments": [
        {"beat": "hook", "start_s": 10, "end_s": 13, "quote": ""},
        {"beat": "stakes", "start_s": 20, "end_s": 28, "quote": ""},
        {"beat": "turn", "start_s": 60, "end_s": 80, "quote": ""},
        {"beat": "button", "start_s": 200, "end_s": 212, "quote": ""},
    ]}
    segs = render.plan_short_segments(case, CFG.require("output.short"))
    assert segs is not None and len(segs) == 4


# ---------------------------------------------------------------- transcript


def test_json3_skips_append_duplicates_and_newlines():
    raw = json.dumps({"events": [
        {"tStartMs": 1000, "segs": [{"utf8": "hello"}, {"utf8": " world", "tOffsetMs": 500}]},
        {"tStartMs": 1400, "aAppend": 1, "segs": [{"utf8": "hello world"}]},
        {"tStartMs": 1500, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 2000, "wWinId": 1},
    ]})
    words = parse_json3(raw)
    assert [w.w for w in words] == ["hello", "world"], "aAppend duplicate leaked through"
    assert words[1].t == 1.5, "tOffsetMs not applied"


def test_transcript_roundtrip_and_slice():
    t = Transcript("v", [Word(1.0, "a"), Word(2.0, "b"), Word(9.0, "c")])
    assert Transcript.from_json(t.to_json()).words[2].w == "c"
    assert t.text_between(0, 5) == "a b"


def test_llm_rendering_has_timestamps():
    t = Transcript("v", [Word(float(i), f"w{i}") for i in range(60)])
    lines = t.render_for_llm(window_s=10).splitlines()
    assert len(lines) == 6, f"expected 6 ten-second windows, got {len(lines)}"
    assert lines[0].startswith("[00:00:00]") and lines[1].startswith("[00:00:10]")


def test_caption_grouping_respects_line_budget():
    words = [Word(float(i), "abcdefgh") for i in range(20)]
    for group in render.group_words(words, max_chars=22, max_lines=2):
        assert sum(len(w.w) + 1 for w in group) - 1 <= 22 * 2 + 1


def test_caption_events_never_overlap(tmp_path=None):
    """Two cards on screen at once is four lines, not two.

    A card's last word used to end at start+0.45 with nothing to clamp it, so
    it ran over the next card and libass stacked the collision. Shipped in the
    Thompson short: events 0:01.27-1.72 and 0:01.39-1.75.
    """
    out = Path(tmp_path or ".") / "_overlap.ass"
    # Words tight enough that a flat 0.45s tail must cross the next card.
    words = [Word(i * 0.12, "wordy") for i in range(40)]
    render.build_ass(words, 0.0, 10.0, {"max_chars_per_line": 12,
                                        "max_lines": 2}, None, out)

    spans = []
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        _, start, end = line.split(",")[0:3]
        spans.append((_ass_seconds(start), _ass_seconds(end)))
    out.unlink()

    assert spans, "no dialogue events were written"
    for (s0, e0), (s1, _) in zip(spans, spans[1:]):
        assert e0 <= s1 + 1e-6, f"event {s0}-{e0} overlaps the next at {s1}"


def _ass_seconds(stamp: str) -> float:
    h, m, s = stamp.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def test_silence_trim_keeps_a_pad_and_refuses_stutter_cuts():
    """Cutting flush to the detected boundary clips the next word's attack."""
    # Beat 100-110 in source time is 5-15 in file time at offset 95, so a file
    # silence of 7-8 falls at source 102-103. Getting this conversion backwards
    # is exactly the failure the function's offset argument exists to prevent.
    seg = [render.Segment(100.0, 110.0)]
    kept = render.plan_silence_trim(seg, [(7.0, 8.0)], offset_s=95.0,
                                    min_silence_s=0.40, keep_s=0.12)
    assert len(kept) == 2, [(s.start_s, s.end_s) for s in kept]
    assert abs(kept[0].end_s - 102.12) < 1e-6, kept[0].end_s
    assert abs(kept[1].start_s - 102.88) < 1e-6, kept[1].start_s

    # Under min_silence_s it is breath, not dead air.
    assert render.plan_silence_trim(seg, [(7.0, 7.3)], 95.0) == seg

    # A cut that would leave a fragment shorter than min_piece_s is a stutter.
    tight = render.plan_silence_trim(seg, [(5.1, 5.9), (5.95, 6.9)], 95.0,
                                     min_piece_s=1.0)
    assert len(tight) == 2, [(s.start_s, s.end_s) for s in tight]


def test_silence_trim_never_extends_a_beat():
    seg = [render.Segment(100.0, 110.0)]
    # A silence running past the beat's end must not drag the piece with it.
    kept = render.plan_silence_trim(seg, [(9.0, 20.0)], offset_s=95.0)
    assert kept[-1].end_s <= 110.0 + 1e-9
    assert all(s.start_s >= 100.0 - 1e-9 for s in kept)


def test_words_survive_a_removed_gap():
    """A word timestamped inside a cut is snapped forward, never dropped."""
    segments = [render.Segment(10.0, 12.0), render.Segment(13.0, 15.0)]
    words = [Word(10.5, "a"), Word(12.4, "gap"), Word(13.5, "b")]
    mapped = render.map_words_to_timeline(words, segments)

    assert [w.w for w in mapped] == ["a", "gap", "b"]
    assert abs(mapped[0].t - 0.5) < 1e-6
    assert abs(mapped[1].t - 2.0) < 1e-6      # clamped to the piece's end
    assert abs(mapped[2].t - 2.5) < 1e-6      # 2.0 elapsed + 0.5 into piece 2
    assert mapped == sorted(mapped, key=lambda w: w.t)


def test_gap_between_beats_is_not_absorbed():
    """Only a trimmed pause is absorbed — never the minutes between two beats.

    Thompson's beats 2 and 3 are 22 minutes apart. Absorbing every gap mapped
    15,568 words onto a 32.9s timeline.
    """
    segments = [render.Segment(10.0, 12.0), render.Segment(1400.0, 1402.0)]
    words = [Word(11.0, "in"), Word(700.0, "unrelated"), Word(1401.0, "also_in")]
    mapped = render.map_words_to_timeline(words, segments)
    assert [w.w for w in mapped] == ["in", "also_in"]


# ---------------------------------------------------------------- discovery


def test_docket_date_and_session_parsing():
    cases = [
        ("TUES., AUG 4, 2026/JUDGE STEPHANIE BOYD/187TH DISTRICT COURT/MORNING DOCKET",
         "2026-08-04", "morning"),
        ("THURS., JULY 30, 2026/JUDGE STEPHANIE BOYD/187TH DISTRICT COURT/MORN DOCKET",
         "2026-07-30", "morning"),
        ("MON, MARCH 9, 2026/JUDGE STEPHANIE BOYD/187TH DISTRICT COURT/AFTER DOCKET",
         "2026-03-09", "afternoon"),
        ("no date here", "", "unknown"),
    ]
    for title, expect_date, expect_session in cases:
        assert discover.parse_docket_date(title) == expect_date, title
        assert discover.parse_session(title) == expect_session, title


def test_filter_new_applies_every_gate():
    from datetime import date
    made = [
        discover.Docket("keep", "t", 3600, "2026-08-08", "morning"),
        discover.Docket("seen", "t", 3600, "2026-08-08", "morning"),
        discover.Docket("short", "t", 60, "2026-08-08", "morning"),
        discover.Docket("old", "t", 3600, "2026-01-01", "morning"),
    ]
    kept = discover.filter_new(
        made, seen={"seen"}, min_duration_s=900, max_age_days=4,
        today=date(2026, 8, 9),
    )
    assert [d.video_id for d in kept] == ["keep"]


def test_a_docket_defaults_to_boyd_and_can_carry_another_judge():
    """The judge field is additive: the five positional arguments every
    existing constructor uses still mean Judge Stephanie Boyd."""
    default = discover.Docket("v", "t", 3600, "2026-08-08", "morning")
    assert default.judge_id == "stephanie_boyd"
    assert default.judge_name == "Judge Stephanie Boyd"

    west = discover.Docket(
        "w", "t", 3600, "2026-08-08", "morning",
        judge_id="raquel_west", judge_name="Judge Raquel West",
    )
    assert (west.judge_id, west.judge_name) == ("raquel_west", "Judge Raquel West")


def test_list_recent_stamps_every_docket_with_its_judge(monkeypatch):
    """Default stays exactly Boyd; an explicit judge is stamped on each row."""
    rows = (
        "aaa\tTUES., AUG 4, 2026/SOME JUDGE/MORNING DOCKET\t3600\n"
        "bbb\tafternoon session\t1800"
    )
    monkeypatch.setattr(discover, "_run_ytdlp", lambda args, timeout=300: rows)

    default = discover.list_recent("https://example.invalid/streams", 2)
    assert [d.video_id for d in default] == ["aaa", "bbb"]
    assert {(d.judge_id, d.judge_name) for d in default} == {
        ("stephanie_boyd", "Judge Stephanie Boyd")
    }

    west = discover.list_recent(
        "https://example.invalid/streams", 2, "raquel_west", "Judge Raquel West"
    )
    assert {(d.judge_id, d.judge_name) for d in west} == {
        ("raquel_west", "Judge Raquel West")
    }


def test_source_metadata_and_manifest_carry_the_judge(tmp_path):
    """The analyzer metadata dict and the manifest source block name the judge.

    The three original metadata keys are unchanged, and a docket object that
    predates the field (duck-typed, no judge attributes) still produces exactly
    the old metadata and still stamps a Boyd manifest.
    """
    from types import SimpleNamespace
    from boydclips import pipeline

    west = discover.Docket(
        "w", "t", 3600, "2026-08-08", "morning",
        judge_id="raquel_west", judge_name="Judge Raquel West",
    )
    meta = pipeline._docket_meta(west)
    assert (meta["title"], meta["docket_date"], meta["url"]) == ("t", "2026-08-08", west.url)
    assert (meta["judge_id"], meta["judge_name"]) == ("raquel_west", "Judge Raquel West")

    class HistoricalDocket:
        video_id, title, docket_date, session = "old", "t", "2026-01-01", "morning"

        @property
        def url(self) -> str:
            return "https://www.youtube.com/watch?v=old"

    assert pipeline._docket_meta(HistoricalDocket()) == {
        "title": "t", "docket_date": "2026-01-01",
        "url": "https://www.youtube.com/watch?v=old",
    }

    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = CFG
    pipe._analyzer = SimpleNamespace(prompt_versions={"segment_cases": "fixture"},
                                     usage_events=[], calls_used=0)
    case = {"start_s": 0.0, "end_s": 60.0, "safety": {"safety_reasoning": "fixture"},
            "scores": {}, "total_score": 12.0}
    result = {
        "case_key": "w:0", "short_editor": None, "short": None,
        "longform": {"file_path": "longform.mp4", "duration_s": 60.0,
                     "title": "T", "description": "D"},
    }

    for docket, expect_id, expect_name in (
        (west, "raquel_west", "Judge Raquel West"),
        (discover.Docket("v", "t", 3600, "2026-08-08", "morning"),
         "stephanie_boyd", "Judge Stephanie Boyd"),
        (HistoricalDocket(), "stephanie_boyd", "Judge Stephanie Boyd"),
    ):
        review_dir = tmp_path / f"{docket.video_id}_{expect_id}"
        review_dir.mkdir()
        pipe._write_manifest(review_dir, docket, case, {"hook_verified": True}, result)
        manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["source"]["judge_id"] == expect_id, docket.video_id
        assert manifest["source"]["judge_name"] == expect_name, docket.video_id
        assert manifest["source"]["video_id"] == docket.video_id


# ---------------------------------------------------------------- state


def test_store_idempotency_and_promotion_gate(tmp_path=None):
    import tempfile
    tmp = Path(tmp_path or tempfile.mkdtemp())
    store = Store(tmp / "t.db")

    store.add_docket("v1", "t", "2026-08-06", 100.0)
    store.add_docket("v1", "t", "2026-08-06", 100.0)
    assert store.seen_docket("v1") and not store.seen_docket("v2")

    gate = CFG.require("autonomy.promotion_gate")
    ready, _ = store.promotion_ready(gate["min_consecutive_approvals"], gate["max_safety_rejects"])
    assert not ready, "empty ledger must not satisfy the promotion gate"

    for i in range(gate["min_consecutive_approvals"]):
        store.record_decision(f"v1:{i}", "approved")
    ready, _ = store.promotion_ready(gate["min_consecutive_approvals"], gate["max_safety_rejects"])
    assert ready

    store.record_decision("v1:bad", "rejected", "misleading", safety_related=True)
    ready, why = store.promotion_ready(
        gate["min_consecutive_approvals"], gate["max_safety_rejects"]
    )
    assert not ready, "a safety reject must revoke promotion readiness"
    store.close()


def test_store_returns_nearest_later_case_boundary(tmp_path):
    store = Store(tmp_path / "t.db")
    store.add_docket("v1", "docket", "2026-09-12", 100.0)
    for start, end in ((10.0, 20.0), (31.0, 40.0), (55.0, 70.0)):
        store.save_case("v1", {"start_s": start, "end_s": end}, None)

    assert store.next_case_start("v1", 10.0) == 31.0
    assert store.next_case_start("v1", 31.0) == 55.0
    assert store.next_case_start("v1", 55.0) is None
    store.close()


# ------------------------------------------------- regressions (code review)


def test_discovered_docket_is_not_treated_as_finished():
    """A docket is recorded at discovery, before any work. Treating that as
    'seen' made --dry-run and any crash consume it permanently."""
    import tempfile
    store = Store(Path(tempfile.mkdtemp()) / "t.db")
    store.add_docket("v1", "t", "2026-08-06", 100.0)

    assert store.seen_docket("v1"), "row should exist"
    assert not store.is_terminal("v1"), "discovered != finished"

    for status in ("transcribed", "analyzed", "error", "refused"):
        store.mark_docket("v1", status)
        assert not store.is_terminal("v1"), f"{status} must stay retryable"

    store.mark_docket("v1", "complete")
    assert store.is_terminal("v1")
    store.close()


def test_same_day_sessions_sort_chronologically():
    """'afternoon' < 'morning' alphabetically, which handed the day's single
    clip slot to the later session."""
    from datetime import date
    made = [
        discover.Docket("pm", "t", 3600, "2026-08-06", "afternoon"),
        discover.Docket("am", "t", 3600, "2026-08-06", "morning"),
    ]
    kept = discover.filter_new(
        made, seen=set(), min_duration_s=900, max_age_days=4, today=date(2026, 8, 7)
    )
    assert [d.video_id for d in kept] == ["am", "pm"]


def test_renamed_rubric_weight_is_rejected_at_startup():
    from boydclips.config import Config, _validate
    import copy
    bad = copy.deepcopy(CFG._data)
    w = bad["analysis"]["rubric_weights"]
    w["story_engines"] = w.pop("story_engine")  # still sums to 100
    _expect_raises(lambda: _validate(Config(bad)), "renamed rubric weight")


def test_sixty_second_short_is_rejected():
    from boydclips.config import Config, _validate
    import copy
    bad = copy.deepcopy(CFG._data)
    bad["output"]["short"]["max_duration_s"] = 60
    _expect_raises(lambda: _validate(Config(bad)), "max_duration_s of exactly 60")


def test_consecutive_approvals_deterministic_within_one_second():
    """decided_at has second resolution; without an id tiebreaker a rejection
    can sort behind approvals and inflate the autonomy promotion counter."""
    import tempfile
    store = Store(Path(tempfile.mkdtemp()) / "t.db")
    store.record_decision("c0", "rejected", "bad", safety_related=True)
    for i in range(5):
        store.record_decision(f"c{i+1}", "approved")
    assert store.reliability()["consecutive_approvals"] == 5

    store.record_decision("c9", "rejected", "bad")
    assert store.reliability()["consecutive_approvals"] == 0, (
        "newest decision is a rejection; streak must be zero"
    )
    store.close()


def test_stacked_layout_always_fits_the_canvas():
    """At the old 2.2 threshold the stacked pair was 2084px tall and the lower
    participant was pushed off a 1920px frame."""
    a = render.SPLIT_STACK_MIN_ASPECT
    for aspect in (a, a + 0.01, 2.7, 3.0, 4.0):
        tile_h = round(1080 / (aspect / 2))
        bottom = render.STACK_TOP_Y + 2 * tile_h
        assert bottom <= 1920, f"aspect {aspect:.2f}: stack bottom {bottom} overflows"
        assert 1920 - bottom >= 0, "no room left for captions"


def test_explicit_vertical_mode_is_honoured():
    """The margin must match the layout that actually gets rendered."""
    wide = "crop=1280:476:0:0"
    cfg = dict(CFG.require("output.short"))

    cfg["vertical_mode"] = "auto"
    mode, _ = render.choose_vertical_layout(Path("x"), wide, cfg)
    assert mode == "split_stack", "wide 2-up should auto-select stacking"

    for forced in ("blur_pad", "center_crop"):
        cfg["vertical_mode"] = forced
        mode, margin = render.choose_vertical_layout(Path("x"), wide, cfg)
        assert mode == forced, f"{forced} must not be overridden by detection"
        assert margin == cfg["captions"]["margin_v"], (
            f"{forced} got a stacked-layout margin ({margin}) it will not render"
        )


def test_every_proceeding_type_has_a_readable_label():
    """Schema enums are machine tokens. Title-casing them put the literal
    sentence "Other before Judge Stephanie Boyd" into a real description."""
    from boydclips.pipeline import PROCEEDING_LABELS, _proceeding_label

    for value in analyze.PROCEEDING_TYPES:
        assert value in PROCEEDING_LABELS, f"{value} has no description label"
        label = _proceeding_label(value)
        assert label[0].isupper() and "_" not in label
        assert label.lower() not in ("other", "administrative"), (
            f"{value} renders as {label!r}, which reads as a stray enum token"
        )


# ------------------------------------------------------------ llm backend


def test_prune_drops_echoed_schema_keywords():
    """The CLI backend pastes the schema into the prompt, and models sometimes
    echo schema metadata back as data. Observed in production: a `safety`
    object returned with a `required` key, which burned all three retries and
    dropped a 20-case docket."""
    from boydclips import llm

    schema = {
        "type": "object",
        "properties": {
            "safety": {
                "type": "object",
                "properties": {"safety_pass": {"type": "boolean"}},
                "required": ["safety_pass"],
                "additionalProperties": False,
            }
        },
        "required": ["safety"],
        "additionalProperties": False,
    }
    polluted = {
        "safety": {"safety_pass": True, "required": ["safety_pass"], "type": "object"},
        "properties": {"junk": 1},
    }
    cleaned = llm.prune_unknown(polluted, schema)
    assert cleaned == {"safety": {"safety_pass": True}}
    assert llm.validate(cleaned, schema) == []


def test_prune_preserves_arrays_and_real_data():
    from boydclips import llm

    schema = {
        "type": "object",
        "properties": {
            "cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"start_s": {"type": "number"}},
                    "required": ["start_s"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["cases"],
        "additionalProperties": False,
    }
    data = {"cases": [{"start_s": 1.0, "enum": "x"}, {"start_s": 2.0}]}
    assert llm.prune_unknown(data, schema) == {"cases": [{"start_s": 1.0}, {"start_s": 2.0}]}


def test_validate_still_catches_real_problems():
    """Pruning must not paper over missing required fields or wrong types."""
    from boydclips import llm

    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "s": {"type": "string"}},
        "required": ["n", "s"],
        "additionalProperties": False,
    }
    assert llm.validate({"n": 1}, schema), "missing required field must error"
    assert llm.validate({"n": "no", "s": "x"}, schema), "wrong type must error"
    assert llm.validate({"n": True, "s": "x"}, schema), "bool is not an integer"
    assert llm.validate({"n": 1, "s": "x"}, schema) == []


def test_extract_json_never_raises_raw_decode_errors():
    """A JSONDecodeError escaping as itself bypasses the retry loop."""
    from boydclips import llm

    for bad in ('{"a": 1,}', "not json at all", "", '{"a": '):
        try:
            llm.extract_json(bad)
        except llm.BackendError:
            pass
        except Exception as exc:
            raise AssertionError(
                f"{bad!r} raised {type(exc).__name__}, which the retry loop cannot catch"
            ) from exc

    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.extract_json('Here you go:\n{"a": 1}') == {"a": 1}


# ---------------------------------------------------------------- config


def test_config_validation_catches_bad_values():
    from boydclips.config import Config, _validate
    import copy

    base = copy.deepcopy(CFG._data)

    bad = copy.deepcopy(base)
    bad["analysis"]["rubric_weights"]["story_engine"] = 99
    _expect_raises(lambda: _validate(Config(bad)), "rubric weights")

    bad = copy.deepcopy(base)
    bad["output"]["short"]["max_duration_s"] = 75
    _expect_raises(lambda: _validate(Config(bad)), "short duration")

    bad = copy.deepcopy(base)
    bad["autonomy"]["mode"] = "yolo"
    _expect_raises(lambda: _validate(Config(bad)), "autonomy mode")


def _expect_raises(fn, label):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError(f"config validation failed to catch: {label}")


# ---------------------------------------------------------------- runner


def test_short_beats_are_clamped_to_the_case_not_discarded():
    """A hook opening slightly before case_start must be trimmed, not thrown out.

    Observed 2026-08-10 on SPSHGzlOe8c:6031: the hook began 6s before the case
    boundary and killed an otherwise valid 52s short. Clamping keeps the short
    while still guaranteeing no audio from the previous defendant.
    """
    cfg = {"min_duration_s": 25, "max_duration_s": 59}
    case = {
        "start_s": 6031, "end_s": 6300, "shortable": True,
        "short_segments": [
            {"start_s": 6025, "end_s": 6040},   # starts before the case
            {"start_s": 6147, "end_s": 6160},
            {"start_s": 6188, "end_s": 6198},
            {"start_s": 6198, "end_s": 6212},
        ],
    }
    segments = render.plan_short_segments(case, cfg)
    assert segments is not None, "valid short was discarded over a 6s overhang"
    assert all(s.start_s >= case["start_s"] and s.end_s <= case["end_s"]
               for s in segments), "a beat still reaches outside the case window"
    assert sum(s.duration for s in segments) >= cfg["min_duration_s"]


def test_short_beat_wholly_outside_the_case_is_rejected():
    """Clamping must not rescue a plan that points at another defendant."""
    cfg = {"min_duration_s": 25, "max_duration_s": 59}
    case = {
        "start_s": 6031, "end_s": 6300, "shortable": True,
        "short_segments": [
            {"start_s": 5900, "end_s": 5930},   # entirely before the case
            {"start_s": 6147, "end_s": 6180},
            {"start_s": 6188, "end_s": 6212},
        ],
    }
    assert render.plan_short_segments(case, cfg) is None


def test_out_of_order_beats_still_rejected():
    """Clamping must not have weakened the no-reordering guarantee (R5)."""
    cfg = {"min_duration_s": 25, "max_duration_s": 59}
    case = {
        "start_s": 6031, "end_s": 6300, "shortable": True,
        "short_segments": [
            {"start_s": 6188, "end_s": 6212},
            {"start_s": 6100, "end_s": 6130},   # goes backwards
            {"start_s": 6240, "end_s": 6260},
        ],
    }
    assert render.plan_short_segments(case, cfg) is None


def test_repair_json_recovers_observed_malformations():
    """The exact failures that killed dockets on 2026-08-09.

    Each case was taken from logs/rejected/. `undefined` in value position is
    the one that mattered most: prune_unknown() would have dropped the invented
    field a moment later, but the parse died first and took the whole run.
    """
    from boydclips.llm import extract_json

    cases = {
        "js undefined":
            '{"cases":[{"safety_rule_violations_note":undefined,"score":58}]}',
        "invalid apostrophe escape":
            r'{"cases":[{"reasoning":"stays at \'charged with\' throughout"}]}',
        "trailing comma":
            '{"cases":[{"score":58},]}',
        "all three at once":
            '{"cases":[{"note":undefined,"r":"say \'accused\'",},]}',
    }
    for label, payload in cases.items():
        parsed = extract_json(payload)
        assert isinstance(parsed, dict) and "cases" in parsed, \
            f"{label}: did not recover"

    # A dropped closing brace must NOT be silently guessed at — a wrong repair
    # could attach one case's safety verdict to another. It has to fail.
    try:
        extract_json('{"cases":[{"a":{"b":1},{"c":2}]}')
    except Exception:
        pass
    else:
        raise AssertionError("structurally broken JSON was silently 'repaired'")


def test_repair_json_leaves_valid_json_untouched():
    """Repair must never alter a response that already parses."""
    from boydclips.llm import repair_json

    good = json.dumps({
        "cases": [{"summary": "he said 'one time' about his attorney",
                   "path": "a/b", "score": 60.4, "ok": None}]
    })
    assert json.loads(repair_json(good)) == json.loads(good)


def test_safety_rule_ids_match_the_spec():
    """SAFETY_RULE_IDS drifting from SAFETY_RULES.md silently breaks the gate:
    the model cites a rule the validator rejects as an unknown enum value."""
    spec = (ROOT / "spec" / "SAFETY_RULES.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^## (R\d+)\b", spec, re.MULTILINE))
    assert documented == set(analyze.SAFETY_RULE_IDS), (
        f"SAFETY_RULES.md defines {sorted(documented)} but analyze.py declares "
        f"{sorted(analyze.SAFETY_RULE_IDS)}"
    )


# ------------------------------------------------- packaging / thumbnail wire


def test_package_schema_carries_the_yellow_split():
    """publish.py attaches thumbnail_quote.jpg and the renderer needs to know
    which half is yellow. If the schema loses the field the renderer silently
    falls back to a midpoint split and the house style quietly stops being the
    house style."""
    props = analyze.PACKAGE_SCHEMA["properties"]
    assert "thumbnail_quote_yellow" in props
    assert "thumbnail_quote_yellow" in analyze.PACKAGE_SCHEMA["required"]


def test_package_prompt_states_the_thumbnail_contract():
    """The thumbnail pair has a relationship JSON Schema cannot express —
    `thumbnail_quote_yellow` must be a verbatim SUFFIX of `thumbnail_quote`.
    Structure alone will not get that right, so the prompt has to say it. If
    this drifts, the split silently degrades to a word-count midpoint.

    Scoped to that pair deliberately. `longform_title`, `short_title` and
    `guilt_posture_check` are not named in the prompt either — they are carried
    by the schema and described in prose, which has worked — so asserting a
    naming convention across every field would be inventing a standard this
    repo does not hold.
    """
    # prompt_text returns only the USER half; this contract lives in SYSTEM.
    text = (ROOT / "prompts" / "package_post.md").read_text(encoding="utf-8")
    assert "thumbnail_quote_yellow" in text
    assert "suffix" in text.lower(), (
        "package_post.md no longer states that the yellow half must be a "
        "verbatim suffix — split_thumbnail_quote will fall back to a midpoint"
    )


def test_thumbnail_quote_splits_on_a_real_suffix():
    from boydclips.pipeline import split_thumbnail_quote

    white, yellow = split_thumbnail_quote({
        "thumbnail_quote": "This cop was lying!",
        "thumbnail_quote_yellow": "cop was lying!",
    })
    assert (white, yellow) == ("This", "cop was lying!")


def test_thumbnail_quote_rejects_a_non_suffix_and_still_returns_the_quote():
    """A model that paraphrases the yellow half instead of copying it must not
    put text on the thumbnail that the manifest does not record."""
    from boydclips.pipeline import split_thumbnail_quote

    white, yellow = split_thumbnail_quote({
        "thumbnail_quote": "This cop was lying!",
        "thumbnail_quote_yellow": "he lied",
    })
    assert f"{white} {yellow}" == "This cop was lying!"


def test_thumbnail_quote_refuses_when_empty():
    from boydclips.pipeline import split_thumbnail_quote

    try:
        split_thumbnail_quote({"thumbnail_quote": "  "})
    except ValueError:
        return
    raise AssertionError("an empty thumbnail_quote should refuse, not render blank")


# ------------------------------------------------------------ publish guards


def test_publish_refuses_while_the_api_project_is_unaudited():
    """videos.insert from an unaudited project produces a video locked private
    with no appeal, and the duplicate guard then refuses to re-upload it — so
    the case is spent. This must be a refusal, not a warning."""
    from boydclips import publish

    cfg = load_config()
    cfg._data["autonomy"]["mode"] = "auto"
    cfg._data["publish"]["youtube"]["api_audited"] = False

    class _NoStore:
        def publication_url(self, *a, **k):
            return None

    report = publish.publish_pair(
        cfg, _NoStore(),
        longform={"clip_id": 1, "file_path": "x.mp4", "title": "t", "description": "d"},
        short=None,
        context={"hook_line": "h"},
    )
    assert not report["longform"], "an unaudited project must not upload"
    assert any("api_audited" in s for s in report["skipped"]), report["skipped"]


def test_longform_duration_bounds_are_sane():
    """Both bounds are enforced in produce() now; a config where the floor is
    above the cap would reject every case with a confusing message."""
    lf = CFG.require("output.longform")
    assert lf["min_duration_s"] < lf["max_duration_s"]
    assert lf.get("dead_air_s", 4.0) > 0


def test_content_spec_dead_air_threshold_matches_config():
    """CONTENT_SPEC §2 states the threshold in prose and the pipeline reads it
    from config. If they drift, the rendered video stops matching the contract
    it claims to follow — which is exactly how 21% dead air shipped."""
    spec = (ROOT / "spec" / "CONTENT_SPEC.md").read_text(encoding="utf-8")
    stated = re.search(r"[Dd]ead air longer than (\d+(?:\.\d+)?) seconds", spec)
    assert stated, "CONTENT_SPEC §2 no longer states a dead-air threshold"
    assert float(stated.group(1)) == float(CFG.require("output.longform")["dead_air_s"])



def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            print(f"  FAIL  {name}\n          {exc}")
            failed.append(name)
        except Exception as exc:
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")
            failed.append(name)

    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        print("failures: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


# --------------------------------------------------------------------------
# Repeat-defendant lane (repeats.py) — the 1.36x "BACK AGAIN" format.
# --------------------------------------------------------------------------

def _repeat_db(tmp_path, rows, dockets):
    import sqlite3
    db = tmp_path / "r.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE dockets (video_id TEXT, docket_date TEXT)")
    c.execute("CREATE TABLE cases (case_key TEXT, video_id TEXT, defendant TEXT,"
              " cause_number TEXT, total_score REAL, safety_pass INT,"
              " shortable INT, start_s REAL, end_s REAL, proceeding_type TEXT,"
              " created_at TEXT)")
    c.executemany("INSERT INTO dockets VALUES (?,?)", dockets)
    c.executemany("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return c


def test_name_key_normalises_accents_suffixes_and_word_order():
    from boydclips.repeats import name_key
    assert name_key("PEÑA, Arnold Jr.") == name_key("Arnold Pena")
    assert name_key("Jose Ismael Salazar Jr.") == name_key("SALAZAR, Jose Ismael")
    # too short to identify -> unmatchable, not its own group
    assert name_key("Smith") == ""
    assert name_key("") == ""


def test_name_key_does_not_merge_different_people():
    from boydclips.repeats import name_key
    assert name_key("Jose Garcia") != name_key("Jose Garza")
    assert name_key("Robert Castillo") != name_key("Roberto Castillo")


def test_find_episodes_requires_two_distinct_dockets(tmp_path):
    from boydclips.repeats import find_episodes
    # same person twice in ONE docket is not a return appearance
    conn = _repeat_db(tmp_path,
        [("k1", "v1", "Eric Mason", None, 80.0, 1, 1, 0, 600, "plea", "t"),
         ("k2", "v1", "MASON, Eric", None, 70.0, 1, 1, 700, 1200, "reset", "t")],
        [("v1", "2026-08-01")])
    assert find_episodes(conn) == []


def test_find_episodes_groups_across_dockets_in_chronological_order(tmp_path):
    from boydclips.repeats import find_episodes
    conn = _repeat_db(tmp_path,
        [("k2", "v2", "MASON, Eric", None, 70.0, 1, 1, 0, 600, "reset", "t"),
         ("k1", "v1", "Eric Mason", None, 80.0, 1, 1, 0, 600, "plea", "t")],
        [("v1", "2026-08-01"), ("v2", "2026-08-09")])
    eps = find_episodes(conn)
    assert len(eps) == 1
    assert eps[0].dockets == 2
    assert eps[0].best_score == 80.0
    # oldest first — the format is watching someone come back, not a flashback
    assert [h["case_key"] for h in eps[0].hearings] == ["k1", "k2"]


def test_disagreeing_cause_numbers_split_a_name_group(tmp_path):
    from boydclips.repeats import find_episodes
    conn = _repeat_db(tmp_path,
        [("k1", "v1", "Jose Garcia", "2025CR001529", 80.0, 1, 1, 0, 60, "p", "t"),
         ("k2", "v2", "Jose Garcia", "2024 CR 0007", 80.0, 1, 1, 0, 60, "p", "t")],
        [("v1", "2026-08-01"), ("v2", "2026-08-09")])
    # two different men who share a very common Bexar County name
    assert find_episodes(conn) == []


def test_qualifying_respects_score_and_safety_gates(tmp_path):
    from boydclips.repeats import qualifying
    rows = [("k1", "v1", "Kit Kilpatrick", None, 85.0, 1, 1, 0, 600, "p", "t"),
            ("k2", "v2", "Kit Kilpatrick", None, 30.0, 1, 1, 0, 600, "r", "t"),
            ("k3", "v1", "Adam Gonzalez", None, 82.0, 1, 1, 0, 600, "p", "t"),
            ("k4", "v2", "Adam Gonzalez", None, 66.0, 0, 1, 0, 600, "r", "t")]
    conn = _repeat_db(tmp_path, rows, [("v1", "2026-08-01"), ("v2", "2026-08-09")])
    cfg = {"enabled": True, "min_dockets": 2, "min_best_score": 50,
           "require_all_safety_pass": True}
    got = [e.defendant for e in qualifying(conn, cfg)]
    assert got == ["Kit Kilpatrick"]          # a weak SECOND hearing is fine
    cfg2 = {**cfg, "require_all_safety_pass": False}
    assert len(qualifying(conn, cfg2)) == 2   # a FAILED safety hearing is not
    assert qualifying(conn, {**cfg, "enabled": False}) == []


# --------------------------------------------------------------------------
# On-camera probe (oncamera.py) — is anyone in the other Zoom window?
#
# Calibration ground truth, measured 2026-08-18 on real frames:
#   Thompson  465 / 678 detail, 0.56 / 0.54 dark  -> usable   (approved short)
#   Rodriguez 628 / 467 detail, 0.54 / 0.52 dark  -> usable   (approved short)
#   Blackburn 617 / 679 detail, 0.41 / 0.39 dark  -> usable   (people visible)
#   Pena       50 /  69 detail, 0.91 / 0.91 dark  -> NOT usable (black name card)
# --------------------------------------------------------------------------

def _tile(name, detail, dark, motion=10.0, faces=0):
    from boydclips.oncamera import Tile
    return Tile(name, motion, detail, faces, dark)


def test_real_courtroom_tiles_read_as_live():
    for detail, dark in ((465, 0.56), (678, 0.54), (628, 0.54), (617, 0.41)):
        assert _tile("t", detail, dark).live


def test_black_name_card_reads_as_dead():
    # Pena's actual numbers. This is the case the probe exists to reject.
    for detail, dark in ((50, 0.91), (69, 0.91), (91, 0.92)):
        assert not _tile("t", detail, dark).live


def test_dark_share_overrides_edge_energy():
    # A mostly-black tile is a name card no matter how sharp its text is.
    assert not _tile("t", detail=9000, dark=0.95).live
    assert _tile("t", detail=9000, dark=0.10).live


def test_faces_never_decide_on_their_own():
    # Haar misses profiles constantly — Thompson scored 0 faces and is good.
    assert _tile("t", 465, 0.56, faces=0).live
    assert not _tile("t", 50, 0.91, faces=3).live


def test_verdict_needs_two_live_tiles():
    from boydclips.oncamera import Verdict
    live, dead = _tile("l", 465, 0.5), _tile("r", 50, 0.91)
    assert Verdict(2, [live, live], 6, "2up").usable
    assert not Verdict(1, [live, dead], 6, "2up").usable
    assert "name card" in Verdict(1, [live, dead], 6, "2up").reason
    assert not Verdict(0, [dead, dead], 6, "2up").usable


def test_no_frames_is_not_a_pass():
    from boydclips.oncamera import Verdict
    v = Verdict(0, [], 0, "2up")
    assert not v.usable and "no frames" in v.reason


def test_region_split_covers_the_frame_exactly():
    from boydclips.oncamera import _regions
    for layout, n in (("2up", 2), ("grid", 4), ("single", 1)):
        r = _regions(1280, 720, layout)
        assert len(r) == n
        area = sum((x2 - x1) * (y2 - y1) for _, (x1, y1, x2, y2) in r)
        assert area == 1280 * 720


# --------------------------------------------------------------------------
# Moment mining (moments.py) — where Judge Boyd chews somebody out.
#
# The product is a MOMENT, not a case. Every filter below exists because the
# ranking WITHOUT it was measurably wrong on the 352-transcript archive, and
# each test pins the specific failure it fixed.
# --------------------------------------------------------------------------

class _W:
    def __init__(self, t, w):
        self.t, self.w = t, w


class _T:
    """Minimal stand-in for Transcript — moments.py only reads .words/.video_id."""
    def __init__(self, video_id, turns):
        self.video_id = video_id
        self.words = []
        t = 0.0
        for txt in turns:
            toks = txt.split()
            self.words.append(_W(t, ">> " + toks[0]))
            for w in toks[1:]:
                t += 0.4
                self.words.append(_W(t, w))
            t += 1.0


CHEWOUT = (
    "let me just tell you I do not smoke cigarettes right never done drugs never did "
    "but what I can tell you anybody who comes in I can smell cigarette smoke on them "
    "you can chew all the spearmint gum you want then you just smell like spearmint gum "
    "guess what you need to understand the consequences of your choices because your "
    "excuses about marijuana and the drug test are not going to work in this court "
    "you are an adult and you have to take responsibility for your probation violation"
)

BOILERPLATE = (
    "the court will find there is sufficient evidence to find you guilty and the court "
    "is going to place you on community supervision with your attorney there will be no "
    "employment as a home health care provider or with minors and field visits one time "
    "per month and proof of employment within days and court costs and fees are assessed "
    "and you must report to the probation department do you understand these conditions"
)

# A real docket roll call, which took 4 of the top 8 before proper-noun
# suppression: nothing but names, so every token is a corpus hapax. The
# trailing "the court is calling" is what makes it look judicial.
ROLLCALL = (
    "thank you Luis Alec Martinez Carlos Pettis Emanuel Moses Perez David Escabedo "
    "Diana Marcia Nicholas Carion Josh Randall Sanchez Emanuel Chavaria Ashley Medina "
    "Jason Donahue Demontay Williams Jacob Dilday Daryl Harper Kenneth Salinas Guzman "
    "Antonio Carrizales Teresa Zamora Shane Collette Akira Santiago Deamber Cross "
    "all right the court is calling the next names on this docket present custody"
)

BANTER_TURN = (
    "let me just tell you this if you need a hug concerning the football season Sean is "
    "right over there with her Pittsburgh Steelers and he said he was deeply disappointed "
    "with the Texas teams and I told LSU not to hire that coach but guess what they are "
    "not listening to me and you know the whole coaching package thing is ridiculous"
)


def _idf_for(*texts):
    from boydclips import moments
    return moments.build_idf(list(texts))


def test_chewout_is_kept_and_boilerplate_is_dropped():
    from boydclips import moments
    t = _T("vid", [CHEWOUT, BOILERPLATE])
    kept = [txt for _a, _b, txt in moments.judicial_turns(t)]
    assert any("spearmint" in k for k in kept)
    assert not any("home health care provider" in k for k in kept)


def test_rollcall_is_dropped():
    # Every name is a corpus hapax, so novelty alone ranked roll call top-8.
    from boydclips import moments
    t = _T("vid", [ROLLCALL])
    assert moments.judicial_turns(t) == []


def test_banter_is_dropped():
    # She talks about LSU and the Steelers between cases: novel, second-person,
    # and nobody is being held to account.
    from boydclips import moments
    t = _T("vid", [BANTER_TURN])
    assert moments.judicial_turns(t) == []


def test_cross_examination_is_not_attributed_to_the_judge():
    from boydclips import moments
    cross = ("objection hearsay sustained okay now showing you what has been marked as "
             "states exhibit four do you recognize it yes sir and you told the officer "
             "that you were not there correct no further questions I will pass the witness "
             "and you understand that you have to answer truthfully about the offense")
    assert moments.judicial_turns(_T("vid", [cross])) == []


def test_dropped_speaker_marker_turns_are_rejected():
    # Two deferential replies inside ONE turn means the caption stream lost a '>>'.
    from boydclips import moments
    mixed = ("you need to explain your excuses about the drug test yes sir I understand "
             "and the probation violation is a choice not a mistake yes sir I know that "
             "and you have to take responsibility as an adult for these consequences now")
    assert moments.judicial_turns(_T("vid", [mixed])) == []


def test_proper_nouns_do_not_inflate_novelty():
    """A token capitalised in >60% of its appearances is a name and is excluded.

    Detection needs the token seen at least twice, so the fixture repeats the
    names — a single-appearance name in a three-document corpus is
    indistinguishable from any other hapax, and that is intended.
    """
    from boydclips import moments
    idf = _idf_for(ROLLCALL, ROLLCALL, CHEWOUT, BOILERPLATE)
    proper = idf["__PROPER__"]
    assert {"martinez", "sanchez", "zamora"} <= proper
    # ordinary vocabulary must survive, or novelty measures nothing
    assert not ({"spearmint", "consequences", "excuses"} & proper)


def test_novelty_ignores_a_roll_call_once_names_are_removed():
    from boydclips import moments
    idf = _idf_for(ROLLCALL, ROLLCALL, CHEWOUT, CHEWOUT, BOILERPLATE)
    assert moments.novelty(CHEWOUT, idf) > moments.novelty(ROLLCALL, idf)


def test_address_rates_separate_a_chewout_from_a_recital():
    """Second-person density is what removed expert testimony and roll call."""
    from boydclips import moments
    you_c, i_c = moments.address_rates(CHEWOUT)
    you_r, _i_r = moments.address_rates(ROLLCALL)
    assert you_c > moments.MIN_YOU_RATE
    assert i_c > 0
    assert you_r < moments.MIN_YOU_RATE


def test_expert_testimony_is_rejected_by_attribution_not_by_address_rate():
    """Recorded because a test asserting the opposite failed.

    A pathologist says "you can see" constantly, so the second-person floor
    does NOT remove expert testimony - it clears it. What removes it is that
    the turn is not the bench speaking and it carries examination markers.
    """
    from boydclips import moments
    expert = ("you can see the irregular contour of that nasal bridge and the purple "
              "discoloration from the hemorrhage beneath the skin and you can see the "
              "laceration right over that fracture site now publishing states exhibit "
              "forty six do you understand what that photograph shows about the offense")
    you_e, _ = moments.address_rates(expert)
    assert you_e > moments.MIN_YOU_RATE          # the floor does not catch it
    assert moments.judicial_turns(_T("vid", [expert])) == []   # attribution does


def test_scan_scores_and_orders_moments():
    from boydclips import moments
    idf = _idf_for(CHEWOUT, BOILERPLATE, ROLLCALL, BANTER_TURN)
    got = moments.scan(_T("vid", [CHEWOUT, BOILERPLATE, ROLLCALL]), idf)
    assert len(got) == 1
    m = got[0]
    assert m.score > 0 and m.words > 45
    assert "guess what" in m.labels
    assert m.url.startswith("https://www.youtube.com/watch?v=vid&t=")


def test_turns_split_on_the_marker():
    from boydclips import moments
    t = _T("v", ["alpha beta gamma", "delta epsilon zeta"])
    got = moments.turns(t)
    assert len(got) == 2
    assert ">>" not in got[0][2] and got[0][2].startswith("alpha")


# --------------------------------------------------------------------------
# Moment -> case adapter (momentrun.py).
#
# produce() reads seven fields off a case. A judged moment supplies all seven,
# which is why the moment product needed an adapter and not a new renderer —
# CONTENT_SPEC Form B ("one contiguous stretch, one segment, beat 'moment'")
# was already the shape.
# --------------------------------------------------------------------------

def _judged(**over):
    base = {
        "is_boyd": True, "safe_to_publish": True, "out_of_pocket": 93,
        "hook_quote": "You can chew all the spearmint gum you want",
        "why": "an autobiographical riff about her own nose",
        "context_needed": "A mother said she only smokes away from home.",
        "speaker_note": "", "clip_start_offset_s": 15, "clip_end_offset_s": 73,
        "_c": {"video_id": "zHchVGBX9iA", "start_s": 10721.0},
    }
    base.update(over)
    return base


def test_adapter_supplies_every_field_produce_reads():
    from boydclips import momentrun
    c = momentrun.moment_to_case(_judged())
    for k in ("start_s", "end_s", "hook_start_s", "proceeding_type",
              "shortable", "shortable_reasoning", "short_segments"):
        assert k in c, k
    assert c["start_s"] == 10736.0 and c["end_s"] == 10794.0
    assert c["hook_start_s"] == c["start_s"]


def test_adapter_emits_form_b_not_a_four_beat():
    from boydclips import momentrun
    c = momentrun.moment_to_case(_judged())
    assert c["short_form"] == "single_moment"
    assert [s["beat"] for s in c["short_segments"]] == ["moment"]
    seg = c["short_segments"][0]
    assert (seg["start_s"], seg["end_s"]) == (c["start_s"], c["end_s"])


def test_segments_survive_plan_short_segments_clamping():
    """plan_short_segments clamps every beat to [case_start, case_end] so a
    short can never take audio from the previous defendant. A moment's own
    window IS that boundary, so nothing may be clamped away."""
    from boydclips import momentrun, render
    c = momentrun.moment_to_case(_judged())
    got = render.plan_short_segments(c, {})
    assert got is not None and len(got) == 1
    assert abs(got[0].duration - 58.0) < 0.01


def test_not_boyd_is_refused():
    from boydclips import momentrun
    import pytest
    with pytest.raises(momentrun.MomentError, match="not Boyd"):
        momentrun.moment_to_case(_judged(is_boyd=False, speaker_note="defence counsel"))


def test_unsafe_is_refused():
    from boydclips import momentrun
    import pytest
    with pytest.raises(momentrun.MomentError, match="unsafe"):
        momentrun.moment_to_case(_judged(safe_to_publish=False))


def test_too_short_is_refused_and_too_long_is_trimmed_at_the_tail():
    from boydclips import momentrun
    import pytest
    with pytest.raises(momentrun.MomentError, match="floor"):
        momentrun.moment_to_case(_judged(clip_start_offset_s=0, clip_end_offset_s=8))
    # The hook is at the top and the judge ends ON the line, so slack is at the
    # end — trimming must never move the start.
    c = momentrun.moment_to_case(_judged(clip_start_offset_s=10, clip_end_offset_s=400))
    assert c["start_s"] == 10731.0
    assert c["end_s"] - c["start_s"] == momentrun.MAX_CLIP_S


def test_inverted_offsets_are_refused():
    from boydclips import momentrun
    import pytest
    with pytest.raises(momentrun.MomentError, match="not after"):
        momentrun.moment_to_case(_judged(clip_start_offset_s=90, clip_end_offset_s=30))


def test_guilt_posture_defaults_to_accused():
    """A moment carries no plea colloquy, so it can never establish more."""
    from boydclips import momentrun
    assert momentrun.moment_to_case(_judged())["guilt_posture"] == "accused"


def test_moment_source_is_what_exempts_the_longform_floor():
    """A 58s moment failing a 120s long-form floor is the floor being asked the
    wrong question. The exemption keys on case["source"], which only
    momentrun.moment_to_case sets — a hand-built short case must still fail."""
    from boydclips import momentrun
    c = momentrun.moment_to_case(_judged())
    assert c["source"] == "moments"
    assert c["end_s"] - c["start_s"] < 120


def test_moment_case_row_satisfies_save_case(tmp_path):
    """clips.case_key is a FK to cases.case_key, so a moment must be saveable
    as a case row before produce() writes a clip — otherwise the encode is
    paid for and then thrown away on a constraint error."""
    from boydclips import momentrun
    from boydclips.state import Store
    c = momentrun.moment_to_case(_judged())
    store = Store(tmp_path / "t.db")
    store.add_docket("zHchVGBX9iA", "docket", "2026-04-01", 10800.0)
    key = store.save_case("zHchVGBX9iA", c, None)
    assert key == "zHchVGBX9iA:10736"
    row = store.get_case(key)
    assert row["safety"]["safety_pass"] is True
    assert row["shortable"] and row["total_score"] == 93.0
    store.close()


def test_moment_carries_a_scores_block_with_only_its_own_axis():
    """_write_manifest reads case["scores"]. A moment has one axis; faking the
    five case dimensions would put a pushback score in the manifest that the
    judge never gave."""
    from boydclips import momentrun
    sc = momentrun.moment_to_case(_judged())["scores"]
    assert list(sc) == ["out_of_pocket"]
    assert sc["out_of_pocket"]["score"] == 93.0
    assert sc["out_of_pocket"]["justification"]


# ---------------------------------------------------------------- BOYD_EDITORIAL_V2 stabilisation


def test_old_rubric_cache_is_stale_not_reused():
    """A scored.json written under the retired rubric (a bare list, no version
    stamp) or under any other prompt version must be rejected, never ranked."""
    from boydclips import editorial
    v = analyze.current_rubric_version()
    assert editorial.RULESET in v
    old_list = [_case()]                                   # pre-V2 cache shape
    cases, why = analyze.score_cache_load(old_list, v)
    assert cases is None and "retired" in why
    other = analyze.score_cache_dump([dict(_case(), rubric_version="1.1.0")], "1.1.0")
    cases, why = analyze.score_cache_load(other, v)
    assert cases is None and "1.1.0" in why
    mixed = analyze.score_cache_dump([dict(_case(), rubric_version=v), _case()], v)
    cases, why = analyze.score_cache_load(mixed, v)
    assert cases is None and "different rubric_version" in why
    good = analyze.score_cache_dump([dict(_case(), rubric_version=v)], v)
    cases, why = analyze.score_cache_load(good, v)
    assert cases and why == "current"


class _StubBackend:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, system, user, schema, label):
        self.calls.append(label)
        return json.loads(json.dumps(self.response))


def _v2_response(start_s=10.0, end_s=200.0, total_scores=None):
    from boydclips import editorial
    scores = total_scores or {d: mx for d, mx in editorial.DIMENSIONS.items()}
    return {"cases": [{
        "start_s": start_s, "end_s": end_s, "defendant_name": "X", "cause_number": "c",
        "proceeding_type": "sentencing", "guilt_posture": "pled_guilty",
        "safety": {"safety_pass": True, "safety_rule_violations": [], "safety_reasoning": "r"},
        "scores": {d: {"score": v, "justification": "j"} for d, v in scores.items()},
        "editorial": {"gate_pass": True, "gate_failures": [], "story_angle": "a", "money_moment": "m",
                      "money_moment_s": 50.0, "why_viewer_cares": "w", "title_angles": ["1", "2", "3"],
                      "weakness": "x", "decision": "MAKE"},
        "audio_quality": 4, "hook_quote": "h", "hook_start_s": 20.0, "shortable": True,
        "short_form": "single_moment", "shortable_reasoning": "r",
        "short_segments": [{"beat": "moment", "start_s": 20.0, "end_s": 60.0, "quote": "q"}],
        "summary": "s",
    }]}


def _stub_analyzer(response):
    an = analyze.Analyzer.__new__(analyze.Analyzer)
    an.cfg, an.log, an.prompt_versions = CFG, None, {}
    an.backend = _StubBackend(response)
    return an


def test_score_stamps_rubric_version_and_cache_roundtrips():
    """Every scored case carries the score prompt's version; a cache written
    from it loads under the same version and is stale under any other."""
    tr = Transcript(video_id="x", words=[Word(t=float(i), w=f"w{i}") for i in range(0, 260)])
    an = _stub_analyzer(_v2_response())
    scored = an.score(tr, [{"start_s": 10.0, "end_s": 200.0}], {"title": "t", "docket_date": "d", "url": "u"})
    v = analyze.current_rubric_version()
    assert scored and scored[0]["rubric_version"] == v == an.prompt_versions["score_cases"]
    assert scored[0]["total_score"] == 100.0 and scored[0]["decision"] == "MAKE" and scored[0]["eligible"]
    dump = analyze.score_cache_dump(scored, v)
    assert analyze.score_cache_load(json.loads(json.dumps(dump)), v)[0] is not None
    assert analyze.score_cache_load(json.loads(json.dumps(dump)), "3.0.0+SOMETHING_ELSE")[0] is None


def test_repeat_defendant_tiebreak_semantics():
    """PART 5: continuity breaks ties only inside the window, after the gates."""
    from boydclips import editorial
    gates = CFG.require("analysis.gates")
    window = float(CFG.get("analysis.repeat_defendant.tie_break_window", editorial.REPEAT_TIE_WINDOW))
    assert window == 3.0
    mk = lambda name, total, rep: dict(_case(total_score=float(total)), defendant_name=name, _rep=rep)
    rep = lambda c: c["_rep"]
    order = lambda cs: [c["defendant_name"] for c in editorial.tiebreak_order(cs, rep, window)]
    # 88 one-off beats 79 repeat
    assert order([mk("rep79", 79, True), mk("one88", 88, False)]) == ["one88", "rep79"]
    # 83 repeat may beat 85 one-off inside the window
    assert order([mk("one85", 85, False), mk("rep83", 83, True)]) == ["rep83", "one85"]
    # 81 repeat does not beat 85 (outside the window)
    assert order([mk("one85", 85, False), mk("rep81", 81, True)]) == ["one85", "rep81"]
    # a HOLD (75) or SKIP (60) repeat never rescues itself over a MAKE one-off:
    # the gates run first and it is not in the list the tie-break sees.
    scored = [mk("hold75rep", 75, True), mk("skip60rep", 60, True), mk("make79", 79, False)]
    for c in scored:
        c["eligible"], c["ineligible_reason"] = analyze._check_gates(c, gates)
    eligible = [c for c in scored if c["eligible"]]
    assert [c["defendant_name"] for c in eligible] == ["make79"]
    assert order(eligible) == ["make79"]
    # and no multiplier: two repeats compare on raw totals
    assert order([mk("rep80", 80, True), mk("rep84", 84, True)]) == ["rep84", "rep80"]


# ---------------------------------------------------------------- story-preserving cap (capfit)


def _cap_case(mm=None, segs=None, start=1000.0, end=2400.0):
    c = {"start_s": start, "end_s": end}
    if mm is not None:
        c["editorial"] = {"money_moment_s": mm}
    if segs:
        c["short_segments"] = [{"beat": b, "start_s": a, "end_s": e, "quote": "q"} for b, a, e in segs]
    return c


def _total(pieces):
    return sum(p.duration for p in pieces)


def _kept(pieces, a, b):
    return sum(max(0.0, min(p.end_s, b) - max(p.start_s, a)) for p in pieces)


def test_capfit_under_cap_is_unchanged():
    from boydclips import capfit
    pieces = [render.Segment(1000.0, 1300.0), render.Segment(1400.0, 1900.0)]
    plan = capfit.plan_cap_fit(pieces, 1200.0, _cap_case(mm=1850.0))
    assert not plan.changed and plan.pieces == pieces and plan.after_s == 800.0


def test_capfit_payoff_near_end_survives():
    """The exact failure: 1,387 s of pieces, payoff + ruling in the last two
    minutes. The old walk kept the first 1,200 s and cut the ruling."""
    from boydclips import capfit
    pieces = [render.Segment(5773.0, 6129.0), render.Segment(6299.0, 6336.0),
              render.Segment(6427.0, 7160.0)]            # 356 + 37 + 733 = 1126 -> pad to 1387 with a 4th run
    pieces = [render.Segment(5773.0, 6129.0), render.Segment(6299.0, 7160.0), render.Segment(7160.0, 7421.0)]
    assert abs(_total(pieces) - 1478.0) < 1e-6
    case = _cap_case(mm=7300.0, start=5773.0, end=7421.0)
    plan = capfit.plan_cap_fit(pieces, 1200.0, case)
    assert plan.changed and plan.after_s <= 1200.0 + 1e-6
    # the money-moment window and the ending are intact
    assert abs(_kept(plan.pieces, 7270.0, 7360.0) - 90.0) < 1e-6
    assert abs(_kept(plan.pieces, 7421.0 - 45.0, 7421.0) - 45.0) < 1e-6
    assert plan.pieces[-1].end_s == 7421.0
    # and the setup survived too
    assert abs(_kept(plan.pieces, 5773.0, 5863.0) - 90.0) < 1e-6
    # the old behaviour would have ended at 7017.3, 404 s before the case ends
    assert plan.money_moment_source == "editorial.money_moment_s"


def test_capfit_sacrifices_far_middle_before_payoff():
    from boydclips import capfit
    # setup 0-200 | far middle 200-1100 | payoff run 1100-1400 (money moment 1300) | ending inside it
    pieces = [render.Segment(0.0, 200.0), render.Segment(200.0, 1100.0), render.Segment(1100.0, 1400.0)]
    plan = capfit.plan_cap_fit(pieces, 900.0, _cap_case(mm=1300.0, start=0.0, end=1400.0))
    assert plan.after_s <= 900.0 + 1e-6
    assert abs(_kept(plan.pieces, 1270.0, 1360.0) - 90.0) < 1e-6      # payoff window whole
    assert abs(_kept(plan.pieces, 1355.0, 1400.0) - 45.0) < 1e-6      # ending whole
    assert abs(_kept(plan.pieces, 0.0, 90.0) - 90.0) < 1e-6           # setup whole
    dropped = sum(b - a for a, b in plan.dropped)
    assert dropped >= 500.0 - 1e-6
    # everything dropped lies in the far middle, not next to the story
    assert all(200.0 <= a and b <= 1100.0 for a, b in plan.dropped), plan.dropped
    # what was kept of the middle is the part nearest an anchor (contiguous with setup or payoff)
    mids = [(p.start_s, p.end_s) for p in plan.pieces if 200.0 <= p.start_s < 1100.0]
    assert mids and all(a == 200.0 or b == 1100.0 for a, b in mids), mids


def test_capfit_refuses_when_protected_story_cannot_fit():
    from boydclips import capfit
    pieces = [render.Segment(0.0, 1000.0)]
    with pytest.raises(capfit.CapFitError) as e:
        capfit.plan_cap_fit(pieces, 150.0, _cap_case(mm=500.0, start=0.0, end=1000.0))
    assert "refusing" in str(e.value) and "150s cap" in str(e.value)


def test_capfit_never_exceeds_cap_and_keeps_protected():
    """Property over a deterministic grid of shapes: total <= cap, protected
    regions whole, chronological, no piece boundary bridged."""
    from boydclips import capfit
    import itertools
    shapes = [
        [(0, 400), (450, 900), (950, 1500)],
        [(0, 120), (130, 1300), (1310, 1400), (1405, 1700)],
        [(100, 2000)],
        [(0, 300), (2000, 2300), (2300, 2600)],
    ]
    for shape, cap, mm_frac in itertools.product(shapes, (600.0, 900.0, 1200.0), (0.2, 0.55, 0.93)):
        pieces = [render.Segment(float(a), float(b)) for a, b in shape]
        lo, hi = pieces[0].start_s, pieces[-1].end_s
        case = _cap_case(mm=lo + mm_frac * (hi - lo), start=lo, end=hi,
                         segs=[("hook", lo + 10, lo + 16), ("button", hi - 20, hi - 8)])
        try:
            plan = capfit.plan_cap_fit(pieces, cap, case)
        except capfit.CapFitError:
            continue                                   # explicit refusal is allowed
        assert plan.after_s <= cap + 1e-6, (shape, cap, mm_frac, plan.after_s)
        starts = [p.start_s for p in plan.pieces]
        assert starts == sorted(starts)
        for a, b in plan.protected:
            want = _kept(pieces, a, b)
            assert abs(_kept(plan.pieces, a, b) - want) < 1e-6, (shape, cap, mm_frac, a, b)
        for p in plan.pieces:                          # every kept piece lies inside one original piece
            assert any(o.start_s - 1e-9 <= p.start_s and p.end_s <= o.end_s + 1e-9 for o in pieces)
        if _total(pieces) <= cap:
            assert not plan.changed


def test_capfit_money_moment_fallbacks():
    from boydclips import capfit
    lo, hi = 0.0, 1000.0
    assert capfit.resolve_money_moment(_cap_case(mm=400.0, segs=[("turn", 600, 620)]), lo, hi) == (400.0, "editorial.money_moment_s")
    assert capfit.resolve_money_moment(_cap_case(segs=[("turn", 600, 620)]), lo, hi) == (600.0, "short_segments.turn")
    assert capfit.resolve_money_moment({"hook_start_s": 50.0}, lo, hi) == (50.0, "hook_start_s")
    t, src = capfit.resolve_money_moment(_cap_case(mm=5000.0), lo, hi)      # outside the case -> ignored, said so
    assert t is None and "outside" in src


def test_capfit_interior_cuts_snap_to_pauses_outward_only():
    from boydclips import capfit
    pieces = [render.Segment(0.0, 1400.0)]
    case = _cap_case(mm=1300.0, start=0.0, end=1400.0)
    plain = capfit.plan_cap_fit(pieces, 900.0, case)
    (d0, d1), = plain.dropped
    # pauses just outside both cut edges: the cut must widen onto them
    gaps = [(d0 - 2.0, d0 - 1.5), (d1 + 1.0, d1 + 1.8)]
    snapped = capfit.plan_cap_fit(pieces, 900.0, case, gaps=gaps, snap_s=3.0)
    (s0, s1), = snapped.dropped
    assert abs(s0 - (d0 - 1.5)) < 1e-6 and abs(s1 - (d1 + 1.0)) < 1e-6
    assert snapped.after_s <= plain.after_s + 1e-6 <= 900.0 + 1e-6      # never more kept
    assert abs(_kept(snapped.pieces, 1270.0, 1360.0) - 90.0) < 1e-6      # protected untouched
    # a pause beyond the snap window is ignored
    far = capfit.plan_cap_fit(pieces, 900.0, case, gaps=[(d0 - 10.0, d0 - 9.0)], snap_s=3.0)
    assert far.dropped == plain.dropped
    # word_gaps reads dict or object words
    assert capfit.word_gaps([{"t": 1.0}, {"t": 1.2}, {"t": 3.0}], 0.0, 10.0) == [(1.2, 3.0)]

# ---------------------------------------------------------------- SHORTS_EDITOR_V2


def _script_words(script, t0=100.0, wps=0.32, pause=0.9, gaps=None):
    """Transcript words for a scripted exchange: [(speaker, text), ...].
    Speaker changes carry the '>>' marker the auto-captions use. `gaps` maps
    a turn index to an extra silence inserted BEFORE that turn."""
    from boydclips.transcribe import Word
    words, t = [], t0
    for k, (_spk, txt) in enumerate(script):
        t += (gaps or {}).get(k, 0.0)
        for i, tok in enumerate(txt.split()):
            words.append(Word(t=round(t, 3), w=(">>" + tok if (i == 0 and k > 0) else tok)))
            t += wps
        t += pause
    return words, t


_PHONE_Q = ("boyd", "Explain to me why your phone being stolen interferes with your ability to get a GED.")
_REAL_ANSWER = ("dfd", "Well, I mean, as soon as I enrolled into the class I had got an email and they were "
                       "telling me to show up on this day and I did show up. I did show up and I did talk to some lady")
_LATER_LINE = ("dfd", "and she told me that she was going to send me emails and I never got a Well, I mean, "
                      "my my phone had got stolen, so I don't know if I got the emails or I didn't.")
_RIFF = ("boyd", "Well, here's the thing. So, why didn't you go to the library? You had a chance to "
                 "commit a failure to identify and an evading on foot. So, why you couldn't evade, run towards "
                 "your local library, and get on the computer? Because last time I checked, if your phone gets "
                 "stolen, that doesn't mean your email has been stolen.")
_QUOTE = ("You had a chance to commit a failure to identify and an evading on foot. So, why you couldn't evade, "
          "run towards your local library, and get on the computer? Because last time I checked, if your phone "
          "gets stolen, that doesn't mean your email has been stolen.")
_FLORES = [_PHONE_Q, _REAL_ANSWER, _LATER_LINE, _RIFF, ("dfd", "Yes, ma'am.")]

_EXCHANGE = [
    ("boyd", "All right. State your name for the record and your date of birth."),
    ("dfd",  "Angel Flores. March 3rd 2005."),
    ("boyd", "So you stopped reporting for four months. Why did you stop reporting?"),
    ("dfd",  "My phone got stolen your honor so I didn't know where I was supposed to be."),
    ("boyd", "You had a chance to commit an evading on foot. So why you couldn't evade, run towards your local "
             "library, and get on the computer? Because last time I checked, if your phone gets stolen, "
             "that doesn't mean your email has been stolen."),
    ("dfd",  "Yes ma'am. I understand."),
]
_CAP_STYLE = {"font": "Anton", "font_size": 84, "max_lines": 1, "safe_width": 960, "uppercase": True,
              "rail_x": 540, "rail_y": 960, "mode": "kinetic", "pop_ms": 110, "hold_s": 1.0, "gap_ms": 60}
_LEGACY_CAP_STYLE = {"slot_margins": {"defendant": 1020, "boyd": 700}, "margin_v": 700, "font_size": 140,
                     "max_lines": 2, "max_words_per_card": 3, "max_chars_per_line": 13, "uppercase": True,
                     "animation": "pop_color"}
_TILES = {"boyd": "bottom", "defendant": "top"}


def _v2_plan(script=_EXCHANGE, money_word="library,", cfg=None, case_over=None, t0=100.0, gaps=None,
             tiles=_TILES, quote=None):
    from boydclips import shorts_editor as se
    words, end = _script_words(script, t0=t0, gaps=gaps)
    case = {"start_s": t0 - 5.0, "end_s": end + 5.0, "shortable": True, "editorial": {}}
    if money_word:
        mm = next(w.t for w in words if w.w.lstrip(">") == money_word)
        case["editorial"] = {"money_moment_s": mm, "money_moment": quote or "run towards your local library"}
    case.update(case_over or {})
    c = {"min_score": 40}
    c.update(cfg or {})
    plan = se.plan_short(case, "vid:95", words, c, _CAP_STYLE, tile_map=tiles)
    return plan, words, case


def test_short_v2_plan_is_bound_to_its_case():
    from boydclips import shorts_editor as se
    plan, _w, case = _v2_plan()
    assert plan.ok, plan.refusal
    assert plan.case_key == plan.source_case_key == "vid:95"
    lo, hi = case["start_s"], case["end_s"]
    assert all(lo <= s.start_s and s.end_s <= hi for s in plan.segments)
    se.verify_same_case(plan, "vid:95", case)
    with pytest.raises(se.ShortPlanError):
        se.verify_same_case(plan, "vid:4000", case)
    with pytest.raises(se.ShortPlanError):
        se.verify_same_case(plan, "vid:95", {"start_s": 1000.0, "end_s": 2000.0})
    assert plan.as_dict()["source_case_key"] == "vid:95"


def test_short_v2_executes_validated_producer_sequence_before_keyword_search():
    from boydclips import shorts_editor as se
    words, _end = _script_words(_EXCHANGE, wps=0.5)
    start_s = next(word.t for word in words if word.w == ">>So")
    end_s = words[-1].t
    case = {
        "start_s": start_s,
        "end_s": end_s,
        "shortable": True,
        "editorial": {},
        "producer_short_plan": {
            "decision": "MAKE",
            "chronology_strategy": "chronological",
            "hook_start_s": start_s,
            "hook_end_s": end_s,
            "sequence": [{
                "edit_order": 1,
                "source_order": 1,
                "role": "hook_context_turn_payoff",
                "start_s": start_s,
                "end_s": end_s,
                "quote": " ".join(word.w for word in words if start_s <= word.t <= end_s),
            }],
        },
    }

    plan = se.plan_short(case, "vid:95", words, {"min_score": 40}, _CAP_STYLE, tile_map=_TILES)

    assert plan.ok, plan.refusal
    assert "executed validated Producer Brain sequence" in " ".join(plan.notes)
    assert "alternatives:" in se.describe(plan)
    assert next(g for g in plan.qc if g["gate"] == "producer_alignment")["ok"]
    assert plan.segments[0].start_s <= start_s + 0.2
    assert plan.segments[-1].end_s >= end_s - 0.8
    assert next(beat for beat in plan.beats if beat["role"] == "payoff")

    # The Producer path honours the hook floor too — it used to run QC without
    # any per-dimension floor, so an approved-but-weak opening shipped.
    floor = next(g for g in plan.qc if g["gate"] == "hook_floor")
    assert floor["ok"] and floor["critical"], floor
    strict = se.plan_short(case, "vid:95", words, {"min_score": 40, "hook_min_score": 25},
                           _CAP_STYLE, tile_map=_TILES)
    assert not strict.ok and "hook_floor" in strict.refusal, strict.refusal


def test_short_v2_flores_question_is_followed_by_its_real_answer():
    """THE FLORES REGRESSION. The first render cut Boyd's phone question
    straight to 'and she told me that she was…' — a line about something
    else, 20 s later. The body must be contiguous: the question is followed
    by the answer that followed it, and the bad join is refused by QC."""
    from boydclips import shorts_editor as se
    plan, words, case = _v2_plan(_FLORES, money_word="library,", quote=_QUOTE, t0=200.0)
    assert plan.ok, plan.refusal
    body = plan.body_text
    q = _PHONE_Q[1]
    assert q in body
    after = body[body.index(q) + len(q):].strip()
    assert after.startswith("Well, I mean, as soon as I enrolled"), after[:80]
    assert "and she told me that she was" in body      # kept too, in its place, after the real answer
    assert all(x["ok"] for x in plan.question_answer), plan.question_answer
    assert all(x["ok"] for x in plan.interior_cuts), plan.interior_cuts
    assert next(g for g in plan.qc if g["gate"] == "continuity_gaps")["ok"]
    assert next(g for g in plan.qc if g["gate"] == "question_answer")["ok"]
    # the payoff riff is whole
    payoff = next(b for b in plan.beats if b["role"] == "payoff")
    assert "last time I checked" in payoff["text"] and "You had a chance" in payoff["text"]

    # The exact bad sequence, rebuilt by hand, must fail — deterministically.
    ws = [w for w in words]
    def t_of(token): return next(w.t for w in ws if w.w.lstrip(">") == token)
    q_start, q_end = t_of("Explain") - 0.12, t_of("GED.") + 0.4
    later_start, later_end = t_of("and") - 0.12, t_of("didn't.") + 0.4
    riff_start = t_of("Well,") - 0.12
    riff_end = t_of("stolen.") + 0.4
    bad = {"case_key": "vid:95", "source_case_key": "vid:95", "teaser": None,
           "segments": [[q_start, q_end], [later_start, later_end], [riff_start, riff_end]]}
    with pytest.raises(se.ShortPlanError, match="skips substantive dialogue"):
        se.verify_continuity(bad, words, case)
    audit = se.audit_interior_cuts([render.Segment(a, b) for a, b in bad["segments"]],
                                   se.timed_words(words, case["start_s"], case["end_s"]), [], False, 0.6)
    assert not audit[0]["ok"] and "SUBSTANTIVE" in audit[0]["classes"]
    assert "as soon as I enrolled" in audit[0]["skipped_text"]
    # and the question/answer check names the substitution
    tw = se.timed_words(words, case["start_s"], case["end_s"])
    sents = se.case_sentences(se.label_speakers(se.split_turns(tw)), 0.6)
    q_sent = next(x for x in sents if x.text.startswith("Explain to me"))
    later = next(x for x in sents if x.text.startswith("and she told me"))
    pairs = se.question_answer_pairs([q_sent, later], sents)
    assert pairs and not pairs[0]["ok"]
    assert pairs[0]["source_next"].startswith("Well, I mean, as soon as I enrolled")


def test_short_v2_only_allowed_material_is_cut():
    """Inside the body only dead air, acknowledgments, repeated wording and
    clearly procedural filler may go — and every cut is recorded."""
    script = [
        ("boyd", "So you stopped reporting for four months. Why did you stop reporting? What is your date of birth?"),
        ("dfd",  "March 3rd 2005. My phone got stolen your honor so I didn't know where I was supposed to be."),
        ("boyd", "You had a chance to commit an evading on foot. You had a chance to commit an evading on foot. "
                 "So why you couldn't evade, run towards your local library, and get on the computer?"),
        ("dfd",  "Yes ma'am. I understand."),
    ]
    plan, words, case = _v2_plan(script, gaps={2: 4.0})
    assert plan.ok, plan.refusal
    cuts_text = " ".join(d for b in plan.beats for d in b["dropped"])
    assert "date of birth" in cuts_text, plan.beats
    assert "March 3rd 2005." in cuts_text              # the clerical one-line answer went with its question
    assert cuts_text.count("You had a chance to commit an evading on foot.") == 1   # the repeat, once
    classes = {c for cut in plan.interior_cuts for c in cut["classes"]}
    assert classes <= {"silence", "acknowledgment", "procedural", "clerical answer", "duplicate", "filler", "fragment"}, classes
    assert all(cut["ok"] for cut in plan.interior_cuts)
    for cut in plan.interior_cuts:
        if cut["skipped_text"]:
            assert cut["classes"] and "SUBSTANTIVE" not in cut["classes"]
    # the 4 s pause is not in the short
    raw = plan.segments[-1].end_s - plan.segments[0].start_s
    assert plan.duration_s < raw - 2.5
    assert "Why did you stop reporting?" in plan.body_text and "My phone got stolen" in plan.body_text


def test_short_v2_over_ceiling_moves_the_start_never_the_payoff():
    long_story = [
        ("boyd", "Let me ask you about the last four months. Where were you? " * 4),
        ("dfd",  "Well I was working and my ride fell through and then my mom got sick. " * 4),
        _PHONE_Q, _REAL_ANSWER, _LATER_LINE, _RIFF, ("dfd", "Yes, ma'am."),
    ]
    free, _w, _c = _v2_plan(long_story, money_word="library,", quote=_QUOTE, cfg={"max_duration_s": 200.0})
    assert free.ok and free.duration_s > 59.0
    plan, _w2, _c2 = _v2_plan(long_story, money_word="library,", quote=_QUOTE)
    assert plan.ok, plan.refusal
    assert plan.duration_s <= 59.0 + 1e-6
    payoff = next(b for b in plan.beats if b["role"] == "payoff")
    assert "You had a chance to commit a failure to identify" in payoff["text"]
    assert "that doesn't mean your email has been stolen." in payoff["text"]
    assert plan.segments[0].start_s > free.segments[0].start_s          # started later, not cut inside
    assert all(x["ok"] for x in plan.interior_cuts)
    assert all(x["ok"] for x in plan.question_answer)


def test_short_v2_does_not_pad_a_complete_short_story():
    short_story = [
        _EXCHANGE[2], _EXCHANGE[3],
        ("boyd", "Guess what? Last time I checked the library is free."),
        _EXCHANGE[5],
    ]
    plan, _w, _c = _v2_plan(short_story, money_word="library", t0=200.0)
    assert plan.ok, plan.refusal
    assert 15.0 <= plan.duration_s <= 21.0, plan.duration_s
    assert plan.segments[0].start_s >= 199.0


def test_short_v2_cuts_on_word_boundaries_only():
    from boydclips import shorts_editor as se
    plan, words, case = _v2_plan(gaps={4: 4.0})
    tw = se.timed_words(words, case["start_s"], case["end_s"])
    for seg in plan.segments:
        for t in (seg.start_s, seg.end_s):
            inside = [w for w in tw if w.t + 0.01 < t < w.e - 0.01]
            assert not inside, f"boundary {t} inside {inside[0].w!r}"
    assert next(g for g in plan.qc if g["gate"] == "no_mid_word_cuts")["ok"]


def test_short_v2_teaser_is_declared_and_repeated_in_place():
    from boydclips import shorts_editor as se
    script = [
        ("dfd",  "I got the paperwork from the office and I brought it with me today."),
        ("boyd", "Okay."),
        ("dfd",  "My phone got stolen your honor so I didn't know where I was supposed to be."),
        ("boyd", "Guess what? Last time I checked the library is free. That doesn't mean your email has been stolen."),
        ("dfd",  "Yes ma'am."),
    ]
    plan, _w, _c = _v2_plan(script, money_word="library", cfg={"hook_teaser_below": 30})
    assert plan.ok, plan.refusal
    assert plan.nonlinear and plan.teaser, plan.notes
    ta, tb = plan.teaser["start_s"], plan.teaser["end_s"]
    payoff = next(b for b in plan.beats if b["role"] == "payoff")
    assert payoff["start_s"] - 0.2 <= ta and tb <= payoff["end_s"] + 0.2
    assert plan.segments[0].start_s == ta and plan.segments[0].end_s == tb
    body = plan.segments[1:]
    assert all(b.start_s >= a.end_s - 1e-6 for a, b in zip(body, body[1:]))
    assert next(g for g in plan.qc if g["gate"] == "teaser_declared_and_repeated")["ok"]
    se.verify_chronology(plan)
    # the teased words carry captions at BOTH output occurrences
    times = sorted(t for c in plan.captions for t, w in c["words"] if w == "checked")
    assert len(times) == 2 and times[0] < tb - ta < times[1], (times, plan.captions[:6])


def test_short_v2_declared_teaser_satisfies_the_hook_floor():
    """A cold-open teaser IS the editor's answer to a weak natural hook, so it
    satisfies the hook floor: the line the viewer hears first is the strongest
    one, and it appears again in place. Set the floor above the dimension's own
    maximum so only a declared teaser can pass."""
    script = [
        ("dfd",  "I got the paperwork from the office and I brought it with me today."),
        ("boyd", "Okay."),
        ("dfd",  "My phone got stolen your honor so I didn't know where I was supposed to be."),
        ("boyd", "Guess what? Last time I checked the library is free. That doesn't mean your email has been stolen."),
        ("dfd",  "Yes ma'am."),
    ]
    plan, _w, _c = _v2_plan(script, money_word="library",
                            cfg={"hook_teaser_below": 30, "hook_min_score": 30})
    assert plan.ok, plan.refusal
    assert plan.nonlinear and plan.teaser, plan.notes
    assert plan.scores["hook"] < 30, plan.scores
    floor = next(g for g in plan.qc if g["gate"] == "hook_floor")
    assert floor["ok"] and "teaser" in floor["detail"], floor


def test_short_v2_ending_must_complete_its_line():
    """THE 2725 ENDING. The saved bHAuH5U4NYI:2725 Short stops on
    "...all right and here's the thing I" and the rest of that sentence never
    plays; every technical gate passed. The ending is now checked against the
    source: the last kept word must end a sentence, be followed by a real
    pause, or be the last word of the case."""
    from boydclips import shorts_editor as se

    def tw(items):
        return [se.TWord(i=i, t=t, e=t + 0.4, w=w) for i, (t, w) in enumerate(items)]

    # the recorded 2725 boundary, rebuilt: "...here's the thing I" then "understand" 0.28 s later
    source = tw([(3571.40, "check"), (3571.80, "all"), (3571.92, "right"), (3572.08, "and"),
                 (3572.24, "here's"), (3572.48, "the"), (3572.64, "thing"), (3573.64, "I"),
                 (3574.20, "understand"), (3574.48, "because")])
    kept = source[:8]
    ok, detail = se.last_word_completes_a_line(kept, source, {"sentence_gap_s": 0.6})
    assert not ok, detail
    assert "mid-sentence" in detail and "'I'" in detail, detail

    # control 1: the same words, but the line really did end there (a real pause)
    paused = tw([(3571.40, "check"), (3573.64, "now."), (3576.20, "Next")])
    assert se.last_word_completes_a_line(paused[:2], paused, {"sentence_gap_s": 0.6})[0]

    # control 2: sentence-final punctuation alone is enough without a pause
    ended = tw([(1.0, "you"), (1.4, "understand?")])
    assert se.last_word_completes_a_line(ended[:2], ended, {"sentence_gap_s": 0.6})[0]

    # control 3: the last word of the case cannot be "chopped"
    tail = tw([(1.0, "court"), (1.4, "adjourned")])
    assert se.last_word_completes_a_line(tail[:2], tail, {"sentence_gap_s": 0.6})[0]

    # and every planned Short carries the gate as a critical check
    plan, _w, _c = _v2_plan()
    assert plan.ok, plan.refusal
    gate = next(g for g in plan.qc if g["gate"] == "ending_is_a_complete_line")
    assert gate["ok"] and gate["critical"], gate


def test_short_v2_reordered_segments_are_refused():
    from boydclips import shorts_editor as se
    plan, _w, _c = _v2_plan()
    d = plan.as_dict()
    d["segments"] = list(reversed(d["segments"]))
    with pytest.raises(se.ShortPlanError, match="out of order"):
        se.verify_chronology(d)
    d = plan.as_dict()
    d["teaser"] = {"start_s": d["segments"][-1][0], "end_s": d["segments"][-1][1], "text": "x", "source": "x"}
    d["segments"] = [d["segments"][-1]] + d["segments"][:-1]
    with pytest.raises(se.ShortPlanError, match="not repeated"):
        se.verify_chronology(d)


def test_short_v2_captions_are_kinetic_phrases_over_kept_words():
    """The plan's captions come from the authoritative word stream (kept
    words, output times, verified speakers): one line each, one speaker
    each, in transcript order, every word at its mapped time; 'um' is
    verbatim and the cut sentence never reaches the screen."""
    from boydclips import captions as cap
    from boydclips import shorts_editor as se
    script = list(_EXCHANGE)
    script[3] = ("dfd", "Um my phone uh got stolen your honor so I didn't know where I was supposed to be.")
    script[2] = ("boyd", "So you stopped reporting for four months. What is your date of birth? Why did you stop reporting?")
    plan, words, case = _v2_plan(script)
    assert plan.ok and plan.captions and plan.word_stream, plan.refusal
    display = [a for a in plan.caption_audit if a["kept"]]
    for c in plan.captions:
        assert len(c["lines"]) == 1 and c["width_px"] <= 960
        assert len({display[i]["speaker"] for i in range(c["start"], c["end"])}) == 1
        assert " ".join(c["tokens"]) == c["text"]
    text = " ".join(c["text"] for c in plan.captions)
    assert "UM" not in text.split() and "UH" not in text.split()          # fillers omitted for display...
    omitted = [a for a in plan.caption_audit if not a["kept"]]
    assert {a["reason"] for a in omitted} <= {"filler", "repeat", "restart", "abandoned_fragment"}
    assert {a["w"].lower().strip(",.") for a in omitted} >= {"um", "uh"}       # ...and audited
    assert all(a["kept"] for a in plan.caption_audit if a["w"].lower().strip(",.") in ("stolen", "didn't", "know"))
    assert "DATE OF BIRTH" not in text
    joined = [c["text"] for c in plan.captions]
    assert not any(t.endswith(" YOUR") for t in joined), joined
    tw = se.timed_words(words, case["start_s"], case["end_s"])
    kept = [w for seg in plan.segments for w in tw if seg.start_s - 1e-6 <= w.t <= seg.end_s + 1e-6]
    out_words = render.map_words_to_timeline([Word(t=w.t, w=w.w) for w in kept], plan.segments, absorb_gap_s=0.0)
    assert [(round(w.t, 2), render.strip_caption_artifact(w.w)) for w in out_words] ==         [(round(x["t"], 2), render.strip_caption_artifact(x["w"])) for x in plan.word_stream]
    for g in ("captions_from_kept_words", "ONE_LINE_ONLY", "SPEAKER_PURITY", "NO_CROSS_SPEAKER_CARD",
              "SPEAKER_RESET", "WORD_ORDER", "DISPLAY_AUDIT", "FIT", "TIMING", "SEGMENT_JOINS", "DENSITY", "caption_rail"):
        assert next(x for x in plan.qc if x["gate"] == g)["ok"], g
    assert all(1 <= len(c["events"]) <= 3 for c in plan.captions)


def test_short_v2_focus_follows_the_speaker_within_budget():
    plan, _w, _c = _v2_plan()
    assert plan.ok
    for b in plan.beats:
        want = {"boyd": "boyd", "defendant": "defendant", "counsel": "defendant"}.get(b["speaker"], "duo")
        assert b["focus"] == want, b
    punches = [b for b in plan.beats if b["punch_in"]]
    assert 1 <= len(punches) <= 2 and all(b["role"] in ("payoff", "hook") for b in punches)
    assert next(b for b in plan.beats if b["role"] == "payoff")["punch_in"]
    rapid = _EXCHANGE[2:3] + [("dfd", "No."), ("boyd", "No?"), ("dfd", "No ma'am."), ("boyd", "Why not?"), ("dfd", "I just didn't.")] + _EXCHANGE[4:6]
    plan2, _w2, _c2 = _v2_plan(rapid)
    assert plan2.ok, plan2.refusal
    short_beats = [b for b in plan2.beats if b["end_s"] - b["start_s"] <= 3.0 and b["role"] in ("setup", "turn", "hook")]
    assert short_beats and all(b["focus"] == "duo" for b in short_beats), [(b["role"], b["focus"]) for b in plan2.beats]
    plan3, _w3, _c3 = _v2_plan(tiles=None)
    assert plan3.ok and all(b["focus"] == "duo" and not b["punch_in"] for b in plan3.beats)


def test_short_v2_qc_invariants_hold():
    plan, _w, _c = _v2_plan()
    assert plan.ok
    assert plan.duration_s <= 59.0
    assert all(s.duration >= 0.2 for s in plan.segments)
    ranges = [(s.start_s, s.end_s) for s in plan.segments]
    for (a0, b0), (a1, b1) in zip(ranges, ranges[1:]):
        assert a1 >= b0 - 1e-6
    assert all(g["ok"] for g in plan.qc if g["critical"]), [g for g in plan.qc if not g["ok"]]
    d = plan.as_dict()
    assert d["ruleset"] == "SHORTS_EDITOR_V2" and d["chronological_except_teaser"]
    assert set(d["scores"]) == {"hook", "clarity", "payoff", "escalation", "quote", "visual"}
    assert d["total"] == sum(d["scores"].values())
    assert "interior_cuts" in d and "question_answer" in d and "body_text" in d


def test_short_v2_refuses_a_routine_case_explicitly():
    routine = [
        ("boyd", "All right. State your name for the record."),
        ("dfd",  "John Smith."),
        ("boyd", "We'll reset it to the next setting. Sign the paperwork with the clerk. Anything further?"),
        ("cns",  "No your honor. Thank you your honor."),
        ("boyd", "Calling the next case."),
    ]
    plan, _w, _c = _v2_plan(routine, money_word=None)
    assert not plan.ok
    assert "no valid mini-story" in plan.refusal, plan.refusal
    plan2, _w2, _c2 = _v2_plan(cfg={"min_score": 99})
    assert not plan2.ok and "score_floor" in plan2.refusal, plan2.refusal
    plan3, _w3, _c3 = _v2_plan(money_word=None, case_over={"editorial": {"money_moment_s": 99999.0}})
    assert plan3.anchor.get("kind") != "money_moment"
    # an isolated loud line two minutes after the exchange, past max_window_s, has no story of its own
    script = _EXCHANGE + [("boyd", "Get out of my courtroom!")]
    plan4, _w4, _c4 = _v2_plan(script, money_word=None, gaps={6: 120.0})
    assert plan4.ok and "library" in plan4.body_text
    assert not any(a["anchor"] == "tell" and "custody" in a["note"] and a["passes_qc"] for a in plan4.alternatives)


def _hook_dimension_max() -> int:
    from boydclips import shorts_editor as se
    return se.SCORE_DIMENSIONS["hook"]


def test_short_v2_weak_hook_is_refused_even_when_the_total_passes():
    """THE 8929 REGRESSION. The rejected dAKO7myCd-g:8929 cut scored hook 7/25
    and escalation 7/15 but 65/100 total, so it passed the only acceptance test
    there was — a floor on the TOTAL — and shipped an opening that was the
    setup half of the money moment. The opening beat is now floored on its own
    dimension, so a strong payoff cannot buy a preamble."""
    plan, _w, _c = _v2_plan()
    assert plan.ok, plan.refusal
    floor = next(g for g in plan.qc if g["gate"] == "hook_floor")
    assert floor["ok"] and floor["critical"], floor
    assert f"hook {plan.scores['hook']}/{_hook_dimension_max()}" in floor["detail"], floor

    # Bad control: a floor no candidate can reach (above the dimension's own
    # maximum) refuses the same script. The total is untouched, so only the new
    # per-dimension floor can produce this refusal.
    unreachable, _w2, _c2 = _v2_plan(cfg={"hook_min_score": _hook_dimension_max() + 1})
    assert not unreachable.ok, unreachable.refusal
    assert "hook_floor" in unreachable.refusal, unreachable.refusal

    # The old behaviour is recoverable from configuration, not by editing code:
    # with the floor at zero the identical script passes on its total alone.
    off, _w3, _c3 = _v2_plan(cfg={"hook_min_score": 0})
    assert off.ok, off.refusal
    assert next(g for g in off.qc if g["gate"] == "hook_floor")["ok"]

    # And the floor steers the search: demanding a full-marks opening picks a
    # different window rather than accepting the preamble on a strong payoff.
    strict, _w4, _c4 = _v2_plan(cfg={"hook_min_score": _hook_dimension_max()})
    assert strict.ok, strict.refusal
    assert strict.scores["hook"] == _hook_dimension_max(), strict.scores
    assert strict.total < plan.total, (strict.total, plan.total)


def test_render_punch_graph_is_fixed_50_50_and_parses():
    """Every segment scales both windows to 1080x960 and stacks them: the
    divider is at 960 on every frame; a punch-in is only a narrower crop
    on one tile. The graph parses and runs under ffmpeg."""
    import shutil
    import subprocess
    from boydclips import layout
    segs = [render.Segment(0.10, 0.40), render.Segment(0.50, 0.90), render.Segment(0.95, 1.20)]
    tiles = ("crop=640:360:0:0", "crop=640:360:640:0")
    anchors = {"top": layout.Anchor(0.5, 0.42), "bottom": layout.Anchor(0.5, 0.42)}
    comp = layout.compose(["boyd", "defendant", "boyd"], [False, True, False], tiles,
                          {"boyd": "bottom", "defendant": "top"}, anchors, {"punch_zoom": 1.08})
    windows = [(x.top.crop, x.bottom.crop) for x in comp["_segments"]]
    chain = render.duo_punch_filter(segs, 0.0, windows, 1080, 1920)
    assert "concat=n=3:v=1:a=0[vv]" in chain and "concat=n=3:v=0:a=1[ac]" in chain
    assert chain.count("scale=1080:960") == 6 and "scale=1080:1152" not in chain and "scale=1080:768" not in chain
    assert windows[0] == windows[2] and windows[1][1] == windows[0][1]        # the un-punched tile never changes
    assert windows[1][0] != windows[0][0]                                    # the punched tile is a narrower window
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not on PATH")
    graph = chain + ";[vv]format=yuv420p[vout]"
    r = subprocess.run([ff, "-v", "error", "-f", "lavfi",
                        "-i", "testsrc=size=1280x720:rate=30:duration=2[out0];sine=frequency=440:duration=2[out1]",
                        "-filter_complex", graph, "-map", "[vout]", "-map", "[ac]",
                        "-t", "0.3", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]


def test_short_render_uses_the_house_grade_in_both_paths(tmp_path, monkeypatch):
    """The colour correction the shipped shorts have (config/short_floor.json
    grade.eq) is applied by render_short on the legacy AND the V2 graph, from
    one source, before the captions burn in."""
    floor_eq = json.loads((ROOT / "config" / "short_floor.json").read_text(encoding="utf-8"))["grade"]["eq"]
    cfg = dict(CFG.require("output.short"))
    cfg["vertical_mode"] = "duo_fill"
    cfg["watermark"] = False
    cfg["color"] = dict(cfg["color"], source="short_floor")
    assert render.short_grade_filter(cfg) == floor_eq
    assert floor_eq.startswith("eq=")
    # option "b" (2026-09-06): the floor without its global brightness term, derived from the floor file
    nb = render.short_grade_filter({"color": {"source": "short_floor_no_brightness"}})
    assert nb.startswith("eq=") and "brightness" not in nb
    assert "contrast=1.08" in nb and "saturation=1.50" in nb
    assert CFG.require("output.short")["color"]["source"] == "short_floor_no_brightness"
    captured = []
    monkeypatch.setattr(render, "_run", lambda cmd, cwd=None, timeout=3600: captured.append(cmd))
    monkeypatch.setattr(render, "probe_duration", lambda p: 1.0)
    segs = [render.Segment(1.0, 2.0), render.Segment(3.0, 4.0)]
    tiles = ("crop=640:360:0:0", "crop=640:360:640:0")
    windows = (render.plan_fill_window(tiles[0], 1080 / 960), render.plan_fill_window(tiles[1], 1080 / 960))
    src = tmp_path / "src.mp4"
    render.render_short(src, 0.0, segs, cfg, None, tmp_path / "legacy.mp4", tile_crops=windows)
    render.render_short(src, 0.0, segs, cfg, None, tmp_path / "v2.mp4", tile_crops=windows,
                        duo_punch=[(windows[0], windows[1]), (windows[0], windows[1])])
    graphs = [cmd[cmd.index("-filter_complex") + 1] for cmd in captured]
    assert len(graphs) == 2
    for g in graphs:
        assert floor_eq in g, g
        stage = next(part for part in g.split(";") if part.startswith("[vv]fps="))
        assert floor_eq in stage and stage.endswith("[vbase]")
        assert "curves=" not in g
    # the grade stage is byte-identical on both paths
    stages = [next(part for part in g.split(";") if part.startswith("[vv]fps=")) for g in graphs]
    assert stages[0] == stages[1]
    # the old daily curve is still reachable for reproducing earlier renders, and 'none' disables
    assert "curves=all=" in render.short_grade_filter({"color": {"source": "curve"}})
    assert render.short_grade_filter({"color": {"source": "none"}}) == ""
    assert render.short_grade_filter({"color": {"enabled": False}}) == ""


def test_build_ass_captions_follow_the_timeline_map(tmp_path):
    """Text on screen = the words that survive the edit, at the time the
    renderer plays them. An interior cut removes its words from the
    captions; a teaser's words appear once per occurrence."""
    words = [Word(t=100.0 + 0.5 * i, w=tok) for i, tok in enumerate(
        "one two three four five six SKIPPED SKIPPED SKIPPED nine ten eleven twelve".split())]
    # keep 100.0-102.6 (one..six) and 104.5-106.1 (nine..twelve); cut 103.0-104.0 (SKIPPED x3)
    segs = [render.Segment(99.9, 102.7), render.Segment(104.4, 106.2)]
    out_words = render.map_words_to_timeline(words, segs, absorb_gap_s=0.0)
    assert [w.w for w in out_words] == "one two three four five six nine ten eleven twelve".split()
    nine = next(w for w in out_words if w.w == "nine")
    assert abs(nine.t - (2.8 + 0.1)) < 1e-6                     # 104.5 -> offset 2.8 + (104.5 - 104.4)
    style = dict(_LEGACY_CAP_STYLE)
    path = render.build_ass(out_words, 0.0, 4.6, style, None, tmp_path / "c.ass", turns=[(0.0, "boyd")])
    text = path.read_text(encoding="utf-8")
    events = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert events and "SKIPPED" not in text
    assert any("NINE" in e and e.split(",")[1] == "0:00:02.90" for e in events), events[:12]
    # teaser: the same source words twice, once per occurrence
    segs_t = [render.Segment(104.4, 105.2), render.Segment(99.9, 102.7), render.Segment(104.4, 106.2)]
    out_t = render.map_words_to_timeline(words, segs_t, absorb_gap_s=0.0)
    assert [w.w for w in out_t].count("nine") == 2
    times = sorted(w.t for w in out_t if w.w == "nine")
    assert abs(times[0] - 0.1) < 1e-6 and abs(times[1] - (0.8 + 2.8 + 0.1)) < 1e-6


def _stream(script, t0=1.0, wps=0.28):
    out, t = [], t0
    for spk, text in script:
        for w in text.split():
            out.append({"t": round(t, 3), "w": w, "speaker": spk})
            t += wps
        t += 0.4
    return out


def test_captions_never_cross_a_speaker_boundary():
    """THE REGRESSION. Boyd: 'Why did you stop reporting?' / defendant:
    'Because my phone was stolen.' — no phrase may hold both; 'STOP REPORTING?
    BECAUSE' must be structurally impossible, even from a provider."""
    from boydclips import captions as cap
    stream = _stream([("boyd", "Why did you stop reporting?"), ("defendant", "Because my phone was stolen.")])
    cards, used = cap.plan_phrases(stream, _CAP_STYLE)
    assert used == "deterministic"
    for c in cards:
        assert len({stream[i]["speaker"] for i in range(c["start"], c["end"])}) == 1
        assert c["speaker"] in ("boyd", "defendant")
    texts = [c["text"] for c in cards]
    assert not any("REPORTING? BECAUSE" in t for t in texts), texts
    assert any(t.startswith("BECAUSE") for t in texts)
    assert cap.speaker_runs(stream) == [(0, 5, "boyd"), (5, 10, "defendant")]
    crossing = lambda ws, hb, cfg: {"cards": [[0, 3], [3, 7], [7, 10]]}   # noqa: E731
    _c, used = cap.plan_phrases(stream, _CAP_STYLE, provider=crossing)
    assert used.startswith("deterministic (provider rejected") and "speaker boundary" in used
    bad = [dict(cards[0], start=3, end=7, text="STOP REPORTING? BECAUSE MY",
                tokens=["STOP", "REPORTING?", "BECAUSE", "MY"], words=[(stream[i]["t"], stream[i]["w"]) for i in range(3, 7)])]
    gates = {g["gate"]: g["ok"] for g in cap.kinetic_qc(bad, stream, _CAP_STYLE)}
    assert not gates["SPEAKER_PURITY"] and not gates["NO_CROSS_SPEAKER_CARD"] and not gates["WORD_ORDER"]


def test_captions_are_one_line_and_split_rather_than_wrap():
    from boydclips import captions as cap
    stream = _stream([("boyd", "Explain to me why your phone being stolen interferes with your ability to get a GED.")])
    cards, _u = cap.plan_phrases(stream, _CAP_STYLE)
    assert all(len(c["lines"]) == 1 and c["width_px"] <= 960 for c in cards)
    assert "measured" in cap.width_source(_CAP_STYLE)
    assert all(1 <= c["end"] - c["start"] <= 7 for c in cards), [c["text"] for c in cards]
    assert cap.text_width("YOUR PHONE BEING STOLEN", _CAP_STYLE) <= 960
    assert [i for c in cards for i in range(c["start"], c["end"])] == list(range(len(stream)))
    texts = [c["text"] for c in cards]
    assert not any(t.endswith((" YOUR", " THE", " TO", " OF", " AND", " WITH")) for t in texts), texts
    long = _stream([("boyd", "It takes considerably more knowledge to commit a crime because the knowledge to do right")])
    cards2, _u = cap.plan_phrases(long, _CAP_STYLE)
    assert all(c["width_px"] <= 960 for c in cards2) and len(cards2) >= 3


def test_kinetic_events_build_word_by_word_and_reset_on_speaker_change():
    from boydclips import captions as cap
    stream = _stream([("boyd", "Why did you stop reporting?"), ("defendant", "Because my phone was stolen.")])
    cards, _u = cap.plan_phrases(stream, _CAP_STYLE)
    first = cards[0]
    vis = [ev["visible"] for ev in first["events"]]
    assert 1 <= len(vis) <= 3                                             # chunks, not every word
    assert vis[0] == first["events"][0]["new"]                            # the first state is the first chunk alone
    for k in range(1, len(vis)):
        assert vis[k].startswith(vis[k - 1] + " ")                        # builds by a chunk, earlier text unchanged
        assert vis[k] == vis[k - 1] + " " + first["events"][k]["new"]
    assert vis[-1] == first["text"]
    for ev in first["events"]:
        la = ev["new_range"][0]
        assert abs(ev["t"] - first["words"][la][0]) < 1e-6                # a chunk reveals at its first word's start
        assert abs((ev["pop"][1] - ev["pop"][0]) - 0.11) < 1e-6
    for a, b in zip(first["events"], first["events"][1:]):
        assert abs(a["end"] - b["t"]) < 1e-6
    assert first["events"][-1]["end"] == first["clear_s"]
    boyd_last = [c for c in cards if c["speaker"] == "boyd"][-1]
    dfd_first = [c for c in cards if c["speaker"] == "defendant"][0]
    assert boyd_last["clear_s"] <= dfd_first["start_s"]
    assert dfd_first["events"][0]["visible"] == dfd_first["events"][0]["new"]
    assert "CLEAR (speaker reset)" in [s["kind"] for s in cap.kinetic_states(cards)]
    gates = {g["gate"]: g["ok"] for g in cap.kinetic_qc(cards, stream, _CAP_STYLE)}
    assert all(gates.values()), gates


def test_caption_provider_is_validated_and_falls_back():
    from boydclips import captions as cap
    stream = _stream([("boyd", "So why did you stop reporting to your probation officer for four months")])
    n = len(stream)
    good = lambda ws, hb, cfg: {"cards": [[0, 5], [5, 6], [6, 10], [10, n]]}   # noqa: E731
    cards, used = cap.plan_phrases(stream, _CAP_STYLE, provider=good)
    assert used == "provider" and [(c["start"], c["end"]) for c in cards] == [(0, 5), (5, 6), (6, 10), (10, n)], used
    dangling = lambda ws, hb, cfg: {"cards": [[0, 4], [4, 6], [6, 10], [10, n]]}   # noqa: E731  ("SO WHY DID YOU" | "STOP")
    _c, used = cap.plan_phrases(stream, _CAP_STYLE, provider=dangling)
    assert used.startswith("deterministic (provider rejected") and "subject 'you' dangles" in used
    liar = lambda ws, hb, cfg: {"cards": [[0, 5], [5, 6], [6, 10], [10, n]], "text": "JUDGE DESTROYS HIM"}   # noqa: E731
    cards, used = cap.plan_phrases(stream, _CAP_STYLE, provider=liar)
    assert "DESTROYS" not in " ".join(c["text"] for c in cards)
    bad = lambda ws, hb, cfg: {"cards": [[0, 8], [8, n]]}   # noqa: E731  ("your" | "probation")
    _c, used = cap.plan_phrases(stream, _CAP_STYLE, provider=bad)
    assert used.startswith("deterministic (provider rejected")
    wide = lambda ws, hb, cfg: {"cards": [[0, 6], [6, n]]}   # noqa: E731  (does not fit one line)
    _c, used = cap.plan_phrases(stream, _CAP_STYLE, provider=wide)
    assert used.startswith("deterministic (provider rejected") and "one line" in used
    _c, used = cap.plan_phrases(stream, _CAP_STYLE, hard_breaks=[8], provider=good)   # a join inside [6, 10)
    assert used.startswith("deterministic (provider rejected") and "segment join" in used
    boom = lambda ws, hb, cfg: (_ for _ in ()).throw(RuntimeError("no model"))   # noqa: E731
    _c, used = cap.plan_phrases(stream, _CAP_STYLE, provider=boom)
    assert used.startswith("deterministic (provider failed")


def test_layout_divider_fixed_and_punch_inside_tile():
    from boydclips import layout
    tiles = ("crop=390:348:125:186", "crop=390:348:765:186")
    anchors = {"top": layout.Anchor(0.36, 0.40, 0.18, 0.28, "test"), "bottom": layout.Anchor(0.62, 0.45, 0.2, 0.3, "test")}
    comp = layout.compose(["boyd", "defendant", "boyd", "boyd"], [True, False, False, True], tiles,
                          {"boyd": "bottom", "defendant": "top"}, anchors, {"punch_zoom": 1.08})
    segs = comp["segments"]
    assert all(sg["divider_y"] == 960 for sg in segs)
    assert [sg["punch"] for sg in segs] == ["bottom", "", "", "bottom"]
    assert segs[0]["top"] == segs[1]["top"] == segs[2]["top"] == segs[3]["top"]        # the top tile never changes
    assert segs[1]["bottom"] == segs[2]["bottom"] and segs[0]["bottom"] == segs[3]["bottom"]
    base_w = layout.parse_crop(segs[1]["bottom"]["crop"])[0]
    punched_w = layout.parse_crop(segs[0]["bottom"]["crop"])[0]
    assert abs(punched_w * 1.08 - base_w) <= 4                                          # punch = 1.08 inside the tile
    assert abs(segs[0]["bottom"]["subject_x"] - segs[1]["bottom"]["subject_x"]) <= 3    # zoom about the anchor
    overlay = layout.overlay_layout(_CAP_STYLE, {"watermark_margin_frac": 0.035}, (119.0, 70.0))
    checks = layout.composition_checks(comp, overlay)
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]


def test_layout_centers_subject_from_measured_anchor():
    from boydclips import layout
    tile = "crop=628:348:6:186"
    # the geometric centre is NOT the person: he stands at ~28 % of the tile (Flores)
    win = layout.center_window(tile, layout.Anchor(0.2785, 0.339, 0.106, 0.238, "test"))
    assert abs(win.subject_x - 540) <= 40, win
    assert 1.0 < win.zoom <= 1.15 and win.upscale <= 3.2
    w, h, x, y = layout.parse_crop(win.crop)
    assert x >= 6 and x + w <= 6 + 628 and y >= 186 and y + h <= 186 + 348     # never outside the tile
    assert abs(w / h - 1.125) < 0.02
    # a centred subject needs no zoom at all
    win2 = layout.center_window(tile, layout.Anchor(0.5, 0.42, 0.18, 0.28, "test"))
    assert win2.zoom == 1.0 and abs(win2.residual_x) <= 2
    # far off-centre: the QUALITY cap wins — zoom stops at 1.15, the residual is recorded, not chased
    win3 = layout.center_window(tile, layout.Anchor(0.12, 0.42, 0.18, 0.28, "test"))
    assert win3.zoom == 1.15 and any("zoom cap" in n for n in win3.notes) and abs(win3.residual_x) > 40
    comp = layout.compose(["boyd"], [False], (tile, "crop=628:348:646:186"), {"boyd": "bottom", "defendant": "top"},
                          {"top": layout.Anchor(0.12, 0.42, 0.18, 0.28, "test"), "bottom": layout.Anchor(0.5, 0.45)}, {})
    checks = layout.composition_checks(comp, layout.overlay_layout(_CAP_STYLE, {}, (119.0, 70.0)))
    top = next(c for c in checks if c["check"] == "top_subject_centered")
    assert top["ok"] and top["at_zoom_cap"] and top["upscale"] > 3.0


def test_overlay_layout_collision_verdict():
    from boydclips import layout
    ok = layout.overlay_layout(_CAP_STYLE, {"watermark_margin_frac": 0.035}, (119.0, 70.0))
    assert ok["overlay_collision"] == "PASS" and ok["ok"] and ok["end_card"] == "none"
    assert ok["caption_center"] == [540.0, 960.0]
    cap = ok["boxes"][0]
    assert cap["y"] < 960 < cap["y"] + cap["h"]                                          # straddles the divider
    # the legacy second mark pinned under the seam would sit inside the rail -> FAIL
    seam_mark = layout.Box(1080 - 38 - 119, 960 + 38, 119, 70, "watermark_seam", True)
    bad = layout.overlay_layout(_CAP_STYLE, {"watermark_margin_frac": 0.035}, (119.0, 70.0), extra=[seam_mark])
    assert bad["overlay_collision"] == "FAIL" and ("caption", "watermark_seam") in bad["collisions"]
    # a non-critical overlay may overlap without failing
    soft = layout.Box(0, 900, 300, 100, "debug", False)
    assert layout.overlay_layout(_CAP_STYLE, {}, (119.0, 70.0), extra=[soft])["overlay_collision"] == "PASS"


def test_rail_ass_kinetic_structure(tmp_path):
    from boydclips import captions as cap
    stream = _stream([("boyd", "Why did you stop reporting?"), ("defendant", "Because my phone was stolen.")])
    cards, _u = cap.plan_phrases(stream, _CAP_STYLE)
    path = render.build_rail_ass(cards, _CAP_STYLE, 8.0, tmp_path / "rail.ass")
    text = path.read_text(encoding="utf-8")
    events = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == sum(len(c["events"]) for c in cards)            # one event per reveal chunk
    assert len(events) < len(stream)                                       # fewer changes than words
    assert "Card," not in text and "FULL CASE" not in text and "FULL VIDEO" not in text
    import re as _re
    for c in cards:
        x_left = int(c["x_left"])                                             # captions.caption_origin: visual box centred
        assert abs(c["predicted_center"] - 540) <= 0.5
        mine = [e for e in events if f"\\an4\\pos({x_left},960)" in e]
        assert len(mine) == len(c["events"]), (c["text"], x_left)
        for ev, e in zip(c["events"], mine):
            body = e.split(",", 9)[9]
            assert body.count("\\c&H003FD2FF") == 1                       # exactly the new chunk is yellow
            pf, pk = cap.DEFAULTS["pop_from"], cap.DEFAULTS["pop_peak"]
            assert body.count(f"\\fscx{pf}") == 1 and f"\\fscx{pk}" in body   # the eased pop on that chunk only
            assert "\\alpha&HFF&" in body and "\\alpha&H00&" in body            # opacity entrance on the chunk only
            assert f"\\t(0,{cap.DEFAULTS['pop_rise_ms']},{cap.DEFAULTS['ease_rise']:g}," in body
            assert f"\\t({cap.DEFAULTS['pop_rise_ms']},{cap.DEFAULTS['pop_ms']},{cap.DEFAULTS['ease_settle']:g}," in body
            plain = _re.sub(r"\{[^}]*\}", "", body)
            assert plain == ev["visible"]                                    # earlier chunks plain, unchanged
    starts = [e.split(",")[1] for e in events]
    assert starts == sorted(starts)
    text2 = render.build_rail_ass(cards, dict(_CAP_STYLE, mode="static"), 8.0, tmp_path / "s.ass").read_text(encoding="utf-8")
    ev2 = [l for l in text2.splitlines() if l.startswith("Dialogue:")]
    assert len(ev2) == len(cards) and "\\c&H003FD2FF" not in text2 and "\\fscx" not in text2


def test_camera_grade_filter_builds_from_config():
    cfg = {"defendant": {"curve": "0/0 0.5/0.5 1/0.82"}, "boyd": {"curve": None}}
    assert render.camera_grade_filter(cfg, "defendant") == "curves=all='0/0 0.5/0.5 1/0.82'"
    assert render.camera_grade_filter(cfg, "boyd") == ""
    assert render.camera_grade_filter({"boyd": "eq=contrast=1.05"}, "boyd") == "eq=contrast=1.05"
    assert render.camera_grade_filter({"boyd": {"curve": "0/0 1/0.9", "eq": "saturation=1.1"}}, "boyd") == \
        "curves=all='0/0 1/0.9',eq=saturation=1.1"
    assert render.camera_grade_filter(None, "defendant") == ""
    # the per-camera stage sits on the TOP tile chain only, before its scale, before the assembly
    segs = [render.Segment(0.10, 0.40)]
    chain = render.duo_punch_filter(segs, 0.0, [("crop=348:310:7:186", "crop=390:348:795:186")], 1080, 1920,
                                    tile_filters=("curves=all='0/0 1/0.82'", ""))
    top = next(part for part in chain.split(";") if part.startswith("[l0]"))
    bottom = next(part for part in chain.split(";") if part.startswith("[r0]"))
    assert "curves=all='0/0 1/0.82',scale=1080:960" in top and "curves" not in bottom
    assert chain.index("curves") < chain.index("vstack")


def test_visual_qc_checks_flag_a_moved_divider_and_a_collision():
    from boydclips import layout
    tiles = ("crop=640:360:0:0", "crop=640:360:640:0")
    anchors = {"top": layout.Anchor(0.5, 0.42), "bottom": layout.Anchor(0.5, 0.42)}
    comp = layout.compose(["boyd", "defendant"], [True, False], tiles, {"boyd": "bottom", "defendant": "top"},
                          anchors, {"punch_zoom": 1.08})
    overlay = layout.overlay_layout(_CAP_STYLE, {}, (119.0, 70.0))
    assert all(c["ok"] for c in layout.composition_checks(comp, overlay))
    moved = dict(comp)
    moved["segments"] = [dict(sg, divider_y=1152) for sg in comp["segments"][:1]] + comp["segments"][1:]
    assert not next(c for c in layout.composition_checks(moved, overlay) if c["check"] == "divider_fixed")["ok"]
    off = dict(comp)
    off["base"] = {"top": dict(comp["base"]["top"], subject_x=356.0), "bottom": comp["base"]["bottom"]}
    assert not next(c for c in layout.composition_checks(off, overlay) if c["check"] == "top_subject_centered")["ok"]


def test_caption_planner_respects_spoken_punctuation_and_sentence_tails():
    from boydclips import captions as cap
    stream = _stream([("boyd", "I can do this, and I can do that. Why can you do it beforehand? I just I don't have no excuses, Judge. I just I don't have the knowledge.")])
    assert cap.boundary_forbidden(stream, 3, 0.35) is None            # "this," ends a phrase
    assert cap.boundary_forbidden(stream, 8, 0.35) is None            # "that." ends a sentence
    cards, _u = cap.plan_phrases(stream, _CAP_STYLE)
    texts = [c["text"] for c in cards]
    assert not any(t.startswith("THAT. ") or t.startswith("JUDGE. ") for t in texts), texts
    assert any(t.endswith("JUDGE.") for t in texts), texts
    assert not any(t.endswith(" DO") for t in texts), texts
    assert all(len(c["lines"]) == 1 for c in cards)


def test_display_cleanup_is_conservative_and_audited():
    """Display-only cleanup, audio untouched, every omission audited, and
    nothing that carries meaning is dropped."""
    from boydclips import captions as cap
    s = _stream([("defendant", "I just I don't have no excuses, Judge.")])
    disp, audit = cap.clean_disfluencies(s, _CAP_STYLE)
    assert [x["w"] for x in disp] == ["I", "just", "don't", "have", "no", "excuses,", "Judge."]
    assert [a for a in audit if not a["kept"]][0]["reason"] == "restart"
    s = _stream([("defendant", "I I didn't know")])
    disp, _a = cap.clean_disfluencies(s, _CAP_STYLE)
    assert [x["w"] for x in disp] == ["I", "didn't", "know"]
    s = _stream([("defendant", "I just I don't I don't have the knowledge to that I didn't No, no.")])
    disp, audit = cap.clean_disfluencies(s, _CAP_STYLE)
    assert [x["w"] for x in disp] == ["I", "just", "don't", "have", "the", "knowledge"], [x["w"] for x in disp]
    reasons = {a["w"]: a["reason"] for a in audit if not a["kept"]}
    assert reasons["to"] == "abandoned_fragment" and "negation" in [a["note"] for a in audit if a["w"] == "didn't"][0]
    # an answer that repeats "no" is emphasis, kept; a mid-run stumble is collapsed
    s = _stream([("defendant", "No, no, I didn't do that.")])
    disp, _a = cap.clean_disfluencies(s, _CAP_STYLE)
    assert [x["w"] for x in disp][:2] == ["No,", "no,"]
    # fillers go, numbers and names never collapse, negation stays
    s = _stream([("boyd", "Um you had uh four four years and Mr. Flores Flores never never showed up")])
    disp, audit = cap.clean_disfluencies(s, _CAP_STYLE)
    ws = [x["w"] for x in disp]
    assert "Um" not in ws and "uh" not in ws
    assert ws.count("four") == 2 and ws.count("Flores") == 2 and "never" in ws
    # every displayed word maps to exactly one source index, in order
    assert [x["src"][0] for x in disp] == sorted(x["src"][0] for x in disp)
    # cleanup never crosses a speaker: an echo across the change is two speakers' words
    s = _stream([("boyd", "You didn't know?"), ("defendant", "I didn't know.")])
    disp, _a = cap.clean_disfluencies(s, _CAP_STYLE)
    assert len(disp) == len(s)
    # off switch keeps everything
    disp, audit = cap.clean_disfluencies(_stream([("defendant", "I I um know")]), dict(_CAP_STYLE, clean_disfluencies=False))
    assert len(disp) == 4 and all(a["kept"] for a in audit)


def test_reveal_chunks_follow_density_and_natural_breaks():
    from boydclips import captions as cap
    # "I just" ... pause ... "don't have" -> two chunks on the pause
    s = [{"t": 10.38, "w": "I", "speaker": "defendant"}, {"t": 10.42, "w": "just", "speaker": "defendant"},
         {"t": 11.18, "w": "don't", "speaker": "defendant"}, {"t": 11.34, "w": "have", "speaker": "defendant"},
         {"t": 11.46, "w": "no", "speaker": "defendant"}, {"t": 11.62, "w": "excuses,", "speaker": "defendant"},
         {"t": 12.14, "w": "Judge.", "speaker": "defendant"}]
    res = cap.plan_captions(s, _CAP_STYLE)
    cards = res["cards"]
    assert all(1 <= len(c["events"]) <= 3 for c in cards)
    first = cards[0]
    assert first["chunks"][0] in ("I JUST", "I JUST DON'T HAVE") and first["events"][0]["t"] == 10.38
    if len(first["chunks"]) > 1:
        assert first["events"][1]["t"] in (11.18, 11.46)
    assert res["density"]["per_second"] <= 2.5
    gates = {g["gate"]: g["ok"] for g in cap.kinetic_qc(cards, res["display"], _CAP_STYLE, res["hard_breaks"], res["audit"])}
    assert gates["DENSITY"] and gates["DISPLAY_AUDIT"] and gates["TIMING"]
    # slow speech does not generate constant motion: one word every 1.5 s -> at most 3 reveals per phrase
    slow = [{"t": 1.0 + 1.5 * k, "w": w, "speaker": "boyd"} for k, w in enumerate("the court will accept the plea".split())]
    res2 = cap.plan_captions(slow, _CAP_STYLE)
    assert all(len(c["events"]) <= 3 for c in res2["cards"]) and res2["density"]["per_second"] <= 2.0


def test_negation_is_never_dropped_by_display_cleanup():
    """NEGATION SAFETY (Nathan, 2026-09-06): 'I didn't do it' can never
    become 'I did it'; 'No, I didn't' cannot lose its negation. A negation
    leaves the display only inside a whole abandoned fragment, audited."""
    from boydclips import captions as cap

    def shown(script, style=_CAP_STYLE):
        disp, audit = cap.clean_disfluencies(_stream(script), style)
        return [x["w"] for x in disp], audit

    ws, audit = shown([("defendant", "I didn't do it")])
    assert ws == ["I", "didn't", "do", "it"] and all(a["kept"] for a in audit)
    ws, audit = shown([("defendant", "I didn't I did it")])                 # a correction is not a restart
    assert ws == ["I", "didn't", "I", "did", "it"] and all(a["kept"] for a in audit)
    ws, _a = shown([("defendant", "I I didn't do it")])
    assert ws == ["I", "didn't", "do", "it"]
    ws, _a = shown([("defendant", "I didn't didn't do it")])                # an isolated negation is never a duplicate
    assert ws.count("didn't") == 2
    ws, audit = shown([("defendant", "No, I didn't")])
    assert ws == ["No,", "I", "didn't"] and all(a["kept"] for a in audit)
    ws, _a = shown([("defendant", "No, no, I didn't")])
    assert ws == ["No,", "no,", "I", "didn't"]
    ws, _a = shown([("defendant", "Um no I didn't")])
    assert ws == ["no", "I", "didn't"]
    ws, _a = shown([("defendant", "I never I never did that")])            # exact repeat keeps the negated copy
    assert ws == ["I", "never", "did", "that"]
    ws, _a = shown([("defendant", "I did it, no I didn't")])               # a tail opening with a negation is an answer
    assert ws == ["I", "did", "it,", "no", "I", "didn't"]
    ws, _a = shown([("defendant", "I did it. Not really.")])
    assert "Not" in ws
    for script in (
        [("boyd", "You didn't report?"), ("defendant", "No ma'am, I didn't, I couldn't.")],
        [("defendant", "I don't have nothing, nobody never told me.")],
        [("defendant", "It wasn't me, I wasn't there, I can't drive.")],
    ):
        src = _stream(script)
        ws, audit = shown(script)
        want = [w for w in (x["w"] for x in src) if w.strip(",.?!").lower() in cap.NEGATIONS]
        got = [w for w in ws if w.strip(",.?!").lower() in cap.NEGATIONS]
        assert want == got, (script, want, got)
    # the Flores tail: omitted WHOLE under the fragment rule, original words + negation in the audit
    ws, audit = shown([("defendant", "I just I don't I don't have the knowledge to that I didn't No, no.")])
    assert ws == ["I", "just", "don't", "have", "the", "knowledge"]
    frag = [a for a in audit if a["reason"] == "abandoned_fragment"]
    assert [a["w"] for a in frag] == ["to", "that", "I", "didn't", "No,", "no."]
    assert all("original: \"to that I didn't No, no.\"" in a["note"] and "didn't" in a["note"] for a in frag)
    # the same words NOT hanging off a completed statement stay
    ws, _a = shown([("defendant", "I didn't no, no.")])
    assert ws == ["I", "didn't", "no,", "no."]



def test_visual_polish_clarity_scaler_and_encode():
    """Visual polish 2026-09-06: better scaler + per-tile post-scale clarity
    on the tile chain (after the scale, before the stack), captions after;
    encode preset/crf from config."""
    cfg = {"scale_flags": "lanczos+accurate_rnd+full_chroma_int", "defendant": "cas=strength=0.40", "boyd": "cas=strength=0.30"}
    assert render.camera_clarity_filter(cfg, "defendant") == "cas=strength=0.40"
    assert render.camera_clarity_filter(cfg, "boyd") == "cas=strength=0.30"
    assert render.camera_clarity_filter({"enabled": False, "boyd": "cas=1"}, "boyd") == ""
    assert render.camera_clarity_filter(None, "boyd") == ""
    segs = [render.Segment(0.10, 0.40)]
    chain = render.duo_punch_filter(segs, 0.0, [("crop=348:310:7:186", "crop=390:348:795:186")], 1080, 1920,
                                    tile_filters=("curves=all='0/0 1/0.82'", ""), scale_flags=cfg["scale_flags"],
                                    tile_post=(cfg["defendant"], cfg["boyd"]))
    top = next(part for part in chain.split(";") if part.startswith("[l0]"))
    bottom = next(part for part in chain.split(";") if part.startswith("[r0]"))
    assert "curves=all='0/0 1/0.82',scale=1080:960:flags=lanczos+accurate_rnd+full_chroma_int,cas=strength=0.40,setsar=1" in top
    assert "scale=1080:960:flags=lanczos+accurate_rnd+full_chroma_int,cas=strength=0.30,setsar=1" in bottom
    assert top.index("scale=") < top.index("cas=")                          # clarity AFTER the scale
    assert chain.index("cas=") < chain.index("vstack")                      # and before the stack (captions come later)
    assert render.encode_args({"preset": "slow", "crf": 17}) == ["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p"]
    assert render.encode_args({}) == ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
    sh = CFG.require("output.short")
    assert sh["preset"] == "slow" and int(sh["crf"]) == 17 and sh["fps"] == 30
    assert sh["clarity"]["scale_flags"].startswith("lanczos") and sh["clarity"]["defendant"].startswith("cas=")


def test_caption_size_and_visual_centering():
    """Clean phrase preset: font 82 on a 980 px safe width; a phrase's
    origin centres its VISUAL box (ink + outline + shadow) on the rail, and
    every reveal state of the phrase shares that origin."""
    from boydclips import captions as cap
    cfg = dict(CFG.require("output.short")["captions"])
    cfg.update(cfg.pop("rail"))
    assert cfg["preset"] == "clean_phrase" and int(cfg["font_size"]) == 82 and int(cfg["safe_width"]) == 980
    for text in ("YOU DON'T DO ANYTHING", "I JUST DON'T HAVE", "NO EXCUSES, JUDGE.", "IT TAKES MORE KNOWLEDGE", "ALL YOU HAVE TO SAY IS,"):
        assert cap.text_width(text, cfg) <= 980, text
    res = cap.plan_captions(_stream([("boyd", "Why can you do it beforehand? All you have to say is, would I want somebody to do this to me?")]), cfg)
    for c in res["cards"]:
        l, _t, r, _b = cap.text_ink_box(c["text"], cfg)
        visual_center = c["x_left"] + ((l - 6) + (r + 6 + 2)) / 2.0
        assert abs(visual_center - 540) <= 0.5
        assert c["width_px"] <= 980 and len(c["lines"]) == 1
    text = render.build_rail_ass(res["cards"], cfg, 12.0, Path(__file__).parent / "_polish.ass").read_text(encoding="utf-8")
    (Path(__file__).parent / "_polish.ass").unlink(missing_ok=True)
    # libass renders Fontsize as the cell height (winAscent + winDescent), so the intended 96 px em
    # needs Fontsize 96 x 1.7334 for Anton (measured: Fontsize 84 rendered a 48 px em, 0.577 x the widths)
    k = render.ass_font_scale("Anton")
    assert abs(k - 1.7334) < 0.001
    assert f"Style: Rail,Anton,{round(82 * k, 1)}," in text
    for c in res["cards"]:
        n = text.count(f"\\an4\\pos({int(c['x_left'])},960)")
        assert n == len(c["events"])                                        # one origin for every reveal state


def test_punch_count_counts_runs_not_segments():
    """Robinson (2026-09-06): two punched beats became four punched segments
    after interior cuts and the layout check refused the short. A punch-in is
    one zoom that stays on through its beat: count runs."""
    from boydclips import layout
    tiles = ("crop=628:348:6:186", "crop=628:348:646:186")
    anchors = {"top": layout.Anchor(0.5, 0.42), "bottom": layout.Anchor(0.5, 0.42)}
    tm = {"boyd": "bottom", "defendant": "top"}
    overlay = layout.overlay_layout(_CAP_STYLE, {}, (119.0, 70.0))
    focus = ["boyd"] * 6
    comp = layout.compose(focus, [True, True, False, True, True, False], tiles, tm, anchors, {"punch_zoom": 1.08})
    pc = next(c for c in layout.composition_checks(comp, overlay) if c["check"] == "punch_count")
    assert pc["ok"] and pc["value"] == 2 and pc["segments_punched"] == 4
    comp4 = layout.compose(["boyd"] * 7, [True, False, True, False, True, False, True], tiles, tm, anchors, {"punch_zoom": 1.08})
    pc4 = next(c for c in layout.composition_checks(comp4, overlay) if c["check"] == "punch_count")
    assert pc4["ok"] and pc4["value"] == 4 and pc4["policy"] == "editorial_spacing"


def test_subject_face_prefers_the_defendant_at_the_lectern():
    """Garcia/Robinson (2026-09-06): the largest face was counsel beside the
    defendant and the defendant was cut off at the tile edge."""
    from boydclips.pipeline import choose_subject_face
    prosecutor_edge = (60.0, 0.06, 0.45, 0.10, 0.18)
    defendant = (58.0, 0.42, 0.44, 0.09, 0.17)
    attorney = (70.0, 0.77, 0.46, 0.11, 0.20)
    gallery = (20.0, 0.30, 0.50, 0.03, 0.06)
    rows = [prosecutor_edge, defendant, attorney, gallery]
    assert choose_subject_face(rows, "defendant") == defendant
    assert choose_subject_face(rows, "boyd") == attorney          # Boyd's tile: largest
    assert choose_subject_face([attorney], "defendant") == attorney
    assert choose_subject_face([], "defendant") is None
    # only edge faces present: the substantial pool still answers
    assert choose_subject_face([prosecutor_edge, gallery], "defendant") == prosecutor_edge
    # Alonzo: counsel on both sides of her -> the middle face
    left_counsel = (62.0, 0.13, 0.45, 0.10, 0.18)
    alonzo = (55.0, 0.35, 0.46, 0.09, 0.17)
    right_counsel = (66.0, 0.75, 0.44, 0.10, 0.19)
    assert choose_subject_face([left_counsel, alonzo, right_counsel], "defendant") == alonzo
    # Robinson: two faces, defendant left of counsel
    robinson = (50.0, 0.25, 0.40, 0.08, 0.16)
    counsel = (72.0, 0.70, 0.42, 0.11, 0.20)
    assert choose_subject_face([counsel, robinson], "defendant") == robinson


def test_headroom_floor_admits_a_standing_defendant():
    """Garcia (2026-09-06): face centre at 12.8 % of the tile; the slot is the
    tile's full height so the 20 % floor could never be met. 12 % admits it,
    a face at 5 % (cut by the slot edge) is still refused."""
    from boydclips import layout
    tiles = ("crop=628:348:6:186", "crop=628:348:646:186")
    tm = {"boyd": "top", "defendant": "bottom"}
    overlay = layout.overlay_layout(_CAP_STYLE, {}, (119.0, 70.0))
    comp = layout.compose(["defendant"], [False], tiles, tm,
                          {"top": layout.Anchor(0.5, 0.42), "bottom": layout.Anchor(0.39, 0.128, 0.09, 0.17, "test")}, {})
    hr = next(c for c in layout.composition_checks(comp, overlay) if c["check"] == "bottom_subject_headroom")
    assert hr["ok"], hr
    low = layout.compose(["defendant"], [False], tiles, tm,
                         {"top": layout.Anchor(0.5, 0.42), "bottom": layout.Anchor(0.39, 0.05, 0.09, 0.17, "test")}, {})
    hr2 = next(c for c in layout.composition_checks(low, overlay) if c["check"] == "bottom_subject_headroom")
    assert not hr2["ok"]


def test_headroom_ceiling_measures_the_head_not_the_face_centre():
    """IDGfe1rPUQo:6130 (2026-09-13). The judge's webcam close-up puts the face
    centre at 626.9 px of the 960 slot — 3 px over the old flat 0.65 ceiling —
    while the head top sits at 438.7 px (45.7 %) and the chin at 815.1 px. The
    slot is the tile's full height, so subject_y == fy * SLOT_H at every legal
    zoom: that case could not be rendered at all. The bounds that matter are
    where the head and the chin land, and they are now what is checked when the
    face box was measured. Bad controls still refuse a small face parked at the
    bottom, and a chin below the slot."""
    from boydclips import layout
    tiles = ("crop=628:348:6:186", "crop=628:348:646:186")
    tm = {"boyd": "bottom", "defendant": "top"}
    overlay = layout.overlay_layout(_CAP_STYLE, {}, (119.0, 70.0))

    def headroom(fy: float, fh: float) -> dict:
        comp = layout.compose(["boyd"], [False], tiles, tm,
                              {"top": layout.Anchor(0.356, 0.331, 0.080, 0.193, "test"),
                               "bottom": layout.Anchor(0.588, fy, 0.173, fh, "test")}, {})
        return next(c for c in layout.composition_checks(comp, overlay)
                    if c["check"] == "bottom_subject_headroom")

    real = headroom(0.653, 0.392)
    assert real["ok"] and round(real["value"], 1) == 626.9
    assert round(real["head_top"], 1) == 438.7 and round(real["chin"], 1) == 815.1

    parked = headroom(0.72, 0.15)          # bad control: small face at the bottom
    assert not parked["ok"] and parked["head_top"] > 0.62 * 960

    overflow = headroom(0.80, 0.30)        # bad control: chin below the slot
    assert not overflow["ok"] and overflow["chin"] > 0.94 * 960


def test_run_case_refuses_an_ineligible_current_rubric_row(monkeypatch):
    """Miosek (2026-09-06): an operator-bounded re-score under the CURRENT
    rubric came back HOLD 71 and run_case rendered it anyway, because only
    the stale-rubric branch checked eligibility."""
    from unittest.mock import MagicMock
    from boydclips import analyze, pipeline
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.store = MagicMock()
    pipe.store.get_case.return_value = {
        "start_s": 10.0, "end_s": 610.0, "defendant_name": "X", "total_score": 71.0,
        analyze.RUBRIC_VERSION_KEY: analyze.current_rubric_version(),
        "eligible": False, "ineligible_reason": "HOLD 71/100 (below MAKE 78)",
        "safety": {"safety_pass": True, "safety_rule_violations": []},
    }
    pipe.store.case_published.return_value = False
    pipe.store.get_docket_row.return_value = {"video_id": "vid", "title": "t", "duration_s": 1000.0, "docket_date": "2026-01-01"}
    pipe.produce = MagicMock(side_effect=AssertionError("produce must not run for an ineligible row"))
    assert pipe.run_case("vid:10") is None
    pipe.produce.assert_not_called()
