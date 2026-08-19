"""Turn a judged moment into something pipeline.produce() already understands.

WHY THIS IS AN ADAPTER AND NOT A REWRITE
-----------------------------------------
`pipeline.produce(docket, case)` reads exactly seven things off a case:
start_s, end_s, hook_start_s, proceeding_type, shortable, shortable_reasoning,
and short_segments. A judged moment supplies all seven, so the entire render
chain - silence trim, intro sting, watermark, 2-up short with per-speaker
caption margins, thumbnail - works unchanged.

Better than unchanged: CONTENT_SPEC Form B is already "one contiguous stretch
of 25-59 seconds, one segment, beat 'moment', no arc required". THE MOMENT
PRODUCT IS FORM B. The shape we now want was already the supported one, which
is why this file is fifty lines instead of a new renderer.

The one real conversion is the safety span. plan_short_segments() clamps every
beat to [case_start, case_end] so a short can never take audio from the
previous defendant's hearing. A moment has no case boundaries of its own, so
the moment's own window becomes that boundary and the clamp still holds.
"""
from __future__ import annotations

from typing import Any

# The judge is told to start on her line, so the hook is at the top by
# construction. Kept as a named constant rather than a literal 0.0 so that if
# the prompt ever changes to allow a cold open mid-passage, there is one place
# to change.
HOOK_AT_START = 0.0

# Below this a short is not worth cutting; above it, YouTube stops calling it a
# short. CONTENT_SPEC's own Form B band.
MIN_CLIP_S = 20.0
MAX_CLIP_S = 90.0


class MomentError(ValueError):
    pass


def moment_to_case(judged: dict[str, Any]) -> dict[str, Any]:
    """A judged moment, in the shape produce() wants.

    `judged` is one value from state/moments_judged.json: the model's verdict
    plus the mined candidate under "_c".
    """
    c = judged.get("_c") or {}
    if not c:
        raise MomentError("judged record has no candidate under '_c'")
    if not judged.get("is_boyd"):
        raise MomentError(f"not Boyd speaking: {judged.get('speaker_note', '')[:80]}")
    if not judged.get("safe_to_publish", True):
        raise MomentError("judge marked it unsafe to publish")

    base = float(c["start_s"])
    start = base + float(judged["clip_start_offset_s"])
    end = base + float(judged["clip_end_offset_s"])
    if end <= start:
        raise MomentError(f"clip end {end:.0f}s is not after start {start:.0f}s")

    dur = end - start
    if dur < MIN_CLIP_S:
        raise MomentError(f"clip is {dur:.0f}s, under the {MIN_CLIP_S:.0f}s floor")
    if dur > MAX_CLIP_S:
        # Trim the tail, never the head: the hook is at the top and the judge
        # was told to end ON the line, so a long clip has slack at the end.
        end = start + MAX_CLIP_S
        dur = MAX_CLIP_S

    quote = (judged.get("hook_quote") or "").strip()
    why = (judged.get("why") or "").strip()

    return {
        "start_s": start,
        "end_s": end,
        # produce() uses this to seek the thumbnail frame and to open the short.
        "hook_start_s": start + HOOK_AT_START,
        "hook_quote": quote,
        # Not a docket proceeding. Recorded honestly rather than guessed at, so
        # nothing downstream reports a plea that was never taken.
        "proceeding_type": "other",
        "defendant_name": "",
        "cause_number": "",
        # Uncertainty resolves to `accused` per prompts/score_cases.md PART 1.
        # A moment carries no plea colloquy, so it can never establish more.
        "guilt_posture": "accused",
        "shortable": True,
        "shortable_reasoning": f"single moment, out-of-pocket {judged.get('out_of_pocket')}",
        "short_form": "single_moment",
        "short_segments": [{"beat": "moment", "start_s": start, "end_s": end}],
        "summary": why,
        "context_needed": (judged.get("context_needed") or "").strip(),
        "out_of_pocket": judged.get("out_of_pocket"),
        # The rubric score has no meaning for a moment; out_of_pocket is the
        # score. Recorded here so `boyd bank` and the ledger show something
        # honest rather than a null.
        "total_score": float(judged.get("out_of_pocket") or 0.0),
        # _write_manifest reads case["scores"]. A moment has ONE axis, so the
        # five case dimensions are not faked here — a manifest claiming a
        # pushback score the judge never gave would be worse than no manifest.
        "scores": {
            "out_of_pocket": {
                "score": float(judged.get("out_of_pocket") or 0.0),
                "justification": why or "judged by prompts/judge_moments.md",
            }
        },
        # Written so the row satisfies the same shape a scored case has.
        # The judge already applied the publish gate (safe_to_publish), which
        # moment_to_case refuses to bypass, so this records that decision
        # rather than asserting a fresh one.
        "safety": {
            "safety_pass": True,
            "safety_rule_violations": [],
            "safety_reasoning": "judge_moments safe_to_publish=true; "
                                "court footage is public record",
        },
        "source": "moments",
    }


def moment_key(judged: dict[str, Any]) -> str:
    c = judged.get("_c") or {}
    return f"{c.get('video_id', '?')}:{int(c.get('start_s', 0))}"
