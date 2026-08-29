"""Thumbnail cloned from the SHIPPED Thompson thumbnail's geometry.

Nathan, 2026-08-26: "okay now look at their placment all you have to do is
literally copy all of it but with the otther stuff". The reference is not a
competitor here — it is our own `READY-TO-POST/1_LONGFORM_thumbnail.jpg`, the
one that actually went up with the Thompson long-form. Every constant below was
measured off that JPEG, not chosen:

    canvas            1280 x 720
    type              ONE line, sentence case, not all-caps
                      x 23 -> 1072   (0.018 -> 0.838 W)
                      cap 71px = 0.0986 H (measured on the letter "Y", not the glyph box)
                      line runs x 23 -> 1072 = 1049px for 26 characters,
                      i.e. ~40px average advance
                      white run x 23-595, yellow run starts x 596 (0.466 W)
                      black stroke ~11px, plus a zero-offset black glow
    arrow             red, 105 x 76 px = 0.41% of frame
                      bbox x 466-570 (0.364-0.445 W), y 166-241 (0.231-0.335 H)
                      tip lower-left at ~(0.364 W, 0.323 H), pointing down-left
                      into the secondary subject
    construction      courtroom plate carrying the DEFENDANT on the left, the
                      judge cut out and composited on the right, bled off the
                      right edge, bottom-anchored. No seam, no plate, no bar.

Deliberately NOT carried over from the courtroomtime winner template measured on
2026-08-23: no bottom yellow plate, no red name plate. Those numbers are real but
they describe a different channel's house style; this file exists to match the
one thumbnail of ours that has actually shipped.

    python scripts/make_thumbnail_v5.py --plate room.png --cutout boyd.png \\
        --white "No monkey business" --yellow "in her court" \\
        --arrow 0.36,0.32 --out t.jpg
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
W, H = 1280, 720

YELLOW = (254, 251, 3)
WHITE = (255, 255, 255)
ARROW_RED = (253, 1, 1)

TEXT_X = 23                 # measured left inset
TEXT_TOP = 31               # measured top inset
TEXT_RIGHT = 1072           # measured right extent
CAP_PX = 71                 # measured cap height of the "Y" in "Your": 0.0986 H.
                            # The 141px first read was the whole glyph box including
                            # the yellow '?' descender, which is not the cap.
STROKE = 11                 # measured
GLOW_RADIUS = 20
ARROW_W, ARROW_H = 105, 76  # measured
SUBJECT_H = 0.90            # judge cut-out height as a fraction of H
SUBJECT_BLEED = 60          # px of the cut-out pushed past the right edge


def _font(px: int, path: str | None = None,
          weight: int | None = 900,
          width: int | None = None) -> ImageFont.FreeTypeFont:
    """The house face is Archivo Variable at weight 900, WIDTH 70.

    Identified by matching the shipped Thompson thumbnail rather than by
    picking one: its quote is 26 characters spanning 1049px at cap 71. Rendered
    at that width, Montserrat Black gives cap 52 and Archivo SemiCondensed
    SemiBold gives cap 68 — both far lighter than the real letterforms. Sweeping
    Archivo's weight and width axes, w900/wd70 lands on cap 71 exactly and
    matches the stroke weight by eye. Archivo SemiCond-SemiBold was the right
    proportion at the wrong weight, which is why the type read thin and cheap.
    """
    if path:
        f = ImageFont.truetype(path, px)
        axes = []
        if weight:
            axes.append(weight)
        if width:
            axes.append(width)
        if axes:
            try:
                f.set_variation_by_axes(axes)
            except Exception:
                pass
        return f
    # Prefer the baked static instance so the thumbnail and the burned-in
    # captions are provably the same face — libass cannot set a variable axis,
    # so the shorts can only use the static file.
    static = FONTS / "TTTHeadline-Regular.ttf"
    if static.is_file():
        return ImageFont.truetype(str(static), px)
    var = FONTS / "Archivo-Var.ttf"
    if var.is_file():
        f = ImageFont.truetype(str(var), px)
        try:
            f.set_variation_by_axes([weight or 900, width or 70])
            return f
        except Exception:
            pass
    var = FONTS / "Montserrat-Var.ttf"
    if var.is_file():
        f = ImageFont.truetype(str(var), px)
        try:
            f.set_variation_by_axes([900])
            return f
        except Exception:
            pass
    static = (ROOT / "research" / "blender" / "graphics" / "fonts_static"
              / "Montserrat-Bold.ttf")
    if static.is_file():
        return ImageFont.truetype(str(static), px)
    raise SystemExit(f"no Montserrat in {FONTS}")


def _headroom(img: Image.Image, frac: float) -> Image.Image:
    """Grow the plate upward by stretching its own top rows.

    Thompson's plate came from a wider courtroom camera, so the defendant sat
    low enough for a line of type to clear his head. Our source is a Zoom tile
    framed chest-up: measured on this build the defendant's face box starts at
    y~0.10 H, which leaves no band at all. This manufactures one out of the
    room's own ceiling rather than a flat colour, and _cover then anchors to the
    TOP so the band survives the crop.
    """
    if frac <= 0:
        return img
    add = int(round(img.height * frac))
    top = img.crop((0, 0, img.width, max(2, int(img.height * 0.05))))
    out = Image.new("RGB", (img.width, img.height + add))
    out.paste(top.resize((img.width, add), Image.LANCZOS), (0, 0))
    out.paste(img, (0, add))
    return out


def _cover(img: Image.Image, w: int, h: int, anchor_top: bool = False) -> Image.Image:
    s = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))),
                     Image.LANCZOS)
    x = (img.width - w) // 2
    y = 0 if anchor_top else (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _arrow_poly(tip_x: float, tip_y: float, angle_deg: float, scale: float):
    """The arrow's polygon in canvas pixels, so it can be tested before drawing."""
    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    px, py = -uy, ux
    aw, ah = ARROW_W * scale, ARROW_H * scale
    head_len, head_w, shaft_w = aw * 0.46, ah * 0.92, ah * 0.38

    def at(back, side):
        return (tip_x * W - ux * back + px * side,
                tip_y * H - uy * back + py * side)

    return [at(0, 0), at(head_len, head_w / 2), at(head_len, shaft_w / 2),
            at(aw, shaft_w / 2), at(aw, -shaft_w / 2),
            at(head_len, -shaft_w / 2), at(head_len, -head_w / 2)]


def _place_arrow(person: "Image.Image", head: tuple[float, float],
                 angle_deg: float, scale: float, exclude_top: float = 0.0):
    """Find a tip that puts the WHOLE arrow in empty space, nearest the head.

    Measured on the shipped Thompson thumbnail: 3,822 arrow pixels, **0 of them**
    overlapping the person matte — it sits entirely in the gap beside the
    defendant and points back into him. Mine had drifted onto his cheek because
    the tip was hand-set and then the crop changed underneath it.

    So this is now a constraint the builder satisfies, not a number I choose:
    walk outward from the head, and take the first position where the arrow's
    own polygon touches nobody.
    """
    import numpy as _np
    from PIL import ImageDraw as _D
    occ = _np.asarray(person, dtype=_np.uint8) > 24
    if exclude_top > 0:
        # The type is drawn AFTER the arrow, so a tip inside the caption band
        # gets painted over — the first fix produced an arrow of 803 visible
        # pixels against Thompson's 3,822, most of it buried under the glow.
        # Treat the caption band as occupied.
        occ[: int(H * exclude_top), :] = True
    hx, hy = head
    # A FULL ring, not just the upward angles. The first version searched only
    # above the head because Thompson's arrow comes down from empty space — but
    # measured on this composition the largest clear region sits DOWN-RIGHT of
    # him (r=98px at 0.62,0.44), and the search could never reach it. Assuming
    # the reference's geometry instead of measuring our own is what made it
    # refuse when there was in fact room.
    for radius in range(80, 520, 12):
        for deg in range(-180, 180, 10):
            a = math.radians(deg)
            tx = (hx + radius * math.cos(a)) / W
            ty = (hy + radius * math.sin(a)) / H
            if not (0.03 < tx < 0.97 and 0.05 < ty < 0.95):
                continue
            # Point BACK at the head from wherever it landed, so the arrow
            # always reads as indicating him rather than at a fixed angle.
            point_at = math.degrees(math.atan2(hy - ty * H, hx - tx * W))
            poly = _arrow_poly(tx, ty, point_at, scale)
            m = Image.new("L", (W, H), 0)
            _D.Draw(m).polygon(poly, fill=255)
            if not ((_np.asarray(m, dtype=_np.uint8) > 0) & occ).any():
                return (tx, ty), radius, point_at
    return None, None, None


def _arrow(canvas: Image.Image, tip_x: float, tip_y: float,
           angle_deg: float = 150.0, scale: float = 1.0) -> None:
    """Red arrow, tip at (tip_x, tip_y) as fractions of W,H, pointing down-left.

    Sized to the measured 105x76 box rather than to taste: the reference arrow
    is 0.41% of the frame and Audit's own 42K flop oversized theirs by 67%, so
    arrow area is a real constraint.
    """
    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    px, py = -uy, ux
    aw, ah = ARROW_W * scale, ARROW_H * scale
    head_len, head_w, shaft_w = aw * 0.46, ah * 0.92, ah * 0.38

    def at(back: float, side: float):
        return (tip_x * W - ux * back + px * side,
                tip_y * H - uy * back + py * side)

    pts = [at(0, 0), at(head_len, head_w / 2), at(head_len, shaft_w / 2),
           at(aw, shaft_w / 2), at(aw, -shaft_w / 2),
           at(head_len, -shaft_w / 2), at(head_len, -head_w / 2)]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=ARROW_RED + (255,),
                                  outline=(0, 0, 0, 255),
                                  width=max(3, int(round(3 * scale))))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), layer)
                 .convert("RGB"), (0, 0))


def _find_scrubs(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Locate the defendant by his JAIL SCRUBS, not by face detection.

    Face detection has failed on this docket three times in a row — on CARTHIEF
    it picked the attorney (who stands nearer the camera than his client) and on
    ROMERO it found no face at all. But every in-custody defendant on this
    docket wears county scrubs, and scrubs are the most saturated large garment
    in the room: the attorneys wear grey and navy suits, the room is beige.

    So: the biggest strongly-saturated blob in the lower two-thirds of the plate
    is the defendant's torso, and his head sits directly above it. That is a
    property of the subject matter rather than of a classifier, which is why it
    holds where the classifier did not.

    Returns the scrubs bbox in image pixels, or None.
    """
    import numpy as _np
    hsv = _np.asarray(img.convert("HSV"), dtype=_np.uint8)
    h, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    H, W = sat.shape
    # orange (~10-30) or the lighter blue scrubs (~130-160), well saturated and
    # not dark — a navy suit is saturated but dark, so `val` separates them.
    orange = (h > 5) & (h < 32)
    blue = (h > 125) & (h < 165)
    mask = (orange | blue) & (sat > 110) & (val > 80)
    mask[: int(H * 0.28), :] = False          # ignore ceiling and heads
    ys, xs = _np.where(mask)
    if len(xs) < (H * W) * 0.004:
        return None
    # densest column band, so a stray saturated object does not drag the centre
    hist, edges = _np.histogram(xs, bins=24, range=(0, W))
    peak = int(_np.argmax(hist))
    lo, hi = edges[max(0, peak - 2)], edges[min(len(edges) - 1, peak + 3)]
    sel = (xs >= lo) & (xs <= hi)
    if sel.sum() < 50:
        return None
    x0, x1 = int(xs[sel].min()), int(xs[sel].max())
    y0, y1 = int(ys[sel].min()), int(ys[sel].max())
    return x0, y0, x1 - x0, y1 - y0


def _headroom_a(a: Image.Image, frac: float) -> Image.Image:
    """_headroom for a single-channel alpha, so the mask stays registered."""
    if frac <= 0:
        return a
    add = int(round(a.height * frac))
    out = Image.new("L", (a.width, a.height + add), 0)
    out.paste(a, (0, add))
    return out


def _cover_a(a: Image.Image, w: int, h: int, anchor_top: bool = False) -> Image.Image:
    s = max(w / a.width, h / a.height)
    a = a.resize((max(1, round(a.width * s)), max(1, round(a.height * s))),
                 Image.LANCZOS)
    x = (a.width - w) // 2
    y = 0 if anchor_top else (a.height - h) // 2
    return a.crop((x, y, x + w, y + h))


def _depth(plate: Image.Image, blur: float, darken: float,
           desat: float, cool: float) -> Image.Image:
    """Push the background back, photographically.

    The court's Zoom feed is flat fluorescent light with no direction and no
    depth of field, so a cut-out pasted on it sits FLAT — subject and background
    are equally sharp, equally bright, equally warm, and the eye has nothing to
    separate them. Every one of these is something a real lens or a real room
    would do, which is the constraint: it has to still read as an unretouched
    frame, never as a composite.

      blur   - depth of field. A real portrait lens throws the background soft.
      darken - light falls off with distance; the back of a room is dimmer.
      desat  - so does colour saturation with distance (aerial perspective).
      cool   - and distant light reads cooler than the subject.
    """
    if blur > 0:
        plate = plate.filter(ImageFilter.GaussianBlur(blur))
    if darken > 0 or desat > 0 or cool > 0:
        import numpy as _np
        a = _np.asarray(plate, dtype=_np.float32)
        if darken > 0:
            a *= (1.0 - darken)
        if desat > 0:
            grey = a.mean(axis=2, keepdims=True)
            a = a * (1.0 - desat) + grey * desat
        if cool > 0:
            a[:, :, 2] *= (1.0 + cool * 0.5)      # lift blue
            a[:, :, 0] *= (1.0 - cool * 0.3)      # drop red
        plate = Image.fromarray(_np.clip(a, 0, 255).astype("uint8"), "RGB")
    return plate


def _vignette(img: Image.Image, strength: float, cx: float, cy: float) -> Image.Image:
    """Radial light falloff centred on the subject.

    Not a black frame border — a soft gradient, the way a single key light in a
    real room falls off toward the corners. Centred on the face rather than the
    canvas so it reads as light rather than as a filter.
    """
    if strength <= 0:
        return img
    import numpy as _np
    w, h = img.size
    yy, xx = _np.mgrid[0:h, 0:w].astype(_np.float32)
    dx = (xx - cx * w) / (w * 0.78)
    dy = (yy - cy * h) / (h * 0.78)
    r = _np.sqrt(dx * dx + dy * dy)
    mask = _np.clip(1.0 - strength * _np.clip(r - 0.30, 0, None) ** 1.6, 0.0, 1.0)
    a = _np.asarray(img, dtype=_np.float32) * mask[:, :, None]
    return Image.fromarray(_np.clip(a, 0, 255).astype("uint8"), "RGB")


def _rim(cut: Image.Image, amount: float) -> Image.Image:
    """A faint bright edge on the subject, as if lit from behind.

    This is the one move that most separates a cut-out from a paste-up: real
    subjects catch a little light on their contour. Built from the alpha's own
    edge so it follows the silhouette exactly, and kept low — an obvious rim is
    worse than none.
    """
    if amount <= 0:
        return cut
    import numpy as _np
    alpha = cut.getchannel("A")
    edge = alpha.filter(ImageFilter.FIND_EDGES).filter(
        ImageFilter.GaussianBlur(2.2))
    e = _np.asarray(edge, dtype=_np.float32) / 255.0
    a = _np.asarray(cut, dtype=_np.float32)
    lift = (e * amount * 255.0)[:, :, None]
    a[:, :, :3] = _np.clip(a[:, :, :3] + lift, 0, 255)
    return Image.fromarray(a.astype("uint8"), "RGBA")


def build(plate: Path, cutout: Path, white_part: str, yellow_part: str,
          out: Path, arrow: tuple[float, float] | None = (0.364, 0.323),
          subject_h: float = SUBJECT_H, cap_px: int = CAP_PX,
          font_path: str | None = None, font_weight: int | None = 900,
          font_width: int | None = 70,
          max_lines: int = 1, protect: tuple | None = None,
          plate_headroom: float = 0.0, force_top: bool = False,
          text_top_adjust: int = 0, arrow_angle: float = 150.0,
          arrow_scale: float = 1.0, glow_radius: float = GLOW_RADIUS,
          glow_alpha: float = 1.0, grade_cfg: dict | None = None,
          bg_blur: float = 0.0,
          bg_darken: float = 0.0, bg_desat: float = 0.0, bg_cool: float = 0.0,
          vignette: float = 0.0, rim: float = 0.0,
          plate_subject: Path | None = None, plate_pan: float = 0.0) -> Path:
    _plate_img = _headroom(Image.open(plate).convert("RGB"), plate_headroom)
    if plate_pan:
        # Pan the plate instead of moving anybody in it. Nathan asked to "scoot
        # the defendant closer to his attorney ... so everything just fits
        # better"; panning the frame changes what the crop includes and brings
        # him out from behind the judge's cut-out, and it is a pure crop offset,
        # so no pixel is invented and nothing can leave a seam. Actually
        # relocating a person would mean inpainting the hole behind him, which
        # is the one thing that would stop this reading as a real frame.
        pw, ph = _plate_img.size
        dx = int(round(pw * plate_pan))
        shifted = Image.new("RGB", (pw, ph))
        shifted.paste(_plate_img, (dx, 0))
        if dx > 0:
            shifted.paste(_plate_img.crop((0, 0, dx, ph)).transpose(
                Image.FLIP_LEFT_RIGHT), (0, 0))
        elif dx < 0:
            edge = _plate_img.crop((pw + dx, 0, pw, ph)).transpose(
                Image.FLIP_LEFT_RIGHT)
            shifted.paste(edge, (pw + dx, 0))
        _plate_img = shifted
    canvas = _cover(_plate_img, W, H, anchor_top=plate_headroom > 0)
    # Depth of field, done correctly: the two PEOPLE are at the same distance
    # from the camera, so a real lens focused on them would throw only the ROOM
    # soft. Blurring the whole plate softened the defendant — the very person
    # the arrow points at — which read as a mistake rather than as depth. So the
    # plate's own subject is matted out, the room behind is pushed back, and he
    # is composited back at full sharpness.
    if bg_blur > 0 and plate_subject is not None and Path(plate_subject).is_file():
        sharp = Image.open(plate_subject).convert("RGBA")
        sharp = _cover(_headroom(sharp.convert("RGB"), plate_headroom), W, H,
                       anchor_top=plate_headroom > 0)
        alpha = Image.open(plate_subject).convert("RGBA").getchannel("A")
        alpha = _headroom_a(alpha, plate_headroom)
        alpha = _cover_a(alpha, W, H, anchor_top=plate_headroom > 0)
        canvas = _depth(canvas, bg_blur, bg_darken, bg_desat, bg_cool)
        canvas.paste(sharp, (0, 0), alpha)
        print("  depth: room pushed back, plate subject kept sharp")
    else:
        canvas = _depth(canvas, bg_blur, bg_darken, bg_desat, bg_cool)

    # Judge cut out, bottom-anchored, bled off the right edge. Bottom-anchored
    # because a subject floating with air beneath them is the tell that it was
    # pasted; the reference has her cropped by the frame edge on two sides.
    cut = Image.open(cutout).convert("RGBA")
    bb = cut.getchannel("A").getbbox()
    if bb:
        cut = cut.crop(bb)
    th = int(H * subject_h)
    s = th / cut.height
    cut = cut.resize((max(1, round(cut.width * s)), th), Image.LANCZOS)
    cut = _rim(cut, rim)
    cut_x = W - cut.width + SUBJECT_BLEED
    canvas.paste(cut, (cut_x, H - cut.height), cut)

    # Everything the type must not touch: the judge's own alpha, plus the
    # defendant's box in the plate. Nathan, 2026-08-26: "try to fit 'in my
    # court!' without it overlapping on either of them" — so this is checked
    # against pixels, not eyeballed.
    # FACES, not whole silhouettes. Guarding the full cut-out alpha protects
    # hair too, and the shipped Thompson thumbnail's own line runs across the
    # top of Judge Boyd's hair — so an alpha guard rejects the very layout being
    # copied. Detected with OpenCV Haar on the composite, then padded.
    occupied = Image.new("L", (W, H), 0)
    od = ImageDraw.Draw(occupied)
    nonlocal_def = [None]
    try:
        import cv2
        import numpy as _np
        g = cv2.cvtColor(_np.asarray(canvas), cv2.COLOR_RGB2GRAY)
        g = cv2.equalizeHist(g)
        boxes = []
        for xml in ("haarcascade_frontalface_alt2.xml",
                    "haarcascade_profileface.xml"):
            cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
            for (fx, fy, fw, fh) in cc.detectMultiScale(g, 1.08, 5,
                                                        minSize=(70, 70)):
                boxes.append((fx, fy, fw, fh))
        # Only the TWO subjects, not every face in the room. Nathan's rule is
        # "not overlapping on either of them" — the defendant and the judge.
        # A bystander attorney standing behind the defendant was being detected
        # and protected, and his box alone shrank the clear band below what one
        # line of type needs. Keep the largest face left of the cut-out (the
        # defendant) and the largest inside it (the judge).
        keep = []
        left = [b for b in boxes if b[0] + b[2] / 2 < cut_x]
        right = [b for b in boxes if b[0] + b[2] / 2 >= cut_x]
        if left:
            keep.append(max(left, key=lambda b: b[2] * b[3]))
        if right:
            keep.append(max(right, key=lambda b: b[2] * b[3]))
        # Protect the FEATURES, not the whole head. Measured on the shipped
        # Thompson thumbnail: 18.8% of its text pixels sit inside Judge Boyd's
        # raw Haar face box (36% once padded) — the line crosses her hair and
        # forehead and stops above her eyes. A zero-overlap rule therefore
        # rejects the exact layout being copied. So the guarded region starts
        # a quarter of the way down the box, which is roughly the brow line.
        for (fx, fy, fw, fh) in keep:
            pad = int(fw * 0.12)
            brow = fy + int(fh * 0.25)
            od.rectangle([fx - pad, brow, fx + fw + pad, fy + fh + pad],
                         fill=255)
        print(f"  {len(boxes)} face(s) found, {len(keep)} protected "
              f"(defendant + judge)")
        # Remember the DEFENDANT box (the one left of the cut-out) so the arrow
        # can be aimed at a real face instead of a hardcoded point. A fixed tip
        # was landing on empty ceiling in all three of the 2026-08-27 builds,
        # because every docket frames its tiles differently.
        if left:
            nonlocal_def[0] = max(left, key=lambda b: b[2] * b[3])
    except Exception as e:                       # noqa: BLE001
        print(f"  face detect unavailable ({e}); falling back to the alpha")
        occupied.paste(cut.getchannel("A"), (cut_x, H - cut.height))
    if protect:
        od.rectangle([int(protect[0] * W), int(protect[1] * H),
                      int(protect[2] * W), int(protect[3] * H)], fill=255)

    # ---- arrow, aimed ---------------------------------------------------- #
    # Thompson's arrow sits up-and-right of the defendant's head and points
    # down-left into it (angle 150 deg). Reproduced here relative to the
    # MEASURED face rather than to fixed fractions.
    if arrow == "auto":
        scrubs = _find_scrubs(canvas)
        if scrubs is not None:
            sx, sy, sw, sh = scrubs
            # His head is above his shoulders: about one shoulder-width up from
            # the top of the scrubs, and the tip sits just off his temple.
            # The tip lands ON him, at the temple — Thompson's arrow points
            # INTO the subject, it does not hover above him. An earlier version
            # put the tip a head's height above the scrubs, which rendered as a
            # small mark floating in the ceiling with nothing under it.
            head_cx = sx + sw * 0.5
            head_cy = sy - sw * 0.30          # centre of the head, not above it
            tip_x = (head_cx + sw * 0.26) / W
            tip_y = max(0.12, head_cy / H)
            arrow = (tip_x, tip_y)
            print(f"  arrow from SCRUBS at x{sx}-{sx+sw} y{sy}: "
                  f"tip ({tip_x:.3f}, {tip_y:.3f})")
        else:
            fb = nonlocal_def[0]
            if fb is None:
                print("  no scrubs and no face found - arrow skipped")
                arrow = None
            else:
                fx, fy, fw, fh = fb
                arrow = ((fx + fw * 0.92) / W, (fy + fh * 0.12) / H)
                print(f"  no scrubs; fell back to a face box at {arrow}")
    # Rough height of the caption block, needed before the arrow is placed.
    lh_est = int(round(cap_px / 0.72 * 1.04))

    if arrow is not None:
        # Everyone in frame: the plate's people plus the judge's cut-out.
        person = Image.new("L", (W, H), 0)
        if plate_subject is not None and Path(plate_subject).is_file():
            pa = Image.open(plate_subject).convert("RGBA").getchannel("A")
            pa = _cover_a(_headroom_a(pa, plate_headroom), W, H,
                          anchor_top=plate_headroom > 0)
            person.paste(pa, (0, 0))
        person.paste(cut.getchannel("A"), (cut_x, H - cut.height),
                     cut.getchannel("A"))
        head_px = (arrow[0] * W, arrow[1] * H)
        ex = 0.0
        if force_top:
            # two lines at cap 71 plus stroke ~ 0.30 H, measured on this build
            ex = (TEXT_TOP + text_top_adjust + 2 * lh_est + 2 * STROKE) / H
        placed, rad, deg = _place_arrow(person, head_px, arrow_angle,
                                        arrow_scale, exclude_top=ex)
        if deg is not None:
            arrow_angle = deg
        if placed is None:
            print("  REFUSING the arrow: no clear space beside him for it")
            arrow = None
        else:
            if placed != arrow:
                print(f"  arrow moved to clear space: {arrow[0]:.3f},"
                      f"{arrow[1]:.3f} -> {placed[0]:.3f},{placed[1]:.3f} "
                      f"({rad}px out at {deg} deg)")
            arrow = placed
    if arrow is not None:
        _arrow(canvas, arrow[0], arrow[1], angle_deg=arrow_angle,
               scale=arrow_scale)
        print(f"  arrow: tip ({arrow[0]:.3f}, {arrow[1]:.3f}), "
              f"{arrow_angle:.0f} deg, x{arrow_scale:.2f} "
              f"({ARROW_W * arrow_scale:.0f}x{ARROW_H * arrow_scale:.0f}px, "
              f"{100 * (ARROW_W * arrow_scale) * (ARROW_H * arrow_scale) / (W * H):.2f}% of frame)")


    # ---- GRADE THE PICTURE, before any type is drawn --------------------
    #
    # This was the bug behind "the font is off and looks way lower quality".
    # The thumbnail was built with the type burned in, saved, and only THEN
    # graded — so the tone curve lifted the black stroke, the chroma median
    # filter softened the white/yellow letter boundary, and the unsharp mask
    # crisped compression noise around every glyph. `render.py` already
    # documents the rule for video: "Grading after `ass=` would lift the
    # caption white too ... it would clip the text edges and eat the black
    # outline that makes them readable." It applies identically here.
    if grade_cfg is not None:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "src"))
        from boydclips.thumbnail import grade_image
        canvas = grade_image(canvas, grade_cfg)
        print("  graded the picture BEFORE the type")

    if vignette > 0:
        # Centred on the judge's face, which is the subject the eye should land
        # on. Applied AFTER the subject and arrow, BEFORE the type, so the
        # caption keeps its full contrast.
        fb = nonlocal_def[0]
        vcx, vcy = 0.72, 0.45
        canvas = _vignette(canvas, vignette, vcx, vcy)

    # ---- type: shrink, then wrap, then PROVE it clears both subjects ----
    d = ImageDraw.Draw(canvas)
    words = [(w, WHITE) for w in white_part.split()]
    words += [(w, YELLOW) for w in yellow_part.split()]

    # The type box stops at the judge's left edge rather than at Thompson's
    # measured x=1072. In Thompson her cut-out sits far enough right that the
    # line clears her; ours is scaled larger, so wrapping to the same absolute
    # x would put words across her face no matter where the block sits.
    # Thompson's own line runs to x=1072 while the judge's cut-out begins well
    # left of that — it crosses her hair and shoulder and stops short of her
    # face. So the box keeps the measured width and the FACE guard below is what
    # enforces Nathan's rule; clipping to the silhouette instead was stricter
    # than the reference and forced the type down to cap 44px.
    text_right = TEXT_RIGHT

    def lay(cap):
        f = _font(round(cap / 0.72), font_path, font_weight, font_width)
        out_l, cur = [], []
        for wd, col in words:
            trial = " ".join(w for w, _ in cur + [(wd, col)])
            if cur and d.textlength(trial, font=f) > (text_right - TEXT_X):
                out_l.append(cur)
                cur = [(wd, col)]
            else:
                cur.append((wd, col))
        if cur:
            out_l.append(cur)
        return f, out_l

    cap = cap_px
    font, lines = lay(cap)
    while len(lines) > max_lines and cap > 40:
        cap = int(cap * 0.96)
        font, lines = lay(cap)
    lh = round(font.size * 1.04)

    # Slide the whole block down until it clears `occupied`, then refuse if it
    # never does rather than shipping type over a face.
    import numpy as _np
    occ = _np.asarray(occupied, dtype=_np.uint8) > 8
    block_h = lh * len(lines) + 2 * STROKE
    right = text_right
    placed = None
    if force_top:
        # Nathan, 2026-08-27: "i like 2 but move the captions all the way to the
        # top". That is Thompson's own placement, and Thompson accepts crossing
        # the hair and forehead to get it. So pin to y=TEXT_TOP and MEASURE what
        # it costs against the feature region rather than silently allowing it.
        placed = max(0, TEXT_TOP + text_top_adjust)
        blk = occ[placed:placed + block_h, max(0, TEXT_X - STROKE):right]
        print(f"  pinned to y{TEXT_TOP}; {int(blk.sum())}px of the block's box "
              f"falls inside a guarded feature region "
              f"({blk.sum() / max(1, blk.size) * 100:.1f}% of it)")
    for cand in ([] if force_top else range(TEXT_TOP, H - block_h)):
        if not occ[cand:cand + block_h, max(0, TEXT_X - STROKE):right].any():
            placed = cand
            break
    if placed is None:
        rows = occ[:, max(0, TEXT_X - STROKE):right].any(axis=1)
        free = int((~rows).sum())
        print(f"  DEBUG cap={cap} lines={len(lines)} block_h={block_h} "
              f"box x{TEXT_X}-{right} free_rows={free}/{H}")
        raise RuntimeError("no band clears both subjects - shorten the copy, "
                           "drop the cut-out height, or use a narrower face")
    top = placed + STROKE
    if top != TEXT_TOP:
        print(f"  type moved y {TEXT_TOP} -> {top} to clear both subjects")

    # Glow, measured against the reference rather than chosen.
    #
    # A radius-20 glow composited at FULL black put 33.4% of the text band into
    # near-black, against 18.4% on the shipped Thompson thumbnail — nearly
    # double, and only 13.4% of our band was bright against his 30.4%. That is
    # what made the type read heavy and muddy: the stroke is right, the glow was
    # doing the damage. It is a separation aid, not an outline; it should sit
    # under the type, not swallow it.
    if glow_alpha > 0:
        glow = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(glow)
        for i, ln in enumerate(lines):
            gd.text((TEXT_X, top + i * lh), " ".join(w for w, _ in ln),
                    font=font, fill=255, stroke_width=STROKE, stroke_fill=255)
        g = glow.filter(ImageFilter.GaussianBlur(glow_radius))
        g = g.point(lambda v: int(v * glow_alpha))
        canvas.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), g)

    d = ImageDraw.Draw(canvas)
    for i, ln in enumerate(lines):
        x = TEXT_X
        for wd, col in ln:
            d.text((x, top + i * lh), wd, font=font, fill=col,
                   stroke_width=STROKE, stroke_fill=(0, 0, 0))
            x += d.textlength(wd + " ", font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=96, subsampling=0)
    print(f"{out.name}: cap {cap}px ({cap / H:.4f} H), {len(lines)} line(s), "
          f"top y{top}, font {Path(font.path).name if hasattr(font, 'path') else '?'}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", required=True, type=Path)
    ap.add_argument("--cutout", required=True, type=Path)
    ap.add_argument("--white", required=True)
    ap.add_argument("--yellow", required=True)
    ap.add_argument("--arrow", default="auto",
                    help='"auto" aims at the detected defendant face, or give '
                         'cx,cy fractions for the tip')
    ap.add_argument("--no-arrow", action="store_true")
    ap.add_argument("--subject-h", type=float, default=SUBJECT_H)
    ap.add_argument("--cap", type=int, default=CAP_PX)
    ap.add_argument("--font", default=None)
    ap.add_argument("--weight", type=int, default=900)
    ap.add_argument("--width", type=int, default=70,
                    help="Archivo width axis; 70 matches the shipped Thompson")
    ap.add_argument("--max-lines", type=int, default=1)
    ap.add_argument("--plate-headroom", type=float, default=0.0)
    ap.add_argument("--grade", type=float, default=None,
                    help="curve_strength; grades the PICTURE before the type")
    ap.add_argument("--contrast", type=float, default=None)
    ap.add_argument("--glow-radius", type=float, default=GLOW_RADIUS)
    ap.add_argument("--glow-alpha", type=float, default=1.0,
                    help="0 = no glow, 1 = solid black glow")
    ap.add_argument("--plate-pan", type=float, default=0.0,
                    help="pan the plate as a fraction of its width; positive "
                         "moves its content RIGHT")
    ap.add_argument("--plate-subject", default=None, type=Path,
                    help="RGBA matte of the plate's own subject; kept sharp "
                         "while the room behind is blurred")
    ap.add_argument("--bg-blur", type=float, default=0.0)
    ap.add_argument("--bg-darken", type=float, default=0.0)
    ap.add_argument("--bg-desat", type=float, default=0.0)
    ap.add_argument("--bg-cool", type=float, default=0.0)
    ap.add_argument("--vignette", type=float, default=0.0)
    ap.add_argument("--rim", type=float, default=0.0)
    ap.add_argument("--arrow-angle", type=float, default=150.0,
                    help="degrees; 150 points down-left, 210 down-right, "
                         "90 straight down")
    ap.add_argument("--arrow-scale", type=float, default=1.0,
                    help="multiplier on the measured 105x76 reference arrow")
    ap.add_argument("--top-adjust", type=int, default=0,
                    help="px to nudge the pinned type up (negative) or down")
    ap.add_argument("--force-top", action="store_true",
                    help="pin the type to the measured Thompson inset")
    ap.add_argument("--protect", default=None,
                    help="x0,y0,x1,y1 fractions of the OTHER subject to avoid")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    if a.no_arrow:
        tip = None
    elif a.arrow == "auto":
        tip = "auto"
    else:
        tip = tuple(float(v) for v in a.arrow.split(","))
    prot = tuple(float(v) for v in a.protect.split(",")) if a.protect else None
    build(a.plate, a.cutout, a.white, a.yellow, a.out, arrow=tip,
          subject_h=a.subject_h, cap_px=a.cap, font_path=a.font,
          font_weight=a.weight, font_width=a.width,
          max_lines=a.max_lines, protect=prot,
          plate_headroom=a.plate_headroom, force_top=a.force_top,
          text_top_adjust=a.top_adjust, arrow_angle=a.arrow_angle,
          arrow_scale=a.arrow_scale, bg_blur=a.bg_blur, bg_darken=a.bg_darken,
          bg_desat=a.bg_desat, bg_cool=a.bg_cool, vignette=a.vignette,
          rim=a.rim, plate_subject=a.plate_subject, plate_pan=a.plate_pan,
          glow_radius=a.glow_radius, glow_alpha=a.glow_alpha,
          grade_cfg=(None if a.grade is None else
                     {"curve_strength": a.grade,
                      **({} if a.contrast is None else {"contrast": a.contrast})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
