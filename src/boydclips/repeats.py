"""Find defendants who came back, and assemble their hearings into one episode.

WHY THIS EXISTS
---------------
Measured 2026-08-18 across the full catalogues of all seven channels clipping
this docket (3,645 videos). On Court Trials TV Network — 899 videos, 134K subs,
holder of 29 of the 40 highest-viewed videos in the niche — titles that announce
a RETURN APPEARANCE ("BACK AGAIN", "Watch Both Cases", "UPDATE", "5 Hearings")
run a median of 15,000 views against 11,000 for one-offs (n=348 vs 551).

That is 1.36x at the same runtime (17m vs 15m), and it survives inside every
duration band — 1.20x at 0-20m, 1.24x at 20-30m, 1.84x at 30-40m — so it is not
a proxy for length. Their #2, #3, #8, #9, #10 and #15 videos are all returns.

It is NOT universal. On Courtroom Time the format is 3% of the catalogue and
shows no lift (1.01x). This is adopted because Court Trials TV is the channel
worth copying, not because every channel does it.

The material is already on disk. Nothing new has to be downloaded, transcribed
or scored: 48 defendants in state/pipeline.db appear across two or more
dockets, 33 of them already clear the gate.

NAME MATCHING, AND WHY IT IS DELIBERATELY CONSERVATIVE
------------------------------------------------------
Defendant names here are LLM-extracted from auto-captions, so they arrive with
inconsistent casing, dropped/added middle names, suffix noise ("Jr.", "III")
and stripped diacritics. Matching normalises for exactly those and nothing
else — accents, case, punctuation, suffixes, and word order.

It does NOT do fuzzy or phonetic matching. In Bexar County 314+ people share
the name "Jose Garcia" (see priors.py), so a loose matcher will merge two
different people into one episode and narrate a stranger's record as theirs.
This module therefore errs toward missing a return, never toward inventing one.
Where a cause number is present on both hearings and they disagree, the pair is
split rather than merged.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from typing import Any

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_NOISE = re.compile(r"[^a-z ]+")


def name_key(raw: str | None) -> str:
    """A conservative identity key for a docket name.

    'PEÑA, Arnold Jr.' and 'Arnold Pena' -> 'arnold pena'. Word order is
    normalised because the docket alternates 'LAST, First' and 'First Last'
    between hearings of the same person.

    Returns '' for anything too short to identify, which callers must treat as
    unmatchable rather than as a group of its own.
    """
    s = unicodedata.normalize("NFKD", raw or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = _NOISE.sub(" ", s)
    words = [w for w in s.split() if len(w) > 1 and w not in _SUFFIXES]
    if len(words) < 2:
        return ""
    return " ".join(sorted(words))


def cause_key(raw: str | None) -> str:
    """'2025 CR0133' / '2025CR001529' -> '2025cr133' — digits unpadded.

    Cause numbers are LLM-extracted and inconsistently formatted, so this is
    only ever used to SPLIT a name group that disagrees, never to merge one.
    """
    s = re.sub(r"[^a-z0-9]", "", (raw or "").lower())
    m = re.match(r"^(\d{4})?(cr)?(\d+)$", s)
    if not m:
        return ""
    year, _, num = m.groups()
    return f"{year or ''}cr{int(num)}"


@dataclass
class Episode:
    """One defendant's hearings across two or more dockets, oldest first."""

    defendant: str
    hearings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def dockets(self) -> int:
        return len({h["video_id"] for h in self.hearings})

    @property
    def best_score(self) -> float:
        return max((h["total_score"] or 0.0) for h in self.hearings)

    @property
    def total_s(self) -> float:
        return sum(max(0.0, (h["end_s"] or 0) - (h["start_s"] or 0))
                   for h in self.hearings)

    @property
    def all_safe(self) -> bool:
        return all(h["safety_pass"] for h in self.hearings)

    def qualifies(self, *, min_dockets: int, min_best_score: float,
                  require_all_safety_pass: bool) -> bool:
        if self.dockets < min_dockets:
            return False
        if self.best_score < min_best_score:
            return False
        if require_all_safety_pass and not self.all_safe:
            return False
        return True


def find_episodes(conn: sqlite3.Connection) -> list[Episode]:
    """Group every scored case by defendant identity. No filtering."""
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT case_key, video_id, defendant, cause_number, total_score, "
        "       safety_pass, shortable, start_s, end_s, proceeding_type, created_at "
        "FROM cases"
    )]
    # docket_date orders hearings across dockets; created_at is when WE saw it.
    order = {r["video_id"]: r["docket_date"] for r in
             conn.execute("SELECT video_id, docket_date FROM dockets")}

    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        k = name_key(r["defendant"])
        if not k:
            continue
        groups.setdefault(k, []).append(r)

    episodes: list[Episode] = []
    for hearings in groups.values():
        # Split a name group whose cause numbers actively disagree. Missing
        # cause numbers never split — most hearings have none.
        causes = {cause_key(h["cause_number"]) for h in hearings} - {""}
        if len(causes) <= 1:
            buckets = [hearings]
        else:
            # The name group holds more than one person. Hearings WITHOUT a
            # cause number cannot be attributed to either of them, so they are
            # dropped rather than guessed into a bucket — attaching the wrong
            # man's prior hearings to a named defendant is the one mistake
            # here with real consequences.
            buckets = [[h for h in hearings if cause_key(h["cause_number"]) == c]
                       for c in sorted(causes)]
        for b in buckets:
            if len({h["video_id"] for h in b}) < 2:
                continue
            b.sort(key=lambda h: (order.get(h["video_id"]) or "", h["start_s"] or 0))
            episodes.append(Episode(defendant=b[0]["defendant"] or "?", hearings=b))

    episodes.sort(key=lambda e: (-e.best_score, -e.dockets))
    return episodes


def qualifying(conn: sqlite3.Connection, cfg: dict[str, Any]) -> list[Episode]:
    """Episodes that clear the configured repeat_defendant gate."""
    if not cfg.get("enabled", False):
        return []
    return [e for e in find_episodes(conn)
            if e.qualifies(min_dockets=int(cfg.get("min_dockets", 2)),
                           min_best_score=float(cfg.get("min_best_score", 50)),
                           require_all_safety_pass=bool(
                               cfg.get("require_all_safety_pass", True)))]
