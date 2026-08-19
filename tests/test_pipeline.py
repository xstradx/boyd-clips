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
    """Weights live in config but are described in the prompt. Drift = silent
    mis-scoring, because the model reasons against one and code sums the other."""
    _, system, _ = prompt_text("score_cases")
    for dim, weight in CFG.require("analysis.rubric_weights").items():
        assert f"weight {weight}" in system, (
            f"rubric weight for {dim} is {weight} in config but not stated "
            f"as 'weight {weight}' in prompts/score_cases.md"
        )


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
    base = {
        "start_s": 10.0, "end_s": 200.0, "audio_quality": 5,
        "safety": {"safety_pass": True, "safety_rule_violations": [], "safety_reasoning": ""},
        "scores": {d: {"score": 80, "justification": "j"} for d in
                   ("pushback", "boyd_register", "receipt",
                    "consequence", "hook_strength")},
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


def test_threshold_is_reachable_by_real_scores():
    """Regression on the calibration itself: 70 passed nothing across 18 real
    cases (best 57.0). Guard against silently restoring an unreachable gate."""
    threshold = CFG.require("analysis.gates.min_total_score")
    assert threshold <= 57, (
        f"min_total_score is {threshold}, but the best case measured across two "
        "real dockets scored 57.0 — this gate would pass nothing"
    )


def test_no_pushback_blocked():
    """A compliant defendant is what actually kills a clip.

    Measured across 14 videos on the channel clipping this same judge: someone
    pushing back at Boyd appears in 8 of 8 winners and 1 of 6 losers. Their
    lowest performer has tears, a remand and a life sentence in it and still
    died, because the defendant agreed with everything.
    """
    case = _case()
    case["scores"]["pushback"]["score"] = 20
    ok, reason = analyze._check_gates(case, CFG.require("analysis.gates"))
    assert not ok and "pushback" in reason.lower()


def test_weighted_total_matches_manual_sum():
    weights = CFG.require("analysis.rubric_weights")
    scores = {"pushback": 90, "boyd_register": 70, "receipt": 60,
              "consequence": 80, "hook_strength": 50}
    expected = sum(scores[d] * w for d, w in weights.items()) / 100.0
    # 73.5 under the 2026-08-18 weights (pushback 30 / boyd_register 25 /
    # receipt 20 / consequence 15 / hook_strength 10). Was 71.5 under the old
    # abstract rubric. This asserts the weighting MATH, so it only moves when
    # the weights deliberately move.
    assert round(expected, 2) == 73.5, f"weighting math changed: got {expected}"


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
    w["boyd_registers"] = w.pop("boyd_register")  # still sums to 100
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
    bad["analysis"]["rubric_weights"]["pushback"] = 99
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
