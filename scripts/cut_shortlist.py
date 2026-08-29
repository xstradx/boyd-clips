"""Download, trim and assemble the shortlisted hearings.

Takes hearings the judge scored 5 and produces finished long-forms: the branded
sting, then the hearing from "the court is calling" to just before the next case
is called.

Built to Nathan's answers of 2026-08-21:
  * sting on the long-form, no burned captions
  * pauses STAY. Nothing is trimmed for silence here - his rule is "only cut if
    the screen goes black or she says shes gonna call them back in a couple min",
    and the four-second rule that used to strip them is gone
  * no watermark: the config names an asset that is not on disk, and inventing
    one is worse than leaving it off

Resumable - anything already rendered is skipped. Paths are handled Windows-side
throughout, because ffmpeg is a Windows binary and cannot open the POSIX paths
Git Bash produces; that fault cost two failed cuts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import render                    # noqa: E402

SHORTLIST = ROOT / "state" / "final_shortlist.json"
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"
STING = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "boyd-brand" / "sting.mp4"
STATUS = ROOT / "state" / "cut_status.json"


def run(cmd: list[str], cwd: Path | None = None) -> bool:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        print(f"    ffmpeg: {p.stderr.strip()[:200]}")
    return p.returncode == 0


def slug(r: dict) -> str:
    return f"HEARING_{r['date']}_{r['video_id'][:6]}.mp4"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--score", type=int, default=5)
    args = ap.parse_args()

    rows = [r for r in json.loads(SHORTLIST.read_text(encoding="utf-8"))
            if r["post"] >= args.score]
    # Longest first. Sorting shortest-first to deliver something quickly gave
    # Nathan the two thinnest hearings of fifteen - 8.7 and 9.1 minutes - and
    # his verdict was "really short and no drama really". Length is not drama,
    # but in this set the long ones are where the back-and-forth is.
    rows.sort(key=lambda r: -r["span_s"])
    picked, seen = [], set()
    for r in rows:
        if r["video_id"] in seen:                 # spread across dockets
            continue
        seen.add(r["video_id"])
        picked.append(r)
        if len(picked) >= args.count:
            break

    OUTDIR.mkdir(parents=True, exist_ok=True)
    work = ROOT / "work"
    print(f"cutting {len(picked)} hearings -> {OUTDIR}\n")

    done = []
    for n, r in enumerate(picked, 1):
        dest = OUTDIR / slug(r)
        print(f"[{n}/{len(picked)}] {r['date']}  {r['span_s']/60:.1f} min  {r['video_id']}")
        if dest.exists():
            print("    already rendered, skipping")
            done.append(str(dest))
            continue
        try:
            t0 = time.time()
            src = work / r["video_id"] / f"{r['video_id']}_h_{int(r['t'])}.mp4"
            src.parent.mkdir(parents=True, exist_ok=True)
            path, sec = render.download_section(r["video_id"], r["t"],
                                                r["t"] + r["span_s"], src)
            print(f"    downloaded {path.stat().st_size/1e6:.0f} MB in {time.time()-t0:.0f}s")
        except Exception as e:                    # noqa: BLE001
            print(f"    download failed: {str(e)[:160]}")
            continue

        off = max(0.0, r["t"] - sec)
        body, sting, lst = work / "_b.mp4", work / "_s.mp4", work / "_l.txt"
        ok = run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.1f}",
                  "-i", str(path), "-t", f"{r['span_s']:.1f}",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-r", "30", "-s", "1280x720",
                  "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                  str(body)])
        if not ok:
            continue
        ok = run(["ffmpeg", "-v", "error", "-y", "-i", str(STING),
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                  "-r", "30", "-s", "1280x720",
                  "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                  str(sting)])
        if not ok:
            continue
        lst.write_text("file '_s.mp4'\nfile '_b.mp4'\n", encoding="utf-8")
        ok = run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                  "-i", "_l.txt", "-c", "copy", str(dest)], cwd=work)
        for f in (body, sting, lst):
            f.unlink(missing_ok=True)
        if ok and dest.exists():
            print(f"    -> {dest.name}  {dest.stat().st_size/1e6:.0f} MB")
            done.append(str(dest))
        STATUS.write_text(json.dumps({"done": done, "of": len(picked)}, indent=1),
                          encoding="utf-8")

    print(f"\nfinished: {len(done)}/{len(picked)}")
    for d in done:
        print("   ", Path(d).name)


if __name__ == "__main__":
    main()
