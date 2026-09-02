"""The measurement that decides whether Judge Boyd reads PALE against her plate.

Nathan, 2026-08-29: "in sanchez thumbnail boyd still looks so bright and pale,
same thing in offer up ... thats slop".

This is a BETWEEN-LAYER measurement and every number here is taken INSIDE her
matte, never on the canvas. The reason is measured: whole-canvas luma does not
rank-order with his verdict at all -- OFFERUP shipped at 114.2, DARKER than both
files he approved (Thompson 124.9, CARTHIEF 118.6), and he still called it pale.
Whole-canvas dynamic range is a full 0..255 on all four files including both
rejects, because the PLATE supplies the deep blacks; her layer floats above them
and no canvas-level gate can see it.

The four quantities, in the order they discriminate:

  black_floor   1st-percentile luma inside her matte. THE primary metric: it
                rank-orders his verdict perfectly with no overlap.
                    THOMPSON 3.7  CARTHIEF 13.1 | SANCHEZ 36.1  OFFERUP 41.9
                Gate: <= 15.
  skin_a        Lab a* of her skin. "Pale" is loss of RED, not gain of
                brightness -- her skin LIGHTNESS interleaves across his verdicts
                and is therefore not the variable.
                    THOMPSON 17.6  CARTHIEF 18.8 | SANCHEZ 9.2  OFFERUP 9.8
  her_minus_ring  her mean L* minus the L* of the plate ring 8-70px around her.
                    THOMPSON -17.7  CARTHIEF -21.8 | SANCHEZ +2.0  OFFERUP +16.0
  skin_dluma    her skin mean luma minus the plate people's skin mean luma.
                    liked -5.0 / +16.7 | rejected +23.4 / +25.9.  Gate: <= +15.

Also reported because the OFFERUP shrink shows up in them: her share of the
canvas, and her L* p5-p95 range (OFFERUP 52.6 against 75-82 for the other
three -- 71% of her pixels inside one 30-point band, which is why she reads as
a flat grey sticker rather than a photograph).
"""
from __future__ import annotations

import numpy as np

BLACK_FLOOR_MAX = 18.0      # approved 0.6 / 14.2 ; rejected 37.2 / 23.9
SKIN_A_MIN = 13.0           # approved 17.6 / 18.3 ; rejected 9.0 / 9.7

# her_minus_ring is REPORTED BUT NOT GATED. It separates his four verdicts
# cleanly (-14.4/-16.8 approved against +4.9/+17.0 rejected) but it is
# CONFOUNDED with wardrobe and with how much of her the crop holds: in both
# files he approved she is in a BLACK ROBE that fills a third of her matte, and
# in SANCHEZ she is in a light grey blazer and white collar. Gating on it would
# order the builder to darken a light jacket until it stopped being a light
# jacket, which is a lie about the picture rather than an integration fix. The
# black floor measures the same defect without the confound, because her hair
# is the darkest structure in every crop regardless of what she is wearing.

# skin_dluma is REPORTED BUT NOT GATED, and that is a correction to the
# diagnosis rather than an oversight. The diagnosis measured it on hand-placed
# boxes and got approved -5.0/+16.7 against rejected +23.4/+25.9. Re-measured
# here over the whole matte it INVERTS - approved +15.2/+20.3 against rejected
# +7.2/+14.0 - so it would fail both files Nathan likes and pass both he
# rejects. A metric that flips sign when the region changes is not measuring his
# taste, so it stays a note.


def luma(rgb: np.ndarray) -> np.ndarray:
    a = rgb.astype(np.float32)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    """YCrCb skin, the same window the diagnosis used (133<=Cr<=180, 77<=Cb<=127)."""
    import cv2
    y = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2YCrCb)
    cr, cb = y[..., 1], y[..., 2]
    return (cr >= 133) & (cr <= 180) & (cb >= 77) & (cb <= 127)


def measure(rgb: np.ndarray, jmask: np.ndarray, type_top: int = 150) -> dict:
    """rgb HxWx3 uint8, jmask HxW bool/uint8 = Judge Boyd's layer in canvas space.

    type_top excludes the headline band: the type is a graphic and its black
    stroke would supply a fake black floor.
    """
    import cv2
    import scipy.ndimage as nd
    H, W = rgb.shape[:2]
    her = (np.asarray(jmask) > 24) if jmask.dtype != bool else jmask.copy()
    her[:type_top, :] = False
    core = nd.binary_erosion(her, iterations=4)
    if core.sum() < 500:
        core = her
    L = luma(rgb)
    lab = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    Ls, As = lab[..., 0] * 100.0 / 255.0, lab[..., 1] - 128.0

    # the plate ring 8..70px around her, which is what she is judged against
    ring = nd.binary_dilation(her, iterations=70) & ~nd.binary_dilation(her, iterations=8)
    ring[:type_top, :] = False

    sk = skin_mask(rgb)
    her_skin = core & sk
    plate_skin = sk & ~nd.binary_dilation(her, iterations=6)
    plate_skin[:type_top, :] = False

    def p(m, arr, q):
        return float(np.percentile(arr[m], q)) if m.sum() > 50 else float("nan")

    out = {
        "black_floor": p(core, L, 1),
        "her_L_mean": float(Ls[core].mean()),
        "ring_L_mean": float(Ls[ring].mean()) if ring.sum() > 50 else float("nan"),
        "her_L_p5": p(core, Ls, 5),
        "her_L_p95": p(core, Ls, 95),
        "skin_a": float(As[her_skin].mean()) if her_skin.sum() > 50 else float("nan"),
        "plate_skin_a": float(As[plate_skin].mean()) if plate_skin.sum() > 50 else float("nan"),
        "her_skin_luma": float(L[her_skin].mean()) if her_skin.sum() > 50 else float("nan"),
        "plate_skin_luma": float(L[plate_skin].mean()) if plate_skin.sum() > 50 else float("nan"),
        "her_px_pct": 100.0 * float(her.sum()) / (H * W),
        "her_below_L30_pct": 100.0 * float((Ls[core] < 30).mean()),
    }
    out["her_minus_ring"] = out["her_L_mean"] - out["ring_L_mean"]
    out["her_L_range"] = out["her_L_p95"] - out["her_L_p5"]
    out["skin_dluma"] = out["her_skin_luma"] - out["plate_skin_luma"]
    return out


def verdict(m: dict) -> list[str]:
    """The gates, each calibrated against a file he approved AND one he rejected."""
    bad = []
    if not np.isnan(m["black_floor"]) and m["black_floor"] > BLACK_FLOOR_MAX:
        bad.append(f"PALE black floor {m['black_floor']:.1f} > {BLACK_FLOOR_MAX:.0f} "
                   f"(approved 0.6/14.2, rejected 37.2/23.9) - her layer is "
                   f"floating above the plate's blacks")
    if not np.isnan(m["skin_a"]) and m["skin_a"] < SKIN_A_MIN:
        bad.append(f"PALE her skin a* {m['skin_a']:.1f} < {SKIN_A_MIN:.0f} "
                   f"(approved 17.6/18.3, rejected 9.0/9.7) - red drained")
    return bad


def fmt(name: str, m: dict) -> str:
    return (f"{name:26} blackfloor {m['black_floor']:6.1f}   "
            f"skin a* {m['skin_a']:5.1f}   her-ring L* {m['her_minus_ring']:+6.1f}   "
            f"skin dluma {m['skin_dluma']:+6.1f}   her {m['her_px_pct']:5.2f}% of canvas   "
            f"L* range {m['her_L_range']:5.1f}")
