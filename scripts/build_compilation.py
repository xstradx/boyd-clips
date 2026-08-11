"""Cut the hand-picked Boyd moments into one long-form compilation.

Each moment gets ~2 minutes: the setup that makes it land, the moment itself,
and enough of the ruling to resolve it. Five of those clears the 8-minute
mid-roll threshold without padding, which a single exchange never can.

Horizontal 16:9 — this is the long-form. The vertical shorts from
clip_moments.py are the promo for it.

Usage:  python scripts/build_compilation.py [out_dir]
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                      # noqa: E402
from boydclips.config import load_config          # noqa: E402
from boydclips.render import Segment              # noqa: E402
from boydclips.transcribe import get_transcript   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("compile")

# (video_id, start_s, end_s, slug, chapter title)
PARTS = [
    ("XiWwYFPhPn0", 134 * 60 + 38, 136 * 60 + 48, "guns",
     "\"You shot somebody in the face\" - 18-year-old, no record"),
    ("BLtJn8XTfzA", 24 * 60 + 38, 26 * 60 + 50, "dwi",
     "\"You could have killed somebody\" - third DWI"),
    ("jcf7y3da_W8", 22 * 60 + 8, 24 * 60 + 20, "adult",
     "\"Legally you're an adult, technically you're not\""),
    ("QzcSk3BNYqI", 151 * 60 + 38, 154 * 60 + 10, "marijuana",
     "\"Would you give your child a marijuana cigarette?\""),
    ("0OXHpQjbb8Y", 80 * 60 + 8, 82 * 60 + 20, "batman",
     "\"Batman could beat anybody\" - Judge Boyd on comics"),
]


def main() -> int:
    cfg = load_config()
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/compilation")
    out_root.mkdir(parents=True, exist_ok=True)
    parts_dir = out_root / "parts"
    parts_dir.mkdir(exist_ok=True)
    work = Path("work")

    lf_cfg = dict(cfg.get("output.longform") or {})
    if not lf_cfg:
        raise SystemExit("output.longform missing from config/pipeline.yaml")

    rendered, chapters, elapsed = [], [], 0.0
    for vid, start, end, slug, title in PARTS:
        log.info("\n=== %s  %s %d:%02d-%d:%02d", slug, vid,
                 start // 60, start % 60, end // 60, end % 60)
        try:
            source, offset = render.download_section(
                vid, float(start), float(end), work / vid / f"comp_{slug}.mp4")
            crop = render.detect_content_crop(source)
            out = parts_dir / f"{slug}.mp4"
            dur = render.render_longform(
                source, offset, [Segment(float(start), float(end))],
                lf_cfg, out, crop=crop)
            chapters.append((elapsed, title, vid, start))
            elapsed += dur
            rendered.append(out)
            log.info("  -> %s (%.1fs, running %.1f min)", out.name, dur, elapsed / 60)
        except Exception as exc:
            log.error("  FAILED %s: %s", slug, exc)

    if len(rendered) < 2:
        log.error("not enough parts to concatenate")
        return 1

    listing = parts_dir / "concat.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in rendered),
        encoding="utf-8")

    final = out_root / "compilation.mp4"
    # Re-encode rather than stream-copy: the parts come from different source
    # streams and concat demuxer needs identical parameters to copy safely.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c:v", "libx264", "-preset", "medium",
         "-crf", str(lf_cfg.get("crf", 20)), "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", lf_cfg.get("audio_bitrate", "160k"),
         str(final)],
        check=True, timeout=3600)

    lines = ["00:00 Intro" if False else ""]
    lines = []
    for t, title, vid, src_s in chapters:
        lines.append(f"{int(t//60):02d}:{int(t%60):02d}  {title}\n"
                     f"        source: https://youtu.be/{vid}?t={int(src_s)}")
    (out_root / "chapters.txt").write_text(
        "\n".join(lines) + f"\n\ntotal: {elapsed/60:.1f} min\n", encoding="utf-8")

    log.info("\n%s  (%.1f min, %d parts)", final, elapsed / 60, len(rendered))
    log.info("chapters -> %s", out_root / "chapters.txt")
    if elapsed < 8 * 60:
        log.warning("UNDER 8 MINUTES (%.1f) — no mid-roll ads at this length",
                    elapsed / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
