"""Blind first-impression review: the words must make sense to a stranger.

Nathan rejected B "Leave or accept it!" and C "What if she cheated?" as not
making sense; the source-grounded reviewer, which sees the transcript, the plan
and the rationale, rubber-stamped both. ``boydclips.thumbnail_visible`` repairs
the reviewer's context instead of tuning the wording: it receives the thumbnail
words, the paired titles and a neutral image description and nothing else.

These tests pin that blindness at the byte level of the request, plus the
refusal and cache behaviour. No model is called and nothing is rendered.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from boydclips import thumbnail_visible as tv
from boydclips.config import load_config


REJECTED = ("LEAVE OR ACCEPT IT!", 'BOYD: "YOUR RELATIONSHIP IS DOOMED"', "WHAT IF SHE CHEATED?")
TRANSCRIPT = "he told her on 2026-04-02 that the shed was locked and she never came back"
STORY = "She kept the ring after the hearing and he never got it back."
RATIONALE = "Chosen because the judge's reaction scored highest on the rescue pass."
APPROVAL = "Nathan approved A on 2026-09-19"
SOURCE_QUOTE = "the transcript says he admitted the shed was his"


def configured_model() -> str:
    return str(load_config().require("packaging.thumbnail.direct.model"))


def package(texts=REJECTED) -> dict:
    """A package carrying every field this gate must never let through."""
    return {
        "thumbnail_quote": texts[0],
        "thumbnail_quote_yellow": "DOOMED",
        "transcript": TRANSCRIPT,
        "story_summary": STORY,
        "packaging_rationale": RATIONALE,
        "thumbnail_editorial_selection": {"winner": "A", "note": APPROVAL},
        "packaging_pairs": [
            {"label": label, "title": f"Judge Boyd reacts in court {label}",
             "thumbnail_text": text, "reason": RATIONALE,
             "thumbnail_hypothesis": "confrontation",
             "thumbnail_direction": {"reason_to_click": RATIONALE,
                                      "curiosity_gap": STORY}}
            for label, text in zip("ABC", texts)
        ],
        "producer_brain": {
            "case_source": {"video_id": "one", "transcript_sha256": "abc",
                            "transcript": TRANSCRIPT},
            "story_summary": STORY,
            "thumbnail_plan": [
                {"concept": label, "quote_sources": [{"quote": SOURCE_QUOTE}],
                 "subjects_and_expression": "Judge Boyd leaning forward, defendant calm"}
                for label in "ABC"
            ],
            "title_angles": [{"title": "Hidden angle", "reason": RATIONALE}],
        },
    }


def verdict(**flags) -> dict:
    return {"concepts": [
        {"label": label, "understandable": True, "references_clear": True,
         "interpretation": "The viewer reads one clear claim about the judge and the defendant.",
         "reason": "One idea, and the visible title names the person being referred to.",
         **flags}
        for label in "ABC"
    ]}


class Reviewer:
    """Stands in for the real Analyzer: records the exact args, calls no model."""

    def __init__(self, result: dict | None = None, model: str | None = None):
        self.cfg = {"analysis.model": model or configured_model()}
        self.result = result or verdict()
        self.calls = 0
        self.args: list[tuple] = []
        self.reserved_calls = 0

    def _complete(self, *args):
        self.calls += 1
        self.args.append(args)
        assert args[0] == tv.LABEL
        return copy.deepcopy(self.result)


def test_visible_input_is_only_the_words_titles_and_neutral_image_description():
    body = tv.visible_input(package())
    assert body["version"] == tv.VERSION
    assert [row["label"] for row in body["concepts"]] == list("ABC")
    for row in body["concepts"]:
        assert set(row) == {"label", "title", "thumbnail_text", "image_description"}
        assert row["image_description"] == "Judge Boyd leaning forward, defendant calm"
    assert body["concepts"][1]["thumbnail_text"] == REJECTED[1]


def test_plan_description_is_scrubbed_of_source_and_plot_residue():
    pkg = package()
    pkg["producer_brain"]["thumbnail_plan"][0]["subjects_and_expression"] = (
        'Defendant_frame_2 glaring (source: hearing 00:14:02) as he "admits the shed was his"'
    )
    described = tv.visible_input(pkg)["concepts"][0]["image_description"]
    assert "source" not in described.lower()
    assert "00:14" not in described and "frame" not in described.lower()
    assert "admits the shed" not in described
    assert "glaring" in described


def test_experiment_image_description_wins_and_its_own_scrubber_applies():
    pkg = package()
    pkg["thumbnail_experiment"] = {
        "type": "thumbnail_text_only", "fixed_title": "Fixed title",
        "image_description": 'Boyd and the defendant from this hearing (clip 00:31), judge "LISTEN"',
    }
    for row in pkg["packaging_pairs"]:
        row["title"] = "Fixed title"
    for row in tv.visible_input(pkg)["concepts"]:
        assert row["image_description"] == "Boyd and the defendant from this hearing, judge"


def test_request_bytes_exclude_transcript_summary_rationale_sources_and_approval(tmp_path):
    pkg = package()
    reviewer = Reviewer()
    tv.ensure_review(reviewer, pkg, tmp_path / "thumbnail_visible_review.json")

    assert len(reviewer.args) == 1
    # Five positional args only: no stage-context block can be attached, so the
    # canonical source-bearing contract cannot reach this call.
    assert len(reviewer.args[0]) == 5
    label, version, system, user_text, schema = reviewer.args[0]
    assert (label, version) == (tv.LABEL, tv.VERSION)
    assert schema["properties"]["concepts"]["maxItems"] == 3
    for secret in (TRANSCRIPT, STORY, RATIONALE, APPROVAL, SOURCE_QUOTE, "2026-04-02"):
        assert secret not in user_text
        assert secret not in system
    for leaked in ("story_summary", "transcript", "quote_sources", "rationale",
                   "CURRENT PROJECT RULES", "SOL-PRODUCTION-CONTRACT"):
        assert leaked not in user_text
    assert TRANSCRIPT.encode("utf-8") not in user_text.encode("utf-8")
    # The visible material is still there: the gate is blind, not empty.
    body = json.loads(user_text)
    assert {row["label"]: row["thumbnail_text"] for row in body["concepts"]} == dict(zip("ABC", REJECTED))
    assert {row["label"]: row["title"] for row in body["concepts"]}["B"] == "Judge Boyd reacts in court B"


def test_real_analyzer_stays_blind_even_with_the_rule_loader_installed(tmp_path):
    """The label, not the caller, is what keeps the source-bearing rules out."""
    from boydclips import stage_context
    from boydclips.analyze import Analyzer

    seen: dict = {}

    class Backend:
        def complete(self, system, request_text, schema, label):
            seen.update(system=system, request=request_text, label=label, schema=schema)
            return verdict()

    analyzer = object.__new__(Analyzer)
    analyzer.cfg = load_config()
    analyzer.backend = Backend()
    analyzer.calls_used = 0
    analyzer.reserved_calls = 0
    analyzer.usage_events = []
    analyzer.prompt_versions = {}
    # The pipeline installs this loader so the sibling copy review receives the
    # packaging rules. This gate must still receive none of them.
    analyzer.stage_context_loader = stage_context.load_context
    pkg = package()
    tv.ensure_review(analyzer, pkg, tmp_path / "visible.json")

    assert seen["label"] == tv.LABEL
    assert seen["request"] == json.dumps(tv.visible_input(pkg), ensure_ascii=False)
    assert "CURRENT PROJECT RULES" not in seen["request"]
    assert "SOL-PRODUCTION-CONTRACT" not in seen["request"]
    assert analyzer.calls_used == 1                    # spent through the Analyzer, as normal
    assert analyzer.usage_events[0]["stage"] == tv.LABEL
    assert "stage_context" not in analyzer.usage_events[0]


def test_consistent_review_is_cached_with_provenance_and_no_approval_claim(tmp_path):
    pkg = package()
    reviewer = Reviewer()
    path = tmp_path / "thumbnail_visible_review.json"
    report = tv.ensure_review(reviewer, pkg, path)
    assert (report["version"], report["model"]) == (tv.VERSION, configured_model())
    assert report["input_sha256"] == tv.input_hash(pkg)
    assert not [key for key in report if key in tv.APPROVAL_CLAIMS]
    assert pkg["thumbnail_visible_review"] == report
    tv.require_review(pkg)
    assert json.loads(path.read_text(encoding="utf-8"))["input_sha256"] == tv.input_hash(pkg)
    assert tv.ensure_review(reviewer, pkg, path) == report
    assert reviewer.calls == 1


@pytest.mark.parametrize("mutate, match", [
    (lambda r: r["concepts"][1].update(understandable=False), "understandable"),
    (lambda r: r["concepts"][2].update(references_clear=False), "references_clear"),
    (lambda r: r["concepts"][0].pop("references_clear"), "references_clear"),
    (lambda r: r["concepts"][1].update(interpretation=""), "understandable to a blind viewer"),
    (lambda r: r["concepts"][2].pop("reason"), "understandable to a blind viewer"),
])
def test_a_false_or_missing_flag_refuses_and_the_failure_is_cached(tmp_path, mutate, match):
    pkg = package()
    result = verdict()
    mutate(result)
    reviewer = Reviewer(result)
    path = tmp_path / "visible.json"
    with pytest.raises(tv.VisibleReviewError, match=match):
        tv.ensure_review(reviewer, pkg, path)
    assert reviewer.calls == 1 and path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["version"] == tv.VERSION          # the real result is cached, not dropped
    assert "thumbnail_visible_review" not in pkg   # and no approval is attached
    with pytest.raises(tv.VisibleReviewError, match=match):
        tv.ensure_review(reviewer, pkg, path)
    assert reviewer.calls == 1                     # refused verdict is held, not re-bought


def test_wrong_model_wrong_label_missing_rows_and_approval_claims_refuse(tmp_path):
    pkg = package()
    reviewer = Reviewer()
    tv.ensure_review(reviewer, pkg, tmp_path / "visible.json")
    report = pkg["thumbnail_visible_review"]
    for mutate in (
        lambda r: r.update(model="some-other-model"),
        lambda r: r["concepts"][1].update(label="A"),
        lambda r: r["concepts"].pop(),
        lambda r: r.pop("concepts"),
        lambda r: r.update(approved_by="operator note"),
    ):
        broken = copy.deepcopy(report)
        mutate(broken)
        with pytest.raises(tv.VisibleReviewError):
            tv.require_review(pkg, broken)
    assert tv.require_review(pkg) is None          # the intact report still passes


def test_title_copy_or_image_description_change_invalidates_and_respends(tmp_path):
    pkg = package()
    reviewer = Reviewer()
    path = tmp_path / "visible.json"
    tv.ensure_review(reviewer, pkg, path)
    for change in (lambda p: p["packaging_pairs"][1].update(title="A different title"),
                   lambda p: p["packaging_pairs"][2].update(thumbnail_text="WHAT IF HE CHEATED?")):
        changed = copy.deepcopy(pkg)
        change(changed)
        with pytest.raises(tv.VisibleReviewError, match="stale"):
            tv.require_review(changed)
        tv.ensure_review(reviewer, changed, path)
        assert reviewer.calls >= 2
    described = copy.deepcopy(pkg)
    described["producer_brain"]["thumbnail_plan"][0]["subjects_and_expression"] = "Boyd alone, calm"
    with pytest.raises(tv.VisibleReviewError, match="stale"):
        tv.require_review(described)


def test_other_configured_model_or_incomplete_labels_refuse_before_spending(tmp_path):
    path = tmp_path / "visible.json"
    other = Reviewer(model="another-model")
    with pytest.raises(tv.VisibleReviewError, match="configured"):
        tv.ensure_review(other, package(), path)
    assert other.calls == 0 and not path.exists()

    short = package()
    short["packaging_pairs"] = short["packaging_pairs"][:2]
    reviewer = Reviewer()
    for call in (lambda: tv.ensure_review(reviewer, short, path),
                 lambda: tv.require_review(short)):
        with pytest.raises(tv.VisibleReviewError, match="three A/B/C pairs"):
            call()
    assert reviewer.calls == 0 and not path.exists()


def test_a_saved_report_from_another_version_is_never_reused(tmp_path):
    pkg = package()
    path = tmp_path / "visible.json"
    path.write_text(json.dumps({"version": "VISIBLE_COPY_V0", "model": configured_model(),
                                "input_sha256": tv.input_hash(pkg),
                                "concepts": verdict()["concepts"]}), encoding="utf-8")
    reviewer = Reviewer()
    tv.ensure_review(reviewer, pkg, path)
    assert reviewer.calls == 1
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == tv.VERSION


def accepted_control():
    pkg = package()
    pkg["producer_brain"]["case_source"]["internal_case_id"] = "case:1"
    pkg["thumbnail_experiment"] = {"base_sha256": "a" * 64}
    pkg["thumbnail_user_feedback"] = {
        "case_key": "case:1", "fixed_title": pkg["packaging_pairs"][0]["title"],
        "base_sha256": "a" * 64, "accepted_texts": [pkg["packaging_pairs"][0]["thumbnail_text"]],
    }
    result = verdict()
    result["concepts"][0].update(understandable=False, references_clear=False)
    return pkg, result


def test_exact_human_choice_can_settle_clarity_without_rewriting_model_opinion(tmp_path):
    pkg, result = accepted_control()
    reviewer = Reviewer(result)
    report = tv.ensure_review(reviewer, pkg, tmp_path / "visible.json")
    assert report["concepts"][0]["understandable"] is False
    assert report["concepts"][0]["references_clear"] is False
    assert reviewer.calls == 1
    tv.require_review(pkg, report)


@pytest.mark.parametrize("mutate", [
    lambda p: p["thumbnail_user_feedback"].update(case_key="case:2"),
    lambda p: p["thumbnail_user_feedback"].update(fixed_title="Different title"),
    lambda p: p["thumbnail_user_feedback"].update(base_sha256="b" * 64),
    lambda p: p["thumbnail_user_feedback"].update(accepted_texts=["Different words"]),
    lambda p: (p["thumbnail_user_feedback"].pop("base_sha256"), p["thumbnail_experiment"].pop("base_sha256")),
])
def test_human_choice_does_not_transfer_to_another_case_title_image_or_copy(tmp_path, mutate):
    pkg, result = accepted_control()
    mutate(pkg)
    with pytest.raises(tv.VisibleReviewError, match="understandable"):
        tv.ensure_review(Reviewer(result), pkg, tmp_path / "visible.json")


@pytest.mark.parametrize("missing", ["understandable", "references_clear", "interpretation", "reason"])
def test_human_choice_does_not_waive_incomplete_review(tmp_path, missing):
    pkg, result = accepted_control()
    result["concepts"][0].pop(missing)
    with pytest.raises(tv.VisibleReviewError):
        tv.ensure_review(Reviewer(result), pkg, tmp_path / "visible.json")


def test_blind_failure_stops_source_review_and_legacy_render(tmp_path, monkeypatch):
    from boydclips import thumbnail
    from boydclips.pipeline import Pipeline
    from boydclips.thumbnail_copy import CopyReviewError
    pkg = package()
    result = verdict()
    result["concepts"][1]["understandable"] = False
    reviewer = Reviewer(result)
    rendered = []
    monkeypatch.setattr(thumbnail, "build", lambda *a, **k: rendered.append(True))
    pipe = object.__new__(Pipeline)
    pipe.cfg = {"packaging.thumbnail": {"mode": "legacy"}}
    pipe._analyzer = reviewer
    with pytest.raises(CopyReviewError, match="understandable"):
        pipe._produce_thumbnail(tmp_path / "source.mp4", 0.0,
                                {"start_s": 1.0, "hook_start_s": 3.0}, pkg, tmp_path)
    assert reviewer.calls == 1
    assert [args[0] for args in reviewer.args] == [tv.LABEL]
    assert not rendered
