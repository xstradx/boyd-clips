# -*- coding: utf-8 -*-
"""Structural checker for the recovered work board and the live wiring it claims.

Read-only by construction: it opens files, never writes, never calls a model and
never uses the network. Every check returns what it actually observed.

    python tools/check_recovery_structure.py
    python tools/check_recovery_structure.py --json
    python tools/check_recovery_structure.py --repo . --codex-home %USERPROFILE%\\.codex \\
        --board "C:/Users/natha/OneDrive/Documents/ChatGPT/New project/conversation-recovery/items.json"

Exit code 0 = every check passed, 1 = at least one check failed, 2 = the checker
itself could not run.

The production model is read from live configuration and compared with Nathan's
recorded selection in the maintained board. Model aliases and historical
filenames do not count as conflicting production instructions.

Check names (stable; tests and reports refer to them):
    file:<path>                                required repo/board/skill file exists
    bench:cases_nonempty                       bench/bench.json holds at least one case
    contract:no_false_bench_claim              current contract does not say "No bench exists yet"
    config:analysis_model_present              config/pipeline.yaml analysis.model is set
    config:thumbnail_direction_model_matches_analysis
    config:autonomy_manual
    automation:model_matches_orchestrator      automation.toml model == .codex/config.toml model
    automation:prompt_names_production_model   prompt names analysis.model or defers to live config
    automation:prompt_no_stale_sol             no GPT-5.6 Sol prescription when the model differs
    automation:prompt_no_astra_fallback        no "No automatic Claude or Astra fallback" while Astra orchestrates
    recovery:ids_unique_stable
    recovery:source_paths_exist
    recovery:source_line_bounds                source line numbers are one-based and inside the file
    recovery:verified_complete_receipt         "Verified complete" items carry a verification receipt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older interpreters
    tomllib = None

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - PyYAML is a project dependency
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_BOARD = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "ChatGPT"
    / "New project"
    / "conversation-recovery"
    / "items.json"
)

REQUIRED_FILES = (
    "AGENTS.md",
    "STATE.md",
    "docs/SOL-PRODUCTION-CONTRACT.md",
    "docs/SOL-CLOSEOUT-QUEUE.md",
    "bench/bench.json",
    "src/boydclips/stage_context.py",
    "docs/PIPELINE-ARCHITECTURE-AND-LEARNING-LAYER.md",
    ".codex/config.toml",
)

# The prose that must not contradict the bench on disk. These are the current
# contract documents, not dated archives.
CONTRACT_DOCS = (
    "docs/SOL-PRODUCTION-CONTRACT.md",
    "docs/PIPELINE-ARCHITECTURE-AND-LEARNING-LAYER.md",
)
FALSE_BENCH_CLAIM = "no bench exists yet"

# (root, relative path). "codex_home" = --codex-home, "codex_agents" = its
# sibling ~/.agents, where the Boyd thumbnail skill is installed.
GLOBAL_SKILLS = (
    ("codex_home", "skills/astra-deepseek-workers/SKILL.md"),
    ("codex_home", "skills/conversation-recovery/SKILL.md"),
    ("codex_home", "skills/courtroom-thumbnail-director/SKILL.md"),
    ("codex_agents", "skills/boyd-thumbnail/SKILL.md"),
)

AUTOMATION_REL = "automations/boyd-daily-production/automation.toml"
ORCHESTRATION_REL = ".codex/config.toml"

MODEL_TOKEN_RE = re.compile(
    r"gpt-[0-9][\w.\-]*|deepseek[\w.\-]*|claude[\w.\-]*|gemini[\w.\-]*|\bsol\b", re.I
)
DEFERRAL_RE = re.compile(
    r"analysis\.model"
    r"|configured (analysis|production) model"
    r"|production model from the (live )?config"
    r"|live (production )?config(uration)?"
    r"|from (the )?(live )?config",
    re.I,
)
STALE_SOL_RE = re.compile(
    r"(?:using|requires?|use)\s+(?:gpt[\s\-]*5\.6[\s\-]*)?sol\b"
    r"|\b\d+\s+(?:gpt[\s\-]*5\.6[\s\-]*)?sol\s+calls\b", re.I)
ASTRA_FALLBACK_RE = re.compile(r"no automatic claude or astra fallback", re.I)
CLARIFY_RE = re.compile(r"orchestrat|supervisor|primary (model|brain|agent)", re.I)

ID_RE = re.compile(r"^R\d{2,}$")
RECEIPT_KEYS = (
    "verification",
    "verification_receipt",
    "verification_receipts",
    "receipt",
    "receipts",
    "verified_by",
)
RECEIPT_SOURCE_RE = re.compile(r"receipt|verification", re.I)


def _read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _load_json(path: Path):
    text, err = _read_text(path)
    if text is None:
        return None, err
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def _load_yaml(path: Path):
    if yaml is None:
        return None, "PyYAML unavailable"
    text, err = _read_text(path)
    if text is None:
        return None, err
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {exc}"
    if not isinstance(data, dict):
        return None, "YAML root is not a mapping"
    return data, None


def _load_toml(path: Path):
    if tomllib is None:
        return None, "tomllib unavailable"
    text, err = _read_text(path)
    if text is None:
        return None, err
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return None, f"invalid TOML: {exc}"
    if not isinstance(data, dict):
        return None, "TOML root is not a table"
    return data, None


def _clip(value, limit: int = 300) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _dig(data, *path: str) -> str:
    node = data
    for key in path:
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    return "" if node is None else str(node).strip()


def _summ(values, limit: int = 5) -> str:
    values = list(values)
    if not values:
        return "none"
    shown = ", ".join(_clip(v, 80) for v in values[:limit])
    if len(values) > limit:
        shown += f" (+{len(values) - limit} more)"
    return shown


def _sentences(text: str):
    return [part for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _sentence_window(text: str, index: int) -> str:
    sentences = _sentences(text)
    for position, sentence in enumerate(sentences):
        start = text.find(sentence)
        if start <= index < start + len(sentence):
            return " ".join(sentences[max(0, position - 1) : position + 2])
    return text


def _sentence_at(text: str, index: int) -> str:
    for sentence in _sentences(text):
        start = text.find(sentence)
        if start <= index < start + len(sentence):
            return sentence
    return text


def _foreign_model_tokens(prompt: str, allowed: set[str]):
    found = []
    for match in MODEL_TOKEN_RE.finditer(prompt):
        token = match.group(0).strip().lower()
        if token in allowed:
            continue
        if token not in found:
            found.append(token)
    return found


def run_checks(repo=ROOT, codex_home=None, board=None):
    """Return a list of check dicts. Read-only; no network, no model calls."""
    repo = Path(repo)
    codex_home = Path(codex_home) if codex_home is not None else DEFAULT_CODEX_HOME
    agents_home = codex_home.parent / ".agents"
    board_path = Path(board) if board is not None else DEFAULT_BOARD
    checks: list[dict] = []

    def add(name: str, ok: bool, observed, expected) -> None:
        checks.append(
            {"check": name, "ok": bool(ok), "observed": _clip(observed), "expected": _clip(expected)}
        )

    # ---- required files -------------------------------------------------
    for rel in REQUIRED_FILES:
        path = repo / rel
        add(f"file:{rel}", path.is_file(), f"{'exists' if path.is_file() else 'MISSING'} {path}", "file present")
    add(
        "file:recovery_board",
        board_path.is_file(),
        f"{'exists' if board_path.is_file() else 'MISSING'} {board_path}",
        "file present",
    )
    for root_key, rel in GLOBAL_SKILLS:
        root = codex_home if root_key == "codex_home" else agents_home
        path = root / rel
        add(
            f"file:{root_key}/{rel}",
            path.is_file(),
            f"{'exists' if path.is_file() else 'MISSING'} {path}",
            "global skill file present",
        )

    # ---- bench ----------------------------------------------------------
    bench, bench_err = _load_json(repo / "bench" / "bench.json")
    cases = bench.get("cases") if isinstance(bench, dict) else None
    case_count = len(cases) if isinstance(cases, list) else 0
    add(
        "bench:cases_nonempty",
        case_count > 0,
        f"cases={case_count}" + (f" ({bench_err})" if bench_err else ""),
        "at least one case",
    )

    # ---- contract does not contradict the bench -------------------------
    hits = []
    scanned = 0
    for rel in CONTRACT_DOCS:
        path = repo / rel
        text, _ = _read_text(path)
        if text is None:
            continue
        scanned += 1
        if FALSE_BENCH_CLAIM in text.lower():
            hits.append(rel)
    add(
        "contract:no_false_bench_claim",
        not hits,
        f"scanned={scanned} files; claim '{FALSE_BENCH_CLAIM}' in {_summ(hits)}",
        "claim absent",
    )

    # ---- live configuration ---------------------------------------------
    pipeline, pipeline_err = _load_yaml(repo / "config" / "pipeline.yaml")
    pipeline = pipeline if isinstance(pipeline, dict) else {}
    analysis_model = _dig(pipeline, "analysis", "model")
    thumbnail_model = _dig(pipeline, "packaging", "thumbnail", "direct", "model")
    autonomy_mode = _dig(pipeline, "autonomy", "mode")
    add(
        "config:analysis_model_present",
        bool(analysis_model),
        f"analysis.model={analysis_model or 'MISSING'}" + (f" ({pipeline_err})" if pipeline_err else ""),
        "analysis.model set in config/pipeline.yaml",
    )
    add(
        "config:thumbnail_direction_model_matches_analysis",
        bool(analysis_model) and thumbnail_model == analysis_model,
        f"packaging.thumbnail.direct.model={thumbnail_model or 'MISSING'} analysis.model={analysis_model or 'MISSING'}",
        "thumbnail direction model equals analysis model",
    )
    add(
        "config:autonomy_manual",
        autonomy_mode == "manual",
        f"autonomy.mode={autonomy_mode or 'MISSING'}",
        "manual",
    )

    orchestration, orchestration_err = _load_toml(repo / ORCHESTRATION_REL)
    orchestration_source = str(repo / ORCHESTRATION_REL)
    if orchestration is None:
        orchestration, orchestration_err = _load_toml(codex_home / "config.toml")
        orchestration_source = str(codex_home / "config.toml")
    orchestration = orchestration if isinstance(orchestration, dict) else {}
    orchestrator_model = _dig(orchestration, "model")
    add(
        "config:orchestration_model_present",
        bool(orchestrator_model),
        f"model={orchestrator_model or 'MISSING'} from {orchestration_source}"
        + (f" ({orchestration_err})" if orchestration_err else ""),
        "orchestration model set",
    )

    automation, automation_err = _load_toml(codex_home / AUTOMATION_REL)
    automation = automation if isinstance(automation, dict) else {}
    automation_model = _dig(automation, "model")
    prompt = str(automation.get("prompt", ""))
    automation_status = _dig(automation, "status")
    add(
        "automation:model_matches_orchestrator",
        bool(automation_model) and automation_model == orchestrator_model,
        f"automation model={automation_model or 'MISSING'} (status={automation_status or 'MISSING'}) "
        f"orchestration model={orchestrator_model or 'MISSING'}"
        + (f" ({automation_err})" if automation_err else ""),
        "equal models",
    )

    allowed_models = {m.lower() for m in (analysis_model, orchestrator_model) if m}
    foreign = _foreign_model_tokens(prompt, allowed_models) if prompt else []
    names_model = bool(analysis_model) and analysis_model.lower() in prompt.lower()
    defers = bool(DEFERRAL_RE.search(prompt)) if prompt else False
    add(
        "automation:prompt_names_production_model",
        bool(prompt) and (names_model or defers),
        f"names analysis.model={names_model} defers_to_live_config={defers}",
        "prompt names the configured analysis.model or defers to it; stale prescriptions checked separately",
    )

    stale_sol = STALE_SOL_RE.search(prompt) if prompt else None
    stale_sol_hit = None
    if stale_sol and analysis_model and analysis_model.lower() != "gpt-5.6-sol":
        stale_sol_hit = _sentence_at(prompt, stale_sol.start())
    add(
        "automation:prompt_no_stale_sol",
        stale_sol_hit is None,
        f"analysis.model={analysis_model or 'MISSING'}; stale Sol text: {stale_sol_hit or 'none'}",
        "no GPT-5.6 Sol prescription while a different model is configured",
    )

    astra_fallback = ASTRA_FALLBACK_RE.search(prompt) if prompt else None
    astra_fallback_hit = None
    if astra_fallback and "astra" in orchestrator_model.lower():
        window = _sentence_window(prompt, astra_fallback.start())
        if not CLARIFY_RE.search(window):
            astra_fallback_hit = _clip(window, 200)
    add(
        "automation:prompt_no_astra_fallback",
        astra_fallback_hit is None,
        f"orchestration model={orchestrator_model or 'MISSING'}; unclarified fallback text: "
        f"{astra_fallback_hit or 'none'}",
        "no Astra-fallback ban while Astra orchestrates (or wording that clarifies it)",
    )

    # ---- recovery board --------------------------------------------------
    board_data, board_err = _load_json(board_path)
    runtime = board_data.get("runtime", {}) if isinstance(board_data, dict) else {}
    if runtime:
        add("recovery:confirmed_model_selection",
            runtime.get("production_model") == analysis_model
            and runtime.get("orchestrator_model") == orchestrator_model,
            f"confirmed={runtime.get('production_model')}; configured={analysis_model}; orchestrator={orchestrator_model}",
            "configuration matches the recorded user selection")
    items = board_data.get("items") if isinstance(board_data, dict) else None
    items = items if isinstance(items, list) else []

    ids = [str(item.get("id", "")).strip() for item in items if isinstance(item, dict)]
    duplicates = sorted({i for i in ids if i and ids.count(i) > 1})
    malformed = sorted({i for i in ids if not ID_RE.match(i)})
    add(
        "recovery:ids_unique_stable",
        bool(items) and len(ids) == len(items) and not duplicates and not malformed and all(i for i in ids),
        f"items={len(items)} unique_ids={len(set(ids))} duplicates={_summ(duplicates)} "
        f"malformed={_summ(malformed)}" + (f" ({board_err})" if board_err else ""),
        "every item has one unique, stable, non-empty ID",
    )

    missing_paths = []
    items_without_sources = []
    line_violations = []
    line_counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "?"))
        sources = item.get("sources")
        sources = sources if isinstance(sources, list) else []
        if not sources:
            items_without_sources.append(item_id)
        for source in sources:
            if not isinstance(source, dict):
                missing_paths.append(f"{item_id}: <non-object source>")
                continue
            raw = str(source.get("path", "")).strip()
            if not raw:
                missing_paths.append(f"{item_id}: <empty path>")
                continue
            path = Path(raw)
            if not path.is_absolute():
                path = repo / path
            if not path.is_file():
                missing_paths.append(f"{item_id}: {path.name} ({path})")
                continue
            key = str(path)
            if key not in line_counts:
                text, err = _read_text(path)
                line_counts[key] = -1 if text is None else len(text.splitlines())
            total = line_counts[key]
            for field, label in (("line", "line"), ("line_end", "line_end")):
                if field not in source:
                    continue
                value = source.get(field)
                try:
                    if type(value) is not int:
                        raise ValueError("line must be an integer")
                    number = value
                except (TypeError, ValueError):
                    line_violations.append(f"{item_id}: {label}={value!r} not an integer")
                    continue
                if number < 1 or total < number:
                    line_violations.append(f"{item_id}: {label}={number} outside 1..{total} in {path.name}")
            start, end = source.get("line"), source.get("line_end")
            try:
                if start is not None and end is not None and int(end) < int(start):
                    line_violations.append(f"{item_id}: line_end={end} < line={start}")
            except (TypeError, ValueError):
                pass

    add(
        "recovery:source_paths_exist",
        not missing_paths and not items_without_sources,
        f"items={len(items)} missing_paths={_summ(missing_paths)} "
        f"items_without_sources={_summ(items_without_sources)}"
        + (f" ({board_err})" if board_err else ""),
        "every item has at least one source and every source path exists",
    )
    add(
        "recovery:source_line_bounds",
        not line_violations,
        f"violations={_summ(line_violations)}",
        "source line numbers are one-based and inside the referenced file",
    )

    no_receipt = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", ""))
        if "verified complete" not in status.lower():
            continue
        item_id = str(item.get("id", "?"))
        receipts = item.get("verification_receipts")
        valid = isinstance(receipts, list) and bool(receipts)
        for receipt in receipts if valid else []:
            if not isinstance(receipt, dict) or not str(receipt.get("outcome", "")).strip():
                valid = False
                break
            paths = receipt.get("evidence")
            paths = [paths] if isinstance(paths, str) else paths
            if not isinstance(paths, list) or not paths:
                valid = False
                break
            for raw in paths:
                if not isinstance(raw, str) or not raw.strip():
                    valid = False
                    break
                target = Path(raw)
                if not target.is_absolute():
                    target = board_path.parent / target
                valid = valid and target.is_file()
        if not valid:
            no_receipt.append(item_id)
    add(
        "recovery:verified_complete_receipt",
        not no_receipt,
        f"verified-complete items without receipt={_summ(no_receipt)}"
        + (f" ({board_err})" if board_err else ""),
        "every 'Verified complete' item carries a verification receipt",
    )

    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only structural checker for the recovery board.")
    parser.add_argument("--repo", default=str(ROOT), help="repository root (default: this repo)")
    parser.add_argument("--codex-home", default=str(DEFAULT_CODEX_HOME), help="Codex home directory")
    parser.add_argument("--board", default=str(DEFAULT_BOARD), help="canonical recovery items.json")
    parser.add_argument("--json", action="store_true", help="print a machine-readable result")
    args = parser.parse_args(argv)

    try:
        checks = run_checks(repo=Path(args.repo), codex_home=Path(args.codex_home), board=Path(args.board))
    except Exception as exc:  # pragma: no cover - defensive: never a silent pass
        print(f"CHECKER_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    passed = sum(1 for check in checks if check["ok"])
    ok = passed == len(checks)
    if args.json:
        print(json.dumps({"ok": ok, "passed": passed, "total": len(checks), "checks": checks}, indent=2))
    else:
        for check in checks:
            print(
                f"{'PASS' if check['ok'] else 'FAIL'}  {check['check']}  "
                f"observed={check['observed']}  expected={check['expected']}"
            )
        print(f"\n{passed}/{len(checks)} checks passed")
        print("RECOVERY_STRUCTURE_OK" if ok else "RECOVERY_STRUCTURE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
