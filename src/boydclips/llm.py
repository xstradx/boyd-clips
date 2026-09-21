"""Model backends.

Backends are selected explicitly by `analysis.backend`:

  codex_cli   Runs the authenticated Codex CLI in an isolated temporary
              directory with an explicit model and JSON output schema.

  claude_cli  Shells out to the Claude Code CLI in headless mode, reusing the
              OAuth login you already have. No API key, no separate billing.
  sdk         The Anthropic SDK. Needs ANTHROPIC_API_KEY or an `ant auth`
              profile, and gives schema-enforced structured outputs.

The active Codex CLI route uses its output-schema support and then applies this
module's existing parser and validator as a second boundary. It makes one
attempt by default so an invalid response cannot silently spend another call.
The legacy Claude CLI route retains its older client-side retry behavior.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

MAX_ATTEMPTS = 3

# Rejected responses are kept verbatim. Diagnosing a malformed reply from a log
# line alone is guesswork: on 2026-09-16 a Producer response was rejected at
# "char 26652 of 26652" — the text ended exactly where the JSON parser expected
# a comma — and no copy of that text survived, so whether it was truncated by a
# token ceiling or malformed by the model could not be settled from evidence.
REJECTED_DIR = Path("logs") / "rejected"


def dump_rejected(label: str, attempt: int, raw: str,
                  usage: dict[str, Any] | None = None) -> None:
    """Keep a rejected response (and the turn's token usage) for diagnosis."""
    try:
        REJECTED_DIR.mkdir(parents=True, exist_ok=True)
        (REJECTED_DIR / f"{label}_attempt{attempt}.txt").write_text(raw, encoding="utf-8")
        if usage:
            (REJECTED_DIR / f"{label}_attempt{attempt}.usage.json").write_text(
                json.dumps(usage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    except OSError:
        pass


# Analysis is pure text generation. Claude Code would otherwise happily go read
# files or search the web mid-task, which would be slower, non-deterministic,
# and outside anything these prompts ask for.
DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "NotebookEdit", "Glob", "Grep",
    "WebSearch", "WebFetch", "Task", "TodoWrite",
]

JSON_CONTRACT = """

---

# OUTPUT CONTRACT

Respond with a single JSON object and nothing else.

- No prose before or after. No markdown code fences. No commentary.
- The response must parse as JSON on the first attempt.
- It must conform exactly to this schema, including every required field:

{schema}
"""


class BackendError(RuntimeError):
    pass


class RefusalError(BackendError):
    """The model declined the request outright."""


class Backend(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: dict[str, Any], label: str) -> dict[str, Any]:
        ...


# --------------------------------------------------------------- validation


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate against the JSON Schema subset these prompts use.

    Deliberately small — the schemas here only use type/properties/required/
    items/enum/additionalProperties, because that is all the structured-outputs
    API supports. Anything richer would not survive the sdk backend either.
    """
    errors: list[str] = []
    expected = schema.get("type")

    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required field missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in schema.get("properties", {}):
                    errors.append(f"{path}.{key}: unexpected field")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors.extend(validate(value[key], sub, f"{path}.{key}"))

    elif expected == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array, got {type(value).__name__}"]
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(validate(item, item_schema, f"{path}[{i}]"))

    elif expected == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__}")
        elif "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} not in {schema['enum']}")

    elif expected == "integer":
        # bool is a subclass of int; an integer field must not accept True.
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{path}: expected integer, got {type(value).__name__}")

    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{path}: expected number, got {type(value).__name__}")

    elif expected == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean, got {type(value).__name__}")

    return errors


def prune_unknown(value: Any, schema: dict[str, Any]) -> Any:
    """Drop keys the schema does not declare, recursively.

    The CLI backend has to describe the wanted shape by pasting the JSON schema
    into the prompt, and models sometimes mirror schema *metadata* back as if
    it were data — an observed failure was a `safety` object returned with a
    `required` key copied straight out of the schema. That is harmless: nothing
    downstream reads undeclared fields.

    Treating it as fatal was not harmless. One echoed key burned all three
    retries and dropped a 20-case docket. Prune first, then validate what
    remains, so retries are spent on real problems — missing required fields
    and wrong types.
    """
    if isinstance(value, dict) and schema.get("type") == "object":
        properties = schema.get("properties", {})
        return {
            k: prune_unknown(v, properties[k]) if k in properties else v
            for k, v in value.items()
            if k in properties
        }

    if isinstance(value, list) and schema.get("type") == "array":
        item_schema = schema.get("items")
        if item_schema:
            return [prune_unknown(v, item_schema) for v in value]

    return value


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

# JavaScript literals in value position. Models reach for `undefined` when they
# invent an optional field they have nothing to put in — observed in the wild as
# `"safety_rule_violations_note":undefined`, which fails the whole docket even
# though prune_unknown() would have dropped that key a moment later.
_JS_LITERAL = re.compile(r"(:\s*)(undefined|NaN|-?Infinity)(\s*[,}\]])")
# \' is never a valid JSON escape; models emit it when quoting inside a string.
_BAD_ESCAPE = re.compile(r"\\(['`])")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def repair_json(text: str) -> str:
    """Fix malformations models produce that carry no semantic content.

    Deliberately conservative: only value-position JS literals, invalid escapes
    and trailing commas. Anything that could change the meaning of valid JSON is
    left alone — a response we cannot repair honestly should fail and retry
    rather than be silently reinterpreted.
    """
    text = _JS_LITERAL.sub(r"\1null\3", text)
    text = _BAD_ESCAPE.sub(r"\1", text)
    text = _TRAILING_COMMA.sub(r"\1", text)
    return text


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response.

    Tries the whole string first, then strips markdown fences, then repairs
    known-benign malformations, then falls back to the outermost braced span —
    models sometimes prepend a sentence despite being told not to.
    """
    for candidate in (text, _FENCE.sub("", text), repair_json(_FENCE.sub("", text))):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    repaired = repair_json(text)
    start, end = repaired.find("{"), repaired.rfind("}")
    if start != -1 and end > start:
        text = repaired
        span = text[start:end + 1]
        # Must not let a JSONDecodeError escape: complete() catches
        # BackendError to drive its retry, so a raw decode error here would
        # bypass the retry loop entirely and abort the run.
        try:
            parsed = json.loads(span)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            # Two different failures wore the same message until 2026-09-16.
            # A parse error AT the end of the text means the reply stops where
            # the JSON was still expecting more — the shape of a generation that
            # stopped early (measured on a Producer reply that ended at char
            # 26652 of 26652, while the same model and backend emitted 52,010
            # output tokens in one clean turn, so no output ceiling is involved).
            # Anything earlier is a structurally malformed object. The
            # distinction is the whole diagnosis, and it is in the error text.
            if exc.pos >= len(span):
                detail = ("the reply stops where the JSON still expected more - it "
                          "ended early rather than carrying a bad object")
            else:
                detail = "the reply is malformed mid-response"
            raise BackendError(
                f"response is not valid JSON ({exc.msg} at char {exc.pos} of "
                f"{len(text)}); {detail}; raw reply: logs/rejected/"
            ) from exc

    raise BackendError(f"no JSON object in response (first 200 chars: {text[:200]!r})")


# -------------------------------------------------------------- Codex CLI


class CodexCliBackend:
    """Text-only structured generation through the authenticated Codex CLI."""

    name = "codex_cli"

    def __init__(self, model: str, effort: str = "medium", timeout_s: int = 1800,
                 attempts: int = 1, log=None, provider: dict[str, Any] | None = None):
        # Resolve once, and run the absolute path. On Windows the CLI is an npm
        # shim (`codex.CMD`); CreateProcess searches PATH for `codex` but will
        # not append `.CMD`, so passing the bare name raises
        # "[WinError 2] The system cannot find the file specified" before any
        # model call is made.
        self.codex = shutil.which("codex") or shutil.which("codex.cmd")
        if self.codex is None:
            raise BackendError(
                "analysis.backend is 'codex_cli' but the codex CLI is not on PATH."
            )
        if attempts < 1:
            raise BackendError("analysis.cli_attempts must be at least 1")
        self.model = model
        self.effort = effort
        self.timeout_s = timeout_s
        self.attempts = attempts
        self.log = log
        # Token usage of the most recent turn; recorded even when the response
        # is rejected so the rejection's cause can be measured (a response that
        # stops at the model's output ceiling looks exactly like a truncated
        # one, and the usage numbers are the difference).
        self.last_usage: dict[str, Any] = {}
        self.provider = dict(provider or {})
        env_key = self.provider.get("env_key")
        if env_key and not os.environ.get(str(env_key)):
            # Fail at construction rather than three stages into a nightly run.
            raise BackendError(
                f"analysis.provider.env_key is {env_key!r} but that variable is "
                "not set. Put it in config/.env (gitignored) or export it."
            )

    def _provider_flags(self) -> list[str]:
        """Point the isolated CLI session at an explicitly configured provider.

        Every production call runs with `--ignore-user-config` so no local hook,
        skill or stray setting can reach it. That also hides the provider the
        user's own `~/.codex/config.toml` selects, so when `analysis.provider`
        is set it is passed in explicitly here.

        The API key itself is never an argv entry: the provider is told which
        environment variable carries it (`env_key`) and config.load_env()
        supplies that variable from the gitignored config/.env.
        """
        if not self.provider:
            return []
        name = str(self.provider.get("name") or "").strip()
        if not name:
            raise BackendError("analysis.provider is set but has no name")
        flags = [f'model_provider="{name}"', f'model_providers.{name}.name="{name}"']
        for field in ("base_url", "wire_api", "env_key"):
            value = self.provider.get(field)
            if value:
                flags.append(f'model_providers.{name}.{field}="{value}"')
        return flags

    def complete(self, system: str, user: str, schema: dict[str, Any], label: str) -> dict[str, Any]:
        prompt = (
            system + JSON_CONTRACT.format(schema=json.dumps(schema, indent=2))
            + "\n\n---\n\n# USER INPUT\n\n" + user
            + "\n\nDo not call tools. Return only the requested JSON object."
        )
        last_error = ""
        base_prompt = prompt
        for attempt in range(1, self.attempts + 1):
            raw = ""
            self.last_usage = {}
            try:
                raw = self._invoke(prompt, schema, label, attempt)
                data = prune_unknown(extract_json(raw), schema)
                errors = validate(data, schema)
                if not errors:
                    return data
                last_error = "; ".join(errors[:8])
            except RefusalError:
                raise
            except (BackendError, ValueError) as exc:
                last_error = str(exc)

            if self.log:
                usage_note = ""
                if self.last_usage:
                    usage_note = (
                        f" (in {self.last_usage.get('input_tokens')} / "
                        f"out {self.last_usage.get('output_tokens')} tokens)"
                    )
                self.log.warning("  %s: Codex response rejected — %s%s",
                                 label, last_error, usage_note)
            # Keep the exact bytes the parser refused. A rejected response is
            # the only evidence of whether the model malformed the JSON or the
            # request was cut short, and the temporary file is gone by now.
            if raw:
                dump_rejected(label, attempt, raw, self.last_usage)
            # 2026-09-16: the retry used to resend the identical prompt, so a
            # model that malformed the JSON once (measured on deepseek-v4-pro:
            # one docket scored as malformed and no second attempt was made)
            # had no better chance on attempt 2. Carry the rejection back.
            prompt = (
                base_prompt
                + "\n\nYour previous reply was rejected: " + last_error
                + "\nReturn only the JSON object described above, with every required field present."
            )

        raise BackendError(
            f"{label}: Codex response failed after {self.attempts} attempt(s). "
            f"Last error: {last_error}"
        )

    def _invoke(self, prompt: str, schema: dict[str, Any], label: str, attempt: int) -> str:
        with tempfile.TemporaryDirectory(prefix="boyd-codex-") as tmp:
            work = Path(tmp)
            schema_path = work / "output-schema.json"
            output_path = work / "last-message.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                self.codex, "exec",
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--disable", "shell_tool",
                "--disable", "unified_exec",
                "--disable", "multi_agent",
                "--disable", "image_generation",
                "--disable", "apps",
                "--disable", "plugins",
                "--disable", "computer_use",
                "--disable", "view_image",
                "--model", self.model,
                "--config", f'model_reasoning_effort="{self.effort}"',
                "--config", 'web_search="disabled"',
                "--config", 'approval_policy="never"',
                *[arg for flag in self._provider_flags() for arg in ("--config", flag)],
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path),
                "--json",
                "--color", "never",
                "--cd", str(work),
                "-",
            ]
            try:
                proc = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self.timeout_s,
                    cwd=work,
                )
            except subprocess.TimeoutExpired as exc:
                raise BackendError(
                    f"{label}: codex CLI timed out after {self.timeout_s}s"
                ) from exc
            except OSError as exc:
                raise BackendError(f"{label}: could not start codex CLI: {exc}") from exc

            events = self._events(proc.stdout)
            failure = next((e for e in events if e.get("type") in ("error", "turn.failed")), None)
            if failure:
                detail = json.dumps(failure.get("error") or failure.get("message") or failure)
                if "refus" in detail.lower() or "declin" in detail.lower():
                    raise RefusalError(f"{label}: model declined the request")
                raise BackendError(f"{label}: codex CLI reported an error: {detail[:400]}")
            tool_event = next((e for e in events if self._is_tool_event(e)), None)
            if tool_event:
                raise BackendError(
                    f"{label}: codex CLI emitted a forbidden tool event: "
                    f"{json.dumps(tool_event)[:400]}"
                )
            if proc.returncode != 0:
                raise BackendError(
                    f"{label}: codex CLI exited {proc.returncode}: "
                    f"{(proc.stderr or '').strip()[:400]}"
                )
            if not output_path.exists():
                raise BackendError(f"{label}: codex CLI produced no final response file")

            completed = next((e for e in reversed(events) if e.get("type") == "turn.completed"), {})
            self.last_usage = dict(completed.get("usage") or {})
            if self.log:
                usage = self.last_usage
                self.log.debug(
                    "  %s attempt %d: %s in / %s out",
                    label, attempt, usage.get("input_tokens"), usage.get("output_tokens"),
                )
            return output_path.read_text(encoding="utf-8")

    @staticmethod
    def _events(stdout: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    @staticmethod
    def _is_tool_event(event: dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "")
        if event_type.startswith("tool.") or event_type in ("tool_call", "tool_result"):
            return True
        if event_type not in ("item.started", "item.completed"):
            return False
        item = event.get("item") or {}
        # Codex reports local configuration diagnostics (for example a hook
        # timeout clamp) as item.type=error even when the model turn succeeds
        # and writes the schema-validated final response. It is not a tool call.
        # A real failed turn is still caught by turn.failed, nonzero exit, or a
        # missing final-response file above.
        return str(item.get("type") or "") not in ("reasoning", "agent_message", "error")


# ------------------------------------------------------------- claude CLI


class ClaudeCliBackend:
    name = "claude_cli"

    def __init__(self, model: str, timeout_s: int = 1800, log=None):
        if shutil.which("claude") is None:
            raise BackendError(
                "analysis.backend is 'claude_cli' but the claude CLI is not on PATH."
            )
        self.model = model
        self.timeout_s = timeout_s
        self.log = log

    def complete(self, system: str, user: str, schema: dict[str, Any], label: str) -> dict[str, Any]:
        full_system = system + JSON_CONTRACT.format(
            schema=json.dumps(schema, indent=2)
        )
        prompt = user
        last_error = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            raw = self._invoke(full_system, prompt, label, attempt)
            try:
                data = extract_json(raw)
            except (BackendError, ValueError) as exc:
                last_error = str(exc)
                if self.log:
                    self.log.warning(
                        "  %s: unparseable response on attempt %d — %s",
                        label, attempt, last_error,
                    )
                    self._dump(label, attempt, raw)
                prompt = self._correction(user, last_error)
                continue

            data = prune_unknown(data, schema)
            errors = validate(data, schema)
            if not errors:
                return data

            last_error = "; ".join(errors[:8])
            if self.log:
                self.log.warning(
                    "  %s: schema mismatch on attempt %d — %s", label, attempt, last_error
                )
            prompt = self._correction(user, last_error)

        raise BackendError(
            f"{label}: response failed schema validation after {MAX_ATTEMPTS} "
            f"attempts. Last error: {last_error}"
        )

    @staticmethod
    def _dump(label: str, attempt: int, raw: str) -> None:
        """Keep the rejected response. Diagnosing a malformed reply from a log
        line alone is guesswork, and these only appear on failures."""
        dump_rejected(label, attempt, raw)

    @staticmethod
    def _correction(original: str, error: str) -> str:
        return (
            f"{original}\n\n---\n\nYour previous response was rejected:\n"
            f"  {error}\n\n"
            "Return the corrected JSON object and nothing else. The schema "
            "describes the shape your output must take — do not copy schema "
            "keywords such as \"required\", \"type\", \"properties\" or "
            "\"enum\" into the output itself. Emit data only.\n\n"
            "These four mistakes caused every failure observed so far. Check "
            "for them specifically:\n"
            "  1. Every object you open must be closed. A dropped `}` on one "
            "case invalidates the entire response — count your braces.\n"
            "  2. No `undefined`, `NaN` or `Infinity`. They are JavaScript, not "
            "JSON. Use null, or omit the field.\n"
            "  3. Do not invent fields the schema does not define (no "
            "`*_note`, no commentary keys). Put reasoning in the field that "
            "already exists for it.\n"
            "  4. Inside a string, write an apostrophe as ' — never \\'. The "
            "only valid escapes are \\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX."
        )

    def _invoke(self, system: str, prompt: str, label: str, attempt: int) -> str:
        # The system prompt goes via file and the user prompt via stdin.
        # Neither can be an argv entry: Windows caps a command line at ~32KB
        # and a three-hour docket transcript is well over 100KB.
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(system)
            system_path = Path(fh.name)

        try:
            proc = subprocess.run(
                [
                    "claude", "-p",
                    "--output-format", "json",
                    "--model", self.model,
                    "--system-prompt-file", str(system_path),
                    "--exclude-dynamic-system-prompt-sections",
                    "--disallowed-tools", *DISALLOWED_TOOLS,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendError(
                f"{label}: claude CLI timed out after {self.timeout_s}s"
            ) from exc
        finally:
            system_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            raise BackendError(
                f"{label}: claude CLI exited {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:400]}"
            )

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise BackendError(
                f"{label}: CLI did not return a JSON envelope: {proc.stdout[:300]!r}"
            ) from exc

        if envelope.get("is_error"):
            raise BackendError(f"{label}: CLI reported an error: {envelope.get('result')}")
        if envelope.get("stop_reason") == "refusal":
            raise RefusalError(f"{label}: model declined the request")

        if self.log:
            usage = envelope.get("usage") or {}
            self.log.debug(
                "  %s attempt %d: %s in / %s out, %.1fs",
                label, attempt,
                usage.get("input_tokens"), usage.get("output_tokens"),
                (envelope.get("duration_api_ms") or 0) / 1000,
            )

        return envelope.get("result") or ""


# ------------------------------------------------------------------- SDK


class SdkBackend:
    name = "sdk"

    def __init__(self, model: str, effort: str, max_tokens: int, log=None):
        import anthropic  # imported lazily so the CLI path needs no SDK creds

        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.log = log

    def complete(self, system: str, user: str, schema: dict[str, Any], label: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        try:
            message = self._stream(self.client.beta.messages, kwargs)
        except TypeError:
            kwargs.pop("betas", None)
            kwargs.pop("fallbacks", None)
            message = self._stream(self.client.messages, kwargs)

        if message.stop_reason == "refusal":
            category = getattr(getattr(message, "stop_details", None), "category", None)
            raise RefusalError(f"{label}: model declined the request (category={category})")
        if message.stop_reason == "max_tokens":
            raise BackendError(
                f"{label}: hit max_tokens ({self.max_tokens}); response is truncated. "
                "Raise analysis.max_tokens."
            )

        text = next((b.text for b in message.content if b.type == "text"), None)
        if not text:
            raise BackendError(f"{label}: no text block in response")
        return json.loads(text)

    @staticmethod
    def _stream(namespace: Any, kwargs: dict[str, Any]) -> Any:
        with namespace.stream(**kwargs) as stream:
            return stream.get_final_message()


def build_backend(cfg, log=None) -> Backend:
    kind = cfg.get("analysis.backend", "codex_cli")
    model = cfg.require("analysis.model")

    if kind == "codex_cli":
        return CodexCliBackend(
            model=model,
            effort=cfg.get("analysis.effort", "medium"),
            timeout_s=cfg.get("analysis.cli_timeout_s", 1800),
            attempts=cfg.get("analysis.cli_attempts", 1),
            log=log,
            provider=cfg.get("analysis.provider"),
        )
    if kind == "claude_cli":
        return ClaudeCliBackend(
            model=model, timeout_s=cfg.get("analysis.cli_timeout_s", 1800), log=log
        )
    if kind == "sdk":
        return SdkBackend(
            model=model,
            effort=cfg.get("analysis.effort", "high"),
            max_tokens=cfg.get("analysis.max_tokens", 32000),
            log=log,
        )
    raise BackendError(
        f"unknown analysis.backend: {kind!r} (expected codex_cli, claude_cli or sdk)"
    )
