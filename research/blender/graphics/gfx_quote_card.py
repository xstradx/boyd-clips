"""DELIVERABLE 3 - QUOTE CARD. Lower-two-thirds card, verbatim quote plus
attribution.

    blender -b --python gfx_quote_card.py

MECHANISM - a mask rise, per line, timed off the scrim
-----------------------------------------------------
Each line of the quote sits in its own hard band exactly one line tall and
travels UP into it from 30px below. The band never moves; the type does. That
is a mask reveal, and it is the one thing that separates a quote card that
reads as printed matter from one that reads as a slideshow fade.

Line stagger is +4 frames, at the tight end of the measured broadcast range
(+4,+5,+8,+5), because these lines are one sentence and must read as one
utterance. The scrim's own descending edge gates line one, so again nothing is
revealed before the surface it sits on exists.

Wrapping is measured in Blender, not estimated from a metrics table, so the
wrap that renders is the wrap that was measured (Stage.wrap).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G

HERE = os.path.dirname(os.path.abspath(__file__))

SCRIM_TOP = 372
SCRIM_ALPHA = 0.90
RULE_H = 4

# cap= is CAP HEIGHT, and an opening quote is only ~0.3 of the cap height, so
# a 132 'cap' renders a 40px mark. Sized against the H, not against the glyph.
MARK_CAP = 380
MARK_X = 128
MARK_BASE = 700

TEXT_X = 286
TEXT_W = 1420
QUOTE_CAP = 40
LEADING = 68
FIRST_BASE = 520

ATTR_RULE_W, ATTR_RULE_H = 64, 3
ATTR_CAP, ATTR_TRACK = 18, 190
ATTR_ALPHA = 0.72

QUOTE_FONT = "Archivo-Regular"
# NOT Anton. Measured: Anton's U+201C is 14 vertices - two hard slabs, not a
# comma form - and at 380 cap it renders as two red rectangles. Vertex count is
# a reliable tell for this: slab quotes 14, drawn quotes 152-224.
#   Anton 14 | Bebas 14 | Oswald-Bold 152 | Archivo-Bold 154 | Montserrat-Bold 224
MARK_FONT = "Archivo-Bold"
ATTR_FONT = "Archivo-SemiCond-SemiBold"

F_SCRIM = (1, 9)
F_RULE = (3, 13)
F_MARK = (7, 14)
LINE_STAGGER = 4
LINE_TRAVEL = 8
RISE_PX = 30

DEFAULT_QUOTE = ("He told the officers he had been drinking since noon and "
                 "that he never saw the crosswalk at all.")
DEFAULT_ATTR = "OFFICER D. REYES — ARREST REPORT, 14 MARCH 2025"


def build(quote=DEFAULT_QUOTE, attribution=DEFAULT_ATTR, hold=90,
          out_dir=None, samples=64, dither=1.0, render=True):
    st = G.Stage(1920, 1080, fps=30, frames=10, samples=samples, dither=dither)
    lines = st.wrap(quote, QUOTE_FONT, QUOTE_CAP, TEXT_W)
    n = len(lines)

    f_last_in = F_MARK[0] + (n - 1) * LINE_STAGGER + LINE_TRAVEL
    f_attr = f_last_in + 2
    f_out = f_attr + 10 + hold
    f_end = f_out + 16
    st.sc.frame_end = f_end

    scrim = st.rect(0, SCRIM_TOP, 1920, 1080 - SCRIM_TOP, color=G.GROUND,
                    opacity=SCRIM_ALPHA, name="SCRIM")
    rule = st.rect(0, SCRIM_TOP, 1920, RULE_H, color=G.RED, name="TOPRULE")
    scrim.layer(0)
    rule.layer(1)

    scrim.set_wipe_z(SCRIM_TOP)
    scrim.wipe_z([(F_SCRIM[0], SCRIM_TOP), (F_SCRIM[1], 1080)], [G.EASE_OUT])
    rule.set_wipe_x(0)
    rule.wipe_x([(F_RULE[0], 0), (F_RULE[1], 1920)], [G.EASE_OUT])

    mark = st.text("“", font=MARK_FONT, cap=MARK_CAP, x=MARK_X,
                   baseline=MARK_BASE, color=G.RED, name="MARK")
    mark.layer(2)
    # NO band on the mark. A quotation mark's ink sits high above its baseline,
    # so a band derived from cap height and baseline chops it - measured, the
    # glyph rendered as two solid red blocks. It is decorative, not a mask-rise
    # element, so it rises and fades instead.
    mark.slide_y([(1, RISE_PX * 1.5), (F_MARK[0], RISE_PX * 1.5),
                  (F_MARK[1], 0)], [None, G.EASE_OUT])
    mark.opacity([(1, 0.0), (F_MARK[0], 0.0), (F_MARK[1], 1.0)],
                 [None, G.EASE_OUT])

    qlines = []
    for i, line in enumerate(lines):
        base = FIRST_BASE + i * LEADING
        e = st.text(line, font=QUOTE_FONT, cap=QUOTE_CAP, x=TEXT_X,
                    baseline=base, color=G.INK, name="Q%d" % i)
        e.layer(2)
        # the band is ONE LINE tall: the ascender of the line below and the
        # descender of the line above must never leak in.
        e.band(base - QUOTE_CAP - 10, base + 12)
        f0 = F_MARK[0] + i * LINE_STAGGER
        e.slide_y([(1, RISE_PX), (f0, RISE_PX), (f0 + LINE_TRAVEL, 0)],
                  [None, G.EASE_OUT])
        e.opacity([(1, 0.0), (f0, 0.0), (f0 + LINE_TRAVEL // 2, 1.0)],
                  [None, G.EASE_OUT])
        qlines.append(e)

    attr_base = FIRST_BASE + n * LEADING + 44
    ar = st.rect(TEXT_X, attr_base - 8, ATTR_RULE_W, ATTR_RULE_H, color=G.RED,
                 name="ATTRRULE")
    at = st.text(attribution, font=ATTR_FONT, cap=ATTR_CAP,
                 x=TEXT_X + ATTR_RULE_W + 20, baseline=attr_base, color=G.INK,
                 opacity=ATTR_ALPHA, tracking=ATTR_TRACK, name="ATTR")
    ar.layer(2); at.layer(2)
    ar.set_wipe_x(TEXT_X)
    ar.wipe_x([(f_attr, TEXT_X), (f_attr + 6, TEXT_X + ATTR_RULE_W)],
              [G.EASE_OUT])
    at.band(attr_base - ATTR_CAP - 8, attr_base + 10)
    at.slide_y([(1, 18), (f_attr + 2, 18), (f_attr + 10, 0)], [None, G.EASE_OUT])
    at.opacity([(1, 0.0), (f_attr + 2, 0.0), (f_attr + 8, ATTR_ALPHA)],
               [None, G.EASE_OUT])

    # exit: everything fades together. A quote card is a held READ - retracting
    # it with a wipe would imply the sentence is being taken away mid-sentence.
    for e in [scrim, rule, mark, ar, at] + qlines:
        e.opacity([(f_out, e.base_opacity), (f_end, 0.0)], [G.EASE_INOUT])

    out = out_dir or os.path.join(HERE, "renders", "quote_card")
    print("QUOTE CARD  %d lines  attr_base=%d  frames=1..%d" % (n, attr_base, f_end))
    for i, l in enumerate(lines):
        print("   line %d: %r" % (i, l))
    if render:
        st.render(out)
    return st, out, f_end


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build(a[0] if a else DEFAULT_QUOTE, a[1] if len(a) > 1 else DEFAULT_ATTR)
