"""One lower-third spec, shared verbatim by all three implementations.

The comparison is only meaningful if the three renderers are drawing the SAME
picture, so geometry, colour, cap heights and the easing curve all live here and
nothing downstream is allowed to invent its own.

Easing is easeOutCubic rather than the kit's CSS cubic-bezier(0.33,1,0.68,1),
because ffmpeg has to express the ease as a closed-form arithmetic expression
and cannot evaluate an arbitrary bezier. Holding the ease identical is worth
more to the comparison than holding it optimal - and the fact that ffmpeg forces
this substitution is itself one of the findings.
"""
import os

FONTS_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fonts_static")
FONTS_SRC = r"C:\Users\natha\Projects\boyd-clips\assets\fonts"

W, H, FPS = 1920, 1080, 30
FRAMES = 135

GROUND_HEX, INK_HEX, RED_HEX = "15181D", "F2EEE3", "D42B2B"

X0 = 118
RULE_W = 10
PAD_L = 30
T1_TOP, T1_H = 762, 84
T2_TOP, T2_H = 846, 44
W1, W2 = 388, 553                 # fixed here so all three agree exactly
PLATE_ALPHA = 0.93

NAME = "MARCUS D. BOYD"
CHARGE = "MANSLAUGHTER, SECOND DEGREE"
NAME_CAP, NAME_BASE = 42, 822
CHARGE_CAP, CHARGE_BASE = 16, 876
CHARGE_TRACK = 130                # 1/1000 em

NAME_FONT = os.path.join(FONTS_SRC, "Anton-Regular.ttf")
CHARGE_FONT = os.path.join(FONTS_STATIC, "Archivo-SemiCond-SemiBold.ttf")

# cap/upm read from the font files with fontTools (probe output in
# GRAPHICS-SPEC.md). FreeType-based renderers (ffmpeg, PIL) size by EM, so
# em_px = cap_px / cap_per_em. Blender does NOT - see boyd_gfx rule 4.
NAME_CAP_PER_EM = 1760 / 2048.0       # Anton
CHARGE_CAP_PER_EM = 686 / 1000.0      # Archivo

LEAD = PAD_L - 12
F_RULE = (2, 6)
F_T1 = (5, 12)
F_T2 = (10, 17)
F_OUT = 122
FADE_OUT = 9
CLOSED = X0 - 2


def ease_out_cubic(u):
    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
    return 1.0 - (1.0 - u) ** 3


def ramp(frame, f0, f1, v0, v1):
    if frame <= f0:
        return v0
    if frame >= f1:
        return v1
    return v0 + (v1 - v0) * ease_out_cubic((frame - f0) / float(f1 - f0))


def edge_tier1(frame):
    """Screen-x of the tier-1 wipe edge at this frame."""
    if frame < F_OUT:
        return ramp(frame, F_T1[0], F_T1[1], CLOSED, X0 + W1)
    return ramp(frame, F_OUT, F_OUT + FADE_OUT, X0 + W1, CLOSED)


def edge_tier2(frame):
    if frame < F_OUT - 3:
        return ramp(frame, F_T2[0], F_T2[1], CLOSED, X0 + W2)
    return ramp(frame, F_OUT - 3, F_OUT - 3 + FADE_OUT, X0 + W2, CLOSED)


def edge_rule(frame):
    """Screen-y of the accent rule's descending edge."""
    bot = T1_TOP + T1_H + T2_H
    if frame < F_OUT + 4:
        return ramp(frame, F_RULE[0], F_RULE[1], T1_TOP, bot)
    return ramp(frame, F_OUT + 4, F_OUT + FADE_OUT, bot, T1_TOP)


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
