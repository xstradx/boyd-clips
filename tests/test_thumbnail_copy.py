"""Meaning failures must stop image spending and stale package delivery."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from boydclips import thumbnail_copy as tc, readiness, thumbnail
from boydclips.config import load_config
from boydclips.pipeline import Pipeline


def package():
    return {
        "thumbnail_quote": "PROBABLY HAUNTED?", "thumbnail_quote_yellow": "HAUNTED?",
        "producer_brain": {"case_source": {"video_id": "one", "transcript_sha256": "abc"},
                           "story_summary": "He entered an open building belonging to someone else.",
                           "thumbnail_plan": [{"concept": k, "quote_sources": [{"quote": "not your building"}]}
                                              for k in "ABC"], "title_angles": []},
        "packaging_pairs": [{"label": k, "title": f"Distinct title {k}", "thumbnail_text": text}
                            for k, text in zip("ABC", ["PROBABLY HAUNTED?", "BOYD: IT WASN'T YOURS", "WHY GO IN?"])],
    }


def verdict():
    # 2026-09-19 (THUMBNAIL_COPY_MEANING_V2): one row per concept now has to
    # carry the hook judgements and a viewer question/source anchor, and the
    # report has to judge the wording the legacy compositor renders. `CHECKS`
    # is read from the module so this fixture cannot silently drift from the
    # contract it stands in for.
    return {
        "concepts": [{"label": k, **{c: True for c in tc.CHECKS},
                      "viewer_question": "Why did he think the building was his to enter?",
                      "source_anchor": 'hearing transcript: "not your building"',
                      "interpretation": "The judge challenges his right to enter.",
                      "reason": "Evidence supports meaning; the hook names his own excuse."}
                     for k in "ABC"],
        "shipped_quote": {
            "ok": True,
            "viewer_question": "Was he allowed to go into that building?",
            "reason": "The rendered words are his own excuse and raise the title's question.",
        },
    }


class Reviewer:
    def __init__(self, result=None):
        # 2026-09-16: follow the configured brain instead of pinning Sol, which
        # is unreachable from this PC.
        self.cfg = {"analysis.model": str(load_config().require("packaging.thumbnail.direct.model"))}
        self.result = result or verdict()
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


@pytest.mark.parametrize("text", ["YOU BEING THE ADULT", 'BOYD: “YOU BEING THE ADULT”',
                                 'HE: “PROBABLY HAUNTED” / BOYD: “YOU SHOULDN’T”',
                                 'This caption has far too many words to fit clearly on a mobile thumbnail'])
def test_user_rejections_stop_before_any_model_or_image_call(tmp_path, text):
    p = package(); p["packaging_pairs"][1]["thumbnail_text"] = text
    a = Reviewer()
    with pytest.raises(tc.CopyReviewError):
        tc.ensure_review(a, p, tmp_path / "review.json")
    assert a.calls == 0
    with pytest.raises(tc.CopyReviewError):
        thumbnail.build_direct(Path("unused.mp4"), 0, {}, p, tmp_path)


@pytest.mark.parametrize("text", ["YOU'RE THE ADULT", 'HE: “IT WAS OPEN” / BOYD: “IT STILL WASN’T YOURS”',
                                 "BOYD: YOU FOLLOWED A TEEN—TO PAWN STOLEN PROPERTY?", ""])
def test_coherent_short_copy_not_rejected_for_paraphrase_or_style(text):
    assert tc.fragment_errors(text) == []


def test_separate_review_refuses_incoherence_even_when_words_are_real(tmp_path):
    p = package(); result = verdict()
    result["concepts"][1].update(exchange_coherent=False, reason="Reply addresses an unrelated question.")
    a = Reviewer(result); path = tmp_path / "review.json"
    with pytest.raises(tc.CopyReviewError, match="exchange_coherent"):
        tc.ensure_review(a, p, path)
    assert path.is_file() and a.calls == 1
    with pytest.raises(tc.CopyReviewError):
        tc.ensure_review(a, p, path)
    assert a.calls == 1  # failed cache is held, not retried until allowance disappears


def test_exact_review_cache_saves_calls_but_copy_title_and_source_changes_invalidate(tmp_path):
    p = package(); a = Reviewer(); path = tmp_path / "review.json"
    tc.ensure_review(a, p, path); tc.ensure_review(a, p, path)
    assert a.calls == 1
    for change in (lambda q: q["packaging_pairs"][1].update(thumbnail_text="NOT YOUR BUILDING"),
                   lambda q: q["packaging_pairs"][1].update(title="Changed title"),
                   lambda q: q["producer_brain"]["case_source"].update(transcript_sha256="changed")):
        updated = copy.deepcopy(p); change(updated)
        with pytest.raises(tc.CopyReviewError, match="stale"):
            tc.require_review(updated)
    p["packaging_pairs"][1]["title"] = "Revised title"
    tc.ensure_review(a, p, path)
    assert a.calls == 2


@pytest.mark.parametrize("field", ["pair", "rendered_quote"])
def test_case_feedback_blocks_rejected_words_before_either_model_call(tmp_path, field):
    p = package()
    p["producer_brain"]["case_source"]["internal_case_id"] = "case:1"
    p["thumbnail_user_feedback"] = {
        "case_key": "case:1", "rejected_texts": ["Leave or accept it!"],
    }
    if field == "pair":
        p["packaging_pairs"][1]["thumbnail_text"] = "LEAVE OR ACCEPT IT"
    else:
        p["thumbnail_quote"] = "Leave or accept it!"
    reviewer = Reviewer()
    with pytest.raises(tc.CopyReviewError, match="rejected by Nathan"):
        tc.ensure_review(reviewer, p, tmp_path / "review.json")
    assert reviewer.calls == 0 and getattr(reviewer, "visible_calls", 0) == 0
    # A different, unblocked line still goes through both independent reviews.
    if field == "pair":
        p["packaging_pairs"][1]["thumbnail_text"] = "BOYD: IT WASN'T YOURS"
    else:
        p["thumbnail_quote"] = "PROBABLY HAUNTED?"
    tc.ensure_review(reviewer, p, tmp_path / "review.json")
    assert reviewer.calls == 1 and reviewer.visible_calls == 1


def test_accepted_copy_does_not_waive_factual_source_review(tmp_path):
    p = package()
    p["producer_brain"]["case_source"]["internal_case_id"] = "case:1"
    p["thumbnail_experiment"] = {"base_sha256": "a" * 64}
    p["thumbnail_user_feedback"] = {
        "case_key": "case:1", "fixed_title": p["packaging_pairs"][0]["title"],
        "base_sha256": "a" * 64, "accepted_texts": [p["packaging_pairs"][0]["thumbnail_text"]],
    }
    result = verdict()
    result["concepts"][0]["source_meaning_preserved"] = False
    with pytest.raises(tc.CopyReviewError, match="source_meaning_preserved"):
        tc.ensure_review(Reviewer(result), p, tmp_path / "review.json")


@pytest.mark.parametrize("defect", ["missing", "duplicate", "wrong_model"])
def test_no_partial_or_wrong_model_approval(tmp_path, defect):
    p = package(); tc.ensure_review(Reviewer(), p, tmp_path / "review.json")
    r = p["thumbnail_copy_review"]
    if defect == "missing": r["concepts"].pop()
    elif defect == "duplicate": r["concepts"][1]["label"] = "A"
    else: r["model"] = "some-other-model"
    with pytest.raises(tc.CopyReviewError): tc.require_review(p)


def test_other_configured_model_cannot_be_stamped_as_sol(tmp_path):
    a=Reviewer();a.cfg['analysis.model']='another-model'
    with pytest.raises(tc.CopyReviewError,match='configured'):
        tc.ensure_review(a,package(),tmp_path/'review.json')
    assert a.calls==0


def test_known_editorial_failure_cannot_be_hidden_by_technical_qc():
    with pytest.raises(readiness.ReadinessError,match='unresolved blockers'):
        readiness._require_qc({'editorial_review':{'blockers':['Ambiguous caption changes the answer.']}})


def test_pipeline_blocks_bad_copy_before_builder_and_preserves_image_allowance(tmp_path, monkeypatch):
    p = package(); p["packaging_pairs"][1]["thumbnail_text"] = "YOU BEING THE ADULT"
    pipe = object.__new__(Pipeline)
    pipe.cfg = {"packaging.thumbnail": {"mode": "direct_gen"}}
    pipe._analyzer = Reviewer(); pipe._thumbnail_images_remaining = 6
    pipe._thumbnail_model_calls_used = 2
    monkeypatch.setattr(thumbnail, "build_for_mode", lambda *a: pytest.fail("image builder called"))
    with pytest.raises(tc.CopyReviewError):
        pipe._produce_thumbnail(tmp_path / "unused.mp4", 0, {"hook_start_s": 2}, p, tmp_path)
    assert pipe._analyzer.calls == 0 and pipe._analyzer.reserved_calls == 0
    assert pipe._thumbnail_images_remaining == 6


def rendered(tmp_path, p):
    candidates = {}; concepts = {}
    for row in p["packaging_pairs"]:
        k = row["label"]; image = tmp_path / f"{k}.jpg"; image.write_bytes(f"image {k}".encode())
        candidates[k] = str(image)
        concepts[k] = {"ok": True, "reported": {"text": row["thumbnail_text"]},
                       "gates": [{"gate": gate, "ok": True} for gate in
                                 ["reviewed_copy_unchanged", "complete_copy", "critical_copy_words_visible"]],
                       "copy_binding": {"words": tc.copy_words(row["thumbnail_text"]),
                                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}}
    path = tmp_path / "manifest.json"; path.write_text(json.dumps({"concepts": concepts}))
    return {"candidates": candidates, "manifest": str(path)}


def test_changed_image_or_old_rendered_words_cannot_reuse_approved_copy(tmp_path):
    p = package(); tc.ensure_review(Reviewer(), p, tmp_path / "review.json")
    output = rendered(tmp_path, p); tc.require_rendered_copy(p, output)
    image = Path(output["candidates"]["B"]); image.write_bytes(b"replaced image")
    with pytest.raises(tc.CopyReviewError, match="image bytes"): tc.require_rendered_copy(p, output)
    output = rendered(tmp_path, p)
    m = json.loads(Path(output["manifest"]).read_text()); m["concepts"]["B"]["reported"]["text"] = "YOU SHOULD"
    Path(output["manifest"]).write_text(json.dumps(m))
    with pytest.raises(tc.CopyReviewError, match="wording differs"): tc.require_rendered_copy(p, output)


def test_readiness_enforces_rendered_copy_without_image_spending(tmp_path):
    p = package(); tc.ensure_review(Reviewer(), p, tmp_path / "review.json")
    with pytest.raises(readiness.ReadinessError, match="rendered-copy evidence"):
        readiness._require_packaging_pairs({"packaging": p, "outputs": {
            "longform": {"file_path": "unused"}, "short": {"file_path": "unused"}, "thumbnail": {"mode": "direct_gen"}}})


def test_unchanged_image_cache_cannot_bypass_current_meaning_review(tmp_path, monkeypatch):
    p = package(); a = Reviewer(); tc.ensure_review(a, p, tmp_path / "thumbnail_copy_review.json")
    output = rendered(tmp_path, p); output['complete'] = True
    source = tmp_path / "source.mp4"; source.write_bytes(b"source")
    case = {"start_s": 0, "hook_start_s": 2}
    key = {"source_sha256": hashlib.sha256(b"source").hexdigest(), "offset_s": 0,
           "case_start_s": 0, "hook_start_s": 2, "packaging_pairs": p["packaging_pairs"]}
    cache = {"key": key, "output": output,
             "hashes": {k: hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in output['candidates'].items()}}
    (tmp_path / "thumbnail_cache.json").write_text(json.dumps(cache))
    # The image bytes and cache match, but a QC sidecar was replaced with old text.
    m = json.loads(Path(output['manifest']).read_text()); m['concepts']['B']['reported']['text'] = 'YOU SHOULD'
    Path(output['manifest']).write_text(json.dumps(m))
    pipe=object.__new__(Pipeline);pipe.cfg={"packaging.thumbnail":{"mode":"direct_gen"}};pipe._analyzer=a
    import boydclips.pipeline as module
    monkeypatch.setattr(module,'require_thumbnail',lambda path:path)
    monkeypatch.setattr(thumbnail,'build_for_mode',lambda *args:pytest.fail('builder called'))
    with pytest.raises(tc.CopyReviewError,match='wording differs'):
        pipe._produce_thumbnail(source,0,case,p,tmp_path)
    assert a.calls == 1
