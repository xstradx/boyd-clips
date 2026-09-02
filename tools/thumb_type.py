# -*- coding: utf-8 -*-
"""Type treatments for the thumbnail: ONE renderer, named presets.

Nathan, 2026-09-01: "Maybe throw in a underline under hates you" / "make the
words [not] look so generic and cheap" - the THIRD time the type has been
called low quality (N17 08-29 02:40 "font is off and looks way lower
quality"; P36 08-29 17:25 "more click baity type font ... give me multiple
options to pick from"). The old renderer was two near-copies of the same
drawing code (title in Thumb.type_layer, kicker in Thumb.kicker) with every
device hard-coded, so a treatment could only change by editing both, and the
"multiple options" P36 asked for were never built because there was nothing
to build them with.

Every device lives here now, as data. A STYLE says how every run is drawn
(font, tracking, stroke, drop shadow, hard extrude, gradient, skew) and what
the EMPHASISED run gets on top (glow, underline, highlight box, size bump).
`render_runs` is the only thing that puts glyphs on a canvas.

Everything a style adds is INK: the mask returned covers the underline and
the highlight box exactly as it covers a glyph, so R1 (title never on a
subject, kicker never on a face), the arrow's avoidance and the kicker's
bottom clamp see the whole treatment.

The "house" preset reproduces the five accepted 2026-08-31 builds byte for
byte (`selftest` proves it against Thumb's own constants); every other preset
is an option for Nathan to pick and lock in, never a silent default.
"""
import os
import copy
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FONTS = os.path.join(ROOT, "assets", "fonts")

# The house numbers, measured off the accepted builds. thumb.py carries the
# same values as its own constants; selftest() asserts they still agree.
HOUSE_SHADOW = dict(dx=5, dy=6, blur=7, alpha=0.72)
HOUSE_TITLE_STROKE = 8
HOUSE_TITLE_SHADOW_STROKE = 10
HOUSE_KICKER_STROKE = 9
HOUSE_EMPHASIS = dict(stroke=11, blur=13.0, alpha=0.85)

# --------------------------------------------------------------------------
# A style is a dict. Keys (all optional except font):
#   font          file in assets/fonts
#   axes          {"Weight": 900, "Width": 125} for a variable font
#   tracking      extra advance per glyph, em fraction (0 = native layout)
#   skew          shear in degrees, positive leans right (italic)
#   stroke        black outline, px
#   shadow        {dx, dy, blur, alpha, stroke} soft black drop shadow, or None
#   extrude       {dx, dy, n, color} n hard copies stepped by (dx, dy)
#   gradient      (top, bottom) multipliers on the fill colour, or None
#   ink_stroke    stroke used for the collision mask (defaults to stroke)
#   emphasis      what the emphasised run gets:
#       glow      {stroke, blur, alpha, color=None -> run colour}
#       underline {thick, gap, tilt, taper, color=None -> run colour, stroke}
#                 thick/gap as fractions of the cap height
#       highlight {pad_x, pad_y, color, skew, text=(r,g,b) fill override}
#       scale     size multiplier for the run (baseline aligned)
#   title / kicker   per-element overrides of any of the above
# --------------------------------------------------------------------------
# Every preset below "house" is MEASURED off a winner, not designed. Survey
# 2026-09-01 (scratchpad/typesurvey/measured2.json, 58 crops; verified by eye
# on scratchpad/survey_check.jpg):
#   audit   Audit 12/12 top thumbnails (1.2M, 971K ...): wide geometric
#           grotesque (Montserrat 800-900 ratio-matched), sentence case, white
#           + #fdfb05, NO glyph stroke, a soft black halo 5-13 px (hardness
#           <= 0.30), one line 0.07-0.12 H at the top.
#   audit_now  Audit's 8 MOST RECENT (2026, .firecrawl/type/sheets/
#           AudittheAudit.jpg, zoomed in scratchpad audit_now_zoom.jpg): the
#           channel MOVED to condensed heavy caps (Anton-class), white +
#           yellow, a hard black stroke ~5 px (~4% of cap) plus a soft dark
#           halo, caps 0.17 H, top. Same face as house, thinner stroke, a
#           halo, no glow, bigger.
#   client  Nathan's OWN top three (72K / 62K / 37K): Archivo 900 / Montserrat
#           800 caps, red #f20203 + white, no stroke, one deep soft black
#           shadow (+4,+6), blur 14, alpha 0.85, ~23 px reach.
#   crt     CourtroomTime winners (891K, 553K): condensed caps (Anton/Bebas),
#           HARD black stroke 0.08-0.09 x cap, HARD offset shadow (+8,+12),
#           flat red second line - no glow anywhere.
# The "cheap" tells measured on MONKEY_S and found in 0/45 winners: a uniform
# hard 7-10 px outline as the ONLY edge device, Anton in lowercase, a coloured
# glow behind the key word, the offset shadow absorbed into the stroke.
#
# The underline is DERIVED, not observed: the only underlines in the reference
# set are two 3-4 px hairlines on 1.4K/2.3K TTT-own images. Rule used here:
# thickness 0.14 x cap, gap 0.08 x cap, exactly the ink width of the run, the
# run's own fill, carrying the letters' stroke and shadow. Presets ending in
# _ul carry it under the emphasised run (his ask: "a underline under hates
# you", 2026-09-01).
#
# Colours are NOT a style property: the case's white/yellow/red runs stay
# whatever config/cases.json says (2026-08-31 "your owner is white and hates
# you is red").
_MONTSERRAT_800 = dict(font="Montserrat-Var.ttf", axes={"Weight": 800})
_ARCHIVO_900 = dict(font="Archivo-Var.ttf", axes={"Weight": 900, "Width": 100})
_UL = dict(thick=0.14, gap=0.08, tilt=0.0, taper=0.0)


def _with_underline(style, stroke):
    st = copy.deepcopy(style)
    k = st.setdefault("kicker", {})
    em = k.setdefault("emphasis", {})
    em["underline"] = dict(_UL, stroke=stroke)
    return st


_AUDIT = dict(
    _MONTSERRAT_800,
    stroke=0,
    title=dict(shadow=dict(dx=0, dy=2, blur=8, alpha=0.9, stroke=6), ink_stroke=6),
    kicker=dict(shadow=dict(dx=0, dy=4, blur=12, alpha=0.9, stroke=6), ink_stroke=6,
                emphasis={}),
)
_AUDIT_NOW = dict(
    font="Anton-Regular.ttf",
    title=dict(stroke=4, shadow=dict(dx=0, dy=3, blur=10, alpha=0.85, stroke=8), ink_stroke=8),
    kicker=dict(stroke=5, shadow=dict(dx=0, dy=3, blur=10, alpha=0.85, stroke=8), ink_stroke=8,
                emphasis={}),
)
_CLIENT = dict(
    _ARCHIVO_900,
    stroke=0,
    shadow=dict(dx=4, dy=6, blur=14, alpha=0.85, stroke=5), ink_stroke=5,
    title=dict(),
    kicker=dict(emphasis={}),
)
_CRT = dict(
    _MONTSERRAT_800,
    # title: sentence case is R33, so the display face is the wide grotesque
    # with the CRT edge; the kicker is the condensed caps the winners use.
    title=dict(stroke=8, shadow=dict(dx=6, dy=9, blur=1.5, alpha=1.0, stroke=8), ink_stroke=8),
    kicker=dict(font="Anton-Regular.ttf", axes=None, stroke=10,
                shadow=dict(dx=8, dy=12, blur=1.5, alpha=1.0, stroke=10), ink_stroke=10,
                emphasis={}),
)

STYLES = {
    # the accepted 2026-08-31 treatment, untouched
    "house": dict(
        font="Anton-Regular.ttf",
        title=dict(stroke=HOUSE_TITLE_STROKE,
                   shadow=dict(HOUSE_SHADOW, stroke=HOUSE_TITLE_SHADOW_STROKE),
                   ink_stroke=HOUSE_TITLE_SHADOW_STROKE),
        kicker=dict(stroke=HOUSE_KICKER_STROKE,
                    shadow=dict(HOUSE_SHADOW, stroke=HOUSE_KICKER_STROKE),
                    ink_stroke=HOUSE_KICKER_STROKE,
                    emphasis=dict(glow=dict(HOUSE_EMPHASIS))),
    ),
    "audit": _AUDIT,
    "audit_ul": _with_underline(_AUDIT, 0),
    "audit_now": _AUDIT_NOW,
    "audit_now_ul": _with_underline(_AUDIT_NOW, 5),
    "client": _CLIENT,
    "client_ul": _with_underline(_CLIENT, 0),
    "crt": _CRT,
    "crt_ul": _with_underline(_CRT, 10),
}

_ELEMENT_KEYS = ("font", "axes", "tracking", "skew", "stroke", "shadow", "extrude",
                 "gradient", "ink_stroke", "emphasis")


def resolve(style, element):
    """Flatten a preset (name or dict) for one element ('title' | 'kicker')."""
    if isinstance(style, str):
        if style not in STYLES:
            raise SystemExit(f"TYPE_STYLE_UNKNOWN: {style!r} (have {sorted(STYLES)})")
        style = STYLES[style]
    base = {k: copy.deepcopy(style.get(k)) for k in _ELEMENT_KEYS if k in style}
    base.update(copy.deepcopy(style.get(element, {}) or {}))
    base.setdefault("font", "Anton-Regular.ttf")
    base.setdefault("tracking", 0.0)
    base.setdefault("skew", 0.0)
    base.setdefault("stroke", 8)
    base.setdefault("ink_stroke", base["stroke"])
    base.setdefault("emphasis", {})
    return base


# -- fonts ------------------------------------------------------------------
_FONT_CACHE = {}


def load_font(spec, size):
    key = (spec["font"], tuple(sorted((spec.get("axes") or {}).items())), int(size))
    f = _FONT_CACHE.get(key)
    if f is None:
        f = ImageFont.truetype(os.path.join(FONTS, spec["font"]), int(size))
        if spec.get("axes"):
            names = [a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
                     for a in f.get_variation_axes()]
            defaults = [a["default"] for a in f.get_variation_axes()]
            vals = [spec["axes"].get(n, d) for n, d in zip(names, defaults)]
            f.set_variation_by_axes(vals)
        _FONT_CACHE[key] = f
    return f


def cap_height(font):
    bb = font.getbbox("H")
    return bb[3] - bb[1]


def text_len(font, text, tracking, size):
    if not tracking:
        return font.getlength(text)
    return sum(font.getlength(ch) + tracking * size for ch in text)


def _draw_text(draw, xy, text, font, tracking, size, **kw):
    if not tracking:
        draw.text(xy, text, font=font, **kw)
        return
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, **kw)
        x += font.getlength(ch) + tracking * size


# -- layout -----------------------------------------------------------------
class Layout:
    """Where each run sits at a given size: fonts, x offsets, baseline shifts."""

    def __init__(self, spec, runs, size, x, y):
        self.spec, self.runs, self.size = spec, runs, int(size)
        self.base = load_font(spec, size)
        emph = spec.get("emphasis") or {}
        sc = float(emph.get("scale", 1.0) or 1.0)
        self.emph_font = load_font(spec, round(size * sc)) if sc != 1.0 else self.base
        self.emph_size = round(size * sc) if sc != 1.0 else self.size
        asc0 = self.base.getmetrics()[0]
        self.items = []
        cx = float(x)
        for text, fill, is_emph in runs:
            f = self.emph_font if is_emph else self.base
            s = self.emph_size if is_emph else self.size
            dy = asc0 - f.getmetrics()[0] if is_emph else 0     # baseline-align the bump
            self.items.append(dict(text=text, fill=tuple(fill), emph=bool(is_emph),
                                   font=f, size=s, x=cx, y=float(y) + dy))
            cx += text_len(f, text, spec["tracking"], s)
        self.width = cx - float(x)
        self.x, self.y = float(x), float(y)

    def ink_bbox(self, stroke):
        """Bounding box of the glyph ink (with stroke) over all runs."""
        x0 = y0 = 1e9
        x1 = y1 = -1e9
        for it in self.items:
            bb = it["font"].getbbox(it["text"], stroke_width=stroke)
            x0 = min(x0, it["x"] + bb[0]); y0 = min(y0, it["y"] + bb[1])
            x1 = max(x1, it["x"] + bb[2]); y1 = max(y1, it["y"] + bb[3])
        return x0, y0, x1, y1


def fit(spec, runs, cap_px, max_w, size_hi, size_lo=24, x=0, y=0):
    """The house sizing rule: the largest size whose cap height fits cap_px,
    then shrink until the whole line fits max_w. Returns a Layout."""
    size = size_lo
    for t in range(int(size_hi), size_lo, -1):
        if cap_height(load_font(spec, t)) <= cap_px:
            size = t
            break
    lay = Layout(spec, runs, size, x, y)
    while lay.width > max_w and size > size_lo:
        size -= 1
        lay = Layout(spec, runs, size, x, y)
    return lay


def extra_below(spec, cap_px):
    """Pixels the treatment adds BELOW the glyph ink (underline, highlight
    pad) - the kicker's face-clear solve and bottom clamp must reserve it."""
    e = spec.get("emphasis") or {}
    below = 0
    u = e.get("underline")
    if u:
        # the ink mask grows the bar by max(bar stroke, ink_stroke) - same here
        below = max(below, int(cap_px * (u["gap"] + u["thick"]))
                    + max(int(u.get("stroke", spec["stroke"])), int(spec["ink_stroke"])))
    h = e.get("highlight")
    if h:
        below = max(below, int(cap_px * h["pad_y"]) + int(h.get("stroke", 0)))
    ex = spec.get("extrude")
    if ex:
        below += int(ex["dy"] * ex["n"])
    sh = spec.get("shadow")
    if sh and _hard(sh):
        below += int(max(0, sh["dy"]))
    return below


def _hard(sh):
    """A HARD shadow (blur <= 2 px) is a solid block and counts as ink at its
    offset - the CRT look. A soft one (house 7, Audit 8-12, client 14) is a
    gradient and does not; the house ink mask stays what it was."""
    return float(sh.get("blur") or 0) <= 2.0


# -- rendering --------------------------------------------------------------
def _shape_masks(lay, spec, W, H, cap_px):
    """Underline / highlight polygons for the emphasised runs -> (colour, L
    mask without stroke, L mask with stroke) lists, in draw order."""
    e = spec.get("emphasis") or {}
    shapes = []
    for it in lay.items:
        if not it["emph"]:
            continue
        bb = it["font"].getbbox(it["text"])
        ix0, ix1 = it["x"] + bb[0], it["x"] + bb[2]
        if spec["tracking"]:
            ix1 = it["x"] + text_len(it["font"], it["text"], spec["tracking"], it["size"])
        asc = it["font"].getmetrics()[0]
        baseline = it["y"] + asc
        u = e.get("underline")
        if u:
            thick = cap_px * u["thick"]
            gap = cap_px * u["gap"]
            tilt = np.tan(np.radians(u.get("tilt", 0.0)))
            taper = float(u.get("taper", 0.0))
            y_top = baseline + gap
            # a marker stroke: thinner at the start, full at the end; the
            # tilt pivots about the bar's centre so the gap stays honest
            t0 = thick * (1.0 - taper)
            rise = (ix1 - ix0) * tilt / 2.0
            pts = [(ix0, y_top - rise), (ix1, y_top + rise),
                   (ix1, y_top + rise + thick), (ix0, y_top - rise + t0)]
            shapes.append(("underline", u.get("color") or it["fill"], pts,
                           int(u.get("stroke", spec["stroke"]))))
        h = e.get("highlight")
        if h:
            px, py = cap_px * h["pad_x"], cap_px * h["pad_y"]
            top = it["y"] + bb[1] - py
            bot = it["y"] + bb[3] + py
            sk = np.tan(np.radians(h.get("skew", 0.0))) * (bot - top) / 2.0
            pts = [(ix0 - px + sk, top), (ix1 + px + sk, top),
                   (ix1 + px - sk, bot), (ix0 - px - sk, bot)]
            shapes.append(("highlight", h.get("color") or it["fill"], pts,
                           int(h.get("stroke", 0))))
    return shapes


def _poly_mask(pts, W, H, grow=0):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.polygon([(float(x), float(y)) for x, y in pts], fill=255)
    if grow > 0:
        d.line([(float(x), float(y)) for x, y in pts] + [(float(pts[0][0]), float(pts[0][1]))],
               fill=255, width=grow * 2, joint="curve")
        for x, y in pts:
            d.ellipse((x - grow, y - grow, x + grow, y + grow), fill=255)
    return m


def render_runs(lay, spec, W, H, cap_px):
    """Draw a laid-out line. Returns (RGBA PIL image, ink L image).

    Layer order, back to front: soft shadow -> hard extrude -> emphasis glow
    -> highlight panel -> glyphs (stroke + fill, gradient) -> underline.
    The ink mask is every solid layer at `ink_stroke`, glow excluded."""
    tr, size = spec["tracking"], lay.size
    e = spec.get("emphasis") or {}
    shapes = _shape_masks(lay, spec, W, H, cap_px)
    hl = [s for s in shapes if s[0] == "highlight"]
    ul = [s for s in shapes if s[0] == "underline"]

    def glyph_mask(stroke, dx=0, dy=0, only=None):
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        for it in lay.items:
            if only is not None and it["emph"] != only:
                continue
            _draw_text(d, (it["x"] + dx, it["y"] + dy), it["text"], it["font"], tr, it["size"],
                       fill=255, stroke_width=stroke, stroke_fill=255)
        return m

    def solid_mask(stroke, dx=0, dy=0):
        m = glyph_mask(stroke, dx, dy)
        for kind, col, pts, st in shapes:
            sm = _poly_mask([(x + dx, y + dy) for x, y in pts], W, H, grow=max(st, stroke) if kind == "underline" else st)
            m = Image.fromarray(np.maximum(np.asarray(m), np.asarray(sm)))
        return m

    rgba = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # 1. soft drop shadow
    sh = spec.get("shadow")
    if sh:
        sm = solid_mask(int(sh.get("stroke", spec["stroke"])), sh["dx"], sh["dy"])
        if sh.get("blur"):
            sm = sm.filter(ImageFilter.GaussianBlur(sh["blur"]))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.putalpha(sm.point(lambda v: int(v * sh["alpha"])))
        rgba.alpha_composite(layer)
    # 2. hard extrude
    ex = spec.get("extrude")
    if ex:
        acc = np.zeros((H, W), np.uint8)
        for i in range(int(ex["n"]), 0, -1):
            acc = np.maximum(acc, np.asarray(solid_mask(spec["stroke"], ex["dx"] * i, ex["dy"] * i)))
        layer = Image.new("RGBA", (W, H), (*tuple(ex.get("color", (0, 0, 0))), 0))
        layer.putalpha(Image.fromarray(acc))
        rgba.alpha_composite(layer)
    # 3. emphasis glow in the run's own hue
    g = e.get("glow")
    if g and any(it["emph"] for it in lay.items):
        gm = glyph_mask(int(g["stroke"]), only=True).filter(ImageFilter.GaussianBlur(g["blur"]))
        col = g.get("color") or next(it["fill"] for it in lay.items if it["emph"])
        layer = Image.new("RGBA", (W, H), (*tuple(col), 0))
        layer.putalpha(gm.point(lambda v: int(v * g["alpha"])))
        rgba.alpha_composite(layer)
    # 4. highlight panels
    for kind, col, pts, st in hl:
        if st:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.putalpha(_poly_mask(pts, W, H, grow=st))
            rgba.alpha_composite(layer)
        layer = Image.new("RGBA", (W, H), (*tuple(col), 0))
        layer.putalpha(_poly_mask(pts, W, H))
        rgba.alpha_composite(layer)
    # 5. glyphs
    d = ImageDraw.Draw(rgba)
    hl_text = (e.get("highlight") or {}).get("text")
    for it in lay.items:
        fill = tuple(hl_text) if (it["emph"] and hl_text and hl) else it["fill"]
        _draw_text(d, (it["x"], it["y"]), it["text"], it["font"], tr, it["size"],
                   fill=(*fill, 255), stroke_width=spec["stroke"], stroke_fill=(0, 0, 0, 255))
    gr = spec.get("gradient")
    if gr:
        fm = np.asarray(glyph_mask(0)).astype(np.float32) / 255.0
        arr = np.asarray(rgba).astype(np.float32)
        y0, y1 = lay.ink_bbox(0)[1], lay.ink_bbox(0)[3]
        ramp = np.interp(np.arange(H), [y0, y1], [gr[0], gr[1]]).astype(np.float32)[:, None]
        mult = 1.0 + (ramp - 1.0) * fm
        arr[..., :3] = np.clip(arr[..., :3] * mult[..., None], 0, 255)
        rgba = Image.fromarray(arr.astype(np.uint8), "RGBA")
    # 6. underline, stroked like the glyphs
    for kind, col, pts, st in ul:
        if st:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.putalpha(_poly_mask(pts, W, H, grow=st))
            rgba.alpha_composite(layer)
        layer = Image.new("RGBA", (W, H), (*tuple(col), 0))
        layer.putalpha(_poly_mask(pts, W, H))
        rgba.alpha_composite(layer)
    # ink: every solid layer at ink_stroke (+ the extrude's reach, + a HARD
    # shadow at its offset)
    ink = solid_mask(int(spec["ink_stroke"]))
    if sh and _hard(sh):
        ink = Image.fromarray(np.maximum(np.asarray(ink),
                                         np.asarray(solid_mask(int(spec["ink_stroke"]), sh["dx"], sh["dy"]))))
    if ex:
        acc = np.asarray(ink)
        for i in range(int(ex["n"]), 0, -1):
            acc = np.maximum(acc, np.asarray(solid_mask(int(spec["ink_stroke"]), ex["dx"] * i, ex["dy"] * i)))
        ink = Image.fromarray(acc)
    # 7. skew the whole line about its own centre
    if spec.get("skew"):
        a = np.tan(np.radians(spec["skew"]))
        bb = lay.ink_bbox(spec["stroke"])
        cy = (bb[1] + bb[3]) / 2.0
        coeffs = (1, a, -a * cy, 0, 1, 0)
        rgba = rgba.transform((W, H), Image.AFFINE, coeffs, resample=Image.BICUBIC)
        ink = ink.transform((W, H), Image.AFFINE, coeffs, resample=Image.BILINEAR)
    return rgba, ink


def describe(style):
    """One line per element for the build log."""
    out = {}
    for el in ("title", "kicker"):
        s = resolve(style, el)
        out[el] = {k: s.get(k) for k in _ELEMENT_KEYS if s.get(k) not in (None, {}, 0, 0.0)}
    return out


# The three things that made MONKEY_S read "generic and cheap" (his words,
# 2026-09-01; measured on the file the same evening, see NATHAN_RULES R45).
# Each is a property of the resolved preset, so the build can REPORT them.
# Reported, not refused: 'house' carries all three and stays the default
# until he locks a preset in. Whether a preset LOOKS cheap is his call and is
# NOT AUTOMATED - this is the list of the tells he has already named.
TELLS = {
    "glow": "coloured glow behind the key word",
    "heavy_outline": "outline >= 7 px with the shadow hidden inside it (outline is the only edge device)",
    "anton_lowercase": "Anton set in sentence case (the title is sentence case by R33)",
}


def tells(style):
    """Cheap tells a preset carries, as a sorted list of TELLS keys."""
    found = set()
    for el in ("title", "kicker"):
        s = resolve(style, el)
        if (s.get("emphasis") or {}).get("glow"):
            found.add("glow")
        sh = s.get("shadow") or {}
        st = int(s.get("stroke") or 0)
        if st >= 7 and (not sh or (abs(sh.get("dx", 0)) <= st and abs(sh.get("dy", 0)) <= st)):
            found.add("heavy_outline")
        if el == "title" and str(s.get("font", "")).startswith("Anton"):
            found.add("anton_lowercase")
    return sorted(found)


# -- selftest ---------------------------------------------------------------
def selftest():
    """(1) every preset renders both elements; (2) the underline and the
    highlight are IN the ink mask (a known-bad control: an underline placed
    over a face box must show up as ink there); (3) house == Thumb's constants;
    (4) extra_below reserves at least what the ink actually adds."""
    ok = True

    def check(label, good):
        nonlocal ok
        ok = ok and bool(good)
        print(f"  {'ok  ' if good else 'FAIL'} {label}")

    W, H = 1280, 720
    runs = [("YOUR OWNER ", (255, 255, 255), False), ("HATES YOU", (253, 1, 1), True)]
    for name in STYLES:
        for el, cap, maxw, hi in (("title", int(0.125 * H), int(0.965 * W), 190),
                                  ("kicker", int(0.167 * H), int(0.62 * W), 240)):
            spec = resolve(name, el)
            lay = fit(spec, runs, cap, maxw, hi, x=40, y=300)
            rgba, ink = render_runs(lay, spec, W, H, cap)
            a = np.asarray(rgba)[..., 3]
            m = np.asarray(ink) > 40
            check(f"{name}/{el}: renders ({int((a > 0).sum())} px), ink covers the fill",
                  (a > 0).sum() > 2000 and (m & (a > 200)).sum() >= 0.98 * (a > 200).sum())
    # the underline is ink: a control where it would land on a "face"
    spec = resolve("audit_ul", "kicker")
    lay = fit(spec, runs, int(0.167 * H), int(0.62 * W), 240, x=40, y=300)
    rgba, ink = render_runs(lay, spec, W, H, int(0.167 * H))
    spec0 = resolve("audit", "kicker")
    lay0 = fit(spec0, runs, int(0.167 * H), int(0.62 * W), 240, x=40, y=300)
    rgba0, ink0 = render_runs(lay0, spec0, W, H, int(0.167 * H))
    extra = (np.asarray(ink) > 40) & ~(np.asarray(ink0) > 40)
    ys, xs = np.where(extra)
    it = lay.items[1]
    baseline = it["y"] + it["font"].getmetrics()[0]
    ux1 = it["x"] + it["font"].getlength(it["text"])
    check("underline: adds ink under the emphasised run (below its baseline, inside its span)",
          extra.sum() > 500 and ys.mean() > baseline and ys.min() >= baseline - 12
          and xs.min() >= it["x"] - 20 and xs.max() <= ux1 + 20)
    face = np.zeros((H, W), bool)
    face[int(ys.min()):int(ys.max()) + 1, int(xs.min()):int(xs.max()) + 1] = True
    check("underline: a face box under the bar is HIT through the ink mask (control)",
          int(((np.asarray(ink) > 40) & face).sum()) > 0
          and int(((np.asarray(ink0) > 40) & face).sum()) < int(((np.asarray(ink) > 40) & face).sum()))
    check("underline: extra_below reserves the bar",
          extra_below(spec, int(0.167 * H)) >= (ys.max() - baseline) - 1)
    # highlight likewise (no preset carries it; the device stays available)
    spec = resolve(dict(STYLES["house"], kicker=dict(
        STYLES["house"]["kicker"],
        emphasis=dict(highlight=dict(pad_x=0.10, pad_y=0.10, skew=-8, stroke=6)))), "kicker")
    spec0 = resolve("house", "kicker")
    lay0 = fit(spec0, runs, int(0.167 * H), int(0.62 * W), 240, x=40, y=300)
    rgba0, ink0 = render_runs(lay0, spec0, W, H, int(0.167 * H))
    lay = fit(spec, runs, int(0.167 * H), int(0.62 * W), 240, x=40, y=300)
    rgba, ink = render_runs(lay, spec, W, H, int(0.167 * H))
    extra = (np.asarray(ink) > 40) & ~(np.asarray(ink0) > 40)
    check("highlight: the panel is ink", extra.sum() > 2000)
    # house agrees with thumb.py's constants
    try:
        import thumb as T
        check("house == thumb.py constants",
              T.TYPE_SHADOW == HOUSE_SHADOW and T.KICKER_STROKE == HOUSE_KICKER_STROKE
              and T.KICKER_EMPHASIS == HOUSE_EMPHASIS["alpha"]
              and T.KICKER_EMPHASIS_BLUR == HOUSE_EMPHASIS["blur"])
    except ImportError:
        check("house == thumb.py constants (thumb not importable here)", False)
    # a no-stroke style's halo is still ink where it is solid (R1 must see it)
    for name in ("audit", "client"):
        spec = resolve(name, "kicker")
        lay = fit(spec, runs, int(0.167 * H), int(0.62 * W), 240, x=40, y=300)
        rgba, ink = render_runs(lay, spec, W, H, int(0.167 * H))
        a = np.asarray(rgba)[..., 3]
        m = np.asarray(ink) > 40
        check(f"{name}: stroke 0, halo core (alpha>200) inside the ink mask",
              spec["stroke"] == 0 and (m & (a > 200)).sum() >= 0.98 * (a > 200).sum())
    # the _ul presets differ from their base ONLY by the underline
    for base, ul in (("audit", "audit_ul"), ("audit_now", "audit_now_ul"),
                     ("client", "client_ul"), ("crt", "crt_ul")):
        a_, b_ = resolve(base, "kicker"), resolve(ul, "kicker")
        ea, eb = dict(a_["emphasis"]), dict(b_["emphasis"])
        eb.pop("underline", None)
        a_["emphasis"], b_["emphasis"] = ea, eb
        check(f"{ul} == {base} + underline", a_ == b_ and "underline" in resolve(ul, "kicker")["emphasis"]
              and resolve(ul, "title") == resolve(base, "title"))
    # a variable font actually varies
    f9 = load_font(dict(font="Archivo-Var.ttf", axes={"Weight": 900, "Width": 125}), 100)
    f1 = load_font(dict(font="Archivo-Var.ttf", axes={"Weight": 100, "Width": 62}), 100)
    check("variable font: Black-Expanded is wider than Thin-Condensed",
          f9.getlength("HATES") > 1.5 * f1.getlength("HATES"))
    # cheap tells: the known-bad control is the house preset itself (all three
    # measured on MONKEY_S 2026-09-01); the clean controls carry none.
    check("tells: house carries glow + heavy_outline + anton_lowercase (known-bad control)",
          tells("house") == ["anton_lowercase", "glow", "heavy_outline"])
    for name in ("audit", "audit_ul", "client", "client_ul", "crt", "crt_ul"):
        check(f"tells: {name} carries none", tells(name) == [])
    check("tells: audit_now keeps Anton on the title and nothing else",
          tells("audit_now") == ["anton_lowercase"] and tells("audit_now_ul") == ["anton_lowercase"])
    print("TYPE_SELFTEST", "ALL_OK" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(0 if selftest() else 1)
