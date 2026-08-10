"""Stage 2 — segmentation, safety gating, scoring, and packaging.

Three Claude calls per docket, all driven by the versioned files in prompts/
and constrained by JSON schemas so nothing downstream ever parses prose.

Measured cost (claude-opus-5, effort=high): ~$0.38 for a 52-minute docket,
~$0.61 for a 171-minute one — about $1.00 for a typical two-session day.

Two things about that number are worth knowing before tuning it:

  * Output dominates. Roughly 12k output tokens per docket at $25/1M costs more
    than the input does on short dockets. `analysis.effort` is the lever, not
    the transcript size.

  * Cross-call caching does NOT apply here. Caching is a prefix match over
    tools -> system -> messages, and each of the three stages sends a different
    system prompt, so the prefix diverges immediately and nothing is reused
    between them. The cache_control block below earns its keep only on a retry
    of the same call. Making the transcript itself cacheable would require the
    three stages to share one system prefix.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from .config import Config, prompt_text
from .transcribe import Transcript, hhmmss

# ---------------------------------------------------------------------------
# Schemas. Note the constraints the API does NOT support: no `minimum`,
# `maximum`, `minLength`, or `maxLength`. Ranges are enforced in the prompt
# text and validated in Python after the response comes back.
# ---------------------------------------------------------------------------

PROCEEDING_TYPES = [
    "arraignment", "plea", "sentencing", "bond_hearing", "probation_revocation",
    "motion_hearing", "status_conference", "trial_segment", "administrative", "other",
]

SEGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "defendant_name": {"type": "string"},
                    "cause_number": {"type": "string"},
                    "charge": {"type": "string"},
                    "proceeding_type": {"type": "string", "enum": PROCEEDING_TYPES},
                    "outcome": {"type": "string"},
                    "one_line": {"type": "string"},
                    "continued": {"type": "boolean"},
                    "extraction_confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": [
                    "start_s", "end_s", "defendant_name", "cause_number", "charge",
                    "proceeding_type", "outcome", "one_line", "continued",
                    "extraction_confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cases"],
    "additionalProperties": False,
}

SAFETY_RULE_IDS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]

_SEGMENT_REF = {
    "type": "object",
    "properties": {
        "beat": {"type": "string", "enum": ["hook", "stakes", "turn", "button"]},
        "start_s": {"type": "number"},
        "end_s": {"type": "number"},
        "quote": {"type": "string"},
    },
    "required": ["beat", "start_s", "end_s", "quote"],
    "additionalProperties": False,
}

_SCORE_DIM = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "justification": {"type": "string"},
    },
    "required": ["score", "justification"],
    "additionalProperties": False,
}

SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "defendant_name": {"type": "string"},
                    "cause_number": {"type": "string"},
                    "proceeding_type": {"type": "string", "enum": PROCEEDING_TYPES},
                    "guilt_posture": {
                        "type": "string",
                        "enum": ["accused", "pled_guilty", "convicted", "unclear"],
                    },
                    "safety": {
                        "type": "object",
                        "properties": {
                            "safety_pass": {"type": "boolean"},
                            "safety_rule_violations": {
                                "type": "array",
                                "items": {"type": "string", "enum": SAFETY_RULE_IDS},
                            },
                            "safety_reasoning": {"type": "string"},
                        },
                        "required": [
                            "safety_pass", "safety_rule_violations", "safety_reasoning",
                        ],
                        "additionalProperties": False,
                    },
                    "scores": {
                        "type": "object",
                        "properties": {
                            "human_stakes": _SCORE_DIM,
                            "dramatic_turn": _SCORE_DIM,
                            "judge_moment": _SCORE_DIM,
                            "self_contained": _SCORE_DIM,
                            "hook_strength": _SCORE_DIM,
                        },
                        "required": [
                            "human_stakes", "dramatic_turn", "judge_moment",
                            "self_contained", "hook_strength",
                        ],
                        "additionalProperties": False,
                    },
                    "audio_quality": {"type": "integer"},
                    "hook_quote": {"type": "string"},
                    "hook_start_s": {"type": "number"},
                    "shortable": {"type": "boolean"},
                    "shortable_reasoning": {"type": "string"},
                    "short_segments": {"type": "array", "items": _SEGMENT_REF},
                    "summary": {"type": "string"},
                },
                "required": [
                    "start_s", "end_s", "defendant_name", "cause_number",
                    "proceeding_type", "guilt_posture", "safety", "scores",
                    "audio_quality", "hook_quote", "hook_start_s", "shortable",
                    "shortable_reasoning", "short_segments", "summary",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cases"],
    "additionalProperties": False,
}

PACKAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hook_line": {"type": "string"},
        "summary": {"type": "string"},
        "longform_title": {"type": "string"},
        "short_title": {"type": "string"},
        "title_support_quote": {"type": "string"},
        "guilt_posture_check": {"type": "string"},
    },
    "required": [
        "hook_line", "summary", "longform_title", "short_title",
        "title_support_quote", "guilt_posture_check",
    ],
    "additionalProperties": False,
}


class RefusalError(RuntimeError):
    """The model's safety classifiers declined the request outright."""


class Analyzer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = anthropic.Anthropic()
        self.model = cfg.require("analysis.model")
        self.effort = cfg.get("analysis.effort", "high")
        self.max_tokens = cfg.get("analysis.max_tokens", 32000)
        self.prompt_versions: dict[str, str] = {}

    # ------------------------------------------------------------------ core

    def _call(self, prompt_name: str, user_text: str, schema: dict[str, Any]) -> dict[str, Any]:
        version, system, _ = prompt_text(prompt_name)
        self.prompt_versions[prompt_name] = version

        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            # Caching the system block matters here: it carries the entire rubric
            # and safety spec, and all three stages reuse most of it within the
            # 5-minute window of a single docket run.
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_text}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            # Criminal-court transcripts sit close to enough policy boundaries
            # that a classifier decline is a real possibility. Fall back rather
            # than lose the day's run.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        try:
            message = self._stream(self.client.beta.messages, kwargs)
        except TypeError:
            # SDK predates the fallbacks parameter — proceed without it.
            kwargs.pop("betas", None)
            kwargs.pop("fallbacks", None)
            message = self._stream(self.client.messages, kwargs)

        if message.stop_reason == "refusal":
            category = getattr(getattr(message, "stop_details", None), "category", None)
            raise RefusalError(
                f"{prompt_name}: model declined the request (category={category})"
            )
        if message.stop_reason == "max_tokens":
            raise RuntimeError(
                f"{prompt_name}: response hit max_tokens ({self.max_tokens}) and is "
                "truncated. Raise analysis.max_tokens."
            )

        text = next((b.text for b in message.content if b.type == "text"), None)
        if not text:
            raise RuntimeError(f"{prompt_name}: no text block in response")
        return json.loads(text)

    @staticmethod
    def _stream(namespace: Any, kwargs: dict[str, Any]) -> Any:
        # max_tokens is well above the SDK's non-streaming timeout guard, so
        # streaming is required rather than optional here.
        with namespace.stream(**kwargs) as stream:
            return stream.get_final_message()

    # ---------------------------------------------------------------- stage 1

    def segment(self, transcript: Transcript, meta: dict[str, Any]) -> list[dict[str, Any]]:
        _, _, template = prompt_text("segment_cases")
        user = template.format(
            video_id=transcript.video_id,
            video_title=meta["title"],
            docket_date=meta.get("docket_date", "unknown"),
            duration_s=int(transcript.duration_s),
            transcript=transcript.render_for_llm(),
        )
        result = self._call("segment_cases", user, SEGMENT_SCHEMA)
        cases = result["cases"]

        real = [c for c in cases if c["proceeding_type"] != "administrative"]
        return [c for c in real if _valid_span(c, transcript.duration_s)]

    # ---------------------------------------------------------------- stage 2

    def score(
        self, transcript: Transcript, cases: list[dict[str, Any]], meta: dict[str, Any]
    ) -> list[dict[str, Any]]:
        _, _, template = prompt_text("score_cases")
        user = template.format(
            video_title=meta["title"],
            docket_date=meta.get("docket_date", "unknown"),
            source_url=meta["url"],
            cases_json=json.dumps(cases, ensure_ascii=False, indent=2),
            transcript=transcript.render_for_llm(),
        )
        result = self._call("score_cases", user, SCORE_SCHEMA)

        weights = self.cfg.require("analysis.rubric_weights")
        gates = self.cfg.require("analysis.gates")

        scored: list[dict[str, Any]] = []
        for case in result["cases"]:
            if not _valid_span(case, transcript.duration_s):
                continue

            # The weighted total is computed here, not by the model. Asking a
            # model to do arithmetic it has no reason to get right is a
            # reliability bug waiting to happen.
            case["total_score"] = round(
                sum(case["scores"][dim]["score"] * w for dim, w in weights.items()) / 100.0,
                2,
            )
            case["eligible"], case["ineligible_reason"] = _check_gates(case, gates)
            scored.append(case)

        scored.sort(key=lambda c: (c["eligible"], c["total_score"]), reverse=True)
        for i, case in enumerate(scored, start=1):
            case["rank"] = i if case["eligible"] else None
        return scored

    # ---------------------------------------------------------------- stage 3

    def package(
        self, transcript: Transcript, case: dict[str, Any], meta: dict[str, Any], spec_version: str
    ) -> dict[str, Any]:
        _, _, template = prompt_text("package_post")
        user = template.format(
            spec_version=spec_version,
            court=self.cfg.require("source.court"),
            docket_date=meta.get("docket_date", "unknown"),
            source_url=meta["url"],
            start_timestamp=hhmmss(case["start_s"]),
            case_json=json.dumps(case, ensure_ascii=False, indent=2),
            case_transcript=transcript.text_between(case["start_s"], case["end_s"]),
        )
        pkg = self._call("package_post", user, PACKAGE_SCHEMA)

        lf_max = self.cfg.get("packaging.longform.title_max_chars", 100)
        sh_max = self.cfg.get("packaging.short.title_max_chars", 90)
        pkg["longform_title"] = _trim_title(pkg["longform_title"], lf_max)
        pkg["short_title"] = _trim_title(pkg["short_title"], sh_max)

        # CONTENT_SPEC §6: the hook must be a line actually spoken. Verify it
        # against the transcript rather than trusting the model's own claim.
        pkg["hook_verified"] = _quote_appears(
            pkg["hook_line"], transcript.text_between(case["start_s"], case["end_s"])
        )
        return pkg


# --------------------------------------------------------------------- utils


def _valid_span(case: dict[str, Any], duration_s: float) -> bool:
    start, end = case.get("start_s"), case.get("end_s")
    if start is None or end is None:
        return False
    return 0 <= start < end <= duration_s + 5


def _check_gates(case: dict[str, Any], gates: dict[str, Any]) -> tuple[bool, str]:
    if gates.get("safety_must_pass", True) and not case["safety"]["safety_pass"]:
        rules = ", ".join(case["safety"]["safety_rule_violations"]) or "unspecified"
        return False, f"safety gate failed ({rules})"
    if case["total_score"] < gates.get("min_total_score", 0):
        return False, f"score {case['total_score']} below minimum {gates['min_total_score']}"
    if case["audio_quality"] < gates.get("min_audio_quality", 0):
        return False, f"audio quality {case['audio_quality']} below minimum"
    if gates.get("requires_self_contained") and case["scores"]["self_contained"]["score"] < 60:
        return False, "not self-contained without outside context"
    return True, ""


def _trim_title(title: str, limit: int) -> str:
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") or title[:limit]


_APOSTROPHES = "'’ʼ`´"


def _quote_appears(quote: str, haystack: str) -> bool:
    """Loose containment check.

    Auto-captions punctuate inconsistently, and apostrophes are the worst
    offender: the same utterance appears as "that's" or "thats" depending on
    the segment. Apostrophes are therefore *deleted* rather than turned into
    separators — splitting "that's" into "that s" would fail to match "thats"
    and mark almost every genuine verbatim hook as unverified.
    """
    def norm(s: str) -> str:
        stripped = "".join(ch for ch in s if ch not in _APOSTROPHES)
        flattened = "".join(
            ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in stripped
        )
        return " ".join(flattened.split())

    return norm(quote) in norm(haystack)
