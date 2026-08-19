"""Re-render a case's short from its already-stored beats and cached source.

Exists because the framing, backdrop and caption fixes of 2026-08-16 changed
how a short is built but not what it contains. Re-running `boyd run --case`
would redo the packaging step — a Claude call — to arrive at titles that are
already correct for these cases, and would re-download a section already
sitting in work/. This reuses both and costs nothing.

It deliberately does NOT re-derive the beats. `short_segments` in the DB is the
editorial decision; re-deriving it would silently change the cut while claiming
to be a re-render.

    python scripts/rerender_short.py mvGmUbuS0sU:1358
    python scripts/rerender_short.py --all
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                                    # noqa: E402
from boydclips.config import load_config                        # noqa: E402
from boydclips.transcribe import Transcript                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ["mvGmUbuS0sU:1358", "4zkUTUavW4I:116"]


def find_source(video_id: str) -> tuple[Path, float] | None:
    """The cached section for this case, and the source time it starts at.

    Section files are named <video>_<case>_<start>-<end>.mp4, so the offset is
    read back off the filename and then checked against the file's real
    duration. A mismatch means the cache is not the section it claims to be —
    every beat would land in the wrong place, so bail rather than guess.
    """
    work = ROOT / "work" / video_id
    best: tuple[Path, float] | None = None
    for p in sorted(work.glob(f"{video_id}_*-*.mp4")):
        span = p.stem.rsplit("_", 1)[-1]
        try:
            start, end = (float(v) for v in span.split("-"))
        except ValueError:
            continue
        actual = render.probe_duration(p)
        if abs(actual - (end - start)) > 2.0:
            print(f"  skipping {p.name}: duration {actual:.0f}s != span "
                  f"{end - start:.0f}s")
            continue
        if best is None or (end - start) > best[1]:
            best = (p, start)
    return best


def rerender(case_key: str, cfg) -> bool:
    video_id, start_s = case_key.split(":")
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT payload FROM cases WHERE case_key = ?",
                     (case_key,)).fetchone()
    if not row:
        print(f"{case_key}: no such case")
        return False
    case = json.loads(row["payload"])

    beats = case.get("short_segments") or []
    if not beats:
        print(f"{case_key}: no stored beats — nothing to re-render")
        return False

    found = find_source(video_id)
    if not found:
        print(f"{case_key}: no usable cached source in work/{video_id} — "
              f"run `boyd run --case {case_key}` to fetch it")
        return False
    source, offset = found

    docket_date = None
    drow = db.execute("SELECT docket_date FROM dockets WHERE video_id = ?",
                      (video_id,)).fetchone()
    if drow:
        docket_date = drow["docket_date"]
    stamp = f"{docket_date or 'undated'}_{video_id}_{int(round(float(start_s)))}"
    review = ROOT / "out" / "review" / stamp
    if not review.is_dir():
        print(f"{case_key}: no review dir at {review}")
        return False

    sh_cfg = cfg.require("output.short")
    segments = [render.Segment(float(b["start_s"]), float(b["end_s"]))
                for b in beats]
    total = sum(s.duration for s in segments)
    print(f"{case_key}: {len(segments)} beat(s), {total:.1f}s, "
          f"source {source.name} @ offset {offset:.0f}")

    crop = render.detect_content_crop(source)
    bg_crop = crop or render.detect_content_crop(source, min_agreement=0.25)
    mode, caption_margin = render.choose_vertical_layout(source, crop, sh_cfg)
    print(f"  crop={crop} bg_crop={bg_crop} mode={mode} margin={caption_margin}")

    tpath = ROOT / "work" / video_id / f"{video_id}.transcript.json"
    ass_path = None
    cap_cfg = dict(sh_cfg.get("captions", {}))
    cap_cfg["margin_v"] = caption_margin
    if cap_cfg.get("enabled", True) and tpath.is_file():
        transcript = Transcript.from_json(tpath.read_text(encoding="utf-8"))
        words, elapsed = [], 0.0
        for seg in segments:
            for w in transcript.slice(seg.start_s, seg.end_s):
                words.append(type(w)(t=elapsed + (w.t - seg.start_s), w=w.w))
            elapsed += seg.duration
        ass_path = render.build_ass(
            words, 0.0, elapsed, cap_cfg,
            cfg.get("packaging.short.end_card"), review / "captions.ass",
        )

    out = review / "short.mp4"
    dur = render.render_short(source, offset, segments, sh_cfg, ass_path, out,
                              crop=crop, bg_crop=bg_crop)
    print(f"  rendered {dur:.1f}s -> {out}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    cases = DEFAULT_CASES if (a.all or not a.cases) else a.cases

    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    ok = 0
    for c in cases:
        if rerender(c, cfg):
            ok += 1
    print(f"\n{ok}/{len(cases)} re-rendered")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
