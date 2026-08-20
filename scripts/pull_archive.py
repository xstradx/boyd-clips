"""Pull captions for every docket on the channel that we do not have yet.

The channel lists 1,750 streams and we hold 352 transcripts, so the selection
stage has been choosing from a fifth of what exists. This is the grind that
closes that gap: no decisions, no model calls, just captions.

Captions only - no video. Transcripts average 468 KB, so the full archive is
about 0.8 GB rather than the terabyte the video would be.

Resumable by construction: anything already on disk is skipped, so killing this
and restarting loses nothing. Failures are recorded rather than retried
forever, because YouTube rate-limits and a stuck retry loop would look like
progress while making none. Re-run to sweep them up once the limiter relaxes.

Progress is written to state/archive_pull.json after every video, so the run can
be checked from another window without attaching to it.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import discover                      # noqa: E402
from boydclips.config import load_config            # noqa: E402
from boydclips.state import Store                   # noqa: E402
from boydclips.transcribe import fetch_captions     # noqa: E402

STATUS = ROOT / "state" / "archive_pull.json"
FAILED = ROOT / "state" / "archive_failed.json"


def on_disk() -> set[str]:
    return {os.path.basename(os.path.dirname(p))
            for p in glob.glob(str(ROOT / "work" / "*" / "*.transcript.json"))}


def write_status(**kw) -> None:
    kw["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(kw, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=2500)
    ap.add_argument("--limit", type=int, default=0, help="stop after N (0 = all)")
    ap.add_argument("--pace", type=float, default=1.5, help="seconds between videos")
    ap.add_argument("--resolve-dates", action="store_true",
                    help="ask YouTube for the upload date of streams whose title "
                         "has none (847 of 1,750 - see discover.fetch_upload_date)")
    args = ap.parse_args()

    cfg = load_config()
    store = Store(ROOT / "state" / "pipeline.db")
    channel = cfg.require("source.channel_url")

    print(f"listing {channel} ...", flush=True)
    listing = discover.list_recent(channel, args.depth)
    have = on_disk()
    todo = [d for d in listing if d.video_id not in have and d.docket_date]

    # Nearly half the channel has a title this parser cannot read - 344 titled
    # only "Judge Boyd's Zoom Meeting" but running two to six hours, and 503
    # ordinary dockets with a typo in the date. Skipping them loses real
    # material, so resolve the date from the video itself when asked.
    if args.resolve_dates:
        undated = [d for d in listing if d.video_id not in have and not d.docket_date]
        print(f"resolving upload dates for {len(undated)} undated streams...",
              flush=True)
        for n, d in enumerate(undated, 1):
            iso = discover.fetch_upload_date(d.video_id)
            if iso:
                d.docket_date = iso
                todo.append(d)
            if n % 25 == 0:
                print(f"  resolved {n}/{len(undated)}", flush=True)
            time.sleep(0.4)
        got = sum(1 for d in undated if d.docket_date)
        print(f"  recovered {got} of {len(undated)}", flush=True)

    if args.limit:
        todo = todo[: args.limit]

    print(f"channel streams : {len(listing)}")
    print(f"already on disk : {len(have)}")
    print(f"to pull         : {len(todo)}\n", flush=True)
    if not todo:
        print("nothing to do.")
        return

    failed: list[dict] = []
    ok = skipped = 0
    t0 = time.time()

    for i, d in enumerate(todo, 1):
        vid = d.video_id
        work = ROOT / "work" / vid
        work.mkdir(parents=True, exist_ok=True)
        try:
            tr = fetch_captions(vid, work)
            if tr is None:
                skipped += 1
                failed.append({"video_id": vid, "date": d.docket_date,
                               "reason": "no captions available"})
            else:
                (work / f"{vid}.transcript.json").write_text(tr.to_json(),
                                                             encoding="utf-8")
                if not store.seen_docket(vid):
                    store.add_docket(vid, d.title, d.docket_date, d.duration_s)
                store.mark_docket(
                    vid, "transcribed", None,
                    transcribed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                ok += 1
        except Exception as e:                      # noqa: BLE001
            skipped += 1
            failed.append({"video_id": vid, "date": d.docket_date,
                           "reason": str(e)[:200]})

        rate = i / max(1e-9, time.time() - t0)
        left = (len(todo) - i) / max(1e-9, rate)
        write_status(total=len(todo), done=i, ok=ok, failed=skipped,
                     eta_minutes=round(left / 60, 1),
                     last=vid, last_date=d.docket_date)
        if i % 10 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] ok={ok} failed={skipped} "
                  f"eta={left/60:.0f}m  ({d.docket_date})", flush=True)
        if failed:
            FAILED.write_text(json.dumps(failed, indent=1), encoding="utf-8")
        # Pace the requests. YouTube rate-limits an unpaced loop and starts
        # refusing, which costs far more time than the sleep does.
        time.sleep(args.pace + random.uniform(0, 0.7))

    mins = (time.time() - t0) / 60
    print(f"\ndone in {mins:.0f}m: {ok} pulled, {skipped} failed")
    print(f"transcripts on disk now: {len(on_disk())}")
    if failed:
        print(f"failures recorded in {FAILED} - re-run to sweep them up")


if __name__ == "__main__":
    main()
