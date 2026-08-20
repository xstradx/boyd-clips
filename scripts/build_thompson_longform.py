"""Rebuild the Thompson long-form to CONTENT_SPEC §2. Restart, not a patch.

The shipped longform.mp4 was a straight concat of the two sitting windows. It
carries **179.6s of silence in runs longer than 4 seconds across its 838s** —
21.4% of the video — including one 75s run and one 30s run, and it opens on
4.8s of nothing. CONTENT_SPEC §2 is explicit:

    [0:00]  COLD OPEN     - the case begins; no intro, no branding
            BODY          - the proceeding, uncut except for dead air > 4s
            RESOLUTION    - the judge's ruling or the case's natural end
    [end]   HARD CUT      - no outro

    "Dead air longer than 4 seconds is removed. Shorter gaps stay - courtroom
     pauses carry weight and cutting them makes proceedings feel falsified."

So the threshold is the spec's 4.0s, not a number I chose, and gaps under it are
left alone deliberately.

FRAMING: no crop. The court's 2-up content strip is 3.64:1, so cropping to it
and scaling to 1920 wide fills 527 of 1080 rows — the same share of the canvas
the full court frame already gives (348 of 720). Cropping buys nothing here and
would inherit `detect_content_crop`, which is threshold-per-pixel and was
measured wrong on this exact source: it kept 132 rows of black inside Judge
Boyd's tile because a flag runs down the edge. A document imposes nothing.

NOT DONE HERE, and deliberately: no chapters, no narration, no legal
exposition. `docs/reference/LONGFORM-ANTIPATTERNS.md` §5 items 12-13 want those and treat
a lightly-trimmed feed as a failure; CONTENT_SPEC §2 defines this product as the
proceeding itself. CONTENT_SPEC says of itself "This file is the format
contract", and the antipatterns file's own scope note calls it one specialist's
negative-space output — so the contract governs and the conflict is worth
raising rather than silently resolving.

    python scripts/build_thompson_longform.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                                    # noqa: E402
from boydclips.config import load_config                        # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI_6698_6674-8866.mp4"
REVIEW = ROOT / "out" / "review" / "2026-04-27_JgvW7oCQxuI_6698"
OFFSET = 6674.0
CAUSE = "2022 CR0273"
VIDEO_ID = "JgvW7oCQxuI"

# CONTENT_SPEC §2. Named rather than inlined so the source of the number is
# obvious at the call site.
DEAD_AIR_S = 4.0
# Left in place at each end of a removed run. A hard zero-length join between
# two rooms of silence reads as a glitch; a third of a second reads as an edit.
KEEP_S = 0.35
# The stutter guard, deliberately looser here than on a short. At 1.0s it
# refused a legitimate cut because the fragment between two dead runs was only
# 0.80s long — and the result was a 6.5s dead run surviving into an 11-minute
# document. Two cuts 0.8s apart are invisible at this length; 6.5s of nothing
# is not.
MIN_PIECE_S = 0.5


def windows() -> list[tuple[float, float]]:
    """Both sittings of the cause, chronologically, straight from the bank."""
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    out = []
    for row in db.execute("SELECT payload FROM cases WHERE video_id = ?",
                          (VIDEO_ID,)):
        p = json.loads(row["payload"])
        if p.get("cause_number") == CAUSE:
            out.append((float(p["start_s"]), float(p["end_s"])))
    return sorted(out)


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1

    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    lf_cfg = dict(cfg.require("output.longform"))

    wins = windows()
    if len(wins) < 2:
        print(f"expected both sittings of {CAUSE}, got {wins}", file=sys.stderr)
        return 1
    sittings = [render.Segment(a, b) for a, b in wins]
    raw = sum(s.duration for s in sittings)
    print(f"  {len(sittings)} sittings, {raw:.0f}s raw:")
    for s in sittings:
        print(f"    {s.start_s:.0f} -> {s.end_s:.0f}  ({s.duration:.0f}s)")

    silences = render.detect_silences(SOURCE, noise_db=-30.0,
                                      min_silence_s=DEAD_AIR_S)
    pieces = render.plan_silence_trim(
        sittings, silences, OFFSET,
        min_silence_s=DEAD_AIR_S, keep_s=KEEP_S, min_piece_s=MIN_PIECE_S,
        edge_keep_s=0.05,
    )
    kept = sum(p.duration for p in pieces)
    print(f"  dead air >{DEAD_AIR_S:.0f}s removed: {raw:.0f}s -> {kept:.0f}s "
          f"(-{raw - kept:.0f}s, {100 * (raw - kept) / raw:.1f}%) "
          f"across {len(pieces)} pieces")

    if kept < float(lf_cfg.get("min_duration_s", 120)):
        print(f"REFUSING: {kept:.0f}s under the {lf_cfg['min_duration_s']}s floor",
              file=sys.stderr)
        return 1
    # The cap is documented but was never enforced anywhere — see STATE.md.
    cap = float(lf_cfg.get("max_duration_s", 1200))
    if kept > cap:
        print(f"REFUSING: {kept:.0f}s over the {cap:.0f}s cap", file=sys.stderr)
        return 1
    starts = [p.start_s for p in pieces]
    if starts != sorted(starts):
        print("REFUSING: pieces out of chronological order", file=sys.stderr)
        return 1

    out = REVIEW / "longform_v2.mp4"
    dur = render.render_longform(SOURCE, OFFSET, pieces, lf_cfg, out, crop=None)
    print(f"  rendered {dur:.1f}s ({dur / 60:.1f} min) -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
