import json
from pathlib import Path

import pytest

from scripts.deepseek_workers import MAX_WORKERS, load_tasks


def _manifest(tmp_path: Path, data) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_worker_batch_is_capped_at_eight():
    assert MAX_WORKERS == 8


def test_load_tasks_accepts_bounded_worker_settings(tmp_path):
    tasks = load_tasks(_manifest(tmp_path, [
        {"id": "scan", "task": "Inspect only.", "effort": "low"},
        {"id": "fix_1", "task": "Implement one fix.", "sandbox": "workspace-write"},
    ]))
    assert [(task.id, task.effort, task.sandbox) for task in tasks] == [
        ("scan", "low", "read-only"),
        ("fix_1", "high", "workspace-write"),
    ]


@pytest.mark.parametrize("data, match", [
    ([], "non-empty"),
    ([{"id": "bad id", "task": "x"}], "invalid id"),
    ([{"id": "same", "task": "x"}, {"id": "same", "task": "y"}], "duplicate"),
    ([{"id": "empty", "task": ""}], "no task text"),
    ([{"id": "x", "task": "x", "effort": "medium"}], "invalid effort"),
])
def test_load_tasks_rejects_unsafe_or_ambiguous_manifests(tmp_path, data, match):
    with pytest.raises(ValueError, match=match):
        load_tasks(_manifest(tmp_path, data))

