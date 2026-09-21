"""Stage 2 — bounded Sol segmentation, scoring, and production planning.

Every reasoning call is driven by a versioned prompt and constrained by a JSON
schema. Calls share one per-run ceiling and record input hashes. Subscription
usage is not converted into an invented dollar estimate.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

from .censor import censor
from .config import Config, prompt_text
from . import editorial
from . import stage_context as stage_rules
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
                        # BOYD_EDITORIAL_V2 (2026-09-06): seven dimensions, each
                        # scored on its own scale, summing to 100. The single
                        # definition is editorial.DIMENSIONS; the prompt quotes
                        # the same maxima and the tests hold them together.
                        # Replaced pushback / boyd_register / receipt /
                        # consequence / hook_strength, which rewarded volume,
                        # conflict and charge severity over story.
                        "properties": {dim: _SCORE_DIM for dim in editorial.DIMENSIONS},
                        "required": list(editorial.DIMENSIONS),
                        "additionalProperties": False,
                    },
                    # The editorial eligibility gate and the story angle
                    # (PART 3/4/6 of the ruleset). Additive: DB rows store the
                    # whole payload and the manifest copies named fields, so
                    # nothing downstream breaks; it exists so the gate is a
                    # machine-readable verdict rather than prose in `summary`.
                    "editorial": {
                        "type": "object",
                        "properties": {
                            "gate_pass": {"type": "boolean"},
                            "gate_failures": {
                                "type": "array",
                                "items": {"type": "string", "enum": list(editorial.GATE_REASONS)},
                            },
                            "story_angle": {"type": "string"},
                            "money_moment": {"type": "string"},
                            "money_moment_s": {"type": "number"},
                            "why_viewer_cares": {"type": "string"},
                            "title_angles": {"type": "array", "items": {"type": "string"}},
                            "weakness": {"type": "string"},
                            "decision": {"type": "string", "enum": list(editorial.DECISIONS)},
                        },
                        "required": [
                            "gate_pass", "gate_failures", "story_angle", "money_moment",
                            "money_moment_s", "why_viewer_cares", "title_angles",
                            "weakness", "decision",
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
                    "proceeding_type", "guilt_posture", "safety", "scores", "editorial",
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
        # BOYD_EDITORIAL_V2 PART 15: the title finalists, why the winner won,
        # and why the thumbnail quote complements the title. Additive — it
        # rides into the manifest under `packaging` and nothing downstream
        # reads it by name.
        "packaging_rationale": {"type": "string"},
    },
    "required": [
        "hook_line", "summary", "longform_title", "short_title",
        "thumbnail_quote", "thumbnail_quote_yellow", "title_support_quote",
        "guilt_posture_check", "packaging_rationale",
    ],
    "additionalProperties": False,
}


class ModelCallLimitError(RuntimeError):
    """The configured per-run Sol call budget is exhausted."""


class ProducerPlanError(RuntimeError):
    """Producer Brain returned a plan that failed deterministic evidence gates."""


class Analyzer:
    def __init__(self, cfg: Config, log=None):
        self.cfg = cfg
        self.log = log
        self.backend = build_backend(cfg, log=log)
        self.prompt_versions: dict[str, str] = {}
        self.calls_used = 0
        self.usage_events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ core

    def _reserve_call(self, label: str) -> None:
        limit = int(self.cfg.get("analysis.max_model_calls_per_run", 20))
        used = int(getattr(self, "calls_used", 0))
        reserved = max(0, int(getattr(self, "reserved_calls", 0)))
        stage_limit = max(0, limit - reserved)
        if used >= stage_limit:
            raise ModelCallLimitError(
                f"analysis model-call limit reached ({used}/{limit}; "
                f"{reserved} reserved for bundle completion); "
                "remaining dockets stay available for the next run"
            )
        self.calls_used = used + 1

    def _call(
        self,
        prompt_name: str,
        user_text: str,
        schema: dict[str, Any],
        stage_context: stage_rules.StageContext | None = None,
    ) -> dict[str, Any]:
        version, system, _ = prompt_text(prompt_name)
        self.prompt_versions[prompt_name] = version
        return self._complete(prompt_name, version, system, user_text, schema, stage_context)

    def _complete(
        self,
        label: str,
        version: str,
        system: str,
        user_text: str,
        schema: dict[str, Any],
        stage_context: stage_rules.StageContext | None = None,
    ) -> dict[str, Any]:
        # The current production rules are not in the prompt files; they are
        # rendered from the canonical sources here, fresh on every call, so an
        # edit landing mid-run is reflected rather than frozen at import. A
        # stage that needs rules it cannot load fails before spending a call.
        if stage_context is None and label in {"producer_brain_v1", "package_post", "thumbnail_copy_review"}:
            loader = getattr(self, "stage_context_loader", None)
            if loader is not None:
                stage_context = loader()
            else:
                stage_context = stage_rules.load_context()
        block = stage_context.blocks_for(label) if stage_context is not None else ""
        request_text = f"{block}\n\n{user_text}" if block else user_text
        self._reserve_call(label)
        event = {
            "kind": "model_call",
            "stage": label,
            "backend": self.cfg.get("analysis.backend", "codex_cli"),
            # 2026-09-16: this defaulted to the literal "gpt-5.6-sol", so a
            # config missing analysis.model recorded Sol as the author of work
            # DeepSeek had done — and readiness then refused the bundle. Record
            # nothing rather than a model that never ran; readiness compares the
            # manifest against the configured model and refuses an empty name.
            "model": str(self.cfg.get("analysis.model") or ""),
            "prompt_version": version,
            "input_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
            "call_number": self.calls_used,
            "call_limit": int(self.cfg.get("analysis.max_model_calls_per_run", 20)),
            "attempts_allowed": int(self.cfg.get("analysis.cli_attempts", 1)),
            "token_usage": None,
            "status": "started",
        }
        if block:
            # Provenance for the rule handoff: the hash of the exact text sent,
            # the hash of the context block, and the digest of every source it
            # was quoted from. `input_sha256` stays the stage's own user text.
            event["request_sha256"] = hashlib.sha256(request_text.encode("utf-8")).hexdigest()
            event["stage_context"] = stage_context.provenance(label)
        events = getattr(self, "usage_events", None)
        if events is None:
            self.usage_events = events = []
        events.append(event)
        try:
            result = self.backend.complete(system, request_text, schema, label)
        except Exception as exc:
            event["status"] = "failed"
            event["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
            raise
        event["status"] = "complete"
        return result

    def producer_plan(self, material: dict[str, Any], transcript: Transcript) -> dict[str, Any]:
        """One bounded Sol call through the existing backend, then local validation."""
        from . import producer_brain

        request = producer_brain.prepare_request(material, transcript)
        self.prompt_versions[producer_brain.PROMPT_NAME] = request["version"]
        # Producer planning is isolated: without this the plan is made from the
        # material alone, with no sight of the current production contract or
        # the learned Shorts profile. Loaded here, before the call, so a missing
        # canonical source stops the run instead of silently thinning the plan.
        rules = stage_rules.load_context()
        self.last_producer_context = rules
        plan = self._complete(
            producer_brain.PROMPT_NAME,
            request["version"],
            request["system"],
            request["user"],
            request["schema"],
            rules,
        )
        plan = producer_brain.normalise_source_ids(plan)
        plan = producer_brain.align_transcript_ranges(plan, material, transcript)
        errors = producer_brain.validate_plan(plan, material, transcript)
        if errors:
            payload = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
            rejected = Path("logs") / "rejected" / f"producer_brain_plan_{digest}.json"
            try:
                rejected.parent.mkdir(parents=True, exist_ok=True)
                rejected.write_text(payload + "\n", encoding="utf-8")
                rejected.with_suffix(".errors.txt").write_text(
                    "\n".join(errors) + "\n", encoding="utf-8"
                )
                location = f"; rejected plan saved to {rejected}"
            except OSError:
                location = ""
            raise ProducerPlanError("; ".join(errors[:12]) + location)
        return plan

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
        case["editorial"] = confirmed.get("editorial", case.get("editorial"))
        case["decision"] = confirmed.get("decision", case.get("decision"))
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
        self.cfg.require("analysis.rubric_weights")   # validated at load; mirrors editorial.DIMENSIONS
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

            # The total is computed here, not by the model. BOYD_EDITORIAL_V2:
            # each dimension is scored on its own scale and the total is the
            # plain sum, clamped per dimension to the maximum in
            # editorial.DIMENSIONS (which analysis.rubric_weights mirrors).
            clipped = editorial.over_max(case["scores"])
            if clipped and self.log:
                self.log.warning("    scores over their maximum, clamped: %s", ", ".join(clipped))
            case["total_score"] = editorial.total_score(case["scores"])
            ed = case.setdefault("editorial", {})
            gate_pass = bool(ed.get("gate_pass", True)) and not ed.get("gate_failures")
            ed["gate_pass"] = gate_pass
            # The decision is deterministic from the total and the gate; the
            # model's own verdict is kept only as a disagreement to log.
            case["decision"] = editorial.decision(case["total_score"], gate_pass)
            if ed.get("decision") and ed["decision"] != case["decision"] and self.log:
                self.log.info("    model said %s, ruleset says %s (%.0f/100)",
                              ed["decision"], case["decision"], case["total_score"])
            case["eligible"], case["ineligible_reason"] = _check_gates(case, gates)
            # The model's quotes are verbatim; its timestamps are not (Rodriguez,
            # 2026-09-06: every time was ~590 s late, the money moment and the
            # hook fell outside the case and the cold open / thumbnail frame
            # were lost). Anchor each timestamp to where its quote sits.
            for note in ground_case_times(case, transcript.words):
                if self.log:
                    self.log.info("    grounded: %s", note)
            # Cache/version stamp (BOYD_EDITORIAL_V2 stabilisation): the score
            # prompt's own version string. Anything scored under a different
            # string is stale to analyze_docket() and run_case().
            case[RUBRIC_VERSION_KEY] = self.prompt_versions.get("score_cases", "unknown")
            scored.append(case)
            if self.log:
                self.log.info("    %s\n%s", case.get("defendant_name", "?"),
                              _indent(editorial.rationale_block(case)))

        scored.sort(key=lambda c: (c["eligible"], c["total_score"]), reverse=True)
        for i, case in enumerate(scored, start=1):
            case["rank"] = i if case["eligible"] else None
        return scored

    # ---------------------------------------------------------------- stage 3

    def package(
        self, transcript: Transcript, case: dict[str, Any], meta: dict[str, Any], spec_version: str
    ) -> dict[str, Any]:
        _, _, template = prompt_text("package_post")
        # The legacy one-pair packager writes the same titles and thumbnail copy
        # the Producer plans elsewhere, so it carries the same current rules.
        rules = stage_rules.load_context()
        user = template.format(
            spec_version=spec_version,
            court=self.cfg.require("source.court"),
            docket_date=meta.get("docket_date", "unknown"),
            source_url=meta["url"],
            start_timestamp=hhmmss(case["start_s"]),
            case_json=json.dumps(case, ensure_ascii=False, indent=2),
            case_transcript=transcript.text_between(case["start_s"], case["end_s"]),
        )
        pkg = self._call("package_post", user, PACKAGE_SCHEMA, rules)

        # CONTENT_SPEC §9 — every string returned here is a text surface, and
        # text surfaces are censored even though the audio is not. Done before
        # the length checks so the asterisks are inside the character count.
        for field in (
            "hook_line", "summary", "longform_title", "short_title",
            "thumbnail_quote", "title_support_quote", "packaging_rationale",
        ):
            if isinstance(pkg.get(field), str):
                pkg[field] = censor(pkg[field])

        # BOYD_EDITORIAL_V2 advisory checks, logged never enforced: the title
        # families/hype/docket flags and the title<->thumbnail overlap.
        if self.log:
            for flag in editorial.title_flags(pkg["longform_title"]):
                self.log.info("    title flag: %s", flag)
            for flag in editorial.quote_flags(pkg["thumbnail_quote"]):
                self.log.info("    thumbnail quote flag: %s", flag)
            if editorial.quote_repeats_title(pkg["thumbnail_quote"], pkg["longform_title"]):
                self.log.info("    thumbnail quote repeats the title — they should be two halves of one idea")
            fam = editorial.title_family(pkg["longform_title"])
            self.log.info("    title family: %s | %s", fam or "unrecognised", pkg["longform_title"])

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


# --------------------------------------------------------------- cache version

RUBRIC_VERSION_KEY = "rubric_version"


def current_rubric_version() -> str:
    """The score prompt's version string — the one cache/version mechanism."""
    version, _, _ = prompt_text("score_cases")
    return version


def score_cache_load(payload: Any, version: str) -> tuple[list[dict[str, Any]] | None, str]:
    """Return (cases, reason). cases is None when the cache is stale.

    Accepted shape: {"rubric_version": <version>, "cases": [...]} where every
    case carries the same stamp. A bare list is the pre-V2 cache format and is
    stale by construction (it was scored under the retired rubric).
    """
    if isinstance(payload, list):
        return None, "unversioned cache (retired rubric)"
    if not isinstance(payload, dict) or "cases" not in payload:
        return None, "unrecognised cache shape"
    v = payload.get(RUBRIC_VERSION_KEY)
    if v != version:
        return None, f"scored under {v!r}, current is {version!r}"
    cases = payload["cases"]
    bad = [c for c in cases if c.get(RUBRIC_VERSION_KEY) != version]
    if bad:
        return None, f"{len(bad)} case(s) carry a different rubric_version"
    return cases, "current"


def score_cache_dump(cases: list[dict[str, Any]], version: str) -> dict[str, Any]:
    return {RUBRIC_VERSION_KEY: version, "cases": cases}


def stage1_view(case: dict[str, Any]) -> dict[str, Any]:
    """The stage-1 (segment) fields of a stored case — what score() takes as input."""
    return {
        "start_s": float(case["start_s"]), "end_s": float(case["end_s"]),
        "defendant_name": case.get("defendant_name") or "unknown",
        "cause_number": case.get("cause_number") or "unknown",
        "charge": case.get("charge") or "unknown",
        "proceeding_type": case.get("proceeding_type") or "other",
        "outcome": case.get("outcome") or "unknown",
        "one_line": case.get("one_line") or (case.get("summary") or "")[:140] or "case",
        "continued": bool(case.get("continued", False)),
        "extraction_confidence": case.get("extraction_confidence") or "medium",
    }


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
    """Order is the rule: safety, then the editorial gate, then the score tier,
    then audio, then shortability. BOYD_EDITORIAL_V2 (2026-09-06)."""
    if gates.get("safety_must_pass", True) and not case["safety"]["safety_pass"]:
        rules = ", ".join(case["safety"]["safety_rule_violations"]) or "unspecified"
        return False, f"safety gate failed ({rules})"
    ed = case.get("editorial") or {}
    if gates.get("requires_editorial_gate", True) and (
        not ed.get("gate_pass", True) or ed.get("gate_failures")
    ):
        why = ", ".join(ed.get("gate_failures") or []) or "unspecified"
        return False, f"editorial gate failed ({why})"
    total = float(case["total_score"])
    make_at = float(gates.get("min_total_score", editorial.TIER_MAKE))
    hold_at = float(gates.get("hold_threshold", editorial.TIER_HOLD))
    if total < make_at:
        weakness = (ed.get("weakness") or "").strip()
        if total >= hold_at:
            return False, f"HOLD {total:g}/100 (below MAKE {make_at:g}) — {weakness or 'manual review'}"
        return False, f"SKIP {total:g}/100 (below HOLD {hold_at:g}) — {weakness or 'no story'}"
    if case["audio_quality"] < gates.get("min_audio_quality", 0):
        return False, f"audio quality {case['audio_quality']} below minimum"
    # `requires_self_contained` (retired 2026-08) and `requires_pushback`
    # (retired 2026-09-06, BOYD_EDITORIAL_V2) are no longer read. Both are
    # inert if present in config; clarity and story_engine cover them.
    if gates.get("requires_shortable") and not case.get("shortable"):
        # Not a quality judgement — the case is banked, not discarded. It just
        # cannot carry a publishing day on its own, because the short is what
        # brings anyone to the long-form.
        return False, "no short can be built from it (banked for later)"
    return True, ""


def _indent(block: str, pad: str = "      ") -> str:
    return "\n".join(pad + line for line in block.splitlines())


def _trim_title(title: str, limit: int) -> str:
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") or title[:limit]


_APOSTROPHES = "'’ʼ`´"


def _norm_tokens(s: str) -> list[str]:
    stripped = "".join(ch for ch in s if ch not in _APOSTROPHES)
    flattened = "".join(ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in stripped)
    return flattened.split()


def find_quote_time(words: Sequence[Any], quote: str, lo: float, hi: float,
                    max_tokens: int = 8, min_tokens: int = 4) -> float | None:
    """Start time of the first place inside [lo, hi] where the quote's opening
    tokens appear consecutively in the transcript (normalised like
    _quote_appears). Tries the first `max_tokens`, then shorter prefixes down
    to `min_tokens`. None when the quote is not there."""
    q = _norm_tokens(quote or "")
    if len(q) < 3:
        return None
    seq: list[tuple[float, str]] = []
    for w in words:
        t = float(w["t"] if isinstance(w, dict) else w.t)
        if lo <= t <= hi:
            for tok in _norm_tokens(w["w"] if isinstance(w, dict) else w.w):
                seq.append((t, tok))
    toks = [tok for _, tok in seq]
    for n in range(min(max_tokens, len(q)), min(min_tokens, len(q)) - 1, -1):
        head = q[:n]
        for i in range(len(toks) - n + 1):
            if toks[i:i + n] == head:
                return seq[i][0]
    return None


# Straight double quotes or curly quotes delimit a quoted span; the straight
# apostrophe does not, since it lives inside the quotes ("Don't put Jesus on me").
_QUOTED = re.compile(r"[\"“]([^\"”]{12,}?)[\"”]|‘([^’]{12,}?)’")


def ground_case_times(case: dict[str, Any], words: Sequence[Any], pad_s: float = 90.0,
                      tolerance_s: float = 5.0) -> list[str]:
    """Re-anchor hook_start_s, editorial.money_moment_s and the short_segments
    to where their quotes are found in the transcript, searching the case
    span plus `pad_s`. A timestamp is only moved when the quote is found and
    the model's value is more than `tolerance_s` away. Returns notes."""
    notes: list[str] = []
    try:
        lo, hi = float(case["start_s"]) - pad_s, float(case["end_s"]) + pad_s
    except (KeyError, TypeError, ValueError):
        return notes

    def moved(label: str, old: Any, new: float) -> bool:
        try:
            if old is not None and abs(float(old) - new) <= tolerance_s:
                return False
        except (TypeError, ValueError):
            pass
        notes.append(f"{label}: {old} -> {new:.1f}")
        return True

    hq = case.get("hook_quote")
    if hq:
        t = find_quote_time(words, hq, lo, hi)
        if t is not None and moved("hook_start_s", case.get("hook_start_s"), t):
            case["hook_start_s"] = t
    ed = case.get("editorial") or {}
    mm = ed.get("money_moment")
    if isinstance(mm, str) and mm:
        spans = sorted((a or b for a, b in _QUOTED.findall(mm)), key=len, reverse=True) or [mm]
        for span in spans:
            t = find_quote_time(words, span, lo, hi)
            if t is not None:
                if moved("editorial.money_moment_s", ed.get("money_moment_s"), t):
                    ed["money_moment_s"] = t
                break
    for seg in case.get("short_segments") or []:
        q = seg.get("quote") if isinstance(seg, dict) else None
        if not q:
            continue
        t = find_quote_time(words, q, lo, hi)
        if t is None:
            continue
        try:
            dur = max(2.0, float(seg.get("end_s", 0)) - float(seg.get("start_s", 0)))
        except (TypeError, ValueError):
            dur = 8.0
        if moved(f"short_segments.{seg.get('beat')}", seg.get("start_s"), t):
            seg["start_s"], seg["end_s"] = t, round(t + dur, 3)
    return notes


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
