"""Immutable review-bundle checks used before approval and publication."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import require_file, require_thumbnail
from .metadata import has_case_specific_tag

# 2026-09-19 (Nathan: "make the thumbnail ... audit the court does them and
# then a/b test what it says on the thumbnail"): a fourth thumbnail mode that
# holds ONE picture and ONE video title constant and varies only the words.
# The image and the title are the control, so the three pairs legitimately
# share a single title — and only this explicitly verified mode, whose
# wording was built into real files and re-checked, may do that.
THUMBNAIL_TEXT_ONLY_MODE = "thumbnail_text_only"


class ReadinessError(RuntimeError):
    """A review bundle is incomplete, stale, invalid, or unapproved."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_manual_release(packet_path: Path) -> dict[str, Any]:
    """Check already-selected files for a manual Studio release, without production.

    A release packet records the operator's existing selection and metadata.
    This read-only check neither performs editorial review nor grants approval,
    and deliberately has no dependency on a Short or unselected test arms.
    """
    packet_path = Path(packet_path).resolve()
    data = _read(packet_path)
    for key in ("case_key", "title", "description"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ReadinessError(f"release packet needs {key}")
    if len(data["title"]) > 100 or len(data["description"]) > 5000:
        raise ReadinessError("release metadata exceeds YouTube text limits")
    if data.get("audience") != "not_made_for_kids":
        raise ReadinessError("release audience must be not_made_for_kids")
    assets: dict[str, Any] = {}
    for kind in ("video", "thumbnail"):
        asset = data.get(kind)
        if not isinstance(asset, dict) or not asset.get("path") or not asset.get("sha256"):
            raise ReadinessError(f"release packet needs exact {kind} path and hash")
        path = Path(asset["path"])
        if not path.is_absolute():
            path = packet_path.parent / path
        path = path.resolve()
        if sha256_file(path) != asset["sha256"]:
            raise ReadinessError(f"selected {kind} hash changed")
        assets[kind] = {"path": str(path), "sha256": asset["sha256"]}
    if data["thumbnail"].get("status") != "accepted":
        raise ReadinessError("release packet does not identify an accepted thumbnail")
    try:
        require_thumbnail(Path(assets["thumbnail"]["path"]))
    except RuntimeError as exc:
        raise ReadinessError(str(exc)) from exc
    assets["video"]["probe"] = probe_video(Path(assets["video"]["path"]))
    return {
        "status": "local_files_verified", "case_key": data["case_key"],
        **assets, "title": data["title"], "description": data["description"],
        "tags": data.get("tags") or [], "audience": data["audience"],
        "schedule": data.get("schedule"), "recorded_platform_id": data.get("youtube_video_id"),
        "scope": "manual Studio release of selected long-form and thumbnail only",
        "note": "File integrity and media probe only. Existing editorial review and user release authorization are still required. No model calls, rendering, approval, upload or scheduling performed.",
    }


def _configured_model(key: str) -> str:
    """The model this project is actually configured to use.

    These checks used to compare against the literal string "gpt-5.6-sol". That
    named a brain this PC can no longer reach (2026-09-16: `codex login` answers
    "ChatGPT login is disabled", and the configured provider rejects the model
    name with "The supported API model names are deepseek-flash,
    deepseek-v4-pro"), so every bundle was unready no matter what it contained.

    The rule these checks enforce is not "the string Sol" — it is "the artifact
    was produced by the model this project is configured to use, and no stage
    quietly substituted another one". A manifest naming anything else still
    refuses, which is the part that matters.
    """
    from .config import load_config

    return str(load_config().require(key))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with require_file(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, RuntimeError) as exc:
        raise ReadinessError(str(exc)) from exc
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(require_file(path).read_text(encoding="utf-8"))
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"manifest is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ReadinessError("manifest root must be an object")
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".",
        suffix=".tmp", delete=False,
    )
    tmp = Path(handle.name)
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _outputs(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    outputs = data.get("outputs") or {}
    longform = outputs.get("longform") or {}
    short = outputs.get("short") or {}
    thumbnail = outputs.get("thumbnail") or {}
    if not all(isinstance(value, dict) and value for value in (longform, short, thumbnail)):
        raise ReadinessError("bundle requires long-form, Short, and thumbnail outputs")
    return longform, short, thumbnail


def stamp_manifest(manifest_path: Path) -> dict[str, Any]:
    """Record hashes for exact artifacts without approving the bundle."""
    manifest_path = Path(manifest_path)
    data = _read(manifest_path)
    longform, short, thumbnail = _outputs(data)
    candidates = thumbnail.get("candidates") or {}
    integrity = {
        "algorithm": "sha256",
        "artifacts": {
            "longform": {"path": str(Path(longform["file_path"]).resolve()),
                         "sha256": sha256_file(Path(longform["file_path"]))},
            "short": {"path": str(Path(short["file_path"]).resolve()),
                      "sha256": sha256_file(Path(short["file_path"]))},
            "thumbnails": {
                str(label): {"path": str(Path(path).resolve()), "sha256": sha256_file(Path(path))}
                for label, path in sorted(candidates.items())
            },
        },
        "stamped_at": _now(),
    }
    data["integrity"] = integrity
    _write(manifest_path, data)
    return data


def probe_video(path: Path) -> dict[str, Any]:
    try:
        path = require_file(path)
    except RuntimeError as exc:
        raise ReadinessError(str(exc)) from exc
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,sample_rate",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReadinessError(f"video probe could not run for {path}: {exc}") from exc
    if proc.returncode != 0:
        raise ReadinessError(f"video is not decodable by ffprobe: {path}")
    try:
        raw = json.loads(proc.stdout)
        streams = raw.get("streams") or []
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        audio = next(stream for stream in streams if stream.get("codec_type") == "audio")
        duration = float((raw.get("format") or {}).get("duration") or 0)
    except (ValueError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        raise ReadinessError(f"video is not decodable with video and audio streams: {path}") from exc
    if duration <= 0:
        raise ReadinessError(f"video has no positive duration: {path}")
    return {"duration_s": duration, "video": video, "audio": audio}


def _case_key(longform: dict[str, Any], short: dict[str, Any]) -> str:
    long_id = str(longform.get("clip_id") or "")
    short_id = str(short.get("clip_id") or "")
    if not long_id.endswith(":longform") or not short_id.endswith(":short"):
        raise ReadinessError("clip ids must end in :longform and :short")
    case_key = long_id.removesuffix(":longform")
    if short_id.removesuffix(":short") != case_key:
        raise ReadinessError("long-form and Short clip ids belong to different cases")
    if str(short.get("source_case_key") or "") != case_key:
        raise ReadinessError("Short source_case_key does not match long-form case")
    return case_key


def _require_qc(data: dict[str, Any], *, allow_historical_models: bool = False) -> None:
    blockers = (data.get("editorial_review") or {}).get("blockers") or []
    if blockers:
        raise ReadinessError("editorial review has unresolved blockers: " + "; ".join(map(str, blockers)))
    want_model = _configured_model("analysis.model")
    got_model = str((data.get("models") or {}).get("analysis_model") or "")
    if got_model != want_model and not allow_historical_models:
        raise ReadinessError(
            f"production reasoning model is {got_model or 'unrecorded'}, "
            f"but this project is configured for {want_model}"
        )
    if not bool((data.get("safety") or {}).get("safety_pass")):
        raise ReadinessError("safety gate did not pass")
    if not bool((data.get("packaging") or {}).get("hook_verified")):
        raise ReadinessError("packaging hook is not transcript-verified")
    short_editor = data.get("short_editor") or {}
    if not bool(short_editor.get("ok")):
        raise ReadinessError("Short editor did not pass")
    producer_source = short_editor.get("producer_brain_source")
    if producer_source:
        from .producer_brain import PROMPT_NAME, PROMPT_VERSION
        from .shorts_editor import producer_alignment

        versions = (data.get("models") or {}).get("prompt_versions") or {}
        if versions.get(PROMPT_NAME) != PROMPT_VERSION:
            raise ReadinessError("bundle did not use the current Producer Brain prompt")
        alignment = short_editor.get("producer_alignment") or {}
        source_segments = short_editor.get("source_segments") or []
        if not source_segments:
            raise ReadinessError("rendered Short is missing its source edit timeline")
        words = None
        producer = (data.get("packaging") or {}).get("producer_brain") or {}
        evidence = producer.get("case_source") or {}
        if evidence:
            from .transcribe import Transcript

            transcript_path = Path(str(evidence.get("transcript_path") or ""))
            if not transcript_path.is_absolute():
                transcript_path = Path(__file__).resolve().parents[2] / transcript_path
            if sha256_file(transcript_path) != evidence.get("transcript_sha256"):
                raise ReadinessError("Producer transcript hash changed")
            transcript = Transcript.from_json(transcript_path.read_text(encoding="utf-8"))
            if transcript.video_id != (data.get("source") or {}).get("video_id"):
                raise ReadinessError("Producer transcript belongs to a different source")
            if producer_source.get("sequence") != (producer.get("short_plan") or {}).get("sequence"):
                raise ReadinessError("Short source sequence differs from the Producer plan")
            words = transcript.words
        recomputed = producer_alignment(source_segments, producer_source, words)
        if not bool(alignment.get("ok")) or not recomputed["ok"]:
            raise ReadinessError("rendered Short does not execute the approved Producer Short plan")
        if words is not None:
            from . import render, shorts_editor

            audio = short_editor.get("silence_evidence") or {}
            source_path = Path(str(audio.get("source_path") or ""))
            if sha256_file(source_path) != audio.get("source_sha256"):
                raise ReadinessError("Short audio source hash changed")
            silences = render.detect_silences(source_path, noise_db=-30.0, min_silence_s=0.30)
            checks = shorts_editor.producer_silence_checks(
                [render.Segment(float(a), float(b)) for a, b in source_segments],
                producer_source, silences, float(audio.get("offset_s", 0.0)),
            )
            if any(not check["ok"] for check in checks):
                raise ReadinessError("Short cut removes unverified audio from a transcript gap")
    render_qc = short_editor.get("render_qc") or []
    if not render_qc or any(not bool(check.get("ok")) for check in render_qc):
        raise ReadinessError("Short render QC did not pass")
    visual_qc = short_editor.get("visual_qc") or {}
    if not bool(visual_qc.get("ok")):
        raise ReadinessError("Short visual QC did not pass")
    if any(not bool(check.get("ok")) for check in visual_qc.get("checks") or []):
        raise ReadinessError("Short visual QC contains a failed check")


def _thumbnail_mode(data: dict[str, Any]) -> str:
    """`outputs.thumbnail.mode` without demanding a complete output block."""
    thumbnail = (data.get("outputs") or {}).get("thumbnail") or {}
    if not isinstance(thumbnail, dict):
        return ""
    return str(thumbnail.get("mode") or "")


def _text_only_receipt_path(thumbnail: dict[str, Any], manifest_dir: Path | None) -> Path:
    """Where the built text-only experiment receipt lives, per the manifest.

    The manifest records a PATH, not the receipt body: readiness re-opens the
    actual JSON and the actual images rather than trusting a copy embedded in
    the bundle.
    """
    raw: Any = None
    for key in ("receipt_path", "receipt", "manifest_path", "manifest", "experiment_receipt"):
        value = thumbnail.get(key)
        if isinstance(value, dict):
            value = value.get("path")
        if value:
            raw = value
            break
    if not raw:
        raise ReadinessError(
            "thumbnail_text_only mode requires the manifest to record its experiment "
            "receipt path (thumbnail.receipt_path)"
        )
    path = Path(str(raw))
    if not path.is_absolute() and manifest_dir is not None:
        beside = Path(manifest_dir) / path
        if beside.is_file():
            return beside
    return path


def _read_text_only_receipt(
    thumbnail: dict[str, Any], manifest_dir: Path | None,
) -> tuple[Path, dict[str, Any]]:
    from .thumbnail_text_test import RECEIPT_TYPE

    path = _text_only_receipt_path(thumbnail, manifest_dir)
    if not path.is_file():
        raise ReadinessError(f"text-only experiment receipt is missing: {path}")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"text-only experiment receipt is not readable JSON: {path}") from exc
    if not isinstance(receipt, dict):
        raise ReadinessError(f"text-only experiment receipt must be a JSON object: {path}")
    if receipt.get("receipt_type") != RECEIPT_TYPE:
        raise ReadinessError(
            f"thumbnail receipt {path} is {receipt.get('receipt_type')!r}, not {RECEIPT_TYPE!r}"
        )
    return path, receipt


def _text_only_model(thumbnail: dict[str, Any]) -> str:
    for key in ("model", "direction_model", "orchestration_model"):
        value = thumbnail.get(key)
        if value:
            return str(value)
    return ""


def _problem_summary(problems: Any) -> str:
    parts: list[str] = []
    for row in list(problems or [])[:5]:
        if isinstance(row, dict):
            parts.append(f"{row.get('code')}: {row.get('detail')}")
        else:
            parts.append(str(row))
    return "; ".join(parts)


def _pair_yellow(pair: dict[str, Any]) -> str:
    """The substring the pair renders in the house key-phrase yellow."""
    for key in ("thumbnail_yellow", "thumbnail_emphasis", "emphasis", "yellow"):
        value = pair.get(key)
        if value:
            return str(value).strip()
    return ""


def _require_text_only_candidates(
    thumbnail: dict[str, Any], *,
    allow_historical_models: bool = False,
    manifest_dir: Path | None = None,
) -> dict[str, str]:
    """One shared image, three wordings: verify the block and the printed files.

    The heavy re-validation of the experiment itself (base, font, editable
    layers, fresh re-render of each headline) runs in
    `_require_packaging_pairs`, which also owns the binding between the
    receipt's words and the packaging pairs. Here readiness proves the block
    is complete, names this project's configured model, has a real receipt,
    and points at the exact three images that receipt rendered.
    """
    if thumbnail.get("complete") is not True:
        raise ReadinessError("thumbnail output is not a complete text-only A/B/C session")
    want_model = _configured_model("packaging.thumbnail.direct.model")
    got_model = _text_only_model(thumbnail)
    if got_model != want_model and not allow_historical_models:
        raise ReadinessError(
            f"thumbnail session was orchestrated by {got_model or 'an unrecorded model'}, "
            f"but this project is configured for {want_model}"
        )
    _receipt_file, receipt = _read_text_only_receipt(thumbnail, manifest_dir)
    candidates = thumbnail.get("candidates") or {}
    if set(candidates) != {"A", "B", "C"}:
        raise ReadinessError("text-only thumbnail bundle requires A, B and C candidates")
    variants: dict[str, dict[str, Any]] = {
        str(record.get("label")): record
        for record in (receipt.get("variants") or [])
        if isinstance(record, dict)
    }
    if set(variants) != {"A", "B", "C"}:
        raise ReadinessError("the experiment receipt does not carry exactly A, B and C variants")
    resolved: dict[str, str] = {}
    for label in "ABC":
        try:
            path = require_thumbnail(Path(candidates[label])).resolve()
        except RuntimeError as exc:
            raise ReadinessError(str(exc)) from exc
        recorded = str(variants[label].get("png_path") or "")
        if not recorded or Path(recorded).resolve() != path:
            raise ReadinessError(
                f"thumbnail candidate {label} is {path}, but the experiment receipt "
                f"rendered {recorded or 'no recorded path'} — the manifest is not "
                "pointing at the images that were tested"
            )
        if variants[label].get("png_sha256") != sha256_file(path):
            raise ReadinessError(
                f"thumbnail candidate {label} is not the file the experiment receipt recorded"
            )
        resolved[label] = str(path)
    if len(set(resolved.values())) != 3:
        raise ReadinessError("text-only A/B/C candidates must be three different images")
    return resolved


def _require_candidates(
    thumbnail: dict[str, Any], *, allow_historical_models: bool = False,
    manifest_dir: Path | None = None,
) -> dict[str, str]:
    mode = str(thumbnail.get("mode") or "")
    if mode == "direct_gen":
        if thumbnail.get("complete") is not True:
            raise ReadinessError("thumbnail output is not a complete direct A/B/C session")
        want_model = _configured_model("packaging.thumbnail.direct.model")
        got_model = str(thumbnail.get("model") or "")
        if got_model != want_model and not allow_historical_models:
            raise ReadinessError(
                f"thumbnail session was orchestrated by {got_model or 'an unrecorded model'}, "
                f"but this project is configured for {want_model}"
            )
        candidates = thumbnail.get("candidates") or {}
        if set(candidates) != {"A", "B", "C"}:
            raise ReadinessError("direct thumbnail bundle requires A, B and C candidates")
        resolved: dict[str, str] = {}
        for label in "ABC":
            try:
                path = require_thumbnail(Path(candidates[label])).resolve()
            except RuntimeError as exc:
                raise ReadinessError(str(exc)) from exc
            resolved[label] = str(path)
        return resolved

    if mode == THUMBNAIL_TEXT_ONLY_MODE:
        return _require_text_only_candidates(
            thumbnail, allow_historical_models=allow_historical_models,
            manifest_dir=manifest_dir,
        )

    # Local compositor (`packaging.thumbnail.mode: legacy`). It produces ONE
    # finished image from the video itself and no A/B/C generated candidates —
    # the three concepts exist only as text in packaging.packaging_pairs. That
    # is a smaller deliverable than the direct session, so it is reported under
    # its own label rather than passed off as A/B/C: validate_candidate_bundle
    # returns it with a note, and approve_manifest refuses to bind approval to
    # it because there is no concept to select.
    path = require_thumbnail(Path(str(thumbnail.get("file_path") or "")))
    return {"L": str(path.resolve())}


def _review_package_for_copy(
    packaging: dict[str, Any], *, allow_historical_models: bool = False,
) -> dict[str, Any]:
    """The package body the meaning review is hashed against.

    The historical receipt is the current semantic review. Keep the recorded
    copy review and all of its content/rendered-byte checks, but do not require
    its historical model name to equal today's.
    """
    if not allow_historical_models:
        return packaging
    package_for_copy = copy.deepcopy(packaging)
    report = package_for_copy.get("thumbnail_copy_review") or {}
    if report:
        from .config import load_config

        report["model"] = str(load_config().require("packaging.thumbnail.direct.model"))
    return package_for_copy


def _require_semantic_copy_review(
    packaging: dict[str, Any], *, allow_historical_models: bool = False,
) -> None:
    """The mechanical experiment receipt is not the semantic review.

    `thumbnail_text_test` records that source evidence was SUPPLIED, explicitly
    never that it was verified. The words still have to clear the current
    meaning/hook review before the bundle can move.
    """
    from .thumbnail_copy import CopyReviewError, require_review

    if not isinstance(packaging.get("thumbnail_copy_review"), dict) or not packaging.get("thumbnail_copy_review"):
        raise ReadinessError(
            "thumbnail_text_only requires the current semantic copy review "
            "(packaging.thumbnail_copy_review): the word-experiment receipt only "
            "records that source evidence was supplied, never that it was verified"
        )
    try:
        require_review(
            _review_package_for_copy(packaging, allow_historical_models=allow_historical_models)
        )
    except CopyReviewError as exc:
        raise ReadinessError(str(exc)) from exc


def _require_text_only_experiment(
    data: dict[str, Any], packaging: dict[str, Any], *,
    manifest_dir: Path | None = None,
) -> dict[str, Any]:
    """Re-open the Audit-the-Court wording experiment and bind it to the packaging."""
    from .thumbnail_text_test import validate_experiment

    thumbnail = _outputs(data)[2]
    receipt_path, receipt = _read_text_only_receipt(thumbnail, manifest_dir)
    experiment = packaging.get("thumbnail_experiment")
    if not isinstance(experiment, dict) or not experiment:
        raise ReadinessError(
            "thumbnail_text_only requires packaging.thumbnail_experiment to name the "
            "fixed title and the shared base image"
        )
    if str(experiment.get("type") or "") != THUMBNAIL_TEXT_ONLY_MODE:
        raise ReadinessError(
            "packaging.thumbnail_experiment.type is "
            f"{experiment.get('type')!r}, not {THUMBNAIL_TEXT_ONLY_MODE!r}"
        )
    fixed_title = " ".join(str(experiment.get("fixed_title") or "").split())
    if not fixed_title:
        raise ReadinessError(
            "packaging.thumbnail_experiment is missing the fixed video title the test held constant"
        )
    if fixed_title.lower() != " ".join(str(receipt.get("fixed_title") or "").split()).lower():
        raise ReadinessError(
            f"the experiment receipt was built with title {receipt.get('fixed_title')!r}, "
            f"not the recorded fixed title {experiment.get('fixed_title')!r}"
        )
    base_sha = str(experiment.get("base_sha256") or "").strip().lower()
    if len(base_sha) != 64 or any(char not in "0123456789abcdef" for char in base_sha):
        raise ReadinessError(
            "packaging.thumbnail_experiment.base_sha256 must be the sha256 of the shared base image"
        )
    receipt_base = receipt.get("base") if isinstance(receipt.get("base"), dict) else {}
    if str(receipt_base.get("sha256") or "").strip().lower() != base_sha:
        raise ReadinessError(
            "the experiment receipt was built on a different base image than "
            "packaging.thumbnail_experiment records (base_sha256 does not match)"
        )
    report = validate_experiment(receipt_path)
    if not isinstance(report, dict):
        raise ReadinessError("text-only thumbnail experiment validation returned no verdict")
    problems = report.get("errors") or report.get("failures") or []
    if report.get("ok") is not True or problems:
        raise ReadinessError(
            "text-only thumbnail experiment failed re-validation against its own files: "
            + (_problem_summary(problems) or "no detail")
        )
    return receipt


def _require_text_only_pairs(
    data: dict[str, Any], packaging: dict[str, Any], pairs: dict[str, dict[str, Any]],
    titles: list[str], *, allow_historical_models: bool = False,
    manifest_dir: Path | None = None,
) -> None:
    """Bind the packaging pairs to the wording that was actually rendered.

    Nathan, 2026-09-19: hold the picture and the video title, vary the words.
    The three pairs therefore share the one fixed title, and the words they
    ship must be the words re-verified in the tested images — not a parallel
    description of them.
    """
    from .thumbnail_copy import copy_words

    _require_semantic_copy_review(packaging, allow_historical_models=allow_historical_models)
    receipt = _require_text_only_experiment(data, packaging, manifest_dir=manifest_dir)
    experiment = packaging["thumbnail_experiment"]
    fixed_title = " ".join(str(experiment.get("fixed_title") or "").split()).lower()
    variants: dict[str, dict[str, Any]] = {
        str(record.get("label")): record
        for record in (receipt.get("variants") or [])
        if isinstance(record, dict)
    }
    for index, label in enumerate("ABC"):
        if titles[index] != fixed_title:
            raise ReadinessError(
                f"packaging pair {label} title {pairs[label].get('title')!r} is not the one "
                f"fixed title of the text-only experiment ({experiment.get('fixed_title')!r})"
            )
        pair_text = str(pairs[label].get("thumbnail_text") or "")
        delivered = str(variants.get(label, {}).get("text") or "")
        if not copy_words(pair_text):
            raise ReadinessError(f"packaging pair {label} is missing its thumbnail wording")
        if copy_words(pair_text) != copy_words(delivered):
            raise ReadinessError(
                f"packaging pair {label} wording {pair_text!r} is not the wording rendered "
                f"and re-verified in the tested image ({delivered!r})"
            )
        yellow = _pair_yellow(pairs[label])
        if not yellow:
            raise ReadinessError(
                f"packaging pair {label} is missing the yellow key-phrase substring it renders"
            )
        if yellow not in pair_text:
            if yellow.lower() in pair_text.lower():
                raise ReadinessError(
                    f"packaging pair {label} yellow {yellow!r} matches only case-insensitively; "
                    "pass the exact substring that is rendered"
                )
            raise ReadinessError(
                f"packaging pair {label} yellow {yellow!r} is not part of its thumbnail wording"
            )
        rendered_yellow = " ".join(str(variants.get(label, {}).get("emphasis") or "").split())
        if " ".join(yellow.split()) != rendered_yellow:
            raise ReadinessError(
                f"packaging pair {label} yellow {yellow!r} is not the yellow run rendered in the "
                f"tested image ({rendered_yellow!r})"
            )


def _require_packaging_pairs(
    data: dict[str, Any], *, allow_historical_models: bool = False,
    manifest_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    packaging = data.get("packaging") or {}
    thumbnail_mode = _thumbnail_mode(data)
    # The text-only route requires the semantic review unconditionally (below),
    # so it does not depend on a Producer Brain plan being present; packages
    # that do carry one keep the existing scoped behaviour.
    if packaging.get("producer_brain") and thumbnail_mode != THUMBNAIL_TEXT_ONLY_MODE:
        from .thumbnail_copy import CopyReviewError, require_rendered_copy
        thumbnail = _outputs(data)[2]
        package_for_copy = _review_package_for_copy(
            packaging, allow_historical_models=allow_historical_models,
        )
        if str(thumbnail.get("mode") or "") == "direct_gen":
            try:
                require_rendered_copy(package_for_copy, thumbnail)
            except CopyReviewError as exc:
                raise ReadinessError(str(exc)) from exc
        else:
            # Bind the reviewed words to image bytes only where generated images
            # exist. The legacy compositor writes ONE image and no per-concept
            # candidates, so there are no A/B/C bytes to bind; the three pairs
            # are still required in full below, and validate_candidate_bundle
            # reports the missing generated set as a note instead of passing it
            # off as a complete direct session. The review itself is NOT
            # optional here (2026-09-19, Nathan: "the words in the thumbnail
            # kinda suck you need to make a permament fix for that"): the
            # pipeline now runs it before the legacy compositor too, so an absent
            # or stale report is a live contradiction rather than a recorded gap.
            from .thumbnail_copy import CopyReviewError, require_review

            try:
                require_review(package_for_copy)
            except CopyReviewError as exc:
                raise ReadinessError(str(exc)) from exc
    rows = packaging.get("packaging_pairs") or []
    if not isinstance(rows, list) or len(rows) != 3:
        raise ReadinessError("packaging requires exactly three A/B/C title-thumbnail pairs")
    pairs = {str(row.get("label") or ""): row for row in rows if isinstance(row, dict)}
    if set(pairs) != {"A", "B", "C"}:
        raise ReadinessError("packaging requires exactly three A/B/C title-thumbnail pairs")
    titles = [" ".join(str(pairs[label].get("title") or "").lower().split()) for label in "ABC"]
    if any(not title for title in titles):
        raise ReadinessError("A/B/C titles must be present and genuinely distinct")
    if thumbnail_mode == THUMBNAIL_TEXT_ONLY_MODE:
        # Scoped override: the verified text-only experiment holds the video
        # title constant, so its three pairs carry ONE fixed title. Every other
        # mode still owes three genuinely distinct titles (below).
        _require_text_only_pairs(
            data, packaging, pairs, titles,
            allow_historical_models=allow_historical_models, manifest_dir=manifest_dir,
        )
    elif len(set(titles)) != 3:
        raise ReadinessError("A/B/C titles must be present and genuinely distinct")
    short_title = " ".join(str(packaging.get("short_title") or "").split())
    if not 50 <= len(short_title) <= 70:
        raise ReadinessError("Short title must be a complete 50-70 character title")
    if short_title.lower() in titles:
        raise ReadinessError("Short title cannot copy a long-form packaging title")
    for label in "ABC":
        reason = " ".join(str(pairs[label].get("reason") or "").lower().split())
        if not reason:
            raise ReadinessError(f"packaging pair {label} is missing its pairing reason")
        for other_label, other_title in zip("ABC", titles):
            if other_label != label and other_title in reason:
                raise ReadinessError(
                    f"packaging pair {label} reason names title {other_label} instead of its own title"
                )
    if not has_case_specific_tag(packaging.get("tags") or []):
        raise ReadinessError("packaging needs at least one supported case-specific tag")
    return pairs


def _verify_integrity(data: dict[str, Any]) -> None:
    longform, short, thumbnail = _outputs(data)
    artifacts = ((data.get("integrity") or {}).get("artifacts") or {})
    expected = {
        "longform": (Path(longform["file_path"]), artifacts.get("longform") or {}),
        "short": (Path(short["file_path"]), artifacts.get("short") or {}),
    }
    for label, (path, record) in expected.items():
        if str(path.resolve()) != str(record.get("path") or ""):
            raise ReadinessError(f"{label} path does not match manifest integrity record")
        if sha256_file(path) != record.get("sha256"):
            raise ReadinessError(f"{label} hash changed after manifest stamp")
    thumb_records = artifacts.get("thumbnails") or {}
    for label, path in (thumbnail.get("candidates") or {}).items():
        record = thumb_records.get(label) or {}
        if str(Path(path).resolve()) != str(record.get("path") or ""):
            raise ReadinessError(f"thumbnail {label} path does not match integrity record")
        if sha256_file(Path(path)) != record.get("sha256"):
            raise ReadinessError(f"thumbnail {label} hash changed after manifest stamp")


def _bundle_hash(data: dict[str, Any], selected_label: str) -> str:
    longform, short, _thumbnail = _outputs(data)
    artifacts = data["integrity"]["artifacts"]
    payload = {
        "source": data.get("source"),
        "case": data.get("case"),
        "longform": {"clip_id": longform.get("clip_id"), "sha256": artifacts["longform"]["sha256"]},
        "short": {"clip_id": short.get("clip_id"), "source_case_key": short.get("source_case_key"),
                  "sha256": artifacts["short"]["sha256"]},
        "thumbnail": {"label": selected_label,
                      "sha256": artifacts["thumbnails"][selected_label]["sha256"]},
        "packaging": data.get("packaging"),
        "short_editor": data.get("short_editor"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def approve_manifest(manifest_path: Path, selected_label: str, *, probe: bool = True) -> dict[str, Any]:
    """Select one of a complete A/B/C set and bind approval to exact bytes."""
    manifest_path = Path(manifest_path)
    data = stamp_manifest(manifest_path)
    longform, short, thumbnail = _outputs(data)
    _require_qc(data)
    candidates = _require_candidates(thumbnail, manifest_dir=manifest_path.parent)
    pairs = _require_packaging_pairs(data, manifest_dir=manifest_path.parent)
    selected_label = str(selected_label or "").upper()
    if set(candidates) != {"A", "B", "C"}:
        raise ReadinessError(
            "approval needs a complete direct A/B/C thumbnail set; this bundle has "
            + ", ".join(sorted(candidates))
            + " (legacy compositor output carries no selectable concepts)"
        )
    if selected_label not in candidates:
        raise ReadinessError("thumbnail selection must be A, B or C")
    if probe:
        probe_video(Path(longform["file_path"]))
        probe_video(Path(short["file_path"]))
    _verify_integrity(data)
    case_key = _case_key(longform, short)
    thumbnail["file_path"] = candidates[selected_label]
    thumbnail["selection"] = {"label": selected_label, "selected_at": _now()}
    thumbnail["status"] = "selected"
    data["packaging"]["selection"] = {"label": selected_label, "selected_at": _now()}
    longform["title"] = str(pairs[selected_label]["title"])
    bundle_hash = _bundle_hash(data, selected_label)
    data["status"] = "approved"
    data["review_required"] = False
    data["approval"] = {"case_key": case_key, "bundle_hash": bundle_hash, "approved_at": _now()}
    _write(manifest_path, data)
    return {"case_key": case_key, "bundle_hash": bundle_hash,
            "title": longform["title"],
            "thumbnail": candidates[selected_label], "manifest_path": str(manifest_path.resolve())}


def validate_candidate_bundle(
    manifest_path: Path, *, probe: bool = True,
    historical_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prove a rendered review candidate is complete without approving it."""
    manifest_path = Path(manifest_path)
    data = _read(manifest_path)
    allow_historical_models = historical_receipt is not None
    if allow_historical_models:
        from . import historical_review

        try:
            historical = historical_review.require_receipt(
                manifest_path, historical_receipt, data=data,
            )
        except historical_review.HistoricalReviewError as exc:
            raise ReadinessError(str(exc)) from exc
    longform, short, thumbnail = _outputs(data)
    _require_qc(data, allow_historical_models=allow_historical_models)
    candidates = _require_candidates(
        thumbnail, allow_historical_models=allow_historical_models,
        manifest_dir=manifest_path.parent,
    )
    _require_packaging_pairs(
        data, allow_historical_models=allow_historical_models,
        manifest_dir=manifest_path.parent,
    )
    _verify_integrity(data)
    _require_vertical_short_thumbnail(
        short, allow_historical_models=allow_historical_models,
    )
    if probe:
        probe_video(Path(longform["file_path"]))
        probe_video(Path(short["file_path"]))
    case_key = _case_key(longform, short)
    notes: list[str] = []
    if set(candidates) != {"A", "B", "C"}:
        notes.append(
            "thumbnail mode is legacy: one composited image was produced "
            f"({candidates.get('L', 'unknown')}); no A/B/C generated candidates exist"
        )
    if _thumbnail_mode(data) == THUMBNAIL_TEXT_ONLY_MODE:
        notes.append(
            "thumbnail experiment is wording-only against one shared base and one fixed "
            "video title; preparing the three images is not a live YouTube Studio A/B "
            "test, and no platform experiment state or result has been verified here"
        )
    if not ((data.get("packaging") or {}).get("thumbnail_copy_review")):
        notes.append(
            "no thumbnail meaning review (it is written by the direct A/B/C session); "
            "the three title-thumbnail pairs are transcript-checked but their wording "
            "was not reviewed by a model"
        )
    if allow_historical_models:
        notes.append(
            "historical model provenance is retained; candidate use is covered by "
            "an exact current-review receipt, not human editorial approval"
        )
    return {
        "ready": True,
        "case_key": case_key,
        "manifest_path": str(manifest_path.resolve()),
        "thumbnails": candidates,
        "notes": notes,
        **({"historical_review": historical} if allow_historical_models else {}),
    }


def _require_editorial_clearance(short: dict[str, Any]) -> None:
    """A rejected cut must not move toward publishing.

    2026-09-16: the Short rendered for `dAKO7myCd-g:8929` decodes, validates and
    passes `ready: true`, and Nathan rejected the cut. Technical validity and
    editorial approval are different facts, so the publishing path checks the
    editorial field the review workflow writes.
    """
    status = str((short or {}).get("editorial_status") or "").upper()
    if status in ("REJECTED", "NEEDS_USER_REEDIT"):
        note = (short or {}).get("editorial_note") or "no note recorded"
        raise ReadinessError(
            f"the Short cut is editorially {status} ({note}) — a file that decodes "
            "is not an approved edit")


def _require_vertical_short_thumbnail(
    short: dict[str, Any], *, allow_historical_models: bool = False,
) -> None:
    if not short.get("vertical_thumbnail_required"):
        return
    from PIL import Image
    vertical = short.get("vertical_thumbnail") or {}
    path = Path(vertical.get("file_path") or "")
    if not path.is_file():
        raise ReadinessError("Short package requires a separate 9:16 vertical thumbnail")
    require_thumbnail(path)
    with Image.open(path) as image:
        if image.size != (1080, 1920):
            raise ReadinessError(f"Short vertical thumbnail must decode at 1080x1920, got {image.size}")
    if vertical.get("sha256") != sha256_file(path):
        raise ReadinessError("Short vertical thumbnail hash changed")
    if vertical.get("short_sha256") != sha256_file(Path(short["file_path"])):
        raise ReadinessError("Short vertical thumbnail is not bound to the current Short")
    want_model = _configured_model("packaging.thumbnail.direct.model")
    if vertical.get("direction_model") != want_model and not allow_historical_models:
        raise ReadinessError(
            f"Short vertical thumbnail direction model is "
            f"{vertical.get('direction_model') or 'unrecorded'}, not the configured {want_model}"
        )
    review = vertical.get("visual_review") or {}
    if review.get("full_size") != "passed" or review.get("phone_size") != "passed":
        raise ReadinessError("Short vertical thumbnail needs full-size and phone-size visual review")


def validate_publish_bundle(
    longform: dict[str, Any], short: dict[str, Any], *, store: Any,
) -> dict[str, Any]:
    """Fail before publisher construction unless exact approved bundle is ready."""
    _require_editorial_clearance(short)
    longform = dict(longform or {})
    short = dict(short or {})
    if not longform or not short:
        raise ReadinessError("publication requires both long-form and Short")
    manifest_path = Path(longform["file_path"]).resolve().parent / "manifest.json"
    data = _read(manifest_path)
    saved_longform, saved_short, thumbnail = _outputs(data)
    if Path(saved_longform["file_path"]).resolve() != Path(longform["file_path"]).resolve():
        raise ReadinessError("requested long-form does not match manifest")
    if Path(saved_short["file_path"]).resolve() != Path(short["file_path"]).resolve():
        raise ReadinessError("requested Short does not match manifest")
    if str(saved_longform.get("clip_id")) != str(longform.get("clip_id")):
        raise ReadinessError("requested long-form clip id does not match manifest")
    if str(saved_short.get("clip_id")) != str(short.get("clip_id")):
        raise ReadinessError("requested Short clip id does not match manifest")
    _require_qc(data)
    candidates = _require_candidates(thumbnail, manifest_dir=manifest_path.parent)
    pairs = _require_packaging_pairs(data, manifest_dir=manifest_path.parent)
    selection = thumbnail.get("selection") or {}
    selected_label = str(selection.get("label") or "")
    package_selection = (data.get("packaging") or {}).get("selection") or {}
    if data.get("status") != "approved" or data.get("review_required") is not False:
        raise ReadinessError("manifest is not approved")
    if selected_label not in candidates or thumbnail.get("file_path") != candidates.get(selected_label):
        raise ReadinessError("manifest has no valid selected thumbnail")
    if package_selection.get("label") != selected_label:
        raise ReadinessError("title and thumbnail are not selected as one packaging pair")
    if saved_longform.get("title") != pairs[selected_label].get("title"):
        raise ReadinessError("selected long-form title does not match packaging pair")
    _verify_integrity(data)
    probe_video(Path(longform["file_path"]))
    probe_video(Path(short["file_path"]))
    case_key = _case_key(saved_longform, saved_short)
    bundle_hash = _bundle_hash(data, selected_label)
    if bundle_hash != (data.get("approval") or {}).get("bundle_hash"):
        raise ReadinessError("approved bundle metadata changed")
    if store.decision_for_artifact(case_key, bundle_hash) != "approved":
        raise ReadinessError("approval ledger does not match this artifact bundle")
    return {"case_key": case_key, "bundle_hash": bundle_hash,
            "title": str(saved_longform["title"]),
            "thumbnail": candidates[selected_label], "manifest_path": str(manifest_path)}
