"""DELIVERABLE 2 - FACT PANEL. Persistent label:value rows whose VALUES update
mid-shot, animated, never a hard cut.

    blender -b --python gfx_fact_panel.py

THE UPDATE MECHANISM - an odometer roll, hard-clipped to the row
---------------------------------------------------------------
Each row owns a stack of value strings. Only one is in the row band at a time.
On an update the outgoing value travels UP and out of the band while the
incoming value travels UP into it, both on the same 7-frame curve, so the row
reads as a physical drum rotating rather than as one label cross-fading into
another. A cross-fade would be the template move and it is unreadable at 26px
cap height over moving footage - for two thirds of the transition BOTH strings
are on screen at partial alpha.

The clipping is what makes it work, and it is why boyd_gfx carries TWO z edges
per element: the band is (row_top+30 .. row_top+70) and neither value is ever
visible outside it. No mask datablock, no compositor, no extra render layer.

The changed row is flagged by an accent underline that wipes out under the new
value over 7 frames and then fades over 14. Broadcast practice is to signal the
CHANGE, not just the new state - otherwise a viewer who blinked cannot tell
which of five rows moved.

Panel entrance: the plate's own descending edge times the rows in, +4f apart,
same "one mechanism with a cause" rule as the lower third.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- layout (px)
X0, W = 118, 430
HEAD_TOP, HEAD_H = 470, 38
BODY_TOP = HEAD_TOP + HEAD_H
ROW_H = 74
PAD_L = 22

HEAD_CAP, HEAD_TRACK = 14, 220
LABEL_CAP, LABEL_TRACK = 12, 140
VALUE_CAP = 26
LABEL_ALPHA = 0.52
PLATE_ALPHA = 0.92

HEAD_FONT = "Archivo-Bold"
LABEL_FONT = "Archivo-Medium"
VALUE_FONT = "Oswald-Medium"

ROLL = 44               # px an odometer value travels. > band height, so the
                        # outgoing string is fully clipped before it stops.

# ---------------------------------------------------------------- timing
F_HEAD = (2, 9)
F_PLATE = (6, 22)       # plate edge descends the whole body
ROW_STAGGER = 4
ROW_TRAVEL = 6
UPDATE_TRAVEL = 7
TICK_TRAVEL = 7
TICK_HOLD = 14

DEFAULT_ROWS = [("CHARGE", "MANSLAUGHTER"),
                ("PLEA", "NOT GUILTY"),
                ("BOND", "$250,000"),
                ("PRIORS", "2 FELONY"),
                ("SENTENCE", "PENDING")]

# (frame, row_index, new_value)
DEFAULT_UPDATES = [(150, 1, "GUILTY"),
                   (150, 4, "18 YEARS"),
                   (260, 2, "REVOKED")]


def build(rows=None, updates=None, frames=340, out_dir=None, samples=64,
          dither=1.0, render=True):
    rows = rows or DEFAULT_ROWS
    updates = updates or DEFAULT_UPDATES
    n = len(rows)
    body_h = ROW_H * n
    st = G.Stage(1920, 1080, fps=30, frames=frames, samples=samples,
                 dither=dither)

    head_plate = st.rect(X0, HEAD_TOP, W, HEAD_H, color=G.RED, name="HEADP")
    body_plate = st.rect(X0, BODY_TOP, W, body_h, color=G.GROUND,
                         opacity=PLATE_ALPHA, name="BODYP")

    # The plate's descending edge is authored FIRST and every row's entrance is
    # then READ OFF IT, rather than being an independent +4f stagger. With an
    # independent stagger a row can light up below the plate edge - measured at
    # f10 and f22, where the CHARGE and PRIORS dividers hung in open space
    # outside the panel. Deriving the timing from the curve makes that
    # impossible by construction, and the resulting stagger is uneven in exactly
    # the way the eased descent is, which is the point.
    body_plate.set_wipe_z(BODY_TOP)
    fc_plate = body_plate.wipe_z([(F_PLATE[0], BODY_TOP),
                                  (F_PLATE[1], BODY_TOP + body_h)],
                                 [G.EASE_OUT])

    def frame_plate_passes(y_px):
        target = st.wy(y_px)
        for f in range(F_PLATE[0], F_PLATE[1] + 2):
            if fc_plate.evaluate(f) <= target:
                return f
        return F_PLATE[1]
    head_txt = st.text("CASE FACTS", font=HEAD_FONT, cap=HEAD_CAP, x=X0 + PAD_L,
                       baseline=HEAD_TOP + 25, color=G.INK,
                       tracking=HEAD_TRACK, name="HEADT")
    head_plate.layer(0); body_plate.layer(0); head_txt.layer(3)

    # group updates by row, in frame order
    by_row = {}
    for f, r, v in sorted(updates):
        by_row.setdefault(r, []).append((f, v))

    for i, (label, value0) in enumerate(rows):
        top = BODY_TOP + i * ROW_H
        b_top, b_bot = top + 30, top + 70          # the row band
        f_in = frame_plate_passes(top + ROW_H)

        lab = st.text(label, font=LABEL_FONT, cap=LABEL_CAP, x=X0 + PAD_L,
                      baseline=top + 26, color=G.INK, opacity=LABEL_ALPHA,
                      tracking=LABEL_TRACK, name="LAB%d" % i)
        lab.layer(2)
        lab.set_wipe_x(X0)
        lab.wipe_x([(f_in, X0), (f_in + ROW_TRAVEL, X0 + W)], [G.EASE_OUT])

        if i < len(rows) - 1:
            d = st.rect(X0 + PAD_L, top + ROW_H - 1, W - PAD_L * 2, 1,
                        color=G.INK, opacity=0.10, name="DIV%d" % i)
            d.layer(1)
            d.set_wipe_x(X0)
            d.wipe_x([(f_in + 2, X0), (f_in + 2 + ROW_TRAVEL, X0 + W)],
                     [G.EASE_OUT])

        # ---- the value stack for this row -------------------------------
        seq = [(None, value0)] + by_row.get(i, [])
        elems = []
        for j, (f_upd, txt) in enumerate(seq):
            e = st.text(txt, font=VALUE_FONT, cap=VALUE_CAP, x=X0 + PAD_L,
                        baseline=top + 62, color=G.INK,
                        name="VAL%d_%d" % (i, j))
            e.layer(2)
            e.band(b_top, b_bot)       # STATIC hard clip: the drum housing
            elems.append(e)

        # v0 is revealed with the row; later values are revealed by the roll
        elems[0].set_wipe_x(X0)
        elems[0].wipe_x([(f_in, X0), (f_in + ROW_TRAVEL, X0 + W)], [G.EASE_OUT])

        for j in range(1, len(elems)):
            f_upd = seq[j][0]
            # incoming: from BELOW the band up into place
            elems[j].slide_y([(1, ROLL), (f_upd, ROLL), (f_upd + UPDATE_TRAVEL, 0)],
                             [None, G.EASE_OUT])
            # outgoing: from place up and out of the band
            elems[j - 1].slide_y(
                [(f_upd, 0), (f_upd + UPDATE_TRAVEL, -ROLL)], [G.EASE_OUT])

            # accent underline: signals WHICH row changed
            tick = st.rect(X0 + PAD_L, top + 68, elems[j].width + 6, 3,
                           color=G.RED, name="TICK%d_%d" % (i, j))
            tick.layer(3)
            tick.set_wipe_x(X0 + PAD_L)
            tick.wipe_x([(f_upd + 2, X0 + PAD_L),
                         (f_upd + 2 + TICK_TRAVEL,
                          X0 + PAD_L + elems[j].width + 6)], [G.EASE_OUT])
            tick.opacity([(f_upd, 1.0),
                          (f_upd + TICK_TRAVEL + TICK_HOLD, 1.0),
                          (f_upd + TICK_TRAVEL + TICK_HOLD + 12, 0.0)],
                         [None, G.EASE_INOUT])

    # header and plate entrances
    head_plate.set_wipe_x(X0)
    head_txt.set_wipe_x(X0)
    for e, lead in ((head_plate, 0), (head_txt, 18)):
        e.wipe_x([(F_HEAD[0], X0), (F_HEAD[1], X0 + W - lead)], [G.EASE_OUT])
    out = out_dir or os.path.join(HERE, "renders", "fact_panel")
    print("FACT PANEL  rows=%d  body=%dpx  updates=%s  frames=1..%d"
          % (n, body_h, updates, frames))
    if render:
        st.render(out)
    return st, out, frames


if __name__ == "__main__":
    build()
