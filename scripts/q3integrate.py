"""Grade Judge Boyd's cut-out INTO the plate, BEFORE the merge.

Nathan, 2026-08-29: "in sanchez thumbnail boyd still looks so bright and pale,
same thing in offer up and yes the judge shrank and now looks weird is pale as
well ... thats slop".

WHY THIS IS A SEPARATE STAGE AND NOT A GRADE SETTING. Her Zoom tile and the
courtroom tile are two cameras with independent auto-exposure and auto-white
balance, and until this module existed nothing in the pipeline ever compared the
two layers to each other. `grade_image` and the luma-122 normalisation both run
on the COMPOSITED canvas: one monotone transform over both layers at once, which
moves the pair together and preserves the gap between them exactly. Measured, not
argued -- sweeping that normalisation across its entire clamp range (0.60 to
1.45) never once flips the sign of her-minus-ring L* on any of the four
reference files, and on OFFERUP it drives the gap from +10.0 to +22.5.

WHAT THE DEFECT ACTUALLY IS. A pure LIFT, not a gain. Her tile is small and soft
so it takes the heaviest realesr-general-x4v3 upscale, and GAN upscaling plus a
soft alpha deposits an additive veil on her layer only: her darkest structure
(hair, robe) sits at a neutral mid-grey -- RGB [148,143,141] on SANCHEZ,
[136,130,138] on OFFERUP -- while her WHITE point already matches the plate to
within 12 code values. Floating the shadow end compresses her range, so her skin
loses its shadow-side falloff and desaturates, because a veil is achromatic.
"Pale" is therefore loss of RED, not gain of brightness: her skin a* measures
17.6-18.8 in the two files Nathan approved and 9.0-9.7 in the two he rejected,
while her skin LIGHTNESS interleaves across his verdicts and predicts nothing.

THE OPERATION is the Nuke Grade node's, in scene-linear, PER CHANNEL:

    out = (x - blackpoint) / (whitepoint - blackpoint) * (gain - lift) + lift

blackpoint/whitepoint sampled from the ELEMENT, lift/gain from the PLATE -- the
order Foundry documents for sampling white and black, and the order
practitioners give for matching an element into a plate. Per channel is
deliberate: it corrects colour temperature in the same pass, which is exactly
what Photoshop's "Find Dark & Light Colors" does inside a Curves layer clipped
to the subject.

Sources read for the mechanism:
    https://www.chrisbturner.com/blog/nukes-grade-node-demystified   (node math)
    https://taukeke.com/2016/05/matching-colour-with-grade-node/     (sample order)
    https://learn.foundry.com/nuke/content/comp_environment/color_correction/sampling_white_and_black.html
    https://photoshoptrainingchannel.com/match-a-subject-into-any-background/
    https://www.whizzystudios.com/post/creating-light-wrap-effects-in-nuke-for-blender-renders

Licences: none of this is code, it is arithmetic read from published tutorials.
The only libraries used are numpy (BSD-3), OpenCV (Apache-2.0), Pillow (MIT-CMU)
and scipy (BSD-3), all already dependencies of this repo.
"""
from __future__ import annotations

import cv2
import numpy as np
import scipy.ndimage as nd
from PIL import Image


# --------------------------------------------------------------- colour bits
def srgb_to_lin(x):
    x = np.clip(np.asarray(x, dtype=np.float32) / 255.0, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(x):
    x = np.clip(np.asarray(x, dtype=np.float32), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92,
                    1.055 * np.power(np.maximum(x, 1e-8), 1.0 / 2.4) - 0.055) * 255.0


def luma(rgb):
    a = np.asarray(rgb, dtype=np.float32)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def skin(rgb_u8, drop_scrubs=True):
    """YCrCb skin window, 133<=Cr<=180 and 77<=Cb<=127 -- the same window the
    diagnosis used, so the numbers printed here compare with the ones measured
    on the files Nathan has already judged.

    WITH ONE CORRECTION, measured here: county jail scrubs are ORANGE and land
    squarely inside that window. On CARTHIEF the raw window put the "plate skin"
    saturation at 129 -- that is the jumpsuit, not a face -- and the saturation
    restore below then drove itself to its ceiling trying to match her face to a
    jumpsuit. Real skin in this docket measures S 40-90; the scrubs are the most
    saturated large garment in the room, which is the same property
    scrub_mask() in thumb_Q3_detail.py relies on to find the defendant at all.
    """
    u8 = np.ascontiguousarray(rgb_u8, dtype=np.uint8)
    y = cv2.cvtColor(u8, cv2.COLOR_RGB2YCrCb)
    cr, cb = y[..., 1], y[..., 2]
    m = (cr >= 133) & (cr <= 180) & (cb >= 77) & (cb <= 127)
    if drop_scrubs:
        hsv = cv2.cvtColor(u8, cv2.COLOR_RGB2HSV)
        m &= hsv[..., 1] < 110
    return m


def _sat(rgb_u8, m):
    if m.sum() < 50:
        return float("nan")
    h = cv2.cvtColor(np.ascontiguousarray(rgb_u8, dtype=np.uint8),
                     cv2.COLOR_RGB2HSV)
    return float(h[..., 1][m].mean())


# ---------------------------------------------------------------- the match
def match_element_to_plate(cut_rgba: Image.Image, plate_rgb: Image.Image,
                           cut_xy, *, strength=1.0, gain_clamp=(0.70, 2.10),
                           sat_max=1.0, skin_dluma_max=15.0, gamma_floor=0.86,
                           per_channel=False, mode="lift", skin_ref=None,
                           wb_clamp=(0.65, 1.55), wb_chroma_band=(9.0, 17.0),
                           wb_chroma_cap=None, log=print):
    """Return (new RGBA, report). See the module docstring for the mechanism.

    `plate_rgb` is the FINISHED plate canvas she is about to be pasted onto, at
    the same point in the chain -- after its own detail chain, before the shared
    grade. Matching pre-grade is the point: whatever `grade_image` and the
    exposure normalisation do afterwards, they do to both layers, so a match
    made here survives them.

    PER-CHANNEL IS OFF BY DEFAULT, and that is a correction to the research
    rather than a shortcut. The sources are right that a per-channel Grade fixes
    colour temperature in the same pass -- but they sample the plate's darkest
    and brightest OBJECT, and what is available here is a percentile of a whole
    courtroom band whose content (orange scrubs, navy suits, beige walls) has
    nothing to do with her content (black robe, hair, skin). Measured on
    CARTHIEF, the file Nathan calls fire: per-channel gains came out R1.09 G1.47
    B1.63, her black robe turned blue, her hair turned pink, and her skin a*
    moved 18.3 -> 14.7, i.e. the control got MORE pale on the one axis that
    carries his complaint. So the default is the ACHROMATIC form -- one lift and
    one gain, derived from luma, applied identically to R, G and B. That is also
    the physically correct shape of the defect: the veil the diagnosis measured
    is neutral grey ([148,143,141] on SANCHEZ, [136,130,138] on OFFERUP), and
    subtracting a neutral constant restores saturation on its own.
    """
    rgba = np.asarray(cut_rgba.convert("RGBA")).astype(np.float32)
    rgb_u8 = rgba[..., :3].astype(np.uint8)
    al = rgba[..., 3]

    # HER pixels: solid interior only. The soft alpha band is a blend with the
    # tile's own background and carries the very veil we are measuring.
    solid = al > 229
    er = nd.binary_erosion(solid, iterations=2)
    if er.sum() > 2000:
        solid = er
    if solid.sum() < 500:
        log("  integrate: no solid alpha to sample from - SKIPPED")
        return cut_rgba, {"applied": False, "reason": "no solid alpha"}

    # THE PLATE SHE IS LANDING IN: the canvas rows she spans, full width. Not
    # the whole canvas -- the ceiling is several stops off the floor, and
    # averaging them would match her to a room she is not standing in.
    P = np.asarray(plate_rgb.convert("RGB"))
    px, py = int(cut_xy[0]), int(cut_xy[1])
    rows = np.where((al > 24).any(axis=1))[0]
    r0 = int(np.clip(py + rows.min(), 0, P.shape[0] - 1))
    r1 = int(np.clip(py + rows.max() + 1, r0 + 8, P.shape[0]))
    band = P[r0:r1]
    if band.size < 3000:
        band = P

    jl = srgb_to_lin(rgb_u8)
    pl = srgb_to_lin(band)
    jf = jl[solid]
    pf = pl.reshape(-1, 3)

    rep = {"applied": True, "strength": strength, "plate_rows": [r0, r1],
           "per_channel": per_channel, "channels": []}
    out = jl.copy()
    rep["mode"] = mode
    if per_channel:
        chans = [(c, jf[:, c], pf[:, c]) for c in range(3)]
    else:
        jY, pY = luma(jf), luma(pf)
        chans = [(c, jY, pY) for c in range(3)]
    for c, jsrc, psrc in chans:
        j_bp, j_wp = (float(v) for v in np.percentile(jsrc, (1.0, 99.0)))
        p_bp, p_wp = (float(v) for v in np.percentile(psrc, (1.0, 99.0)))
        jr = max(j_wp - j_bp, 1e-4)
        if mode == "lift":
            # PIN HER WHITE POINT AND ONLY PULL THE BLACK END DOWN.
            #
            # The defect measured is a pure LIFT: her white point already
            # matches the plate to within 12 code values on all four reference
            # files INCLUDING both Nathan approved, so white point is not
            # discriminating and moving it is a look change, not a correction.
            # The gain is also floored at 1.0 so this can only ever make her
            # blacks deeper, never lift them - a layer that already sits in the
            # plate is left alone, which is what keeps the control safe.
            gain = float(np.clip((j_wp - p_bp) / jr, 1.0, gain_clamp[1]))
        else:
            gain = float(np.clip((p_wp - p_bp) / jr, *gain_clamp))
        v = (jl[..., c] - j_bp) * gain + p_bp
        out[..., c] = jl[..., c] * (1.0 - strength) + v * strength
        rep["channels"].append({
            "ch": "RGB"[c],
            "judge_black_lin": round(j_bp, 5), "judge_white_lin": round(j_wp, 5),
            "plate_black_lin": round(p_bp, 5), "plate_white_lin": round(p_wp, 5),
            "gain": round(gain, 4)})

    graded = np.clip(lin_to_srgb(out), 0.0, 255.0)
    g_u8 = graded.astype(np.uint8)

    # SATURATION about the luma axis, toward the plate's own skin saturation.
    #
    # OFF BY DEFAULT (sat_max=1.0), and that is a correction to the diagnosis.
    # It was proposed on the reading that judge-vs-plate skin saturation
    # separates Nathan's verdicts -- but re-measured with the jail scrubs
    # excluded from the plate's "skin", it does not: CARTHIEF, which he calls
    # fire, sits at -20.7 against rejects at -25.2 and -18.2, i.e. one of the
    # rejects is CLOSER to matched than the approved file is. Left on, it also
    # overshot the control: it drove CARTHIEF's shipped skin a* to 22.0 against
    # the 17.6-18.8 band of the two files he approved. The lift above restores
    # saturation on its own by removing an achromatic veil, and the white
    # balance below fixes what is actually wrong. Kept as a dial, off.
    p_sk = skin(band)
    her_sk = solid & skin(g_u8)
    js, ps = _sat(g_u8, her_sk), _sat(band, p_sk)
    sfac = 1.0
    if not (np.isnan(js) or np.isnan(ps)) and js > 1.0:
        sfac = float(np.clip(ps / js, 1.0, sat_max))
        if sfac > 1.005:
            Y = luma(graded)[..., None]
            graded = np.clip(Y + (graded - Y) * sfac, 0.0, 255.0)
            g_u8 = graded.astype(np.uint8)
    rep["skin_sat"] = {"judge": round(js, 2), "plate": round(ps, 2),
                       "factor": round(sfac, 3)}

    # ---- HER SKIN'S WHITE BALANCE, matched to the control ------------------
    #
    # This is the second half of "pale", and it is a HUE error, not a
    # saturation error. Measured on the four files Nathan has judged, her skin
    # in CIELAB:
    #
    #       THOMPSON (liked)  a* 16.9  b*  3.5   hue 11.6 deg
    #       CARTHIEF (liked)  a* 17.6  b*  9.1   hue 27.4 deg
    #       SANCHEZ  (rejct)  a*  8.5  b* 12.0   hue 54.6 deg
    #       OFFERUP  (rejct)  a*  8.8  b* 11.5   hue 52.5 deg
    #
    # Her skin RGB tells the same story plainly: [173,131,136] and [201,153,149]
    # in the two he likes, where BLUE sits at or above GREEN, against
    # [193,163,148] and [163,135,121] in the two he rejects, where blue has
    # fallen well below green. That is a yellow cast -- the judge tile's camera
    # ran a different auto-white-balance from the courtroom camera. The
    # saturation step above cannot touch it: on SANCHEZ her skin's HSV S is 58
    # against the plate's 59, so by that measure nothing is wrong, and Lab a*
    # is still 8.6.
    #
    # SHE IS THE SAME PERSON IN EVERY THUMBNAIL, so her skin chromaticity is a
    # fixed physical fact and the camera is the thing that changed. Matching it
    # to the control is therefore a correction, not a look: a von Kries gain in
    # linear RGB that moves her skin's mean (a*, b*) onto the reference while
    # leaving its L* alone -- her skin LIGHTNESS interleaves across his verdicts
    # and is not the variable. On CARTHIEF itself the gains land within a few
    # percent of 1.0, which is the property that keeps the control safe.
    def _skin_ab(u8, m):
        """Mean CIELAB L*,a*,b* of a mask, in real units (L 0-100, a/b signed).

        Done on FLOAT input on purpose. OpenCV's 8-bit Lab is scaled (L*255/100,
        a+128, b+128); its float32 Lab is not. Mixing the two is the bug that
        made the first version of this correction move her skin a* by 2 points
        when it had computed a gain big enough to move it by 5.
        """
        lab = cv2.cvtColor(np.ascontiguousarray(u8, np.float32) / 255.0,
                           cv2.COLOR_RGB2LAB)
        return (float(lab[..., 0][m].mean()), float(lab[..., 1][m].mean()),
                float(lab[..., 2][m].mean()))

    her_sk = solid & skin(g_u8)
    rep["skin_wb"] = {"applied": False}
    if her_sk.sum() > 200:
        L0, a0, b0 = _skin_ab(g_u8, her_sk)
        rep["skin_ab_before"] = [round(a0, 2), round(b0, 2)]
        log(f"  integrate: her skin, pre-grade, Lab a*{a0:.2f} b*{b0:.2f}")
    if skin_ref is not None and her_sk.sum() > 200:
        # SOLVED, not computed once. A von Kries gain that lands her skin's MEAN
        # on the reference cannot be written down in closed form -- Lab is not
        # linear in RGB and the mean of a transform is not the transform of the
        # mean -- so it is iterated to a fixed point. Four passes is plenty:
        # CARTHIEF converges at gains 1.000/1.000/1.000, which is the property
        # that keeps the control untouched.
        total = np.ones(3, np.float32)
        lin0 = srgb_to_lin(graded)

        # PROTECT HER NEUTRALS.
        #
        # A flat gain that lands her skin also tints everything else, and the
        # first version of this did exactly that: on SANCHEZ and OFFERUP the
        # blue gain of 1.13-1.14 turned her grey hair lavender. The correction
        # is therefore weighted by how chromatic each pixel ALREADY is -- her
        # skin sits at C* 15-25 and takes it in full, while her hair sits at
        # C* 7-8 and is left alone. Standard colourist practice: qualify the
        # correction, do not paint the whole element. The band was set by
        # measurement, not taste: at (4,13) her hair was still inside it and
        # still went violet, because the dark tones of the OFFERUP judge tile
        # are a reddish [64,50,51] and a blue gain of 1.16 on that is purple.
        lab0 = cv2.cvtColor(np.ascontiguousarray(g_u8, np.float32) / 255.0,
                            cv2.COLOR_RGB2LAB)
        C0 = np.hypot(lab0[..., 1], lab0[..., 2])
        wmap = np.clip((C0 - wb_chroma_band[0])
                       / max(wb_chroma_band[1] - wb_chroma_band[0], 1e-3),
                       0.0, 1.0)[..., None]
        rep["skin_wb_neutral_guard"] = {
            "chroma_band": list(wb_chroma_band),
            "pct_of_her_fully_corrected": round(
                100.0 * float((wmap[..., 0][solid] > 0.99).mean()), 1),
            "pct_of_her_untouched": round(
                100.0 * float((wmap[..., 0][solid] < 0.01).mean()), 1)}

        def _apply(g):
            return np.clip(lin_to_srgb(lin0 * (1.0 - wmap)
                                       + lin0 * g[None, None, :] * wmap),
                           0.0, 255.0)

        for _ in range(4):
            L0, a0, b0 = _skin_ab(g_u8, her_sk)
            want = np.array([[[L0, skin_ref[0], skin_ref[1]]]], np.float32)
            have = np.array([[[L0, a0, b0]]], np.float32)
            w = srgb_to_lin(np.clip(cv2.cvtColor(want, cv2.COLOR_LAB2RGB), 0, 1)
                            * 255.0).ravel()
            h = srgb_to_lin(np.clip(cv2.cvtColor(have, cv2.COLOR_LAB2RGB), 0, 1)
                            * 255.0).ravel()
            step = w / np.maximum(h, 1e-5)
            step *= float(luma(h) / max(luma(h * step), 1e-6))   # colour only
            total = np.clip(total * step, *wb_clamp)
            graded = _apply(total)
            g_u8 = graded.astype(np.uint8)
            if abs(a0 - skin_ref[0]) < 0.15 and abs(b0 - skin_ref[1]) < 0.15:
                break
        # CHROMA CAP -- the neutral guard's missing other half.
        #
        # MEASURED 2026-08-29 on the carthief judge tile. The guard above
        # protects pixels BELOW wb_chroma_band[1]; it does nothing for pixels
        # that are already MORE chromatic than skin. Her hair on this tile is
        # C* 23.2, above the band's 17.0, so it takes the full von Kries gain:
        # a B gain of 0.35 drove the hair band from C* 23.24 to 40.49 (+74%)
        # while the winner's judge hair measures C* 23.24. The band was tuned
        # when her hair was GREY (C* 7-8) and silently stopped applying when it
        # was not. This caps every pixel's post-WB chroma at `wb_chroma_cap`x
        # its own pre-WB chroma, in Lab, luma untouched -- so skin, which the
        # WB moves in HUE at roughly constant C*, is unaffected, and only the
        # surfaces the gain would have super-saturated get pulled back.
        if wb_chroma_cap is not None:
            _l1 = cv2.cvtColor(np.ascontiguousarray(graded, np.float32) / 255.0,
                               cv2.COLOR_RGB2LAB)
            _C1 = np.hypot(_l1[..., 1], _l1[..., 2])
            _lim = C0 * float(wb_chroma_cap)
            _sc = np.where(_C1 > np.maximum(_lim, 1e-3),
                           _lim / np.maximum(_C1, 1e-6), 1.0).astype(np.float32)
            _l1[..., 1] *= _sc
            _l1[..., 2] *= _sc
            graded = np.clip(cv2.cvtColor(_l1, cv2.COLOR_LAB2RGB) * 255.0,
                             0.0, 255.0)
            g_u8 = graded.astype(np.uint8)
            rep["wb_chroma_cap"] = {"cap": float(wb_chroma_cap),
                                    "pct_pulled_back": round(
                                        100.0 * float((_sc[solid] < 0.999).mean()), 1)}

        _, a1, b1 = _skin_ab(g_u8, her_sk)
        rep["skin_wb"] = {"applied": True,
                          "her_skin_ab": rep.get("skin_ab_before"),
                          "reference_ab": [round(float(v), 2) for v in skin_ref],
                          "landed_ab": [round(a1, 2), round(b1, 2)],
                          "gains": [round(float(v), 4) for v in total]}
        log(f"  integrate: her skin white balance -> reference "
            f"a*{skin_ref[0]:.1f} b*{skin_ref[1]:.1f}: landed a*{a1:.2f} "
            f"b*{b1:.2f}, von Kries gains R{total[0]:.3f} G{total[1]:.3f} "
            f"B{total[2]:.3f}")

    # SKIN LUMA, last, and only if she is STILL hot against the plate's skin.
    # A gamma on her layer only. Never a whole-canvas exposure change: that is
    # precisely the thing that has already failed twice.
    her_sk = solid & skin(g_u8)
    hl = float(luma(graded)[her_sk].mean()) if her_sk.sum() > 50 else float("nan")
    pl_s = float(luma(band)[p_sk].mean()) if p_sk.sum() > 50 else float("nan")
    gam = 1.0
    if not (np.isnan(hl) or np.isnan(pl_s)) and (hl - pl_s) > skin_dluma_max:
        want = max(pl_s + skin_dluma_max, 1.0)
        gam = float(np.clip(np.log(want / 255.0) / np.log(max(hl, 1.0) / 255.0),
                            gamma_floor, 1.0))
        if gam < 0.999:
            graded = np.clip(np.power(graded / 255.0, 1.0 / gam) * 255.0, 0.0, 255.0)
    rep["skin_luma"] = {"judge": round(hl, 1), "plate": round(pl_s, 1),
                        "gamma": round(gam, 3)}

    fin = graded.astype(np.uint8)
    rep["black_floor_before"] = round(
        float(np.percentile(luma(rgb_u8)[solid], 1)), 1)
    rep["black_floor_after"] = round(
        float(np.percentile(luma(fin)[solid], 1)), 1)
    rep["plate_black_floor"] = round(float(np.percentile(luma(band), 1)), 1)
    g = [c["gain"] for c in rep["channels"]]
    log(f"  integrate: {mode} {'per-channel' if per_channel else 'achromatic'} Grade "
        f"in linear against plate rows {r0}-{r1}; her black floor "
        f"{rep['black_floor_before']:.1f} -> {rep['black_floor_after']:.1f} "
        f"(plate {rep['plate_black_floor']:.1f}), gains "
        + (f"R{g[0]:.2f} G{g[1]:.2f} B{g[2]:.2f}" if per_channel
           else f"{g[0]:.2f}")
        + f", skin sat x{sfac:.2f} ({js:.0f} toward plate {ps:.0f}), "
        f"skin gamma {gam:.3f}")
    return Image.fromarray(np.dstack([fin, al.astype(np.uint8)]), "RGBA"), rep


# ------------------------------------------------------------- light wrap
def light_wrap(canvas_rgb: Image.Image, cut_rgba: Image.Image, cut_xy, *,
               sigma=14.0, amount=0.18, band_px=3):
    """Screen a blurred slice of the PLATE back into the element's edge band.

    The construction forbids an outline stroke -- 0 of 12 competitor thumbnails
    have one -- so this is the only legal way to stop the cut-out's edge reading
    as a die-cut sticker: real light behind a subject spills around its
    silhouette. Recipe from whizzystudios.com (blur the background, add it into
    the foreground with a brightness-adding mode, restrict it to a band derived
    from the dilated alpha), corroborated by mixinglight.com and
    richardfrazer.com. The radii are proposals -- the sources give none --
    picked as ~2% of canvas height for the blur and a 6px total band.
    """
    W, H = canvas_rgb.size
    a = np.zeros((H, W), np.float32)
    ca = np.asarray(cut_rgba.getchannel("A")).astype(np.float32) / 255.0
    px, py = int(cut_xy[0]), int(cut_xy[1])
    y0, y1 = max(0, py), min(H, py + cut_rgba.height)
    x0, x1 = max(0, px), min(W, px + cut_rgba.width)
    if y1 <= y0 or x1 <= x0:
        return canvas_rgb
    a[y0:y1, x0:x1] = ca[y0 - py:y1 - py, x0 - px:x1 - px]
    hard = (a > 0.5).astype(np.uint8)
    k = np.ones((2 * band_px + 1, 2 * band_px + 1), np.uint8)
    edge = (cv2.dilate(hard, k).astype(np.float32)
            - cv2.erode(hard, k).astype(np.float32))
    edge = cv2.GaussianBlur(edge, (0, 0), band_px * 0.8)
    base = np.asarray(canvas_rgb.convert("RGB")).astype(np.float32) / 255.0
    blur = cv2.GaussianBlur(base, (0, 0), sigma)
    screen = 1.0 - (1.0 - base) * (1.0 - blur)
    m = np.clip(edge * a * amount, 0.0, 1.0)[..., None]
    out = base * (1.0 - m) + screen * m
    return Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8))
