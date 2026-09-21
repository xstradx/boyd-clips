# -*- coding: utf-8 -*-
"""Focused controls for tools/check_recovery_structure.py.

The checker is read-only, so every test builds a throwaway project tree under
tmp_path and proves the checker can FAIL as well as pass: a mismatched
automation model, a stale Sol prompt, a missing required file, board sources
that do not exist, an item with no source, a duplicate ID, an out-of-bounds
line number, a false "no bench" claim and a "Verified complete" item with no
verification receipt. No model calls, no network, no writes outside tmp_path.

Run: python -m pytest tests/test_recovery_structure.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_recovery_structure.py"
sys.path.insert(0, str(ROOT / "tools"))
import check_recovery_structure as cr  # noqa: E402

PIPELINE_YAML = """\
autonomy:
  mode: manual

analysis:
  model: "deepseek-flash"

packaging:
  thumbnail:
    mode: legacy
    direct:
      model: deepseek-flash
"""

CLEAN_PROMPT = (
    "Run Boyd Clips production using the analysis.model from the live production "
    "configuration. Keep autonomy.mode=manual and do not publish."
)

AUTOMATION_TOML = """\
version = 1
id = "boyd-daily-production"
kind = "cron"
name = "Boyd Daily Production"
status = "ACTIVE"
model = "{model}"
prompt = "{prompt}"
"""

SKILL_PATHS = (
    "skills/astra-deepseek-workers/SKILL.md",
    "skills/conversation-recovery/SKILL.md",
    "skills/courtroom-thumbnail-director/SKILL.md",
)


@dataclass
class Fixture:
    repo: Path
    home: Path
    codex_home: Path
    board: Path


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _item(item_id: str, *, status: str = "Unfinished", sources=None, **extra):
    item = {
        "id": item_id,
        "priority": "P0",
        "project": "Boyd / continuity",
        "status": status,
        "title": "title",
        "intent": "intent",
        "evidence": "evidence",
        "next_action": "next",
        "acceptance": "acceptance",
        "sources": [] if sources is None else sources,
        "authority": "read-only sweep",
        "checked_date": "2026-09-19 America/Chicago",
    }
    item.update(extra)
    return item


def _source(fixture: Fixture, rel: str, line=None, label: str = "source"):
    source = {"label": label, "path": str(fixture.repo / rel)}
    if line is not None:
        source["line"] = line
    return source


def _write_board(fixture: Fixture, items) -> None:
    _write(
        fixture.board,
        json.dumps({"version": 1, "scope": "test fixture", "items": items}, indent=2),
    )


def _rewrite_automation(fixture: Fixture, *, model: str, prompt: str) -> None:
    _write(
        fixture.codex_home / "automations" / "boyd-daily-production" / "automation.toml",
        AUTOMATION_TOML.format(model=model, prompt=prompt),
    )


def _build(tmp_path: Path) -> Fixture:
    """A minimal tree that satisfies every check, except where a test breaks it."""
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    codex_home = home / ".codex"
    board = tmp_path / "conversation-recovery" / "items.json"
    fixture = Fixture(repo=repo, home=home, codex_home=codex_home, board=board)

    _write(repo / "AGENTS.md", "# AGENTS\n")
    _write(repo / "STATE.md", "# STATE\n\n## 2026-09-19\nRecovery sweep recorded.\n")
    _write(
        repo / "docs" / "SOL-PRODUCTION-CONTRACT.md",
        "# Production contract\n\nThe bench is recorded in bench/bench.json.\n",
    )
    _write(repo / "docs" / "SOL-CLOSEOUT-QUEUE.md", "# Closeout queue\n\nP0: none.\n")
    _write(
        repo / "docs" / "PIPELINE-ARCHITECTURE-AND-LEARNING-LAYER.md",
        "# Architecture\n\nThe bench exists in bench/bench.json.\n",
    )
    _write(
        repo / "bench" / "bench.json",
        json.dumps(
            {
                "version": 1,
                "cases": [{"dir": "case-a", "manifest": "out/review/case-a/manifest.json"}],
            }
        ),
    )
    _write(repo / "src" / "boydclips" / "stage_context.py", "def rules():\n    return []\n")
    _write(repo / "config" / "pipeline.yaml", PIPELINE_YAML)
    _write(repo / ".codex" / "config.toml", 'model = "gpt-6-astra"\n')
    _rewrite_automation(fixture, model="gpt-6-astra", prompt=CLEAN_PROMPT)
    for rel in SKILL_PATHS:
        _write(codex_home / rel, "# skill\n")
    _write(home / ".agents" / "skills" / "boyd-thumbnail" / "SKILL.md", "# boyd-thumbnail\n")

    _write_board(
        fixture,
        [
            _item("R01", sources=[_source(fixture, "STATE.md", line=1)]),
            _item(
                "R02",
                sources=[_source(fixture, "AGENTS.md", line=1, label="recovery board receipt")],
            ),
        ],
    )
    return fixture


def _checks(fixture: Fixture):
    return cr.run_checks(repo=fixture.repo, codex_home=fixture.codex_home, board=fixture.board)


def _check(checks, name: str):
    for check in checks:
        if check["check"] == name:
            return check
    raise AssertionError(f"checker never reported {name!r}")


def _failed(checks):
    return [check["check"] for check in checks if not check["ok"]]


def _cli(fixture: Fixture, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--repo",
            str(fixture.repo),
            "--codex-home",
            str(fixture.codex_home),
            "--board",
            str(fixture.board),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _tree_bytes(root: Path):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_positive_fixture_all_checks_pass(tmp_path):
    fixture = _build(tmp_path)
    checks = _checks(fixture)
    assert checks
    assert _failed(checks) == []
    assert all(check["observed"].strip() for check in checks)
    assert _check(checks, "automation:model_matches_orchestrator")["ok"]
    assert _check(checks, "recovery:verified_complete_receipt")["ok"]


def test_cli_json_positive_and_nonzero_on_regression(tmp_path):
    fixture = _build(tmp_path)
    ok = _cli(fixture, "--json")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    payload = json.loads(ok.stdout)
    assert payload["ok"] is True
    assert payload["passed"] == payload["total"] == len(payload["checks"])
    assert all(check["observed"].strip() for check in payload["checks"])

    _rewrite_automation(fixture, model="gpt-5.6-sol", prompt=CLEAN_PROMPT)
    bad = _cli(fixture, "--json")
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["ok"] is False


def test_checker_is_read_only(tmp_path):
    fixture = _build(tmp_path)
    before = {
        "repo": _tree_bytes(fixture.repo),
        "home": _tree_bytes(fixture.home),
        "board": fixture.board.read_bytes(),
    }
    _checks(fixture)
    _cli(fixture, "--json")
    assert _tree_bytes(fixture.repo) == before["repo"]
    assert _tree_bytes(fixture.home) == before["home"]
    assert fixture.board.read_bytes() == before["board"]


def test_wrong_automation_model_fails(tmp_path):
    fixture = _build(tmp_path)
    _rewrite_automation(fixture, model="gpt-5.6-sol", prompt=CLEAN_PROMPT)
    checks = _checks(fixture)
    assert _failed(checks) == ["automation:model_matches_orchestrator"]
    assert _check(checks, "automation:model_matches_orchestrator")["observed"].find("gpt-5.6-sol") >= 0
    assert _cli(fixture).returncode == 1


def test_stale_sol_prompt_fails_when_configured_model_differs(tmp_path):
    fixture = _build(tmp_path)
    _rewrite_automation(
        fixture,
        model="gpt-6-astra",
        prompt="Run Boyd Clips production using GPT-5.6 Sol. No automatic Claude or Astra fallback.",
    )
    checks = _checks(fixture)
    assert _check(checks, "automation:prompt_no_stale_sol")["ok"] is False
    assert _check(checks, "automation:prompt_names_production_model")["ok"] is False
    assert _check(checks, "automation:prompt_no_astra_fallback")["ok"] is False

    # The same prompt is not stale when the configured model really is Sol.
    pipeline = (fixture.repo / "config" / "pipeline.yaml").read_text(encoding="utf-8")
    _write(
        fixture.repo / "config" / "pipeline.yaml",
        pipeline.replace('model: "deepseek-flash"', 'model: "gpt-5.6-sol"'),
    )
    refreshed = _checks(fixture)
    assert _check(refreshed, "automation:prompt_no_stale_sol")["ok"] is True
    assert _check(refreshed, "config:thumbnail_direction_model_matches_analysis")["ok"] is False


def test_astra_fallback_clarified_wording_passes(tmp_path):
    fixture = _build(tmp_path)
    _rewrite_automation(
        fixture,
        model="gpt-6-astra",
        prompt=(
            "Astra orchestrates this run as the primary model. "
            "No automatic Claude or Astra fallback for the analysis call."
        ),
    )
    checks = _checks(fixture)
    assert _check(checks, "automation:prompt_no_astra_fallback")["ok"] is True


def test_missing_required_file_fails(tmp_path):
    fixture = _build(tmp_path)
    (fixture.repo / "bench" / "bench.json").unlink()
    checks = _checks(fixture)
    assert _check(checks, "file:bench/bench.json")["ok"] is False
    assert "MISSING" in _check(checks, "file:bench/bench.json")["observed"]
    assert _check(checks, "bench:cases_nonempty")["ok"] is False
    assert _cli(fixture).returncode == 1


def test_missing_source_path_fails(tmp_path):
    fixture = _build(tmp_path)
    _write_board(
        fixture,
        [_item("R01", sources=[_source(fixture, "STATE.md", line=1)])],
    )
    board = json.loads(fixture.board.read_text(encoding="utf-8"))
    board["items"][0]["sources"].append({"label": "gone", "path": str(tmp_path / "nope.md")})
    _write(fixture.board, json.dumps(board, indent=2))
    checks = _checks(fixture)
    assert _check(checks, "recovery:source_paths_exist")["ok"] is False
    assert "nope.md" in _check(checks, "recovery:source_paths_exist")["observed"]


def test_item_without_sources_fails(tmp_path):
    fixture = _build(tmp_path)
    _write_board(fixture, [_item("R01", sources=[])])
    checks = _checks(fixture)
    assert _check(checks, "recovery:source_paths_exist")["ok"] is False
    assert "R01" in _check(checks, "recovery:source_paths_exist")["observed"]


def test_duplicate_id_fails(tmp_path):
    fixture = _build(tmp_path)
    _write_board(
        fixture,
        [
            _item("R01", sources=[_source(fixture, "STATE.md", line=1)]),
            _item("R01", sources=[_source(fixture, "AGENTS.md", line=1)]),
        ],
    )
    checks = _checks(fixture)
    assert _check(checks, "recovery:ids_unique_stable")["ok"] is False
    assert "R01" in _check(checks, "recovery:ids_unique_stable")["observed"]


def test_source_line_bounds_are_one_based_and_inside_the_file(tmp_path):
    fixture = _build(tmp_path)
    _write_board(
        fixture,
        [
            _item("R01", sources=[_source(fixture, "STATE.md", line=0)]),
            _item("R02", sources=[_source(fixture, "STATE.md", line=9999)]),
        ],
    )
    checks = _checks(fixture)
    check = _check(checks, "recovery:source_line_bounds")
    assert check["ok"] is False
    assert "R01" in check["observed"] and "R02" in check["observed"]

    _write_board(fixture, [_item("R01", sources=[_source(fixture, "STATE.md", line=1)])])
    assert _check(_checks(fixture), "recovery:source_line_bounds")["ok"] is True


def test_contract_false_bench_claim_fails(tmp_path):
    fixture = _build(tmp_path)
    _write(
        fixture.repo / "docs" / "SOL-PRODUCTION-CONTRACT.md",
        "# Production contract\n\nNo bench exists yet, so nothing is measured.\n",
    )
    checks = _checks(fixture)
    assert _check(checks, "contract:no_false_bench_claim")["ok"] is False
    assert "SOL-PRODUCTION-CONTRACT.md" in _check(checks, "contract:no_false_bench_claim")["observed"]


def test_verified_complete_requires_receipt(tmp_path):
    fixture = _build(tmp_path)
    _write_board(
        fixture,
        [_item("R01", status="Verified complete", sources=[_source(fixture, "STATE.md", line=1)])],
    )
    checks = _checks(fixture)
    assert _check(checks, "recovery:verified_complete_receipt")["ok"] is False
    assert "R01" in _check(checks, "recovery:verified_complete_receipt")["observed"]

    _write_board(
        fixture,
        [
            _item(
                "R01",
                status="Verified complete",
                verification_receipts=[{"evidence": str(fixture.repo / "STATE.md"), "outcome": "Fixture state was inspected."}],
                sources=[_source(fixture, "STATE.md", line=1)],
            )
        ],
    )
    assert _check(_checks(fixture), "recovery:verified_complete_receipt")["ok"] is True


def test_historical_filenames_and_distinct_worker_models_are_not_production_drift(tmp_path):
    fixture = _build(tmp_path)
    _rewrite_automation(fixture, model="gpt-6-astra", prompt=(
        "GPT-6 Astra orchestrates; DeepSeek workers implement. Use deepseek-flash for production. "
        "Read docs/SOL-PRODUCTION-CONTRACT.md. Never substitute Sol or Claude for the configured production model."
    ))
    assert not _failed(_checks(fixture))


def test_empty_or_missing_receipt_evidence_cannot_certify_completion(tmp_path):
    fixture = _build(tmp_path)
    for receipt in ([], [{"outcome": "passed", "evidence": str(tmp_path / "missing.json")} ]):
        _write_board(fixture, [_item("R01", status="Verified complete", verification_receipts=receipt,
                                    sources=[_source(fixture, "STATE.md")])])
        assert not _check(_checks(fixture), "recovery:verified_complete_receipt")["ok"]


def test_live_model_change_cannot_override_recorded_user_selection(tmp_path):
    fixture = _build(tmp_path)
    data = json.loads(fixture.board.read_text(encoding="utf-8"))
    data["runtime"] = {"production_model": "deepseek-flash", "orchestrator_model": "gpt-6-astra"}
    _write(fixture.board, json.dumps(data))
    assert _check(_checks(fixture), "recovery:confirmed_model_selection")["ok"]
    _write(fixture.repo / "config/pipeline.yaml", PIPELINE_YAML.replace("deepseek-flash", "gpt-5.6-sol"))
    assert not _check(_checks(fixture), "recovery:confirmed_model_selection")["ok"]


def test_registry_counts_shell_execution_but_not_comments_or_echo(tmp_path, monkeypatch):
    import check_registry
    monkeypatch.setattr(check_registry, "ROOT", str(tmp_path))
    monkeypatch.setattr(check_registry, "SEARCH_DIRS", ("tools",))
    monkeypatch.setattr(check_registry, "find_checks", lambda: {"check_sample": "tools/check_sample.py"})
    runner = tmp_path / "run_daily.ps1"
    for text in ("# python tools/check_sample.py\n", "<#\npython tools/check_sample.py\n#>\n",
                 'Write-Output "python tools/check_sample.py"\n'):
        _write(runner, text)
        assert check_registry.audit() == 1
    _write(runner, "python tools/check_sample.py 2>&1 | Tee-Object -FilePath $Log -Append\n")
    assert check_registry.audit() == 0
