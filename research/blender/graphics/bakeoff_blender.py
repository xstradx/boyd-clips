"""Implementation A: Blender 5.0.1 + boyd_gfx. Same lower third as bakeoff_spec.

    blender -b --python bakeoff_blender.py

easeOutCubic, 1-(1-t)^3, is EXACTLY cubic-bezier(1/3, 1, 2/3, 1) - solve
3y1*t + (3y2-6y1)*t^2 + (3y1-3y2+1)*t^3 == 3t-3t^2+t^3 and you get y1=y2=1,
with x1=1/3, x2=2/3 to keep the parameter linear in time. So all three
implementations run the identical curve and the comparison is exact rather than
approximate. (It also means boyd_gfx's EASE_OUT = (0.33, 1.0, 0.68, 1.0) was
already easeOutCubic to two decimals.)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_spec as S
import boyd_gfx as G

HERE = os.path.dirname(os.path.abspath(__file__))
EASE = (1.0 / 3.0, 1.0, 2.0 / 3.0, 1.0)


def build(outdir=None, samples=64):
    outdir = outdir or os.path.join(HERE, "renders", "bakeoff_blender")
    st = G.Stage(S.W, S.H, fps=S.FPS, frames=S.FRAMES, samples=samples,
                 dither=1.0)

    name = st.text(S.NAME, font="Anton", cap=S.NAME_CAP,
                   x=S.X0 + S.RULE_W + S.PAD_L, baseline=S.NAME_BASE,
                   color=G.INK, name="NAME")
    charge = st.text(S.CHARGE, font="Archivo-SemiCond-SemiBold",
                     cap=S.CHARGE_CAP, x=S.X0 + S.RULE_W + S.PAD_L,
                     baseline=S.CHARGE_BASE, color=G.INK,
                     tracking=S.CHARGE_TRACK, name="CHARGE")
    p1 = st.rect(S.X0, S.T1_TOP, S.W1, S.T1_H, color=G.GROUND,
                 opacity=S.PLATE_ALPHA, name="PLATE1")
    p2 = st.rect(S.X0, S.T2_TOP, S.W2, S.T2_H, color=G.RED, name="PLATE2")
    rule = st.rect(S.X0, S.T1_TOP, S.RULE_W, S.T1_H + S.T2_H, color=G.RED,
                   name="RULE")
    hair = st.rect(S.X0 + S.RULE_W, S.T1_TOP + S.T1_H - 1, S.W1 - S.RULE_W, 1,
                   color=G.INK, opacity=0.14, name="HAIR")
    for e, n in ((p1, 0), (p2, 0), (rule, 1), (hair, 1), (name, 2), (charge, 2)):
        e.layer(n)

    rule.set_wipe_z(S.T1_TOP)
    bot = S.T1_TOP + S.T1_H + S.T2_H
    rule.wipe_z([(S.F_RULE[0], S.T1_TOP), (S.F_RULE[1], bot)], [EASE])
    rule.wipe_z([(S.F_OUT + 4, bot), (S.F_OUT + S.FADE_OUT, S.T1_TOP)], [EASE])

    tier1 = ((p1, 0), (hair, 0), (name, -S.LEAD))
    tier2 = ((p2, 0), (charge, -S.LEAD))
    for e, off in tier1:
        e.set_wipe_x(S.CLOSED)
        e.wipe_x([(S.F_T1[0], S.CLOSED + off),
                  (S.F_T1[1], S.X0 + S.W1 + off)], [EASE])
        e.wipe_x([(S.F_OUT, S.X0 + S.W1 + off),
                  (S.F_OUT + S.FADE_OUT, S.CLOSED + off)], [EASE])
    for e, off in tier2:
        e.set_wipe_x(S.CLOSED)
        e.wipe_x([(S.F_T2[0], S.CLOSED + off),
                  (S.F_T2[1], S.X0 + S.W2 + off)], [EASE])
        e.wipe_x([(S.F_OUT - 3, S.X0 + S.W2 + off),
                  (S.F_OUT - 3 + S.FADE_OUT, S.CLOSED + off)], [EASE])

    t0 = time.perf_counter()
    st.render(outdir)
    dt = time.perf_counter() - t0
    print("BLENDER %d frames in %.2fs  (%.4f s/frame)  -> %s"
          % (S.FRAMES, dt, dt / S.FRAMES, outdir))
    print("BAKEOFF_SECONDS %.4f" % dt)
    return dt


if __name__ == "__main__":
    build()
