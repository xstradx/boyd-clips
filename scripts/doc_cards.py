"""Document card stack — the 52-second opening.

Built to the spec forensics MEASURED off Audit the Court, not to taste:

  * rotation **+4.81 degrees**
  * card sits over a BLURRED COPY OF ITSELF, not over black
  * highlighter `#FDC501` (their yellow), secondary `#77ABF8` blue
  * median hold **9.1 s** per card; doc cards are 8.5% of their runtime
  * **hard cuts only** — zero dissolves in 100 minutes of their video
  * source branding left visible, because the point is that the record is real

Structure, also measured: they run **51.7 s / 9 beats of cards before any hearing
footage at all**. That is what makes the video survive the "would this be work if
you deleted the footage" test. Ours has better documents than theirs — a full
Register of Actions, a bond record, a jail booking, and a verdict entry.

PIL rather than Blender: the graphics team measured PIL at 11.45 s vs Blender's
24.06 s for a 135-frame plate, and Blender's advantage (0.021 px vs 0.186 px edge
accuracy) only exists on a MOVING edge. These cards are static and hard-cut, so
the moving-edge advantage is worth nothing here and the speed is worth a lot.

Usage:  python scripts/doc_cards.py [out_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
ROT = 4.81                      # measured
HIGHLIGHT = (0xFD, 0xC5, 0x01)  # measured
INK = (0x1A, 0x1A, 0x1A)
PAPER = (0xF4, 0xF2, 0xED)
RULE = (0xC9, 0xC4, 0xB8)
RED = (0xD4, 0x2B, 0x2B)
GROUND = (0x15, 0x18, 0x1D)

FONTS = Path("assets/fonts")


def font(name: str, size: int):
    for cand in (FONTS / name, Path(r"C:\Windows\Fonts") / name):
        if cand.exists():
            return ImageFont.truetype(str(cand), size)
    for fb in ("Anton-Regular.ttf", "Archivo-Var.ttf"):
        p = FONTS / fb
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def head(size):  return font("Anton-Regular.ttf", size)
def body(size):  return font("Archivo-Var.ttf", size)
def mono(size):  return font("consola.ttf", size)


def _text(d, xy, s, f, fill, spacing=0):
    """Draw with optional letter-spacing (PIL has none natively)."""
    if not spacing:
        d.text(xy, s, font=f, fill=fill)
        return
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + spacing


def build_card(title: str, source: str, rows: list[tuple[str, str]],
               highlight_row: int | None = None, note: str | None = None) -> Image.Image:
    """One document plate, unrotated, on paper."""
    # Height follows the content. A fixed 720 left the bottom half of every card
    # empty, which reads as a template with nothing in it rather than a record.
    cw = 1180
    ch = 178 + 78 * len(rows) + (110 if note else 46)
    card = Image.new("RGB", (cw, ch), PAPER)
    d = ImageDraw.Draw(card)

    d.rectangle([-8, -8, cw + 8, 96], fill=INK)
    _text(d, (44, 28), title.upper(), head(44), PAPER, spacing=1.5)
    _text(d, (44, 112), source.upper(), body(20), (0x6B, 0x66, 0x5E), spacing=2.2)
    d.line([(44, 146), (cw - 44, 146)], fill=RULE, width=2)

    y = 178
    for i, (label, value) in enumerate(rows):
        if highlight_row is not None and i == highlight_row:
            # highlighter runs behind the VALUE only, like a marker pen
            vw = d.textlength(value, font=head(46))
            d.rectangle([340, y + 6, 340 + vw + 18, y + 58], fill=HIGHLIGHT)
        _text(d, (44, y + 16), label.upper(), body(22), (0x6B, 0x66, 0x5E), spacing=1.6)
        _text(d, (348, y + 4), value, head(46), INK)
        y += 78
        d.line([(44, y - 6), (cw - 44, y - 6)], fill=RULE, width=1)

    if note:
        d.rectangle([44, ch - 92, 52, ch - 40], fill=RED)
        _text(d, (68, ch - 88), note, body(24), (0x3A, 0x36, 0x30))
    return card


def compose(card: Image.Image) -> Image.Image:
    """Rotate, and lay it over a blurred, enlarged copy of itself."""
    rot = card.rotate(ROT, resample=Image.BICUBIC, expand=True, fillcolor=PAPER)

    # The background IS the card — blown up far enough that you read ITS ink and
    # rules out of focus, not a grey wash. Blending 55% toward the dark ground
    # killed exactly the thing that makes this treatment work, so this darkens
    # with a multiply-ish blend at 32% and scales 2.4x instead of 1.35x.
    scale = 2.4
    bg = card.resize((int(W * scale), int(W * scale * card.height / card.width)),
                     Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(26))
    bg = Image.blend(bg.convert("RGB"), Image.new("RGB", bg.size, GROUND), 0.32)
    frame = Image.new("RGB", (W, H), GROUND)
    frame.paste(bg, ((W - bg.width) // 2, (H - bg.height) // 2))

    # drop shadow so the plate sits off the blur
    sh = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([0, 0, rot.size[0], rot.size[1]], fill=(0, 0, 0, 150))
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    px = (W - rot.width) // 2
    py = (H - rot.height) // 2
    frame.paste(Image.alpha_composite(
        Image.new("RGBA", sh.size, (0, 0, 0, 0)), sh).convert("RGB"),
        (px + 10, py + 16), sh)
    frame.paste(rot, (px, py))
    return frame


# ------------------------------------------------------------------ the 9 beats
CARDS = [
    ("The crash", "Bexar County Sheriff's Office — booking record",
     [("Offense date", "25 MARCH 2023"), ("Location", "S. ALAMO & PROBANDT"),
      ("Charge", "COLLISION INVOLVING DEATH")], 2,
     "Booking B202527680 — offence recorded 03/25/2023"),

    ("The victim", "Bexar County Medical Examiner / news record",
     [("Name", "ERIK MICHAEL MOODY"), ("Age", "36"),
      ("Found", "SIDEWALK, BLUE STAR")], 0,
     "Reported by KSAT, mySA and KENS5, March 2023"),

    ("The arrest", "Register of Actions — DC2023CR8866",
     [("Arrest date", "27 MARCH 2023"), ("Surrendered", "TWO DAYS AFTER"),
      ("Agency", "BEXAR COUNTY SHERIFF")], 1, None),

    ("The bond", "Register of Actions — bond record",
     [("Amount", "$100,000"), ("Type", "CORPORATE SURETY"),
      ("Released", "1 APRIL 2023")], 0,
     "Bond #2011322 — 5 days in custody"),

    ("The defendant", "Bexar County jail record — SID 965702",
     [("Name", "ROBERT CASTILLO"), ("Age at offense", "29"),
      ("Prior arrests", "TWO, AS A TEENAGER")], 2,
     "2011 and 2013. Nothing in the decade before the crash."),

    ("The charges", "187th District Court — DC2023CR8866",
     [("Count 1", "MANSLAUGHTER"),
      ("Count 2", "FAIL TO STOP & RENDER AID"), ("Case type", "FELONY")], 0, None),

    ("The trial", "187th District Court — Judge Stephanie Boyd",
     [("Began", "11 MAY 2026"), ("Days of testimony", "EIGHT"),
      ("Defendant testified", "YES")], 2, None),

    ("The defense", "Court's charge to the jury",
     [("Theory 1", "MISTAKE OF FACT"), ("Theory 2", "NECESSITY"),
      ("Theory 3", "DURESS")], None,
     "He said he was being shot at."),

    ("The verdict", "Register of Actions — disposition entry",
     [("Finding", "GUILTY BY THE JURY"), ("Date", "19 MAY 2026"),
      ("Appeal filed", "12 JUNE 2026")], 0, None),
]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/review/castillo_cards")
    out.mkdir(parents=True, exist_ok=True)
    print(f"{'#':>2}  {'card':16s} hold   file")
    total = 0.0
    for i, (title, src, rows, hl, note) in enumerate(CARDS, 1):
        img = compose(build_card(title, src, rows, hl, note))
        p = out / f"card_{i:02d}.png"
        img.save(p)
        hold = 9.1 if i not in (1, 9) else 6.0     # open and close land harder
        total += hold
        print(f"{i:>2}  {title[:16]:16s} {hold:4.1f}s  {p.name}")
    print(f"\n{len(CARDS)} cards, {total:.1f}s total "
          f"(Audit's measured opening: 51.7s across 9 beats)")
    print(f"-> {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
