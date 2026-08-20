"""Tell the pipeline about the transcripts that are already on disk.

The archive was pulled by a separate grab script that never registered anything
with the database, so `work/` holds 352 transcripts while `dockets` knows about
51. Everything downstream selects from those 51 - roughly a seventh of the
material actually available - which quietly made every count in the project
wrong rather than merely incomplete.

This registers the gap. Titles, durations and dates come from one flat-playlist
listing of the channel (`discover.list_recent`), not 300 separate metadata
requests. A docket whose transcript exists is marked `transcribed`, which is the
state the pipeline expects before analysis, so `boyd run` picks them up
naturally rather than needing a special path.

Idempotent: re-running adds nothing and re-stamps nothing.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import discover              # noqa: E402
from boydclips.config import load_config    # noqa: E402
from boydclips.state import Store           # noqa: E402


def transcripts_on_disk() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in glob.glob(str(ROOT / "work" / "*" / "*.transcript.json")):
        vid = os.path.basename(os.path.dirname(p))
        out[vid] = Path(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=2500,
                    help="how far back to list the channel")
    ap.add_argument("--apply", action="store_true",
                    help="write to the database (default is a dry run)")
    args = ap.parse_args()

    cfg = load_config()
    store = Store(ROOT / "state" / "pipeline.db")

    disk = transcripts_on_disk()
    known = {r["video_id"] for r in store.conn.execute("SELECT video_id FROM dockets")}
    missing = sorted(set(disk) - known)

    print(f"transcripts on disk      : {len(disk)}")
    print(f"dockets known to the db  : {len(known)}")
    print(f"on disk but NOT in the db: {len(missing)}")
    if not missing:
        print("\nnothing to do - the database already knows every transcript.")
        return

    channel = cfg.require("source.channel_url")
    print(f"\nlisting {channel} (depth {args.depth})...", flush=True)
    listing = discover.list_recent(channel, args.depth)
    meta = {d.video_id: d for d in listing}
    print(f"channel listing returned : {len(listing)} streams")

    have_meta = [v for v in missing if v in meta]
    no_meta = [v for v in missing if v not in meta]
    print(f"  of the missing, matched : {len(have_meta)}")
    print(f"  no metadata found       : {len(no_meta)}")

    dated = [v for v in have_meta if meta[v].docket_date]
    print(f"  with a parseable date   : {len(dated)}")
    if dated:
        ds = sorted(meta[v].docket_date for v in dated)
        print(f"  date range to be added  : {ds[0]} -> {ds[-1]}")

    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to commit.")
        for v in have_meta[:8]:
            d = meta[v]
            print(f"    {v}  {d.docket_date}  {int(d.duration_s):6d}s  {d.title[:58]}")
        return

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = 0
    for v in have_meta:
        d = meta[v]
        if not d.docket_date:
            continue
        store.add_docket(v, d.title, d.docket_date, d.duration_s)
        store.mark_docket(v, "transcribed", None, transcribed_at=stamp)
        added += 1

    total = store.conn.execute("SELECT count(*) c FROM dockets").fetchone()["c"]
    pend = len(store.pending_dockets())
    print(f"\nregistered {added} dockets")
    print(f"dockets in the db now : {total}")
    print(f"pending analysis      : {pend}")
    if no_meta:
        print(f"\n{len(no_meta)} transcripts had no channel metadata and were skipped:")
        for v in no_meta[:10]:
            print(f"    {v}")


if __name__ == "__main__":
    main()
