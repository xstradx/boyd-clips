"""Deterministic, factual YouTube metadata helpers."""

from __future__ import annotations

import re
from typing import Any, Iterable


FILLER = {"viral", "trending", "fyp", "youtube shorts", "shorts viral"}
GENERIC_CHANNEL_TAGS = {
    "judge boyd", "judge stephanie boyd", "187th district court", "bexar county",
    "courtroom", "zoom court", "court", "court video", "texas court",
}
TOPIC_RULES = (
    ("cell phone", "cell phone dispute"),
    ("phone", "phone dispute"),
    ("restitution", "court restitution"),
    ("parenting class", "parenting class requirement"),
    ("mental health", "mental health court"),
    ("competency", "competency hearing"),
    ("jury trial", "jury trial request"),
    ("self defense", "self defense claim"),
    ("family violence", "family violence case"),
    ("domestic violence", "domestic violence case"),
    ("assault", "assault case"),
    ("theft", "theft case"),
    ("firearm", "firearm case"),
    ("ankle monitor", "ankle monitor violation"),
    ("gps", "gps monitor violation"),
    ("drug", "drug treatment court"),
    ("alcohol", "alcohol monitoring"),
    ("custody", "custody dispute"),
)


def has_case_specific_tag(tags: Iterable[str]) -> bool:
    return any(
        str(tag).strip().lower() not in GENERIC_CHANNEL_TAGS | FILLER
        for tag in tags
        if str(tag).strip()
    )


def case_tags(base: Iterable[str], case: dict[str, Any], package: dict[str, Any]) -> list[str]:
    """Preserve useful channel terms and add only supported case topics."""
    candidates = [str(tag).strip().lower() for tag in base]
    proceeding = re.sub(r"[_-]+", " ", str(case.get("proceeding_type") or "").lower()).strip()
    text = " ".join(
        str(value or "").lower()
        for value in (package.get("longform_title"), package.get("summary"), proceeding)
    )
    if proceeding and proceeding not in {"other", "administrative", "unknown"}:
        candidates.append(proceeding if "hearing" in proceeding else f"{proceeding} hearing")
    topic_rules = (
        ("probation", "probation hearing"),
        ("revocation", "probation revocation"),
        ("sentenc", "sentencing hearing"),
        ("bond", "bond hearing"),
        ("plea", "plea hearing"),
        ("violation", "probation violation"),
        ("warrant", "warrant hearing"),
    ) + TOPIC_RULES
    for needle, tag in topic_rules:
        if needle in text:
            candidates.append(tag)

    if not has_case_specific_tag(candidates):
        name_tokens = set(re.findall(r"[a-z0-9]+", str(case.get("defendant_name") or "").lower()))
        stop = {
            "judge", "boyd", "court", "courtroom", "asked", "says", "said", "what", "when",
            "where", "which", "with", "that", "this", "from", "into", "after", "before",
            "their", "there", "about", "video", "hearing", "texas", "bexar", "county",
        }
        words = [
            word for word in re.findall(r"[a-z0-9]+", str(package.get("longform_title") or "").lower())
            if len(word) >= 4 and word not in stop and word not in name_tokens
        ]
        phrase = " ".join(dict.fromkeys(words[:2]))
        if phrase:
            candidates.append(phrase)

    out: list[str] = []
    used = 0
    for tag in candidates:
        tag = " ".join(tag.split())
        if not tag or tag in FILLER or tag in out or len(tag) > 100:
            continue
        added = len(tag) + (1 if out else 0)
        if used + added > 500:
            break
        out.append(tag)
        used += added
    return out
