"""DELIVERABLE 1 - LOWER THIRD. Defendant name + charge. In, hold, out.

    blender -b --python gfx_lower_third.py -- "MARCUS D. BOYD" "MANSLAUGHTER, 2ND DEGREE"

Renders an RGBA PNG sequence to renders/lower_third/.

THE MECHANISM, and why it is not the template one
-------------------------------------------------
The template lower third fades in, or slides in from the left, and the text
fades up on top of it. That is two events that co-occur. Here the accent rule
strikes down first, the plate wipes out FROM that rule, and the name's own wipe
edge is the plate's edge minus the padding - so the plate is what uncovers the
name. One event with a cause. Same reasoning that picked the sting concept.

Concretely, all four wipe edges are the same animation offset in time and space:

    f2 ->  f6   accent rule grows DOWN from the top of the plate  (4f)
    f5 -> f12   tier-1 plate edge  118 -> 118+W1                  (7f, easeOut)
    f5 -> f12   name edge          plate edge - PAD_L             (identical curve)
    f10 -> f17  tier-2 plate edge                                 (+5f stagger)
    f10 -> f17  charge edge        tier-2 edge - PAD_L
    hold
    exit: reverse wipe, 9f, tier 2 leads tier 1 by 3f, EASE_OUT_HARD

No overshoot anywhere - 0 of 7 measured broadcast references overshoot on a
settle. No motion blur - the two pure-letterform references render a 3px edge
whether moving 31 px/frame or standing still.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- layout (px)
X0 = 118            # left edge. 1080 title-safe is 96; 118 clears it.
PAD_L = 30          # plate edge -> text left
RULE_W = 10         # accent rule
T1_TOP, T1_H = 762, 84
T2_TOP, T2_H = 846, 44

NAME_CAP = 42
NAME_BASE = T1_TOP + 60           # 822
CHARGE_CAP = 16
CHARGE_BASE = T2_TOP + 30         # 876
CHARGE_TRACK = 130                # 1/1000 em

PLATE_ALPHA = 0.93                # footage reads through, still legible
NAME_FONT = "Anton"
CHARGE_FONT = "Archivo-SemiCond-SemiBold"

# ---------------------------------------------------------------- timing (30fps)
F_RULE = (2, 6)
F_T1 = (5, 12)
F_T2 = (10, 17)
HOLD_F = 105                      # 3.5 s of readable hold
F_OUT2 = None                     # computed
FADE_OUT = 9


def build(name_text, charge_text, hold=HOLD_F, out_dir=None, samples=64,
          dither=1.0, render=True):
    f_out = F_T2[1] + hold
    f_end = f_out + FADE_OUT + 4

    st = G.Stage(1920, 1080, fps=30, frames=f_end, samples=samples,
                 dither=dither)

    # measure the text first so the plates are sized to their content
    name = st.text(name_text, font=NAME_FONT, cap=NAME_CAP,
                   x=X0 + RULE_W + PAD_L, baseline=NAME_BASE, color=G.INK,
                   name="NAME")
    charge = st.text(charge_text, font=CHARGE_FONT, cap=CHARGE_CAP,
                     x=X0 + RULE_W + PAD_L, baseline=CHARGE_BASE, color=G.INK,
                     tracking=CHARGE_TRACK, name="CHARGE")

    W1 = RULE_W + PAD_L + name.width + PAD_L + 18
    W2 = RULE_W + PAD_L + charge.width + PAD_L

    p1 = st.rect(X0, T1_TOP, W1, T1_H, color=G.GROUND, opacity=PLATE_ALPHA,
                 name="PLATE1")
    p2 = st.rect(X0, T2_TOP, W2, T2_H, color=G.RED, opacity=1.0, name="PLATE2")
    rule = st.rect(X0, T1_TOP, RULE_W, T1_H + T2_H, color=G.RED, name="RULE")
    hair = st.rect(X0 + RULE_W, T1_TOP + T1_H - 1, W1 - RULE_W, 1,
                   color=G.INK, opacity=0.14, name="HAIR")

    # The text has to be MEASURED before the plates can be sized to it, so it
    # is authored first and its stacking order is set explicitly afterwards.
    for e, n in ((p1, 0), (p2, 0), (rule, 1), (hair, 1), (name, 2), (charge, 2)):
        e.layer(n)

    # ---------------------------------------------------------------- animate
    # 1. the rule strikes DOWN. Its clip_z edge travels from the plate top to
    #    the plate bottom; nothing translates, so there is no smear.
    rule.set_wipe_z(T1_TOP)
    rule.wipe_z([(F_RULE[0], T1_TOP), (F_RULE[1], T1_TOP + T1_H + T2_H)],
                [G.EASE_OUT])

    # 2/3. plate 1 wipes right, and the NAME's edge is the same curve shifted
    #      left by LEAD: the plate uncovers the name.
    #      LEAD must be < PAD_L or the text's own right edge gets cut off at the
    #      end of the wipe - the first build clipped 8px off "SECOND DEGREE"
    #      because the offset was -(PAD_L + 8) instead of -(PAD_L - 12).
    LEAD = PAD_L - 12                      # 18 px
    tier1 = ((p1, 0), (hair, 0), (name, -LEAD))
    tier2 = ((p2, 0), (charge, -LEAD))

    # CLOSED means X0 - 2, not X0 + RULE_W. Starting the wipe at the rule's
    # right edge leaves a 10px stub of plate on screen from frame 1 until the
    # wipe begins - measured at f1 as 12 columns of #15181D at alpha 237, i.e.
    # the plate, four frames before the rule has even drawn.
    CLOSED = X0 - 2
    for e, off in tier1:
        e.set_wipe_x(CLOSED)
        e.wipe_x([(F_T1[0], CLOSED),
                  (F_T1[1], X0 + W1 + off)], [G.EASE_OUT])

    # 4/5. tier 2, +5 frame stagger
    for e, off in tier2:
        e.set_wipe_x(CLOSED)
        e.wipe_x([(F_T2[0], CLOSED),
                  (F_T2[1], X0 + W2 + off)], [G.EASE_OUT])

    # 6. exit. Reverse wipe, faster, tier 2 leads by 3 - the reverse of the
    #    entrance stagger, so it reads as the same object retracting.
    for e, off in tier2:
        e.wipe_x([(f_out - 3, X0 + W2 + off),
                  (f_out - 3 + FADE_OUT, CLOSED)], [G.EASE_OUT_HARD])
    for e, off in tier1:
        e.wipe_x([(f_out, X0 + W1 + off),
                  (f_out + FADE_OUT, CLOSED)], [G.EASE_OUT_HARD])
    rule.wipe_z([(f_out + 4, T1_TOP + T1_H + T2_H), (f_out + FADE_OUT, T1_TOP)],
                [G.EASE_OUT_HARD])

    out = out_dir or os.path.join(HERE, "renders", "lower_third")
    print("LOWER THIRD  name_w=%.1f charge_w=%.1f  W1=%.0f W2=%.0f  frames=1..%d"
          % (name.width, charge.width, W1, W2, f_end))
    print("  in %d-%d/%d-%d   hold to %d   out %d-%d"
          % (F_T1[0], F_T1[1], F_T2[0], F_T2[1], f_out, f_out, f_out + FADE_OUT))
    if render:
        st.render(out)
    return st, out, f_end


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build(a[0] if a else "MARCUS D. BOYD",
          a[1] if len(a) > 1 else "MANSLAUGHTER, SECOND DEGREE")
