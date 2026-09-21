"""The story ledger — project memory for "have we already made this video?".

The pipeline's own store keys work by CASE (`<video_id>:<start_s>`), and a
re-scored docket produces several rows for one hearing. On 2026-09-16 that cost
a whole render: `dAKO7myCd-g:8929` was scored, selected and rendered as a new
package although the same hearing already had a long-form and a Short from
2026-09-06 (`dAKO7myCd-g:8340`) plus a Producer review of the same story. Exact
candidate deduplication could never see it, because the row was new.

This module answers the question one level up, at STORY level:

    python tools/story_ledger.py preflight dAKO7myCd-g:8929

A story is a hearing, or a set of hearings, that a viewer would experience as
one case being covered: identified by cause number when the record carries one,
by the docket window when it does not, and by defendant name only as a
POSSIBLE match that a human has to settle.

Two independent status dimensions are recorded for every artifact, because
"the file decodes" and "the cut is good" are different facts:

  technical_status    MISSING | GENERATED | VALID | BROKEN | SUPERSEDED
  editorial_status    UNREVIEWED | REVIEWED | APPROVED | REJECTED |
                      NEEDS_USER_REEDIT | SUPERSEDED
  publication_status  NONE | DELIVERED_FOR_REVIEW | DRAFTED | PUBLISHED | UNKNOWN

On 2026-09-16 Nathan rejected the Short cut for `dAKO7myCd-g:8929` while the
file itself decoded and the bundle validated. Nothing downstream may treat
VALID technical status, `decode rc=0`, or `ready: true` as editorial approval.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

# ------------------------------------------------------------------- vocabulary

TECHNICAL_STATUSES = ("MISSING", "GENERATED", "VALID", "BROKEN", "SUPERSEDED")
EDITORIAL_STATUSES = ("UNREVIEWED", "REVIEWED", "APPROVED", "REJECTED",
                      "NEEDS_USER_REEDIT", "SUPERSEDED")
PUBLICATION_STATUSES = ("NONE", "DELIVERED_FOR_REVIEW", "DRAFTED", "PUBLISHED", "UNKNOWN")
ARTIFACT_KINDS = ("longform", "short", "thumbnail", "short_thumbnail", "packaging", "source")
MATCH_KINDS = ("NEW", "EXISTING", "POSSIBLE_MATCH")

# A candidate window this much inside an existing story's window is that story.
OVERLAP_FRACTION = 0.5

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    story_id            TEXT PRIMARY KEY,
    label               TEXT,
    cause_number        TEXT,
    defendant_label     TEXT,
    confidence          TEXT NOT NULL DEFAULT 'CONFIRMED',
    selection_eligible  INTEGER NOT NULL DEFAULT 1,
    ineligible_reason   TEXT,
    review_state        TEXT NOT NULL DEFAULT 'UNREVIEWED',
    publication_status  TEXT NOT NULL DEFAULT 'NONE',
    first_seen          TEXT,
    last_updated        TEXT,
    notes               TEXT
);
CREATE TABLE IF NOT EXISTS story_sources (
    story_id            TEXT NOT NULL,
    video_id            TEXT NOT NULL,
    start_s             REAL NOT NULL,
    end_s               REAL,
    hearing_date        TEXT,
    source_url          TEXT,
    cause_number        TEXT,
    evidence            TEXT,
    confidence          TEXT,
    PRIMARY KEY (story_id, video_id, start_s)
);
CREATE TABLE IF NOT EXISTS story_artifacts (
    story_id            TEXT NOT NULL,
    kind                TEXT NOT NULL,
    path                TEXT NOT NULL,
    sha256              TEXT,
    duration_s          REAL,
    technical_status    TEXT NOT NULL DEFAULT 'GENERATED',
    editorial_status    TEXT NOT NULL DEFAULT 'UNREVIEWED',
    publication_status  TEXT NOT NULL DEFAULT 'NONE',
    created_at          TEXT,
    evidence            TEXT,
    note                TEXT,
    PRIMARY KEY (story_id, kind, path)
);
CREATE TABLE IF NOT EXISTS story_decisions (
    story_id            TEXT NOT NULL,
    decision            TEXT NOT NULL,
    reason              TEXT,
    source              TEXT,
    quote               TEXT,
    recorded_at         TEXT,
    PRIMARY KEY (story_id, decision, source, quote)
);
CREATE TABLE IF NOT EXISTS story_feedback (
    story_id            TEXT NOT NULL,
    dimension           TEXT NOT NULL,
    preference          TEXT NOT NULL,
    source              TEXT,
    quote               TEXT,
    status              TEXT NOT NULL DEFAULT 'LEARNED',
    recorded_at         TEXT,
    PRIMARY KEY (story_id, dimension, preference, source)
);
CREATE TABLE IF NOT EXISTS story_index (
    source              TEXT PRIMARY KEY,
    sha256              TEXT,
    built_at            TEXT,
    note                TEXT
);
CREATE TABLE IF NOT EXISTS short_edit_profile (
    dimension           TEXT NOT NULL,
    preference          TEXT NOT NULL,
    evidence            TEXT,
    source              TEXT NOT NULL,
    confidence          TEXT NOT NULL DEFAULT 'MEDIUM',
    learned_at          TEXT,
    PRIMARY KEY (dimension, preference, source)
);
CREATE INDEX IF NOT EXISTS idx_story_sources_video ON story_sources(video_id);
CREATE INDEX IF NOT EXISTS idx_story_sources_cause ON story_sources(cause_number);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "unknown"


def _norm_name(text: str | None) -> str:
    """A defendant label reduced to comparable words, surname last-name only."""
    words = re.findall(r"[a-z]+", (text or "").lower())
    drop = {"unknown", "the", "state", "of", "and", "detention", "officer",
            "defendant", "name", "not", "captured", "in", "transcript", "excerpt"}
    # Generational suffixes are not surnames: comparing them matched
    # "Oscar Carvajal Jr." to "Gilbert Pacina Jr." and flagged a false
    # POSSIBLE_MATCH on a case that had nothing to do with either.
    drop |= {"jr", "sr", "ii", "iii", "iv", "mr", "ms", "mrs"}
    words = [w for w in words if w not in drop]
    return " ".join(words[:3])


# The shape a Texas cause number actually takes in these transcripts:
# "2023 CR 10327", "2025 CR012572-02", "2023-CR-7231", sometimes two of them
# ("2024 CR 4372 and 2025 CR 008059"). Anything else the scorer wrote into the
# field is prose, not an identity — the old code stripped it to a 90-character
# story id and split one story in two.
_CASE_NUMBER = re.compile(r"20\d{2}\s*-?\s*cr\s*\d+(?:\s*-\s*\d+)?", re.IGNORECASE)


def _norm_cause(cause: str | None) -> str:
    text = cause or ""
    found = _CASE_NUMBER.findall(text)
    if found:
        parts = sorted({re.sub(r"[^0-9a-z]", "", value.lower()) for value in found})
        return "+".join(parts)
    value = re.sub(r"[^0-9a-z]", "", text.lower())
    return "" if value in ("", "unknown", "none") else value[:24]


def overlap_fraction(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """How much of window A sits inside window B, as a fraction of A."""
    span = float(a_end) - float(a_start)
    if span <= 0:
        return 0.0
    inside = min(float(a_end), float(b_end)) - max(float(a_start), float(b_start))
    return max(0.0, inside) / span


class StoryLedger:
    """Story-level memory over the same SQLite file the pipeline already uses."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    # ---------------------------------------------------------------- schema
    def ensure_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ write
    def story_id(self, video_id: str, start_s: float,
                 cause_number: str | None = None) -> str:
        cause = _norm_cause(cause_number)
        if cause:
            return f"cause:{cause}"
        return f"window:{video_id}:{int(round(float(start_s)))}"

    def upsert_story(self, story_id: str, *, label: str | None = None,
                     cause_number: str | None = None, defendant_label: str | None = None,
                     confidence: str = "CONFIRMED", selection_eligible: bool = True,
                     ineligible_reason: str | None = None, review_state: str = "UNREVIEWED",
                     publication_status: str = "NONE", notes: str | None = None) -> str:
        row = self.conn.execute("SELECT first_seen FROM stories WHERE story_id = ?",
                                (story_id,)).fetchone()
        first_seen = row["first_seen"] if row else now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO stories (story_id, label, cause_number, defendant_label,"
                " confidence, selection_eligible, ineligible_reason, review_state,"
                " publication_status, first_seen, last_updated, notes)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(story_id) DO UPDATE SET"
                "  label=COALESCE(excluded.label, stories.label),"
                "  cause_number=COALESCE(excluded.cause_number, stories.cause_number),"
                "  defendant_label=COALESCE(excluded.defendant_label, stories.defendant_label),"
                "  confidence=excluded.confidence,"
                "  selection_eligible=excluded.selection_eligible,"
                "  ineligible_reason=excluded.ineligible_reason,"
                "  review_state=excluded.review_state,"
                "  publication_status=excluded.publication_status,"
                "  last_updated=excluded.last_updated,"
                "  notes=COALESCE(excluded.notes, stories.notes)",
                (story_id, label, cause_number, defendant_label, confidence,
                 1 if selection_eligible else 0, ineligible_reason, review_state,
                 publication_status, first_seen, now(), notes))
        return story_id

    def add_source(self, story_id: str, video_id: str, start_s: float, end_s: float | None,
                   *, hearing_date: str | None = None, source_url: str | None = None,
                   cause_number: str | None = None, evidence: str | None = None,
                   confidence: str = "CONFIRMED") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO story_sources (story_id, video_id, start_s, end_s,"
                " hearing_date, source_url, cause_number, evidence, confidence)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (story_id, video_id, float(start_s),
                 None if end_s is None else float(end_s), hearing_date, source_url,
                 cause_number, evidence, confidence))

    def add_artifact(self, story_id: str, kind: str, path: str | Path, *,
                     sha256: str | None = None, duration_s: float | None = None,
                     technical_status: str = "GENERATED",
                     editorial_status: str = "UNREVIEWED",
                     publication_status: str = "NONE", created_at: str | None = None,
                     evidence: str | None = None, note: str | None = None) -> None:
        if kind not in ARTIFACT_KINDS:
            raise ValueError(f"unknown artifact kind {kind!r}")
        if technical_status not in TECHNICAL_STATUSES:
            raise ValueError(f"unknown technical status {technical_status!r}")
        if editorial_status not in EDITORIAL_STATUSES:
            raise ValueError(f"unknown editorial status {editorial_status!r}")
        if publication_status not in PUBLICATION_STATUSES:
            raise ValueError(f"unknown publication status {publication_status!r}")
        with self.conn:
            self.conn.execute(
                "INSERT INTO story_artifacts (story_id, kind, path, sha256, duration_s,"
                " technical_status, editorial_status, publication_status, created_at,"
                " evidence, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(story_id, kind, path) DO UPDATE SET"
                "  sha256=COALESCE(excluded.sha256, story_artifacts.sha256),"
                "  duration_s=COALESCE(excluded.duration_s, story_artifacts.duration_s),"
                "  technical_status=excluded.technical_status,"
                "  editorial_status=excluded.editorial_status,"
                "  publication_status=excluded.publication_status,"
                "  created_at=COALESCE(excluded.created_at, story_artifacts.created_at),"
                "  evidence=COALESCE(excluded.evidence, story_artifacts.evidence),"
                "  note=COALESCE(excluded.note, story_artifacts.note)",
                (story_id, kind, str(path), sha256, duration_s, technical_status,
                 editorial_status, publication_status, created_at, evidence, note))

    def add_decision(self, story_id: str, decision: str, *, reason: str | None = None,
                     source: str | None = None, quote: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO story_decisions (story_id, decision, reason,"
                " source, quote, recorded_at) VALUES (?,?,?,?,?,?)",
                (story_id, decision, reason, source, quote or "", now()))

    def add_feedback(self, story_id: str, dimension: str, preference: str, *,
                     source: str | None = None, quote: str | None = None,
                     status: str = "LEARNED") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO story_feedback (story_id, dimension, preference,"
                " source, quote, status, recorded_at) VALUES (?,?,?,?,?,?,?)",
                (story_id, dimension, preference, source, quote or "", status, now()))

    # ------------------------------------------------------------------- read
    def _sources(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM story_sources"))

    def match(self, video_id: str, start_s: float, end_s: float,
              cause_number: str | None = None,
              defendant_label: str | None = None) -> tuple[str, str, str]:
        """(match_kind, story_id or "", why) for a candidate window.

        Order of evidence: exact cause number, then the docket window, then a
        defendant-name resemblance. The first two are identity; the third is
        only a lead and is reported as POSSIBLE_MATCH.
        """
        cause = _norm_cause(cause_number)
        rows = self._sources()
        if cause:
            for row in rows:
                if _norm_cause(row["cause_number"]) == cause:
                    return ("EXISTING", row["story_id"],
                            f"same cause number {cause} on {row['video_id']}")
        best = None
        for row in rows:
            if row["video_id"] != video_id or row["end_s"] is None:
                continue
            part = overlap_fraction(start_s, end_s, row["start_s"], row["end_s"])
            if part >= OVERLAP_FRACTION and (best is None or part > best[0]):
                best = (part, row["story_id"])
        if best:
            return ("EXISTING", best[1],
                    f"{best[0] * 100:.0f}% of the candidate window lies inside "
                    f"an already-recorded window on {video_id}")
        name = _norm_name(defendant_label)
        if name:
            parts = name.split()
            first, surname = parts[0], parts[-1]
            if len(surname) < 3:
                return ("NEW", "", "no source, cause or window in the ledger matches")
            for story in self.conn.execute(
                    "SELECT story_id, defendant_label FROM stories"
                    " WHERE defendant_label IS NOT NULL"):
                other = _norm_name(story["defendant_label"])
                if not other:
                    continue
                oparts = other.split()
                # A surname alone is a coincidence, not identity: this docket
                # carries an Oscar Carvajal Jr. and, months earlier, a Jose
                # Carvajal, and Andrew Garcia is not Javier Garcia. Full-name
                # agreement, or first name AND surname agreement, is a lead.
                if other == name or (oparts[-1] == surname and oparts[0] == first):
                    return ("POSSIBLE_MATCH", story["story_id"],
                            f"defendant name resembles {story['defendant_label']!r}"
                            " — same surname is not identity; review before rendering")
        return ("NEW", "", "no source, cause or window in the ledger matches")

    def story(self, story_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM stories WHERE story_id = ?",
                                 (story_id,)).fetchone()

    def resolve(self, video_id: str, start_s: float, end_s: float | None = None,
                cause_number: str | None = None,
                defendant_label: str | None = None) -> str:
        """The story a source belongs to: cause, then window, then a new id.

        Writers use this instead of `story_id()`, so a verdict on a re-scored row
        (dAKO7myCd-g:8929) lands on the story that already exists rather than on
        a fresh id that means nothing.
        """
        kind, story_id, _why = self.match(
            video_id, start_s, end_s if end_s is not None else start_s,
            cause_number, defendant_label)
        if kind == "EXISTING" and story_id:
            return story_id
        return self.story_id(video_id, start_s, cause_number)

    def artifacts(self, story_id: str, kind: str | None = None) -> list[sqlite3.Row]:
        if kind:
            return list(self.conn.execute(
                "SELECT * FROM story_artifacts WHERE story_id = ? AND kind = ?"
                " ORDER BY kind, path", (story_id, kind)))
        return list(self.conn.execute(
            "SELECT * FROM story_artifacts WHERE story_id = ? ORDER BY kind, path",
            (story_id,)))

    def preflight(self, video_id: str, start_s: float, end_s: float,
                  cause_number: str | None = None,
                  defendant_label: str | None = None) -> dict[str, Any]:
        """The memory check that runs before expensive work on any candidate."""
        kind, story_id, why = self.match(video_id, start_s, end_s, cause_number,
                                         defendant_label)
        info: dict[str, Any] = {
            "story_match": kind, "story_id": story_id, "why": why,
            "prior_longform": "UNKNOWN", "prior_short": "UNKNOWN",
            "prior_user_review": "UNKNOWN", "selection_eligible": True,
            "reason": "", "label": None, "publication_status": "UNKNOWN",
        }
        if not story_id:
            info["prior_longform"] = "NO"
            info["prior_short"] = "NO"
            info["prior_user_review"] = "NONE ON RECORD"
            info["selection_eligible"] = True
            info["reason"] = "new story — nothing in the ledger covers this window"
            return info

        row = self.story(story_id)
        artifacts = self.artifacts(story_id)
        info["label"] = row["label"] if row else None
        info["publication_status"] = row["publication_status"] if row else "UNKNOWN"
        info["prior_longform"] = "YES" if any(a["kind"] == "longform" for a in artifacts) else "NO"
        info["prior_short"] = "YES" if any(a["kind"] == "short" for a in artifacts) else "NO"
        feedback = list(self.conn.execute(
            "SELECT dimension, preference, quote, status FROM story_feedback"
            " WHERE story_id = ?", (story_id,)))
        decisions = list(self.conn.execute(
            "SELECT decision, reason, quote FROM story_decisions WHERE story_id = ?",
            (story_id,)))
        if feedback or decisions:
            info["prior_user_review"] = "; ".join(
                [f"{d['decision']}: {d['reason'] or d['quote']}" for d in decisions][:2]
                or [f"{f['dimension']}: {f['preference']}" for f in feedback][:2])
        else:
            info["prior_user_review"] = "NONE ON RECORD"
        eligible = bool(row["selection_eligible"]) if row else False
        info["selection_eligible"] = eligible
        info["reason"] = (row["ineligible_reason"] if row and row["ineligible_reason"]
                          else "story has no completed package on record")
        if not eligible and kind == "POSSIBLE_MATCH":
            info["reason"] = (f"POSSIBLE MATCH to {story_id} — {why}; a human must "
                              "confirm identity before any render")
        return info

    def selection_block(self, video_id: str, start_s: float, end_s: float,
                        cause_number: str | None = None,
                        defendant_label: str | None = None) -> tuple[bool, str]:
        """(blocked, reason) for unattended selection."""
        info = self.preflight(video_id, start_s, end_s, cause_number, defendant_label)
        if info["story_match"] == "NEW":
            return False, ""
        if info["story_match"] == "POSSIBLE_MATCH":
            return True, (f"possible match to {info['story_id']} ({info['why']}) — "
                          "needs review before selection")
        if info["selection_eligible"]:
            return False, ""
        return True, f"story {info['story_id']} already has a package: {info['reason']}"

    def format_preflight(self, info: Mapping[str, Any]) -> str:
        return "\n".join((
            "  STORY MATCH:        " + str(info["story_match"]),
            "  PRIOR LONG FORM:    " + str(info["prior_longform"]),
            "  PRIOR SHORT:        " + str(info["prior_short"]),
            "  PRIOR USER REVIEW:  " + str(info["prior_user_review"]),
            "  SELECTION ELIGIBLE: " + ("YES" if info["selection_eligible"] else "NO"),
            "  REASON:             " + str(info["reason"] or info["why"]),
        ))

    # ---------------------------------------------------------------- helpers
    def record_source_build(self, source: str, path: Path) -> None:
        digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO story_index (source, sha256, built_at, note)"
                " VALUES (?,?,?,?)", (source, digest, now(), str(path)))


def open_ledger(db_path: str | Path) -> tuple[StoryLedger, sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path))
    return StoryLedger(conn), conn


def collect_longform_short(ledger: StoryLedger, story_id: str) -> dict[str, list[dict]]:
    """Group a story's artifacts by kind — what a report needs, and nothing more."""
    grouped: dict[str, list[dict]] = {}
    for row in ledger.artifacts(story_id):
        grouped.setdefault(row["kind"], []).append(dict(row))
    return grouped
