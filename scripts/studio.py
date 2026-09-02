"""One command: hearing id -> an editor you can open.

The gap this closes: of thirteen rendered long-forms, exactly one had an editor,
because getting there meant running three scripts by hand and typing a --base
offset worked out from a map file. That offset is the dangerous part - it is the
number that converts player time to source time, and if it is wrong every cut is
silently off by a constant. Nothing should ever type it again.

So base is DERIVED, from the .map.json sidecar written at render time, and if it
cannot be derived this refuses to build a page rather than guessing. A page built
on a guessed offset looks correct and cuts the wrong footage.

    python scripts/studio.py --video 2XkPnvstmRQ

Skips any stage whose output already exists, so re-running is cheap.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"
PY = sys.executable


def run(args: list[str], why: str) -> bool:
    print(f"\n>> {why}")
    p = subprocess.run([PY] + args, cwd=str(ROOT))
    if p.returncode != 0:
        print(f"   FAILED: {' '.join(args[:3])}")
    return p.returncode == 0


def vertical_for(video: str) -> tuple[Path, float] | None:
    """The mp4 the editor plays, and the source second at its t=0.

    Only a file with a .map.json beside it counts. The sidecar is written by
    make_short.py and records exactly where each piece came from.
    """
    found = []
    for mp4 in sorted(OUTDIR.glob("*.mp4")):
        side = mp4.with_suffix(".map.json")
        if not side.exists():
            continue
        try:
            d = json.loads(side.read_text(encoding="utf-8"))
        except Exception:                            # noqa: BLE001
            continue
        if d.get("video") != video:
            continue
        pieces = d.get("pieces") or []
        # one continuous piece means player time maps to source by a constant
        if len(pieces) == 1 and abs(pieces[0]["short_start"]) < 0.01:
            span = float(pieces[0]["short_end"]) - float(pieces[0]["short_start"])
            found.append((span, mp4, float(pieces[0]["src_start"])))
    if not found:
        return None
    found.sort(key=lambda r: -r[0])          # the full hearing, not a 12s test clip
    return found[0][1], found[0][2]


def hearing_span(video: str) -> tuple[float, float] | None:
    for name in ("final_shortlist.json", "called_hearings.json"):
        f = ROOT / "state" / name
        if not f.exists():
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                            # noqa: BLE001
            continue
        best = None
        for r in rows:
            if r.get("video_id") != video:
                continue
            span = float(r.get("span_s") or 0)
            if best is None or span > best[1] - best[0]:
                best = (float(r["t"]), float(r["t"]) + span)
        if best:
            return best
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", type=float, default=None,
                    help="hearing start in source seconds (else read from state)")
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--force", action="store_true", help="redo stages already done")
    args = ap.parse_args()
    v = args.video

    span = (args.start, args.end) if args.start is not None and args.end is not None \
        else hearing_span(v)
    if not span:
        print(f"no hearing span known for {v}. Pass --start and --end in source seconds.")
        return
    start, end = span
    print(f"hearing {v}: {start:.0f}-{end:.0f}s  ({(end-start)/60:.1f} min)")

    # 1 - the vertical cut the editor plays, plus the offset it implies.
    #     This is the PLAYER file, not a short: the whole hearing, raw, so the
    #     editor's player-time -> source-time map stays linear. Shorts cut from
    #     it go through tools/short_chain.py (check_short_entry.py exempts only
    #     this VERTICAL_ render).
    vf = None if args.force else vertical_for(v)
    if not vf:
        out = OUTDIR / f"VERTICAL_{v}.mp4"
        if not run(["scripts/make_short.py", "--video", v,
                    "--seg", f"{start:.1f}:{end:.1f}", "--out", str(out)],
                   "rendering the vertical cut the editor plays"):
            return
        vf = vertical_for(v)
    if not vf:
        print("\nSTOP: no .map.json sidecar, so the base offset cannot be derived.")
        print("Refusing to build a page on a guessed offset - every cut would be off.")
        return
    vpath, base = vf
    print(f"\nplayer file: {vpath.name}   base offset {base:.1f}s (from its .map.json)")

    # 2 - moments
    if args.force or not (ROOT / "state" / f"moments_{v}.json").exists():
        if not run(["scripts/index_moments.py", "--video", v,
                    "--start", f"{start:.1f}", "--end", f"{end:.1f}"],
                   "indexing moments (Opus)"):
            return
    else:
        print("\n>> moments already indexed")

    # 3 - suggestions
    if args.force or not (ROOT / "state" / f"suggest_{v}.json").exists():
        if not run(["scripts/suggest_edit.py", "--video", v, "--base", f"{base:.1f}"],
                   "planning the cuts (Opus)"):
            return
    else:
        print(">> suggestions already made")

    # 4 - the page
    if not run(["scripts/build_studio.py", "--file", vpath.name, "--video", v,
                "--base", f"{base:.1f}",
                "--out", str(OUTDIR / f"SHORT_{v}.mp4")], "building the editor"):
        return

    print(f"\nready:  {OUTDIR / ('STUDIO_' + v + '.html')}")
    print("open it with Studio.bat (gives you the Render button), or double-click it.")


if __name__ == "__main__":
    main()
