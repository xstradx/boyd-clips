"""Model backends.

Two ways to reach Claude, chosen by `analysis.backend`:

  claude_cli  Shells out to the Claude Code CLI in headless mode, reusing the
              OAuth login you already have. No API key, no separate billing.
  sdk         The Anthropic SDK. Needs ANTHROPIC_API_KEY or an `ant auth`
              profile, and gives schema-enforced structured outputs.

The CLI path is the default because it needs no extra credential. It costs one
real capability: the API can *guarantee* a response matches a JSON schema
(`output_config.format`), and the CLI cannot. So this module carries its own
validator and retry loop — the model is asked for JSON, the result is checked
against the schema in Python, and a failure is fed back as a correction rather
than propagating a malformed case into the render stage.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

MAX_ATTEMPTS = 3

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


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response.

    Tries the whole string first, then strips markdown fences, then falls back
    to the outermost braced span — models sometimes prepend a sentence despite
    being told not to.
    """
    for candidate in (text, _FENCE.sub("", text)):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        # Must not let a JSONDecodeError escape: complete() catches
        # BackendError to drive its retry, so a raw decode error here would
        # bypass the retry loop entirely and abort the run.
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise BackendError(
                f"response is not valid JSON ({exc.msg} at char {exc.pos} of "
                f"{len(text)}); response may be truncated"
            ) from exc

    raise BackendError(f"no JSON object in response (first 200 chars: {text[:200]!r})")


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
        try:
            out = Path("logs") / "rejected"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{label}_attempt{attempt}.txt").write_text(raw, encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _correction(original: str, error: str) -> str:
        return (
            f"{original}\n\n---\n\nYour previous response was rejected:\n"
            f"  {error}\n\n"
            "Return the corrected JSON object and nothing else. The schema "
            "describes the shape your output must take — do not copy schema "
            "keywords such as \"required\", \"type\", \"properties\" or "
            "\"enum\" into the output itself. Emit data only."
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
    kind = cfg.get("analysis.backend", "claude_cli")
    model = cfg.require("analysis.model")

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
    raise BackendError(f"unknown analysis.backend: {kind!r} (expected claude_cli or sdk)")
