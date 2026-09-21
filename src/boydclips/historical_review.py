"""Explicit review receipt for historical packages produced by another model.

This module records a current factual/semantic review; it does not perform one
and it is not human editorial approval. A receipt is accepted only when it was
created from an explicit, approved review by the configured DeepSeek reviewer,
and only while the current artifacts, package bindings and rule hashes still
match exactly.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import stage_context
from .artifacts import require_file
from .config import load_config

VERSION = "HISTORICAL_REVIEW_V1"
KIND = "historical_factual_semantic_review"
REVIEW_PROMPT_VERSION = "HISTORICAL_REVIEW_PROMPT_V1"
REVIEW_CHECKS = (
    "source_fidelity",
    "edit_semantics",
    "packaging_meaning",
    "metadata_factual",
)


class HistoricalReviewError(RuntimeError):
    """A historical review receipt is absent, incomplete, stale, or unapproved."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _read_manifest(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        data = json.loads(require_file(path).read_text(encoding="utf-8"))
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise HistoricalReviewError(f"manifest is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise HistoricalReviewError("manifest root must be an object")
    return data


def _outputs(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    outputs = data.get("outputs") or {}
    longform = outputs.get("longform") or {}
    short = outputs.get("short") or {}
    thumbnail = outputs.get("thumbnail") or {}
    if not all(isinstance(value, dict) and value for value in (longform, short, thumbnail)):
        raise HistoricalReviewError("historical package requires long-form, Short and thumbnail outputs")
    return longform, short, thumbnail


def _reviewer_model() -> str:
    model = str(load_config().require("analysis.model"))
    if not model.startswith("deepseek-"):
        raise HistoricalReviewError(
            f"historical review requires a configured DeepSeek reviewer, got {model or 'unrecorded'}"
        )
    return model


def _current_file_hash(path: Path) -> str:
    path = Path(path)
    try:
        handle = require_file(path).open("rb")
    except (OSError, RuntimeError) as exc:
        raise HistoricalReviewError(str(exc)) from exc
    digest = hashlib.sha256()
    try:
        with handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise HistoricalReviewError(f"artifact is not readable: {path}") from exc
    return digest.hexdigest()


def _artifact_hashes(data: dict[str, Any]) -> dict[str, Any]:
    longform, short, thumbnail = _outputs(data)
    artifacts = ((data.get("integrity") or {}).get("artifacts") or {})
    records: dict[str, Any] = {}

    for label, output in (("longform", longform), ("short", short)):
        record = artifacts.get(label) or {}
        path = Path(str(output.get("file_path") or ""))
        if str(path.resolve()) != str(record.get("path") or ""):
            raise HistoricalReviewError(f"{label} path does not match manifest integrity record")
        actual = _current_file_hash(path)
        if actual != record.get("sha256"):
            raise HistoricalReviewError(f"{label} hash changed after manifest stamp")
        records[label] = {"path": str(path.resolve()), "sha256": actual}

    thumb_records = artifacts.get("thumbnails") or {}
    records["thumbnails"] = {}
    for label, path in (thumbnail.get("candidates") or {}).items():
        path = Path(path)
        record = thumb_records.get(label) or {}
        if str(path.resolve()) != str(record.get("path") or ""):
            raise HistoricalReviewError(f"thumbnail {label} path does not match integrity record")
        actual = _current_file_hash(path)
        if actual != record.get("sha256"):
            raise HistoricalReviewError(f"thumbnail {label} hash changed after manifest stamp")
        records["thumbnails"][str(label)] = {"path": str(path.resolve()), "sha256": actual}

    vertical = short.get("vertical_thumbnail") or {}
    if vertical.get("file_path"):
        path = Path(str(vertical["file_path"]))
        actual = _current_file_hash(path)
        if vertical.get("sha256") != actual:
            raise HistoricalReviewError("Short vertical thumbnail hash changed")
        records["vertical_thumbnail"] = {"path": str(path.resolve()), "sha256": actual}
    return records


def _metadata(data: dict[str, Any]) -> dict[str, Any]:
    longform, short, _thumbnail = _outputs(data)
    return {
        "source": data.get("source"),
        "case": data.get("case"),
        "scores": data.get("scores"),
        "total_score": data.get("total_score"),
        "longform": {
            "clip_id": longform.get("clip_id"),
            "title": longform.get("title"),
            "description": longform.get("description"),
            "duration_s": longform.get("duration_s"),
        },
        "short": {
            "clip_id": short.get("clip_id"),
            "source_case_key": short.get("source_case_key"),
            "title": short.get("title"),
            "description": short.get("description"),
            "duration_s": short.get("duration_s"),
        },
    }


def _source_bindings(data: dict[str, Any]) -> dict[str, Any]:
    _longform, short, _thumbnail = _outputs(data)
    short_editor = data.get("short_editor") or {}
    packaging = data.get("packaging") or {}
    producer = packaging.get("producer_brain") or {}
    return {
        "source": data.get("source"),
        "case": data.get("case"),
        "producer_case_source": producer.get("case_source"),
        "short_audio": short_editor.get("silence_evidence"),
        "producer_brain_source": short_editor.get("producer_brain_source"),
        "producer_alignment": short_editor.get("producer_alignment"),
        "source_segments": short_editor.get("source_segments"),
        "edit_plan": short.get("edit_plan"),
    }


def _original_provenance(data: dict[str, Any]) -> dict[str, Any]:
    _longform, _short, thumbnail = _outputs(data)
    models = data.get("models") or {}
    calls = []
    for event in ((data.get("usage") or {}).get("model_calls") or []):
        if not isinstance(event, dict):
            continue
        calls.append({
            "label": event.get("label"),
            "model": event.get("model"),
            "prompt_version": event.get("prompt_version"),
            "input_sha256": event.get("input_sha256"),
            "request_sha256": event.get("request_sha256"),
            "stage_context": event.get("stage_context"),
        })
    return {
        "analysis_model": models.get("analysis_model"),
        "prompt_versions": models.get("prompt_versions") or {},
        "thumbnail": {
            "mode": thumbnail.get("mode"),
            "model": thumbnail.get("model"),
        },
        "model_calls": calls,
    }


def _binding_hashes(data: dict[str, Any], context: stage_context.StageContext) -> dict[str, Any]:
    _longform, short, _thumbnail = _outputs(data)
    return {
        "source_sha256": _canonical_hash(data.get("source")),
        "case_sha256": _canonical_hash(data.get("case")),
        "metadata_sha256": _canonical_hash(_metadata(data)),
        "packaging_sha256": _canonical_hash(data.get("packaging")),
        "edit_plan_sha256": _canonical_hash(short.get("edit_plan")),
        "source_bindings_sha256": _canonical_hash(_source_bindings(data)),
        "artifact_sha256": _artifact_hashes(data),
        "rule_hashes": context.provenance(),
    }


def _review_input(
    data: dict[str, Any], context: stage_context.StageContext,
) -> dict[str, Any]:
    _longform, short, _thumbnail = _outputs(data)
    return {
        "version": VERSION,
        "scope": KIND,
        "original_provenance": _original_provenance(data),
        "source": data.get("source"),
        "case": data.get("case"),
        "metadata": _metadata(data),
        "packaging": data.get("packaging"),
        "edit_plan": short.get("edit_plan"),
        "source_bindings": _source_bindings(data),
        "artifacts": _artifact_hashes(data),
        "rule_hashes": context.provenance(),
    }


def review_input(manifest_path: Path) -> dict[str, Any]:
    """Return the exact material a current historical reviewer must inspect."""
    data = _read_manifest(Path(manifest_path))
    return _review_input(data, stage_context.load_context())


def review_input_sha256(manifest_path: Path) -> str:
    """Return the digest the review document must carry in `input_sha256`."""
    return _canonical_hash(review_input(manifest_path))


def _require_approved_review(review: Any, expected_input_sha256: str) -> None:
    if not isinstance(review, dict):
        raise HistoricalReviewError("historical review is missing or not an object")
    status = str(review.get("status") or "").strip().lower()
    if status != "approved":
        raise HistoricalReviewError(
            f"historical review is {status or 'missing'}, not approved"
        )
    if review.get("provider") != "deepseek":
        raise HistoricalReviewError("historical review provider is not DeepSeek")
    want_model = _reviewer_model()
    if review.get("model") != want_model:
        raise HistoricalReviewError(
            f"historical review used {review.get('model') or 'no recorded model'}, "
            f"not the configured {want_model}"
        )
    if review.get("prompt_version") != REVIEW_PROMPT_VERSION:
        raise HistoricalReviewError(
            f"historical review prompt is {review.get('prompt_version') or 'missing'}, "
            f"not the current {REVIEW_PROMPT_VERSION}"
        )
    if not str(review.get("reviewed_at") or "").strip():
        raise HistoricalReviewError("historical review is missing its review time")
    if review.get("input_sha256") != expected_input_sha256:
        raise HistoricalReviewError(
            "historical review input hash does not match current assets and rules"
        )
    checks = review.get("checks")
    if not isinstance(checks, dict):
        raise HistoricalReviewError("historical review checks are missing")
    failed = [key for key in REVIEW_CHECKS if checks.get(key) is not True]
    if failed:
        raise HistoricalReviewError(
            "historical review did not pass: " + ", ".join(failed)
        )


def create_receipt(
    manifest_path: Path, review: dict[str, Any], *, created_at: str | None = None,
) -> dict[str, Any]:
    """Create a receipt from an explicit approved review of exact current files."""
    data = _read_manifest(Path(manifest_path))
    context = stage_context.load_context()
    review_doc = copy.deepcopy(review)
    expected_input_sha256 = _canonical_hash(_review_input(data, context))
    _require_approved_review(review_doc, expected_input_sha256)
    body = {
        "version": VERSION,
        "kind": KIND,
        "human_editorial_approval": False,
        "status": "approved",
        "review": review_doc,
        "original_provenance": _original_provenance(data),
        "bindings": _binding_hashes(data, context),
        "created_at": created_at or _now(),
    }
    body["receipt_sha256"] = _canonical_hash(body)
    return body


def require_receipt(
    manifest_path: Path, receipt: dict[str, Any], *, data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refuse unless a receipt is intact, current, approved and exactly bound."""
    if not isinstance(receipt, dict):
        raise HistoricalReviewError("historical review receipt is missing or not an object")
    if receipt.get("version") != VERSION or receipt.get("kind") != KIND:
        raise HistoricalReviewError("historical review receipt has the wrong kind or version")
    if receipt.get("human_editorial_approval") is not False:
        raise HistoricalReviewError("historical review receipt must not claim human editorial approval")
    if receipt.get("status") != "approved":
        raise HistoricalReviewError("historical review receipt is not approved")
    signature = receipt.get("receipt_sha256")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if not signature or _canonical_hash(body) != signature:
        raise HistoricalReviewError("historical review receipt was altered")

    manifest_path = Path(manifest_path)
    current = data if data is not None else _read_manifest(manifest_path)
    context = stage_context.load_context()
    expected_input_sha256 = _canonical_hash(_review_input(current, context))
    _require_approved_review(receipt.get("review"), expected_input_sha256)
    if receipt.get("original_provenance") != _original_provenance(current):
        raise HistoricalReviewError("historical review original model/prompt provenance changed")
    if receipt.get("bindings") != _binding_hashes(current, context):
        raise HistoricalReviewError("historical review bindings changed")
    return {
        "ok": True,
        "version": VERSION,
        "reviewer": receipt["review"]["model"],
        "reviewed_at": receipt["review"]["reviewed_at"],
        "receipt_sha256": signature,
    }
