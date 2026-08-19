"""Generate N thumbnail variants per case, for side-by-side picking.

The point is to stop guessing. Five thumbnail defects in a row shipped because
one variant was rendered, eyeballed, and corrected one variable at a time. Four
at once turns it into a comparison, and a comparison produces a preference that
can be written down and reused.

Axes varied, all of them things previously chosen by assertion:

  * FRAME       - which second of the clip. `_sharpest_frame` picks by edge
                  energy over the whole 1280x720 canvas, and measured across
                  nine candidates that score spans 1.7% (34.3-35.4). It is
                  choosing noise. So sample the window instead and let a person
                  choose.
  * SUBJECT_W   - how wide the traced subject sits. Reference set runs 0.33-0.40.
  * SUBJECT_CX  - which side, and how far over. Reference set is 0.23 or 0.78,
                  never centred.
  * GRADE       - ungraded, standard, punchy.

    python scripts/thumb_variants.py <case_key> [--n 4]
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render, thumbnail                          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "thumbvariants"

# (subject_w, subject_cx, grade_name, frame_pick)
AXES = {
    "subject_w": [0.38, 0.52],
    "subject_cx": [0.74, 0.80],
    "grade": ["standard", "punchy"],
}
GRADES = {
    "none": None,
    "standard": {},
    "punchy": {"contrast": 1.20, "saturation": 1.30, "brightness": 1.06,
               "sharpen_percent": 140},
}


def case_row(case_key: str) -> dict:
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    r = db.execute("SELECT payload FROM cases WHERE case_key = ?",
                   (case_key,)).fetchone()
    if not r:
        raise SystemExit(f"no such case: {case_key}")
    return json.loads(r["payload"])


def find_source(video_id: str) -> tuple[Path, float]:
    """The cached section and the SOURCE time it begins at.

    Section files are named <video>_<case>_<start>-<end>.mp4. The offset matters:
    `hook_start_s` on the case is in source-stream time (e.g. 8814s into a
    3-hour docket) while the cached file starts at its own zero. Seeking to
    8814 in a 478-second file returns nothing, which is exactly how the first
    run produced four "could not extract any frame" failures.
    """
    hits = sorted((ROOT / "work" / video_id).glob(f"{video_id}_*-*.mp4"))
    if not hits:
        raise SystemExit(f"no cached source in work/{video_id}")
    best = max(hits, key=lambda p: p.stat().st_size)
    try:
        start = float(best.stem.rsplit("_", 1)[-1].split("-")[0])
    except (ValueError, IndexError):
        start = 0.0
    return best, start


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_key")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--quote", default=None, help="override white|yellow")
    a = ap.parse_args()

    case = case_row(a.case_key)
    video_id = a.case_key.split(":")[0]
    source, offset = find_source(video_id)

    pkg = {"thumbnail_quote": case.get("thumbnail_quote") or "",
           "thumbnail_quote_yellow": case.get("thumbnail_quote_yellow") or ""}
    if a.quote and "|" in a.quote:
        white, yellow = a.quote.split("|", 1)
    elif pkg["thumbnail_quote"]:
        from boydclips.pipeline import split_thumbnail_quote
        white, yellow = split_thumbnail_quote(pkg)
    else:
        raise SystemExit("no thumbnail_quote stored; pass --quote 'white|yellow'")

    dest = OUT / a.case_key.replace(":", "_")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    combos = list(itertools.product(
        AXES["subject_w"], AXES["subject_cx"], AXES["grade"]))[: a.n]

    hook = max(0.0, float(case.get("hook_start_s", 0)) - offset)
    print(f"source {source.name} @ offset {offset:.0f}s, hook at {hook:.1f}s in-file")
    manifest = []
    for i, (sw, cx, grade) in enumerate(combos, 1):
        out = dest / f"v{i}.jpg"
        # Vary the frame too: walk the search window so each variant sees a
        # different moment rather than four grades of one frame.
        cfg = {
            "subject_w": sw,
            "subject_cx": cx,
            "grade": grade != "none",
            "grade_params": GRADES[grade],
            "search_window_s": 8.0,
            "frame_samples": 5,
            "frame_offset_s": (i - 1) * 2.0,
        }
        try:
            thumbnail.build(source, hook + (i - 1) * 2.0, white, yellow, out, cfg)
            manifest.append({"file": out.name, "subject_w": sw,
                             "subject_cx": cx, "grade": grade})
            print(f"  v{i}: w={sw} cx={cx} grade={grade}")
        except Exception as exc:
            print(f"  v{i} FAILED: {exc}")

    (dest / "manifest.json").write_text(
        json.dumps({"case_key": a.case_key, "white": white, "yellow": yellow,
                    "variants": manifest}, indent=1), encoding="utf-8")
    print(f"\n{len(manifest)} variants -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
