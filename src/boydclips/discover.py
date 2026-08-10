"""Stage 0 — find new docket streams on the court's channel.

Deliberately cheap: this touches metadata only. No video, no captions. The
expensive stages downstream only ever see dockets that survive this filter.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Titles look like:
#   "TUES., AUG 4, 2026/JUDGE STEPHANIE BOYD/187TH DISTRICT COURT/MORNING DOCKET"
_DATE_RE = re.compile(
    r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEPT|SEP|OCT|NOV|DEC)[A-Z.]*\s+(\d{1,2})\s*,?\s*(\d{4})",
    re.IGNORECASE,
)
_SESSION_RE = re.compile(r"\b(MORN\w*|AFTER\w*|EVEN\w*)\s*DOCKET", re.IGNORECASE)

# Chronological, for sorting same-day sessions.
SESSION_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, "unknown": 3}


@dataclass
class Docket:
    video_id: str
    title: str
    duration_s: float
    docket_date: str  # ISO yyyy-mm-dd, or "" when unparseable
    session: str      # morning | afternoon | unknown

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def parse_docket_date(title: str) -> str:
    m = _DATE_RE.search(title)
    if not m:
        return ""
    month = MONTHS.get(m.group(1).upper().rstrip("."), 0)
    if not month:
        return ""
    try:
        return date(int(m.group(3)), month, int(m.group(2))).isoformat()
    except ValueError:
        return ""


def parse_session(title: str) -> str:
    m = _SESSION_RE.search(title)
    if not m:
        return "unknown"
    head = m.group(1).upper()
    if head.startswith("MORN"):
        return "morning"
    if head.startswith("AFTER"):
        return "afternoon"
    return "unknown"


def _run_ytdlp(args: list[str], timeout: int = 300) -> str:
    proc = subprocess.run(
        ["yt-dlp", "--no-warnings", "--ignore-config", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
    return proc.stdout


def list_recent(channel_url: str, depth: int) -> list[Docket]:
    """List the most recent streams. Uses --flat-playlist: one request, no
    per-video extraction, so this stays fast even at depth 50."""
    out = _run_ytdlp(
        [
            "--flat-playlist",
            "--playlist-end", str(depth),
            "--print", "%(id)s\t%(title)s\t%(duration)s",
            channel_url,
        ]
    )

    dockets: list[Docket] = []
    seen: set[str] = set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        vid, title, dur = parts
        if not vid or vid in seen:
            continue
        seen.add(vid)
        try:
            duration = float(dur)
        except ValueError:
            duration = 0.0
        dockets.append(
            Docket(
                video_id=vid,
                title=title,
                duration_s=duration,
                docket_date=parse_docket_date(title),
                session=parse_session(title),
            )
        )
    return dockets


def filter_new(
    dockets: list[Docket],
    *,
    seen: set[str],
    min_duration_s: float,
    max_age_days: int,
    today: date | None = None,
) -> list[Docket]:
    """Apply the cheap gates before anything expensive happens."""
    today = today or date.today()
    cutoff = today - timedelta(days=max_age_days)
    keep: list[Docket] = []

    for d in dockets:
        if d.video_id in seen:
            continue
        if d.duration_s < min_duration_s:
            continue
        if d.docket_date:
            try:
                if date.fromisoformat(d.docket_date) < cutoff:
                    continue
            except ValueError:
                pass
        keep.append(d)

    # Oldest first, so a backlog is worked through in chronological order.
    # Session must sort by time of day, not alphabetically — "afternoon" sorts
    # before "morning", which would hand the day's single clip slot to the
    # later session.
    keep.sort(key=lambda x: (x.docket_date or "9999", SESSION_ORDER.get(x.session, 9)))
    return keep


def probe(video_id: str) -> dict:
    """Full metadata for one video. Only called once a docket has passed the
    cheap filters — this is a real extraction and costs a round trip."""
    out = _run_ytdlp(
        ["--dump-single-json", "--skip-download", f"https://www.youtube.com/watch?v={video_id}"],
        timeout=180,
    )
    return json.loads(out)


def has_english_captions(meta: dict) -> bool:
    auto = meta.get("automatic_captions") or {}
    manual = meta.get("subtitles") or {}
    return any(
        k == "en" or k.startswith("en-") for k in list(auto.keys()) + list(manual.keys())
    )
