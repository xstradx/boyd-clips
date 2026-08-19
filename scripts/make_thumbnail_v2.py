"""Thumbnail built to the measured Audit the Court system, not to defaults.

Every number here comes from `research/reference/competitor/THUMBNAILS.md`,
which is a pixel read of all 12 of their thumbnails at 1280x720. The previous
builder (`make_thumbnail.py`) got five things wrong against that measurement,
and each one is a documented tell:

  * It painted a black scrim behind the text. Their top strip measures
    BRIGHTER than the bottom half in 12/12 (ratio 1.17-2.22). No scrim, no
    gradient, no colour block anywhere in the set — legibility comes from the
    stroke and glow alone.
  * It put the text at the bottom. Theirs sits in a top band, y 0.029-0.208 H,
    in 10/12.
  * It auto-sized type up to 132px. Their cap height is 0.0773 H (sigma
    0.0155) — about 56px at 720. The 971K thumbnail uses the SMALLEST cap in
    the set, 0.051 H.
  * It centred the subject. Theirs is at cx 0.23 W or 0.78 W, never centred,
    and the text moves to whichever side is empty.
  * It used one plate. 9/12 are a subject cut out over a second courtroom
    plate, feathered, with NO outline stroke on the cut-out — an outline is
    the loudest amateur tell in the client-vs-competitor diff.

Judge on the right in 7/12, which is what Nathan asked for independently.

    python scripts/make_thumbnail_v2.py --bg left.jpg --subject right.jpg \\
        --white "Your ex-wife and your children" --yellow "were killed?" \\
        --out thumbnail_quote.jpg
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"

W, H = 1280, 720

# --- measured constants, THUMBNAILS.md §5 -----------------------------------
YELLOW = (254, 251, 3)          # #FEFB03, mean of 12 sampled medians
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

CAP_FRAC = 0.0773               # cap height as a fraction of H -> ~56px
STROKE_RATIO = 1 / 6            # stroke : cap height, from median 9.5px @ 56px
GLOW_RADIUS = 20                # zero-offset black glow, NOT a drop shadow
# Text sits BELOW the top quarter. Corrected 2026-08-18 against @courtroomtime,
# who clip this same Boyd docket at 46K subs.
#
# 0.045 put our text line at cy ~0.084 — which is the LOSER signature in their
# set, not the winner one. Measured, winners vs losers: share of text rows above
# y=0.20 is 6.5% vs 25.8%, and 10th-percentile row centre is 0.236 vs 0.067.
# Ours measured 25.0% — indistinguishable from their losers.
#
# The old 0.029-0.208 band came from a 12-thumbnail read of a different channel
# (Audit the Court). @courtroomtime is a bigger, closer-matched sample on the
# identical subject, so it governs.
TEXT_TOP_FRAC = 0.30
TEXT_SIDE_FRAC = 0.036          # x start when the face is on the right
TEXT_MAX_FRAC = 0.86            # measured: their text band runs to x 0.87 W

SUBJECT_CX = 0.78               # hero face centre, 7/12
SUBJECT_W = 0.38                # panel width; Nathan's three refs run 0.33-0.40
FEATHER = 70                    # px of soft edge on the pasted plate

# Red arrow, present in 9/12. Points from empty space diagonally down INTO the
# secondary subject. Area 3016-4133px (mean 3578) ~ 0.4% of frame; their own
# 42K flop oversized it by 67%, so the size is a real constraint, not a taste.
ARROW_RED = (253, 1, 1)         # #FD0101, mean of 6 sampled medians
ARROW_W, ARROW_H = 123, 92


def _font(px: int) -> ImageFont.FreeTypeFont:
    """Montserrat Black — IoU 0.904 against their extracted glyphs, best of 11."""
    var = FONTS / "Montserrat-Var.ttf"
    if var.is_file():
        f = ImageFont.truetype(str(var), px)
        try:
            f.set_variation_by_axes([900])
            return f
        except Exception:
            pass
    static = ROOT / "research" / "blender" / "graphics" / "fonts_static" / "Montserrat-Bold.ttf"
    if static.is_file():
        return ImageFont.truetype(str(static), px)
    raise SystemExit(f"no Montserrat in {FONTS}")


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _wrap(words, font, max_w):
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = [[]]
    for word, colour in words:
        trial = " ".join(w for w, _ in lines[-1] + [(word, colour)])
        if lines[-1] and draw.textlength(trial, font=font) > max_w:
            lines.append([(word, colour)])
        else:
            lines[-1].append((word, colour))
    return [ln for ln in lines if ln]


def _arrow(canvas: Image.Image, cx: float, cy: float,
           angle_deg: float = 150.0) -> None:
    """Red arrow with its tip at (cx, cy), pointing along `angle_deg`.

    Built in local coordinates — tip at the origin, body running back along
    +x — then rotated. The previous version hand-placed seven points in frame
    space and produced a truncated blob: the tail corners did not line up with
    the shaft, so it read as a cut-off shape rather than an arrow.

    Default 150 degrees is down-left (screen y grows downward), which is the
    direction in 9/12 of the measured set: from empty space diagonally down
    into the secondary subject.
    """
    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)        # unit vector, tip direction
    px, py = -uy, ux                             # perpendicular

    head_len = ARROW_W * 0.46
    head_w = ARROW_H * 0.92
    shaft_w = ARROW_H * 0.38
    total = ARROW_W

    def at(back: float, side: float) -> tuple[float, float]:
        """A point `back` px behind the tip and `side` px off the axis."""
        return (cx * W - ux * back + px * side,
                cy * H - uy * back + py * side)

    pts = [
        at(0, 0),                                # tip
        at(head_len, head_w / 2),                # head corner
        at(head_len, shaft_w / 2),               # head -> shaft
        at(total, shaft_w / 2),                  # tail
        at(total, -shaft_w / 2),
        at(head_len, -shaft_w / 2),
        at(head_len, -head_w / 2),
    ]

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.polygon(pts, fill=ARROW_RED + (255,), outline=(0, 0, 0, 255), width=3)
    merged = Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")
    canvas.paste(merged, (0, 0))


def build(bg: Path, subject: Path, white_part: str, yellow_part: str,
          out: Path, arrow: tuple[float, float] | None = None,
          cutout: Path | None = None,
          subject_w: float = SUBJECT_W,
          subject_cx: float = SUBJECT_CX) -> Path:
    canvas = _cover(Image.open(bg).convert("RGB"), W, H)

    if cutout is not None:
        # A traced cut-out over the courtroom plate — the construction 9/12 of
        # theirs use. Masked with BiRefNet-portrait (MIT). NOT the rembg
        # default, which is BRIA RMBG-2.0 under CC BY-NC 4.0 and therefore
        # unusable on a monetised channel.
        #
        # No outline stroke on it, deliberately: 0/12 of theirs have one and it
        # is the loudest amateur tell in the client-vs-competitor diff.
        cut = Image.open(cutout).convert("RGBA")
        box = cut.getchannel("A").getbbox()
        if box:
            cut = cut.crop(box)

        # Scale to a WIDTH budget, not to the canvas height.
        #
        # This was `scale = H / cut.height`, which sized the cut-out to fill the
        # full 720 rows and then right-aligned it. Measured across four renders
        # the pasted widths came out 1479, 924, 1055 and 1051 px — 1.16 W, 0.72
        # W, 0.82 W, 0.82 W. At 1.16 W the courtroom plate behind it is 100%
        # hidden, so "a traced subject over a second courtroom plate" — the
        # construction 9/12 of the measured set uses and the entire reason this
        # builder exists — had never once actually shipped. Every thumbnail was
        # a single blown-up tile.
        #
        # SUBJECT_W (0.38) and SUBJECT_CX (0.78) were already declared for this
        # and were dead code: SUBJECT_W was read only in the `else` branch the
        # pipeline never takes, and SUBJECT_CX was referenced nowhere at all.
        target_w = W * subject_w
        scale = target_w / cut.width
        # Don't let a wide crop become a giant: cap at the canvas height.
        if cut.height * scale > H:
            scale = H / cut.height
        cut = cut.resize((max(1, round(cut.width * scale)),
                          max(1, round(cut.height * scale))), Image.LANCZOS)

        # Bottom-anchored and centred on SUBJECT_CX. People are cut off by the
        # frame edge at the bottom in 12/12 of the reference set; floating a
        # subject with air beneath them is the tell that it was pasted.
        x = int(round(W * subject_cx - cut.width / 2))
        x = max(0, min(x, W - cut.width))
        canvas.paste(cut, (x, H - cut.height), cut)
    else:
        # Rectangular second plate with a feathered left edge — the same
        # composite without a traced mask.
        panel_w = int(W * SUBJECT_W)
        panel = _cover(Image.open(subject).convert("RGB"), panel_w, H)
        mask = Image.new("L", (panel_w, H), 255)
        md = ImageDraw.Draw(mask)
        for i in range(FEATHER):
            md.line([(i, 0), (i, H)], fill=int(255 * i / FEATHER))
        canvas.paste(panel, (W - panel_w, 0), mask)

    # Type. Size is fixed by the measurement, not fitted to the string; if the
    # copy is too long it wraps, exactly as their 3-4 line variants do.
    # "Longer string -> smaller cap" is their own rule: cap height ranges
    # 0.051-0.100 H across the 12, and the 31-character example runs 0.060 H
    # while the 19-character one runs 0.078 H. So step DOWN from their mean
    # until the copy fits one line, rather than wrapping at a fixed size — a
    # 3-line card is what they reserve for 38-43 character strings.
    words = [(w, WHITE) for w in white_part.split()]
    words += [(w, YELLOW) for w in yellow_part.split()]
    max_w = int(W * TEXT_MAX_FRAC)
    cap_px = round(H * CAP_FRAC)
    # Shrink until the quote fits on ONE line.
    #
    # A second line is what puts type over a face. The band the measured set
    # uses runs y 0.029-0.208 H, and one line of cap 0.0773 H ends around
    # 0.11 H — clear of almost every head in this room. Two lines reach to
    # ~0.19 H, which is exactly where a standing bystander's head sits, and
    # that is how "Then why does he / smell like marijuana?" landed across a
    # defendant's face.
    #
    # The ladder used to stop at 0.051 — the smallest cap in the measured set,
    # from their 971K thumbnail. Going below that is off-spec, so two more
    # rungs are allowed rather than accepting the second line: a slightly small
    # quote reads, a quote over a face does not. If even 0.044 needs two lines
    # the copy is too long and packaging should be fixed, not the type.
    for frac in (CAP_FRAC, 0.072, 0.066, 0.060, 0.055, 0.051, 0.047, 0.044):
        cap_px = round(H * frac)
        font = _font(round(cap_px / 0.72))
        if len(_wrap(words, font, max_w)) == 1:
            break
    size = round(cap_px / 0.72)            # Montserrat cap/em ~0.72
    font = _font(size)
    lines = _wrap(words, font, max_w)
    line_h = round(size * 1.06)

    stroke = max(6, round(cap_px * STROKE_RATIO))
    x0 = int(W * TEXT_SIDE_FRAC)
    y0 = int(H * TEXT_TOP_FRAC)

    # Zero-offset black glow: the glyph mask, blurred, composited as black.
    # Verified symmetric in their set (up6 vs down6 within 1.5 L), so it is a
    # glow and not a shadow — offsetting it would be the wrong artefact.
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    for i, line in enumerate(lines):
        gd.text((x0, y0 + i * line_h), " ".join(w for w, _ in line),
                font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(GLOW_RADIUS / 2))
    canvas = Image.composite(Image.new("RGB", (W, H), BLACK), canvas, glow)

    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        x, y = x0, y0 + i * line_h
        for word, colour in line:
            draw.text((x, y), word, font=font, fill=colour,
                      stroke_width=stroke, stroke_fill=BLACK)
            x += draw.textlength(word + " ", font=font)

    if arrow:
        _arrow(canvas, arrow[0], arrow[1])

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=94)
    print(f"cap {cap_px}px ({cap_px / H:.4f} H)  stroke {stroke}px  "
          f"{len(lines)} line(s)  -> {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bg", required=True, type=Path)
    ap.add_argument("--subject", required=True, type=Path)
    ap.add_argument("--white", required=True)
    ap.add_argument("--yellow", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--arrow", default=None,
                    help="tip position as X,Y in frame fractions, e.g. 0.30,0.46")
    ap.add_argument("--subject-w", type=float, default=SUBJECT_W,
                    help="traced subject width as a fraction of the canvas")
    ap.add_argument("--subject-cx", type=float, default=SUBJECT_CX,
                    help="subject centre x as a fraction of the canvas")
    ap.add_argument("--cutout", default=None, type=Path,
                    help="RGBA png of the subject, masked; overrides --subject")
    a = ap.parse_args()
    tip = None
    if a.arrow:
        x, y = (float(v) for v in a.arrow.split(","))
        tip = (x, y)
    build(a.bg, a.subject, a.white, a.yellow, a.out, arrow=tip,
          cutout=a.cutout, subject_w=a.subject_w, subject_cx=a.subject_cx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


