"""Configuration loading. Every knob lives in config/pipeline.yaml; secrets
live in config/.env. Nothing else in the package reads either file directly."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "pipeline.yaml"
ENV_PATH = ROOT / "config" / ".env"
SPEC_VERSION = "1.0.0"


class Config:
    """Dot-and-bracket access over the YAML tree, with path resolution."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, dotted: str, default: Any = None) -> Any:
        """cfg.get('output.short.max_duration_s')"""
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        sentinel = object()
        value = self.get(dotted, sentinel)
        if value is sentinel:
            raise KeyError(f"missing required config key: {dotted}")
        return value

    def path(self, dotted: str) -> Path:
        """Resolve a configured relative path against the project root."""
        p = Path(self.require(dotted))
        return p if p.is_absolute() else ROOT / p

    @property
    def root(self) -> Path:
        return ROOT


def load_env() -> None:
    """Minimal .env loader — avoids a python-dotenv dependency.

    Does not overwrite variables already present in the environment, so a shell
    export or CI secret always wins over the file.
    """
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: Path | None = None) -> Config:
    load_env()
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"config not found: {cfg_path}")
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg = Config(data)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    """Fail loudly at startup rather than three stages into a nightly run."""
    mode = cfg.get("autonomy.mode")
    if mode not in {"manual", "assisted", "auto"}:
        raise ValueError(f"autonomy.mode must be manual|assisted|auto, got {mode!r}")

    weights = cfg.require("analysis.rubric_weights")
    total = sum(weights.values())
    if total != 100:
        raise ValueError(
            f"analysis.rubric_weights must sum to 100, got {total}. "
            "Scores are computed against these weights and will be meaningless otherwise."
        )

    short_max = cfg.require("output.short.max_duration_s")
    if short_max > 60:
        raise ValueError(
            f"output.short.max_duration_s is {short_max}; platforms reject "
            "vertical shorts at 60s or longer."
        )

    lf = cfg.require("output.longform")
    if lf["min_duration_s"] >= lf["max_duration_s"]:
        raise ValueError("output.longform.min_duration_s must be < max_duration_s")


def prompt_text(name: str) -> tuple[str, str, str]:
    """Load a prompt file, returning (version, system, user_template).

    Prompt files carry YAML front matter and are split on the '# SYSTEM' and
    '# USER' headers. Versions get stamped into every clip manifest so a
    published clip can always be traced to the exact instructions that made it.
    """
    path = ROOT / "prompts" / f"{name}.md"
    raw = path.read_text(encoding="utf-8")

    version = "unknown"
    if raw.startswith("---"):
        _, front, raw = raw.split("---", 2)
        meta = yaml.safe_load(front) or {}
        version = str(meta.get("version", "unknown"))

    if "# SYSTEM" not in raw or "# USER" not in raw:
        raise ValueError(f"prompt {name} must contain '# SYSTEM' and '# USER' sections")

    _, rest = raw.split("# SYSTEM", 1)
    system, user = rest.split("# USER", 1)
    return version, system.strip(), user.strip()
