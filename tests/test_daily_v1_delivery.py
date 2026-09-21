from pathlib import Path
from types import SimpleNamespace

from boydclips import publish
from boydclips.config import load_config


class Store:
    def __init__(self):
        self.urls = {}
        self.descriptions = {}
        self.records = []

    def publication_url(self, clip_id, platform):
        return self.urls.get((clip_id, platform))

    def record_publication(self, clip_id, platform, remote_id, url, privacy):
        self.urls[(clip_id, platform)] = url
        self.records.append((clip_id, platform, url))

    def set_clip_description(self, clip_id, description):
        self.descriptions[clip_id] = description

    @staticmethod
    def promotion_ready(min_consecutive, max_safety_rejects):
        return False, "fixture promotion block"


def cfg(mode="assisted"):
    config = load_config()
    config._data["autonomy"]["mode"] = mode
    config._data["publish"]["youtube"]["api_audited"] = True
    config._data["publish"]["youtube"]["enabled"] = True
    return config


def clips(tmp_path):
    return (
        {"clip_id": "case:10:longform", "file_path": str(tmp_path / "longform.mp4"),
         "title": "Long", "description": "Description"},
        {"clip_id": "case:10:short", "file_path": str(tmp_path / "short.mp4"),
         "title": "Short", "description": "", "source_case_key": "case:10"},
    )


class Publisher:
    name = "youtube"

    def __init__(self, fail_short=False):
        self.fail_short = fail_short
        self.calls = []

    def publish(self, path, title, description, privacy, **kwargs):
        self.calls.append(Path(path).name)
        if Path(path).name == "short.mp4" and self.fail_short:
            raise RuntimeError("fixture short failure")
        stem = Path(path).stem
        return SimpleNamespace(platform="youtube", remote_id=stem,
                               url=f"https://youtube.test/{stem}", privacy=privacy)


def approve_preflight(monkeypatch):
    monkeypatch.setattr(publish.readiness, "validate_publish_bundle", lambda *args, **kwargs: {
        "thumbnail": "selected.jpg", "bundle_hash": "abc", "case_key": "case:10",
    })


def test_retry_resumes_only_missing_short(tmp_path, monkeypatch):
    config = cfg()
    store = Store()
    longform, short = clips(tmp_path)
    approve_preflight(monkeypatch)

    first_publisher = Publisher(fail_short=True)
    monkeypatch.setattr(publish, "build_publishers", lambda _cfg: {"youtube": first_publisher})
    first = publish.publish_pair(config, store, longform=longform, short=short, context={"hook_line": "hook"})
    assert first_publisher.calls == ["longform.mp4", "short.mp4"]
    assert first["complete"] is False

    retry_publisher = Publisher()
    monkeypatch.setattr(publish, "build_publishers", lambda _cfg: {"youtube": retry_publisher})
    second = publish.publish_pair(config, store, longform=longform, short=short, context={"hook_line": "hook"})
    assert retry_publisher.calls == ["short.mp4"]
    assert second["longform"]["reused"] is True
    assert second["complete"] is True
    assert len([row for row in store.records if row[0].endswith(":longform")]) == 1


def test_existing_short_platform_is_not_uploaded_again(tmp_path, monkeypatch):
    config = cfg()
    store = Store()
    longform, short = clips(tmp_path)
    store.urls[(longform["clip_id"], "youtube")] = "https://youtube.test/long"
    store.urls[(short["clip_id"], "youtube")] = "https://youtube.test/short"
    approve_preflight(monkeypatch)
    adapter = Publisher()
    monkeypatch.setattr(publish, "build_publishers", lambda _cfg: {"youtube": adapter})

    report = publish.publish_pair(config, store, longform=longform, short=short, context={"hook_line": "hook"})

    assert adapter.calls == []
    assert report["complete"] is True
    assert report["short"]["youtube"]["reused"] is True


def test_auto_mode_enforces_promotion_gate_before_preflight_or_network(tmp_path, monkeypatch):
    config = cfg("auto")
    store = Store()
    longform, short = clips(tmp_path)
    called = {"preflight": 0, "publisher": 0}
    monkeypatch.setattr(publish.readiness, "validate_publish_bundle",
                        lambda *args, **kwargs: called.__setitem__("preflight", 1))
    monkeypatch.setattr(publish, "build_publishers",
                        lambda _cfg: called.__setitem__("publisher", 1) or {})

    report = publish.publish_pair(config, store, longform=longform, short=short, context={"hook_line": "hook"})

    assert report["complete"] is False
    assert "fixture promotion block" in report["skipped"][0]
    assert called == {"preflight": 0, "publisher": 0}
