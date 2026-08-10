"""Verification suite for the paths that don't need an API key.

Written because the pipeline's riskiest failures are silent ones that only
surface at 3am inside a scheduled run: a template that raises on .format(),
a JSON schema the API rejects, a segment plan that reorders courtroom speech.

Run:  python tests/test_pipeline.py       (no pytest needed)
      pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import json
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
                   ("human_stakes", "dramatic_turn", "judge_moment",
                    "self_contained", "hook_strength")},
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


def test_not_self_contained_blocked():
    case = _case()
    case["scores"]["self_contained"]["score"] = 20
    ok, reason = analyze._check_gates(case, CFG.require("analysis.gates"))
    assert not ok and "self-contained" in reason


def test_weighted_total_matches_manual_sum():
    weights = CFG.require("analysis.rubric_weights")
    scores = {"human_stakes": 90, "dramatic_turn": 70, "judge_moment": 60,
              "self_contained": 80, "hook_strength": 50}
    expected = sum(scores[d] * w for d, w in weights.items()) / 100.0
    assert round(expected, 2) == 71.5, f"weighting math changed: got {expected}"


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
    w["judge_moments"] = w.pop("judge_moment")  # still sums to 100
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


# ---------------------------------------------------------------- config


def test_config_validation_catches_bad_values():
    from boydclips.config import Config, _validate
    import copy

    base = copy.deepcopy(CFG._data)

    bad = copy.deepcopy(base)
    bad["analysis"]["rubric_weights"]["human_stakes"] = 99
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
