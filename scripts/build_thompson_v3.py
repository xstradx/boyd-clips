"""Thompson short v3 — full-bleed duo, captions anchored to the speaker.

Nathan, verbatim: "zoom in so theres no black on the top middle and bottom",
"judge boyd and the defendant would be more centered since youd be zooming in",
and "when judge boyd talks have the text near her and when the defendant talks
its near him".

What that needs, and what v2 could not do:

  * Each tile is cropped to the exact aspect of the half-canvas it fills
    (1080x960, so 1.125:1) and centred on its subject, rather than being
    letterboxed into the slot. The frame therefore has no black anywhere. The
    two Zoom halves are different shapes — left holds 628x348 of picture, right
    628x488, measured at four separate beats — so each gets its own window.
  * Captions carry a per-event MarginV, so the text sits in the top half beside
    the defendant while he is talking and in the bottom half beside Judge Boyd
    while she is. ASS supports this per Dialogue line; no second Style and no
    \\pos is needed, the alignment stays \\an2.

Speaker turns are written out by hand, for the same reason the beats are. The
transcript holds 125 '>>' turn markers but only ONE of them falls inside these
four beats — and it is not in the hook, which is where all the alternation is.
Audio diarisation would be the general answer; it is not installed and its
models are gated, so the honest thing for four beats is to read the transcript
and write down who says what. Timestamps below are the first word of each turn,
taken from the word-level transcript, not estimated.

    python scripts/build_thompson_v3.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                                    # noqa: E402
from boydclips.config import load_config                        # noqa: E402
from boydclips.transcribe import Transcript, Word               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI_6698_6674-8866.mp4"
TRANSCRIPT = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI.transcript.json"
REVIEW = ROOT / "out" / "review" / "2026-04-27_JgvW7oCQxuI_6698"
OFFSET = 6674.0

BEATS = [
    (6930.85, 6943.60, "HOOK"),
    (6949.85, 6959.80, "SETUP"),
    (8313.90, 8321.60, "TURN"),
    (8560.25, 8564.40, "BUTTON"),
]

BOYD, DEF = "boyd", "defendant"

# (source time of the turn's first word, who starts speaking).
TURNS = [
    (6930.88, BOYD),   # "Wait, you're saying your ex-wife and your children were killed?"
    (6933.28, DEF),    # "Yes, including my my my sister."
    (6935.84, BOYD),   # "While you were on probation?"
    (6937.24, DEF),    # "Yes."
    (6937.80, BOYD),   # "So, your ex-wife, your children, and your sister were killed?"
    (6940.80, DEF),    # "Including including my nieces."
    (6949.88, BOYD),   # "That should be easy to verify. If you will give the names to"
    (6954.40, DEF),    # "I do."
    (6954.80, BOYD),   # "counsel and we'll Google. Please. All right. So, just have a seat..."
    (8313.90, BOYD),   # the Google search result
    (8560.25, BOYD),   # "you're saying that these people are deceased, I don't believe it."
]

# Where each subject sits inside its own tile, as a fraction of that tile — so
# the numbers survive the tile being re-measured. Read off the extracted tiles
# at native size: defendant x~140 of 628, Judge Boyd x~395 of 628.
FOCUS = {
    "left": (140 / 628, 0.5),
    "right": (395 / 628, 0.5),
}
# Both tiles measure 628x348, so narrowing either to the slot's 1.125:1 already
# magnifies 1.61x horizontally and uses the full tile height. No extra zoom is
# wanted: cropping height as well would start throwing away picture that the
# 9:16 slot has room for.
ZOOM = {"left": 1.0, "right": 1.0}

# Two slots, measured against the safe band (text must sit inside y 288..1248).
# Defendant owns the top half of the canvas, Boyd the bottom half.
SLOTS = {DEF: 1020, BOYD: 700}

CAPTIONS = {
    "enabled": True,
    "font": "Anton",
    "font_size": 140,
    "max_chars_per_line": 13,
    "max_lines": 2,
    "margin_v": 700,
    "outline": 6,
    "shadow": 2,
    "uppercase": True,
    "primary_color": "&H00FFFFFF",
    "highlight_color": "&H0000D7FF",
    "animation": "pop_color",
    "pop_scale": 115,
    "pop_ms": 60,
    "slot_margins": SLOTS,
}

# Measured off 12 current high-view vertical shorts (yt-dlp + frame differencing
# at native fps, ~900 frames each). The headline finding is negative: caption
# state changes take exactly ONE frame in 340+ of ~350 measured transitions.
# No scale ramp, no fade, no slide, no sliding highlight box — a 33ms hard cut,
# every time, across nine unrelated channels at both high and low view counts.
#
# Per-word karaoke highlight appeared in 1 of 9 (Court TV) and is the weakest
# captioned performer in the set at 464k. An enlarged active word appeared only
# in the 40k control. So the treatment this project has been iterating on is
# the one the measurement says is NOT winning.
#
# Numbers below come from lawbyMike (4 videos, 12-19M views each, the leader in
# the legal niche): x-height 37-39px at 1080x1920, ascender 56-59px, outline
# 12-14px black plus a small hard shadow, 2-4 words per card (mode 3), card
# duration median 500-567ms, horizontally centred.
WINNER = {
    "font": "Montserrat",
    # Montserrat's cap/em ratio measured at 0.658 (Anton's is 0.514), so 64
    # yields ~42px of cap — inside the 37-41px band the winners sit in. Note
    # this is BELOW the 72px BBC/EBU-TT-D floor used earlier in this project:
    # the published accessibility minimum and observed practice disagree, and
    # this preset deliberately follows the measurement.
    "font_size": 64,
    "outline": 13,
    "shadow": 3,
    "max_words_per_card": 3,
    "max_lines": 1,
    "max_chars_per_line": 40,    # loose, so the word cap is what binds
    "animation": "plain",
    "card_fade_ms": 0,           # hard cut - the whole point
}

TRIM = dict(min_silence_s=0.50, keep_s=0.15, min_piece_s=0.40)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-slots", action="store_true",
                    help="one fixed caption position, for comparison")
    ap.add_argument("--name", default=None)
    ap.add_argument("--winner", action="store_true",
                    help="the measured mechanism from current high-view shorts")
    ap.add_argument("--anim", default=None,
                    choices=["plain", "highlight", "pop", "pop_color",
                             "card_punch"])
    a = ap.parse_args()

    if not SOURCE.is_file():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1

    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    sh_cfg = dict(cfg.require("output.short"))
    sh_cfg["vertical_mode"] = "duo_fill"
    w, h = sh_cfg.get("resolution", [1080, 1920])
    transcript = Transcript.from_json(TRANSCRIPT.read_text(encoding="utf-8"))

    beats = [render.Segment(x, y) for x, y, _ in BEATS]
    raw_total = sum(s.duration for s in beats)
    silences = render.detect_silences(SOURCE, noise_db=-30.0, min_silence_s=0.30)
    segments = render.plan_silence_trim(beats, silences, OFFSET, **TRIM)
    total = sum(s.duration for s in segments)
    print(f"  {len(beats)} beats {raw_total:.2f}s -> {len(segments)} pieces "
          f"{total:.2f}s")
    if not 25.0 <= total <= 59.0:
        print(f"REFUSING: {total:.1f}s outside the 25-59s window", file=sys.stderr)
        return 1
    if [s.start_s for s in segments] != sorted(s.start_s for s in segments):
        print("REFUSING: pieces out of chronological order", file=sys.stderr)
        return 1

    tiles = render.detect_tile_crops(SOURCE)
    if not tiles:
        print("REFUSING: could not measure the two tiles", file=sys.stderr)
        return 1
    slot_aspect = w / (h / 2)
    windows = (
        render.plan_fill_window(tiles[0], slot_aspect, FOCUS["left"], ZOOM["left"]),
        render.plan_fill_window(tiles[1], slot_aspect, FOCUS["right"], ZOOM["right"]),
    )
    print(f"  tiles   {tiles[0]} | {tiles[1]}")
    print(f"  windows {windows[0]} | {windows[1]}  (slot aspect {slot_aspect:.3f})")

    words = render.map_words_to_timeline(transcript.words, segments)

    # Turn markers ride through the same mapping as the words by borrowing the
    # Word type — same field names, same clamping, so a turn cannot drift out of
    # sync with the speech it labels.
    turns = None
    if not a.no_slots:
        mapped = render.map_words_to_timeline(
            [Word(t=t, w=who) for t, who in TURNS], segments)
        turns = [(0.0, mapped[0].w)] + [(x.t, x.w) for x in mapped[1:]]
        print(f"  {len(turns)} speaker turns: "
              + " ".join(f"{t:.1f}s:{who[:4]}" for t, who in turns))

    cap = dict(CAPTIONS)
    if a.winner:
        cap.update(WINNER)
    if a.anim:
        cap["animation"] = a.anim
    if a.no_slots:
        cap.pop("slot_margins", None)
    ass_path = render.build_ass(
        words, 0.0, total, cap, cfg.get("packaging.short.end_card"),
        REVIEW / f"captions_v3_{a.name or ('fixed' if a.no_slots else 'slots')}.ass",
        turns=turns,
    )
    out = REVIEW / f"short_v3_{a.name or ('fixed' if a.no_slots else 'slots')}.mp4"
    dur = render.render_short(SOURCE, OFFSET, segments, sh_cfg, ass_path, out,
                              tile_crops=windows)
    print(f"  rendered {dur:.2f}s -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
