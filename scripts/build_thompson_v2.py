"""Re-cut the Thompson short: dead air removed, captions resized and replaced.

Same four beats and the same chronological order as build_thompson_formA.py —
the editorial decision is unchanged. What changes is everything measured to be
wrong with how it was rendered:

  1. 13.7% of the shipped 34.55s short was silence (10 spans >= 0.35s at
     -30dBFS). Now trimmed per beat, with 120ms of each pause left in place so
     the next word keeps its attack.
  2. Caption events overlapped, and libass stacks a collision rather than
     dropping it — the shipped short opens on FOUR lines of text. Fixed in
     build_ass by clamping every event against its successor.
  3. Captions rendered at 38px cap height against a 72px floor (BBC/EBU-TT-D
     gives 3.75% of height for vertical; W3C IMSC1.3's 32x15 cellResolution
     lands on the same number), and their ink ran to y=1751 on a canvas where
     Google's own Universal Video Ad Safe Zones PDF wants everything above
     y=1248. Both measured with scripts/caption_probe.py, not calculated.

Font changed from Arial Black to Anton for a measured reason: at the size that
clears the 72px floor (140), Arial Black overflows the safe band at ~9
characters per line and Anton at ~13. Same legibility, half again as much text.
Anton also lives in assets/fonts, so it stops depending on a system font.

Three caption treatments are rendered from one cut, because which one is right
is a taste call that should be made by looking:

    python scripts/build_thompson_v2.py
    python scripts/build_thompson_v2.py --only pop
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                                    # noqa: E402
from boydclips.config import load_config                        # noqa: E402
from boydclips.transcribe import Transcript                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI_6698_6674-8866.mp4"
TRANSCRIPT = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI.transcript.json"
REVIEW = ROOT / "out" / "review" / "2026-04-27_JgvW7oCQxuI_6698"
OFFSET = 6674.0

BEATS = [
    (6930.85, 6943.60, "HOOK: 'Wait, you're saying your ex-wife and your children were killed?'"),
    (6949.85, 6959.80, "SETUP: 'That should be easy to verify... we'll Google.'"),
    (8313.90, 8321.60, "TURN: 'Google search of all names didn't reveal any murders'"),
    (8560.25, 8564.40, "BUTTON: 'you're saying that these people are deceased, I don't believe it.'"),
]

# Measured against the safe band with scripts/caption_probe.py.
CAPTIONS = {
    "enabled": True,
    "font": "Anton",
    "font_size": 140,          # -> 72px cap height (0.514 x size, measured)
    "max_chars_per_line": 13,  # Anton overflows the 823px band at ~14
    "max_lines": 2,
    "margin_v": 700,           # ink bottom lands at y~1190, limit 1248
    "outline": 6,
    "shadow": 2,
    "uppercase": True,
    "primary_color": "&H00FFFFFF",
    "highlight_color": "&H0000D7FF",
}

# Court footage, not entertainment: a pause after "your children were killed?"
# is the drama, so only genuinely dead spans go. A working podcast editor's
# rule, quoted from r/podcasting 2025-12-21: "If it follows an interesting
# question where the guest has clearly taken pause... it adds effect. If it's
# an awkward pause... I'll trim that." No algorithm can tell those apart, so
# the threshold is set where only long dead air qualifies and the rest stays.
TRIM = dict(min_silence_s=0.50, keep_s=0.15, min_piece_s=0.40)

VARIANTS = {
    "plain": {},
    "pop": {"pop_scale": 112, "pop_ms": 70},
    "pop_color": {"pop_scale": 115, "pop_ms": 60},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(VARIANTS), default=None)
    a = ap.parse_args()

    if not SOURCE.is_file():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1

    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    sh_cfg = dict(cfg.require("output.short"))
    transcript = Transcript.from_json(TRANSCRIPT.read_text(encoding="utf-8"))

    beats = [render.Segment(x, y) for x, y, _ in BEATS]
    raw_total = sum(s.duration for s in beats)

    silences = render.detect_silences(SOURCE, noise_db=-30.0, min_silence_s=0.30)
    segments = render.plan_silence_trim(beats, silences, OFFSET, **TRIM)
    total = sum(s.duration for s in segments)
    print(f"  {len(beats)} beats {raw_total:.2f}s -> {len(segments)} pieces "
          f"{total:.2f}s  (-{raw_total - total:.2f}s dead air, "
          f"{100 * (raw_total - total) / raw_total:.1f}%)")

    if not 25.0 <= total <= 59.0:
        print(f"REFUSING: {total:.1f}s is outside the spec's 25-59s window",
              file=sys.stderr)
        return 1
    starts = [s.start_s for s in segments]
    if starts != sorted(starts):
        print("REFUSING: pieces are not in chronological order", file=sys.stderr)
        return 1

    crop = render.detect_content_crop(SOURCE)
    bg_crop = crop or render.detect_content_crop(SOURCE, min_agreement=0.25)
    mode, stack_margin = render.choose_vertical_layout(SOURCE, crop, sh_cfg)
    # The two Zoom halves are not the same shape, so one shared crop leaves a
    # black stripe between the stacked tiles and keeps Zoom's green
    # active-speaker border in frame. Measured per half instead.
    tile_crops = render.detect_tile_crops(SOURCE)
    print(f"  framing: crop={crop} mode={mode} "
          f"(stack margin {stack_margin} NOT used — safe zone governs captions)")
    print(f"  tiles:   {tile_crops if tile_crops else 'NOT DETECTED — falling back'}")

    words = render.map_words_to_timeline(transcript.words, segments)
    print(f"  {len(words)} caption words on a {total:.2f}s timeline")

    wanted = [a.only] if a.only else list(VARIANTS)
    for name in wanted:
        cap = dict(CAPTIONS)
        cap["animation"] = name
        cap.update(VARIANTS[name])
        # choose_vertical_layout's margin puts captions in the clear band under
        # the stacked tiles, which the safe-zone measurement says is exactly
        # where the platform UI sits. The published limit wins over the layout.
        ass_path = render.build_ass(
            words, 0.0, total, cap,
            cfg.get("packaging.short.end_card"),
            REVIEW / f"captions_v2_{name}.ass",
        )
        out = REVIEW / f"short_v2_{name}.mp4"
        dur = render.render_short(SOURCE, OFFSET, segments, sh_cfg, ass_path,
                                  out, crop=crop, bg_crop=bg_crop,
                                  tile_crops=tile_crops)
        print(f"  [{name}] rendered {dur:.2f}s -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
