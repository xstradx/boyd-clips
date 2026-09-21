from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "boydclips" / "producer_brain.py"
PIPELINE_PATH = ROOT / "src" / "boydclips" / "pipeline.py"


def test_module_has_no_network_process_render_generation_or_publish_dependency():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    forbidden = {
        "anthropic",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "publish",
        "render",
        "thumb_direct",
        "thumb_pipeline",
    }
    assert imported.isdisjoint(forbidden)


def test_v1_is_connected_at_the_review_gated_pipeline_seam():
    pipeline_source = PIPELINE_PATH.read_text(encoding="utf-8").lower()

    assert "producer_brain.material_from_pipeline" in pipeline_source
    assert "producer_brain.package_from_plan" in pipeline_source
    assert "autonomy.mode" not in MODULE_PATH.read_text(encoding="utf-8")


def test_module_exposes_request_data_but_never_constructs_or_calls_a_backend():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert "build_backend" not in called_names
    assert "complete" not in called_names
    assert "publish" not in called_names
    assert "render_longform" not in called_names
    assert "generate" not in called_names
