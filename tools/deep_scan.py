"""Search what the pipeline already owns, across every date.

Step beyond `source.max_age_days: 4`, which is why the daily route only ever
sees this week. This reads the local store (state/pipeline.db) — every docket
already discovered and every case already scored — and ranks it. No network, no
model calls.

    python tools/deep_scan.py            # top cases by stored score
    python tools/deep_scan.py --candidates  # shortable, never rendered, any date
    python tools/deep_scan.py --schema   # what the store actually holds
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "state" / "pipeline.db"


def connect() -> sqlite3.Connection:
    if not DB.is_file():
        raise SystemExit(f"deep_scan: no store at {DB}")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def schema(conn: sqlite3.Connection) -> None:
    for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        name = row["name"]
        cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({name})")]
        count = conn.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
        print(f"{name} ({count} rows): {', '.join(cols)}")


def top(limit: int = 20) -> int:
    conn = connect()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "cases" not in tables:
        print("deep_scan: no 'cases' table; run with --schema")
        return 1
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(cases)")}
    score_col = next((c for c in ("score", "total_score", "total", "rank_score") if c in cols), None)
    if not score_col:
        print(f"deep_scan: cases has no score column ({', '.join(sorted(cols))}); run with --schema")
        return 1
    fields = [c for c in ("video_id", "start_s", "end_s", "score", "total_score", "title", "status")
              if c in cols]
    rows = conn.execute(
        f"SELECT {', '.join(fields)} FROM cases ORDER BY {score_col} DESC LIMIT ?", (limit,)
    ).fetchall()
    print(f"top {len(rows)} cases by {score_col} (all dates in the store):")
    for row in rows:
        video = row["video_id"] if "video_id" in fields else "?"
        start = row["start_s"] if "start_s" in fields else "?"
        score = row[score_col]
        title = (row["title"] if "title" in fields else "") or ""
        print(f"  {score:>6}  {video}:{start}  {str(title)[:70]}")
    return 0


def candidates(limit: int = 12) -> int:
    """Shortable cases with nothing rendered yet — the backlog the daily route ignores.

    The daily route looks back four days; this looks at everything the store has
    ever scored and excludes anything that already produced a clip, so it can
    hand the pipeline the best unused material instead of the newest.

    2026-09-16: "already produced a clip" has to mean the STORY, not the row.
    dAKO7myCd-g was scored twice — 8340 (8340-9465, cause 2023 CR 10327, clips on
    disk) and 8929 (8929-9469, cause "unknown") — and this query offered the
    second row as never-rendered material. The run it produced was a second
    package for the same nine minutes. A candidate window that is mostly inside a
    rendered window on the same docket is excluded now, alongside the exact-key
    and same-cause matches the pipeline's own selection guard also makes.
    """
    conn = connect()
    rows = conn.execute(
        """
        SELECT c.case_key, c.video_id, c.start_s, c.end_s, c.total_score, c.defendant,
               c.proceeding_type, c.guilt_posture, d.title AS docket_title, d.docket_date
        FROM cases c
        LEFT JOIN clips cl ON cl.case_key = c.case_key
        LEFT JOIN dockets d ON d.video_id = c.video_id
        WHERE COALESCE(c.shortable, 0) = 1
          AND cl.case_key IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM clips made_clip
              JOIN cases made_case ON made_case.case_key = made_clip.case_key
              WHERE made_case.video_id = c.video_id
                AND (
                    (c.end_s > c.start_s
                     AND (MIN(c.end_s, made_case.end_s) - MAX(c.start_s, made_case.start_s))
                         >= 0.5 * (c.end_s - c.start_s))
                    OR (c.cause_number IS NOT NULL AND c.cause_number != 'unknown'
                        AND made_case.cause_number = c.cause_number)
                )
          )
        ORDER BY c.total_score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    # 2026-09-16: this list is case-key filtered, and a re-scored hearing has a
    # new case key. The story ledger is the level at which "already made" is
    # true, so every row is checked against it before it is offered.
    ledger_note = ""
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from boydclips.stories import StoryLedger  # noqa: WPS433

        ledger = StoryLedger(conn)
        kept: list = []
        skipped: list = []
        for row in rows:
            blocked, why = ledger.selection_block(
                row["video_id"], row["start_s"], row["end_s"], None, row["defendant"])
            (skipped if blocked else kept).append((row, why))
        if skipped:
            ledger_note = (
                f"\nstory ledger: {len(skipped)} case(s) already have a story on record "
                "and were not offered:\n"
                + "\n".join(f"  {row['case_key']:<26} {why}" for row, why in skipped[:6]))
        rows = [row for row, _ in kept]
    except Exception as exc:  # noqa: BLE001 — a missing ledger must not fake a clean list
        ledger_note = (f"\nstory ledger unavailable ({exc}); this list is case-key "
                       "based only — check `python tools/story_ledger.py preflight` first")
    if not rows:
        print("deep_scan: no unused shortable cases in the store")
        if ledger_note:
            print(ledger_note)
        return 1
    print(f"top {len(rows)} unused shortable cases, any date:")
    for row in rows:
        print(f"  {row['total_score']:>6}  {row['case_key']:<24} {row['docket_date'] or '?'}  "
              f"{row['proceeding_type'] or '?':<22} {str(row['defendant'] or '')[:26]}")
    if ledger_note:
        print(ledger_note)
    print("\nproceeding_type and defendant are for selection only — no names in titles or thumbnail text.")
    return 0


if __name__ == "__main__":
    if "--schema" in sys.argv:
        schema(connect())
        raise SystemExit(0)
    if "--candidates" in sys.argv:
        raise SystemExit(candidates())
    raise SystemExit(top())
