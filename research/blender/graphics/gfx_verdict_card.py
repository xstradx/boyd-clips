"""DELIVERABLE 4 - VERDICT CARD. Full frame, heavy, for the end.

    blender -b --python gfx_verdict_card.py -- GUILTY MANSLAUGHTER "19 MAY 2026"

WHERE THE WEIGHT ACTUALLY COMES FROM
------------------------------------
Not from size, and not from a long ease. Three things, in this order:

1  The plate opens as a BAND FROM THE CENTRE OUT in 4 frames - both z edges
   move at once, in opposite directions, on EASE_IN (accelerating INTO the
   stop). Four frames at 30fps is under the ~5-frame threshold at which the eye
   stops tracking an edge and starts reading an event.

2  A FRAME SHAKE on the landing frame, 11px, decaying 1.0/-0.55/0.28/-0.12 over
   4 frames then dead. This is the single biggest contributor and it costs
   nothing. Amplitudes for a double strike are EQUAL, not decaying between
   strikes - the measured gavel reference's two blows sit within 1.1 dB.

3  The verdict word arrives on a 3-frame scale from 1.045 to 1.000. NOT a
   bounce. 0 of 7 measured broadcast references overshoot on a settle;
   overshoot is the template tell.

Everything else - eyebrow, charge, rule, date - is staggered AFTER the impact
so the card resolves rather than assembles.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G

HERE = os.path.dirname(os.path.abspath(__file__))

CX = 960
PLATE_ALPHA = 0.95

EYEBROW_CAP, EYEBROW_TRACK, EYEBROW_ALPHA = 15, 320, 0.55
EYEBROW_BASE = 402
VERDICT_CAP, VERDICT_BASE = 168, 606
CHARGE_CAP, CHARGE_BASE = 62, 700
RULE_W, RULE_H, RULE_Y, RULE_ALPHA = 560, 2, 744, 0.22
DATE_CAP, DATE_TRACK, DATE_ALPHA, DATE_BASE = 20, 280, 0.70, 800

EYEBROW_FONT = "Archivo-Bold"
VERDICT_FONT = "Anton"
CHARGE_FONT = "Anton"
DATE_FONT = "Archivo-SemiCond-SemiBold"

F_SLAM = (1, 5)          # plate opens from the centre
F_IMPACT = 5
F_VERDICT = (5, 8)
F_CHARGE = (10, 17)
F_RULE = (14, 21)
F_DATE = (18, 26)
F_EYEBROW = (7, 13)
SCALE_FROM = 1.045


def build(verdict="GUILTY", charge="MANSLAUGHTER", date="19 MAY 2026",
          eyebrow="THE VERDICT", hold=110, out_dir=None, samples=64,
          dither=1.0, render=True):
    f_out = F_DATE[1] + hold
    f_end = f_out + 14
    st = G.Stage(1920, 1080, fps=30, frames=f_end, samples=samples,
                 dither=dither)

    # OVERSIZE by 24px on every side. The card takes an 11px frame shake, and a
    # plate cut exactly to 1920x1080 would expose a transparent strip along the
    # top or bottom on the shake frames - i.e. a flash of raw footage through
    # what is meant to be a solid card.
    plate = st.rect(-24, -24, 1968, 1128, color=G.GROUND, opacity=PLATE_ALPHA,
                    name="PLATE")
    plate.layer(0)
    # band opening from the centre: BOTH z edges move, opposite directions.
    plate.band(540, 540)
    plate.wipe_z([(F_SLAM[0], 540), (F_SLAM[1], 1110)], [G.EASE_IN])
    plate.wipe_z_top([(F_SLAM[0], 540), (F_SLAM[1], -30)], [G.EASE_IN])

    eb = st.text(eyebrow, font=EYEBROW_FONT, cap=EYEBROW_CAP, x=CX,
                 baseline=EYEBROW_BASE, color=G.INK, opacity=EYEBROW_ALPHA,
                 tracking=EYEBROW_TRACK, align="CENTER", name="EYEBROW")
    vd = st.text(verdict, font=VERDICT_FONT, cap=VERDICT_CAP, x=CX,
                 baseline=VERDICT_BASE, color=G.INK, align="CENTER",
                 name="VERDICT")
    ch = st.text(charge, font=CHARGE_FONT, cap=CHARGE_CAP, x=CX,
                 baseline=CHARGE_BASE, color=G.RED, align="CENTER",
                 name="CHARGE")
    ru = st.rect(CX - RULE_W // 2, RULE_Y, RULE_W, RULE_H, color=G.INK,
                 opacity=RULE_ALPHA, name="RULE")
    dt = st.text(date, font=DATE_FONT, cap=DATE_CAP, x=CX, baseline=DATE_BASE,
                 color=G.INK, opacity=DATE_ALPHA, tracking=DATE_TRACK,
                 align="CENTER", name="DATE")
    for e in (eb, vd, ch, ru, dt):
        e.layer(2)

    # 1. the verdict word: 3-frame scale-down into place. No overshoot.
    vd.scale([(F_VERDICT[0], SCALE_FROM), (F_VERDICT[1], 1.0)], [G.EASE_OUT])
    vd.opacity([(1, 0.0), (F_VERDICT[0], 0.0), (F_VERDICT[0] + 1, 1.0)])

    # 2. the frame shake IS the weight
    st.shake([F_IMPACT], amp=11.0)

    # 3. everything else resolves after the impact
    eb.band(EYEBROW_BASE - EYEBROW_CAP - 8, EYEBROW_BASE + 8)
    eb.slide_y([(1, 16), (F_EYEBROW[0], 16), (F_EYEBROW[1], 0)],
               [None, G.EASE_OUT])
    eb.opacity([(1, 0.0), (F_EYEBROW[0], 0.0),
                (F_EYEBROW[1], EYEBROW_ALPHA)], [None, G.EASE_OUT])

    # the charge wipes out from the CENTRE both ways, matching the plate's own
    # opening gesture rather than introducing a second, unrelated direction
    ch.band(CHARGE_BASE - CHARGE_CAP - 12, CHARGE_BASE + 16)
    ch.slide_y([(1, 22), (F_CHARGE[0], 22), (F_CHARGE[1], 0)],
               [None, G.EASE_OUT])
    ch.opacity([(1, 0.0), (F_CHARGE[0], 0.0), (F_CHARGE[0] + 3, 1.0)],
               [None, G.EASE_OUT])

    ru.set_wipe_x(CX - RULE_W // 2)
    ru.wipe_x([(F_RULE[0], CX - RULE_W // 2), (F_RULE[1], CX + RULE_W // 2)],
              [G.EASE_OUT])

    dt.band(DATE_BASE - DATE_CAP - 8, DATE_BASE + 10)
    dt.slide_y([(1, 14), (F_DATE[0], 14), (F_DATE[1], 0)], [None, G.EASE_OUT])
    dt.opacity([(1, 0.0), (F_DATE[0], 0.0), (F_DATE[1], DATE_ALPHA)],
               [None, G.EASE_OUT])

    for e in (plate, eb, vd, ch, ru, dt):
        e.opacity([(f_out, e.base_opacity), (f_end, 0.0)], [G.EASE_INOUT])

    out = out_dir or os.path.join(HERE, "renders", "verdict_card")
    print("VERDICT CARD  %r / %r / %r  verdict_w=%.0f  frames=1..%d"
          % (verdict, charge, date, vd.width, f_end))
    if render:
        st.render(out)
    return st, out, f_end


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build(*(a[:3] if a else []))
