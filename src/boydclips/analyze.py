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

from .censor import censor
from .config import Config, prompt_text
from .llm import BackendError, RefusalError, build_backend  # noqa: F401  (re-exported)
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

SAFETY_RULE_IDS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]

_SEGMENT_REF = {
    "type": "object",
    "properties": {
        "beat": {
            "type": "string",
            # "moment" is the Form B single-segment short (CONTENT_SPEC §3).
            "enum": ["hook", "stakes", "turn", "button", "moment"],
        },
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
                            # The five beats that separated 8 winning videos
                            # from 6 losing ones on @courtroomtime, who clip
                            # this same judge. Replaces human_stakes /
                            # dramatic_turn / judge_moment / self_contained —
                            # abstract ratings the model had to interpret, and
                            # which scored a routine plea-deadline hearing 92.
                            # See spec/SPEC.md §2.
                            "pushback": _SCORE_DIM,
                            "boyd_register": _SCORE_DIM,
                            "receipt": _SCORE_DIM,
                            "consequence": _SCORE_DIM,
                            "hook_strength": _SCORE_DIM,
                        },
                        "required": [
                            "pushback", "boyd_register", "receipt",
                            "consequence", "hook_strength",
                        ],
                        "additionalProperties": False,
                    },
                    "audio_quality": {"type": "integer"},
                    "hook_quote": {"type": "string"},
                    "hook_start_s": {"type": "number"},
                    "shortable": {"type": "boolean"},
                    "short_form": {
                        "type": "string",
                        "enum": ["four_beat", "single_moment", "none"],
                    },
                    "shortable_reasoning": {"type": "string"},
                    "short_segments": {"type": "array", "items": _SEGMENT_REF},
                    "summary": {"type": "string"},
                },
                "required": [
                    "start_s", "end_s", "defendant_name", "cause_number",
                    "proceeding_type", "guilt_posture", "safety", "scores",
                    "audio_quality", "hook_quote", "hook_start_s", "shortable",
                    "short_form", "shortable_reasoning", "short_segments", "summary",
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
        "thumbnail_quote": {"type": "string"},
        # spec/PACKAGING.md §Thumbnails rule 4 — the emotionally loaded half of
        # the quote is yellow and the setup stays white, split mid-sentence.
        # Which half is loaded is a judgement about meaning, so the model makes
        # it here rather than the renderer guessing with a word count. Must be
        # a verbatim SUFFIX of thumbnail_quote; pipeline.split_thumbnail_quote
        # rejects anything else and says so.
        "thumbnail_quote_yellow": {"type": "string"},
        "title_support_quote": {"type": "string"},
        "guilt_posture_check": {"type": "string"},
    },
    "required": [
        "hook_line", "summary", "longform_title", "short_title",
        "thumbnail_quote", "thumbnail_quote_yellow", "title_support_quote",
        "guilt_posture_check",
    ],
    "additionalProperties": False,
}


class Analyzer:
    def __init__(self, cfg: Config, log=None):
        self.cfg = cfg
        self.log = log
        self.backend = build_backend(cfg, log=log)
        self.prompt_versions: dict[str, str] = {}

    # ------------------------------------------------------------------ core

    def _call(self, prompt_name: str, user_text: str, schema: dict[str, Any]) -> dict[str, Any]:
        version, system, _ = prompt_text(prompt_name)
        self.prompt_versions[prompt_name] = version
        return self.backend.complete(system, user_text, schema, prompt_name)

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

    def confirm_selection(
        self, transcript: Transcript, case: dict[str, Any], meta: dict[str, Any]
    ) -> tuple[bool, str]:
        """Re-run the gate on one selected case against the full transcript.

        Batch scoring shows each batch only its own cases' transcript span,
        which bounds cost but measurably shifts safety judgements between runs
        — R4 in particular ("would the cut invert the outcome?") is a question
        about context, so narrowing the context changes the answer. Observed:
        three of six cases that passed the gate on one run were rejected on
        another.

        Re-checking only the day's pick, with everything the model can see, is
        cheap (one case, one call) and lands exactly where the cost of a wrong
        answer is highest — immediately before anything is downloaded,
        rendered, or published.
        """
        rechecked = self.score(transcript, [case], meta, full_context=True)
        if not rechecked:
            return False, "re-check returned no result for the selected case"

        confirmed = rechecked[0]
        if not confirmed["safety"]["safety_pass"]:
            rules = ", ".join(confirmed["safety"]["safety_rule_violations"]) or "unspecified"
            return False, f"failed safety re-check ({rules})"
        if not confirmed["eligible"]:
            return False, f"failed re-check: {confirmed['ineligible_reason']}"

        # Carry the fuller judgement forward — it saw more than the batch did.
        case["safety"] = confirmed["safety"]
        case["scores"] = confirmed["scores"]
        case["total_score"] = confirmed["total_score"]
        case["recheck_score"] = confirmed["total_score"]
        return True, ""

    def score(
        self,
        transcript: Transcript,
        cases: list[dict[str, Any]],
        meta: dict[str, Any],
        full_context: bool = False,
    ) -> list[dict[str, Any]]:
        """Score in batches.

        A single call cannot carry a full docket: each scored case emits five
        justifications, safety reasoning, a summary, and segment ranges, so a
        20-case docket overflows the model's output limit and comes back as
        truncated JSON that no amount of retrying repairs. Batching bounds the
        response, and passing only each batch's own transcript span bounds the
        input too.
        """
        _, _, template = prompt_text("score_cases")
        batch_size = max(1, self.cfg.get("analysis.score_batch_size", 6))
        weights = self.cfg.require("analysis.rubric_weights")
        gates = self.cfg.require("analysis.gates")

        raw_cases: list[dict[str, Any]] = []
        batches = [cases[i:i + batch_size] for i in range(0, len(cases), batch_size)]

        for n, batch in enumerate(batches, start=1):
            label = f"batch {n}/{len(batches)}"
            user = template.format(
                video_title=meta["title"],
                docket_date=meta.get("docket_date", "unknown"),
                source_url=meta["url"],
                cases_json=json.dumps(batch, ensure_ascii=False, indent=2),
                transcript=(
                    transcript.render_for_llm() if full_context
                    else _excerpt_for(transcript, batch)
                ),
            )
            result = self._call("score_cases", user, SCORE_SCHEMA)
            raw_cases.extend(result["cases"])
            if self.log:
                self.log.info(
                    "    scored %s (%d case(s))", label, len(result["cases"])
                )

        scored: list[dict[str, Any]] = []
        for case in raw_cases:
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

        # CONTENT_SPEC §9 — every string returned here is a text surface, and
        # text surfaces are censored even though the audio is not. Done before
        # the length checks so the asterisks are inside the character count.
        for field in (
            "hook_line", "summary", "longform_title", "short_title",
            "thumbnail_quote", "title_support_quote",
        ):
            if isinstance(pkg.get(field), str):
                pkg[field] = censor(pkg[field])

        lf_max = self.cfg.get("packaging.longform.title_max_chars", 70)
        sh_max = self.cfg.get("packaging.short.title_max_chars", 70)
        pkg["longform_title"] = _trim_title(pkg["longform_title"], lf_max)
        pkg["short_title"] = _trim_title(pkg["short_title"], sh_max)

        # PACKAGING.md band is 50-65, hard ceiling 70. Trimming already enforces
        # the ceiling; a short title is the model ignoring the floor and cannot
        # be fixed by truncation, so surface it rather than silently shipping it.
        floor = self.cfg.get("packaging.title_min_chars", 50)
        pkg["title_lengths"] = {
            "longform": len(pkg["longform_title"]),
            "short": len(pkg["short_title"]),
        }
        pkg["title_band_ok"] = all(
            floor <= n <= 70 for n in pkg["title_lengths"].values()
        )
        if not pkg["title_band_ok"] and self.log:
            self.log.warning(
                "title outside the 50-70 band: longform=%d short=%d",
                pkg["title_lengths"]["longform"], pkg["title_lengths"]["short"],
            )

        # CONTENT_SPEC §6: the hook must be a line actually spoken. Verify it
        # against the transcript rather than trusting the model's own claim.
        pkg["hook_verified"] = _quote_appears(
            pkg["hook_line"], transcript.text_between(case["start_s"], case["end_s"])
        )
        return pkg


# --------------------------------------------------------------------- utils


def _excerpt_for(transcript: Transcript, batch: list[dict[str, Any]], pad_s: float = 45.0) -> str:
    """Transcript covering only this batch's cases, with a little lead-in.

    Sending the whole docket to every batch would multiply input tokens by the
    batch count for no benefit — a case is scored on its own content, and the
    surrounding two hours are not evidence about it.
    """
    spans = sorted(
        (max(0.0, c["start_s"] - pad_s), c["end_s"] + pad_s) for c in batch
    )

    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    chunks = []
    for start, end in merged:
        words = transcript.slice(start, end)
        if not words:
            continue
        body = Transcript(transcript.video_id, words).render_for_llm()
        chunks.append(f"--- {hhmmss(start)} to {hhmmss(end)} ---\n{body}")
    return "\n\n".join(chunks)


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
    # `requires_self_contained` is retired: the format is now one defendant
    # across ALL their appearances, so a chapter that only makes sense next to
    # the others is the product rather than a defect. The gate now asks for
    # PUSHBACK instead, which is the single strongest measured separator
    # (present in 8 of 8 winners, 1 of 6 losers) — a compliant defendant is
    # what actually kills a clip. See spec/SPEC.md §2.
    if gates.get("requires_pushback") and case["scores"]["pushback"]["score"] < 40:
        return False, "no pushback — defendant complies throughout (banked)"
    if gates.get("requires_shortable") and not case.get("shortable"):
        # Not a quality judgement — the case is banked, not discarded. It just
        # cannot carry a publishing day on its own, because the short is what
        # brings anyone to the long-form.
        return False, "no short can be built from it (banked for later)"
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
