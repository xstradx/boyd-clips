"""Focused proof for explicit historical-package revalidation receipts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from boydclips import historical_review as hr, readiness
from boydclips.config import load_config

OLD_MODEL = "gpt-5.6-sol"


def make_bundle(
    tmp_path: Path,
    *,
    candidate_labels: tuple[str, ...] = ("A", "B", "C"),
    safety_pass: bool = True,
    producer_brain: bool = False,
) -> tuple[Path, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    longform = tmp_path / "longform.mp4"
    short = tmp_path / "short.mp4"
    longform.write_bytes(b"fixture long-form")
    short.write_bytes(b"fixture short")
    candidates = {}
    for label, color in zip("ABC", ("red", "green", "blue")):
        if label not in candidate_labels:
            continue
        path = tmp_path / f"thumb_{label}.jpg"
        Image.new("RGB", (1280, 720), color).save(path)
        candidates[label] = str(path)

    packaging = {
        "hook_verified": True,
        "tags": ["judge boyd", "phone dispute"],
        "short_title": "The Missing Phone Story Changed This Court Hearing",
        "packaging_pairs": [
            {"label": label, "title": f"Distinct title {label}",
             "thumbnail_text": f"TEXT {label}", "reason": f"reason {label}"}
            for label in "ABC"
        ],
    }
    if producer_brain:
        packaging["producer_brain"] = {"story_summary": "A factual fixture summary."}

    manifest = {
        "status": "candidate",
        "review_required": True,
        "source": {"video_id": "video"},
        "case": {"start_s": 10.0, "end_s": 610.0, "story_windows": [[10.0, 610.0]]},
        "safety": {"safety_pass": safety_pass},
        "models": {"analysis_model": OLD_MODEL, "prompt_versions": {}},
        "packaging": packaging,
        "short_editor": {
            "ok": True,
            "render_qc": [{"gate": "fixture", "ok": True}],
            "visual_qc": {"ok": True, "checks": [{"check": "fixture", "ok": True}]},
        },
        "outputs": {
            "longform": {"clip_id": "video:10:longform", "file_path": str(longform)},
            "short": {
                "clip_id": "video:10:short",
                "file_path": str(short),
                "source_case_key": "video:10",
                "edit_plan": {"segments": [[10.0, 20.0]]},
            },
            "thumbnail": {
                "file_path": str(candidates.get("A") or ""),
                "status": "candidate",
                "candidates": candidates,
                "mode": "direct_gen",
                "model": "historical-thumbnail-model",
                "complete": True,
            },
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)
    return manifest_path, manifest


def approved_review(manifest_path: Path, **overrides) -> dict:
    review = {
        "status": "approved",
        "provider": "deepseek",
        "model": str(load_config().require("analysis.model")),
        "prompt_version": hr.REVIEW_PROMPT_VERSION,
        "reviewed_at": "2026-09-19T20:00:00+00:00",
        "input_sha256": hr.review_input_sha256(manifest_path),
        "checks": {key: True for key in hr.REVIEW_CHECKS},
        "summary": "Synthetic test review fixture; not a production review result.",
    }
    review.update(overrides)
    return review


def test_default_validation_still_rejects_historical_model(tmp_path):
    manifest_path, _manifest = make_bundle(tmp_path)

    with pytest.raises(readiness.ReadinessError, match="reasoning model"):
        readiness.validate_candidate_bundle(manifest_path, probe=False)


def test_approved_receipt_handles_historical_model_for_candidate_only(tmp_path):
    manifest_path, _manifest = make_bundle(tmp_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    checked = readiness.validate_candidate_bundle(
        manifest_path, probe=False, historical_receipt=receipt,
    )

    assert receipt["original_provenance"]["analysis_model"] == OLD_MODEL
    assert receipt["human_editorial_approval"] is False
    assert checked["ready"] is True
    assert checked["historical_review"]["reviewer"] == load_config().require("analysis.model")
    assert checked["historical_review"]["receipt_sha256"] == receipt["receipt_sha256"]
    assert "not human editorial approval" in " ".join(checked["notes"])

    # Approval remains on the default path and still refuses the old model.
    with pytest.raises(readiness.ReadinessError, match="reasoning model"):
        readiness.approve_manifest(manifest_path, "A", probe=False)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"status": "pending"}, "not approved"),
        ({"status": "rejected"}, "not approved"),
        ({"provider": "other"}, "not DeepSeek"),
        ({"model": "deepseek-v4-pro"}, "configured"),
        ({"prompt_version": ""}, "prompt"),
        ({"reviewed_at": ""}, "review time"),
        ({"input_sha256": "0" * 64}, "input hash"),
        ({"checks": {**{key: True for key in hr.REVIEW_CHECKS}, "source_fidelity": False}},
         "did not pass"),
    ],
)
def test_failed_or_incomplete_review_cannot_create_receipt(tmp_path, overrides, match):
    manifest_path, _manifest = make_bundle(tmp_path)

    with pytest.raises(hr.HistoricalReviewError, match=match):
        hr.create_receipt(manifest_path, approved_review(manifest_path, **overrides))


def test_missing_review_cannot_create_receipt(tmp_path):
    manifest_path, _manifest = make_bundle(tmp_path)

    with pytest.raises(hr.HistoricalReviewError, match="missing or not an object"):
        hr.create_receipt(manifest_path, None)


def test_altered_receipt_is_rejected(tmp_path):
    manifest_path, _manifest = make_bundle(tmp_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    with pytest.raises(readiness.ReadinessError, match="wrong kind or version"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt={},
        )

    altered = copy.deepcopy(receipt)
    altered["review"]["checks"]["source_fidelity"] = False

    with pytest.raises(readiness.ReadinessError, match="altered"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=altered,
        )


def test_changed_artifact_rejects_receipt(tmp_path):
    manifest_path, manifest = make_bundle(tmp_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))
    Path(manifest["outputs"]["short"]["file_path"]).write_bytes(b"changed after receipt")

    with pytest.raises(readiness.ReadinessError, match="hash changed"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=receipt,
        )


def test_changed_reviewer_config_rejects_receipt(tmp_path, monkeypatch):
    manifest_path, _manifest = make_bundle(tmp_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    class ChangedConfig:
        def require(self, key):
            assert key == "analysis.model"
            return "deepseek-v4-pro"

    monkeypatch.setattr(hr, "load_config", lambda: ChangedConfig())
    with pytest.raises(readiness.ReadinessError, match="configured"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=receipt,
        )


def test_changed_rules_reject_receipt(tmp_path, monkeypatch):
    manifest_path, _manifest = make_bundle(tmp_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    class ChangedContext:
        def provenance(self):
            return {"sha256": "changed-rules", "sources": []}

    monkeypatch.setattr(hr.stage_context, "load_context", lambda: ChangedContext())
    with pytest.raises(readiness.ReadinessError, match="input hash"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=receipt,
        )


def test_changed_copy_rejects_receipt(tmp_path):
    manifest_path, _manifest = make_bundle(tmp_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["packaging"]["packaging_pairs"][0]["thumbnail_text"] = "CHANGED COPY"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)

    with pytest.raises(readiness.ReadinessError, match="input hash"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=receipt,
        )


def test_receipt_cannot_pass_safety_or_missing_component(tmp_path):
    unsafe_path, _unsafe = make_bundle(tmp_path / "unsafe", safety_pass=False)
    unsafe_receipt = hr.create_receipt(unsafe_path, approved_review(unsafe_path))
    with pytest.raises(readiness.ReadinessError, match="safety gate"):
        readiness.validate_candidate_bundle(
            unsafe_path, probe=False, historical_receipt=unsafe_receipt,
        )

    incomplete_path, _incomplete = make_bundle(
        tmp_path / "incomplete", candidate_labels=("A", "B"),
    )
    incomplete_receipt = hr.create_receipt(
        incomplete_path, approved_review(incomplete_path),
    )
    with pytest.raises(readiness.ReadinessError, match="A, B and C"):
        readiness.validate_candidate_bundle(
            incomplete_path, probe=False, historical_receipt=incomplete_receipt,
        )


def test_receipt_cannot_bypass_ab_copy_review(tmp_path):
    manifest_path, _manifest = make_bundle(tmp_path, producer_brain=True)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    with pytest.raises(readiness.ReadinessError, match="missing or stale"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=receipt,
        )


def test_receipt_allows_historical_vertical_direction_but_not_pending_review(tmp_path):
    manifest_path, manifest = make_bundle(tmp_path)
    vertical = tmp_path / "vertical.jpg"
    Image.new("RGB", (1080, 1920), "black").save(vertical)
    short = manifest["outputs"]["short"]
    short["vertical_thumbnail_required"] = True
    short["vertical_thumbnail"] = {
        "file_path": str(vertical),
        "sha256": readiness.sha256_file(vertical),
        "short_sha256": readiness.sha256_file(Path(short["file_path"])),
        "direction_model": OLD_MODEL,
        "visual_review": {"full_size": "passed", "phone_size": "passed"},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)
    receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    checked = readiness.validate_candidate_bundle(
        manifest_path, probe=False, historical_receipt=receipt,
    )
    assert checked["ready"] is True

    short["vertical_thumbnail"]["direction_model"] = OLD_MODEL
    short["vertical_thumbnail"]["visual_review"] = {"full_size": "pending", "phone_size": "passed"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)
    pending_receipt = hr.create_receipt(manifest_path, approved_review(manifest_path))

    with pytest.raises(readiness.ReadinessError, match="full-size and phone-size"):
        readiness.validate_candidate_bundle(
            manifest_path, probe=False, historical_receipt=pending_receipt,
        )
