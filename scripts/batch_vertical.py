"""Render every downloaded hearing as a full-length VERTICAL cut.

Nathan: "give me the cropped short layout but full length in a folder on the
desktop".

Same 1080x1920 two-tile framing a short gets - defendant over judge, each tile
found by measuring the Zoom grid rather than guessing at it - but the whole
hearing instead of a 60-second slice. That is the file you scrub to find
moments, and it is what the studio editor plays.

No captions: the auto-transcript and the speaker attribution are both still
wrong, and burning them in would bake the error into the file.

Resumable. Anything already in the folder is skipped, so re-running after a
reboot costs nothing.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "VERTICAL-FULL"
PY = sys.executable


def duration_of(path: Path) -> float:
    """Playable duration in seconds, 0.0 if the file is unreadable."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip() or 0)
    except Exception:                                # noqa: BLE001
        return 0.0


def is_complete(path: Path, expect_s: float) -> bool:
    """A killed render leaves a file with no moov atom - it exists, it has size,
    and ffprobe reports 0.0s. Checking only existence treated that as done and
    would have shipped an unplayable file, so the duration has to match."""
    if not path.exists() or path.stat().st_size < 1_000_000:
        return False
    got = duration_of(path)
    return got > 0 and abs(got - expect_s) <= max(3.0, expect_s * 0.02)


def hearings() -> list:
    """Pair each downloaded section with the hearing it was actually downloaded for.

    Picking the LONGEST hearing per video was wrong: a stream holds several
    hearings, and the section on disk may belong to a different one. Measured on
    -4WiCeWxBu0 the section covered source 8876-9527s while the longest listed
    hearing sat at 2885-3760s - a 6000s miss. Rendering that would not have
    errored, it would have produced the wrong defendant.

    The section filename carries the hearing start: {vid}_h_{t}_{a}-{b}.mp4.
    Match on that, and skip anything that cannot be matched rather than guess.
    """
    rows = json.loads((ROOT / "state" / "final_shortlist.json").read_text(encoding="utf-8"))
    out, seen = [], set()
    for f in sorted(glob.glob(str(ROOT / "work" / "*" / "*_h_*.mp4"))):
        name = Path(f).name
        vid = Path(f).parent.name
        m = re.search(r"_h_(\d+)", name)
        if not m:
            print(f"  skipping {name}: no hearing time in the filename")
            continue
        t = float(m.group(1))
        cand = [r for r in rows if r["video_id"] == vid and abs(float(r["t"]) - t) < 30]
        if not cand:
            print(f"  skipping {name}: no shortlist row near t={t:.0f}")
            continue
        r = max(cand, key=lambda r: r.get("span_s", 0))
        key = (vid, int(t))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    out.sort(key=lambda r: r.get("date", ""))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="one video id")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    rows = [r for r in hearings() if not args.only or r["video_id"] == args.only]
    print(f"{len(rows)} hearings -> {DEST}\n")

    done, failed = [], []
    for n, r in enumerate(rows, 1):
        vid, date = r["video_id"], r.get("date", "undated")
        out = DEST / f"VERTICAL_{date}_{vid[:6]}.mp4"
        mins = r["span_s"] / 60
        print(f"[{n}/{len(rows)}] {date}  {vid}  {mins:.1f} min")
        if is_complete(out, r["span_s"]):
            print(f"    already done ({out.stat().st_size/1e6:.0f} MB, "
                  f"{duration_of(out)/60:.1f} min)")
            done.append(out.name)
            continue
        if out.exists():
            print(f"    partial from an interrupted run "
                  f"({out.stat().st_size/1e6:.0f} MB, {duration_of(out):.1f}s) - redoing")
            out.unlink(missing_ok=True)
            out.with_suffix(".map.json").unlink(missing_ok=True)
        t0 = time.time()
        p = subprocess.run(
            # tools/short_chain.py, never scripts/make_short.py (2026-09-02):
            # the raw render has none of the engine's gates
            [PY, str(ROOT / "tools" / "short_chain.py"), "--video", vid,
             "--seg", f"{r['t']:.1f}:{r['t'] + r['span_s']:.1f}",
             "--out", str(out)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=7200)
        if is_complete(out, r["span_s"]):
            print(f"    -> {out.name}  {out.stat().st_size/1e6:.0f} MB "
                  f"in {time.time()-t0:.0f}s")
            done.append(out.name)
        elif out.exists():
            print(f"    INCOMPLETE ({duration_of(out):.1f}s of {r['span_s']:.0f}s) - removed")
            out.unlink(missing_ok=True)
            failed.append(vid)
        else:
            tail = (p.stdout or p.stderr or "").strip().splitlines()[-3:]
            print("    FAILED: " + " | ".join(t[:90] for t in tail))
            failed.append(vid)

    print(f"\nfinished: {len(done)}/{len(rows)}")
    for d in done:
        print("   ", d)
    if failed:
        print("failed:", ", ".join(failed))


if __name__ == "__main__":
    main()
