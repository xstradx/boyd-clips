"""Caption a finished cut in THE THOMPSON STYLE (short_v3), which Nathan approved.

Every value here comes from config/pipeline.yaml, not from taste. The comments
in that file record what was measured and why:

  Anton 140       cap height is 0.514 x font_size; the old Arial Black at 74 put
                  38px of cap on screen, under the legibility threshold. Anton
                  at 140 clears it.
  13 chars/line   Anton overflows the safe band past this.
  3 words/card    mode of the winner set; median card 500-567ms.
  outline 6 + shadow 2
  hard cut        340+ of ~350 measured transitions in the winner set are a
                  single frame. No fade, no slide.
  pop_color       colour-only per-word emphasis. Scaling a word makes libass
                  re-lay out the line - measured 33px left and 65px wide drift
                  on EVERY word. Colour-only drifts 0/0/0.
  slot_margins    the text sits beside whoever is talking: defendant 1020,
                  judge 700, both px from the bottom of the 1920 canvas, inside
                  the safe band y 288..1248.

Word timings come from Whisper, and the speaker labels from caption_edit.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FONT = "Anton"
SIZE = 140
PRIMARY = "&H00FFFFFF"
HIGHLIGHT = "&H0000D7FF"
OUTLINE_C = "&H00000000"
OUTLINE = 6
SHADOW = 2
MAX_CHARS = 13
MAX_WORDS = 3
MAX_LINES = 2
# Both speakers are anchored to the SPLIT between the two tiles, and grow away
# from it - not to the top and bottom of the canvas.
#
# The anchor matters as much as the number. With everything bottom-anchored
# (\an2) a two-line card grows upward, so the judge's second line would climb
# back across the split into the defendant's tile. So the defendant is bottom-
# anchored (grows up, away from the split) and the judge is TOP-anchored
# (grows down, away from it). Each keeps a fixed edge against the divide
# whatever the card length.
SPLIT = 960                  # the two 960-tall tiles meet here
GAP = 14                     # wanted clearance between INK and the divide
#
# A MarginV positions the text BOX, and Anton's box carries internal leading, so
# the ink lands further from the divide than the margin implies. Measured by
# rendering the subtitles over black and taking the ink bounding box:
#   defendant \an2  margin edge 942 -> ink bottom 916   (26px of descender gap)
#   judge     \an8  margin edge 978 -> ink top   1020   (42px of ascender gap)
# Both constant regardless of line count, so they are simple offsets.
LEAD_BOTTOM = 26             # ink bottom sits this far above an \an2 edge
LEAD_TOP = 42                # ink top sits this far below an \an8 edge
SAFE_TOP, SAFE_BOTTOM = 288, 1248


def t(x: float) -> str:
    x = max(0.0, x)
    return f"{int(x//3600):d}:{int((x%3600)//60):02d}:{x%60:05.2f}"


def layout(tokens: list) -> list:
    """Group tokens into lines ONCE, from the plain text.

    The layout has to be decided before any colour tags exist. Wrapping the
    TAGGED text instead let the tag characters count toward the 13-char limit,
    so the line break moved as the highlight advanced and the card visibly
    re-flowed on every word - measured as SO/WITH THIS, then SO/WITH, then
    SO WITH/THIS across three consecutive events. That is the same drift the
    config records for pop_scale. Fixed layout; colour is the only change.
    """
    lines, cur = [], []
    for tok in tokens:
        cand = " ".join(cur + [tok])
        if cur and len(cand) > MAX_CHARS:
            lines.append(cur)
            cur = [tok]
        else:
            cur.append(tok)
    if cur:
        lines.append(cur)
    return lines[:MAX_LINES]


def build(segs: list, dest: Path) -> int:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{FONT},{SIZE},{PRIMARY},{PRIMARY},{OUTLINE_C},&H80000000,-1,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},2,60,60,700,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    out = []
    for sg in segs:
        words = sg.get("words") or []
        if not words:
            continue
        who = sg.get("who", "B")
        if who == "D":
            # ink bottom lands GAP above the split, grows upward
            an, margin = 2, 1920 - (SPLIT - GAP + LEAD_BOTTOM)
        else:
            # ink top lands GAP below the split, grows downward
            an, margin = 8, SPLIT + GAP - LEAD_TOP

        # split the line into cards of at most MAX_WORDS
        cards = [words[i:i + MAX_WORDS] for i in range(0, len(words), MAX_WORDS)]
        for card in cards:
            toks = [w["w"].strip().upper().replace("{", "").replace("}", "")
                    for w in card]
            rows = layout(toks)                  # decided once, before colour
            idx_rows, k = [], 0
            for row in rows:
                idx_rows.append(list(range(k, k + len(row))))
                k += len(row)

            # one event per word: the card stays on screen unchanged and only
            # the colour of the live word moves, so nothing re-flows
            for i, w in enumerate(card):
                a = w["a"]
                b = card[i + 1]["a"] if i + 1 < len(card) else w["b"]
                if b - a < 0.10:
                    b = a + 0.10
                painted = []
                for row_idx in idx_rows:
                    parts = [
                        (f"{{\\c{HIGHLIGHT}}}{toks[j]}{{\\c{PRIMARY}}}"
                         if j == i else toks[j])
                        for j in row_idx if j < len(toks)
                    ]
                    painted.append(" ".join(parts))
                out.append(f"Dialogue: 0,{t(a)},{t(b)},Main,,0,0,{margin},,"
                           + "{\\an%d}" % an + "\\N".join(painted))
    # No two events may overlap. The 0.10s minimum duration above can push an
    # event's end past the next event's start, and libass STACKS overlapping
    # lines of the same alignment - the later card gets shunted a full card
    # height out of its slot, which is what put the defendant 299px away from
    # the split instead of 14px. Clip each end to the next start.
    parsed = []
    for line in out:
        f = line.split(",", 9)
        parsed.append([f, f[1], f[2]])

    def secs(x: str) -> float:
        h, m, s = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    fixed, clipped = [], 0
    for i, (f, a, b) in enumerate(parsed):
        if i + 1 < len(parsed):
            nxt = secs(parsed[i + 1][1])
            if secs(b) > nxt:
                f[2] = t(nxt)
                clipped += 1
        if secs(f[2]) <= secs(f[1]):
            continue                      # nothing left of it; drop rather than overlap
        fixed.append(",".join(f))
    if clipped:
        print(f"  clipped {clipped} overlapping events so libass cannot stack them")

    dest.write_text(head + "\n".join(fixed) + "\n", encoding="utf-8")
    return len(fixed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True, help="json from caption_edit.py")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    segs = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    n = build(segs, Path(args.out))

    cap_px = 0.514 * SIZE
    print(f"{n} caption events -> {args.out}")
    print(f"  {FONT} {SIZE}  (cap height {cap_px:.0f}px, threshold ~40px)")
    print(f"  <= {MAX_WORDS} words per card, <= {MAX_CHARS} chars per line, uppercase")
    print(f"  defendant: bottom edge at y={SPLIT-GAP}, grows UP  (\\an2)")
    print(f"  judge:     top edge at y={SPLIT+GAP}, grows DOWN (\\an8)")
    print(f"  both hug the split at y={SPLIT}, {GAP}px clear")


if __name__ == "__main__":
    main()
