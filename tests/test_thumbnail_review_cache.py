"""The thumbnail meaning review is cached against what that stage is shown.

Confirmed overbroad invalidation: the cache compared whole-file digests for
every source and every stage, so an edit to an unrelated contract section, or
to the Shorts profile the reviewer never sees, bought another thumbnail model
call for identical copy. These tests use a fake backend and never call a model.
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest

from boydclips import stage_context, thumbnail_copy as tc
from boydclips.config import load_config

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("docs/SOL-PRODUCTION-CONTRACT.md")
PROFILE_PATH = Path("docs/SHORTS-EDITING-PROFILE.md")
UNRELATED_CONTRACT_HEADING = "## 5. Required closeout procedure"
PACKAGING_HEADING = "## 4. Presentation and packaging"


def package() -> dict:
    return {
        "thumbnail_quote": "PROBABLY HAUNTED?", "thumbnail_quote_yellow": "HAUNTED?",
        "producer_brain": {"case_source": {"video_id": "one", "transcript_sha256": "abc"},
                           "story_summary": "He entered an open building belonging to someone else.",
                           "thumbnail_plan": [{"concept": k, "quote_sources": [{"quote": "not your building"}]}
                                              for k in "ABC"], "title_angles": []},
        "packaging_pairs": [{"label": k, "title": f"Distinct title {k}", "thumbnail_text": text}
                            for k, text in zip("ABC", ["PROBABLY HAUNTED?", "BOYD: IT WASN'T YOURS", "WHY GO IN?"])],
    }


def verdict() -> dict:
    return {
        "concepts": [{"label": k, **{check: True for check in tc.CHECKS},
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
        self.cfg = {"analysis.model": str(load_config().require("packaging.thumbnail.direct.model"))}
        self.result = result or verdict()
        self.calls = 0
        self.visible_calls = 0

    def _complete(self, *args):
        if args[0] == "thumbnail_visible_review":
            self.visible_calls += 1
            return {"concepts": [{"label": k, "understandable": True, "references_clear": True,
                                  "interpretation": "The visible words form a complete idea.",
                                  "reason": "The visible title resolves the intended subject."}
                                 for k in "ABC"]}
        self.calls += 1
        assert args[0] == "thumbnail_copy_review"
        return copy.deepcopy(self.result)


def _fixture_root(tmp_path: Path) -> Path:
    for source in stage_context.CONTEXT_SOURCES:
        target = tmp_path / source.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source.path, target)
    return tmp_path


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


def test_unrelated_sections_do_not_buy_another_thumbnail_model_call(tmp_path, monkeypatch):
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(stage_context, "ROOT", root)
    p = package()
    a = Reviewer()
    path = tmp_path / "review.json"

    tc.ensure_review(a, p, path)  # the first review writes the cache
    tc.ensure_review(a, p, path)
    assert a.calls == 1 and a.visible_calls == 1

    before = stage_context.load_context().cache_signature()
    _amend_first_body_line(root / CONTRACT_PATH, UNRELATED_CONTRACT_HEADING)
    _amend_first_body_line(root / CONTRACT_PATH, "## 3. Editorial execution")
    _amend_first_body_line(root / PROFILE_PATH, "# Shorts editing profile")
    after = stage_context.load_context().cache_signature()
    assert before != after  # the whole-file signature really did move

    tc.ensure_review(a, p, path)
    assert a.calls == 1 and a.visible_calls == 1
    assert path.is_file()


def test_a_packaging_rule_edit_still_invalidates_the_review(tmp_path, monkeypatch):
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(stage_context, "ROOT", root)
    p = package()
    a = Reviewer()
    path = tmp_path / "review.json"

    tc.ensure_review(a, p, path)
    assert a.calls == 1
    _amend_first_body_line(root / CONTRACT_PATH, PACKAGING_HEADING)
    tc.ensure_review(a, p, path)
    assert a.calls == 2


@pytest.mark.parametrize("mutate", [
    lambda q: q["packaging_pairs"][1].update(thumbnail_text="IT WAS OPEN"),
    lambda q: q["packaging_pairs"][1].update(title="A changed title"),
    lambda q: q.update(thumbnail_quote="IT STILL WASN'T YOURS"),
    lambda q: q["producer_brain"]["case_source"].update(transcript_sha256="changed"),
], ids=["copy", "title", "shipped_words", "source"])
def test_copy_words_title_and_source_changes_still_invalidate(tmp_path, monkeypatch, mutate):
    monkeypatch.setattr(stage_context, "ROOT", _fixture_root(tmp_path))
    p = package()
    a = Reviewer()
    path = tmp_path / "review.json"

    tc.ensure_review(a, p, path)
    assert a.calls == 1
    changed = copy.deepcopy(p)
    mutate(changed)
    tc.ensure_review(a, changed, path)
    assert a.calls == 2


def test_a_cached_failure_still_holds_after_an_unrelated_edit(tmp_path, monkeypatch):
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(stage_context, "ROOT", root)
    result = verdict()
    result["concepts"][1].update(exchange_coherent=False)
    p = package()
    a = Reviewer(result)
    path = tmp_path / "review.json"

    with pytest.raises(tc.CopyReviewError, match="exchange_coherent"):
        tc.ensure_review(a, p, path)
    assert a.calls == 1 and path.is_file()

    _amend_first_body_line(root / CONTRACT_PATH, UNRELATED_CONTRACT_HEADING)
    with pytest.raises(tc.CopyReviewError, match="exchange_coherent"):
        tc.ensure_review(a, p, path)
    assert a.calls == 1  # the failed verdict is still the cached one, not re-bought
