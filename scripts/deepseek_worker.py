"""Run one bounded Boyd task on the configured DeepSeek production model.

A ChatGPT-authenticated Astra session cannot spawn a Codex custom agent on an
API-key provider. This wrapper creates a separate Codex exec process and passes
the existing gitignored DEEPSEEK_API_KEY through the environment, never argv.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "pipeline.yaml"
DOTENV = ROOT / "config" / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


def _settings() -> tuple[str, str, str, str]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    analysis = cfg["analysis"]
    provider = analysis["provider"]
    return (
        str(analysis["model"]),
        str(provider["name"]),
        str(provider["base_url"]),
        str(provider["env_key"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="?", help="Task text. Reads stdin when omitted.")
    parser.add_argument("--effort", choices=("low", "high", "max"), default="high")
    parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write"),
        default="workspace-write",
    )
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output", type=Path, help="Optional final-message output file.")
    args = parser.parse_args()

    task = args.task if args.task is not None else sys.stdin.read()
    if not task.strip():
        parser.error("task text is required as an argument or on stdin")

    _load_dotenv(DOTENV)
    model, provider, base_url, env_key = _settings()
    if not os.environ.get(env_key):
        raise SystemExit(f"{env_key} is not set; expected it in config/.env or environment")

    codex = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        raise SystemExit("codex CLI is not on PATH")
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    model_catalog = codex_home / "models.json"
    if not model_catalog.exists():
        raise SystemExit(f"DeepSeek model catalog is missing: {model_catalog}")

    with tempfile.TemporaryDirectory(prefix="boyd-deepseek-worker-") as tmp:
        final_path = args.output.resolve() if args.output else Path(tmp) / "last-message.txt"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            codex,
            "exec",
            "--ephemeral",
            "--sandbox",
            args.sandbox,
            "--disable",
            "plugins",
            "--disable",
            "apps",
            "--disable",
            "multi_agent",
            "--disable",
            "image_generation",
            "--disable",
            "computer_use",
            "--disable",
            "hooks",
            "--enable",
            "skip_host_skill_discovery",
            "--model",
            model,
            "--config",
            f'model_provider="{provider}"',
            "--config",
            f'model_providers.{provider}.name="{provider}"',
            "--config",
            f'model_providers.{provider}.base_url="{base_url}"',
            "--config",
            f'model_providers.{provider}.wire_api="responses"',
            "--config",
            f'model_providers.{provider}.env_key="{env_key}"',
            "--config",
            f'model_reasoning_effort="{args.effort}"',
            "--config",
            f'model_catalog_json="{model_catalog.as_posix()}"',
            "--config",
            'approval_policy="never"',
            "--config",
            'web_search="disabled"',
            "--output-last-message",
            str(final_path),
            "--cd",
            str(ROOT),
            "-",
        ]
        print(f"deepseek-worker: model={model} provider={provider} effort={args.effort}")
        try:
            completed = subprocess.run(
                command,
                input=task,
                text=True,
                encoding="utf-8",
                timeout=args.timeout,
                cwd=ROOT,
            )
        except subprocess.TimeoutExpired:
            print(f"deepseek-worker: timed out after {args.timeout}s", file=sys.stderr)
            return 124

        if args.output and final_path.exists():
            print(f"deepseek-worker: final message saved to {final_path}")
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
