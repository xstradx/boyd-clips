import json
from pathlib import Path

import pytest
from PIL import Image

from boydclips import cli, producer_brain, readiness
from boydclips.config import load_config
from boydclips.state import Store


def configured_model(key: str) -> str:
    """The model this project is configured to run.

    2026-09-16: these fixtures used to hard-code "gpt-5.6-sol". That model is
    unreachable from this PC (`codex login` reports "ChatGPT login is
    disabled"), so pinning it in fixtures made the suite assert a world that
    cannot exist. Reading the configured value keeps the same guarantee — a
    bundle naming a different model still refuses — without hard-coding a
    retired name.
    """
    return str(load_config().require(key))


class Decisions:
    def __init__(self):
        self.approved = set()

    def decision_for_artifact(self, case_key, artifact_hash):
        return "approved" if (case_key, artifact_hash) in self.approved else None


def make_bundle(tmp_path: Path):
    longform = tmp_path / "longform.mp4"
    short = tmp_path / "short.mp4"
    longform.write_bytes(b"fixture long-form")
    short.write_bytes(b"fixture short")
    candidates = {}
    for label, color in zip("ABC", ("red", "green", "blue")):
        path = tmp_path / f"thumb_{label}.jpg"
        Image.new("RGB", (1280, 720), color).save(path)
        candidates[label] = str(path)
    manifest = {
        "status": "candidate",
        "review_required": True,
        "source": {"video_id": "video"},
        "case": {"start_s": 10.0, "end_s": 610.0, "story_windows": [[10.0, 610.0]]},
        "safety": {"safety_pass": True},
        "models": {"analysis_model": configured_model("analysis.model"), "prompt_versions": {}},
        "packaging": {
            "hook_verified": True,
            "tags": ["judge boyd", "phone dispute"],
            "short_title": "The Missing Phone Story Changed This Court Hearing",
            "packaging_pairs": [
                {"label": label, "title": f"Distinct title {label}",
                 "thumbnail_text": f"TEXT {label}", "reason": f"reason {label}"}
                for label in "ABC"
            ],
        },
        "short_editor": {
            "ok": True,
            "render_qc": [{"gate": "fixture", "ok": True}],
            "visual_qc": {"ok": True, "checks": [{"check": "fixture", "ok": True}]},
        },
        "outputs": {
            "longform": {"clip_id": "video:10:longform", "file_path": str(longform), "duration_s": 600},
            "short": {"clip_id": "video:10:short", "file_path": str(short), "duration_s": 45,
                      "source_case_key": "video:10"},
            "thumbnail": {"file_path": str(candidates["A"]), "status": "candidate",
        "candidates": candidates, "mode": "direct_gen",
        "model": configured_model("packaging.thumbnail.direct.model"),
                          "complete": True},
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)
    return manifest_path, manifest["outputs"]["longform"], manifest["outputs"]["short"]


def allow_video_probe(monkeypatch):
    monkeypatch.setattr(readiness, "probe_video", lambda path: {
        "duration_s": 1.0, "video": {"codec": "h264"}, "audio": {"codec": "aac"},
    })


def test_approval_binds_exact_three_thumbnails_and_artifact_hash(tmp_path, monkeypatch):
    allow_video_probe(monkeypatch)
    manifest_path, longform, short = make_bundle(tmp_path)
    candidate = readiness.validate_candidate_bundle(manifest_path)
    assert candidate["ready"] is True and candidate["case_key"] == "video:10"
    evidence = readiness.approve_manifest(manifest_path, "B")
    store = Decisions()

    with pytest.raises(readiness.ReadinessError, match="approval ledger"):
        readiness.validate_publish_bundle(longform, short, store=store)

    store.approved.add(("video:10", evidence["bundle_hash"]))
    checked = readiness.validate_publish_bundle(longform, short, store=store)
    assert checked["thumbnail"] == str(tmp_path / "thumb_B.jpg")
    assert checked["bundle_hash"] == evidence["bundle_hash"]
    assert checked["case_key"] == "video:10"


def test_changed_artifact_fails_hash_check(tmp_path, monkeypatch):
    allow_video_probe(monkeypatch)
    manifest_path, longform, short = make_bundle(tmp_path)
    evidence = readiness.approve_manifest(manifest_path, "A")
    store = Decisions()
    store.approved.add(("video:10", evidence["bundle_hash"]))
    Path(short["file_path"]).write_bytes(b"changed after approval")

    with pytest.raises(readiness.ReadinessError, match="hash changed"):
        readiness.validate_publish_bundle(longform, short, store=store)


def test_missing_short_qc_fails_closed(tmp_path, monkeypatch):
    allow_video_probe(monkeypatch)
    manifest_path, longform, short = make_bundle(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["short_editor"]["visual_qc"]["ok"] = False
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)

    with pytest.raises(readiness.ReadinessError, match="Short visual QC"):
        readiness.approve_manifest(manifest_path, "A")


def test_candidate_bundle_requires_sol_for_reasoning_and_thumbnails(tmp_path):
    manifest_path, _longform, _short = make_bundle(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["models"]["analysis_model"] = "legacy-model"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)
    with pytest.raises(readiness.ReadinessError, match="reasoning model"):
        readiness.validate_candidate_bundle(manifest_path, probe=False)

    data["models"]["analysis_model"] = configured_model("analysis.model")
    data["outputs"]["thumbnail"]["model"] = "legacy-model"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)
    with pytest.raises(readiness.ReadinessError, match="thumbnail session"):
        readiness.validate_candidate_bundle(manifest_path, probe=False)


def test_producer_short_must_match_rendered_source_timeline(tmp_path, monkeypatch):
    allow_video_probe(monkeypatch)
    manifest_path, _longform, _short = make_bundle(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["short_editor"]["producer_brain_source"] = {
        "decision": "MAKE", "hook_start_s": 30.0,
        "sequence": [{"edit_order": 1, "role": "hook", "start_s": 30.0, "end_s": 35.0}],
    }
    data["short_editor"]["producer_alignment"] = {"ok": True}
    data["short_editor"]["source_segments"] = [[10.0, 20.0]]
    # The version here is incidental setup: pin it to the CURRENT prompt so the
    # refusal under test is the source-timeline one, not the version gate.
    # (Left at 1.3.0 when the prompt moved to 1.3.1 on 2026-09-13, which made
    # this test fail on the wrong message.)
    data["models"]["prompt_versions"]["producer_brain_v1"] = producer_brain.PROMPT_VERSION
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)

    with pytest.raises(readiness.ReadinessError, match="does not execute"):
        readiness.validate_candidate_bundle(manifest_path)


def test_direct_bundle_requires_all_three_candidates(tmp_path):
    manifest_path, _longform, _short = make_bundle(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    del data["outputs"]["thumbnail"]["candidates"]["C"]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)

    with pytest.raises(readiness.ReadinessError, match="A, B and C"):
        readiness.approve_manifest(manifest_path, "A")


def test_incomplete_direct_session_fails_closed(tmp_path):
    manifest_path, _longform, _short = make_bundle(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["outputs"]["thumbnail"]["complete"] = False
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    readiness.stamp_manifest(manifest_path)

    with pytest.raises(readiness.ReadinessError, match="complete direct A/B/C"):
        readiness.approve_manifest(manifest_path, "A")


def test_packaging_pair_reason_cannot_name_another_labels_title(tmp_path):
    manifest_path, _longform, _short = make_bundle(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    pairs = {row["label"]: row for row in data["packaging"]["packaging_pairs"]}

    pairs["A"]["reason"] = f'Best paired with "{pairs["C"]["title"]}".'
    with pytest.raises(readiness.ReadinessError, match="pair A reason names title C"):
        readiness._require_packaging_pairs(data)

    pairs["A"]["reason"] = f'Best paired with "{pairs["A"]["title"]}".'
    pairs["B"]["reason"] = "This image adds the human issue while the title supplies context."
    assert set(readiness._require_packaging_pairs(data)) == {"A", "B", "C"}


def test_invalid_video_bytes_fail_real_probe(tmp_path):
    manifest_path, longform, short = make_bundle(tmp_path)
    evidence = readiness.approve_manifest(manifest_path, "C", probe=False)
    store = Decisions()
    store.approved.add(("video:10", evidence["bundle_hash"]))

    with pytest.raises(readiness.ReadinessError, match="not decodable"):
        readiness.validate_publish_bundle(longform, short, store=store)


def test_artifact_approval_is_idempotent_and_hash_bound(tmp_path):
    store = Store(tmp_path / "state.db")
    store.add_docket("video", "title", "2026-09-12", 1000)
    key = store.save_case(
        "video",
        {"start_s": 10.0, "end_s": 610.0, "safety": {"safety_pass": True},
         "total_score": 90, "shortable": True},
        1,
    )
    store.record_decision(key, "approved", artifact_hash="hash-one")
    store.record_decision(key, "approved", artifact_hash="hash-one")
    store.record_decision(key, "approved", artifact_hash="hash-two")

    assert store.decision_for_artifact(key, "hash-one") == "approved"
    assert store.reliability()["total_decisions"] == 2
    store.close()


def test_approve_command_records_exact_bundle_hash(tmp_path, monkeypatch, capsys):
    cfg = load_config()
    cfg._data["paths"]["state_db"] = str(tmp_path / "approve.db")
    store = Store(cfg.path("paths.state_db"))
    store.add_docket("video", "title", "2026-09-12", 1000)
    key = store.save_case(
        "video",
        {"start_s": 10.0, "end_s": 610.0, "hook_quote": "hook",
         "safety": {"safety_pass": True}, "total_score": 90, "shortable": True},
        1,
    )
    store.save_clip(key, "longform", tmp_path / "longform.mp4", 600, "Long", "D", "v")
    store.save_clip(key, "short", tmp_path / "short.mp4", 40, "Short", "", "v")
    store.close()

    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(
        cli.readiness,
        "approve_manifest",
        lambda path, label: {"case_key": key, "bundle_hash": "exact-hash",
                             "thumbnail": "B.jpg", "title": "Distinct title B",
                             "manifest_path": str(path)},
    )
    args = cli.build_parser().parse_args(["approve", key, "--concept", "B"])
    assert args.func(args) == 0

    reopened = Store(cfg.path("paths.state_db"))
    assert reopened.decision_for_artifact(key, "exact-hash") == "approved"
    reopened.close()
    assert "packaging concept B" in capsys.readouterr().out
