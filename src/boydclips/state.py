"""Durable pipeline state.

Two jobs:
  1. Idempotency — a docket is never processed twice, a case never published
     twice, even if a run dies halfway and the scheduler retries.
  2. The reliability ledger — the record that decides whether autonomy.mode is
     allowed to advance from `manual` to `auto`.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS dockets (
    video_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    docket_date     TEXT,
    duration_s      REAL,
    discovered_at   TEXT NOT NULL,
    transcribed_at  TEXT,
    analyzed_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'discovered',
    error           TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    case_key        TEXT PRIMARY KEY,      -- video_id:start_s
    video_id        TEXT NOT NULL,
    start_s         REAL NOT NULL,
    end_s           REAL NOT NULL,
    defendant       TEXT,
    cause_number    TEXT,
    proceeding_type TEXT,
    guilt_posture   TEXT,
    safety_pass     INTEGER,
    safety_rules    TEXT,                  -- JSON array of violated rule ids
    total_score     REAL,
    rank            INTEGER,
    shortable       INTEGER,
    payload         TEXT NOT NULL,         -- full scored case JSON
    created_at      TEXT NOT NULL,
    FOREIGN KEY (video_id) REFERENCES dockets(video_id)
);

CREATE TABLE IF NOT EXISTS clips (
    clip_id         TEXT PRIMARY KEY,      -- case_key:kind
    case_key        TEXT NOT NULL,
    kind            TEXT NOT NULL,         -- longform | short
    file_path       TEXT,
    duration_s      REAL,
    title           TEXT,
    description     TEXT,
    rendered_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'rendered',
    spec_version    TEXT,
    FOREIGN KEY (case_key) REFERENCES cases(case_key)
);

CREATE TABLE IF NOT EXISTS publications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id         TEXT NOT NULL,
    platform        TEXT NOT NULL,
    remote_id       TEXT,
    url             TEXT,
    privacy         TEXT,
    published_at    TEXT NOT NULL,
    UNIQUE (clip_id, platform)
);

CREATE TABLE IF NOT EXISTS ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_key        TEXT NOT NULL,
    decision        TEXT NOT NULL,         -- approved | rejected | takedown
    reason          TEXT,
    safety_related  INTEGER NOT NULL DEFAULT 0,
    decided_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_video ON cases(video_id);
CREATE INDEX IF NOT EXISTS idx_clips_case  ON clips(case_key);
CREATE INDEX IF NOT EXISTS idx_ledger_time ON ledger(decided_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Statuses meaning "do not look at this docket again". Everything else —
# discovered, transcribed, analyzed, error, refused — is retried on the next
# run, which is what makes a failed or dry run recoverable.
TERMINAL_STATUSES = frozenset({"complete", "no_eligible_cases"})


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        """Read-only access for modules that only query.

        Anything that WRITES must go through tx() so it lands in a
        transaction; this exists so read-only analysis (repeats.py) does not
        have to reach into a private attribute.
        """
        return self._conn

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---------------------------------------------------------------- dockets

    def seen_docket(self, video_id: str) -> bool:
        """Has this docket ever been recorded? Use `is_terminal` to decide
        whether to skip it — a recorded docket is not a finished one."""
        row = self._conn.execute(
            "SELECT 1 FROM dockets WHERE video_id = ?", (video_id,)
        ).fetchone()
        return row is not None

    def is_terminal(self, video_id: str) -> bool:
        """True only when a docket is genuinely done with.

        Deliberately narrow. A docket is recorded the moment it is discovered,
        long before any work happens, so treating "recorded" as "finished"
        means a dry run, a crash, or an API outage silently consumes the
        docket and it is never processed again.
        """
        row = self._conn.execute(
            "SELECT status FROM dockets WHERE video_id = ?", (video_id,)
        ).fetchone()
        return row is not None and row["status"] in TERMINAL_STATUSES

    def add_docket(self, video_id: str, title: str, docket_date: str, duration_s: float) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO dockets "
                "(video_id, title, docket_date, duration_s, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (video_id, title, docket_date, duration_s, _now()),
            )

    def mark_docket(self, video_id: str, status: str, error: str | None = None, **stamps: str) -> None:
        sets = ["status = ?", "error = ?"]
        vals: list[Any] = [status, error]
        for field, value in stamps.items():
            sets.append(f"{field} = ?")
            vals.append(value)
        vals.append(video_id)
        with self.tx() as c:
            c.execute(f"UPDATE dockets SET {', '.join(sets)} WHERE video_id = ?", vals)

    def pending_dockets(self) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM dockets WHERE status IN ('discovered', 'transcribed') "
                "ORDER BY docket_date ASC"
            )
        )

    # ------------------------------------------------------------------ cases

    @staticmethod
    def case_key(video_id: str, start_s: float) -> str:
        return f"{video_id}:{int(round(start_s))}"

    def save_case(self, video_id: str, case: dict[str, Any], rank: int | None) -> str:
        key = self.case_key(video_id, case["start_s"])
        safety = case.get("safety", {})
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO cases (case_key, video_id, start_s, end_s, "
                "defendant, cause_number, proceeding_type, guilt_posture, safety_pass, "
                "safety_rules, total_score, rank, shortable, payload, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    video_id,
                    case["start_s"],
                    case["end_s"],
                    case.get("defendant_name"),
                    case.get("cause_number"),
                    case.get("proceeding_type"),
                    case.get("guilt_posture"),
                    1 if safety.get("safety_pass") else 0,
                    json.dumps(safety.get("safety_rule_violations", [])),
                    case.get("total_score"),
                    rank,
                    1 if case.get("shortable") else 0,
                    json.dumps(case, ensure_ascii=False),
                    _now(),
                ),
            )
        return key

    def case_published(self, case_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM publications p JOIN clips c ON c.clip_id = p.clip_id "
            "WHERE c.case_key = ? LIMIT 1",
            (case_key,),
        ).fetchone()
        return row is not None

    def get_case(self, case_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload FROM cases WHERE case_key = ?", (case_key,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def cases_for_docket(self, video_id: str) -> list[sqlite3.Row]:
        """Every case row stored for a docket. Used to detect the case where a
        scored.json cache exists but its DB rows were never written."""
        return list(self._conn.execute(
            "SELECT case_key FROM cases WHERE video_id = ?", (video_id,)))

    def case_windows(self, video_id: str, start_s: float) -> list[tuple[float, float]]:
        """Every window in the docket belonging to the same case, in order.

        A hearing that is recessed and recalled later in the docket is ONE case
        heard in two sittings, but the segmenter sees two runs of transcript and
        writes two rows. Rendering only the row it was handed produces a
        long-form that stops at the recess — Louis Fletcher Thompson,
        2022 CR0273, was published as 6698-6958 (260s) when the judge's ruling
        is in the second sitting at 8279-8843, so the clip ended on "have a
        seat and we'll see" and never showed the outcome.

        Identity is the cause number, not adjacency: two sittings can be an hour
        apart with a dozen unrelated cases between them. Dockets where the
        cause number was never parsed ("unknown") fall back to the single
        window — grouping every unknown in a docket would merge strangers.
        """
        row = self._conn.execute(
            "SELECT cause_number FROM cases WHERE video_id = ? AND start_s = ?",
            (video_id, start_s),
        ).fetchone()
        cause = row["cause_number"] if row else None
        if not cause or cause == "unknown":
            hit = self._conn.execute(
                "SELECT start_s, end_s FROM cases WHERE video_id = ? AND start_s = ?",
                (video_id, start_s),
            ).fetchone()
            return [(float(hit["start_s"]), float(hit["end_s"]))] if hit else []

        return [
            (float(r["start_s"]), float(r["end_s"]))
            for r in self._conn.execute(
                "SELECT start_s, end_s FROM cases "
                "WHERE video_id = ? AND cause_number = ? ORDER BY start_s",
                (video_id, cause),
            )
        ]

    def get_docket_row(self, video_id: str) -> sqlite3.Row | None:
        """The stored docket for a case, so a single case can be rendered
        without re-running discovery over the whole channel."""
        return self._conn.execute(
            "SELECT * FROM dockets WHERE video_id = ?", (video_id,)
        ).fetchone()

    def banked_cases(self, limit: int = 20) -> list[sqlite3.Row]:
        """Qualifying cases that were never published — inventory for slow days."""
        return list(
            self._conn.execute(
                "SELECT c.* FROM cases c "
                "WHERE c.safety_pass = 1 AND c.total_score IS NOT NULL "
                "AND c.case_key NOT IN (SELECT case_key FROM clips) "
                "ORDER BY c.total_score DESC LIMIT ?",
                (limit,),
            )
        )

    # ------------------------------------------------------------------ clips

    def save_clip(
        self,
        case_key: str,
        kind: str,
        file_path: Path,
        duration_s: float,
        title: str,
        description: str,
        spec_version: str,
    ) -> str:
        clip_id = f"{case_key}:{kind}"
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO clips (clip_id, case_key, kind, file_path, "
                "duration_s, title, description, rendered_at, status, spec_version) "
                "VALUES (?,?,?,?,?,?,?,?,'rendered',?)",
                (
                    clip_id,
                    case_key,
                    kind,
                    str(file_path),
                    duration_s,
                    title,
                    description,
                    _now(),
                    spec_version,
                ),
            )
        return clip_id

    def set_clip_description(self, clip_id: str, description: str) -> None:
        """Used to inject the long-form URL into the short after publish."""
        with self.tx() as c:
            c.execute(
                "UPDATE clips SET description = ? WHERE clip_id = ?",
                (description, clip_id),
            )

    def record_publication(
        self, clip_id: str, platform: str, remote_id: str, url: str, privacy: str
    ) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO publications "
                "(clip_id, platform, remote_id, url, privacy, published_at) "
                "VALUES (?,?,?,?,?,?)",
                (clip_id, platform, remote_id, url, privacy, _now()),
            )
            c.execute("UPDATE clips SET status = 'published' WHERE clip_id = ?", (clip_id,))

    def publication_url(self, clip_id: str, platform: str) -> str | None:
        row = self._conn.execute(
            "SELECT url FROM publications WHERE clip_id = ? AND platform = ?",
            (clip_id, platform),
        ).fetchone()
        return row["url"] if row else None

    # ----------------------------------------------------------------- ledger

    def record_decision(
        self, case_key: str, decision: str, reason: str = "", safety_related: bool = False
    ) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO ledger (case_key, decision, reason, safety_related, decided_at) "
                "VALUES (?,?,?,?,?)",
                (case_key, decision, reason, 1 if safety_related else 0, _now()),
            )

    def reliability(self) -> dict[str, Any]:
        """The evidence base for promoting autonomy.mode. Not a vibe check."""
        # `id DESC` is the tiebreaker, not decoration: decided_at has
        # second resolution, so decisions recorded in the same second tie and
        # SQLite may order a rejection behind an approval — inflating
        # consecutive_approvals, which is the number that gates autonomy.
        rows = list(
            self._conn.execute(
                "SELECT decision, safety_related FROM ledger "
                "ORDER BY decided_at DESC, id DESC"
            )
        )
        total = len(rows)
        approved = sum(1 for r in rows if r["decision"] == "approved")
        safety_rejects = sum(
            1 for r in rows if r["decision"] in ("rejected", "takedown") and r["safety_related"]
        )

        consecutive = 0
        for r in rows:  # newest first
            if r["decision"] == "approved":
                consecutive += 1
            else:
                break

        return {
            "total_decisions": total,
            "approved": approved,
            "approval_rate": round(approved / total, 3) if total else None,
            "consecutive_approvals": consecutive,
            "safety_rejects": safety_rejects,
        }

    def promotion_ready(self, min_consecutive: int, max_safety_rejects: int) -> tuple[bool, str]:
        r = self.reliability()
        if r["consecutive_approvals"] < min_consecutive:
            return False, (
                f"{r['consecutive_approvals']}/{min_consecutive} consecutive approvals"
            )
        if r["safety_rejects"] > max_safety_rejects:
            return False, (
                f"{r['safety_rejects']} safety rejects on record "
                f"(gate allows {max_safety_rejects})"
            )
        return True, "promotion gate satisfied"
