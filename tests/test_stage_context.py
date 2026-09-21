"""Focused proof for the recovered-rule handoff.

These tests use a fake backend and never call a model. They check that the
current production rules reach the isolated planning and packaging calls, that
the rule context is recorded in model-call provenance, that a changed rule
invalidates the Producer cache signature, and that a missing canonical source
stops before any backend call.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
from pathlib import Path

import pytest

from boydclips import analyze, pipeline, stage_context
from boydclips.config import load_config
from boydclips import producer_brain
from boydclips.producer_brain import load_json, load_transcript, prepare_request

ROOT = Path(__file__).resolve().parents[1]
MATERIAL_PATH = ROOT / "docs" / "producer_brain_v1" / "real_case_input.json"
PLAN_PATH = ROOT / "docs" / "producer_brain_v1" / "real_case_plan.json"

# The model is read from config at call time; this sentinel proves the recorded
# name comes from there rather than from a literal in the recorder.
CONFIGURED_MODEL = "deepseek-flash"


class RecordingBackend:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def complete(self, system, user, schema, label):
        self.calls.append({"system": system, "user": user, "schema": schema, "label": label})
        return copy.deepcopy(self.response)


def _artifacts():
    material = load_json(MATERIAL_PATH)
    return material, load_transcript(material), load_json(PLAN_PATH)


def _analyzer(backend, model: str = CONFIGURED_MODEL):
    cfg = load_config()
    cfg._data["analysis"]["model"] = model
    worker = analyze.Analyzer.__new__(analyze.Analyzer)
    worker.cfg = cfg
    worker.log = None
    worker.backend = backend
    worker.prompt_versions = {}
    worker.calls_used = 0
    worker.usage_events = []
    return worker


def _fixture_root(tmp_path: Path) -> Path:
    """A copy of the canonical sources the context reads, for edit tests."""
    for source in stage_context.CONTEXT_SOURCES:
        target = tmp_path / source.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source.path, target)
    return tmp_path


# --------------------------------------------------------------- the context


def test_context_is_deterministic_and_bounded_while_sources_are_unchanged():
    first = stage_context.load_context()
    second = stage_context.load_context()

    assert first.text == second.text
    assert first.sha256 == second.sha256
    assert first.cache_signature() == second.cache_signature()
    assert first.provenance() == second.provenance()
    assert first.cache_signature()["sources"] == {
        block.source.key: block.file_sha256 for block in first.blocks
    }
    # Bounded: two contract sections plus the profile table, not a whole corpus.
    assert len(first.text) < 40_000


def test_context_covers_only_the_stages_that_need_it():
    context = stage_context.load_context()

    assert context.applies_to("producer_brain_v1")
    assert context.applies_to("package_post")
    assert context.applies_to("thumbnail_copy_review")
    # Segmentation and scoring have their own prompt contracts; they are not
    # packaging or planning calls and must not be inflated by this context.
    assert not context.applies_to("segment_cases")
    assert not context.applies_to("score_cases")
    assert context.blocks_for("score_cases") == ""

    review = context.blocks_for("thumbnail_copy_review")
    assert "Presentation and packaging" in review
    assert "Editorial execution" not in review


def test_every_source_hash_is_a_digest_of_the_file_actually_read():
    context = stage_context.load_context()
    for block in context.blocks:
        raw = (ROOT / block.source.path).read_text(encoding="utf-8")
        assert block.file_sha256 == hashlib.sha256((ROOT / block.source.path).read_bytes()).hexdigest()
        assert block.text in raw.replace("\r\n", "\n")


def _amend_first_body_line(path: Path, heading: str) -> None:
    """Append to the first prose line of one section, leaving headings alone."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading)
    index = next(
        number for number in range(start + 1, len(lines))
        if lines[number].strip() and not lines[number].startswith("#")
    )
    lines[index] = lines[index].rstrip() + " (amended at review)"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_stage_signature_binds_only_the_sections_that_stage_is_shown():
    context = stage_context.load_context()

    review = context.cache_signature("thumbnail_copy_review")
    assert set(review["sources"]) == {"contract.packaging"}
    assert review["sources"]["contract.packaging"] == next(
        block.section_sha256 for block in context.blocks if block.source.key == "contract.packaging"
    )
    assert review["context_sha256"] == hashlib.sha256(
        context.blocks_for("thumbnail_copy_review").encode("utf-8")
    ).hexdigest()
    # A stage that needs no source still has a stable, empty signature.
    assert context.cache_signature("score_cases") == {
        "context_sha256": hashlib.sha256(b"").hexdigest(), "sources": {},
    }
    # The unlabeled signature keeps the whole-file Producer binding.
    assert context.cache_signature()["sources"] == {
        block.source.key: block.file_sha256 for block in context.blocks
    }
    assert context.cache_signature("thumbnail_copy_review") != context.cache_signature()


def test_edits_outside_a_stages_sections_do_not_invalidate_that_stage(tmp_path):
    root = _fixture_root(tmp_path)
    before = stage_context.load_context(root=root)

    # One unrelated contract section and the Shorts profile, which the
    # thumbnail review never sees, both move whole-file digests.
    _amend_first_body_line(root / "docs" / "SOL-PRODUCTION-CONTRACT.md", "## 5. Required closeout procedure")
    _amend_first_body_line(root / "docs" / "SHORTS-EDITING-PROFILE.md", "# Shorts editing profile")
    after = stage_context.load_context(root=root)

    assert before.cache_signature() != after.cache_signature()
    assert before.cache_signature("thumbnail_copy_review") == \
        after.cache_signature("thumbnail_copy_review")
    # An edit inside a section the stage is shown still invalidates it.
    _amend_first_body_line(root / "docs" / "SOL-PRODUCTION-CONTRACT.md", "## 4. Presentation and packaging")
    edited = stage_context.load_context(root=root)
    assert edited.cache_signature("thumbnail_copy_review") != \
        after.cache_signature("thumbnail_copy_review")


# ------------------------------------------------- the context reaches a call


def test_current_rules_reach_the_producer_request_and_its_provenance():
    material, transcript, plan = _artifacts()
    backend = RecordingBackend(plan)
    worker = _analyzer(backend)

    worker.producer_plan(material, transcript)

    assert len(backend.calls) == 1
    sent = backend.calls[0]["user"]
    context = stage_context.load_context()
    assert context.blocks_for("producer_brain_v1") in sent
    assert "3. Editorial execution" in sent
    assert "4. Presentation and packaging" in sent
    assert "| dimension | preference | evidence | source | confidence |" in sent
    # The stage's own request is unchanged and still follows the context.
    assert sent == context.blocks_for("producer_brain_v1") + "\n\n" + prepare_request(material, transcript)["user"]

    event = worker.usage_events[0]
    assert event["stage_context"]["sha256"] == context.sha256
    assert {row["key"] for row in event["stage_context"]["sources"]} == {
        block.source.key for block in context.blocks
    }
    assert event["request_sha256"] != event["input_sha256"]


def test_thumbnail_copy_review_gets_the_packaging_rules_and_other_stages_do_not():
    backend = RecordingBackend({"concepts": []})
    worker = _analyzer(backend)
    worker.stage_context_loader = stage_context.load_context

    # thumbnail_copy.ensure_review reaches the backend through _complete with
    # its own inline system prompt, not through a prompt file.
    worker._complete("thumbnail_copy_review", "V1", "system", "review input", {})
    worker._complete("score_cases", "v", "system", "score input", {})

    review, score = backend.calls[0]["user"], backend.calls[1]["user"]
    assert "Presentation and packaging" in review
    assert "Editorial execution" not in review
    assert review.endswith("review input")
    assert score == "score input"
    assert "stage_context" not in worker.usage_events[1]


def test_recorded_model_comes_from_live_config_not_a_literal():
    backend = RecordingBackend({"ok": True})
    worker = _analyzer(backend, model="deepseek-v4-pro-test")

    worker._call("package_post", "text", {})

    event = worker.usage_events[0]
    assert event["model"] == "deepseek-v4-pro-test"
    assert event["model"] == worker.cfg.get("analysis.model")
    assert event["model"] != CONFIGURED_MODEL


# ------------------------------------------------------- the Producer cache


def test_one_edited_rule_invalidates_the_producer_cache_signature(tmp_path):
    root = _fixture_root(tmp_path)
    before = stage_context.load_context(root=root)

    # Amend one rule inside the editorial contract, leaving the rest of the
    # document alone. The line is taken from what the context actually quoted,
    # so the test follows prose edits instead of pinning an old sentence.
    rule_line = next(
        line for line in before.blocks[0].text.splitlines()
        if line.strip() and not line.startswith("#")
    )
    contract = root / "docs" / "SOL-PRODUCTION-CONTRACT.md"
    text = contract.read_text(encoding="utf-8")
    assert rule_line in text
    contract.write_text(
        text.replace(rule_line, rule_line + " (amended at review)", 1), encoding="utf-8"
    )

    after = stage_context.load_context(root=root)
    assert after.blocks[0].text != before.blocks[0].text
    # Only the amended section changed; the same file's other excerpt is intact
    # even though the file digest moved.
    assert after.blocks[1].text == before.blocks[1].text
    assert after.blocks[1].section_sha256 == before.blocks[1].section_sha256
    assert before.sha256 != after.sha256
    assert before.cache_signature() != after.cache_signature()
    assert after.cache_signature()["sources"]["contract.editorial"] != \
        before.cache_signature()["sources"]["contract.editorial"]

    material, transcript, plan = _artifacts()
    assert pipeline.producer_cache_is_current(
        material, plan, before.cache_signature(), material, before, transcript
    )
    assert not pipeline.producer_cache_is_current(
        material, plan, before.cache_signature(), material, after, transcript
    )


def test_producer_cache_without_a_context_stamp_is_a_miss_not_a_restamp():
    material, transcript, plan = _artifacts()
    context = stage_context.load_context()

    # An older review directory has the input and the plan but no signature.
    assert not pipeline.producer_cache_is_current(
        material, plan, None, material, context, transcript
    )
    # A plan that no longer validates is a miss however current the rules are.
    assert not pipeline.producer_cache_is_current(
        {}, plan, context.cache_signature(), material, context, transcript
    )
    # The context is not smuggled into the material schema: it still validates
    # as Producer Brain material on its own.
    assert producer_brain.validate_material(material) == []


# ---------------------------------------------------- missing sources fail cold


def test_missing_canonical_source_fails_before_any_backend_call(tmp_path, monkeypatch):
    material, transcript, plan = _artifacts()
    backend = RecordingBackend(plan)
    worker = _analyzer(backend)

    monkeypatch.setattr(stage_context, "ROOT", tmp_path)
    with pytest.raises(stage_context.MissingStageSourceError):
        worker.producer_plan(material, transcript)

    assert backend.calls == []
    assert worker.calls_used == 0
    assert worker.usage_events == []


def test_stage_loader_failure_also_stops_before_the_backend_call(tmp_path):
    backend = RecordingBackend({"ok": True})
    worker = _analyzer(backend)
    worker.stage_context_loader = lambda: stage_context.load_context(root=tmp_path)

    with pytest.raises(stage_context.MissingStageSourceError):
        worker._complete("thumbnail_copy_review", "V1", "system", "review input", {})

    assert backend.calls == []
    assert worker.calls_used == 0
    assert worker.usage_events == []


def test_missing_section_is_reported_not_silently_dropped(tmp_path):
    root = _fixture_root(tmp_path)
    profile = root / "docs" / "SHORTS-EDITING-PROFILE.md"
    profile.write_text(profile.read_text(encoding="utf-8").replace(
        "# Shorts editing profile", "# Shorts profile (renamed)"
    ), encoding="utf-8")

    with pytest.raises(stage_context.MissingStageSourceError, match="SHORTS-EDITING-PROFILE"):
        stage_context.load_context(root=root)


def test_oversized_rules_fail_before_a_call_instead_of_silent_truncation(tmp_path, monkeypatch):
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(stage_context, "MAX_CONTEXT_CHARS", 100)
    backend = RecordingBackend({})
    worker = _analyzer(backend)
    worker.stage_context_loader = lambda: stage_context.load_context(root=root)
    with pytest.raises(stage_context.MissingStageSourceError, match="budget"):
        worker._complete("thumbnail_copy_review", "v", "system", "text", {})
    assert backend.calls == []


def test_review_provenance_hashes_exact_selected_context():
    backend = RecordingBackend({})
    worker = _analyzer(backend)
    worker._complete("thumbnail_copy_review", "v", "system", "input", {})
    context = stage_context.load_context()
    sent_context = context.blocks_for("thumbnail_copy_review")
    receipt = worker.usage_events[0]["stage_context"]
    assert receipt["sha256"] == hashlib.sha256(sent_context.encode()).hexdigest()
    assert [s["key"] for s in receipt["sources"]] == ["contract.packaging"]
