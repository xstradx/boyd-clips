"""Rebuild any case's long-form to CONTENT_SPEC §2. Generalised from Thompson.

Every long-form rendered before 2026-08-17 was a straight concat of its case
windows with no dead-air removal at all. Measured on the rendered files:

    Thompson  838s   179.6s of silence in runs >4s  (21.4%)
    Rodriguez 661s   140.1s                          (21.2%)
    Blackburn 2036s   53.1s                          ( 2.6%)

CONTENT_SPEC §2 is explicit:

    "Dead air longer than 4 seconds is removed. Shorter gaps stay - courtroom
     pauses carry weight and cutting them makes proceedings feel falsified."

So 4.0s is the spec's number, not one chosen here, and every gap under it is
left alone on purpose.

Multi-sitting cases are handled: windows are grouped by cause number exactly as
Store.case_windows does, so a hearing that was recessed and recalled comes back
as one video in chronological order. Nothing is ever reordered.

FRAMING: no crop, deliberately. The court's 2-up content strip is ~3.6:1, so
cropping to it and scaling to 1920 wide fills about the same share of a 16:9
canvas as the untouched court frame already does. Cropping buys nothing and
would inherit detect_content_crop, which is threshold-per-pixel and measured
this footage wrong (it kept 132 rows of black inside Judge Boyd's tile because
a flag runs down the edge).

    python scripts/rebuild_longform.py JgvW7oCQxuI:6698
    python scripts/rebuild_longform.py --all
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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ["JgvW7oCQxuI:6698", "mvGmUbuS0sU:1358", "4zkUTUavW4I:116"]

# The channel sting, prepended to every long-form. sting.mp4 is the subtle
# one — 1.4s, a straight fade-up to the mark. sting_v2.mp4 (2.6s) builds the
# letters with the star travelling and is the flashy variant; sting_gavel.mp4
# reveals letter by letter. Compared frame by frame before choosing.
INTRO = Path(r"D:\Boyd Clips\boyd-brand\sting.mp4")

DEAD_AIR_S = 4.0     # CONTENT_SPEC §2
KEEP_S = 0.35        # left at each end of a removed run so joins read as edits
MIN_PIECE_S = 0.5    # stutter guard; loose enough not to veto a legitimate cut


def find_source(video_id: str) -> tuple[Path, float] | None:
    """The widest cached section for this video, and the time it starts at.

    NOTE: `rerender_short.py` has the same function with a real bug — it
    compares the candidate's SPAN against the incumbent's START (`best[1]`),
    which are different quantities. On this docket that made a 307s cached file
    beat a 2192s one, and the long-form rendered 4.2 minutes of a 13.7-minute
    hearing while reporting success. Fixed here by keeping the span explicitly;
    the copy in rerender_short.py still needs it.
    """
    work = ROOT / "work" / video_id
    best: tuple[Path, float, float] | None = None      # (path, start, span)
    for p in sorted(work.glob(f"{video_id}_*-*.mp4")):
        span_text = p.stem.rsplit("_", 1)[-1]
        try:
            start, end = (float(v) for v in span_text.split("-"))
        except ValueError:
            continue
        actual = render.probe_duration(p)
        if abs(actual - (end - start)) > 2.0:
            print(f"  skipping {p.name}: duration {actual:.0f}s != span "
                  f"{end - start:.0f}s")
            continue
        if best is None or (end - start) > best[2]:
            best = (p, start, end - start)
    return (best[0], best[1]) if best else None


def sittings(db: sqlite3.Connection, case_key: str) -> list[render.Segment]:
    """Every window of this case's cause, chronological.

    Cases whose cause never parsed fall back to their own single window —
    grouping every 'unknown' in a docket would merge strangers.
    """
    video_id = case_key.split(":")[0]
    row = db.execute("SELECT payload FROM cases WHERE case_key = ?",
                     (case_key,)).fetchone()
    if not row:
        return []
    me = json.loads(row["payload"])
    cause = me.get("cause_number")
    if not cause or cause == "unknown":
        return [render.Segment(float(me["start_s"]), float(me["end_s"]))]

    out = []
    for r in db.execute("SELECT payload FROM cases WHERE video_id = ?",
                        (video_id,)):
        p = json.loads(r["payload"])
        if p.get("cause_number") == cause:
            out.append(render.Segment(float(p["start_s"]), float(p["end_s"])))
    return sorted(out, key=lambda s: s.start_s)


def rebuild(case_key: str, cfg) -> bool:
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    video_id = case_key.split(":")[0]

    segs = sittings(db, case_key)
    if not segs:
        print(f"{case_key}: no such case")
        return False

    found = find_source(video_id)
    if not found:
        print(f"{case_key}: no usable cached source in work/{video_id}")
        return False
    source, offset = found

    drow = db.execute("SELECT docket_date FROM dockets WHERE video_id = ?",
                      (video_id,)).fetchone()
    stamp = (f"{drow['docket_date'] if drow else 'undated'}_{video_id}_"
             f"{int(round(float(case_key.split(':')[1])))}")
    review = ROOT / "out" / "review" / stamp
    if not review.is_dir():
        print(f"{case_key}: no review dir at {review}")
        return False

    lf_cfg = dict(cfg.require("output.longform"))
    raw = sum(s.duration for s in segs)
    print(f"{case_key}: {len(segs)} sitting(s), {raw:.0f}s raw, "
          f"source {source.name} @ {offset:.0f}")

    silences = render.detect_silences(source, noise_db=-30.0,
                                      min_silence_s=DEAD_AIR_S)
    pieces = render.plan_silence_trim(
        segs, silences, offset, min_silence_s=DEAD_AIR_S, keep_s=KEEP_S,
        min_piece_s=MIN_PIECE_S, edge_keep_s=0.05,
    )
    kept = sum(p.duration for p in pieces)
    print(f"  dead air >{DEAD_AIR_S:.0f}s removed: {raw:.0f}s -> {kept:.0f}s "
          f"(-{raw - kept:.0f}s, {100 * (raw - kept) / raw:.1f}%) "
          f"across {len(pieces)} pieces")

    floor = float(lf_cfg.get("min_duration_s", 120))
    cap = float(lf_cfg.get("max_duration_s", 1200))
    if kept < floor:
        print(f"  REFUSING: {kept:.0f}s under the {floor:.0f}s floor")
        return False
    if kept > cap:
        # Documented but enforced nowhere until now — see STATE.md.
        print(f"  REFUSING: {kept:.0f}s over the {cap:.0f}s cap")
        return False
    if [p.start_s for p in pieces] != sorted(p.start_s for p in pieces):
        print("  REFUSING: pieces out of chronological order")
        return False

    # Anchor the watermark inside the picture. The court's frame carries a
    # black band above the participant tiles, so the canvas-relative default
    # put the mark on black. Derived from the measured tile top rather than
    # hardcoded, so it follows a docket with different framing.
    wm_y = None
    tiles = render.detect_tile_crops(source)
    if tiles:
        src_w, src_h = render.probe_dimensions(source)
        tile_top = int(tiles[0].split(":")[3])
        scale = float(lf_cfg.get("resolution", [1920, 1080])[1]) / float(src_h)
        wm_y = int(round(tile_top * scale)) + 28
        print(f"  watermark y={wm_y} (picture starts at "
              f"{int(round(tile_top * scale))})")

    intro = INTRO if INTRO.is_file() else None
    if intro is None:
        print(f"  WARNING: intro missing, rendering without it: {INTRO}")

    out = review / "longform_v2.mp4"
    dur = render.render_longform(source, offset, pieces, lf_cfg, out,
                                 crop=None, intro=intro, watermark_y=wm_y)
    print(f"  rendered {dur:.1f}s ({dur / 60:.1f} min) -> {out.name}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    cases = DEFAULT_CASES if (a.all or not a.cases) else a.cases

    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    ok = sum(1 for c in cases if rebuild(c, cfg))
    print(f"\n{ok}/{len(cases)} rebuilt")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
