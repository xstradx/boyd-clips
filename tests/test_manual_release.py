"""Manual selected-file release checks do not restart full-package production."""
import json

import pytest
from PIL import Image

from boydclips import cli, readiness


def packet(tmp_path):
    video = tmp_path / "long.mp4"
    video.write_bytes(b"selected video fixture")
    thumb = tmp_path / "A.png"
    Image.new("RGB", (1280, 720), "navy").save(thumb)
    data = {
        "case_key": "source:100", "title": "Judge Boyd Questions the Phone Dispute",
        "description": "Source-backed description reviewed by the operator.",
        "audience": "not_made_for_kids",
        "video": {"path": "long.mp4", "sha256": readiness.sha256_file(video)},
        "thumbnail": {"path": "A.png", "sha256": readiness.sha256_file(thumb), "status": "accepted"},
    }
    path = tmp_path / "release.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def test_selected_release_needs_no_short_other_thumbnails_or_model(tmp_path, monkeypatch, capsys):
    path, data = packet(tmp_path)
    original = path.read_bytes()
    monkeypatch.setattr(readiness, "probe_video", lambda p: {"duration_s": 60})
    monkeypatch.setattr(cli, "Pipeline", lambda *a, **k: pytest.fail("production started"))
    monkeypatch.setattr(cli, "publish_pair", lambda *a, **k: pytest.fail("upload started"))
    assert cli.main(["release-check", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "local_files_verified"
    assert report["title"] == data["title"]
    assert "ready" not in report and "approved" not in report
    assert path.read_bytes() == original


@pytest.mark.parametrize("kind", ["video", "thumbnail"])
def test_replaced_or_missing_asset_refuses(tmp_path, kind):
    path, data = packet(tmp_path)
    target = tmp_path / data[kind]["path"]
    target.write_bytes(b"different revision")
    with pytest.raises(readiness.ReadinessError, match="hash changed"):
        readiness.check_manual_release(path)
    target.unlink()
    with pytest.raises(readiness.ReadinessError, match="missing"):
        readiness.check_manual_release(path)


@pytest.mark.parametrize("change", [
    lambda p: p["thumbnail"].update(status="rejected"),
    lambda p: p.update(title=""),
    lambda p: p.update(audience="made_for_kids"),
])
def test_incomplete_or_rejected_selection_refuses(tmp_path, change):
    path, data = packet(tmp_path)
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(readiness.ReadinessError):
        readiness.check_manual_release(path)
