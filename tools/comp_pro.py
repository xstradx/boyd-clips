# -*- coding: utf-8 -*-
"""Professional compositing operations. The vocabulary, not a patch list.

Nathan, 2026-08-30: "you're just giving me instructions on how to edit one
little thing but the thing you're not capturing is the vision."

Correct. Fixing defects one at a time never accumulates into a designed image.
A thumbnail that reads as professional has ONE light source, ONE focal point and
ONE colour story, and every element is subordinate to that. What follows is the
vocabulary needed to express such a decision - taken from how the technique is
actually described by people who do it for a living, not invented here:

  light wrap    feather the BACKGROUND's light onto the subject's edge. This is
                the single thing that stops a cutout reading as pasted - a real
                subject picks up ambient light from behind it, a pasted one does
                not. Described as simulating "the ambient light in a scene that
                would cast onto the subject by the background".
  rim light     a painted coloured backlight along the edge facing the key,
                usually cyan or magenta, mimicking studio backlighting. This is
                what separates a subject from a background at thumbnail size.
  dodge & burn  "the single most impactful technique in thumbnail retouching -
                it's how MrBeast's designers make faces pop even at tiny sizes."
  depth         background blurred and pushed back, atmosphere between the
                layers, so the frame has three distances rather than two.
  grade         one LUT-like pass over the WHOLE frame at the end so subject and
                plate share a colour story instead of being two photographs.

Every function is deterministic numpy/OpenCV. Nothing here needs a model: these
are small well-understood image operations, and a 20-line op you can reason
about beats a 6GB network for this job.

Sources for the technique descriptions:
  provideocoalition.com/how-to-light-wrap/
  photoshoptrainingchannel.com/how-to-create-light-wraps-in-photoshop/
  artiphik.com/blog/mrbeast-thumbnail-analysis
"""
import numpy as np
import cv2


def _f32(a):
    return a.astype(np.float32) if a.dtype != np.float32 else a


def edge_band(alpha, width):
    """Soft band lying just INSIDE the subject edge. 0..1."""
    a = np.clip(_f32(alpha), 0, 1)
    inner = cv2.erode((a > 0.5).astype(np.uint8), np.ones((3, 3), np.uint8),
                      iterations=max(1, int(width)))
    band = np.clip(a - inner.astype(np.float32), 0, 1)
    return cv2.GaussianBlur(band, (0, 0), max(1.0, width * 0.6))


def light_wrap(canvas, rgb, alpha, width=14, strength=0.55, blur=None):
    """Screen the blurred BACKGROUND onto the subject's inner edge.

    This is the fix for "it looks pasted". Without it the cut line is a hard
    optical discontinuity - the eye reads the boundary as an edit. With it the
    background's light spills onto the subject exactly as it would in camera.
    """
    a = np.clip(_f32(alpha), 0, 1)
    bg = cv2.GaussianBlur(_f32(canvas), (0, 0), blur or max(4.0, width * 1.4))
    out = _f32(rgb).copy()
    # BRIGHTNESS GATE: only wrap where the background is brighter than the
    # subject. Without it the op paints the darker plate onto the edge and
    # reads as a grey outline - the exact "sticker" look it is meant to cure.
    lb = cv2.cvtColor(np.clip(bg, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    ls = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    gate = np.clip((lb - ls) / 60.0, 0, 1)
    band = edge_band(a, width) * strength * gate
    scr = 255.0 - (255.0 - out) * (255.0 - bg) / 255.0
    return out * (1 - band[..., None]) + scr * band[..., None]


def sample_key_colour(plate, cool=0.55):
    """Take the rim colour FROM the plate's brightest region, not from taste.

    A rim colour picked arbitrarily reads as a Photoshop stroke; one sampled
    from the scene's own light reads as motivated. Pushed toward cool because a
    warm key with a cool backlight is the standard studio pairing.
    """
    p = _f32(plate)
    lum = cv2.cvtColor(np.clip(p, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    hot = p[lum >= np.percentile(lum, 96)]
    c = hot.mean(axis=0) if len(hot) else np.array([220, 220, 230], np.float32)
    cool_ref = np.array([90, 195, 255], np.float32)
    return tuple((c * (1 - cool) + cool_ref * cool).tolist())


def rim_light(rgb, alpha, colour=(120, 205, 255), width=9, strength=0.85,
              direction=(-1.0, -0.55), falloff=1.35, bloom=0.40):
    """Coloured backlight along the edge FACING the key light.

    Not a white outline - an outline is a sticker border. This is light: it only
    appears on the side the key is on, and it falls off.
    """
    a = np.clip(_f32(alpha), 0, 1)
    band = edge_band(a, width)
    gy, gx = np.gradient(cv2.GaussianBlur(a, (0, 0), 2.0))
    dx, dy = direction
    n = float(np.hypot(dx, dy)) or 1.0
    facing = np.clip(-(gx * (dx / n) + gy * (dy / n)), 0, None)
    m = facing / (facing.max() + 1e-6)
    m = (m ** falloff) * band * strength
    col = np.array(colour, np.float32)
    out = _f32(rgb)
    lit = np.clip(out + col * m[..., None], 0, 255)
    # SECOND PASS: a wide, weak bloom off the same rim. One tight pass is a
    # stroke; tight + bloom is a light.
    if bloom:
        wide = cv2.GaussianBlur(m, (0, 0), max(2.0, width * 3.0)) * bloom
        lit = 255.0 - (255.0 - lit) * (255.0 - col * wide[..., None]) / 255.0
    return np.clip(lit, 0, 255)


def dodge_burn(rgb, mask, amount=0.30, radius=25):
    """Deepen the modelling of a face: lift what is already lit, sink what is
    already shadowed. The most impactful single retouch at thumbnail size,
    because it is what survives being scaled to 210px wide in a feed."""
    out = _f32(rgb)
    m = np.clip(_f32(mask), 0, 1)
    lab = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0]
    # MACRO dodge & burn: the shading map is heavily blurred. High-frequency
    # D&B is skin retouching; what makes a face read at 210px in a feed is the
    # low-frequency sculpting of form.
    lo = cv2.GaussianBlur(L, (0, 0), radius)
    ref = lo[m > 0.5].mean() if (m > 0.5).any() else 128.0
    d = np.clip((lo - ref) / 40.0, -1.0, 1.0)      # zero-centred: redistributes,
    lab[..., 0] = np.clip(L * (1.0 + d * amount * m), 4, 250)   # never re-exposes
    # L ONLY. Multiplying RGB shifts chroma and turns skin plastic.
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32)


def depth_push(canvas, subject_mask, blur=2.4, darken=0.34, haze=0.16,
               haze_rgb=(150, 170, 200)):
    """Send the background back: blur it, darken it, and lay a little
    atmosphere over it. Three distances instead of two."""
    c = _f32(canvas)
    bgm = 1.0 - np.clip(_f32(subject_mask), 0, 1)
    b = cv2.GaussianBlur(c, (0, 0), blur)
    b *= (1.0 - darken)
    b = b * (1 - haze) + np.array(haze_rgb, np.float32) * haze
    return c * (1 - bgm[..., None]) + b * bgm[..., None]


def key_light(canvas, cx, cy, radius, strength=0.30, colour=(255, 236, 200)):
    """One warm source. Everything else falls away from it - that is what makes
    a frame look lit rather than evenly exposed."""
    h, w = canvas.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - cx) / radius) ** 2 + ((yy - cy) / (radius * 0.82)) ** 2)
    g = np.exp(-(d ** 2) * 1.1) * strength
    return np.clip(_f32(canvas) + np.array(colour, np.float32) * g[..., None] * 0.55, 0, 255)


def grade(canvas, contrast=1.10, sat=1.12, lift=(2, 0, 6), teal=0.045, gamma=0.98):
    """One pass over the WHOLE frame so subject and plate share a colour story.

    Boost contrast and saturation, push shadows slightly cool and highlights
    slightly warm - the split-tone that reads as 'graded' rather than 'a photo'.
    """
    c = _f32(canvas) / 255.0
    c = np.clip((c - 0.5) * contrast + 0.5, 0, 1)
    c = np.power(c, gamma)
    g = cv2.cvtColor((c * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)[..., None] / 255.0
    c = np.clip(g + (c - g) * sat, 0, 1)
    shadow = np.clip(1.0 - g * 1.6, 0, 1)
    c[..., 2] += teal * shadow[..., 0]
    c[..., 1] += teal * 0.45 * shadow[..., 0]
    hi = np.clip(g * 1.4 - 0.35, 0, 1)
    c[..., 0] += teal * 0.7 * hi[..., 0]
    c = np.clip(c * 255.0 + np.array(lift, np.float32) * 0.6, 0, 255)
    return c


def contact_shadow(canvas, alpha, dx=16, dy=22, blur=26, strength=0.42):
    """A soft offset shadow so the subject sits IN the frame rather than on it."""
    a = np.clip(_f32(alpha), 0, 1)
    c = _f32(canvas)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    sh = cv2.warpAffine(a, M, (a.shape[1], a.shape[0]))
    # blur GROWS with distance from the contact point - a uniformly blurred
    # shadow reads as a smudge. Four-layer stack approximates that cheaply.
    acc = np.zeros_like(sh)
    for i, w in enumerate((0.40, 0.30, 0.20, 0.10)):
        acc += w * cv2.GaussianBlur(sh, (0, 0), blur * (0.45 + 0.55 * i))
    sh = np.clip(acc - a, 0, 1) * strength
    # NEVER multiply toward black. A shadow is a darker, slightly cool TINT of
    # the surface it falls on; multiplying to black is the commonest giveaway.
    tint = c * 0.45 + np.array([10, 6, 2], np.float32)
    return c * (1 - sh[..., None]) + tint * sh[..., None]


def harmonise(rgb, alpha, plate, w_L=0.15, w_ab=0.70):
    """Pull the subject's colour toward the plate's - chroma strongly, luma barely.

    Full Reinhard moment-matching crushes a subject: matching L as hard as a/b
    flattens the very modelling that makes a face read. Chroma is what betrays a
    composite; luminance is what carries the form. So: a/b at 0.70, L at 0.15.
    """
    a = np.clip(_f32(alpha), 0, 1) > 0.5
    if a.sum() < 200:
        return _f32(rgb)
    s_lab = cv2.cvtColor(np.clip(_f32(rgb), 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    p_lab = cv2.cvtColor(np.clip(_f32(plate), 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    for ch, w in ((0, w_L), (1, w_ab), (2, w_ab)):
        ms, ss = s_lab[..., ch][a].mean(), s_lab[..., ch][a].std() + 1e-6
        mp, sp = p_lab[..., ch].mean(), p_lab[..., ch].std() + 1e-6
        tgt = (s_lab[..., ch] - ms) * float(np.clip(sp / ss, 0.75, 1.35)) + mp
        s_lab[..., ch] = s_lab[..., ch] * (1 - w) + tgt * w
    s_lab = np.clip(s_lab, 0, 255)
    return cv2.cvtColor(s_lab.astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32)
