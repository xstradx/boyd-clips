"""PRODUCER BRAIN V1 — evidence-grounded planning before any edit is made.

This module is deliberately pure.  It prepares the request an editorial model
would receive, validates the returned plan against the locally cached hearing,
and renders a human review report.  It does not construct an LLM backend, make
network calls, render media, generate thumbnails, or publish anything.

The daily pipeline calls this layer after all same-case hearing windows and the
cached transcript have been resolved. The module itself remains pure: the
Analyzer owns the one bounded model call and Pipeline owns rendering and review.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import ROOT, prompt_text
from .llm import validate as validate_schema
from .transcribe import Transcript, hhmmss


RULESET = "PRODUCER_BRAIN_V1"
PROMPT_NAME = "producer_brain_v1"
PROMPT_VERSION = "1.3.3+PRODUCER_BRAIN_V1"


def _object(properties: dict[str, Any], required: Sequence[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required if required is not None else properties),
        "additionalProperties": False,
    }


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


_STR = {"type": "string"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}

EVIDENCE_SCHEMA = _object({
    "source_type": {"type": "string", "enum": ["hearing_transcript", "public_record"]},
    "source_id": _STR,
    "start_s": _NUM,
    "end_s": _NUM,
    "quote": _STR,
    "note": _STR,
})

VISUAL_EVIDENCE_SCHEMA = _object({
    "id": _STR,
    "timestamp_s": _NUM,
    "source_path": _STR,
    "subject": {"type": "string", "enum": ["defendant", "boyd", "two_shot"]},
    "description": _STR,
    "same_hearing": _BOOL,
})

PUBLIC_RECORD_SCHEMA = _object({
    "id": _STR,
    "label": _STR,
    "source_url": _STR,
    "excerpt": _STR,
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
})

CASE_SOURCE_SCHEMA = _object({
    "internal_case_id": _STR,
    "video_id": _STR,
    "source_url": _STR,
    "docket_date": _STR,
    "hearing_start_s": _NUM,
    "hearing_end_s": _NUM,
    "defendant_name_internal": _STR,
    "cause_number_internal": _STR,
    "proceeding_type": _STR,
    "guilt_posture": _STR,
    "transcript_path": _STR,
    "transcript_sha256": _STR,
    "transcript_source": _STR,
    "story_windows": _array(_array(_NUM)),
}, required=(
    "internal_case_id", "video_id", "source_url", "docket_date",
    "hearing_start_s", "hearing_end_s", "defendant_name_internal",
    "cause_number_internal", "proceeding_type", "guilt_posture",
    "transcript_path", "transcript_sha256", "transcript_source",
))

MATERIAL_SCHEMA = _object({
    "ruleset": {"type": "string", "enum": [RULESET]},
    "case_source": CASE_SOURCE_SCHEMA,
    "existing_editorial": _object({
        "selection_score": _NUM,
        "selection_decision": _STR,
        "story_angle": _STR,
        "money_moment": _STR,
        "money_moment_s": _NUM,
    }),
    "visual_evidence": _array(VISUAL_EVIDENCE_SCHEMA),
    "public_records": _array(PUBLIC_RECORD_SCHEMA),
})

ARC_BEAT_SCHEMA = _object({
    "summary": _STR,
    "start_s": _NUM,
    "end_s": _NUM,
    "sources": _array(EVIDENCE_SCHEMA),
})

FACT_RELEVANCE_SCHEMA = _object({
    "why_here": _STR,
    "payoff_connection": _STR,
    "story_stakes": _STR,
    "mentioned_by": _STR,
})

INTRO_FACT_SCHEMA = _object({
    "id": _STR,
    "fact": _STR,
    "sources": _array(EVIDENCE_SCHEMA),
    "why_it_matters": _STR,
    "relevance": FACT_RELEVANCE_SCHEMA,
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
})

EXCLUDED_FACT_SCHEMA = _object({
    "fact": _STR,
    "sources": _array(EVIDENCE_SCHEMA),
    "reason": _STR,
})

MOMENT_SCHEMA = _object({
    "start_s": _NUM,
    "end_s": _NUM,
    "description": _STR,
    "why_it_matters": _STR,
    "sources": _array(EVIDENCE_SCHEMA),
})

TITLE_ANGLE_SCHEMA = _object({
    "direction": _STR,
    "title": _STR,
    "story_promise": _STR,
    "sources": _array(EVIDENCE_SCHEMA),
})

THUMBNAIL_SCORES_SCHEMA = _object({
    "story_clarity": _NUM,
    "scroll_stop": _NUM,
    "curiosity": _NUM,
    "realism": _NUM,
    "mobile_readability": _NUM,
    "title_pairing": _NUM,
    "emotion": _NUM,
    "distinctiveness": _NUM,
})

THUMBNAIL_SCHEMA = _object({
    "concept": {"type": "string", "enum": ["A", "B", "C"]},
    "hypothesis": {
        "type": "string",
        "enum": ["court_of_justice_control", "confrontation", "reaction_story_moment"],
    },
    "layout": _STR,
    "subjects_and_expression": _STR,
    "background": _STR,
    "text": _STR,
    "typography": _STR,
    "lighting": _STR,
    "arrow": _STR,
    "defendant_frame_id": _STR,
    "boyd_frame_id": _STR,
    "quote_sources": _array(EVIDENCE_SCHEMA),
    "reason_to_click": _STR,
    "curiosity_gap": _STR,
    "title_pairing": _STR,
    "credibility_risks": _STR,
    "scores": THUMBNAIL_SCORES_SCHEMA,
    "total_score": _NUM,
    "hard_fail": _BOOL,
})

SHORT_SEGMENT_SCHEMA = _object({
    "edit_order": {"type": "integer"},
    "source_order": {"type": "integer"},
    "role": _STR,
    "start_s": _NUM,
    "end_s": _NUM,
    "quote": _STR,
    "description": _STR,
    "sources": _array(EVIDENCE_SCHEMA),
})

CONFIDENCE_SCHEMA = _object({
    "score": _NUM,
    "uncertain": _BOOL,
    "reason": _STR,
})

PLAN_SCHEMA = _object({
    "ruleset": {"type": "string", "enum": [RULESET]},
    "case_source": CASE_SOURCE_SCHEMA,
    "story_summary": _STR,
    "video_decision": _object({
        "decision": {"type": "string", "enum": ["MAKE", "HOLD", "SKIP"]},
        "watchability": _STR,
        "limitation": _STR,
    }),
    "story_arc": _object({
        "setup": ARC_BEAT_SCHEMA,
        "escalation": ARC_BEAT_SCHEMA,
        "payoff": ARC_BEAT_SCHEMA,
    }),
    "big_moments": _array(MOMENT_SCHEMA),
    "cold_open": _object({
        "start_s": _NUM,
        "end_s": _NUM,
        "exact_audio": _STR,
        "why_it_teases": _STR,
        "spoiler_guard": _STR,
        "sources": _array(EVIDENCE_SCHEMA),
    }),
    "intro_angle": _STR,
    "intro_facts": _array(INTRO_FACT_SCHEMA),
    "excluded_facts": _array(EXCLUDED_FACT_SCHEMA),
    "sample_intro_narration": _object({
        "text": _STR,
        "fact_ids": _array(_STR),
    }),
    "mid_video_context_breaks": _array(_object({
        "timestamp_s": _NUM,
        "what_needs_explaining": _STR,
        "proposed_narration": _STR,
        "why_it_improves": _STR,
        "sources": _array(EVIDENCE_SCHEMA),
    })),
    "title_angles": _array(TITLE_ANGLE_SCHEMA),
    "thumbnail_plan": _array(THUMBNAIL_SCHEMA),
    "short_plan": _object({
        "ruleset": {"type": "string", "enum": ["SHORTS_BRAIN_V1"]},
        "decision": {"type": "string", "enum": ["MAKE", "HOLD", "SKIP"]},
        "watchability": _STR,
        "limitation": _STR,
        "title": _STR,
        "hook": _STR,
        "hook_start_s": _NUM,
        "hook_end_s": _NUM,
        "sequence": _array(SHORT_SEGMENT_SCHEMA),
        "payoff": _STR,
        "longform_connection": _STR,
        "chronology_strategy": {
            "type": "string",
            "enum": ["chronological", "payoff_first_recontextualized"],
        },
        "truthfulness_guard": _STR,
    }),
    "longform_end_cta": _object({
        "decision": {"type": "string", "enum": ["USE", "NO_CTA"]},
        "placement": {"type": "string", "enum": ["after_payoff_tail", "none"]},
        "payoff_end_s": _NUM,
        "breathing_room_s": _NUM,
        "end_screen_duration_s": _NUM,
        "spoken_line": _STR,
        "on_screen_text": _STR,
        "youtube_elements": _array({
            "type": "string",
            "enum": ["related_video", "subscribe"],
        }),
        "next_video_strategy": _STR,
        "visual_direction": _STR,
        "reason": _STR,
        "fallback": _STR,
    }),
    "package_coherence_check": _STR,
    "producer_confidence": _object({
        "story_selection": CONFIDENCE_SCHEMA,
        "cold_open": CONFIDENCE_SCHEMA,
        "factual_context": CONFIDENCE_SCHEMA,
        "title_package": CONFIDENCE_SCHEMA,
    }),
    "alternative_story_angle": _object({
        "angle": _STR,
        "why_legitimate": _STR,
        "why_ranked_lower": _STR,
    }),
})

# OpenAI structured outputs require every declared object property to appear in
# `required`. Local validation keeps story_windows optional so versioned review
# fixtures from before recalled-window integration remain readable.
CODEX_PLAN_SCHEMA = deepcopy(PLAN_SCHEMA)
CODEX_PLAN_SCHEMA["properties"]["case_source"]["required"] = list(
    CODEX_PLAN_SCHEMA["properties"]["case_source"]["properties"]
)


THUMBNAIL_LIMITS = {
    "story_clarity": 20,
    "scroll_stop": 15,
    "curiosity": 15,
    "realism": 15,
    "mobile_readability": 15,
    "title_pairing": 10,
    "emotion": 5,
    "distinctiveness": 5,
}

REPORT_SECTIONS = (
    "STORY SUMMARY",
    "WHY THIS IS OR IS NOT A VIDEO",
    "STORY ARC",
    "BIG MOMENTS",
    "BEST COLD OPEN",
    "INTRO ANGLE",
    "INTRO FACTS",
    "EXCLUDED FACTS",
    "SAMPLE INTRO NARRATION",
    "MID-VIDEO CONTEXT BREAKS",
    "TITLE ANGLES",
    "THUMBNAIL PLAN",
    "SHORTS BRAIN V1 PLAN",
    "PACKAGE COHERENCE CHECK",
    "PRODUCER CONFIDENCE",
    "ALTERNATIVE STORY ANGLE",
    "LONG-FORM END CTA PLAN",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def validate_material(material: Mapping[str, Any], root: Path = ROOT) -> list[str]:
    errors = validate_schema(material, MATERIAL_SCHEMA)
    if errors:
        return errors
    case = material["case_source"]
    if float(case["hearing_start_s"]) >= float(case["hearing_end_s"]):
        errors.append("$.case_source: hearing_start_s must be before hearing_end_s")
    windows = case.get("story_windows") or [[case["hearing_start_s"], case["hearing_end_s"]]]
    previous_end = None
    for i, window in enumerate(windows):
        if len(window) != 2 or float(window[0]) >= float(window[1]):
            errors.append(f"$.case_source.story_windows[{i}]: expected increasing [start, end]")
            continue
        if previous_end is not None and float(window[0]) < previous_end:
            errors.append("$.case_source.story_windows: windows must be chronological and non-overlapping")
        if float(window[0]) < float(case["hearing_start_s"]) or float(window[1]) > float(case["hearing_end_s"]):
            errors.append(f"$.case_source.story_windows[{i}]: outside hearing envelope")
        previous_end = float(window[1])
    transcript_path = root / case["transcript_path"]
    if not transcript_path.is_file():
        errors.append(f"$.case_source.transcript_path: missing {transcript_path}")
    elif sha256_file(transcript_path) != case["transcript_sha256"]:
        errors.append("$.case_source.transcript_sha256: cached transcript digest mismatch")
    ids = [row["id"] for row in material["visual_evidence"]]
    if len(ids) != len(set(ids)):
        errors.append("$.visual_evidence: ids must be unique")
    record_ids = [row["id"] for row in material["public_records"]]
    if len(record_ids) != len(set(record_ids)):
        errors.append("$.public_records: ids must be unique")
    for i, row in enumerate(material["visual_evidence"]):
        t = float(row["timestamp_s"])
        windows = case.get("story_windows") or [[case["hearing_start_s"], case["hearing_end_s"]]]
        if not any(float(window[0]) <= t <= float(window[1]) for window in windows):
            errors.append(f"$.visual_evidence[{i}].timestamp_s: outside hearing")
        if not row["same_hearing"]:
            errors.append(f"$.visual_evidence[{i}].same_hearing: cross-hearing frames are forbidden")
    return errors


def load_transcript(material: Mapping[str, Any], root: Path = ROOT) -> Transcript:
    errors = validate_material(material, root=root)
    if errors:
        raise ValueError("invalid Producer Brain material: " + "; ".join(errors))
    path = root / material["case_source"]["transcript_path"]
    transcript = Transcript.from_json(path.read_text(encoding="utf-8"))
    if transcript.video_id != material["case_source"]["video_id"]:
        raise ValueError("cached transcript video_id does not match case source")
    return transcript


def material_from_pipeline(
    case_key: str,
    case: Mapping[str, Any],
    meta: Mapping[str, Any],
    transcript: Transcript,
    transcript_path: Path,
    visual_evidence: Iterable[Mapping[str, Any]] = (),
    public_records: Iterable[Mapping[str, Any]] = (),
    root: Path = ROOT,
) -> dict[str, Any]:
    """Adapt existing Pipeline/Analyzer values without changing their owners."""
    path = transcript_path.resolve()
    try:
        rel = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("transcript_path must live under the project root") from exc
    ed = case.get("editorial") or {}
    material = {
        "ruleset": RULESET,
        "case_source": {
            "internal_case_id": case_key,
            "video_id": transcript.video_id,
            "source_url": str(meta.get("url") or ""),
            "docket_date": str(meta.get("docket_date") or "unknown"),
            "hearing_start_s": float(case["start_s"]),
            "hearing_end_s": float(case["end_s"]),
            "defendant_name_internal": str(case.get("defendant_name") or "unknown"),
            "cause_number_internal": str(case.get("cause_number") or "unknown"),
            "proceeding_type": str(case.get("proceeding_type") or "other"),
            "guilt_posture": str(case.get("guilt_posture") or "unclear"),
            "transcript_path": rel,
            "transcript_sha256": sha256_file(path),
            "transcript_source": transcript.source,
        },
        "existing_editorial": {
            "selection_score": float(case.get("total_score") or 0.0),
            "selection_decision": str(case.get("decision") or ""),
            "story_angle": str(ed.get("story_angle") or ""),
            "money_moment": str(ed.get("money_moment") or ""),
            "money_moment_s": float(ed.get("money_moment_s") or case["start_s"]),
        },
        "visual_evidence": [dict(row) for row in visual_evidence],
        "public_records": [dict(row) for row in public_records],
    }
    if case.get("story_windows"):
        material["case_source"]["story_windows"] = [
            [float(window[0]), float(window[1])]
            for window in case["story_windows"]
        ]
    errors = validate_material(material, root=root)
    if errors:
        raise ValueError("invalid Producer Brain material: " + "; ".join(errors))
    return material


def prepare_request(material: Mapping[str, Any], transcript: Transcript) -> dict[str, Any]:
    """Return a backend-neutral request; calling a model is intentionally external."""
    errors = validate_material(material)
    if errors:
        raise ValueError("invalid Producer Brain material: " + "; ".join(errors))
    case = material["case_source"]
    if transcript.video_id != case["video_id"]:
        raise ValueError("transcript video_id does not match Producer Brain material")
    version, system, template = prompt_text(PROMPT_NAME)
    if version != PROMPT_VERSION:
        raise ValueError(f"{PROMPT_NAME} version {version!r} does not match code {PROMPT_VERSION!r}")
    # Only the selected hearing belongs in this pre-cut decision.  This keeps a
    # long docket's unrelated defendants out of both editorial reasoning and
    # public-record context.
    windows = case.get("story_windows") or [[case["hearing_start_s"], case["hearing_end_s"]]]
    selected_parts = []
    for window in windows:
        words = transcript.slice(float(window[0]), float(window[1]))
        selected_parts.append(
            Transcript(video_id=transcript.video_id, words=words, source=transcript.source).render_for_llm()
        )
    selected = "\n".join(part for part in selected_parts if part)
    prompt_material = deepcopy(material)
    prompt_case = prompt_material["case_source"]
    prompt_case.setdefault(
        "story_windows",
        [[prompt_case["hearing_start_s"], prompt_case["hearing_end_s"]]],
    )
    user = template.format(
        case_material=json.dumps(prompt_material, ensure_ascii=False, indent=2),
        hearing_transcript=selected,
    )
    return {"version": version, "system": system, "user": user, "schema": deepcopy(CODEX_PLAN_SCHEMA)}


def _timestamp_line_inside(line: str, start_s: float, end_s: float) -> bool:
    match = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\]", line)
    if not match:
        return False
    h, m, s = map(int, match.groups())
    value = h * 3600 + m * 60 + s
    return start_s - 10 <= value <= end_s


def package_from_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one validated Producer Brain plan to the existing render contract."""
    titles = list(plan["title_angles"])
    thumbs = {row["concept"]: row for row in plan["thumbnail_plan"]}
    pairs = []
    # A/B/C labels remain one contract from planning through rendering.
    title_for_output = {label: title for label, title in zip("ABC", titles)}
    for label in "ABC":
        title = title_for_output[label]
        thumb = thumbs[label]
        pairs.append({
            "label": label,
            "title": str(title["title"]),
            "title_direction": str(title["direction"]),
            "story_promise": str(title["story_promise"]),
            "thumbnail_text": str(thumb["text"]),
            "thumbnail_hypothesis": str(thumb["hypothesis"]),
            "thumbnail_direction": {
                key: thumb[key]
                for key in (
                    "layout", "subjects_and_expression", "background", "typography",
                    "lighting", "arrow", "reason_to_click", "curiosity_gap",
                    "title_pairing", "credibility_risks",
                )
            },
            "reason": str(thumb["title_pairing"]),
        })

    primary = pairs[0]
    quote = primary["thumbnail_text"].strip()
    if not quote:
        words = str(plan["cold_open"]["exact_audio"]).split()
        quote = " ".join(words[: min(6, len(words))]).strip()
    quote_words = quote.split()
    yellow = " ".join(quote_words[max(1, len(quote_words) // 2):]) or quote
    title_support = ""
    sources = titles[0].get("sources") or []
    if sources:
        title_support = str(sources[0].get("quote") or "")

    case = plan["case_source"]
    hook = str(plan["short_plan"]["hook"])
    return {
        "hook_line": hook,
        "hook_verified": True,
        "summary": str(plan["story_summary"]),
        "longform_title": str(primary["title"]),
        "short_title": str(plan["short_plan"]["title"]),
        "thumbnail_quote": quote,
        "thumbnail_quote_yellow": yellow,
        "title_support_quote": title_support,
        "guilt_posture_check": f"Packaged as {case['guilt_posture']}.",
        "packaging_rationale": str(primary["reason"]),
        "packaging_pairs": pairs,
        "producer_brain": dict(plan),
    }


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower()))


def normalise_source_ids(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalise the fixed transcript source ID without changing evidence.

    Hearing evidence has exactly one possible source in this stage. Quotes and
    time ranges stay untouched and still fail closed in ``validate_plan``.
    """
    result = deepcopy(dict(plan))

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("source_type") == "hearing_transcript" and "source_id" in value:
                value["source_id"] = "hearing-transcript"
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    return result


def _quote_in_text(quote: str, text: str) -> bool:
    # An explicit ellipsis means "ordered omission", not invented glue. This
    # keeps citations readable while requiring every retained fragment to
    # occur, in order, inside the cited evidence window.
    haystack = _normalise(text)
    fragments = [
        _normalise(fragment)
        for fragment in re.split(r"(?:\.{3}|…)", quote)
        if _normalise(fragment)
    ]
    if not fragments:
        return False
    cursor = 0
    for fragment in fragments:
        found = haystack.find(fragment, cursor)
        if found < 0:
            return False
        cursor = found + len(fragment)
    return True


def _exact_quote_range(
    quote: str,
    transcript: Transcript,
    windows: Sequence[Sequence[float]],
    preferred_midpoint: float,
) -> tuple[float, float] | None:
    """Locate exact quoted words and return a word-timed, audio-safe range."""
    fragments = [
        _normalise(fragment)
        for fragment in re.split(r"(?:\.{3}|…)", quote)
        if _normalise(fragment)
    ]
    if not fragments:
        return None

    candidates: list[tuple[float, float]] = []
    for raw_window in windows:
        window_start, window_end = float(raw_window[0]), float(raw_window[1])
        words = transcript.slice(window_start, window_end)
        pieces: list[str] = []
        spans: list[tuple[int, int, int]] = []
        cursor = 0
        for index, word in enumerate(words):
            piece = _normalise(word.w)
            if not piece:
                continue
            if pieces:
                cursor += 1
            start = cursor
            pieces.append(piece)
            cursor += len(piece)
            spans.append((start, cursor, index))
        haystack = " ".join(pieces)
        if not haystack:
            continue

        first_cursor = 0
        while True:
            first = haystack.find(fragments[0], first_cursor)
            if first < 0:
                break
            end = first + len(fragments[0])
            valid = True
            for fragment in fragments[1:]:
                found = haystack.find(fragment, end)
                if found < 0:
                    valid = False
                    break
                end = found + len(fragment)
            if valid:
                first_word = next((idx for lo, hi, idx in spans if lo <= first < hi), None)
                last_pos = max(first, end - 1)
                last_word = next((idx for lo, hi, idx in spans if lo <= last_pos < hi), None)
                if first_word is not None and last_word is not None:
                    start_s = max(window_start, float(words[first_word].t) - 0.15)
                    if last_word + 1 < len(words):
                        end_s = min(window_end, float(words[last_word + 1].t))
                    else:
                        end_s = min(window_end, float(words[last_word].t) + 0.8)
                    candidates.append((start_s, end_s))
            first_cursor = first + 1

    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(((row[0] + row[1]) / 2) - preferred_midpoint))


def align_transcript_ranges(
    plan: Mapping[str, Any], material: Mapping[str, Any], transcript: Transcript
) -> dict[str, Any]:
    """Snap exact transcript quotes from coarse model lines to word timings.

    The model sees transcript lines grouped into roughly ten-second buckets, so
    its ranges are necessarily approximate. This function changes timings only
    when the quoted words occur exactly inside an authorized hearing window.
    Paraphrases and invented wording remain untouched and fail validation.
    """
    result = deepcopy(dict(plan))
    case = material["case_source"]
    windows = case.get("story_windows") or [[case["hearing_start_s"], case["hearing_end_s"]]]

    def align(row: dict[str, Any], quote_key: str = "quote") -> None:
        if quote_key not in row or "start_s" not in row or "end_s" not in row:
            return
        lo, hi = float(row["start_s"]), float(row["end_s"])
        if _quote_in_text(str(row[quote_key]), transcript.text_between(max(0.0, lo - 0.4), hi + 0.4)):
            return
        found = _exact_quote_range(str(row[quote_key]), transcript, windows, (lo + hi) / 2)
        if found is not None:
            row["start_s"], row["end_s"] = found

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("source_type") == "hearing_transcript":
                align(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result)
    cold = result.get("cold_open")
    if isinstance(cold, dict):
        align(cold, "exact_audio")
    short = result.get("short_plan")
    if isinstance(short, dict):
        for row in short.get("sequence", []):
            if isinstance(row, dict):
                align(row)
        if short.get("sequence"):
            first = short["sequence"][0]
            hook_text = str(short.get("hook") or "")
            hook_window = transcript.text_between(
                float(short.get("hook_start_s") or 0) - 0.4,
                float(short.get("hook_end_s") or 0) + 0.4,
            )
            if not _quote_in_text(hook_text, hook_window):
                first_quote = str(first.get("quote") or "")
                first_window = transcript.text_between(
                    float(first.get("start_s") or 0) - 0.4,
                    float(first.get("end_s") or 0) + 0.4,
                )
                if _quote_in_text(first_quote, first_window):
                    short["hook"] = first_quote
            if short.get("hook") == first.get("quote"):
                short["hook_start_s"] = first["start_s"]
                short["hook_end_s"] = first["end_s"]
    return result


def _name_tokens(name: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", name.lower()) if len(token) >= 2}


def _evidence_errors(
    ref: Mapping[str, Any],
    path: str,
    material: Mapping[str, Any],
    transcript: Transcript,
) -> list[str]:
    errors: list[str] = []
    case = material["case_source"]
    if ref["source_type"] == "hearing_transcript":
        if ref["source_id"] != "hearing-transcript":
            errors.append(f"{path}.source_id: expected hearing-transcript")
        lo, hi = float(ref["start_s"]), float(ref["end_s"])
        if lo > hi:
            errors.append(f"{path}: start_s must be before end_s")
        if not _inside_hearing(lo, hi, case):
            errors.append(f"{path}: transcript source outside hearing")
        window = transcript.text_between(max(lo - 0.4, 0), hi + 0.4)
        if not _quote_in_text(str(ref["quote"]), window):
            errors.append(f"{path}.quote: not found in cited transcript range")
    else:
        records = {row["id"]: row for row in material["public_records"]}
        record = records.get(ref["source_id"])
        if record is None:
            errors.append(f"{path}.source_id: unknown public record")
        elif not _quote_in_text(str(ref["quote"]), str(record["excerpt"])):
            errors.append(f"{path}.quote: not found in cited public record excerpt")
    return errors


def _check_sources(
    rows: Sequence[Mapping[str, Any]],
    path: str,
    material: Mapping[str, Any],
    transcript: Transcript,
    required: bool = True,
) -> list[str]:
    errors: list[str] = []
    if required and not rows:
        return [f"{path}: at least one evidence source is required"]
    for i, row in enumerate(rows):
        errors.extend(_evidence_errors(row, f"{path}[{i}]", material, transcript))
    return errors


def _inside_hearing(start_s: float, end_s: float, case: Mapping[str, Any]) -> bool:
    if float(start_s) > float(end_s):
        return False
    windows = case.get("story_windows") or [[case["hearing_start_s"], case["hearing_end_s"]]]
    return any(
        float(window[0]) <= float(start_s) <= float(end_s) <= float(window[1])
        for window in windows
    )


def validate_plan(
    plan: Mapping[str, Any], material: Mapping[str, Any], transcript: Transcript
) -> list[str]:
    """Validate schema, provenance, chronology, anonymity, and package shape."""
    errors = validate_schema(plan, PLAN_SCHEMA)
    if errors:
        return errors
    errors.extend(validate_material(material))
    if errors:
        return errors

    case = material["case_source"]
    if transcript.video_id != case["video_id"]:
        errors.append("$.transcript.video_id: does not match input material")
    pcase = plan["case_source"]
    for field in case:
        if pcase.get(field) != case[field]:
            errors.append(f"$.case_source.{field}: does not match input material")

    arc = plan["story_arc"]
    arc_times = []
    for name in ("setup", "escalation", "payoff"):
        beat = arc[name]
        arc_times.append(float(beat["start_s"]))
        if not _inside_hearing(beat["start_s"], beat["end_s"], case):
            errors.append(f"$.story_arc.{name}: range outside hearing")
        errors.extend(_check_sources(beat["sources"], f"$.story_arc.{name}.sources", material, transcript))
    if arc_times != sorted(arc_times):
        errors.append("$.story_arc: long-form setup, escalation, and payoff must be chronological")

    moments = plan["big_moments"]
    if not moments:
        errors.append("$.big_moments: at least one moment is required")
    moment_starts = []
    for i, row in enumerate(moments):
        moment_starts.append(float(row["start_s"]))
        if not _inside_hearing(row["start_s"], row["end_s"], case):
            errors.append(f"$.big_moments[{i}]: range outside hearing")
        errors.extend(_check_sources(row["sources"], f"$.big_moments[{i}].sources", material, transcript))
    if moment_starts != sorted(moment_starts):
        errors.append("$.big_moments: list must follow source chronology")

    cold = plan["cold_open"]
    duration = float(cold["end_s"]) - float(cold["start_s"])
    if not 5.0 <= duration <= 12.0:
        errors.append("$.cold_open: duration must be 5-12 seconds")
    if not _inside_hearing(cold["start_s"], cold["end_s"], case):
        errors.append("$.cold_open: range outside hearing")
    errors.extend(_check_sources(cold["sources"], "$.cold_open.sources", material, transcript))
    if not _quote_in_text(cold["exact_audio"], transcript.text_between(cold["start_s"] - 0.4, cold["end_s"] + 0.4)):
        errors.append("$.cold_open.exact_audio: not verbatim within the selected range")

    facts = plan["intro_facts"]
    if not 2 <= len(facts) <= 4:
        errors.append("$.intro_facts: include only the strongest 2-4 facts")
    fact_ids = [row["id"] for row in facts]
    if len(fact_ids) != len(set(fact_ids)):
        errors.append("$.intro_facts: ids must be unique")
    for i, row in enumerate(facts):
        errors.extend(_check_sources(row["sources"], f"$.intro_facts[{i}].sources", material, transcript))
    for i, row in enumerate(plan["excluded_facts"]):
        errors.extend(_check_sources(row["sources"], f"$.excluded_facts[{i}].sources", material, transcript))
    narration_ids = plan["sample_intro_narration"]["fact_ids"]
    if set(narration_ids) - set(fact_ids):
        errors.append("$.sample_intro_narration.fact_ids: unknown included fact id")

    title_angles = plan["title_angles"]
    if len(title_angles) != 3:
        errors.append("$.title_angles: exactly three directions are required")
    titles = [_normalise(row["title"]) for row in title_angles]
    directions = [_normalise(row["direction"]) for row in title_angles]
    if len(titles) != len(set(titles)) or len(directions) != len(set(directions)):
        errors.append("$.title_angles: titles and directions must be genuinely distinct")
    forbidden = _name_tokens(case["defendant_name_internal"])
    for i, row in enumerate(title_angles):
        title_tokens = set(re.findall(r"[a-z0-9]+", row["title"].lower()))
        if forbidden & title_tokens:
            errors.append(f"$.title_angles[{i}].title: contains defendant name")
        if len(row["title"]) > 70:
            errors.append(f"$.title_angles[{i}].title: exceeds 70 characters")
        if len(row["title"]) < 50:
            errors.append(f"$.title_angles[{i}].title: below 50 characters")
        errors.extend(_check_sources(row["sources"], f"$.title_angles[{i}].sources", material, transcript))

    visuals = {row["id"]: row for row in material["visual_evidence"]}
    thumbs = plan["thumbnail_plan"]
    expected = [
        ("A", "court_of_justice_control"),
        ("B", "confrontation"),
        ("C", "reaction_story_moment"),
    ]
    if [(row["concept"], row["hypothesis"]) for row in thumbs] != expected:
        errors.append("$.thumbnail_plan: require A Court of Justice control, B confrontation, C reaction/story")
    for i, row in enumerate(thumbs):
        from .thumbnail_copy import fragment_errors
        errors.extend(f"$.thumbnail_plan[{i}].text: {error}" for error in fragment_errors(row["text"]))
        paired = _normalise(row["title_pairing"])
        named_titles = [j for j, title in enumerate(title_angles)
                        if _normalise(title["title"]) in paired]
        if named_titles and i not in named_titles:
            errors.append(f"$.thumbnail_plan[{i}].title_pairing: names a different A/B/C title")
        defendant = visuals.get(row["defendant_frame_id"])
        if defendant is None or defendant["subject"] not in ("defendant", "two_shot"):
            errors.append(f"$.thumbnail_plan[{i}].defendant_frame_id: invalid defendant frame")
        boyd_id = row["boyd_frame_id"]
        if boyd_id:
            boyd = visuals.get(boyd_id)
            if boyd is None or boyd["subject"] not in ("boyd", "two_shot"):
                errors.append(f"$.thumbnail_plan[{i}].boyd_frame_id: invalid Boyd frame")
        if row["quote_sources"]:
            errors.extend(_check_sources(row["quote_sources"], f"$.thumbnail_plan[{i}].quote_sources", material, transcript))
        elif any(mark in row["text"] for mark in ('"', "“", "”")):
            errors.append(f"$.thumbnail_plan[{i}].quote_sources: quoted text requires evidence")
        scores = row["scores"]
        total = 0.0
        for key, maximum in THUMBNAIL_LIMITS.items():
            value = float(scores[key])
            total += value
            if not 0 <= value <= maximum:
                errors.append(f"$.thumbnail_plan[{i}].scores.{key}: outside 0-{maximum}")
        if abs(total - float(row["total_score"])) > 0.001:
            errors.append(f"$.thumbnail_plan[{i}].total_score: does not equal score sum")

    for i, row in enumerate(plan["mid_video_context_breaks"]):
        if not _inside_hearing(row["timestamp_s"], row["timestamp_s"], case):
            errors.append(f"$.mid_video_context_breaks[{i}].timestamp_s: outside hearing")
        errors.extend(_check_sources(row["sources"], f"$.mid_video_context_breaks[{i}].sources", material, transcript))

    short = plan["short_plan"]
    short_title = str(short["title"])
    if not 50 <= len(short_title) <= 70:
        errors.append("$.short_plan.title: must be 50-70 characters")
    if _normalise(short_title) in titles:
        errors.append("$.short_plan.title: must be written for the Short, not copied from a long-form title")
    if forbidden & set(re.findall(r"[a-z0-9]+", short_title.lower())):
        errors.append("$.short_plan.title: contains defendant name")
    if "#shorts" in short_title.lower():
        errors.append("$.short_plan.title: do not spend title space on #shorts")
    if not _inside_hearing(short["hook_start_s"], short["hook_end_s"], case):
        errors.append("$.short_plan: hook range outside hearing")
    elif not _quote_in_text(
        str(short["hook"]),
        transcript.text_between(float(short["hook_start_s"]) - 0.4, float(short["hook_end_s"]) + 0.4),
    ):
        errors.append("$.short_plan.hook: not verbatim in its cited range")
    segments = short["sequence"]
    orders = [row["edit_order"] for row in segments]
    if orders != list(range(1, len(segments) + 1)):
        errors.append("$.short_plan.sequence: edit_order must be consecutive from 1")
    source_orders = [row["source_order"] for row in segments]
    starts = [float(row["start_s"]) for row in segments]
    chronological = sorted(range(len(segments)), key=lambda index: (starts[index], index))
    expected_source_orders = [0] * len(segments)
    for rank, index in enumerate(chronological, start=1):
        expected_source_orders[index] = rank
    if source_orders != expected_source_orders:
        errors.append("$.short_plan.sequence: source_order must match transcript chronology")
    for i, row in enumerate(segments):
        if not _inside_hearing(row["start_s"], row["end_s"], case):
            errors.append(f"$.short_plan.sequence[{i}]: range outside hearing")
        errors.extend(_check_sources(row["sources"], f"$.short_plan.sequence[{i}].sources", material, transcript))
        if row["quote"] and not _quote_in_text(row["quote"], transcript.text_between(row["start_s"] - 0.4, row["end_s"] + 0.4)):
            errors.append(f"$.short_plan.sequence[{i}].quote: not verbatim in range")
    if short["chronology_strategy"] == "chronological" and starts != sorted(starts):
        errors.append("$.short_plan.sequence: chronological strategy has reordered segments")
    short_duration = sum(float(row["end_s"]) - float(row["start_s"]) for row in segments)
    if short["decision"] == "MAKE" and not 15.0 <= short_duration <= 59.0:
        errors.append("$.short_plan.sequence: MAKE duration must be 15-59 seconds")
    if short["decision"] == "MAKE" and len(segments) == 1:
        words = str(segments[0].get("quote") or "").split()
        role = str(segments[0].get("role") or "").lower()
        if len(words) < 20 or not ("hook" in role and ("payoff" in role or "cliffhanger" in role)):
            errors.append(
                "$.short_plan.sequence: one range must contain and label a complete multi-beat exchange"
            )
    if len(short["watchability"].strip()) < 20 or len(short["limitation"].strip()) < 20:
        errors.append("$.short_plan: Shorts Brain needs watchability and limitation reasoning")
    limitation = " ".join(str(short["limitation"]).lower().split())
    admitted_weak_opening = (
        "opening is reflective rather than" in limitation
        or "weak opening" in limitation
        or "slow opening" in limitation
        or "generic opening" in limitation
        or "routine opening" in limitation
        or "hook is weak" in limitation
        or "hook is not immediate" in limitation
        or "hook is delayed" in limitation
    )
    if short["decision"] == "MAKE" and admitted_weak_opening:
        errors.append("$.short_plan.limitation: MAKE admits a weak or delayed opening")
    guard_min = 50 if short["chronology_strategy"] == "chronological" else 80
    if len(short["truthfulness_guard"].strip()) < guard_min:
        errors.append("$.short_plan.truthfulness_guard: needs an explicit chronology and causality guard")

    cta_plan = plan["longform_end_cta"]
    cta_tail = float(cta_plan["payoff_end_s"])
    payoff_end = float(arc["payoff"]["end_s"])
    if cta_tail + 0.05 < payoff_end:
        errors.append("$.longform_end_cta.payoff_end_s: must not precede the verified payoff boundary")
    if not _inside_hearing(cta_tail, cta_tail, case):
        errors.append("$.longform_end_cta.payoff_end_s: must stay inside the authorized hearing")
    if plan["video_decision"]["decision"] in {"HOLD", "SKIP"} and cta_plan["decision"] != "NO_CTA":
        errors.append("$.longform_end_cta.decision: HOLD or SKIP must use NO_CTA")
    forbidden_cta = _name_tokens(case["defendant_name_internal"])
    cta_public_tokens = set(re.findall(
        r"[a-z0-9]+",
        f"{cta_plan['spoken_line']} {cta_plan['on_screen_text']}".lower(),
    ))
    if forbidden_cta & cta_public_tokens:
        errors.append("$.longform_end_cta: public CTA contains defendant name")
    if cta_plan["decision"] == "USE":
        if cta_plan["placement"] != "after_payoff_tail":
            errors.append("$.longform_end_cta.placement: CTA must begin after the payoff")
        if not 0.5 <= float(cta_plan["breathing_room_s"]) <= 1.5:
            errors.append("$.longform_end_cta.breathing_room_s: must be 0.5-1.5 seconds")
        if not 5.0 <= float(cta_plan["end_screen_duration_s"]) <= 8.0:
            errors.append("$.longform_end_cta.end_screen_duration_s: must be 5-8 seconds")
        if not 5 <= len(cta_plan["spoken_line"].split()) <= 18:
            errors.append("$.longform_end_cta.spoken_line: must be a concise 5-18 word sentence")
        if not 2 <= len(cta_plan["on_screen_text"].split()) <= 5:
            errors.append("$.longform_end_cta.on_screen_text: must be a concise 2-5 word label")
        elements = cta_plan["youtube_elements"]
        if len(elements) != len(set(elements)) or not 1 <= len(elements) <= 2:
            errors.append("$.longform_end_cta.youtube_elements: use one or two unique elements")
        if "related_video" not in elements:
            errors.append("$.longform_end_cta.youtube_elements: related_video is required")
        for field in ("next_video_strategy", "visual_direction", "reason", "fallback"):
            if len(cta_plan[field].strip()) < 20:
                errors.append(f"$.longform_end_cta.{field}: needs a specific review instruction")
    else:
        if cta_plan["placement"] != "none":
            errors.append("$.longform_end_cta.placement: NO_CTA placement must be none")
        if float(cta_plan["breathing_room_s"]) != 0 or float(cta_plan["end_screen_duration_s"]) != 0:
            errors.append("$.longform_end_cta: NO_CTA timing must be zero")
        if cta_plan["spoken_line"].strip() or cta_plan["on_screen_text"].strip() or cta_plan["youtube_elements"]:
            errors.append("$.longform_end_cta: NO_CTA must not contain rendered CTA content")
        if len(cta_plan["reason"].strip()) < 20 or len(cta_plan["fallback"].strip()) < 20:
            errors.append("$.longform_end_cta: NO_CTA needs a reason and safe fallback")

    for key, row in plan["producer_confidence"].items():
        score = float(row["score"])
        if not 0 <= score <= 100:
            errors.append(f"$.producer_confidence.{key}.score: outside 0-100")
    return errors


def assert_valid_plan(
    plan: Mapping[str, Any], material: Mapping[str, Any], transcript: Transcript
) -> None:
    errors = validate_plan(plan, material, transcript)
    if errors:
        raise ValueError("invalid Producer Brain plan: " + "; ".join(errors))


def _source_text(source: Mapping[str, Any]) -> str:
    if source["source_type"] == "hearing_transcript":
        return f"hearing transcript {hhmmss(source['start_s'])}–{hhmmss(source['end_s'])}: “{source['quote']}”"
    return f"public record {source['source_id']}: “{source['quote']}”"


def _sources_text(sources: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(_source_text(source) for source in sources)


def _range(start_s: float, end_s: float) -> str:
    return f"{hhmmss(start_s)}–{hhmmss(end_s)}"


def render_report(plan: Mapping[str, Any]) -> str:
    """Render the required CASE/SOURCE + numbered 1-16 review structure."""
    case = plan["case_source"]
    lines = [
        "# PRODUCER BRAIN V1 — REAL CASE REPORT",
        "",
        "## CASE / SOURCE",
        "",
        f"- Internal case: `{case['internal_case_id']}` — {case['defendant_name_internal']} ({case['cause_number_internal']})",
        f"- Hearing: {case['proceeding_type']} on {case['docket_date']}, {_range(case['hearing_start_s'], case['hearing_end_s'])}",
        f"- Court source: {case['source_url']}",
        f"- Transcript: `{case['transcript_path']}` ({case['transcript_source']}; SHA-256 `{case['transcript_sha256']}`)",
        "- Public-facing title rule: no defendant name.",
        "",
        "## 1. STORY SUMMARY",
        "",
        plan["story_summary"],
        "",
        "## 2. WHY THIS IS OR IS NOT A VIDEO",
        "",
        f"**{plan['video_decision']['decision']}.** {plan['video_decision']['watchability']}",
        "",
        f"Limitation: {plan['video_decision']['limitation']}",
        "",
        "## 3. STORY ARC",
        "",
    ]
    for label in ("setup", "escalation", "payoff"):
        beat = plan["story_arc"][label]
        lines.extend([
            f"- **{label.title()} — {_range(beat['start_s'], beat['end_s'])}:** {beat['summary']}",
            f"  Evidence: {_sources_text(beat['sources'])}",
        ])
    lines.extend(["", "## 4. BIG MOMENTS", ""])
    for row in plan["big_moments"]:
        lines.extend([
            f"- **{_range(row['start_s'], row['end_s'])}:** {row['description']}",
            f"  Why it matters: {row['why_it_matters']}",
            f"  Evidence: {_sources_text(row['sources'])}",
        ])
    cold = plan["cold_open"]
    lines.extend([
        "",
        "## 5. BEST COLD OPEN",
        "",
        f"**{_range(cold['start_s'], cold['end_s'])} ({cold['end_s'] - cold['start_s']:.1f}s)**",
        "",
        f"> {cold['exact_audio']}",
        "",
        cold["why_it_teases"],
        "",
        f"Spoiler guard: {cold['spoiler_guard']}",
        "",
        f"Evidence: {_sources_text(cold['sources'])}",
        "",
        "## 6. INTRO ANGLE",
        "",
        plan["intro_angle"],
        "",
        "## 7. INTRO FACTS",
        "",
    ])
    for row in plan["intro_facts"]:
        rel = row["relevance"]
        lines.extend([
            f"- **Fact:** {row['fact']}",
            f"  **Source/evidence:** {_sources_text(row['sources'])}",
            f"  **Why it matters:** {row['why_it_matters']}",
            f"  **Relevance:** why here — {rel['why_here']}; payoff — {rel['payoff_connection']}; stakes — {rel['story_stakes']}; referenced by — {rel['mentioned_by']}.",
            f"  **Confidence:** {row['confidence']}",
        ])
    lines.extend(["", "## 8. EXCLUDED FACTS", ""])
    for row in plan["excluded_facts"]:
        lines.extend([
            f"- **{row['fact']}** — {row['reason']}",
            f"  Evidence considered: {_sources_text(row['sources'])}",
        ])
    lines.extend([
        "",
        "## 9. SAMPLE INTRO NARRATION",
        "",
        f"> {plan['sample_intro_narration']['text']}",
        "",
        "## 10. MID-VIDEO CONTEXT BREAKS",
        "",
    ])
    if not plan["mid_video_context_breaks"]:
        lines.append("None. The hearing states the relevant conflict and consequence plainly; adding an explainer would slow the story without improving understanding.")
    else:
        for row in plan["mid_video_context_breaks"]:
            lines.extend([
                f"- **At {hhmmss(row['timestamp_s'])}:** {row['what_needs_explaining']}",
                f"  Proposed narration: “{row['proposed_narration']}”",
                f"  Why: {row['why_it_improves']}",
                f"  Evidence: {_sources_text(row['sources'])}",
            ])
    lines.extend(["", "## 11. TITLE ANGLES", ""])
    for i, row in enumerate(plan["title_angles"], start=1):
        lines.extend([
            f"{i}. **{row['direction']}:** {row['title']}",
            f"   Story promise: {row['story_promise']}",
            f"   Evidence: {_sources_text(row['sources'])}",
        ])
    lines.extend(["", "## 12. THUMBNAIL PLAN", ""])
    score_labels = {
        "story_clarity": "story clarity",
        "scroll_stop": "scroll stop",
        "curiosity": "curiosity",
        "realism": "realism",
        "mobile_readability": "mobile",
        "title_pairing": "title pairing",
        "emotion": "emotion",
        "distinctiveness": "distinctiveness",
    }
    for row in plan["thumbnail_plan"]:
        scores = ", ".join(
            f"{score_labels[key]} {row['scores'][key]:g}/{maximum}"
            for key, maximum in THUMBNAIL_LIMITS.items()
        )
        lines.extend([
            f"### {row['concept']} — {row['hypothesis'].replace('_', ' ').title()}",
            "",
            f"- Layout: {row['layout']}",
            f"- Subjects/expression: {row['subjects_and_expression']}",
            f"- Grounded frames: defendant `{row['defendant_frame_id']}`; Boyd `{row['boyd_frame_id'] or 'none'}`",
            f"- Background: {row['background']}",
            f"- Text: {row['text'] or 'None'}",
            f"- Typography: {row['typography']}",
            f"- Lighting: {row['lighting']}",
            f"- Arrow: {row['arrow']}",
            f"- Why click: {row['reason_to_click']}",
            f"- Curiosity gap: {row['curiosity_gap']}",
            f"- Title pairing: {row['title_pairing']}",
            f"- Credibility risk: {row['credibility_risks']}",
            f"- Provisional score: **{row['total_score']:g}/100** ({scores}); hard fail: {'yes' if row['hard_fail'] else 'no'}.",
            "",
        ])
    short = plan["short_plan"]
    lines.extend([
        "## 13. SHORTS BRAIN V1 PLAN",
        "",
        f"**{short['decision']}.** {short['watchability']}",
        "",
        f"Limitation: {short['limitation']}",
        "",
        f"Planned kept duration: **{sum(float(row['end_s']) - float(row['start_s']) for row in short['sequence']):.1f}s** across {len(short['sequence'])} source range(s).",
        "",
        f"**Hook ({_range(short['hook_start_s'], short['hook_end_s'])}):** {short['hook']}",
        "",
    ])
    for row in short["sequence"]:
        lines.append(f"- Edit {row['edit_order']} / source {row['source_order']} — **{row['role']} {_range(row['start_s'], row['end_s'])}:** {row['description']} Quote: “{row['quote']}”")
    lines.extend([
        "",
        f"Payoff: {short['payoff']}",
        "",
        f"Connection to long-form: {short['longform_connection']}",
        "",
        f"Chronology: {short['chronology_strategy']}. Truthfulness guard: {short['truthfulness_guard']}",
        "",
        "## 14. PACKAGE COHERENCE CHECK",
        "",
        plan["package_coherence_check"],
        "",
        "## 15. PRODUCER CONFIDENCE",
        "",
    ])
    for label, key in (
        ("Story selection", "story_selection"),
        ("Cold-open", "cold_open"),
        ("Factual-context", "factual_context"),
        ("Title/package", "title_package"),
    ):
        row = plan["producer_confidence"][key]
        lines.append(f"- **{label}: {row['score']:g}/100.** {row['reason']}{' **UNCERTAIN.**' if row['uncertain'] else ''}")
    alt = plan["alternative_story_angle"]
    lines.extend([
        "",
        "## 16. ALTERNATIVE STORY ANGLE",
        "",
        f"**{alt['angle']}**",
        "",
        alt["why_legitimate"],
        "",
        f"Ranked below the primary angle because {alt['why_ranked_lower']}",
        "",
    ])
    end_cta = plan["longform_end_cta"]
    lines.extend([
        "## 17. LONG-FORM END CTA PLAN",
        "",
    ])
    if end_cta["decision"] == "USE":
        elements = ", ".join(item.replace("_", " ") for item in end_cta["youtube_elements"])
        lines.extend([
            "**USE — after the complete courtroom payoff.**",
            "",
            f"- Verified payoff boundary: {hhmmss(end_cta['payoff_end_s'])}",
            f"- Breathing room: {end_cta['breathing_room_s']:g}s after the final meaningful line/reaction",
            f"- End-screen window: {end_cta['end_screen_duration_s']:g}s",
            f"- Spoken line: “{end_cta['spoken_line']}”",
            f"- On-screen text: {end_cta['on_screen_text']}",
            f"- YouTube elements: {elements}",
            f"- Next-video strategy: {end_cta['next_video_strategy']}",
            f"- Visual direction: {end_cta['visual_direction']}",
            f"- Why: {end_cta['reason']}",
            f"- Fallback: {end_cta['fallback']}",
            "",
            "Planning only: this report does not render a tail or configure YouTube elements.",
            "",
        ])
    else:
        lines.extend([
            "**NO CTA.**",
            "",
            f"- Verified payoff boundary: {hhmmss(end_cta['payoff_end_s'])}",
            f"- Reason: {end_cta['reason']}",
            f"- Safe fallback: {end_cta['fallback']}",
            "",
            "No CTA assets or platform elements should be produced for this plan.",
            "",
        ])
    return "\n".join(lines)
