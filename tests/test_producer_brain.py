from __future__ import annotations

import copy
from pathlib import Path

import pytest

from boydclips.producer_brain import (
    REPORT_SECTIONS,
    align_transcript_ranges,
    load_json,
    load_transcript,
    material_from_pipeline,
    normalise_source_ids,
    package_from_plan,
    prepare_request,
    render_report,
    validate_plan,
)
from boydclips import analyze
from boydclips.transcribe import Word


ROOT = Path(__file__).resolve().parents[1]
MATERIAL_PATH = ROOT / "docs" / "producer_brain_v1" / "real_case_input.json"
PLAN_PATH = ROOT / "docs" / "producer_brain_v1" / "real_case_plan.json"


def _artifacts():
    material = load_json(MATERIAL_PATH)
    transcript = load_transcript(material)
    plan = load_json(PLAN_PATH)
    return material, transcript, plan


@pytest.mark.parametrize("text", ["BOYD: YOU BEING THE ADULT", 'HE: PROBABLY HAUNTED / BOYD: YOU SHOULDN\'T'])
def test_rejected_thumbnail_fragments_fail_the_producer_plan(text):
    material, transcript, plan = _artifacts()
    plan["thumbnail_plan"][1]["text"] = text
    errors = validate_plan(plan, material, transcript)
    assert any("incomplete thought" in e or "missing action or object" in e for e in errors)


def test_real_case_plan_passes_schema_provenance_and_editorial_guards():
    material, transcript, plan = _artifacts()

    assert validate_plan(plan, material, transcript) == []


def test_validated_plan_adapts_to_three_exact_packaging_pairs():
    _material, _transcript, plan = _artifacts()
    package = package_from_plan(plan)

    assert [row["label"] for row in package["packaging_pairs"]] == list("ABC")
    assert [row["thumbnail_hypothesis"] for row in package["packaging_pairs"]] == [
        "court_of_justice_control", "confrontation", "reaction_story_moment",
    ]
    assert len({row["title"] for row in package["packaging_pairs"]}) == 3
    assert package["longform_title"] == package["packaging_pairs"][0]["title"]
    assert package["short_title"] == plan["short_plan"]["title"]
    assert package["short_title"] not in {row["title"] for row in package["packaging_pairs"]}
    assert package["hook_verified"] is True


def test_rejects_thumbnail_reason_paired_to_another_label():
    material, transcript, plan = _artifacts()
    plan["thumbnail_plan"][0]["title_pairing"] = 'Pair with ' + plan['title_angles'][1]['title']
    assert any('names a different A/B/C title' in error for error in validate_plan(plan, material, transcript))
    plan["thumbnail_plan"][0]["title_pairing"] = 'Pair with ' + plan['title_angles'][0]['title']
    assert validate_plan(plan, material, transcript) == []


def test_analyzer_calls_producer_once_revalidates_and_saves_rejected_output(tmp_path, monkeypatch):
    material, transcript, plan = _artifacts()

    class Backend:
        def __init__(self, response):
            self.response = response
            self.calls = 0

        def complete(self, *args):
            self.calls += 1
            return copy.deepcopy(self.response)

    worker = analyze.Analyzer.__new__(analyze.Analyzer)
    worker.cfg = type("Cfg", (), {"get": lambda self, key, default=None: 5})()
    worker.log = None
    worker.backend = Backend(plan)
    worker.prompt_versions = {}
    worker.calls_used = 0

    assert worker.producer_plan(material, transcript)["ruleset"] == "PRODUCER_BRAIN_V1"
    assert worker.backend.calls == 1 and worker.calls_used == 1

    bad = copy.deepcopy(plan)
    bad["title_angles"] = bad["title_angles"][:2]
    worker.backend = Backend(bad)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(analyze.ProducerPlanError, match="exactly three"):
        worker.producer_plan(material, transcript)
    assert len(list((tmp_path / "logs" / "rejected").glob("producer_brain_plan_*.json"))) == 1
    assert len(list((tmp_path / "logs" / "rejected").glob("producer_brain_plan_*.errors.txt"))) == 1


def test_real_case_report_has_exact_numbered_review_structure():
    _, _, plan = _artifacts()
    report = render_report(plan)

    for number, section in enumerate(REPORT_SECTIONS, start=1):
        assert f"## {number}. {section}" in report
    assert report.count("## CASE / SOURCE") == 1
    assert "Jules Regine Alonzo" not in "\n".join(
        row["title"] for row in plan["title_angles"]
    )


def test_prepare_request_is_backend_neutral_and_scoped_to_selected_hearing():
    material, transcript, _ = _artifacts()

    request = prepare_request(material, transcript)
    system = " ".join(request["system"].split())

    assert request["version"] == "1.3.3+PRODUCER_BRAIN_V1"
    assert "Do not call any tool or service" in system
    assert "[01:13:" in request["user"]
    assert "[00:10:" not in request["user"]
    assert request["schema"]["properties"]["ruleset"]["enum"] == ["PRODUCER_BRAIN_V1"]

    wrong_hearing = copy.deepcopy(transcript)
    wrong_hearing.video_id = "different-video"
    with pytest.raises(ValueError, match="video_id does not match"):
        prepare_request(material, wrong_hearing)
    assert any(
        "transcript.video_id" in error
        for error in validate_plan(load_json(PLAN_PATH), material, wrong_hearing)
    )


def test_prepare_request_does_not_leak_words_after_authorized_end():
    material, transcript, _ = _artifacts()
    end = float(material["case_source"]["hearing_end_s"])
    with_leak = copy.deepcopy(transcript)
    with_leak.words.append(Word(end + 5.0, "LEAKED_NEXT_CASE"))

    request = prepare_request(material, with_leak)

    assert "LEAKED_NEXT_CASE" not in request["user"]


def test_material_adapter_reuses_existing_pipeline_values():
    material, transcript, _ = _artifacts()
    case_source = material["case_source"]
    case = {
        "start_s": case_source["hearing_start_s"],
        "end_s": case_source["hearing_end_s"],
        "defendant_name": case_source["defendant_name_internal"],
        "cause_number": case_source["cause_number_internal"],
        "proceeding_type": case_source["proceeding_type"],
        "guilt_posture": case_source["guilt_posture"],
        "total_score": material["existing_editorial"]["selection_score"],
        "decision": material["existing_editorial"]["selection_decision"],
        "editorial": {
            "story_angle": material["existing_editorial"]["story_angle"],
            "money_moment": material["existing_editorial"]["money_moment"],
            "money_moment_s": material["existing_editorial"]["money_moment_s"],
        },
    }
    meta = {
        "url": case_source["source_url"],
        "docket_date": case_source["docket_date"],
    }

    adapted = material_from_pipeline(
        case_source["internal_case_id"],
        case,
        meta,
        transcript,
        ROOT / case_source["transcript_path"],
        material["visual_evidence"],
        material["public_records"],
    )

    assert adapted == material


def test_rejects_short_or_long_cold_open():
    material, transcript, plan = _artifacts()
    for duration in (4.9, 12.1):
        bad = copy.deepcopy(plan)
        bad["cold_open"]["end_s"] = bad["cold_open"]["start_s"] + duration
        assert any("duration must be 5-12 seconds" in error for error in validate_plan(bad, material, transcript))


def test_codex_output_schema_requires_story_windows_but_old_fixtures_stay_valid():
    material, transcript, plan = _artifacts()
    request = prepare_request(material, transcript)
    case_schema = request["schema"]["properties"]["case_source"]

    assert "story_windows" in case_schema["required"]
    assert set(case_schema["required"]) == set(case_schema["properties"])
    assert '"story_windows"' in request["user"]
    assert validate_plan(plan, material, transcript) == []


def test_fixed_hearing_source_id_is_canonicalised_without_changing_evidence():
    material, transcript, plan = _artifacts()
    bad = copy.deepcopy(plan)
    source = bad["story_arc"]["setup"]["sources"][0]
    original_quote = source["quote"]
    original_range = (source["start_s"], source["end_s"])
    source["source_id"] = material["case_source"]["video_id"]

    fixed = normalise_source_ids(bad)
    fixed_source = fixed["story_arc"]["setup"]["sources"][0]

    assert fixed_source["source_id"] == "hearing-transcript"
    assert fixed_source["quote"] == original_quote
    assert (fixed_source["start_s"], fixed_source["end_s"]) == original_range
    assert validate_plan(fixed, material, transcript) == []


def test_exact_quote_ranges_are_snapped_from_coarse_lines_without_rewriting_quote():
    material, transcript, plan = _artifacts()
    coarse = copy.deepcopy(plan)
    source = coarse["story_arc"]["setup"]["sources"][0]
    original_quote = source["quote"]
    source["start_s"] += 60
    source["end_s"] += 60
    assert any("not found in cited transcript range" in error for error in validate_plan(coarse, material, transcript))

    fixed = align_transcript_ranges(coarse, material, transcript)

    assert fixed["story_arc"]["setup"]["sources"][0]["quote"] == original_quote
    assert validate_plan(fixed, material, transcript) == []


def test_bad_quotes_and_short_titles_are_rejected_without_semantic_repair():
    material, transcript, plan = _artifacts()
    bad = copy.deepcopy(plan)
    source = bad["story_arc"]["setup"]["sources"][0]
    source["quote"] = source["quote"].replace(" ... ", " ")
    bad["short_plan"]["title"] = "Jail or GPS? He Must Choose in Court"
    original = copy.deepcopy(bad)
    errors = validate_plan(bad, material, transcript)
    assert any("not found in cited transcript range" in error for error in errors)
    assert any("50" in error and "title" in error for error in errors)
    assert bad == original


def test_complete_tail_is_allowed_but_outside_hearing_is_rejected():
    material, transcript, plan = _artifacts()
    tail = copy.deepcopy(plan)
    tail["longform_end_cta"]["payoff_end_s"] = material["case_source"]["hearing_end_s"]
    assert validate_plan(tail, material, transcript) == []
    tail["longform_end_cta"]["payoff_end_s"] += 1
    assert validate_plan(tail, material, transcript)


def test_short_summary_hook_is_replaced_only_by_its_exact_first_sequence_quote():
    material, transcript, plan = _artifacts()
    summarized = copy.deepcopy(plan)
    summarized["short_plan"]["hook"] = "A summarized hook the transcript never said."

    fixed = align_transcript_ranges(summarized, material, transcript)

    assert fixed["short_plan"]["hook"] == fixed["short_plan"]["sequence"][0]["quote"]
    assert fixed["short_plan"]["hook_start_s"] == fixed["short_plan"]["sequence"][0]["start_s"]
    assert validate_plan(fixed, material, transcript) == []


def test_editorial_thumbnail_text_needs_no_quote_source_but_quoted_text_does():
    material, transcript, plan = _artifacts()
    editorial = copy.deepcopy(plan)
    editorial["thumbnail_plan"][0]["text"] = "THE PHONE DISPUTE"
    editorial["thumbnail_plan"][0]["quote_sources"] = []
    assert validate_plan(editorial, material, transcript) == []

    quoted = copy.deepcopy(editorial)
    quoted["thumbnail_plan"][0]["text"] = '"THE PHONE DISPUTE"'
    assert any("quoted text requires evidence" in error for error in validate_plan(quoted, material, transcript))


def test_rejects_invented_evidence_and_cross_case_source_ranges():
    material, transcript, plan = _artifacts()
    invented = copy.deepcopy(plan)
    invented["intro_facts"][0]["sources"][0]["quote"] = "words that never occur in this hearing"
    assert any("not found in cited transcript range" in error for error in validate_plan(invented, material, transcript))

    outside = copy.deepcopy(plan)
    outside["story_arc"]["setup"]["sources"][0]["start_s"] = 10
    assert any("transcript source outside hearing" in error for error in validate_plan(outside, material, transcript))


def test_rejects_nonchronological_longform_and_unguarded_short_reordering():
    material, transcript, plan = _artifacts()
    longform = copy.deepcopy(plan)
    longform["story_arc"]["payoff"]["start_s"] = longform["story_arc"]["setup"]["start_s"] - 1
    assert any("must be chronological" in error for error in validate_plan(longform, material, transcript))

    short = copy.deepcopy(plan)
    short["short_plan"]["chronology_strategy"] = "payoff_first_recontextualized"
    short["short_plan"]["truthfulness_guard"] = "Keep it true."
    assert any("needs an explicit chronology and causality guard" in error for error in validate_plan(short, material, transcript))


def test_payoff_first_short_accepts_source_order_that_tracks_transcript_time():
    material, transcript, plan = _artifacts()
    reordered = copy.deepcopy(plan)
    reordered["short_plan"]["chronology_strategy"] = "payoff_first_recontextualized"
    reordered["short_plan"]["truthfulness_guard"] = (
        "Playback starts with a later payoff, then visibly cuts back to earlier context; "
        "do not imply the two ranges were an uninterrupted exchange or caused each other."
    )
    sequence = reordered["short_plan"]["sequence"]
    sequence[0], sequence[1] = sequence[1], sequence[0]
    for edit_order, row in enumerate(sequence, start=1):
        row["edit_order"] = edit_order
    chronological = sorted(range(len(sequence)), key=lambda index: sequence[index]["start_s"])
    for source_order, index in enumerate(chronological, start=1):
        sequence[index]["source_order"] = source_order
    reordered["short_plan"]["hook"] = sequence[0]["quote"]
    reordered["short_plan"]["hook_start_s"] = sequence[0]["start_s"]
    reordered["short_plan"]["hook_end_s"] = sequence[0]["end_s"]

    assert validate_plan(reordered, material, transcript) == []


def test_rejects_defendant_name_duplicate_titles_and_wrong_thumbnail_set():
    material, transcript, plan = _artifacts()
    named = copy.deepcopy(plan)
    named["title_angles"][0]["title"] = "Jules Explains Everything"
    assert any("contains defendant name" in error for error in validate_plan(named, material, transcript))

    duplicate = copy.deepcopy(plan)
    duplicate["title_angles"][1]["title"] = duplicate["title_angles"][0]["title"]
    assert any("genuinely distinct" in error for error in validate_plan(duplicate, material, transcript))

    thumbs = copy.deepcopy(plan)
    thumbs["thumbnail_plan"] = thumbs["thumbnail_plan"][:2]
    assert any("require A Court of Justice control" in error for error in validate_plan(thumbs, material, transcript))


def test_prompt_preserves_longform_chronology_and_fact_safety():
    prompt = (ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8")
    prompt = " ".join(prompt.split())

    assert "Never reorder the long-form body" in prompt
    assert "Facts are selected, not dumped" in prompt
    assert "prosecutors filed a motion seeking" in prompt
    assert "Do not call any tool or service" in prompt


def test_prompt_states_literal_evidence_contract():
    prompt = (ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8")
    prompt = " ".join(prompt.split())

    assert "literal `hearing-transcript`" in prompt
    assert "character-for-character" in prompt
    assert "must never be paraphrased" in prompt
    assert "including `story_windows`" in prompt


def test_prompt_uses_one_stable_package_and_executable_short_contract():
    prompt = " ".join((ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8").split())

    assert "A `court_of_justice_control`" in prompt
    assert "B `confrontation`" in prompt
    assert "C `reaction_story_moment`" in prompt
    assert "50–70 character title directions" in prompt
    assert "Pair title and thumbnail as complements" in prompt
    assert "Every `MAKE` sequence is an executable edit contract" in prompt
    assert "Do not bridge substantive dialogue" in prompt


def test_prompt_uses_clear_sentence_titles_and_bigger_thumbnail_copy():
    prompt = " ".join((ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8").split())
    assert "plain-English dramatic sentence" in prompt
    assert "front-load Judge Boyd plus the conflict" in prompt
    assert "4–8-word complete thought" in prompt
    assert "vague topic label" in prompt


def test_prompt_requires_spoken_story_first_intro_voice():
    prompt = (ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8")
    prompt = " ".join(prompt.split())

    assert "for the ear, not for a legal memo" in prompt
    assert "Open with the human conflict or unusual situation" in prompt
    assert "Prefer 3–5 short spoken sentences" in prompt
    assert "End on the question, choice, contradiction, or pressure" in prompt
    assert "must still remain fully supported by cited facts" in prompt


def test_end_cta_is_after_payoff_short_and_absent_for_incomplete_video():
    material, transcript, plan = _artifacts()

    before_payoff = copy.deepcopy(plan)
    before_payoff["longform_end_cta"]["payoff_end_s"] -= 1
    assert any("must not precede the verified payoff boundary" in error for error in validate_plan(before_payoff, material, transcript))

    too_long = copy.deepcopy(plan)
    too_long["longform_end_cta"]["end_screen_duration_s"] = 12
    assert any("must be 5-8 seconds" in error for error in validate_plan(too_long, material, transcript))

    named = copy.deepcopy(plan)
    named["longform_end_cta"]["spoken_line"] = "Watch another Jules hearing next."
    assert any("public CTA contains defendant name" in error for error in validate_plan(named, material, transcript))

    incomplete = copy.deepcopy(plan)
    incomplete["video_decision"]["decision"] = "HOLD"
    assert any("HOLD or SKIP must use NO_CTA" in error for error in validate_plan(incomplete, material, transcript))


def test_prompt_requires_payoff_safe_longform_end_cta():
    prompt = (ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8")
    prompt = " ".join(prompt.split())

    assert "Preserve the complete ruling" in prompt
    assert "0.5–1.5 seconds of breathing room" in prompt
    assert "5–8 second YouTube end-screen window" in prompt
    assert "Do not invent a relationship to an unverified next video" in prompt
    assert "return `NO_CTA`" in prompt
    assert "never configures YouTube's clickable elements" in prompt


def test_shorts_brain_rejects_overlong_make_and_bad_source_order():
    material, transcript, plan = _artifacts()
    assert plan["short_plan"]["ruleset"] == "SHORTS_BRAIN_V1"
    assert plan["short_plan"]["decision"] == "MAKE"

    overlong = copy.deepcopy(plan)
    overlong["short_plan"]["sequence"][0]["end_s"] += 20
    assert any("MAKE duration must be 15-59 seconds" in error for error in validate_plan(overlong, material, transcript))

    reordered = copy.deepcopy(plan)
    reordered["short_plan"]["sequence"][1]["source_order"] = 1
    assert any("source_order must match transcript chronology" in error for error in validate_plan(reordered, material, transcript))


def test_shorts_brain_rejects_make_when_its_own_limitation_admits_weak_opening():
    material, transcript, plan = _artifacts()
    weak = copy.deepcopy(plan)
    weak["short_plan"]["limitation"] = (
        "The opening is reflective rather than immediate, although a concrete confrontation appears later."
    )

    assert any(
        "MAKE admits a weak or delayed opening" in error
        for error in validate_plan(weak, material, transcript)
    )


def test_shorts_brain_accepts_one_continuous_range_with_named_hook_and_payoff():
    material, transcript, plan = _artifacts()
    one = copy.deepcopy(plan)
    start_s, end_s = 4610.58, 4649.0
    quote = transcript.text_between(start_s, end_s)
    one["short_plan"]["hook"] = quote
    one["short_plan"]["hook_start_s"] = start_s
    one["short_plan"]["hook_end_s"] = end_s
    one["short_plan"]["sequence"] = [{
        "edit_order": 1,
        "source_order": 1,
        "role": "hook_context_turn_payoff",
        "description": "One uninterrupted multi-speaker exchange contains every required beat.",
        "start_s": start_s,
        "end_s": end_s,
        "quote": quote,
        "sources": [{
            "source_type": "hearing_transcript",
            "source_id": "hearing-transcript",
            "start_s": start_s,
            "end_s": end_s,
            "quote": quote,
            "note": "Continuous verbatim hearing exchange with no bridged dialogue.",
        }],
    }]

    assert validate_plan(one, material, transcript) == []

    isolated = copy.deepcopy(one)
    isolated["short_plan"]["sequence"][0]["role"] = "hook"
    assert any("complete multi-beat exchange" in error for error in validate_plan(isolated, material, transcript))


def test_short_title_is_specific_and_not_a_longform_copy():
    material, transcript, plan = _artifacts()
    copied = copy.deepcopy(plan)
    copied["short_plan"]["title"] = copied["title_angles"][0]["title"]
    assert any("written for the Short" in error for error in validate_plan(copied, material, transcript))

    hashtag = copy.deepcopy(plan)
    hashtag["short_plan"]["title"] = "Judge Boyd Challenges the Courtroom Story #shorts"
    assert any("#shorts" in error for error in validate_plan(hashtag, material, transcript))


def test_prompt_defines_shorts_brain_as_editorial_handoff_not_renderer():
    prompt = (ROOT / "prompts" / "producer_brain_v1.md").read_text(encoding="utf-8")
    prompt = " ".join(prompt.split())

    assert "nested `short_plan` as `SHORTS_BRAIN_V1`" in prompt
    assert "A long-form `SKIP` may still produce a truthful Short" in prompt
    assert "coherent 15–59 second story excerpt" in prompt
    assert "aim around 50 seconds" in prompt
    assert "honest cliffhanger" in prompt
    assert "never mid-word or mid-sentence" in prompt
    assert "50–70 character plain-English dramatic sentence" in prompt
    assert "the promised continuation can be verified, use `HOLD`" in prompt
    assert "One continuous range is valid" in prompt
    assert "first 1–2 seconds" in prompt
    assert "never return `MAKE` with that defect" in prompt
    assert "Do not render, diarize, caption, reframe" in prompt
