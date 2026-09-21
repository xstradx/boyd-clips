"""Run up to eight independent DeepSeek worker tasks for an Astra supervisor.

Input is a JSON array. Each item needs ``id`` and ``task`` and may set
``effort`` (low/high/max) and ``sandbox`` (read-only/workspace-write). Results,
logs, and final messages are kept in one output directory for Astra to inspect.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "deepseek_worker.py"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_WORKERS = 8


@dataclass(frozen=True)
class Task:
    id: str
    task: str
    effort: str = "high"
    sandbox: str = "read-only"


def load_tasks(path: Path) -> list[Task]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("task manifest must be a non-empty JSON array")
    tasks: list[Task] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"task {index} must be an object")
        task_id = str(item.get("id") or "")
        text = str(item.get("task") or "").strip()
        effort = str(item.get("effort") or "high")
        sandbox = str(item.get("sandbox") or "read-only")
        if not ID_RE.fullmatch(task_id):
            raise ValueError(f"task {index} has invalid id {task_id!r}")
        if task_id in seen:
            raise ValueError(f"duplicate task id {task_id!r}")
        if not text:
            raise ValueError(f"task {task_id!r} has no task text")
        if effort not in {"low", "high", "max"}:
            raise ValueError(f"task {task_id!r} has invalid effort {effort!r}")
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError(f"task {task_id!r} has invalid sandbox {sandbox!r}")
        seen.add(task_id)
        tasks.append(Task(task_id, text, effort, sandbox))
    return tasks


def run_task(task: Task, output_dir: Path, timeout: int) -> dict[str, Any]:
    final_path = output_dir / f"{task.id}.final.txt"
    log_path = output_dir / f"{task.id}.log.txt"
    command = [
        sys.executable,
        str(WORKER),
        "--effort",
        task.effort,
        "--sandbox",
        task.sandbox,
        "--timeout",
        str(timeout),
        "--output",
        str(final_path),
    ]
    completed = subprocess.run(
        command,
        input=task.task,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=timeout + 30,
        cwd=ROOT,
    )
    log_path.write_text(
        completed.stdout + ("\nSTDERR\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
    )
    return {
        "id": task.id,
        "returncode": completed.returncode,
        "effort": task.effort,
        "sandbox": task.sandbox,
        "final": str(final_path) if final_path.exists() else None,
        "log": str(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if not 1 <= args.max_workers <= MAX_WORKERS:
        parser.error(f"--max-workers must be between 1 and {MAX_WORKERS}")

    tasks = load_tasks(args.manifest.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    worker_count = min(args.max_workers, len(tasks))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(run_task, task, output_dir, args.timeout): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"id": task.id, "returncode": 1, "error": str(exc)}
            results.append(result)
            print(f"{task.id}: rc={result['returncode']}")

    results.sort(key=lambda item: item["id"])
    summary = output_dir / "summary.json"
    summary.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"summary: {summary}")
    return 0 if all(item.get("returncode") == 0 for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

