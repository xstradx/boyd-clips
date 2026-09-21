"""Build and read the story ledger — the project's answer to
"have we already made a video about this case?".

    python tools/story_ledger.py build      # backfill from every local evidence source
    python tools/story_ledger.py report      # write the reconciliation report
    python tools/story_ledger.py verify      # what the ledger claims still exists on disk
    python tools/story_ledger.py preflight dAKO7myCd-g:8929
    python tools/story_ledger.py profile     # write the Shorts editing profile
    python tools/story_ledger.py stories [--with-packages]

Evidence sources, each recorded with the file it came from:

  state/pipeline.db                    cases, clips, dockets (the pipeline's record)
  out/review/*/manifest.json           every rendered bundle, including superseded ones
  D:/Boyd Clips/BANGERS/READY-2026-09-11/READY_MANIFEST.json
                                       the archived five-pair delivery, with hashes
  D:/Boyd Clips/READY-TO-POST/*/STATUS.md
                                       the earlier hand-built packages
  D:/Boyd Clips/thumbwork/dAKO7myCd-g_8340_*   thumbnail work on the Garcia story
  ~/OneDrive/Pictures/Boyd-Review      what was handed over for review

Curated entries at the bottom carry the editorial facts no scanner can infer
(who approved what, who rejected what, in whose words). Each quotes its source.
Nothing here guesses: an artifact with no recorded verdict stays UNREVIEWED, and
a story whose identity is only a surname resemblance is marked POSSIBLE_MATCH.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips.stories import EDITORIAL_STATUSES, StoryLedger, now  # noqa: E402

DB = ROOT / "state" / "pipeline.db"
ARCHIVE = Path("D:/Boyd Clips")
DELIVERY = Path.home() / "OneDrive" / "Pictures" / "Boyd-Review"

SHORT_REJECTION_NOTE = (
    "2026-09-16, user: the Short cut for dAKO7myCd-g:8929 is NOT editorially "
    "accepted. TECHNICAL_SHORT_STATUS=VALID, EDITORIAL_SHORT_STATUS=REJECTED / "
    "NEEDS_USER_REEDIT. A valid file, decode rc=0 and ready:true are not approval."
)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip()) if out.stdout.strip() else None
    except Exception:  # noqa: BLE001 - a duration is a nicety, not a gate
        return None


def from_store(ledger: StoryLedger) -> dict[str, str]:
    """Every rendered case in the pipeline's own store, and its clips."""
    mapping: dict[str, str] = {}
    rows = list(ledger.conn.execute(
        "SELECT c.case_key, c.video_id, c.start_s, c.end_s, c.cause_number, c.defendant,"
        " c.total_score, d.docket_date, d.title"
        " FROM clips cl JOIN cases c ON c.case_key = cl.case_key"
        " LEFT JOIN dockets d ON d.video_id = c.video_id"
        " GROUP BY c.case_key ORDER BY c.start_s"))
    for row in rows:
        story_id = resolve_story(ledger, row["video_id"], row["start_s"], row["end_s"],
                                 row["cause_number"], row["defendant"])
        mapping[row["case_key"]] = story_id
        ledger.upsert_story(
            story_id,
            label=(f"{row['defendant'] or 'unknown defendant'} — "
                   f"{row['docket_date'] or 'undated'}"),
            cause_number=row["cause_number"],
            defendant_label=row["defendant"],
            confidence="CONFIRMED",
            notes=(f"pipeline case {row['case_key']} scored {row['total_score']}; "
                   f"docket {row['title'] or 'unknown'}"),
        )
        ledger.add_source(story_id, row["video_id"], row["start_s"], row["end_s"],
                          hearing_date=row["docket_date"],
                          source_url=f"https://www.youtube.com/watch?v={row['video_id']}",
                          cause_number=row["cause_number"],
                          evidence=f"state/pipeline.db cases {row['case_key']}",
                          confidence="CONFIRMED")
        for clip in ledger.conn.execute(
                "SELECT kind, file_path, duration_s, rendered_at FROM clips"
                " WHERE case_key = ?", (row["case_key"],)):
            path = Path(clip["file_path"])
            ledger.add_artifact(
                story_id, clip["kind"], path,
                sha256=sha256(path) if path.is_file() else None,
                duration_s=clip["duration_s"],
                technical_status="VALID" if path.is_file() else "MISSING",
                editorial_status="UNREVIEWED",
                publication_status="UNKNOWN",
                created_at=clip["rendered_at"],
                evidence=f"state/pipeline.db clips {row['case_key']}:{clip['kind']}",
            )
    return mapping


def _story_from_dirname(ledger: StoryLedger, dirname: str) -> str | None:
    """Resolve a review-directory name to the story its WINDOW belongs to.

    The first version looked up the first story for the video id alone, so every
    superseded render on a docket landed on that docket's earliest story
    (measured: one story collected 31 Shorts). Video ids contain underscores, so
    the name cannot be split by position either — the video ids already in the
    ledger are matched as prefixes, then the trailing number is the window start.
    """
    match = re.match(r"(\d{4}-\d{2}-\d{2})_(.+)$", dirname)
    if not match:
        return None
    rest = match.group(2)
    for row in ledger.conn.execute("SELECT DISTINCT video_id FROM story_sources"):
        video_id = row["video_id"]
        if not rest.startswith(video_id):
            continue
        tail = rest[len(video_id):].strip("_")
        start_match = re.match(r"(\d+)", tail)
        start_s = float(start_match.group(1)) if start_match else None
        for source in ledger.conn.execute(
                "SELECT story_id, start_s, end_s FROM story_sources WHERE video_id = ?",
                (video_id,)):
            if start_s is None or source["end_s"] is None:
                continue
            if source["start_s"] <= start_s <= float(source["end_s"]):
                return source["story_id"]
    return None


def resolve_story(ledger: StoryLedger, video_id: str, start_s: float,
                  end_s: float | None, cause_number: str | None,
                  defendant_label: str | None = None,
                  label_hint: str | None = None) -> str:
    """The story a source belongs to — cause first, then the window, then a lead.

    Creating a story per row is exactly the bug this ledger exists to undo, so
    every evidence source goes through here instead of `story_id()`.
    """
    kind, story_id, _why = ledger.match(video_id, start_s, end_s or start_s,
                                       cause_number, defendant_label)
    if kind == "EXISTING" and story_id:
        return story_id
    if label_hint:
        needle = re.sub(r"[^a-z0-9]", "", label_hint.lower())
        if needle:
            for row in ledger.conn.execute(
                    "SELECT story_id, label, defendant_label, notes FROM stories"):
                hay = re.sub(r"[^a-z0-9]", "", " ".join(
                    str(row[key] or "") for key in ("label", "defendant_label", "notes")
                ).lower())
                if needle in hay:
                    return row["story_id"]
    return ledger.story_id(video_id, start_s, cause_number)


def reset(conn: sqlite3.Connection) -> None:
    """The ledger is derived from evidence plus the curated block — rebuild it."""
    with conn:
        for table in ("story_artifacts", "story_sources", "story_decisions",
                      "story_feedback", "stories", "short_edit_profile", "story_index"):
            conn.execute(f"DELETE FROM {table}")


def from_review(ledger: StoryLedger, mapping: dict[str, str]) -> int:
    """Every review bundle's manifest, plus any superseded render beside it."""
    seen = 0
    for directory in sorted((ROOT / "out" / "review").iterdir()):
        if not directory.is_dir():
            continue
        manifest = directory / "manifest.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            video_id = (data.get("source") or {}).get("video_id")
            case = data.get("case") or {}
            if not video_id or case.get("start_s") is None:
                continue
            story_id = resolve_story(ledger, video_id, case["start_s"], case.get("end_s"),
                                     case.get("cause_number"),
                                     case.get("defendant_name"))
            mapping.setdefault(f"{video_id}:{case['start_s']}", story_id)
            ledger.upsert_story(
                story_id,
                label=(f"{case.get('defendant_name') or 'unknown defendant'} — "
                       f"{(data.get('source') or {}).get('docket_date') or 'undated'}"),
                cause_number=case.get("cause_number"),
                defendant_label=case.get("defendant_name"),
                notes=f"review bundle {directory.name}",
            )
            ledger.add_source(story_id, video_id, case["start_s"], case.get("end_s"),
                              hearing_date=(data.get("source") or {}).get("docket_date"),
                              source_url=(data.get("source") or {}).get("url"),
                              cause_number=case.get("cause_number"),
                              evidence=f"out/review/{directory.name}/manifest.json",
                              confidence="CONFIRMED")
            outputs = data.get("outputs") or {}
            for key, kind in (("longform", "longform"), ("short", "short"),
                              ("thumbnail", "thumbnail")):
                record = outputs.get(key) or {}
                path_value = record.get("file_path")
                if not path_value:
                    continue
                path = Path(path_value)
                # The review workflow writes the editorial verdict into the
                # manifest (`boyd reject --short` does). A rebuild must preserve
                # it, or the next `build` would quietly reset a rejection to
                # UNREVIEWED — the exact "valid file = approved" mistake.
                status = str(record.get("editorial_status") or "").upper()
                editorial = status if status in EDITORIAL_STATUSES else "UNREVIEWED"
                ledger.add_artifact(
                    story_id, kind, path,
                    sha256=record.get("sha256") or (sha256(path) if path.is_file() else None),
                    duration_s=record.get("duration_s"),
                    technical_status="VALID" if path.is_file() else "MISSING",
                    editorial_status=editorial,
                    publication_status="UNKNOWN",
                    created_at=data.get("generated_at"),
                    evidence=f"out/review/{directory.name}/manifest.json",
                    note=(f"bundle status {data.get('status')}; thumbnail construction "
                          f"{record.get('construction') or 'legacy'}"
                          + (f"; {record.get('editorial_note')}"
                             if record.get("editorial_note") else "")),
                )
            vertical = (outputs.get("short") or {}).get("vertical_thumbnail") or {}
            if vertical.get("file_path"):
                path = Path(vertical["file_path"])
                ledger.add_artifact(
                    story_id, "short_thumbnail", path,
                    sha256=vertical.get("sha256"),
                    technical_status="VALID" if path.is_file() else "MISSING",
                    editorial_status="UNREVIEWED",
                    publication_status="UNKNOWN",
                    created_at=data.get("generated_at"),
                    evidence=f"out/review/{directory.name}/manifest.json",
                    note=f"hook {vertical.get('hook_text')!r}",
                )
            seen += 1

        for sub in directory.glob("superseded_*"):
            story_id = mapping.get(directory.name) or _story_from_dirname(ledger, directory.name)
            if not story_id:
                continue
            for media in list(sub.glob("*.mp4")) + list(sub.glob("*.jpg")):
                if not media.is_file():
                    continue
                kind = ("short" if "short" in media.name.lower()
                        else "thumbnail" if media.suffix == ".jpg" else "longform")
                ledger.add_artifact(
                    story_id, kind, media, sha256=sha256(media),
                    technical_status="VALID", editorial_status="SUPERSEDED",
                    publication_status="UNKNOWN",
                    evidence=f"out/review/{directory.name}/{sub.name}",
                    note="superseded render kept beside the current one",
                )
    return seen


def from_archive(ledger: StoryLedger) -> int:
    """The hand-built packages under D:/Boyd Clips, with their own manifests."""
    count = 0
    archive_manifest = ARCHIVE / "BANGERS" / "READY-2026-09-11" / "READY_MANIFEST.json"
    if archive_manifest.is_file():
        data = json.loads(archive_manifest.read_text(encoding="utf-8"))
        for pair in data.get("pairs") or []:
            video_id = pair.get("source_video_id")
            case_key = str(pair.get("case_key") or "")
            start_s = float(case_key.split(":")[-1]) if ":" in case_key else 0.0
            story_id = resolve_story(ledger, video_id, start_s, None,
                                     pair.get("cause_number"),
                                     pair.get("defendant_name"), pair.get("label"))
            ledger.upsert_story(
                story_id,
                label=f"{pair.get('defendant_name')} — {pair.get('hearing_date')}",
                cause_number=pair.get("cause_number"),
                defendant_label=pair.get("defendant_name"),
                publication_status="NONE",
                notes=f"archived pair {pair.get('label')}",
            )
            ledger.add_source(story_id, video_id, start_s, None,
                              hearing_date=pair.get("hearing_date"),
                              source_url=f"https://www.youtube.com/watch?v={video_id}",
                              cause_number=pair.get("cause_number"),
                              evidence=str(archive_manifest), confidence="CONFIRMED")
            for field, kind in (("long_path", "longform"), ("short_path", "short"),
                                ("rough_short_path", "short")):
                value = pair.get(field)
                if not value:
                    continue
                path = Path(value)
                ledger.add_artifact(
                    story_id, kind, path,
                    sha256=(pair.get("long_sha256") if kind == "longform"
                            else pair.get("short_sha256")) or None,
                    technical_status="VALID" if path.is_file() else "MISSING",
                    editorial_status=("SUPERSEDED" if field == "rough_short_path"
                                      else "UNREVIEWED"),
                    publication_status="NONE",
                    evidence=str(archive_manifest),
                    note=(f"{pair.get('label')} {field}; platform status: "
                          f"{data.get('platform_status')}"),
                )
            count += 1

    for status in sorted((ARCHIVE / "READY-TO-POST").glob("*/STATUS.md")):
        text = status.read_text(encoding="utf-8", errors="replace")
        head = text.splitlines()[0].lstrip("# ").strip()
        cause_match = re.search(r"(20\d\d\s?-?\s?CR\s?\d+)", head, re.IGNORECASE)
        cause = cause_match.group(1) if cause_match else None
        video_match = re.search(r"watch\?v=([A-Za-z0-9_\-]{6,})", text)
        video_id = video_match.group(1) if video_match else None
        label = head.split(" - ")[0].strip()
        if video_id:
            start_match = re.search(r"docket call at (?:stream )?t=(\d+(?:\.\d+)?)", text)
            start_s = float(start_match.group(1)) if start_match else 0.0
            story_id = resolve_story(ledger, video_id, start_s, None, cause, head,
                                     status.parent.name)
            ledger.add_source(story_id, video_id, start_s, None,
                              source_url=f"https://www.youtube.com/watch?v={video_id}",
                              cause_number=cause, evidence=str(status),
                              confidence="CONFIRMED")
        else:
            story_id = resolve_story(ledger, "", 0.0, None, cause, head,
                                     status.parent.name)
            if not story_id or story_id.startswith("window:"):
                story_id = f"archive:{label.lower()}"
        ledger.upsert_story(
            story_id, label=head, cause_number=cause, defendant_label=head,
            publication_status="NONE",
            notes=(f"archived package {status.parent.name}; source video id "
                   f"{video_id or 'not recorded in STATUS.md'}"),
        )
        for media in sorted(status.parent.glob("*.mp4")):
            lowered = media.name.lower()
            kind = "short" if "short" in lowered else "longform"
            superseded = "rough" in lowered or "_v2" in lowered
            ledger.add_artifact(
                story_id, kind, media, sha256=sha256(media),
                duration_s=probe_duration(media),
                technical_status="VALID",
                editorial_status="SUPERSEDED" if superseded else "UNREVIEWED",
                publication_status="NONE",
                evidence=str(status),
                note=("Nothing uploaded, posted or made public"
                      if "Nothing uploaded" in text else "archived export"),
            )
        for image in sorted(status.parent.glob("*.jpg")):
            approved = "approved" in image.name.lower()
            ledger.add_artifact(
                story_id, "thumbnail", image, sha256=sha256(image),
                technical_status="VALID",
                editorial_status="APPROVED" if approved else "UNREVIEWED",
                publication_status="NONE", evidence=str(status),
                note=("filename records user approval" if approved
                      else "archived thumbnail candidate"),
            )
        count += 1

    for brief in sorted((ARCHIVE / "thumbwork").glob("dAKO7myCd-g_8340*/**/brief.json")):
        story_id = ledger.story_id("dAKO7myCd-g", 8340.0, "2023 CR 10327")
        content = json.loads(brief.read_text(encoding="utf-8"))
        ledger.add_artifact(
            story_id, "packaging", brief, sha256=sha256(brief),
            technical_status="VALID", editorial_status="UNREVIEWED",
            publication_status="NONE", evidence=str(brief),
            note=("thumbnail art-direction brief for the 8340 render; money moment "
                  f"{content.get('money_moment')!r}"),
        )
        count += 1
    originals = ARCHIVE / "ORIGINAL-ASSETS-2026-09-07" / "GARCIA"
    for image in sorted(originals.glob("dAKO7myCd-g_8340_*_ORIGINAL.jpg")):
        story_id = ledger.story_id("dAKO7myCd-g", 8340.0, "2023 CR 10327")
        ledger.add_artifact(
            story_id, "thumbnail", image, sha256=sha256(image),
            technical_status="VALID", editorial_status="UNREVIEWED",
            publication_status="NONE", evidence=str(image),
            note="direct_gen ORIGINAL thumbnail for the 8340 render",
        )
        count += 1

    # Top-level exports in READY-TO-POST have no STATUS.md: their identity is
    # only the leading token of the filename, so an unresolved token becomes an
    # archive story marked NEEDS_REVIEW rather than being guessed onto a case.
    for media in sorted((ARCHIVE / "READY-TO-POST").glob("*.mp4")):
        token = media.stem.split("_")[0]
        if len(token) < 4 or token.startswith("_"):
            continue
        # Only a package shape is a package: the same folder holds experiment
        # clips (ANIMATION-OPTIONS, CAPTION-ENTRANCE-AB) and the first version of
        # this scan turned each of them into a story.
        if not re.search(r"_(LONGFORM|SHORT|THUMB|THUMBNAIL)", media.stem.upper()):
            continue
        story_id = resolve_story(ledger, "", 0.0, None, None, token, token)
        unresolved = (not story_id or story_id.startswith("window:"))
        if unresolved:
            story_id = f"archive:{token.lower()}"
        ledger.upsert_story(
            story_id, label=(token if unresolved else None),
            confidence="NEEDS_REVIEW" if unresolved else "CONFIRMED",
            publication_status="UNKNOWN" if unresolved else "NONE",
            notes=(f"archive export {media.name}; identity not recorded in the file"
                   if unresolved else None),
        )
        ledger.add_artifact(
            story_id, "short" if "SHORT" in media.stem.upper() else "longform", media,
            sha256=sha256(media), duration_s=probe_duration(media),
            technical_status="VALID",
            editorial_status=("SUPERSEDED" if re.search(r"(_V\d|_CAP|_TIGHT|_FINAL_V)",
                                                        media.stem.upper())
                              else "UNREVIEWED"),
            publication_status="UNKNOWN",
            evidence=str(media),
            note="top-level archive export (no STATUS.md)",
        )
        count += 1
    # Images are supplements, never a story of their own: the top level also
    # holds QC sheets and measurement dumps (AB_THUMBNAILS, AUDIT, HOTSPOTS…),
    # and the first version of this scan turned each of them into a "story".
    for image in sorted((ARCHIVE / "READY-TO-POST").glob("*.jpg")) + \
            sorted((ARCHIVE / "READY-TO-POST").glob("*.png")):
        token = image.stem.split("_")[0].strip("_")
        if len(token) < 4:
            continue
        story_id = resolve_story(ledger, "", 0.0, None, None, token, token)
        if not story_id or story_id.startswith("window:"):
            continue
        approved = "approved" in image.name.lower()
        ledger.add_artifact(
            story_id, "thumbnail", image, sha256=sha256(image),
            technical_status="VALID",
            editorial_status="APPROVED" if approved else "UNREVIEWED",
            publication_status="UNKNOWN", evidence=str(image),
            note=("filename records user approval" if approved
                  else "top-level archive image"),
        )
        count += 1
    return count


def from_operator_ledger(ledger: StoryLedger) -> int:
    """`boyd approve` / `boyd reject` write to the store's own `ledger` table.

    That table is the operator's record and survives a rebuild, so the story
    ledger derives its decisions from it rather than hoarding rows that the next
    `build` would delete.
    """
    count = 0
    rows = list(ledger.conn.execute(
        "SELECT case_key, decision, reason, safety_related, decided_at FROM ledger"
        " ORDER BY decided_at"))
    for row in rows:
        video_id, _, start = str(row["case_key"]).rpartition(":")
        case = ledger.conn.execute(
            "SELECT end_s, cause_number, defendant FROM cases WHERE case_key = ?",
            (row["case_key"],)).fetchone()
        story_id = ledger.resolve(
            video_id, float(start or 0),
            float(case["end_s"]) if case else None,
            case["cause_number"] if case else None,
            case["defendant"] if case else None)
        reason = row["reason"] or ""
        ledger.add_decision(
            story_id, f"OPERATOR_{str(row['decision']).upper()}",
            reason=reason, source=f"state/pipeline.db ledger ({row['decided_at']})",
            quote=f"{row['case_key']}: {reason}")
        if str(row["decision"]).lower() == "rejected":
            ledger.add_feedback(
                story_id, "package_verdict", reason or "rejected by the user",
                source="state/pipeline.db ledger", quote=reason, status="REJECTED")
            ledger.upsert_story(story_id, selection_eligible=False,
                                review_state="REJECTED",
                                ineligible_reason=reason or "rejected by the user")
        count += 1
    return count


def apply_curated(ledger: StoryLedger) -> int:
    """Editorial facts no scanner can infer. Each one quotes its source."""
    garcia = ledger.story_id("dAKO7myCd-g", 8340.0, "2023 CR 10327")
    ledger.upsert_story(
        garcia,
        label="Andrew Garcia — cadet-tasing sentencing (dAKO7myCd-g, 2024-03-07)",
        cause_number="2023 CR 10327",
        defendant_label="Andrew Garcia",
        confidence="CONFIRMED",
        selection_eligible=False,
        ineligible_reason=("the hearing already has a package (case 8340: long-form + "
                          "Short since 2026-09-06) and a rejected second Short (8929); it "
                          "needs the user's own Short edit, not another automatic render"),
        review_state="REJECTED",
        publication_status="NONE",
        notes=("One story, three scored rows on docket dAKO7myCd-g (8320, 8340, 8929). "
               "This is the failure the story ledger exists to prevent."),
    )
    ledger.add_decision(
        garcia, "SELECTION_FAILED",
        reason=("dAKO7myCd-g:8929 was selected and rendered as new material although the "
                "same hearing was already rendered as 8340"),
        source="user (this thread, 2026-09-16)",
        quote=("you just completed work on dAKO7myCd-g:8929 even though the user had "
               "ALREADY created a long-form and Short from this same underlying "
               "case/story previously"))
    ledger.add_decision(
        garcia, "PRODUCER_HOLD",
        reason=("the 8320 window ended mid-answer, before the final choice and sentence"),
        source="docs/producer_brain_v1/batch_2/garcia_officer_sentencing/REPORT.md",
        quote="HOLD - the selected 8320-8999 window is not a complete hearing")
    ledger.add_decision(
        garcia, "SHORT_REJECTED_BY_USER",
        reason="the Short cut for dAKO7myCd-g:8929 is not editorially accepted",
        source="user (this thread, 2026-09-16)",
        quote=("The Short generated for dAKO7myCd-g:8929 is NOT editorially accepted ... "
               "TECHNICAL_SHORT_STATUS = VALID / EDITORIAL_SHORT_STATUS = REJECTED / "
               "NEEDS_USER_REEDIT"))
    ledger.add_feedback(
        garcia, "short_editorial",
        "the current 8929 Short cut is rejected; it must not move toward publishing",
        source="user (this thread, 2026-09-16)", quote=SHORT_REJECTION_NOTE,
        status="REJECTED_AWAITING_USER_EDIT")
    ledger.add_feedback(
        garcia, "edit_review",
        "rejection means: build a compact source pack of the strongest moments, let the "
        "user assemble the Short, then diff AI vs user edits into the profile",
        source="user (this thread, 2026-09-16)",
        quote=("If user rejects the edit, DO NOT repeatedly regenerate random alternative "
               "edits. Produce a compact source pack of the strongest usable moments."),
        status="PENDING_SOURCE_PACK")
    ledger.add_feedback(
        garcia, "reference_positive",
        "youtube.com/shorts/qWyaPXZuuHw — the user calls it a good Short and wants it used as "
        "a taste reference; measure it, do not copy it",
        source="user (this thread, 2026-09-17)",
        quote=("The user specifically says this is a good Short and wants it used as a taste "
               "reference. Your job is NOT to blindly copy this Short."),
        status="LEARNED")
    ledger.add_feedback(
        garcia, "source_pack",
        "out/editpacks/2024-03-07_dAKO7myCd-g_8929_v2/ — 11 clips from the hearing with "
        "roles, for the user's own edit (no AI recut)",
        source="tools/story_ledger.py / build_source_pack.py",
        quote="strongest-moments source pack -> user makes preferred edit",
        status="PACK_DELIVERED")
    for path, kind, editorial, note in (
            (ROOT / "out/review/2024-03-07_dAKO7myCd-g_8929/short.mp4", "short",
             "NEEDS_USER_REEDIT",
             "technical status VALID (decodes, bundle validates); editorial status "
             "NEEDS_USER_REEDIT - the user rejected this cut on 2026-09-16"),
            (ROOT / "out/review/2024-03-07_dAKO7myCd-g_8929/longform.mp4", "longform",
             "UNREVIEWED",
             "technical status VALID; no editorial verdict on record for this cut")):
        if path.is_file():
            ledger.add_artifact(garcia, kind, path, sha256=sha256(path),
                                technical_status="VALID", editorial_status=editorial,
                                publication_status="NONE",
                                evidence="user review 2026-09-16", note=note)

    perry = ledger.story_id("oL6lV6gCyOc", 736.0, "2025CR005793")
    ledger.upsert_story(
        perry, label="Quannette Perry — pawned-bracelet plea (2026-04-30)",
        selection_eligible=False, review_state="APPROVED",
        publication_status="PUBLISHED",
        ineligible_reason="approved by the user and posted 2026-09-12")
    ledger.add_decision(perry, "APPROVED_AND_POSTED",
                        reason="the user posted this pair on 2026-09-12",
                        source="docs/SOL-CLOSEOUT-QUEUE.md",
                        quote="Perry is already public - Nathan posted it 2026-09-12")
    ledger.add_feedback(perry, "opening_hook",
                        "open on the exact contiguous source line, not a summary",
                        source="out/review/2026-04-30_oL6lV6gCyOc_736/manifest.json",
                        quote="This is the bracelet. I need you to pawn it.",
                        status="LEARNED")

    phone = ledger.story_id("IDGfe1rPUQo", 6130.0, "2026 CR00004664")
    ledger.upsert_story(
        phone, label="Jordan Rhodess — phone dispute (2026-09-08)",
        selection_eligible=False, review_state="UNREVIEWED",
        publication_status="UNKNOWN",
        ineligible_reason=("existing assets keep this story out of automatic selection to "
                           "avoid duplicates; no publication receipt was found, so editorial "
                           "review of the current cut and live release confirmation remain"))
    ledger.add_feedback(phone, "short_keeps_conversation",
                        "keep more of the exchange between the two speakers",
                        source="STATE.md 2026-09-13 entry",
                        quote="i dont like the way the shorts edited i need more convo between them")
    ledger.add_feedback(phone, "payoff_placement",
                        "stop adding the outcome at the end; it kills the reason to watch the long-form",
                        source="STATE.md 2026-09-13 entry",
                        quote=("stop adding the outcome at the end because then people wont "
                               "watch the long form"))

    harrison = ledger.story_id("CqAKrxLobT0", 6499.0, "2024 CR0787")
    ledger.upsert_story(
        harrison, label="Nashia Renee Harrison — probation revocation (2026-09-10)",
        selection_eligible=False, review_state="NEEDS_USER_REEDIT",
        ineligible_reason=("the allocution cut was rejected; the plea-colloquy Short has no "
                          "user verdict on record"))
    ledger.add_feedback(harrison, "short_story_choice",
                        "a cut with no turn is a lame clip; the plea colloquy, not the allocution",
                        source="STATE.md 2026-09-16 night entry",
                        quote='Nathan watched the first re-cut and said "kind of a lame clip."')

    ledger.add_decision(
        garcia, "NOT_THE_SAME_AS_JAVIER_GARCIA",
        reason="a different defendant with the same surname on a different docket",
        source="D:/Boyd Clips/BANGERS/READY-2026-09-11/READY_MANIFEST.json",
        quote="GARCIA_J - Javier Garcia, 2026 CR4388, source XCNZrVkpzNo, hearing 2026-08-31")

    # Publications recorded locally (docs/MEASURED-2026-08-29-outcomes.md pulled
    # the public counts with yt-dlp). These are the only stories the local record
    # proves are live on the channel.
    measured = "docs/MEASURED-2026-08-29-outcomes.md"
    ledger.add_decision(
        perry, "PUBLICATION_EVIDENCE", source=measured,
        reason="public view counts were pulled per video for the posted set",
        quote="Pulled with `yt-dlp -J` per video from `@TexasTrialTracker`")
    thompson = ledger.story_id("JgvW7oCQxuI", 6698.0, "2022 CR0273")
    ledger.upsert_story(thompson, selection_eligible=False, review_state="APPROVED",
                        publication_status="PUBLISHED",
                        ineligible_reason="posted 2026-08-17 (short 5,349 views, long-form 72)",
                        label="Louis Fletcher Thompson — adjudication hearing (2026-04-27)")
    ledger.add_decision(
        thompson, "PUBLISHED_2026-08-17", source=measured,
        reason="both surfaces are live on the channel",
        quote=("2026-08-17 | Judge Boyd checks his story | 5,349 | He says his family "
               "was murdered | 72"))
    for title, date in (("Teen Shot His Friend In The Face", "2026-08-11"),
                        ("Spider Monkey", "2026-08-27")):
        slug = "archive:" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        ledger.upsert_story(
            slug, label=f"published {date}: {title}", confidence="NEEDS_REVIEW",
            publication_status="PUBLISHED", selection_eligible=False,
            ineligible_reason=f"published {date}; the local record does not identify which "
                              "docket or case this belongs to",
            notes=f"publication recovered from {measured}; identity unresolved")
        ledger.add_decision(slug, "PUBLISHED_UNIDENTIFIED", source=measured,
                            reason="public counts exist but the source case is not in the ledger",
                            quote=f"{date} | {title}")
    return 8


def from_delivery(ledger: StoryLedger) -> int:
    """What was actually handed to the user for review (OneDrive)."""
    if not DELIVERY.is_dir():
        return 0
    count = 0
    for path in sorted(DELIVERY.iterdir()):
        if not path.is_file():
            continue
        token = next((name for name in ("HARRISON", "PHONE-DISPUTE", "SANCHEZ")
                      if name in path.name.upper()), None)
        if not token:
            continue
        story_id = resolve_story(ledger, "", 0.0, None, None, token, token)
        if not story_id or story_id.startswith("window:"):
            story_id = f"archive:{token.lower()}"
            ledger.upsert_story(story_id, label=token,
                                notes=f"delivery folder only: {path.name}",
                                publication_status="DELIVERED_FOR_REVIEW")
        kind = ("short_thumbnail" if "vertical" in path.name.lower()
                else "short" if "short" in path.name.lower()
                else "thumbnail" if "thumb" in path.name.lower() else "longform")
        ledger.add_artifact(
            story_id, kind, path, sha256=sha256(path),
            technical_status="VALID", editorial_status="UNREVIEWED",
            publication_status="DELIVERED_FOR_REVIEW", evidence=str(path),
            note="copied into OneDrive/Pictures/Boyd-Review for the user to watch",
        )
        count += 1
    return count


# --------------------------------------------------------------- the profile


def merge_orphans(ledger: StoryLedger) -> int:
    """Fold a story that exists only because a folder was named before the ledger
    could identify it — `archive:phone-dispute` beside the phone-dispute story —
    into the real story. Identity comes from the label slug, and only an
    `archive:` id (never a cause or a window) is ever absorbed."""
    merged = 0
    orphans = list(ledger.conn.execute(
        "SELECT story_id, label FROM stories WHERE story_id LIKE 'archive:%'"))
    for orphan in orphans:
        needle = re.sub(r"[^a-z0-9]", "", (orphan["label"] or "").lower())
        if len(needle) < 4:
            continue
        target = None
        for row in ledger.conn.execute(
                "SELECT story_id, label, defendant_label, notes FROM stories"
                " WHERE story_id NOT LIKE 'archive:%'"):
            hay = re.sub(r"[^a-z0-9]", "", " ".join(
                str(row[key] or "") for key in ("label", "defendant_label", "notes")
            ).lower())
            if needle in hay:
                target = row["story_id"]
                break
        if not target:
            continue
        with ledger.conn:
            ledger.conn.execute(
                "INSERT OR REPLACE INTO story_artifacts (story_id, kind, path, sha256,"
                " duration_s, technical_status, editorial_status, publication_status,"
                " created_at, evidence, note)"
                " SELECT ?, kind, path, sha256, duration_s, technical_status,"
                " editorial_status, publication_status, created_at, evidence, note"
                " FROM story_artifacts WHERE story_id = ?", (target, orphan["story_id"]))
            ledger.conn.execute(
                "INSERT OR REPLACE INTO story_sources (story_id, video_id, start_s, end_s,"
                " hearing_date, source_url, cause_number, evidence, confidence)"
                " SELECT ?, video_id, start_s, end_s, hearing_date, source_url,"
                " cause_number, evidence, confidence FROM story_sources"
                " WHERE story_id = ?", (target, orphan["story_id"]))
            for table in ("story_artifacts", "story_sources", "story_decisions",
                          "story_feedback"):
                ledger.conn.execute(f"DELETE FROM {table} WHERE story_id = ?",
                                    (orphan["story_id"],))
            ledger.conn.execute("DELETE FROM stories WHERE story_id = ?",
                                (orphan["story_id"],))
        merged += 1
    return merged


PROFILE_ROWS: list[tuple[str, str, str, str, str]] = [
    ("opening_hook",
     "Open on the exact contiguous source line, never a summary or a narrator label.",
     "Perry Short opens on 'This is the bracelet. I need you to pawn it.'",
     "out/review/2026-04-30_oL6lV6gCyOc_736/manifest.json", "HIGH"),
    ("opening_hook",
     "The first 1-2 seconds carry a concrete conflict, question or consequence; never a "
     "meta-preamble.",
     "Producer Brain rule; the allocution cut opening on 'Okay. / Good luck to you.' was rejected",
     "prompts/producer_brain_v1.md", "HIGH"),
    ("moment_order",
     "Keep source order and both speakers; one contiguous conversation beats jump-cut highlights.",
     "Nathan: 'i need more convo between them'", "STATE.md 2026-09-13 entry", "HIGH"),
    ("setup_context",
     "Enough setup to follow the conflict; context breaks only when comprehension needs them.",
     "Producer Brain long-form contract", "prompts/producer_brain_v1.md", "HIGH"),
    ("pacing",
     "Aim around 50 seconds (45-55); never pad a weaker excerpt to hit a number.",
     "Producer Brain Short rule", "prompts/producer_brain_v1.md", "HIGH"),
    ("payoff_placement",
     "Stop at the pressure point or cliffhanger when that sells the long-form; do not spend "
     "the ending on the sentence.",
     "Nathan: 'stop adding the outcome at the end'", "STATE.md 2026-09-13 entry", "HIGH"),
    ("ending",
     "End on a complete spoken beat - question, revelation or answer - never mid-word.",
     "Producer Brain Short rule", "prompts/producer_brain_v1.md", "HIGH"),
    ("captions_context",
     "Captions sit on the divider rail and stay clear of faces.",
     "SHORTS_EDITOR_V2 layout", "src/boydclips/layout.py", "MEDIUM"),
    ("cta_timing",
     "The CTA holds to the last frame and never overlaps a face.",
     "config/pipeline.yaml cta block", "config/pipeline.yaml", "MEDIUM"),
    ("edit_review",
     "A rejected Short stops automatic regeneration: hand over a compact source pack of the "
     "strongest moments, take the user's own edit, then diff the two.",
     "user instruction 2026-09-16", "user (this thread, 2026-09-16)", "HIGH"),
    ("edit_review",
     "Never learn editing preferences from a rejected cut as though its choices were good.",
     "user instruction 2026-09-16", "user (this thread, 2026-09-16)", "HIGH"),
    # 2026-09-17, from the measured comparison in
    # docs/SHORTS-EDITOR-FAILURE-8929.md and docs/reference/REFERENCE-SHORT-qWyaPXZuuHw.md.
    ("opening_hook",
     "The first spoken words are the confrontation itself, not the setup half of the same "
     "exchange.",
     "reference qWyaPXZuuHw opens on the judge's accusation; the rejected 8929 cut spent its "
     "first 7.5 s on a baby's age before the question arrived",
     "youtube.com/shorts/qWyaPXZuuHw + out/review/2024-03-07_dAKO7myCd-g_8929", "HIGH"),
    ("moment_order",
     "Chronological loyalty is not a virtue: the Short may open on a later moment and return "
     "to earlier ones when that is what makes the opening land.",
     "reference: hook (0-4.6 s) -> narration (4.6-11 s) -> hearing from its own order (11-114 s)",
     "youtube.com/shorts/qWyaPXZuuHw", "HIGH"),
    ("escalation",
     "Every beat must raise tension, reveal something, show a reaction or move to the payoff; "
     "a beat that does none of those has to justify itself.",
     "8929 escalation 7/15: one 1.8 s reply from the defendant in a 47 s cut",
     "out/review/2024-03-07_dAKO7myCd-g_8929/manifest.json", "HIGH"),
    ("payoff_placement",
     "The strongest line ends the piece; do not let the cut run on for 20 s past it, and keep "
     "the CTA off the best moment.",
     "8929: 20.9 s payoff beat with the CTA over its last 5 s", 
     "out/review/2024-03-07_dAKO7myCd-g_8929/manifest.json", "HIGH"),
    ("context",
     "Context is stakes, not procedure, and it can be one short line.",
     "reference narration = 24 words: who he is to her, what he did, what the judge concluded",
     "youtube.com/shorts/qWyaPXZuuHw", "HIGH"),
    ("continuity",
     "Continuity is an engagement device: the reference holds 122 s with zero cuts, so a cut "
     "must be motivated by removing dead air or filler, never by restlessness.",
     "reference: 0 hard cuts, 2 silences > 0.6 s in 121.8 s", 
     "youtube.com/shorts/qWyaPXZuuHw", "MEDIUM"),
    ("captions_context",
     "Captions must not carry the story the footage is not showing.",
     "8929 opens on three caption cards about the baby's age while nothing is on screen",
     "out/review/2024-03-07_dAKO7myCd-g_8929/short.mp4", "MEDIUM"),
]

POSITIVE_REFERENCES = [
    {
        "reference_id": "qWyaPXZuuHw",
        "url": "https://www.youtube.com/shorts/qWyaPXZuuHw",
        "source": "external reference supplied directly by the user (2026-09-17)",
        "user_verdict": "POSITIVE / GOOD SHORT",
        "inspected": ("fetched and measured on this machine: 121.79 s, 360x640/30, AV1; "
                      "zero hard cuts; fixed 50/50 stacked tiles; no burned-in captions; "
                      "~24-word narration at 4.6-11 s; one red arrow annotation; question card "
                      "held from ~114 s to the last frame; two silences > 0.6 s"),
        "lessons": [
            "the first words are the judge's accusation, verbatim — no preamble",
            "the narration states stakes in one sentence, never procedure",
            "the outcome is withheld until the end",
            "continuity is the engagement device — 122 s with no cuts",
            "graphics point, they do not substitute for footage",
            "it ends on meaning (her closing lines), not on a sentence read off a sheet",
        ],
        "does_not_transfer": [
            "the 2-minute runtime (our Shorts are 45-55 s)",
            "the narrator voice (no approved voice asset exists)",
            "the near-360p picture (grammar beats resolution; it is not a licence to lower "
            "our encode targets)",
        ],
        "analysis": "docs/reference/REFERENCE-SHORT-qWyaPXZuuHw.md",
        "confidence": "HIGH",
    },
]

REJECTED_AI_EDITS = [
    {
        "case_key": "dAKO7myCd-g:8929",
        "verdict": "REJECTED by the user (2026-09-16)",
        "technical_status": "VALID (decodes; the bundle validates)",
        "why": ("opened on the setup half of the money moment (7.5 s of a baby's age before "
                "the question), no escalation (7/15), a 20.9 s payoff tail with the CTA over "
                "it, and it dropped the credibility collapse that precedes the window"),
        "analysis": "docs/SHORTS-EDITOR-FAILURE-8929.md",
        "do_not_use_as_training": True,
        "next_step": ("source pack -> the user's own edit -> diff his edit against this one -> "
                      "only then change the editor"),
    },
]

LEARNING_PRIORITY = [
    "the user's own edited/reviewed Shorts",
    "the user's explicit positive or negative feedback",
    "references the user explicitly names as good",
    "performance data from published Shorts",
    "generic model taste",
]

PROFILE_DIMENSIONS = ("opening_hook", "moment_order", "cut_points", "setup_context",
                      "pacing", "pauses", "payoff_placement", "captions_context",
                      "ending", "cta_timing")


def write_profile(ledger: StoryLedger) -> Path:
    target = ROOT / "docs" / "SHORTS-EDITING-PROFILE.md"
    lines = [
        "# Shorts editing profile",
        "",
        "Learned Shorts editing preferences, each with the evidence it came from.",
        "Generated by `python tools/story_ledger.py profile`; the ledger is the source of",
        "truth, so add rows there rather than editing this file.",
        "",
        "| dimension | preference | evidence | source | confidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for dimension, preference, evidence, source, confidence in PROFILE_ROWS:
        lines.append(f"| {dimension} | {preference} | {evidence} | `{source}` | {confidence} |")
    lines += [
        "",
        "## Open - not yet learned",
        "",
        "`dAKO7myCd-g:8929`: the user rejected the current Short cut (2026-09-16) and has",
        "not yet handed back his own edit, so there is nothing to diff. The rejected cut is",
        "explicitly NOT a lesson. The next step is the compact source pack, then the user's",
        "edit, then the comparison over: " + ", ".join(PROFILE_DIMENSIONS) + ".",
        "",
        "Editorial rejections on record that did teach something: the Harrison allocution",
        "cut ('kind of a lame clip' - no turn), and the phone-dispute Short (more",
        "conversation, outcome removed).",
    ]
    lines += ["", "## Learning priority (highest first)", ""]
    lines += [f"{index}. {item}" for index, item in enumerate(LEARNING_PRIORITY, 1)]
    lines += ["", "A generic model opinion never overrides explicit user evidence.", ""]
    lines += ["## Positive references", ""]
    for ref in POSITIVE_REFERENCES:
        lines += [
            f"### {ref['reference_id']} — {ref['user_verdict']}",
            "",
            f"- reference id: `{ref['reference_id']}`",
            f"- source: {ref['source']}",
            f"- url: {ref['url']}",
            f"- user verdict: **{ref['user_verdict']}**",
            f"- confidence: **{ref['confidence']}**",
            f"- inspected: {ref['inspected']}",
            "",
            "Observed lessons (from inspection only):",
            "",
        ]
        lines += [f"- {lesson}" for lesson in ref["lessons"]]
        lines += ["", "Does not transfer:", ""]
        lines += [f"- {item}" for item in ref["does_not_transfer"]]
        lines += ["", f"Full measurement: `{ref['analysis']}`", ""]
    lines += ["## Rejected AI edits", "",
              "These are on record so they are never mistaken for approved work, and never",
              "used as positive training examples.", ""]
    for edit in REJECTED_AI_EDITS:
        lines += [
            f"### {edit['case_key']} — {edit['verdict']}",
            "",
            f"- technical status: {edit['technical_status']}",
            f"- editorial verdict: **{edit['verdict']}**",
            f"- why: {edit['why']}",
            f"- analysis: `{edit['analysis']}`",
            f"- next step: {edit['next_step']}",
            f"- usable as a positive example: **no**",
            "",
        ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for dimension, preference, evidence, source, confidence in PROFILE_ROWS:
        ledger.conn.execute(
            "INSERT OR REPLACE INTO short_edit_profile (dimension, preference, evidence,"
            " source, confidence, learned_at) VALUES (?,?,?,?,?,?)",
            (dimension, preference, evidence, source, confidence, now()))
    ledger.conn.commit()
    return target


def write_report(ledger: StoryLedger, target: Path) -> dict[str, int]:
    conn = ledger.conn
    totals = {
        "stories": conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0],
        "sources": conn.execute("SELECT COUNT(*) FROM story_sources").fetchone()[0],
        "artifacts": conn.execute("SELECT COUNT(*) FROM story_artifacts").fetchone()[0],
        "with_longform": conn.execute(
            "SELECT COUNT(DISTINCT story_id) FROM story_artifacts"
            " WHERE kind='longform'").fetchone()[0],
        "with_short": conn.execute(
            "SELECT COUNT(DISTINCT story_id) FROM story_artifacts"
            " WHERE kind='short'").fetchone()[0],
        "with_both": conn.execute(
            "SELECT COUNT(*) FROM (SELECT story_id FROM story_artifacts"
            " WHERE kind IN ('longform','short') GROUP BY story_id"
            " HAVING COUNT(DISTINCT kind) = 2)").fetchone()[0],
        "approved": conn.execute(
            "SELECT COUNT(DISTINCT story_id) FROM story_artifacts"
            " WHERE editorial_status='APPROVED'").fetchone()[0],
        "rejected": conn.execute(
            "SELECT COUNT(DISTINCT story_id) FROM story_artifacts"
            " WHERE editorial_status IN ('REJECTED','NEEDS_USER_REEDIT')").fetchone()[0],
        "published": conn.execute(
            "SELECT COUNT(*) FROM stories WHERE publication_status='PUBLISHED'").fetchone()[0],
        "blocked": conn.execute(
            "SELECT COUNT(*) FROM stories WHERE selection_eligible=0").fetchone()[0],
    }
    duplicates = conn.execute(
        "SELECT story_id, COUNT(*) n, GROUP_CONCAT(video_id || ':' || CAST(start_s AS INT))"
        " rows FROM story_sources GROUP BY story_id HAVING n > 1"
        " ORDER BY n DESC").fetchall()
    by_status = conn.execute(
        "SELECT editorial_status, COUNT(*) n FROM story_artifacts"
        " GROUP BY editorial_status ORDER BY n DESC").fetchall()
    by_review = conn.execute(
        "SELECT review_state, COUNT(*) n FROM stories GROUP BY review_state"
        " ORDER BY n DESC").fetchall()
    by_publication = conn.execute(
        "SELECT publication_status, COUNT(*) n FROM stories GROUP BY publication_status"
        " ORDER BY n DESC").fetchall()
    uncertain = conn.execute(
        "SELECT story_id, label, confidence, publication_status FROM stories"
        " WHERE confidence != 'CONFIRMED' ORDER BY story_id").fetchall()
    totals["approved_stories"] = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE review_state='APPROVED'").fetchone()[0]
    totals["uncertain"] = len(uncertain)

    lines = [
        "# Story ledger — reconciliation report",
        "",
        f"Generated {now()} by `python tools/story_ledger.py report`.",
        "",
        "Internal record. Defendant names come from public court records and are",
        "identifiers here only — they never appear in titles or thumbnail text.",
        "",
        "## Counts",
        "",
        f"- stories: **{totals['stories']}**",
        f"- hearings/sources mapped: **{totals['sources']}**",
        f"- artifacts recorded: **{totals['artifacts']}**",
        f"- stories with a long-form: **{totals['with_longform']}**",
        f"- stories with a Short: **{totals['with_short']}**",
        f"- stories with both: **{totals['with_both']}**",
        f"- stories with an APPROVED artifact: **{totals['approved']}**",
        f"- stories with a REJECTED / NEEDS_USER_REEDIT artifact: **{totals['rejected']}**",
        f"- stories recorded as PUBLISHED: **{totals['published']}**",
        f"- stories blocked from selection: **{totals['blocked']}**",
        "",
        "## Artifact editorial states",
        "",
        "| editorial status | artifacts |",
        "| --- | --- |",
    ]
    lines += [f"| {row['editorial_status']} | {row['n']} |" for row in by_status]
    lines += ["", "## Stories with more than one source (grouped hearings)", "",
              "| story | sources | windows |", "| --- | --- | --- |"]
    for row in duplicates:
        lines.append(f"| `{row['story_id']}` | {row['n']} | {row['rows']} |")
    lines += ["", "## Stories by review state", "", "| review state | stories |",
              "| --- | --- |"]
    lines += [f"| {row['review_state']} | {row['n']} |" for row in by_review]
    lines += ["", "## Stories by publication state", "", "| publication | stories |",
              "| --- | --- |"]
    lines += [f"| {row['publication_status']} | {row['n']} |" for row in by_publication]
    lines += ["", "## Uncertain — needs a human", "",
              "| story | label | why uncertain |", "| --- | --- | --- |"]
    for row in uncertain:
        lines.append(f"| `{row['story_id']}` | {row['label']} | confidence "
                     f"{row['confidence']} |")
    lines += [
        "",
        "## dAKO7myCd-g reconciled",
        "",
        "- One story: cause **2023 CR 10327**, docket `dAKO7myCd-g` (2024-03-07),",
        "  defendant Andrew Garcia — the cadet-tasing sentencing.",
        "- Three scored rows for it: `8320` (score 88, Producer verdict HOLD - window ended",
        "  mid-answer), `8340` (score 94, rendered 2026-09-06: long-form 1163.6 s + Short",
        "  52.8 s, never approved or published) and `8929` (score 91, rendered 2026-09-16:",
        "  long-form 561.5 s + Short 47.3 s).",
        "- Why selection missed it: the store keys work by case (`video:start`), the 8929 row",
        "  had `cause_number = unknown`, and the old guard could only match an exact case key",
        "  or an exact cause number. A re-scored row of the same hearing looked brand new.",
        "- Current status: long-form technical state VALID for both renders, no editorial",
        "  verdict recorded; the 8929 **Short is editorially REJECTED / NEEDS_USER_REEDIT**",
        "  (user, 2026-09-16). The story is blocked from selection until the user's own edit",
        "  exists; a revisit needs an explicit reason recorded through the ledger.",
        "- Prior work that also belongs to this story: a Producer Brain floor review",
        "  (`docs/producer_brain_v1/batch_2/garcia_officer_sentencing/`), thumbnail",
        "  art-direction briefs and direct-gen ORIGINALs under `D:/Boyd Clips/thumbwork/` and",
        "  `D:/Boyd Clips/ORIGINAL-ASSETS-2026-09-07/GARCIA/`.",
        "",
        "## Uncertain / needs review",
        "",
        "A story that exists only by surname resemblance is never merged automatically: see",
        "`StoryLedger.match`, which returns POSSIBLE_MATCH and blocks unattended selection",
        "until a human settles identity. The same-surname trap is live in this project:",
        "`GARCIA_J` (Javier Garcia, 2026 CR4388, source XCNZrVkpzNo) is a different story",
        "from Andrew Garcia on dAKO7myCd-g.",
        "",
        "## How to ask the question",
        "",
        "```",
        "python tools/story_ledger.py preflight dAKO7myCd-g:8929",
        "python tools/story_ledger.py stories --with-packages",
        "```",
        "",
        "The pipeline prints the same block before it touches a candidate, and unattended",
        "selection refuses a story that already has a package unless the ledger carries an",
        "explicit revisit reason.",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "report", "verify", "preflight",
                                            "profile", "stories"))
    parser.add_argument("target", nargs="?")
    parser.add_argument("--with-packages", action="store_true")
    args = parser.parse_args(argv)

    conn = connect()
    ledger = StoryLedger(conn)
    if args.command == "build":
        reset(conn)
        mapping = from_store(ledger)
        review_count = from_review(ledger, mapping)
        archive_count = from_archive(ledger)
        delivery_count = from_delivery(ledger)
        curated = apply_curated(ledger)
        merged = merge_orphans(ledger)
        operator = from_operator_ledger(ledger)
        conn.commit()
        stories = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
        sources = conn.execute("SELECT COUNT(*) FROM story_sources").fetchone()[0]
        artifacts = conn.execute("SELECT COUNT(*) FROM story_artifacts").fetchone()[0]
        print(f"story-ledger-build-ok stories={stories} sources={sources} "
              f"artifacts={artifacts}")
        print(f"  store: {len(mapping)} rendered cases | review bundles: {review_count} | "
              f"archive entries: {archive_count} | delivery files: {delivery_count} | "
              f"curated overrides: {curated} | folded folder-only stories: {merged}")
        print(f"  operator verdicts from the store ledger: {operator}")
        return 0
    if args.command == "profile":
        print(f"wrote {write_profile(ledger).relative_to(ROOT)}")
        return 0
    if args.command == "report":
        target = ROOT / "docs" / "STORY-LEDGER-RECONCILIATION.md"
        totals = write_report(ledger, target)
        print(f"wrote {target.relative_to(ROOT)}")
        print(json.dumps(totals, indent=2))
        return 0
    if args.command == "preflight":
        target = args.target or ""
        video_id, _, start = target.partition(":")
        start_s = float(start or 0)
        row = conn.execute(
            "SELECT end_s, cause_number, defendant FROM cases WHERE video_id = ?"
            " AND start_s = ?", (video_id, start_s)).fetchone()
        info = ledger.preflight(video_id, start_s,
                                float(row["end_s"]) if row else start_s,
                                row["cause_number"] if row else None,
                                row["defendant"] if row else None)
        print(f"preflight {target}")
        print(ledger.format_preflight(info))
        return 0 if info["selection_eligible"] else 1
    if args.command == "stories":
        rows = conn.execute(
            "SELECT s.story_id, s.label, s.review_state, s.publication_status,"
            " s.selection_eligible,"
            " (SELECT COUNT(*) FROM story_artifacts a WHERE a.story_id = s.story_id"
            "  AND a.kind='longform') longforms,"
            " (SELECT COUNT(*) FROM story_artifacts a WHERE a.story_id = s.story_id"
            "  AND a.kind='short') shorts FROM stories s ORDER BY s.story_id").fetchall()
        shown = 0
        for row in rows:
            if args.with_packages and not (row["longforms"] or row["shorts"]):
                continue
            shown += 1
            print(f"  {row['story_id']:<34} L{row['longforms']} S{row['shorts']} "
                  f"{row['review_state']:<16} {row['publication_status']:<21} "
                  f"{'eligible' if row['selection_eligible'] else 'blocked':<8} "
                  f"{str(row['label'])[:54]}")
        print(f"  {shown} of {len(rows)} stories shown")
        return 0
    if args.command == "verify":
        problems = []
        for row in conn.execute(
                "SELECT story_id, kind, path FROM story_artifacts"
                " WHERE technical_status IN ('VALID','GENERATED')"):
            if not Path(row["path"]).is_file():
                problems.append(f"{row['story_id']} {row['kind']} missing: {row['path']}")
        for problem in problems[:20]:
            print("  " + problem)
        print(f"story-ledger-verify: {len(problems)} claimed artifacts are not on disk")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
