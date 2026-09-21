"""A truthful thumbnail can still be a bland topic label - refuse it before images.

Nathan, 2026-09-19: "i feel like the words in the thumbnail kinda suck you need
to make a permament fix for that". The rescue images read THE PHONE QUESTION /
Then what? / NO TRUST LEFT. Those three lines are rejected for THIS package: the
repair is a judgement about hook specificity and tension, not a banned-word list,
so a specific line about the same phone dispute still has to pass.

The gate has to fire on BOTH builders and on the cache path. The configured
`legacy` compositor renders pkg["thumbnail_quote"] onto the finished image and
the direct A/B/C session renders the reviewed pairs, so neither may spend an
image - and a saved cache entry may not be reused - before the copy clears
review. THUMBNAIL_COPY_MEANING_V2 adds the hook judgements; a V1 verdict, or a
V2 verdict missing one of them, fails closed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from boydclips import readiness, thumbnail
from boydclips import thumbnail_copy as tc
from boydclips.config import load_config
from boydclips.pipeline import Pipeline


WEAK = ("THE PHONE QUESTION", "Then what?", "NO TRUST LEFT")
STRONG = (
    "HE KEPT THE PHONE ANYWAY?",
    'BOYD: "WHERE IS IT NOW?"',
    "SHE PAID FOR THAT PHONE",
)
DRAMATIC = ("HE ADMITTED HE SOLD IT", "THE PHONE WAS NEVER HERS", "BOYD CAUGHT THE LIE")


def configured_model() -> str:
    return str(load_config().require("packaging.thumbnail.direct.model"))


def concept(label: str, hook: str, *, reason: str | None = None, **flags) -> dict:
    row = {
        "label": label,
        **{check: True for check in tc.CHECKS},
        "viewer_question": f"What does this hearing do about the phone ({label})?",
        "source_anchor": f'hearing transcript: "{hook}"',
        "interpretation": "The words point at a specific choice in this hearing.",
        "reason": reason or "Hook, source and title pairing checked.",
    }
    row.update(flags)
    return row


def verdict(hooks, *, shipped_ok: bool = True, shipped_reason: str | None = None,
            **flags) -> dict:
    return {
        "concepts": [concept(label, hook, **flags) for label, hook in zip("ABC", hooks)],
        "shipped_quote": {
            "ok": shipped_ok,
            "viewer_question": "Whose phone was it, and what did he do with it?",
            "reason": shipped_reason or "The rendered words are his own excuse for keeping it.",
        },
    }


def package(texts=STRONG, *, quote: str | None = None, yellow: str | None = None) -> dict:
    texts = list(texts)
    quote = texts[0] if quote is None else quote
    return {
        "thumbnail_quote": quote,
        "thumbnail_quote_yellow": yellow or quote.split()[-1],
        "producer_brain": {
            "case_source": {"video_id": "one", "transcript_sha256": "abc"},
            "story_summary": "He said the phone was his; the court heard it was not.",
            "thumbnail_plan": [
                {"concept": label, "quote_sources": [{"quote": "it was in your pocket"}]}
                for label in "ABC"
            ],
            "title_angles": [],
        },
        "packaging_pairs": [
            {"label": label, "title": f"Distinct title {label}", "thumbnail_text": text}
            for label, text in zip("ABC", texts)
        ],
    }


class Reviewer:
    def __init__(self, result: dict):
        self.cfg = {"analysis.model": configured_model()}
        self.result = result
        self.calls = 0
        self.reserved_calls = 0

    def _complete(self, *args):
        if args[0] == "thumbnail_visible_review":
            self.visible_calls = getattr(self, "visible_calls", 0) + 1
            return {"concepts": [{"label": k, "understandable": True, "references_clear": True,
                "interpretation": "The visible words form a complete idea.",
                "reason": "The visible title resolves the intended subject."} for k in "ABC"]}
        self.calls += 1
        assert args[0] == "thumbnail_copy_review"
        return copy.deepcopy(self.result)


def test_layout_changes_reuse_semantic_review_but_context_changes_do_not():
    pkg = package()
    pkg["thumbnail_experiment"] = {"type": "thumbnail_text_only", "fixed_title": "Fixed title",
        "base_sha256": "a" * 64, "image_description": "Boyd and defendant from this hearing",
        "typography": {"max_lines": 2}}
    original = tc.input_hash(pkg)
    pkg["thumbnail_experiment"]["typography"]["max_lines"] = 1
    assert tc.input_hash(pkg) == original
    pkg["thumbnail_experiment"]["fixed_title"] = "Changed claim"
    assert tc.input_hash(pkg) != original


def test_case_specific_user_rejection_stops_before_any_paid_review(tmp_path):
    pkg = package()
    pkg["producer_brain"]["case_source"]["internal_case_id"] = "one:100"
    pkg["thumbnail_user_feedback"] = {"case_key": "one:100", "rejected_texts": [STRONG[1]]}
    reviewer = Reviewer(verdict(STRONG))
    with pytest.raises(tc.CopyReviewError, match="rejected by Nathan"):
        tc.ensure_review(reviewer, pkg, tmp_path / "review.json")
    assert reviewer.calls == 0 and getattr(reviewer, "visible_calls", 0) == 0
    pkg["thumbnail_user_feedback"]["rejected_texts"] = ["A different rejected headline"]
    tc.require_user_feedback(pkg)


def test_actual_pipeline_builds_one_row_experiment(tmp_path):
    pkg = package()
    base = tmp_path / "base.png"
    Image.new("RGB", (1280, 720), "navy").save(base)
    pkg["thumbnail_experiment"] = {"type": "thumbnail_text_only", "fixed_title": "Fixed title",
        "base_path": str(base), "base_sha256": hashlib.sha256(base.read_bytes()).hexdigest()}
    for p in pkg["packaging_pairs"]:
        p["title"] = "Fixed title"
        p["thumbnail_yellow"] = p["thumbnail_text"].split()[-1]
    reviewer = Reviewer(verdict(STRONG))
    pipe = object.__new__(Pipeline)
    pipe.cfg = {"packaging.thumbnail": {"mode": "legacy"},
                "packaging.thumbnail.direct.model": configured_model()}
    pipe._analyzer = reviewer
    out = pipe._produce_thumbnail(tmp_path / "unused.mp4", 0,
        {"start_s": 1, "hook_start_s": 3}, pkg, tmp_path)
    receipt = json.loads(Path(out["manifest"]).read_text(encoding="utf-8"))
    assert out["mode"] == "thumbnail_text_only"
    assert set(out["candidates"]) == set("ABC")
    assert all(len(v["lines"]) == 1 for v in receipt["variants"])
    base.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="base is missing or changed"):
        pipe._produce_thumbnail(tmp_path / "unused.mp4", 0,
            {"start_s": 1, "hook_start_s": 3}, pkg, tmp_path)
    assert reviewer.calls == 1


def test_weak_topic_label_refuses_before_the_legacy_compositor(tmp_path, monkeypatch):
    pkg = package(WEAK, quote="THE PHONE QUESTION", yellow="QUESTION")
    reviewer = Reviewer(verdict(WEAK, hook_specificity=False, tension_or_gap=False,
                                distinct_hook=False, reason="Topic label, no tension."))
    pipe = object.__new__(Pipeline)
    pipe.cfg = {"packaging.thumbnail": {"mode": "legacy"}}
    pipe._analyzer = reviewer
    pipe._thumbnail_images_remaining = 9
    monkeypatch.setattr(thumbnail, "build",
                        lambda *a, **k: pytest.fail("legacy compositor ran on refused copy"))

    with pytest.raises(tc.CopyReviewError, match="hook_specificity"):
        pipe._produce_thumbnail(tmp_path / "unused.mp4", 0.0,
                                {"start_s": 1.0, "hook_start_s": 3.0}, pkg, tmp_path)

    assert reviewer.calls == 1
    assert pipe._thumbnail_images_remaining == 9


def test_review_is_required_for_producer_packages_not_as_a_blanket_stop(tmp_path, monkeypatch):
    # Negative control: the gate is scoped to packages whose copy came from the
    # Producer Brain. A non-producer legacy package still renders, so the change
    # above is not "no thumbnail ever again".
    pkg = package(STRONG, quote="HE KEPT THE PHONE ANYWAY?", yellow="ANYWAY?")
    pkg.pop("producer_brain")
    rendered = []

    def fake_build(source, hook_at, white, yellow, staged, cfg):
        rendered.append(white)
        Image.new("RGB", (1280, 720), "red").save(staged)

    monkeypatch.setattr(thumbnail, "build", fake_build)
    pipe = object.__new__(Pipeline)
    pipe.cfg = {"packaging.thumbnail": {"mode": "legacy"}}
    pipe._analyzer = None
    out = pipe._produce_thumbnail(tmp_path / "unused.mp4", 0.0,
                                  {"start_s": 1.0, "hook_start_s": 3.0}, pkg, tmp_path)

    assert rendered and out["file_path"].endswith("thumbnail_quote.jpg")


def test_weak_topic_label_refuses_before_the_direct_builder_and_the_cache(
    tmp_path, monkeypatch,
):
    pkg = package(WEAK)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source fixture")
    case = {"start_s": 1.0, "hook_start_s": 3.0}

    # A complete, hash-consistent cache entry: exactly what a stale review would
    # have been reused against. Refusal must still come first.
    candidates = {}
    for label, color in zip("ABC", ("red", "green", "blue")):
        path = tmp_path / f"{label}.jpg"
        Image.new("RGB", (64, 36), color).save(path)
        candidates[label] = str(path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"concepts": {}}), encoding="utf-8")
    cache = {
        "key": {"source_sha256": readiness.sha256_file(source), "offset_s": 0.0,
                "case_start_s": 1.0, "hook_start_s": 3.0,
                "packaging_pairs": pkg["packaging_pairs"]},
        "output": {"mode": "direct_gen", "complete": True, "candidates": candidates,
                   "file_path": candidates["A"], "manifest": str(manifest)},
        "hashes": {label: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                   for label, path in candidates.items()},
    }
    (tmp_path / "thumbnail_cache.json").write_text(json.dumps(cache), encoding="utf-8")

    reviewer = Reviewer(verdict(WEAK, hook_specificity=False))
    pipe = object.__new__(Pipeline)
    pipe.cfg = {"packaging.thumbnail": {"mode": "direct_gen"}}
    pipe._analyzer = reviewer
    pipe._thumbnail_images_remaining = 9
    pipe._thumbnail_model_calls_used = 0
    monkeypatch.setattr(thumbnail, "build_direct",
                        lambda *a, **k: pytest.fail("direct builder ran on refused copy"))
    monkeypatch.setattr(thumbnail, "build",
                        lambda *a, **k: pytest.fail("fallback compositor ran on refused copy"))

    with pytest.raises(tc.CopyReviewError, match="hook_specificity"):
        pipe._produce_thumbnail(source, 0.0, case, pkg, tmp_path)

    assert reviewer.calls == 1
    assert pipe._thumbnail_images_remaining == 9


def test_specific_truthful_copy_passes_one_cached_call_then_a_weaker_copy_refuses(tmp_path):
    good = package(STRONG)
    reviewer = Reviewer(verdict(STRONG))
    path = tmp_path / "thumbnail_copy_review.json"

    report = tc.ensure_review(reviewer, good, path)
    assert report["version"] == tc.VERSION and reviewer.calls == 1
    tc.require_review(good)
    tc.ensure_review(reviewer, good, path)          # exact cache hit
    assert reviewer.calls == 1

    weak = package(WEAK, quote="THE PHONE QUESTION", yellow="QUESTION")
    reviewer.result = verdict(WEAK, hook_specificity=False, tension_or_gap=False)
    with pytest.raises(tc.CopyReviewError, match="hook_specificity"):
        tc.ensure_review(reviewer, weak, path)
    assert reviewer.calls == 2
    with pytest.raises(tc.CopyReviewError, match="hook_specificity"):
        tc.ensure_review(reviewer, weak, path)
    assert reviewer.calls == 2                    # refused verdict is held, not retried


def test_stale_v1_verdict_and_missing_hook_verdict_fail(tmp_path):
    pkg = package(STRONG)
    tc.ensure_review(Reviewer(verdict(STRONG)), pkg, tmp_path / "review.json")

    # A V1 verdict: the old four checks, no hook judgements, no shipped quote.
    v1 = {
        "version": "THUMBNAIL_COPY_MEANING_V1",
        "model": configured_model(),
        "input_sha256": tc.input_hash(pkg),
        "concepts": [
            {"label": label, "standalone_meaning": True, "exchange_coherent": True,
             "source_meaning_preserved": True, "title_complements": True,
             "interpretation": "Old verdict.", "reason": "Old verdict."}
            for label in "ABC"
        ],
    }
    with pytest.raises(tc.CopyReviewError, match="stale"):
        tc.require_review(pkg, v1)

    stale_path = tmp_path / "stale.json"
    stale_path.write_text(json.dumps(v1), encoding="utf-8")
    reviewer = Reviewer(verdict(STRONG))
    tc.ensure_review(reviewer, pkg, stale_path)     # a V1 file is never reused
    assert reviewer.calls == 1

    report = copy.deepcopy(pkg["thumbnail_copy_review"])
    for mutate, match in (
        (lambda r: r["concepts"][0].pop("hook_specificity"), "hook_specificity"),
        (lambda r: r["concepts"][0].update(distinct_hook=False), "distinct_hook"),
        (lambda r: r["concepts"][1].pop("viewer_question"), "viewer question"),
        (lambda r: r["concepts"][2].pop("source_anchor"), "source anchor"),
        (lambda r: r.pop("shipped_quote"), "long-form quote"),
    ):
        broken = copy.deepcopy(report)
        mutate(broken)
        with pytest.raises(tc.CopyReviewError, match=match):
            tc.require_review(pkg, broken)


def test_unsupported_dramatic_copy_fails_the_source_check(tmp_path):
    pkg = package(DRAMATIC)
    reviewer = Reviewer(verdict(DRAMATIC, source_meaning_preserved=False,
                                reason="No admission is in the supplied transcript."))
    path = tmp_path / "review.json"

    with pytest.raises(tc.CopyReviewError, match="source_meaning_preserved"):
        tc.ensure_review(reviewer, pkg, path)

    assert reviewer.calls == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["version"] == tc.VERSION
    assert saved["concepts"][0]["source_meaning_preserved"] is False


def test_rendered_longform_quote_is_judged_and_hashed(tmp_path):
    pkg = package(STRONG, quote="NO TRUST LEFT", yellow="LEFT")
    reviewer = Reviewer(verdict(STRONG, shipped_ok=False,
                                shipped_reason="A slogan with no case detail to answer."))

    with pytest.raises(tc.CopyReviewError, match="long-form thumbnail quote"):
        tc.ensure_review(reviewer, pkg, tmp_path / "review.json")

    # Changing only the rendered words invalidates any saved verdict.
    other = package(STRONG, quote="HE KEPT THE PHONE ANYWAY?", yellow="ANYWAY?")
    assert tc.input_hash(pkg) != tc.input_hash(other)


def test_rejected_wording_is_not_a_global_ban(tmp_path):
    hooks = ("HE KEPT THE PHONE ANYWAY?", 'BOYD: "WHERE IS IT NOW?"',
             "SHE PAID FOR THAT PHONE")
    specific = package(hooks, quote="HE KEPT THE PHONE ANYWAY?", yellow="ANYWAY?")
    tc.ensure_review(Reviewer(verdict(hooks)), specific, tmp_path / "specific.json")
    tc.require_review(specific)

    weak = package(WEAK, quote="THE PHONE QUESTION", yellow="QUESTION")
    with pytest.raises(tc.CopyReviewError, match="hook_specificity"):
        tc.ensure_review(Reviewer(verdict(WEAK, hook_specificity=False)), weak,
                         tmp_path / "weak.json")
    assert (tmp_path / "specific.json").is_file()


def packaging_bundle(tmp_path, *, review: bool) -> dict:
    packaging = package(STRONG, quote="HE KEPT THE PHONE ANYWAY?", yellow="ANYWAY?")
    packaging.update({
        "hook_verified": True,
        "tags": ["judge boyd", "phone dispute"],
        "short_title": "The Missing Phone Story Changed This Court Hearing",
        "packaging_pairs": [
            {"label": label, "title": f"Distinct title {label}",
             "thumbnail_text": text, "reason": f"reason {label}"}
            for label, text in zip("ABC", STRONG)
        ],
    })
    if review:
        tc.ensure_review(Reviewer(verdict(STRONG)), packaging,
                         tmp_path / "thumbnail_copy_review.json")
    return {
        "packaging": packaging,
        "outputs": {
            "longform": {"file_path": "unused"},
            "short": {"file_path": "unused"},
            "thumbnail": {"mode": "legacy", "file_path": "unused"},
        },
    }


def test_legacy_producer_package_cannot_pass_readiness_without_a_review(tmp_path):
    with pytest.raises(readiness.ReadinessError, match="missing or stale"):
        readiness._require_packaging_pairs(packaging_bundle(tmp_path, review=False))

    checked = readiness._require_packaging_pairs(packaging_bundle(tmp_path, review=True))
    assert set(checked) == {"A", "B", "C"}

    # Negative control: a legacy package that is not a Producer package has no
    # review to require, so readiness still passes it.
    plain = packaging_bundle(tmp_path, review=False)
    plain["packaging"].pop("producer_brain")
    assert set(readiness._require_packaging_pairs(plain)) == {"A", "B", "C"}
