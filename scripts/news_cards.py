"""The news beat — what was reported in March 2023, before any trial.

Nathan, 2026-08-13: "you didnt even include any of the news clips like u said u
would??" Correct. CASTILLO_SINGLE_CUT.md says Act 1 opens on the news record and
the assembled film went straight from the cold open into the State's opening.

WHY THIS BEAT EARNS ITS PLACE, beyond having promised it:

  * It establishes the case as it looked at the time — open and shut — so the
    defence has something to overturn in Act 2.
  * The shooting claim is IN the 2023 reporting. The passenger told police the
    Tesla was shot at. That means the defence is not a courtroom invention, and
    the film can say so with a citation instead of an assertion.
  * It gives Erik Moody time as a person. LONGFORM-ANTIPATTERNS checklist item 9
    requires the victim be given >30s and named again in the closing minute; the
    cut currently names him and moves on, which is the exploitation pattern the
    NCVC guidance names directly.

SOURCING DISCIPLINE. The KSAT card is verbatim from the article, fetched
2026-08-13 — headline, byline, date and the two claims. The community card cites
mySA and KENS5 headlines that came from search results rather than a fetch
(mysanantonio.com blocks our fetcher; the KENS5 URL was truncated), so it carries
the outlets and the substance but does not put words in quotation marks that were
not verified character-for-character.

Style is deliberately NOT the docket card: a press clipping reads as a different
kind of record, and mixing them would flatten both.

Usage:  python scripts/news_cards.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_cards import _text, body, compose, head  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

PAPER = (0xF4, 0xF2, 0xED)
INK = (0x1A, 0x1A, 0x1A)
RULE = (0xC9, 0xC4, 0xB8)
RED = (0xD4, 0x2B, 0x2B)
MUTED = (0x6B, 0x66, 0x5E)

OUT = Path("out/review/castillo_news")

# sentinel row meaning "half-height paragraph gap"
GAP = ""


def wrap(d, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def news_card(outlet: str, dateline: str, headline: str,
              body_lines: list[str], byline: str | None = None,
              kicker: str = "REPORTED AT THE TIME") -> Image.Image:
    cw = 1240
    d0 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    hf = head(60)
    hl = wrap(d0, headline, hf, cw - 96)
    bf = body(28)
    wrapped: list[str] = []
    for ln in body_lines:
        wrapped += wrap(d0, ln, bf, cw - 96) + [GAP]  # marker = half gap
    ch = 150 + 74 * len(hl) + 40 * len(wrapped) + 96

    card = Image.new("RGB", (cw, ch), PAPER)
    d = ImageDraw.Draw(card)

    # masthead
    d.rectangle([-8, -8, cw + 8, 74], fill=INK)
    _text(d, (44, 20), outlet.upper(), head(34), PAPER, spacing=3.0)
    tw = d.textlength(kicker, font=body(19))
    _text(d, (cw - 44 - tw - 10, 28), kicker, body(19), (0xB9, 0xB4, 0xAA), spacing=1.6)

    _text(d, (44, 92), dateline.upper(), body(21), MUTED, spacing=2.4)

    y = 126
    for ln in hl:
        _text(d, (44, y), ln, hf, INK)
        y += 74
    y += 6
    d.line([(44, y), (cw - 44, y)], fill=RULE, width=2)
    y += 22

    for ln in wrapped:
        if ln == GAP:
            y += 20
            continue
        _text(d, (44, y), ln, bf, (0x3A, 0x36, 0x30))
        y += 40

    if byline:
        d.rectangle([44, ch - 74, 52, ch - 34], fill=RED)
        _text(d, (68, ch - 70), byline, body(22), MUTED)
    return card


CARDS = [
    dict(outlet="KSAT 12",
         dateline="San Antonio · 28 March 2023",
         headline="Driver of Tesla that jumped curb, killed man on sidewalk surrenders to police",
         body_lines=[
             "Robert Castillo, 29, charged with failing to stop and render aid — a second-degree felony. Held on a $100,000 bond.",
             "Erik Moody, 36, died at the scene near S. Alamo and Probandt.",
         ],
         byline="Mary Claire Patton, KSAT — verified 2026-08-13"),

    dict(outlet="KSAT 12",
         dateline="From the passenger's account to police, March 2023",
         headline="Two claims were on the record before anyone reached a courtroom",
         body_lines=[
             "The passenger said the two had been drinking that evening and that Castillo \"seemed slightly intoxicated.\"",
             "The same passenger said the Tesla was shot at by occupants of another vehicle during a confrontation.",
         ],
         byline="Both accounts reported 28 March 2023 — three years before trial",
         kicker="BEFORE THE TRIAL"),

    dict(outlet="mySA  ·  KENS 5",
         dateline="San Antonio · late March 2023",
         headline="A community mourned him before a court ever named him a victim",
         body_lines=[
             "\"Blue Star community mourns man killed in Tesla hit-and-run\"  — mySA",
             "\"Man hit and killed by Tesla driver remembered at his favorite Southtown spot\"  — KENS 5",
             "Erik Michael Moody was 36.",
         ],
         byline="Headlines as published; full articles not re-verified",
         kicker="THE MAN WHO DIED"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{'#':>2}  {'outlet':16s} hold   file")
    for i, spec in enumerate(CARDS, 1):
        img = compose(news_card(**spec))
        p = OUT / f"news_{i:02d}.png"
        img.save(p)
        hold = 8.0 if i < 3 else 11.0        # the victim card holds longest
        print(f"{i:>2}  {spec['outlet'][:16]:16s} {hold:4.1f}s  {p.name}")
    print(f"\n-> {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
