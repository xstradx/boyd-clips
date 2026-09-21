"""Bounded competitor leads resolved back to original court transcripts."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

from . import discover
from .transcribe import Transcript, get_transcript


@dataclass(frozen=True)
class Lead:
    video_id: str
    channel: str
    title: str
    view_count: int
    upload_date: str
    duration_s: float

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def views_per_day(self) -> float:
        try:
            age = max(0.5, float((date.today() - date.fromisoformat(self.upload_date)).days))
        except (TypeError, ValueError):
            age = 14.0
        return self.view_count / age

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "url": self.url, "views_per_day": round(self.views_per_day, 2)}


def list_recent(
    channels: Iterable[dict[str, str]],
    *,
    per_channel: int,
    max_leads: int,
    runner: Callable[[list[str]], str] | None = None,
) -> list[Lead]:
    """Read only a bounded metadata window from each configured feed."""
    runner = runner or discover._run_ytdlp
    found: dict[str, Lead] = {}
    for channel in channels:
        label = str(channel.get("name") or channel.get("url") or "competitor")
        url = str(channel.get("url") or "")
        if not url:
            continue
        output = runner([
            "--flat-playlist",
            "--playlist-end", str(max(1, int(per_channel))),
            "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(upload_date)s",
            url,
        ])
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) != 5:
                continue
            video_id, title, duration, views, uploaded = fields
            if not video_id or video_id in found:
                continue
            try:
                duration_s = float(duration)
            except ValueError:
                duration_s = 0.0
            try:
                view_count = int(float(views))
            except ValueError:
                view_count = 0
            upload_date = uploaded
            if len(upload_date) == 8 and upload_date.isdigit():
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            found[video_id] = Lead(video_id, label, title, view_count, upload_date, duration_s)
    return sorted(found.values(), key=lambda lead: (-lead.views_per_day, -lead.view_count, lead.video_id))[
        : max(0, int(max_leads))
    ]


def load_transcripts(leads: Iterable[Lead], work: Path) -> list[tuple[Lead, Transcript]]:
    """Use captions only. A competitor clip never triggers local Whisper."""
    loaded: list[tuple[Lead, Transcript]] = []
    for lead in leads:
        try:
            transcript = get_transcript(
                lead.video_id,
                Path(work) / lead.video_id,
                source="auto_captions",
                whisper_fallback=False,
            )
        except Exception:
            continue
        loaded.append((lead, transcript))
    return loaded


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def transcript_overlap(lead_text: str, case_text: str, *, width: int = 5) -> float:
    """Exact phrase coverage: resilient to intros, resistant to generic court words."""
    lead_tokens = _tokens(lead_text)
    case_tokens = _tokens(case_text)
    if len(lead_tokens) < width or len(case_tokens) < width:
        return 0.0
    lead_shingles = {tuple(lead_tokens[i:i + width]) for i in range(len(lead_tokens) - width + 1)}
    case_shingles = {tuple(case_tokens[i:i + width]) for i in range(len(case_tokens) - width + 1)}
    return len(lead_shingles & case_shingles) / max(1, len(lead_shingles))


def best_match(
    case_text: str,
    leads: Iterable[tuple[Lead, Transcript]],
    *,
    min_overlap: float,
) -> dict[str, Any] | None:
    best: tuple[float, Lead] | None = None
    for lead, transcript in leads:
        overlap = transcript_overlap(transcript.render_for_llm(), case_text)
        if overlap < float(min_overlap):
            continue
        strength = overlap * math.log1p(max(0.0, lead.views_per_day))
        if best is None or strength > best[0]:
            best = (strength, lead)
            best_overlap = overlap
    if best is None:
        return None
    strength, lead = best
    return {
        **lead.as_dict(),
        "transcript_overlap": round(best_overlap, 4),
        "lead_strength": round(strength, 4),
        "original_source_verified": True,
    }


def candidate_priority(case: dict[str, Any], stable_order: int) -> tuple[float, float, float, int]:
    """Verified competitor reuse leads; editorial score ranks the rest."""
    lead = case.get("competitor_lead") or {}
    matched = bool(lead.get("original_source_verified"))
    return (
        0.0 if matched else 1.0,
        -float(lead.get("lead_strength") or 0.0),
        -float(case.get("total_score") or 0.0),
        int(stable_order),
    )
