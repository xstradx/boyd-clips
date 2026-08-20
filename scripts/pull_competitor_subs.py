"""Fetch captions for other channels' Boyd clips, so their edits become labels.

Nathan, 2026-08-20: do not limit this to the one channel - many people clip her
and some clip better. Measured, he is right. Courtroom Time publishes 60-minute
compilations; Court Trials TV Network publishes at a 1,024s median - four times
tighter - and reaches a million views. Juridocs is tighter still.

That matters because a clip is another editor stating "this is the part worth
watching". A 60-minute compilation barely says anything, since almost the whole
hearing is included. A 16-minute clip says a great deal more.

Captions only. Aligning them back onto our own dockets (scripts/align_clips.py)
turns each one into a labelled span in our corpus, which is what the selection
stage has never had.

Resumable: anything already fetched is skipped. Paced, because an unpaced loop
gets refused and that costs far more time than the sleep.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "state" / "scan"
REF = ROOT / "research" / "reference"
STATUS = ROOT / "state" / "competitor_subs.json"

CHANNELS = {
    "CourtTrialsTVNetwork": "court-trials-tv",
    "Juridocs": "juridocs",
    "AmericanJusticeFiles": "american-justice-files",
    "CourtOfJustice": "court-of-justice",
}


def fetch(vid: str, out_dir: Path) -> bool:
    """One clip's auto-captions in vtt. True if a file landed."""
    stem = out_dir / vid
    if list(out_dir.glob(f"{vid}.*.vtt")):
        return True
    proc = subprocess.run(
        ["yt-dlp", "--no-warnings", "--ignore-config", "--skip-download",
         "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
         "--sub-format", "vtt", "-o", str(stem),
         f"https://www.youtube.com/watch?v={vid}"],
        capture_output=True, text=True, timeout=180,
    )
    return bool(list(out_dir.glob(f"{vid}.*.vtt"))) and proc.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", default="CourtTrialsTVNetwork,Juridocs",
                    help="comma-separated keys from CHANNELS")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pace", type=float, default=2.0)
    args = ap.parse_args()

    keys = [k.strip() for k in args.channels.split(",") if k.strip()]
    todo: list[tuple[str, str, Path]] = []
    for key in keys:
        slug = CHANNELS.get(key)
        if not slug:
            print(f"unknown channel key: {key}")
            continue
        idfile = SCAN / f"{key}_boyd_ids.txt"
        if not idfile.exists():
            print(f"no id list for {key} - run the channel scan first")
            continue
        out_dir = REF / slug / "subs"
        out_dir.mkdir(parents=True, exist_ok=True)
        ids = [x.strip() for x in idfile.read_text(encoding="utf-8").splitlines() if x.strip()]
        have = {p.name.split(".")[0] for p in out_dir.glob("*.vtt")}
        want = [v for v in ids if v not in have]
        print(f"{key:24s} {len(ids):4d} clips, {len(have):4d} already fetched, "
              f"{len(want):4d} to go")
        todo += [(key, v, out_dir) for v in want]

    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print("\nnothing to fetch.")
        return
    print(f"\nfetching {len(todo)} caption files...\n", flush=True)

    ok = bad = 0
    t0 = time.time()
    for i, (key, vid, out_dir) in enumerate(todo, 1):
        try:
            if fetch(vid, out_dir):
                ok += 1
            else:
                bad += 1
        except Exception:                       # noqa: BLE001
            bad += 1
        rate = i / max(1e-9, time.time() - t0)
        left = (len(todo) - i) / max(1e-9, rate)
        STATUS.write_text(json.dumps({
            "total": len(todo), "done": i, "ok": ok, "failed": bad,
            "eta_minutes": round(left / 60, 1), "last": vid, "channel": key,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=1), encoding="utf-8")
        if i % 10 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] ok={ok} failed={bad} eta={left/60:.0f}m",
                  flush=True)
        time.sleep(args.pace + random.uniform(0, 0.8))

    print(f"\ndone in {(time.time()-t0)/60:.0f}m: {ok} fetched, {bad} failed")


if __name__ == "__main__":
    main()
