import pytest

from boydclips import analyze
from boydclips.config import load_config


class Backend:
    def __init__(self):
        self.calls = 0

    def complete(self, system, user, schema, label):
        self.calls += 1
        return {"ok": True}


def test_sol_call_limit_stops_before_an_extra_backend_call():
    cfg = load_config()
    cfg._data["analysis"]["max_model_calls_per_run"] = 2
    worker = analyze.Analyzer.__new__(analyze.Analyzer)
    worker.cfg = cfg
    worker.log = None
    worker.backend = Backend()
    worker.prompt_versions = {}
    worker.calls_used = 0

    worker._call("package_post", "one", {})
    worker._call("package_post", "two", {})
    with pytest.raises(analyze.ModelCallLimitError, match="2/2"):
        worker._call("package_post", "three", {})

    assert worker.backend.calls == 2
    assert [event["status"] for event in worker.usage_events] == ["complete", "complete"]
    assert all(event["input_sha256"] for event in worker.usage_events)


def test_analysis_reserves_final_sol_call_for_bundle_completion():
    cfg = load_config()
    cfg._data["analysis"]["max_model_calls_per_run"] = 2
    worker = analyze.Analyzer.__new__(analyze.Analyzer)
    worker.cfg = cfg
    worker.log = None
    worker.backend = Backend()
    worker.prompt_versions = {}
    worker.calls_used = 0
    worker.reserved_calls = 1

    worker._call("package_post", "selection", {})
    with pytest.raises(analyze.ModelCallLimitError, match="1 reserved"):
        worker._call("package_post", "would spend completion reserve", {})

    assert worker.backend.calls == 1


def test_production_limits_are_explicit_and_global():
    cfg = load_config()
    assert cfg.require("output.clips_per_day") == 1
    assert cfg.require("analysis.max_model_calls_per_run") == 20
    assert cfg.require("analysis.cli_attempts") == 1
    assert cfg.require("output.max_thumbnail_images_per_run") == 9
    assert cfg.require("packaging.thumbnail.direct.budget") == 9


def test_thumbnail_resume_reuses_only_exact_source_pairs_and_image_bytes(tmp_path, monkeypatch):
    from PIL import Image
    from boydclips import pipeline
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = load_config()
    # This test is about the DIRECT A/B/C session's resume caching, so it pins
    # that mode rather than inheriting whatever the deployed config currently
    # runs (2026-09-16: the deployed mode is legacy, which takes the compositor
    # branch and tries to grab a real frame from this fake source).
    pipe.cfg._data["packaging"]["thumbnail"]["mode"] = "direct_gen"
    pipe._thumbnail_images_remaining = 9
    pipe._thumbnail_model_calls_used = 0
    pipe._analyzer = None
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source fixture")
    paths = {}
    for key in "ABC":
        path = tmp_path / (key + ".jpg")
        Image.new("RGB", (1280, 720), "blue").save(path)
        paths[key] = str(path)
    calls = []
    def build(*args):
        calls.append(True)
        return {"mode": "direct_gen", "complete": True, "candidates": paths,
                "file_path": paths["A"], "images_generated_total": 3, "model_calls_used": 1}
    monkeypatch.setattr(pipeline.thumbnail, "build_direct", build)
    case = {"start_s": 1, "hook_start_s": 3}
    package = {"thumbnail_quote": "REAL WORDS", "thumbnail_quote_yellow": "WORDS", "packaging_pairs": [{"label": "A", "title": "Original title"}]}
    pipe._produce_thumbnail(source, 0, case, package, tmp_path)
    pipe._produce_thumbnail(source, 0, case, package, tmp_path)
    assert len(calls) == 1 and pipe._thumbnail_images_remaining == 6
    package["packaging_pairs"][0]["title"] = "New title"
    pipe._produce_thumbnail(source, 0, case, package, tmp_path)
    assert len(calls) == 2
    source.write_bytes(b"changed source")
    pipe._produce_thumbnail(source, 0, case, package, tmp_path)
    assert len(calls) == 3
