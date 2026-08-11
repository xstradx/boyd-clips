"""Render hand-picked Boyd moments straight to vertical shorts.

This bypasses scoring on purpose: these five were chosen by reading the
transcripts, not by the rubric. It is a manual override for a same-day post,
not a replacement for `boyd run` — nothing here writes to the state DB or the
publish ledger, so none of it can be approved or uploaded by accident.

Usage:  python scripts/clip_moments.py [out_dir]
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                      # noqa: E402
from boydclips.config import load_config          # noqa: E402
from boydclips.render import Segment              # noqa: E402
from boydclips.transcribe import get_transcript   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("clip")

# (video_id, start_s, end_s, slug, the line it is built around)
MOMENTS = [
    ("XiWwYFPhPn0", 135 * 60 + 4, 136 * 60 + 2, "01_guns-are-not-toys",
     "You shot somebody in the face. Guns are not toys."),
    ("BLtJn8XTfzA", 25 * 60 + 34, 26 * 60 + 37, "02_you-could-have-killed-somebody",
     "You could have killed somebody. This is your third time."),
    ("jcf7y3da_W8", 23 * 60 + 3, 24 * 60 + 1, "03_legally-an-adult",
     "Legally you're an adult, but technically you're not."),
    ("QzcSk3BNYqI", 152 * 60 + 27, 153 * 60 + 52, "04_marijuana-cigarette",
     "Would you give your child a marijuana cigarette to smoke?"),
    ("0OXHpQjbb8Y", 80 * 60 + 16, 81 * 60 + 22, "05_batman-could-beat-anybody",
     "Do you think Batman could beat Captain Marvel?"),
]


def main() -> int:
    cfg = load_config()
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/moments")
    out_root.mkdir(parents=True, exist_ok=True)
    work = Path("work")

    sh_cfg = dict(cfg.get("output.short") or {})
    if not sh_cfg:
        raise SystemExit("output.short missing from config/pipeline.yaml")
    # These run long by design — the moment is the whole clip, and trimming to
    # the daily 59s cap would cut Boyd off mid-sentence.
    sh_cfg["max_duration_s"] = 90

    made = []
    for vid, start, end, slug, line in MOMENTS:
        log.info("\n=== %s  (%s %d:%02d-%d:%02d)", slug, vid,
                 start // 60, start % 60, end // 60, end % 60)
        try:
            source, offset = render.download_section(
                vid, float(start), float(end), work / vid / f"{slug}.mp4")
            crop = render.detect_content_crop(source)
            mode, margin = render.choose_vertical_layout(source, crop, sh_cfg)
            log.info("  framing: %s, caption margin %dpx", mode, margin)

            seg = [Segment(float(start), float(end))]

            ass = None
            cap = dict(sh_cfg.get("captions", {}))
            cap["margin_v"] = margin
            if cap.get("enabled", True):
                t = get_transcript(vid, work / vid)
                words = [type(w)(t=w.t - start, w=w.w)
                         for w in t.slice(float(start), float(end))]
                ass = render.build_ass(words, 0.0, float(end - start), cap,
                                       None, out_root / f"{slug}.ass")

            out = out_root / f"{slug}.mp4"
            dur = render.render_short(source, offset, seg, sh_cfg, ass, out, crop=crop)
            (out_root / f"{slug}.txt").write_text(
                f"{line}\n\nsource: https://youtu.be/{vid}?t={int(start)}\n"
                f"in {start//60}:{start%60:02d}  out {end//60}:{end%60:02d}  "
                f"({dur:.1f}s rendered)\n",
                encoding="utf-8")
            log.info("  -> %s  (%.1fs)", out.name, dur)
            made.append(out)
        except Exception as exc:
            log.error("  FAILED %s: %s", slug, exc)

    log.info("\n%d/%d rendered -> %s", len(made), len(MOMENTS), out_root)
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
