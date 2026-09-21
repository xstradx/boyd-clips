"""Readiness gates for the Audit-the-Court text-only A/B/C wording test.

Nathan, 2026-09-19: "make the thumbnail ... audit the court does them and then
a/b test what it says on the thumbnail". The picture and the video title are
the control; only the words vary. `boydclips.thumbnail_text_test` builds and
re-verifies the three images. These tests prove `boydclips.readiness` refuses
any bundle that does not point at exactly that verified experiment, and that
the single-fixed-title allowance is scoped to this one explicitly verified
mode instead of becoming a blanket override.

The experiment here is BUILT for real (real PNGs, real receipt) and then
tampered, so every refusal is checked against the actual files rather than a
hand-written stand-in for them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from boydclips import readiness, thumbnail_copy as tc
from boydclips import thumbnail_visible as tv
from boydclips.config import load_config
from boydclips.thumbnail_text_test import TextVariant, build_text_only_experiment


TITLE = "Judge Boyd audits the whole docket"
EVIDENCE = 'Judge Boyd: "I audit the court in every single hearing."'
VARIANTS = (
    TextVariant("A", "Audit the court", "court"),
    TextVariant("B", "The court got audited", "audited"),
    TextVariant("C", "She audited the court live", "audited the court"),
)


@pytest.fixture(autouse=True)
def stubbed_probe(monkeypatch):
    """The bundle fixtures are not real videos; decoding is a separate gate."""
    monkeypatch.setattr(readiness, "probe_video", lambda path: {
        "duration_s": 1.0, "video": {"codec_name": "h264"}, "audio": {"codec_name": "aac"},
    })


def _model() -> str:
    return str(load_config().require("packaging.thumbnail.direct.model"))


def _analysis_model() -> str:
    return str(load_config().require("analysis.model"))


def _make_base(path: Path) -> Path:
    """A real 1280x720, deliberately not flat, standing in for the shared base."""
    image = Image.new("RGB", (1280, 720), (34, 42, 56))
    draw = ImageDraw.Draw(image)
    for x in range(0, 1280, 64):
        draw.rectangle([x, 230, x + 28, 560], fill=(92, 46, 44))
    draw.ellipse([860, 200, 1180, 640], fill=(104, 88, 72))
    draw.rectangle([0, 0, 1280, 96], fill=(20, 24, 32))
    image.save(path)
    return path


def _verdict(packaging: dict) -> dict:
    """A current (V2) semantic verdict over the exact packaging body."""
    return {
        "version": tc.VERSION,
        "model": _model(),
        "input_sha256": tc.input_hash(packaging),
        "visible_review": {"version": tv.VERSION, "model": _model(),
            "input_sha256": tv.input_hash(packaging),
            "concepts": [{"label": label, "understandable": True, "references_clear": True,
                "interpretation": "A viewer understands the court audit.",
                "reason": "The visible title identifies the subject."} for label in "ABC"]},
        "concepts": [
            {
                "label": label,
                **{check: True for check in tc.CHECKS},
                "interpretation": "The words name the audit this hearing turned into.",
                "viewer_question": f"What did the audit of the court show for {label}?",
                "source_anchor": 'hearing transcript: "I audit the court"',
                "reason": "Case-specific wording with an open question, supported by the source.",
            }
            for label in "ABC"
        ],
        "shipped_quote": {
            "ok": True,
            "viewer_question": "What did the judge's audit of the court actually turn up?",
            "reason": "The rendered words restate the judge's own promise to audit the court.",
        },
    }


def _rehash_review(packaging: dict) -> None:
    """Re-bind the semantic verdict to a mutated packaging body.

    A real run writes the review once the copy is final, so recomputing the
    input hash keeps a deliberate mutation from being caught by the staleness
    gate instead of the binding under test.
    """
    packaging["thumbnail_copy_review"]["input_sha256"] = tc.input_hash(packaging)
    packaging["thumbnail_copy_review"]["visible_review"]["input_sha256"] = tv.input_hash(packaging)


def build_bundle(tmp_path: Path) -> dict:
    """Build a real text-only experiment and a manifest that points at it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = _make_base(tmp_path / "base_text_only.png")
    outdir = tmp_path / "text_only"
    receipt = build_text_only_experiment(
        base=base, title=TITLE, variants=VARIANTS, evidence=EVIDENCE, outdir=outdir,
    )
    receipt_path = outdir / "thumbnail-text-only.json"
    longform = tmp_path / "longform.mp4"
    short = tmp_path / "short.mp4"
    longform.write_bytes(b"fixture long-form")
    short.write_bytes(b"fixture short")
    candidates = {record["label"]: record["png_path"] for record in receipt["variants"]}
    packaging = {
        "hook_verified": True,
        "tags": ["judge boyd", "courtroom audit"],
        "short_title": "The Judge Audited This Court Hearing And It Changed",
        "packaging_pairs": [
            {
                "label": record["label"],
                # ONE fixed title for all three: the title is the control here.
                "title": TITLE,
                "thumbnail_text": record["text"],
                "thumbnail_yellow": record["emphasis"],
                "reason": f"Variant {record['label']} tests another wording of the same audit hook.",
            }
            for record in receipt["variants"]
        ],
        "thumbnail_experiment": {
            "type": "thumbnail_text_only",
            "fixed_title": TITLE,
            "base_sha256": receipt["base"]["sha256"],
            "receipt_path": str(receipt_path),
        },
    }
    packaging["thumbnail_copy_review"] = _verdict(packaging)
    manifest = {
        "status": "candidate",
        "review_required": True,
        "source": {"video_id": "video"},
        "case": {"start_s": 10.0, "end_s": 610.0, "story_windows": [[10.0, 610.0]]},
        "safety": {"safety_pass": True},
        "models": {"analysis_model": _analysis_model(), "prompt_versions": {}},
        "packaging": packaging,
        "short_editor": {
            "ok": True,
            "render_qc": [{"gate": "fixture", "ok": True}],
            "visual_qc": {"ok": True, "checks": [{"check": "fixture", "ok": True}]},
        },
        "outputs": {
            "longform": {"clip_id": "video:10:longform", "file_path": str(longform),
                         "duration_s": 600},
            "short": {"clip_id": "video:10:short", "file_path": str(short),
                      "duration_s": 45, "source_case_key": "video:10"},
            "thumbnail": {
                "mode": "thumbnail_text_only",
                "complete": True,
                "model": _model(),
                "receipt_path": str(receipt_path),
                "file_path": candidates["A"],
                "status": "candidate",
                "candidates": candidates,
            },
        },
    }
    bundle = {
        "manifest_path": tmp_path / "manifest.json",
        "manifest": manifest,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "base": base,
        "outdir": outdir,
        "candidates": candidates,
    }
    save(bundle)
    return bundle


def save(bundle: dict) -> None:
    """Persist the (possibly mutated) manifest and re-stamp its hashes."""
    bundle["manifest_path"].write_text(json.dumps(bundle["manifest"]), encoding="utf-8")
    readiness.stamp_manifest(bundle["manifest_path"])


def refuse(bundle: dict, match: str) -> None:
    with pytest.raises(readiness.ReadinessError, match=match):
        readiness.validate_candidate_bundle(bundle["manifest_path"], probe=False)


def packaging_of(bundle: dict) -> dict:
    return bundle["manifest"]["packaging"]


class Decisions:
    def __init__(self) -> None:
        self.approved: set[tuple[str, str]] = set()

    def decision_for_artifact(self, case_key, artifact_hash):
        return "approved" if (case_key, artifact_hash) in self.approved else None


# --------------------------------------------------------------------------
# positive route
# --------------------------------------------------------------------------
def test_text_only_bundle_validates_approves_and_reaches_publish(tmp_path):
    bundle = build_bundle(tmp_path)

    checked = readiness.validate_candidate_bundle(bundle["manifest_path"], probe=False)
    assert checked["ready"] is True
    assert checked["case_key"] == "video:10"
    # The verified A/B/C route, not the legacy single-image label.
    assert set(checked["thumbnails"]) == {"A", "B", "C"}
    assert checked["thumbnails"]["B"].endswith("variant_B.png")
    notes = " ".join(checked["notes"])
    assert "fixed" in notes and "Studio" in notes  # never claims a live platform test

    evidence = readiness.approve_manifest(bundle["manifest_path"], "B", probe=False)
    assert evidence["title"] == TITLE
    assert evidence["thumbnail"] == checked["thumbnails"]["B"]

    store = Decisions()
    store.approved.add(("video:10", evidence["bundle_hash"]))
    outputs = bundle["manifest"]["outputs"]
    published = readiness.validate_publish_bundle(
        outputs["longform"], outputs["short"], store=store,
    )
    assert published["bundle_hash"] == evidence["bundle_hash"]
    assert published["title"] == TITLE
    assert published["thumbnail"] == checked["thumbnails"]["B"]


def test_text_only_pairs_share_one_fixed_title_but_legacy_still_needs_three(tmp_path):
    bundle = build_bundle(tmp_path)
    pairs = readiness._require_packaging_pairs(
        bundle["manifest"], manifest_dir=bundle["manifest_path"].parent,
    )
    assert set(pairs) == {"A", "B", "C"}
    assert {pairs[label]["title"] for label in "ABC"} == {TITLE}

    # Negative control: the same single title in any other mode is still refused.
    legacy = {
        "packaging": {
            "tags": ["judge boyd", "courtroom audit"],
            "short_title": "The Judge Audited This Court Hearing And It Changed",
            "packaging_pairs": [
                {"label": label, "title": TITLE, "thumbnail_text": f"hook {label}",
                 "reason": f"reason {label}"}
                for label in "ABC"
            ],
        },
        "outputs": {
            "longform": {"file_path": "unused"},
            "short": {"file_path": "unused"},
            "thumbnail": {"mode": "legacy", "file_path": "unused"},
        },
    }
    with pytest.raises(readiness.ReadinessError, match="genuinely distinct"):
        readiness._require_packaging_pairs(legacy)

    legacy["packaging"]["packaging_pairs"][1]["title"] = "A genuinely different title B"
    legacy["packaging"]["packaging_pairs"][2]["title"] = "A genuinely different title C"
    assert set(readiness._require_packaging_pairs(legacy)) == {"A", "B", "C"}


def test_legacy_mode_keeps_its_own_label_and_the_abc_route_is_not_replaced(tmp_path):
    legacy_image = tmp_path / "quote.jpg"
    Image.new("RGB", (1280, 720), "grey").save(legacy_image)
    assert set(readiness._require_candidates(
        {"mode": "legacy", "file_path": str(legacy_image)},
    )) == {"L"}


# --------------------------------------------------------------------------
# negative controls: manifest no longer points at the verified experiment
# --------------------------------------------------------------------------
def test_pair_wording_must_be_the_wording_that_was_rendered(tmp_path):
    bundle = build_bundle(tmp_path)
    packaging = packaging_of(bundle)
    packaging["packaging_pairs"][1]["thumbnail_text"] = "A completely different hook"
    _rehash_review(packaging)
    save(bundle)

    refuse(bundle, "not the wording rendered")


def test_pair_yellow_must_be_the_yellow_run_that_was_rendered(tmp_path):
    bundle = build_bundle(tmp_path)
    packaging = packaging_of(bundle)
    packaging["packaging_pairs"][2]["thumbnail_yellow"] = "improved"
    _rehash_review(packaging)
    save(bundle)
    refuse(bundle, "yellow")

    bundle = build_bundle(tmp_path / "second")
    packaging = packaging_of(bundle)
    # Present in the words, but not the substring that is actually yellow.
    packaging["packaging_pairs"][0]["thumbnail_yellow"] = "Audit"
    _rehash_review(packaging)
    save(bundle)
    refuse(bundle, "yellow run rendered")

    bundle = build_bundle(tmp_path / "third")
    packaging = packaging_of(bundle)
    del packaging["packaging_pairs"][1]["thumbnail_yellow"]
    _rehash_review(packaging)
    save(bundle)
    refuse(bundle, "missing the yellow key-phrase")


def test_pair_title_must_be_the_one_fixed_title(tmp_path):
    bundle = build_bundle(tmp_path)
    packaging = packaging_of(bundle)
    packaging["packaging_pairs"][1]["title"] = "A different title for the same image"
    _rehash_review(packaging)
    save(bundle)

    refuse(bundle, "is not the one fixed title")


def test_recorded_fixed_title_must_match_the_receipt(tmp_path):
    bundle = build_bundle(tmp_path)
    packaging = packaging_of(bundle)
    packaging["thumbnail_experiment"]["fixed_title"] = "A title the experiment never held"
    for pair in packaging["packaging_pairs"]:
        pair["title"] = "A title the experiment never held"
    _rehash_review(packaging)
    save(bundle)

    refuse(bundle, "fixed title")


def test_recorded_base_hash_must_match_the_receipt(tmp_path):
    bundle = build_bundle(tmp_path)
    packaging = packaging_of(bundle)
    packaging["thumbnail_experiment"]["base_sha256"] = "0" * 64
    _rehash_review(packaging)
    save(bundle)
    refuse(bundle, "base_sha256 does not match")

    bundle = build_bundle(tmp_path / "second")
    packaging = packaging_of(bundle)
    packaging["thumbnail_experiment"]["base_sha256"] = "TBD"
    _rehash_review(packaging)
    save(bundle)
    refuse(bundle, "must be the sha256")


def test_candidates_must_be_the_tested_files(tmp_path):
    bundle = build_bundle(tmp_path)
    lookalike = tmp_path / "not_the_tested_file.png"
    shutil.copyfile(bundle["candidates"]["B"], lookalike)
    bundle["manifest"]["outputs"]["thumbnail"]["candidates"]["B"] = str(lookalike)
    save(bundle)

    refuse(bundle, "not pointing at the images that were tested")


def test_duplicate_images_cannot_stand_in_for_three_variants(tmp_path):
    bundle = build_bundle(tmp_path)
    # Tamper the receipt and the manifest the same way, so the only remaining
    # defect is that A, B and C are one image.
    receipt = json.loads(bundle["receipt_path"].read_text(encoding="utf-8"))
    first = receipt["variants"][0]
    for record in receipt["variants"][1:]:
        record["png_path"] = first["png_path"]
        record["png_sha256"] = first["png_sha256"]
    bundle["receipt_path"].write_text(json.dumps(receipt), encoding="utf-8")
    for label in ("B", "C"):
        bundle["manifest"]["outputs"]["thumbnail"]["candidates"][label] = first["png_path"]
    save(bundle)

    refuse(bundle, "three different images")


def test_missing_receipt_and_missing_receipt_path_refuse(tmp_path):
    bundle = build_bundle(tmp_path)
    Path(bundle["receipt_path"]).unlink()
    refuse(bundle, "receipt is missing")

    bundle = build_bundle(tmp_path / "second")
    bundle["manifest"]["outputs"]["thumbnail"].pop("receipt_path")
    save(bundle)
    refuse(bundle, "receipt path")


def test_current_semantic_review_is_required_even_with_a_valid_receipt(tmp_path):
    bundle = build_bundle(tmp_path)
    packaging_of(bundle).pop("thumbnail_copy_review")
    save(bundle)
    refuse(bundle, "semantic copy review")

    # Stale control: the words changed after the verdict was written, and the
    # review is not silently re-hashed.
    bundle = build_bundle(tmp_path / "second")
    packaging_of(bundle)["packaging_pairs"][0]["thumbnail_text"] = "Audit the court again"
    save(bundle)
    refuse(bundle, "missing or stale")


def test_text_only_receipt_revalidation_is_enforced(tmp_path):
    bundle = build_bundle(tmp_path)
    receipt = json.loads(bundle["receipt_path"].read_text(encoding="utf-8"))
    # A receipt that is internally inconsistent (its own config no longer
    # matches the built title). Readiness must re-run the experiment check
    # against the real files instead of trusting the recorded verdict.
    receipt["config"]["fixed_title"] = "A title the experiment never held"
    bundle["receipt_path"].write_text(json.dumps(receipt), encoding="utf-8")
    save(bundle)

    refuse(bundle, "failed re-validation")


def test_text_only_mode_does_not_bypass_the_production_gates(tmp_path):
    bundle = build_bundle(tmp_path)
    bundle["manifest"]["safety"]["safety_pass"] = False
    save(bundle)
    refuse(bundle, "safety gate")

    bundle = build_bundle(tmp_path / "second")
    bundle["manifest"]["outputs"]["thumbnail"]["complete"] = False
    save(bundle)
    refuse(bundle, "complete text-only A/B/C")

    bundle = build_bundle(tmp_path / "third")
    bundle["manifest"]["outputs"]["thumbnail"]["model"] = "some-other-model"
    save(bundle)
    refuse(bundle, "configured")

    bundle = build_bundle(tmp_path / "fourth")
    del bundle["manifest"]["outputs"]["thumbnail"]["candidates"]["C"]
    save(bundle)
    refuse(bundle, "A, B and C")
