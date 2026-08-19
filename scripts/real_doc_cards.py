"""The opening, built from REAL documents instead of facsimiles.

Nathan, 2026-08-14: "i told you to show real stuff not those cards you just made
and you never listened to me."

He is right, and it was the same miss twice. The forensics team MEASURED that
Audit the Court shows real sourced records with their source branding left
visible — that is the whole reason their card stack reads as evidence rather than
as a slide deck. I took the measured treatment (+4.81 degrees, blurred copy of
itself behind, #FDC501 highlighter, ~9s holds) and applied it to cards I drew
myself, which reproduces the DATA and throws away the thing that made it work.

So these are screenshots of the actual pages:

  * Bexar County's own Jail View — CASTILLO, ROBERT, SO # 965702 — captured
    headless from portal-txbexar.tylertech.cloud, Tyler Technologies footer and
    all. Three bookings: 2013, the 2023 manslaughter arrest, the 2026 remand.
  * Texas Penal Code 19.04 (Manslaughter) and Transportation Code 550.021
    (Accident Involving Personal Injury or Death), from texas.public.law, which
    prints the statutes.capitol.texas.gov source line and an "Up to date /
    Verified" stamp on the page.

The highlighter runs over the passage actually being discussed, which is what
Audit does and what Nathan asked for — highlight the thing you are talking about.

Capture command used (Chrome is installed; no python screenshot package is):
    chrome --headless=new --hide-scrollbars --virtual-time-budget=25000
           --window-size=1500,1500 --screenshot=out.png URL

Usage:  python scripts/real_doc_cards.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_cards import _text, body, head  # noqa: E402

W, H = 1920, 1080
ROT = 4.81
HIGHLIGHT = (0xFD, 0xC5, 0x01)
GROUND = (0x15, 0x18, 0x1D)
INK = (0x1A, 0x1A, 0x1A)
PAPER = (0xF4, 0xF2, 0xED)
RED = (0xD4, 0x2B, 0x2B)

SHOTS = Path("out/source/shots")
OUT = Path("out/review/castillo_realdocs")


def snap(img: Image.Image, box, slack=26, thresh=150):
    """Snap a hand-placed box onto the ink it is meant to mark.

    Hand-typed coordinates land a few pixels off and the marker reads as sloppy —
    a highlighter that misses the line is worse than none. This finds the actual
    dark rows and columns inside the box (widened by `slack`) and returns their
    bounding box, so the mark sits ON the words.
    """
    x0, y0, x1, y1 = box
    g = img.convert("L")
    px = g.load()
    X0, Y0 = max(0, x0 - slack), max(0, y0 - slack)
    X1, Y1 = min(img.width, x1 + slack), min(img.height, y1 + slack)

    rows = [y for y in range(Y0, Y1)
            if sum(1 for x in range(X0, X1, 2) if px[x, y] < thresh) > 3]
    if not rows:
        return box
    # keep the run of rows nearest the requested centre
    mid = (y0 + y1) / 2
    run, best = [], []
    prev = None
    for y in rows:
        if prev is not None and y - prev > 3:
            if not best or abs(sum(run) / len(run) - mid) < abs(sum(best) / len(best) - mid):
                best = run
            run = []
        run.append(y)
        prev = y
    if run and (not best or abs(sum(run) / len(run) - mid) < abs(sum(best) / len(best) - mid)):
        best = run
    ny0, ny1 = min(best), max(best)

    cols = [x for x in range(X0, X1)
            if sum(1 for y in range(ny0, ny1 + 1) if px[x, y] < thresh) > 0]
    if not cols:
        return (x0, ny0, x1, ny1)
    return (min(cols), ny0, max(cols), ny1)


def marker(img: Image.Image, boxes, pad=4):
    """Highlighter behind the ink, like a marker pen — multiply, not paint-over."""
    boxes = [snap(img, b) for b in boxes]
    lay = img.convert("RGB").copy()
    d = ImageDraw.Draw(lay)
    for (x0, y0, x1, y1) in boxes:
        d.rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], fill=HIGHLIGHT)
    # multiply so dark text survives on top of the yellow
    base = img.convert("RGB")
    px_b, px_l = base.load(), lay.load()
    for (x0, y0, x1, y1) in boxes:   # already snapped above
        for y in range(max(0, y0 - pad), min(base.height, y1 + pad)):
            for x in range(max(0, x0 - pad), min(base.width, x1 + pad)):
                r, g, b = px_b[x, y]
                hr, hg, hb = px_l[x, y]
                px_b[x, y] = (r * hr // 255, g * hg // 255, b * hb // 255)
    return base



def stitch(shot: str, bands, gap=10):
    """Stack chosen horizontal bands of a page, dropping what sits between.

    The KSAT article has a law-firm advert wedged between the masthead and the
    story. Cropping past it would lose the KSAT branding, which is the whole
    reason to show the real page. So take the masthead band and the story band
    and butt them together — an advert removed, nothing editorial touched.
    """
    im = Image.open(SHOTS / shot).convert("RGB")
    parts = [im.crop((x0, y0, x1, y1)) for (x0, y0, x1, y1) in bands]
    w = max(p.width for p in parts)
    h = sum(p.height for p in parts) + gap * (len(parts) - 1)
    out = Image.new("RGB", (w, h), (255, 255, 255))
    y = 0
    for pt in parts:
        out.paste(pt, (0, y))
        y += pt.height + gap
    return out


def plate(shot: str, crop, boxes, caption: str, source: str,
          bands=None) -> Image.Image:
    im = stitch(shot, bands) if bands else Image.open(SHOTS / shot).convert("RGB").crop(crop)
    im = marker(im, boxes)

    # caption bar under the document, so the viewer is told what they are seeing
    bar_h = 96
    card = Image.new("RGB", (im.width, im.height + bar_h), PAPER)
    card.paste(im, (0, 0))
    d = ImageDraw.Draw(card)
    d.rectangle([0, im.height, card.width, card.height], fill=INK)
    d.rectangle([28, im.height + 26, 36, im.height + 70], fill=RED)
    _text(d, (52, im.height + 20), caption.upper(), head(30), PAPER, spacing=1.4)
    _text(d, (52, im.height + 60), source, body(19), (0x9A, 0x95, 0x8C), spacing=1.0)
    return card


def compose(card: Image.Image) -> Image.Image:
    rot = card.rotate(ROT, resample=Image.BICUBIC, expand=True, fillcolor=PAPER)
    scale = 2.2
    bg = card.resize((int(W * scale), int(W * scale * card.height / card.width)), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(26))
    bg = Image.blend(bg.convert("RGB"), Image.new("RGB", bg.size, GROUND), 0.34)
    frame = Image.new("RGB", (W, H), GROUND)
    frame.paste(bg, ((W - bg.width) // 2, (H - bg.height) // 2))

    fit = min((W - 190) / rot.width, (H - 150) / rot.height, 1.0)
    if fit < 1.0:
        rot = rot.resize((int(rot.width * fit), int(rot.height * fit)), Image.LANCZOS)

    sh = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([0, 0, rot.size[0], rot.size[1]], fill=(0, 0, 0, 160))
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    px, py = (W - rot.width) // 2, (H - rot.height) // 2
    frame.paste(Image.new("RGB", sh.size, (0, 0, 0)), (px + 10, py + 16), sh)
    frame.paste(rot, (px, py))
    return frame


# Highlight boxes read off the captured screenshots, in CROPPED coordinates.
PLATES = [
    dict(shot="ksat.png", crop=None,
         bands=[(0, 0, 1400, 150), (60, 455, 1400, 770)],
         boxes=[(340, 398, 1060, 432)],     # subhead: "Erik Moody died Saturday near Blue Star"
         caption="How it was reported at the time",
         source="KSAT 12 · Mary Claire Patton · published 28 March 2023"),

    dict(shot="rec_2023.png", crop=(336, 84, 1486, 596),
         boxes=[(20, 130, 66, 148),          # SO # 965702
                (24, 366, 322, 392)],        # COLLISION INVOLVING DEATH
         caption="The arrest — 28 March 2023",
         source="Bexar County Jail View · portal-txbexar.tylertech.cloud · SO # 965702"),

    dict(shot="rec_2023.png", crop=(336, 355, 1486, 600),
         boxes=[(580, 108, 690, 130),        # offense date
                (860, 108, 975, 130)],       # arrest date
         caption="Offense 25 March · arrested 27 March · released on bond",
         source="Bexar County Jail View · warrant 1830086 · San Antonio Police Department"),

    dict(shot="rec_2013.png", crop=(336, 84, 1486, 596),
         boxes=[(24, 366, 300, 392)],
         caption="His record before the crash — two arrests, both as a teenager",
         source="Bexar County Jail View · 2011 and 2013 · nothing in the decade after"),

    dict(shot="statute_1904.png", crop=(340, 110, 1090, 430),
         boxes=[(70, 145, 660, 172)],        # "recklessly causes the death"
         caption="What the State had to prove",
         source="Texas Penal Code § 19.04 Manslaughter · statutes.capitol.texas.gov"),

    dict(shot="rec_2026.png", crop=(336, 84, 1486, 596),
         boxes=[(24, 366, 340, 392)],
         caption="Booked again the day after the jury came back",
         source="Bexar County Jail View · 20 May 2026 · manslaughter, fail to stop and render aid"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{'#':>2}  {'caption':52s} {'hold':>5s}")
    for i, spec in enumerate(PLATES, 1):
        img = compose(plate(**spec))
        p = OUT / f"real_{i:02d}.png"
        img.save(p)
        print(f"{i:>2}  {spec['caption'][:52]:52s} {9.1:5.1f}s  -> {p.name}")
    print(f"\n-> {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
