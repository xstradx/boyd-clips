"""Re-cut every scene so it never spans a courtroom mute.

WHY THIS EXISTS. Judge Boyd cuts the feed and mutes the audio for bench
conferences and anything that cannot be broadcast — the picture collapses to a
single static camera on an empty witness box. That is deliberate, not a
corrupt download. The first long-form EDL picked windows by transcript content
alone, so five of twelve scenes cut straight through a sealed sidebar and
shipped up to 90 seconds of digital silence into the middle of the film.

THE RULE: a scene may never contain a muted stretch. Content selection happens
INSIDE a live window, never across one.

Method, per scene:
  1. silencedetect the SOURCE at -50 dB / 6 s to get its muted stretches
  2. invert those into live windows
  3. keep the live window that overlaps the EDL's requested range the most
  4. clamp the requested in/out into that window
  5. if the survivor is shorter than MIN_S, also take the next-best live window
     and hard-cut them together (Audit uses hard cuts exclusively, so joining
     two live passages is house style, not a compromise)

Usage:  python scripts/fix_mutes.py [--apply]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LONG = ROOT / "out/review/castillo_long"
SRC = ROOT / "out/source"
EDL = LONG / "EDL.md"

SIL_DB = -50
SIL_MIN = 6.0          # a real sidebar, not a pause between questions
MIN_S = 45.0           # below this a scene is not worth keeping alone
PAD = 1.0              # stay clear of the mute boundary


def sh(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return (p.stderr or "") + (p.stdout or "")


def duration(p: Path) -> float:
    out = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(p)]).strip().splitlines()
    for line in out:
        try:
            return float(line)
        except ValueError:
            continue
    return 0.0


def muted(p: Path) -> list[tuple[float, float]]:
    txt = sh(["ffmpeg", "-v", "info", "-i", str(p),
              "-af", f"silencedetect=n={SIL_DB}dB:d={SIL_MIN}", "-f", "null", "-"])
    starts = [float(m) for m in re.findall(r"silence_start: ([0-9.]+)", txt)]
    ends = [float(m) for m in re.findall(r"silence_end: ([0-9.]+)", txt)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duration(p)
        out.append((s, e))
    return out


def live_windows(p: Path) -> list[tuple[float, float]]:
    d = duration(p)
    wins, cur = [], 0.0
    for s, e in muted(p):
        if s - cur > 1.0:
            wins.append((cur + (PAD if cur > 0 else 0), s - PAD))
        cur = e
    if d - cur > 1.0:
        wins.append((cur + PAD, d))
    return [(a, b) for a, b in wins if b - a >= 5.0]


def parse_edl() -> list[dict]:
    rows = []
    for line in EDL.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([0-9.]+)s\s*\|\s*`([^`]+)`"
                     r"\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([^|]*)\|", line)
        if m:
            rows.append({"n": int(m.group(1)), "act": m.group(2), "src": m.group(4),
                         "in": float(m.group(5)), "out": float(m.group(6)),
                         "note": m.group(7).strip()})
    return rows


def overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def plan(row: dict) -> list[tuple[float, float]]:
    src = SRC / row["src"]
    if not src.exists():
        return []
    wins = live_windows(src)
    want = (row["in"], row["out"])
    ranked = sorted(wins, key=lambda w: overlap(w, want), reverse=True)
    if not ranked:
        return []
    best = ranked[0]
    seg = (max(want[0], best[0]), min(want[1], best[1]))
    if seg[1] - seg[0] < 5:
        seg = best
    out = [seg]
    # The cold open is deliberately short — one question, cut before the answer.
    # Padding it to clear MIN_S would staple unrelated footage onto the hook.
    if row['n'] != 1 and seg[1] - seg[0] < MIN_S:
        for w in ranked[1:]:
            if w[1] - w[0] >= 20:
                extra = (w[0], min(w[1], w[0] + max(MIN_S, row["out"] - row["in"])))
                out.append(extra)
                break
    return out


def main() -> int:
    apply = "--apply" in sys.argv
    rows = parse_edl()
    print(f"{'#':>2}  {'src':38s} {'requested':>16s} -> {'live cut(s)':<28s} {'dur':>7s}")
    total = 0.0
    manifest = []
    for r in rows:
        segs = plan(r)
        if not segs:
            print(f"{r['n']:>2}  {r['src'][:38]:38s}  NO SOURCE / NO LIVE WINDOW")
            continue
        dur = sum(b - a for a, b in segs)
        total += dur
        desc = " + ".join(f"{a:.1f}-{b:.1f}" for a, b in segs)
        print(f"{r['n']:>2}  {r['src'][:38]:38s} {r['in']:7.1f}-{r['out']:<7.1f} -> {desc:<28s} {dur:6.1f}s")
        manifest.append({"n": r["n"], "src": r["src"], "segs": segs,
                         "act": r["act"], "note": r["note"]})

        if apply:
            parts = []
            for i, (a, b) in enumerate(segs):
                pth = LONG / f"_p{r['n']:02d}_{i}.mp4"
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(SRC / r["src"]),
                     "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p",
                     "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                     "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                     str(pth)], check=True)
                parts.append(pth)
            dst = LONG / f"scene_{r['n']:02d}.mp4"
            if len(parts) == 1:
                parts[0].replace(dst)
            else:
                lst = LONG / f"_j{r['n']:02d}.txt"
                lst.write_text("\n".join(f"file '{p.name}'" for p in parts), encoding="utf-8")
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-f", "concat", "-safe", "0", "-i", str(lst),
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                     "-af", "aresample=async=1:first_pts=0", str(dst)], check=True)
                for p in parts:
                    p.unlink(missing_ok=True)
                lst.unlink(missing_ok=True)

    print(f"\n{len(manifest)} scenes, {total/60:.1f} min of live-only footage")
    (LONG / "live_cuts.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    if not apply:
        print("dry run — re-run with --apply to cut")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
