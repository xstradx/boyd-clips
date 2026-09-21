import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from boydclips import cli, llm
from boydclips.config import load_config


SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _backend(monkeypatch, **kwargs):
    monkeypatch.setattr(llm.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    return llm.CodexCliBackend("gpt-5.6-sol", timeout_s=12, **kwargs)


def _successful_run(captured, answer="ok"):
    def run(command, **kwargs):
        captured.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(json.dumps({"answer": answer}), encoding="utf-8")
        stdout = json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        })
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
    return run


def test_codex_backend_success_is_explicit_and_isolated(monkeypatch):
    calls = []
    monkeypatch.setattr(llm.subprocess, "run", _successful_run(calls))

    result = _backend(monkeypatch).complete("SYSTEM", "USER", SCHEMA, "score")

    assert result == {"answer": "ok"}
    assert len(calls) == 1
    command, kwargs = calls[0]
    # argv[0] is the resolved absolute path (the CLI is a .CMD shim on
    # Windows, and a bare name does not resolve there).
    assert command[1] == "exec"
    assert str(command[0]).replace("\\", "/").lower().endswith(("codex", "codex.cmd", "codex.exe"))
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert command[command.index("--sandbox") + 1] == "read-only"
    configs = {command[i + 1] for i, value in enumerate(command) if value == "--config"}
    assert configs == {
        'model_reasoning_effort="medium"', 'web_search="disabled"', 'approval_policy="never"',
    }
    assert {command[i + 1] for i, value in enumerate(command) if value == "--disable"} == {
        "shell_tool", "unified_exec", "multi_agent", "image_generation",
        "apps", "plugins", "computer_use", "view_image",
    }
    for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral",
                 "--skip-git-repo-check", "--output-schema", "--json"):
        assert flag in command
    assert command[-1] == "-"
    assert Path(kwargs["cwd"]) == Path(command[command.index("--cd") + 1])
    assert "SYSTEM" in kwargs["input"] and "USER" in kwargs["input"]
    assert "Do not call tools" in kwargs["input"]
    assert "claude" not in command


def test_codex_backend_timeout(monkeypatch):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(llm.subprocess, "run", timeout)
    with pytest.raises(llm.BackendError, match="timed out after 12s"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "segment")


def test_codex_backend_nonzero_exit(monkeypatch):
    monkeypatch.setattr(llm.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 7, stdout="", stderr="bad invocation"))
    with pytest.raises(llm.BackendError, match="exited 7: bad invocation"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "segment")


def test_codex_backend_start_error(monkeypatch):
    monkeypatch.setattr(llm.subprocess, "run", lambda command, **kwargs: (_ for _ in ()).throw(
        OSError("executable unavailable")
    ))
    with pytest.raises(llm.BackendError, match="could not start codex CLI"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "segment")


def test_codex_backend_refusal_event(monkeypatch):
    event = json.dumps({"type": "turn.failed", "error": {"message": "model refusal"}})
    monkeypatch.setattr(llm.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 1, stdout=event, stderr=""))
    with pytest.raises(llm.RefusalError, match="declined"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "segment")


def test_codex_backend_rejects_tool_event(monkeypatch):
    def run(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"answer":"must not be accepted"}', encoding="utf-8")
        event = json.dumps({"type": "item.completed", "item": {"type": "command_execution"}})
        return subprocess.CompletedProcess(command, 0, stdout=event, stderr="")

    monkeypatch.setattr(llm.subprocess, "run", run)
    with pytest.raises(llm.BackendError, match="forbidden tool event"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "segment")


def test_codex_backend_accepts_local_diagnostic_item_when_turn_succeeds(monkeypatch):
    def run(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"answer":"ok"}', encoding="utf-8")
        events = "\n".join((
            json.dumps({
                "type": "item.completed",
                "item": {"type": "error", "message": "clamping SessionEnd hook timeout to 3s"},
            }),
            json.dumps({"type": "turn.completed", "usage": {}}),
        ))
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr="")

    monkeypatch.setattr(llm.subprocess, "run", run)
    assert _backend(monkeypatch).complete("system", "user", SCHEMA, "segment") == {"answer": "ok"}


def test_codex_backend_requires_final_response_file(monkeypatch):
    monkeypatch.setattr(llm.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, stdout="", stderr=""))
    with pytest.raises(llm.BackendError, match="no final response file"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "segment")


def test_codex_backend_invalid_schema_does_not_retry_or_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(llm.subprocess, "run", _successful_run(calls, answer=3))
    with pytest.raises(llm.BackendError, match=r"failed after 1 attempt\(s\).+expected string"):
        _backend(monkeypatch).complete("system", "user", SCHEMA, "score")
    assert len(calls) == 1
    assert calls[0][0][1] == "exec"


class _Cfg:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def require(self, key):
        return self.values[key]


def test_backend_routing_requires_explicit_legacy_selection(monkeypatch):
    monkeypatch.setattr(llm.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    default = llm.build_backend(_Cfg({"analysis.model": "gpt-5.6-sol"}))
    legacy = llm.build_backend(_Cfg({
        "analysis.backend": "claude_cli", "analysis.model": "claude-opus-5",
    }))
    assert isinstance(default, llm.CodexCliBackend)
    assert isinstance(legacy, llm.ClaudeCliBackend)
    assert default.model == "gpt-5.6-sol"
    assert legacy.model == "claude-opus-5"


def test_production_config_explicitly_pins_the_brain_route():
    """The brain is named in config; no stage picks a model by itself.

    2026-09-19: the pinned route is DeepSeek V4.1 Flash through its stable API
    name, deepseek-flash. The intent of this check is unchanged: whichever
    model is in force is stated here, with a complete provider definition when
    it is not the default provider answering, and the run never retries a
    refused paid call or silently falls back.
    """
    cfg = load_config()
    assert cfg.require("analysis.backend") == "codex_cli"
    assert cfg.require("analysis.effort") in {"low", "high", "max"}
    assert cfg.require("analysis.cli_attempts") == 1
    model = cfg.require("analysis.model")
    assert isinstance(model, str) and model.strip()
    provider = cfg.get("analysis.provider")
    if provider:
        # A provider is only usable if it is complete: without env_key the
        # isolated CLI session has no credential and the first call fails.
        assert provider.get("name")
        assert provider.get("base_url")
        assert provider.get("env_key")
    # 2026-09-16: the Short-thumbnail direction model follows the production
    # brain. It stays a pinned config value — no stage picks a model at runtime.
    assert cfg.require("packaging.thumbnail.direct.model") == model
    assert cfg.require("packaging.thumbnail.direct.effort") in {"low", "high", "max"}
    assert cfg.require("packaging.thumbnail.mode") in {"direct_gen", "legacy"}


def test_codex_backend_passes_provider_flags_when_configured(monkeypatch):
    """A configured provider reaches the isolated CLI session explicitly."""
    monkeypatch.setenv("BOYD_TEST_PROVIDER_KEY", "not-a-real-key")
    calls = []
    monkeypatch.setattr(llm.subprocess, "run", _successful_run(calls))
    backend = _backend(monkeypatch, provider={
        "name": "deepseek",
        "base_url": "https://api.deepseek.com/",
        "wire_api": "responses",
        "env_key": "BOYD_TEST_PROVIDER_KEY",
    })

    assert backend.complete("SYSTEM", "USER", SCHEMA, "score") == {"answer": "ok"}

    command = calls[0][0]
    configs = {command[i + 1] for i, value in enumerate(command) if value == "--config"}
    assert 'model_provider="deepseek"' in configs
    assert 'model_providers.deepseek.base_url="https://api.deepseek.com/"' in configs
    assert 'model_providers.deepseek.env_key="BOYD_TEST_PROVIDER_KEY"' in configs
    # The key itself must never be an argv entry.
    assert not any("not-a-real-key" in str(part) for part in command)


def test_codex_backend_refuses_a_provider_whose_key_is_unset(monkeypatch):
    """A missing credential fails at construction, not mid-run."""
    monkeypatch.delenv("BOYD_TEST_PROVIDER_KEY", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    with pytest.raises(llm.BackendError, match="BOYD_TEST_PROVIDER_KEY"):
        llm.CodexCliBackend("deepseek-v4-pro", timeout_s=12,
                            provider={"name": "deepseek",
                                      "env_key": "BOYD_TEST_PROVIDER_KEY"})


def test_doctor_checks_codex_login_for_codex_backend(monkeypatch, capsys):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="Logged in using ChatGPT", stderr="")

    cfg = _Cfg({"analysis.backend": "codex_cli", "autonomy.mode": "manual"})
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(cli.subprocess, "run", run)

    assert cli.cmd_doctor(SimpleNamespace()) == 0
    assert ["codex", "login", "status"] in calls
    assert "Codex login" in capsys.readouterr().out
    assert all("claude" not in command for command in calls)


def test_retry_carries_the_rejection_back_into_the_prompt(monkeypatch):
    """2026-09-16, the DeepSeek switch: one docket came back as malformed JSON
    and `cli_attempts: 1` meant no second try. With attempts allowed, the retry
    used to resend the identical prompt, so attempt 2 had no better chance than
    attempt 1. The rejection now rides along with the second request."""
    seen = []
    replies = ["this is not json", json.dumps({"answer": "ok"})]

    def run(command, **kwargs):
        seen.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(replies[len(seen) - 1], encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(llm.subprocess, "run", run)
    backend = _backend(monkeypatch, attempts=2)

    assert backend.complete("SYSTEM", "USER", SCHEMA, "score") == {"answer": "ok"}
    assert len(seen) == 2
    command, kwargs = seen[1]
    payload = " ".join(str(part) for part in command) + str(kwargs.get("input") or "")
    assert "previous reply was rejected" in payload


def test_codex_backend_keeps_the_rejected_response_and_its_token_usage(monkeypatch, tmp_path):
    """2026-09-16: a Producer response was rejected at "char 26652 of 26652" —
    the text ended exactly where the parser expected a comma — and nothing kept
    the bytes, so truncation-at-a-ceiling and a model-side malformation were
    indistinguishable after the fact. Every rejected Codex response is now
    written to logs/rejected/ next to the turn's token usage, which is the
    measurement that tells the two apart."""
    # The reply stops where the JSON still expected more: an inner object
    # closed, its container never did. This is the 26652-char reply's shape.
    truncated = '{"answer": "ok", "items": [{"n": 1}'

    def run(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(truncated, encoding="utf-8")
        stdout = json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 41997, "output_tokens": 8192},
        })
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(llm.subprocess, "run", run)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(llm.BackendError, match="ended early"):
        _backend(monkeypatch).complete("SYSTEM", "USER", SCHEMA, "producer")

    rejected = tmp_path / "logs" / "rejected"
    assert (rejected / "producer_attempt1.txt").read_text(encoding="utf-8") == truncated
    usage = json.loads(
        (rejected / "producer_attempt1.usage.json").read_text(encoding="utf-8")
    )
    assert usage == {"input_tokens": 41997, "output_tokens": 8192}
