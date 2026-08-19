"""Render one defendant's arc: every hearing of theirs, in order, as one video.

spec/SPEC.md §1 and §4. Chapters run chronologically, dead air over 4s is cut
inside each chapter, the branded sting goes on the front, and the whole thing
is held inside the measured 25-58 minute band.

THE BUDGET PROBLEM. Castillo's arc is 665 minutes of footage against a 58
minute ceiling, so an arc is not "concatenate everything" - it is a selection.
Chapters are dropped whole, worst score first, until the total fits. Dropping a
whole hearing keeps every surviving chapter intact and in sequence; trimming
each one proportionally would leave nine fragments that each stop mid-answer,
which is the failure CONTENT_SPEC has always guarded against.

The last chapter is protected. It carries the outcome, and an arc that stops
before the ruling is the one edit with real defamation exposure
(SAFETY_RULES R4).

    python scripts/build_arc.py "Anthony Blackburn"
    python scripts/build_arc.py --list
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import arcs, render                               # noqa: E402
from boydclips.config import load_config                         # noqa: E402
from boydclips.transcribe import hhmmss                          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "arcs"


def cached_section(video_id: str, start_s: float) -> tuple[Path, float] | None:
    """The downloaded file covering this moment, and the source time it starts."""
    best = None
    for p in (ROOT / "work" / video_id).glob(f"{video_id}_*-*.mp4"):
        try:
            a, b = p.stem.rsplit("_", 1)[-1].split("-")
            a, b = float(a), float(b)
        except ValueError:
            continue
        if a <= start_s < b and (best is None or (b - a) > best[2] - best[1]):
            best = (p, a, b)
    return (best[0], best[1]) if best else None


def fit_budget(chapters: list[dict], cap_s: float) -> tuple[list[dict], list[dict]]:
    """Drop whole chapters, worst first, until the arc fits. Keep the last."""
    keep = list(chapters)
    dropped: list[dict] = []
    while sum(c["end_s"] - c["start_s"] for c in keep) > cap_s and len(keep) > 1:
        candidates = keep[:-1] or keep          # never the finale
        worst = min(candidates, key=lambda c: c["score"])
        keep.remove(worst)
        dropped.append(worst)
    return keep, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("defendant", nargs="?", help="name, or part of one")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = load_config()
    lf = dict(cfg.require("output.longform"))
    cap = float(lf.get("max_duration_s", 3480))
    floor = float(lf.get("min_duration_s", 120))

    all_arcs = arcs.build_arcs(ROOT / "state" / "pipeline.db")

    if a.list or not a.defendant:
        print(f"{'ch':>2} {'dk':>2} {'raw':>6} {'cached':>6}  defendant")
        for arc in all_arcs[:25]:
            have = sum(1 for c in arc["chapters"]
                       if cached_section(c["video_id"], c["start_s"]))
            print(f'{arc["n_chapters"]:2} {arc["n_dockets"]:2} '
                  f'{arc["runtime_s"] / 60:5.0f}m {have:3}/{arc["n_chapters"]:<2}  '
                  f'{arc["defendant"]}')
        return 0

    q = a.defendant.lower()
    arc = next((x for x in all_arcs if q in x["defendant"].lower()), None)
    if arc is None:
        print(f"no arc matching {a.defendant!r}")
        return 1

    print(f'{arc["defendant"]} — {arc["n_chapters"]} chapters across '
          f'{arc["n_dockets"]} docket(s), {arc["runtime_s"] / 60:.0f} min raw')

    keep, dropped = fit_budget(arc["chapters"], cap)
    if dropped:
        print(f"  budget: dropped {len(dropped)} chapter(s) to fit {cap / 60:.0f} min")
        for d in dropped:
            print(f"    - {d['docket_date']} {d['case_key']} (score {d['score']:.1f})")

    plan = []
    for ch in keep:
        found = cached_section(ch["video_id"], ch["start_s"])
        if not found:
            print(f"  MISSING source for {ch['case_key']} — "
                  f"run: python scripts/prefetch_sources.py")
            continue
        plan.append((ch, found[0], found[1]))

    if not plan:
        print("  nothing renderable yet")
        return 1

    print(f"\n  {len(plan)}/{len(keep)} chapters have a cached source:")
    for ch, src, off in plan:
        print(f"    {ch['docket_date']}  {hhmmss(ch['start_s'])}  "
              f"{(ch['end_s'] - ch['start_s']) / 60:4.1f}m  {ch['proceeding_type']}")
    if a.dry_run:
        return 0

    dest = OUT / arc["name_key"].replace(" ", "_")
    dest.mkdir(parents=True, exist_ok=True)

    # Each chapter is rendered on its own because they come from different
    # source files; a single filter graph cannot span them.
    parts = []
    for i, (ch, src, off) in enumerate(plan, 1):
        seg = [render.Segment(ch["start_s"], ch["end_s"])]
        if lf.get("trim_dead_air", True):
            sil = render.detect_silences(
                src, noise_db=float(lf.get("silence_noise_db", -30.0)),
                min_silence_s=float(lf.get("dead_air_s", 4.0)))
            seg = render.plan_silence_trim(
                seg, sil, off,
                min_silence_s=float(lf.get("dead_air_s", 4.0)),
                keep_s=float(lf.get("silence_keep_s", 0.35)),
                min_piece_s=float(lf.get("silence_min_piece_s", 0.5)),
                edge_keep_s=0.05)
        part = dest / f"ch{i:02d}.mp4"
        dur = render.render_longform(src, off, seg, lf, part, crop=None)
        print(f"    ch{i:02d}: {dur / 60:.1f} min -> {part.name}")
        parts.append((part, dur, ch))

    total = sum(p[1] for p in parts)
    if total < floor:
        print(f"  REFUSING: {total:.0f}s is under the {floor:.0f}s floor")
        return 1

    # Concat, with the sting once on the very front rather than per chapter.
    listing = dest / "parts.txt"
    intro = render.resolve_intro(lf.get("intro_path")) if lf.get("intro_enabled", True) else None
    lines = []
    if intro:
        lines.append(f"file '{intro.resolve().as_posix()}'")
    lines += [f"file '{p.resolve().as_posix()}'" for p, _, _ in parts]
    listing.write_text("\n".join(lines), encoding="utf-8")

    out = dest / "longform.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(out)],
        check=True, timeout=1800)

    final = render.probe_duration(out)
    print(f"\n  ARC: {final / 60:.1f} min -> {out}")

    # YouTube chapter markers, offset by the sting.
    t = render.probe_duration(intro) if intro else 0.0
    marks = ["00:00 Intro"] if intro else []
    for _, dur, ch in parts:
        marks.append(f"{int(t // 60):02d}:{int(t % 60):02d} "
                     f"{ch['docket_date']} — {ch['proceeding_type'].replace('_', ' ')}")
        t += dur
    (dest / "CHAPTERS.txt").write_text("\n".join(marks), encoding="utf-8")
    (dest / "arc.json").write_text(json.dumps({
        "defendant": arc["defendant"], "chapters": [c["case_key"] for c in keep],
        "dropped": [c["case_key"] for c in dropped],
        "duration_s": final,
    }, indent=1), encoding="utf-8")
    print("  chapters:\n    " + "\n    ".join(marks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
