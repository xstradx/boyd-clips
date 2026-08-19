"""Group a defendant's hearings into one story.

The product is one defendant across every appearance we have, in order - see
spec/SPEC.md §1. This module answers the only hard question in that: which rows
in the bank are the same person.

WHAT THE DATA LOOKS LIKE, measured over 727 cases:
  defendant_name  present in 727 (100%)
  cause_number    present in 257 (35%), and dirty when it is there -
                  "2026 CR 00008177", "2026-CR-0008177", "2026-CR-455",
                  "2026 CR 455 (as spoken; likely truncated)",
                  "2026-CR-0000426 / 2026-CR-0000424"

So the name is the primary key and the cause number corroborates. That is the
opposite of what a court records system would do, and it is forced by the
source: these fields are read out of an ASR transcript, not a database.

Both keys are unioned rather than requiring agreement. A defendant whose name
was transcribed two different ways still joins on a shared cause number, and a
defendant whose cause number was never spoken still joins on the name.

FALSE MERGES are the risk that matters - two different people stitched into one
video is a much worse failure than a missed sequel. So the name key requires
BOTH a first and last name; a bare surname never merges anything.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|the third|junior|senior)\b\.?", re.I)
PARENS = re.compile(r"\(.*?\)")
NOT_LETTERS = re.compile(r"[^a-z ]")
CAUSE = re.compile(r"(\d{4})\s*-?\s*CR\s*-?\s*0*(\d+)", re.I)


def normalize_name(name: str | None) -> str:
    """A comparable form of a spoken name, or "" if it cannot be trusted.

    Returns empty for anything with fewer than two name parts. "Castillo"
    alone would merge every Castillo on the docket into one person, and a
    wrong merge produces a video about two strangers.
    """
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = PARENS.sub(" ", n)            # "Raquel McMasters (McMaster)"
    n = SUFFIXES.sub(" ", n)          # "Anthony Blackburn Sr."
    n = NOT_LETTERS.sub(" ", n.lower())
    parts = [p for p in n.split() if len(p) > 1]
    if len(parts) < 2:
        return ""
    # First and last only. Middle names appear inconsistently between hearings.
    return f"{parts[0]} {parts[-1]}"


def normalize_causes(cause: str | None) -> set[str]:
    """Every cause number in the field, canonicalised.

    One field can hold several ("2026-CR-0000426 / 2026-CR-0000424") and the
    same cause appears with and without padding zeros between hearings, so this
    returns a SET of {year}CR{digits} with the padding stripped.
    """
    if not cause:
        return set()
    return {f"{y}CR{int(num)}" for y, num in CAUSE.findall(cause)}


class _Union:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_arcs(
    db_path: Path,
    *,
    eligible_only: bool = True,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Every defendant with at least one appearance, newest activity first.

    An arc with a single chapter is still an arc - it is a one-chapter story,
    and most defendants only appear once. The format does not require a sequel,
    it just uses one when it exists.
    """
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    dockets = {r["video_id"]: r for r in db.execute("select * from dockets")}

    rows: list[dict[str, Any]] = []
    for r in db.execute("select video_id, payload from cases"):
        p = json.loads(r["payload"])
        if eligible_only and not (
            p.get("eligible") and (p.get("safety") or {}).get("safety_pass")
        ):
            continue
        if (p.get("total_score") or 0) < min_score:
            continue
        vid = r["video_id"]
        d = dockets.get(vid)
        rows.append({
            "video_id": vid,
            "case_key": f'{vid}:{int(round(p["start_s"]))}',
            "docket_date": (d["docket_date"] if d else "") or "",
            "start_s": float(p["start_s"]),
            "end_s": float(p["end_s"]),
            "name": p.get("defendant_name") or "?",
            "name_key": normalize_name(p.get("defendant_name")),
            "causes": normalize_causes(p.get("cause_number")),
            "score": float(p.get("total_score") or 0),
            "proceeding_type": p.get("proceeding_type") or "",
            "summary": p.get("summary") or "",
            "shortable": bool(p.get("shortable")),
        })

    # Union on the name key, then on every shared cause number.
    u = _Union()
    for row in rows:
        anchor = f"case:{row['case_key']}"
        u.find(anchor)
        if row["name_key"]:
            u.union(f"name:{row['name_key']}", anchor)
        for c in row["causes"]:
            u.union(f"cause:{c}", anchor)

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(u.find(f"case:{row['case_key']}"), []).append(row)

    arcs = []
    for chapters in groups.values():
        chapters.sort(key=lambda c: (c["docket_date"], c["start_s"]))
        # The longest spelling is usually the most complete one ("Anthony
        # Blackburn Sr." over "Blackburn"), and it is what goes in the title.
        display = max((c["name"] for c in chapters), key=len)
        runtime = sum(c["end_s"] - c["start_s"] for c in chapters)
        arcs.append({
            "defendant": display,
            "name_key": next((c["name_key"] for c in chapters if c["name_key"]), ""),
            "chapters": chapters,
            "n_chapters": len(chapters),
            "n_dockets": len({c["video_id"] for c in chapters}),
            "runtime_s": runtime,
            "best_score": max(c["score"] for c in chapters),
            "mean_score": sum(c["score"] for c in chapters) / len(chapters),
            "first_date": chapters[0]["docket_date"],
            "last_date": chapters[-1]["docket_date"],
            "causes": sorted({c for ch in chapters for c in ch["causes"]}),
        })

    # Rank by the BEST HEARING, not by how often the person turned up.
    #
    # This sorted on -n_dockets first and it was wrong. It put Robert Castillo
    # top on 9 appearances with a best chapter of 81.5, and pushed Anthony
    # Blackburn — the highest-scoring case in the entire bank at 92.1 — down to
    # third. Frequency is not quality. A defendant with one outstanding hearing
    # beats a defendant with nine procedural ones, and nine boring chapters is
    # nine boring chapters however well they stitch together.
    #
    # Extra appearances are CONTEXT for a case that already earned its place.
    # They are the reason to open the video, never the reason to make it. So
    # the tiebreak, not the sort.
    arcs.sort(key=lambda a: (-a["best_score"], -a["n_dockets"], -a["runtime_s"]))
    return arcs
