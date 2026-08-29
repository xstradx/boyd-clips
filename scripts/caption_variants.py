"""Emit the SAME cut in several caption treatments so Nathan can compare them.

Everything shares the split-anchor rule proved in caption_thompson_style.py:
the defendant's card is bottom-anchored so it grows UP away from the divide,
Boyd's is top-anchored so it grows DOWN. Only the treatment changes.

Two engines:
  flow   one event per card; libass lays the line out. Colour-only emphasis,
         because anything that changes a glyph's metrics reflows the line.
  place  one event PER WORD at an absolute \\pos, x measured from the real font
         metrics. Nothing shares a layout, so a word can scale or take a box
         without moving its neighbours. This is what the old script could not
         do -- its docstring records that pop_scale drifted every word 33px
         left and 65px wide, which is a reflow artefact, not a law.

Vertical placement is CALIBRATED, not assumed: calibrate_variants.py renders
each variant over black, measures the ink bounding box, and writes the per-
anchor lead offsets back into leads.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTDIR = ROOT / "work/_variants/fonts"

SPLIT, GAP = 960, 14
PLAY_W, PLAY_H = 1080, 1920

FONTFILE = {
    "Anton": "Anton-Regular.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
    "Oswald": "Oswald-Bold.ttf",
    "Montserrat": "Montserrat-Bold.ttf",
    "Archivo": "Archivo-Bold.ttf",
    "Archivo SemiCond": "Archivo-SemiCond-SemiBold.ttf",
}


def t(x: float) -> str:
    x = max(0.0, x)
    return f"{int(x // 3600):d}:{int((x % 3600) // 60):02d}:{x % 60:05.2f}"


def secs(x: str) -> float:
    h, m, s = x.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


DROPPED = []


def wrap(toks, max_chars, max_lines, fnt=None, max_px=None):
    """Break a card into lines. Measures in PIXELS when given a font, because a
    character count is a proxy that is wrong by 2x between Bebas and Archivo.

    Overflow past max_lines is RECORDED, never silently discarded -- the old
    script's `lines[:MAX_LINES]` drops words off the end of a long card and the
    caption then disagrees with the audio."""
    lines, cur = [], []

    def too_wide(cand):
        if fnt is not None and max_px:
            return fnt.getlength(" ".join(cand)) > max_px
        return len(" ".join(cand)) > max_chars

    for tok in toks:
        if cur and too_wide(cur + [tok]):
            lines.append(cur)
            cur = [tok]
        else:
            cur.append(tok)
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        DROPPED.append(" ".join(w for ln in lines[max_lines:] for w in ln))
    return lines[:max_lines]


class V:
    """One caption treatment."""

    def __init__(self, key, desc, font, size, engine="flow", **kw):
        self.key, self.desc, self.font, self.size = key, desc, font, size
        self.engine = engine
        self.caps = kw.get("caps", True)
        self.words = kw.get("words", 3)
        self.chars = kw.get("chars", 13)
        self.lines = kw.get("lines", 2)
        self.primary = kw.get("primary", "&H00FFFFFF")
        self.secondary = kw.get("secondary", "&H00FFFFFF")
        self.hi = kw.get("hi")                    # active-word colour, or None
        self.tint_by_who = kw.get("tint_by_who")  # resting card colour per speaker
        self.outline = kw.get("outline", 6)
        self.shadow = kw.get("shadow", 2)
        self.border = kw.get("border", 1)         # 1 outline, 3 opaque box
        self.back = kw.get("back", "&H80000000")
        self.spacing = kw.get("spacing", 0)
        self.karaoke = kw.get("karaoke", False)
        self.pop = kw.get("pop")                  # (start_scale_pct, ms)
        self.marker = kw.get("marker")            # highlighter box colour
        self.marker_text = kw.get("marker_text", "&H00101010")
        self.lead = {"D": 0.0, "B": 0.0}          # calibrated

    def head(self):
        main = (f"Style: Main,{self.font},{self.size},{self.primary},{self.secondary},"
                f"&H00000000,{self.back},-1,0,0,0,100,100,{self.spacing},0,"
                f"{self.border},{self.outline},{self.shadow},2,60,60,700,1")
        mark = ""
        if self.marker:
            mark = (f"\nStyle: Mark,{self.font},{self.size},{self.marker_text},"
                    f"{self.marker_text},{self.marker},{self.marker},-1,0,0,0,"
                    f"100,100,{self.spacing},0,3,10,0,2,0,0,0,1")
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{main}{mark}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def anchor(self, who):
        """(alignment, MarginV) for a speaker, using the calibrated lead."""
        lead = self.lead.get("D" if who == "D" else "B", 0.0)
        if who == "D":
            return 2, int(round(PLAY_H - (SPLIT - GAP + lead)))
        return 8, int(round(SPLIT + GAP - lead))

    def font_obj(self):
        return ImageFont.truetype(str(FONTDIR / FONTFILE[self.font]), self.size)

    def build(self, segs):
        out = []
        fnt = self.font_obj() if self.engine == "place" else None
        for sg in segs:
            ws = sg.get("words") or []
            if not ws:
                continue
            who = sg.get("who", "B")
            an, margin = self.anchor(who)
            for i in range(0, len(ws), self.words):
                card = ws[i:i + self.words]
                toks = [w["w"].strip().replace("{", "").replace("}", "") for w in card]
                if self.caps:
                    toks = [x.upper() for x in toks]
                if self.engine == "flow":
                    out += self.flow(card, toks, who, an, margin)
                else:
                    out += self.place(card, toks, an, margin, fnt)
        return self.declash(out)

    # ---- flow engine -------------------------------------------------
    def flow(self, card, toks, who, an, margin):
        rows, idx, k = wrap(toks, self.chars, self.lines), [], 0
        for r in rows:
            idx.append(list(range(k, k + len(r))))
            k += len(r)
        base = (self.tint_by_who or {}).get(who, self.primary)
        tag = "{\\an%d}" % an

        if self.karaoke:
            a, b = card[0]["a"], card[-1]["b"]
            painted = []
            for row in idx:
                parts = []
                for j in row:
                    if j >= len(toks):
                        continue
                    cs = max(1, int(round((card[j]["b"] - card[j]["a"]) * 100)))
                    parts.append("{\\kf%d}%s" % (cs, toks[j]))
                painted.append(" ".join(parts))
            return [f"Dialogue: 0,{t(a)},{t(b)},Main,,0,0,{margin},,{tag}"
                    + "\\N".join(painted)]

        if self.hi is None and base == self.primary:
            a, b = card[0]["a"], card[-1]["b"]
            body = "\\N".join(" ".join(toks[j] for j in row if j < len(toks))
                              for row in idx)
            return [f"Dialogue: 0,{t(a)},{t(b)},Main,,0,0,{margin},,{tag}{body}"]

        ev = []
        for i, w in enumerate(card):
            a = w["a"]
            b = card[i + 1]["a"] if i + 1 < len(card) else w["b"]
            if b - a < 0.10:
                b = a + 0.10
            painted = []
            for row in idx:
                parts = []
                for j in row:
                    if j >= len(toks):
                        continue
                    c = (self.hi or self.primary) if j == i else base
                    parts.append("{\\c%s}%s" % (c, toks[j]))
                painted.append(" ".join(parts))
            ev.append(f"Dialogue: 0,{t(a)},{t(b)},Main,,0,0,{margin},,{tag}"
                      + "\\N".join(painted))
        return ev

    # ---- place engine ------------------------------------------------
    def place(self, card, toks, an, margin, fnt):
        widths = [fnt.getlength(x) for x in toks]
        space = fnt.getlength(" ")
        rows, idx, k = wrap(toks, self.chars, self.lines), [], 0
        for r in rows:
            idx.append(list(range(k, k + len(r))))
            k += len(r)
        line_h = self.size * 1.18
        ev = []
        for i, w in enumerate(card):
            a = w["a"]
            b = card[i + 1]["a"] if i + 1 < len(card) else w["b"]
            if b - a < 0.10:
                b = a + 0.10
            for ri, row in enumerate(idx):
                n = len(row)
                total = sum(widths[j] for j in row) + (space + self.spacing) * (n - 1)
                x = PLAY_W / 2 - total / 2
                if an == 2:   # bottom-anchored: rows stack upward off the edge
                    y = (PLAY_H - margin) - (len(idx) - 1 - ri) * line_h
                else:         # top-anchored: rows stack downward off the edge
                    y = margin + self.size + ri * line_h
                for j in row:
                    if j >= len(toks):
                        continue
                    live = (j == i)
                    pos = "{\\an2\\pos(%.1f,%.1f)}" % (x + widths[j] / 2, y)
                    style, pre = "Main", ""
                    if live and self.pop:
                        s0, ms = self.pop
                        pre += "{\\fscx%d\\fscy%d\\t(0,%d,\\fscx100\\fscy100)}" % (s0, s0, ms)
                    if live and self.marker:
                        style = "Mark"
                    elif live and self.hi:
                        pre += "{\\c%s}" % self.hi
                    ev.append(f"Dialogue: 0,{t(a)},{t(b)},{style},,0,0,0,,"
                              f"{pos}{pre}{toks[j]}")
                    x += widths[j] + space + self.spacing
        return ev

    # ---- overlap guard -----------------------------------------------
    def declash(self, out):
        """Same slot + overlapping time => libass STACKS them, which is what
        threw a card 299px out of place in the old script. Clip the earlier
        end back to the later start, per slot."""
        parsed = [l.split(",", 9) for l in out]
        slots = {}
        for f in parsed:
            slots.setdefault((f[3], f[8], f[9]. split("}")[0]), []).append(f)
        clipped = 0
        for group in slots.values():
            group.sort(key=lambda f: secs(f[1]))
            for i in range(len(group) - 1):
                if secs(group[i][2]) > secs(group[i + 1][1]):
                    group[i][2] = group[i + 1][1]
                    clipped += 1
        keep = [",".join(f) for f in parsed if secs(f[2]) > secs(f[1])]
        keep.sort(key=lambda l: secs(l.split(",", 9)[1]))
        if clipped:
            print(f"    clipped {clipped} overlapping events")
        return keep


VARIANTS = [
    V("A_current", "CURRENT - Anton 140, gold active word, 3-word roll",
      "Anton", 140, hi="&H0000D7FF"),

    V("B_popword", "one word at a time, 185px, scale-pop, no colour trick",
      "Anton", 185, engine="place", words=1, chars=24, lines=1,
      outline=8, shadow=0, pop=(114, 90)),

    V("C_broadcast", "news register - Archivo, sentence case, solid scrim",
      "Archivo", 66, caps=False, words=8, chars=30, lines=2,
      border=3, outline=9, shadow=0, back="&HB0000000"),

    V("D_condensed", "Oswald condensed, karaoke fill grey->white",
      "Oswald", 122, words=5, chars=20, karaoke=True,
      primary="&H00FFFFFF", secondary="&H00909090", outline=5, shadow=0),

    V("E_speaker", "colour IS the speaker tag - ice = defendant, amber = Boyd",
      "Anton", 132, hi="&H00FFFFFF",
      tint_by_who={"D": "&H00F0D0A8", "B": "&H0060C8F0"}, outline=6, shadow=2),

    V("F_stripped", "Bebas Neue 168, pure white, no highlight at all",
      "Bebas Neue", 168, words=3, chars=14, outline=7, shadow=0),

    V("G_marker", "highlighter marker box on the live word",
      "Montserrat", 92, engine="place", words=4, chars=17, lines=1,
      outline=5, shadow=0, marker="&H0033C0F0"),
]

BY_KEY = {v.key: v for v in VARIANTS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--leads")
    a = ap.parse_args()
    segs = json.loads(Path(a.transcript).read_text(encoding="utf-8"))
    leads = {}
    if a.leads and Path(a.leads).exists():
        leads = json.loads(Path(a.leads).read_text(encoding="utf-8"))
    od = Path(a.outdir)
    od.mkdir(parents=True, exist_ok=True)
    for v in VARIANTS:
        v.lead = leads.get(v.key, {"D": 0.0, "B": 0.0})
        ev = v.build(segs)
        (od / f"{v.key}.ass").write_text(v.head() + "\n".join(ev) + "\n",
                                         encoding="utf-8")
        print(f"  {v.key:13s} {len(ev):4d} events  {v.desc}")


if __name__ == "__main__":
    main()
