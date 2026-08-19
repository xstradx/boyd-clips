"""TTT gavel sting — the middle T strikes twice, the outer two drop in on the second hit.

Run:  blender -b --python sting_gavel.py

Concept: a T is already gavel-shaped, so the mark makes the courtroom gesture
itself rather than having one decorated onto it. The middle T arrives alone,
strikes twice (tap ... TAP), and the second, harder blow is what sets the other
two letters and cuts the star on. The logo is assembled BY the gavel, not
interrupted by it.

Craft notes, all of which are the difference between a blow and a glitch:
  * ANTICIPATION before each strike. Without a lift the strike reads as a
    dropped frame. Second lift is higher than the first.
  * The strike itself is 3 frames. Faster than the eye tracks — that is what
    makes it feel hard rather than animated.
  * FRAME SHAKE on contact, decaying over ~6 frames. This sells the weight far
    more than the strike does; without it the T just arrives.
  * Audio peaks ON the contact frame, never before. ITU-R BT.1359-1 puts
    audio-early unacceptability at +90 ms and a lead is far more noticeable
    than a lag. gen_gavel_audio.py authors its hits at the same frame numbers.

Geometry, colour management, easing and alpha idioms are lifted verbatim from
sting.py / BLENDER-CAPABILITY.md — proven on this 5.0.1 build, not re-derived.
"""
import math
import os
import sys

import bpy

# ---------------------------------------------------------------- timing (60 fps, 1-based)
FPS = 60
F_START, F_END = 1, 102                 # 102 f = 1.700 s

F_T2_IN_START   = 1                     # gavel T falls into frame
F_T2_IN_LAND    = 18
F_LIFT1_START   = 22                    # anticipation 1
F_LIFT1_TOP     = 28
F_HIT1          = 31                    # CONTACT 1  (audio hit1 lives here)
F_LIFT2_START   = 38                    # anticipation 2 — higher
F_LIFT2_TOP     = 46
F_HIT2          = 50                    # CONTACT 2  (audio hit2 lives here)
F_SIDES_LAND    = 58                    # outer T's finish dropping in
F_HOLD_FROM     = 60                    # dead hold to F_END

LIFT1_PX = 118.0                        # how far the gavel rises before hit 1
LIFT2_PX = 196.0                        # higher = harder-looking second blow
IN_FROM_PX = 1400.0                     # off the top of frame

# ---------------------------------------------------------------- motion / layout
LEAN_DEG = 9.08
K_REST = math.tan(math.radians(LEAN_DEG))
EASE_SETTLE = (0.42, 0.0, 0.58, 1.0)    # symmetric cubic — the one curve, everywhere
EASE_STRIKE = (0.55, 0.0, 1.0, 1.0)     # ease-IN only: accelerate into the block
EASE_LIFT   = (0.25, 0.0, 0.35, 1.0)

RES_X, RES_Y = 1920, 1080
MARK_W_PX = 680.0
STEM_W, BAR_W = 123.0, 373.7
Z_BAR_BOT, Z_BAR_TOP = 284.0, 382.0
STEM_CX = (249.2, 646.2, 1043.2)
STAR_CX, STAR_CZ, STAR_R = 1247.0, 364.5, 173.0

OUT = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(OUT, "renders", "seq_gavel")
WAV = os.path.join(OUT, "renders", "gavel_audio.wav")


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    return tuple(srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4))


GROUND = hex_lin("15181D")
INK = hex_lin("F2EEE3")
RED = hex_lin("D42B2B")


# ---------------------------------------------------------------- fcurve helpers (capability 1.7/1.8)
def get_fcurves(idd):
    ad = idd.animation_data
    return ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves


def find_fc(idd, path, index=-1):
    for fc in get_fcurves(idd):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            return fc
    raise RuntimeError("fcurve not found: %s[%d]" % (path, index))


def css_ease(fc, seg, x1, y1, x2, y2):
    k0, k1 = fc.keyframe_points[seg], fc.keyframe_points[seg + 1]
    k0.interpolation = 'BEZIER'
    for k in (k0, k1):
        k.handle_left_type = k.handle_right_type = 'FREE'
    f0, v0 = k0.co
    f1, v1 = k1.co
    df, dv = f1 - f0, v1 - v0
    k0.handle_right = (f0 + x1 * df, v0 + y1 * dv)
    k1.handle_left = (f0 + x2 * df, v0 + y2 * dv)
    fc.update()


# ---------------------------------------------------------------- geometry
def mark_extent(K):
    xs, zs = [], []
    for cx in STEM_CX:
        for (x0, z0) in ((cx - BAR_W / 2, Z_BAR_TOP), (cx + BAR_W / 2, Z_BAR_TOP),
                         (cx - STEM_W / 2, 0.0), (cx + STEM_W / 2, 0.0)):
            xs.append(x0 - K * z0)
            zs.append(z0)
    xs += [STAR_CX - STAR_R * math.sin(math.radians(72)),
           STAR_CX + STAR_R * math.sin(math.radians(72))]
    zs += [STAR_CZ - STAR_R * math.cos(math.radians(36)), STAR_CZ + STAR_R]
    return min(xs), max(xs), min(zs), max(zs)


_X0, _X1, _Z0, _Z1 = mark_extent(K_REST)
SCALE = MARK_W_PX / (_X1 - _X0)
OFF_X = (_X0 + _X1) / 2.0
OFF_Z = (_Z0 + _Z1) / 2.0


def r2w(x0, z0, K=K_REST):
    return ((x0 - K * z0) - OFF_X) * SCALE, (z0 - OFF_Z) * SCALE


def build_letter(cx):
    """One T: stem quad + crossbar quad, adjacent edges, no overlap."""
    verts, faces = [], []
    for (xl, xr, zb, zt) in ((cx - STEM_W / 2, cx + STEM_W / 2, 0.0, Z_BAR_BOT),
                             (cx - BAR_W / 2, cx + BAR_W / 2, Z_BAR_BOT, Z_BAR_TOP)):
        i = len(verts)
        for (x0, z0) in ((xl, zb), (xr, zb), (xr, zt), (xl, zt)):
            wx, wz = r2w(x0, z0)
            verts.append((wx, 0.0, wz))
        faces.append((i, i + 1, i + 2, i + 3))
    return verts, faces


def build_star():
    r_in = STAR_R * math.cos(math.radians(72)) / math.cos(math.radians(36))
    cwx, cwz = r2w(STAR_CX, STAR_CZ, 0.0)
    verts, faces = [(cwx, 0.0, cwz)], []
    for i in range(10):
        ang = math.radians(90 + i * 36)
        rad = STAR_R if i % 2 == 0 else r_in
        wx, wz = r2w(STAR_CX + rad * math.cos(ang), STAR_CZ + rad * math.sin(ang), 0.0)
        verts.append((wx, 0.0, wz))
    for i in range(10):
        faces.append((0, 1 + i, 1 + (i + 1) % 10))
    return verts, faces


def new_obj(name, verts, faces, y, sc):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = (0.0, y, 0.0)
    sc.collection.objects.link(ob)
    return ob


def flat_mat(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    e = nt.nodes.new('ShaderNodeEmission')
    e.inputs['Color'].default_value = (*rgb, 1.0)
    o = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(e.outputs['Emission'], o.inputs['Surface'])
    mat.surface_render_method = 'DITHERED'
    return mat


# ---------------------------------------------------------------- scene
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y
    sc.render.resolution_percentage = 100
    sc.render.fps, sc.render.fps_base = FPS, 1
    sc.frame_start, sc.frame_end = F_START, F_END
    sc.render.engine = 'BLENDER_EEVEE'
    if hasattr(sc.eevee, "taa_render_samples"):
        sc.eevee.taa_render_samples = 64
    sc.render.filter_size = 1.50

    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    sc.world = w

    cd = bpy.data.cameras.new("Cam")
    cd.type = 'ORTHO'
    cd.ortho_scale = float(RES_X)
    cd.clip_start, cd.clip_end = 1.0, 20000.0
    cam = bpy.data.objects.new("Cam", cd)
    cam.location = (0.0, -1000.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0, 0)   # -Y looking +Y; '-Y' align, never '+Y' (capability 4.1)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # ground plane, well behind everything
    g = new_obj("GROUND", [(-RES_X, 0, -RES_Y), (RES_X, 0, -RES_Y),
                           (RES_X, 0, RES_Y), (-RES_X, 0, RES_Y)],
                [(0, 1, 2, 3)], 400.0, sc)
    g.data.materials.append(flat_mat("M_GROUND", GROUND))

    ink = flat_mat("M_INK", INK)
    red = flat_mat("M_RED", RED)

    letters = []
    for i, cx in enumerate(STEM_CX):
        v, f = build_letter(cx)
        ob = new_obj("T%d" % (i + 1), v, f, 0.0, sc)
        ob.data.materials.append(ink)
        letters.append(ob)

    sv, sf = build_star()
    star = new_obj("STAR", sv, sf, -1.0, sc)
    star.data.materials.append(red)

    # everything hangs off SHAKE so one set of keys shakes the whole frame
    shake = bpy.data.objects.new("SHAKE", None)
    sc.collection.objects.link(shake)
    for ob in letters + [star]:
        ob.parent = shake

    return sc, letters, star, shake


# ---------------------------------------------------------------- animation
def key_z(ob, keys, eases):
    for f, v in keys:
        ob.location.z = v
        ob.keyframe_insert("location", index=2, frame=f)
    fc = find_fc(ob, "location", 2)
    for seg, e in enumerate(eases):
        if e:
            css_ease(fc, seg, *e)
    return fc


def animate(letters, star, shake):
    T1, T2, T3 = letters

    # --- the gavel: in, lift, STRIKE, lift higher, STRIKE ---------------------------
    key_z(T2, [
        (F_T2_IN_START, IN_FROM_PX),
        (F_T2_IN_LAND, 0.0),
        (F_LIFT1_START, 0.0),
        (F_LIFT1_TOP, LIFT1_PX),
        (F_HIT1, 0.0),
        (F_LIFT2_START, 0.0),
        (F_LIFT2_TOP, LIFT2_PX),
        (F_HIT2, 0.0),
        (F_END, 0.0),
    ], [EASE_SETTLE, None, EASE_LIFT, EASE_STRIKE, None, EASE_LIFT, EASE_STRIKE, None])

    # --- outer letters: held above frame, dropped by the second blow -----------------
    for ob, delay in ((T1, 0), (T3, 2)):        # 2-frame stagger reads as weight, not error
        key_z(ob, [
            (F_START, IN_FROM_PX),
            (F_HIT2 + delay, IN_FROM_PX),       # dead still until the blow lands
            (F_SIDES_LAND + delay, 0.0),
            (F_END, 0.0),
        ], [None, EASE_STRIKE, None])

    # --- star: hard cut on at the second impact -------------------------------------
    for f, v in ((F_START, False), (F_HIT2 - 1, False), (F_HIT2, True), (F_END, True)):
        star.hide_viewport = star.hide_render = v is False
        star.keyframe_insert("hide_render", frame=f)
        star.keyframe_insert("hide_viewport", frame=f)
    for fc in get_fcurves(star):
        for k in fc.keyframe_points:
            k.interpolation = 'CONSTANT'

    # --- frame shake: the thing that actually sells the weight -----------------------
    # decaying alternation, authored per-frame so contact reads as a jolt not a wobble
    shake_keys = [(F_START, 0.0)]
    for hit, amp in ((F_HIT1, 7.0), (F_HIT2, 15.0)):
        shake_keys.append((hit - 1, 0.0))
        a = amp
        for n in range(6):
            shake_keys.append((hit + n, -a if n % 2 == 0 else a))
            a *= 0.55
        shake_keys.append((hit + 6, 0.0))
    shake_keys.append((F_END, 0.0))
    for f, v in shake_keys:
        shake.location.z = v
        shake.keyframe_insert("location", index=2, frame=f)
    fc = find_fc(shake, "location", 2)
    for k in fc.keyframe_points:
        k.interpolation = 'LINEAR'      # linear = snap; bezier would make it float


def add_audio(sc):
    if not os.path.exists(WAV):
        print("!! no audio at %s — rendering silent" % WAV)
        return False
    if sc.sequence_editor is None:
        sc.sequence_editor_create()
    sc.sequence_editor.strips.new_sound(name="gavel", filepath=WAV, channel=1, frame_start=1)
    return True


def render(sc, has_audio):
    ims = sc.render.image_settings
    ims.file_format = 'PNG'
    ims.color_mode = 'RGB'
    ims.color_depth = '8'
    ims.color_management = 'OVERRIDE'                 # capability 5.2 — without this
    ims.view_settings.view_transform = 'Standard'     # the ink ships as mid-grey
    sc.render.film_transparent = False
    os.makedirs(SEQ, exist_ok=True)
    sc.render.filepath = os.path.join(SEQ, "g_")
    bpy.ops.render.render(animation=True)

    mp4 = os.path.join(OUT, "renders", "sting_gavel.mp4")
    # ORDER MATTERS (capability 1.3): media_type gates file_format, and codec must
    # be set before color_mode because the colour enum is computed from the codec.
    ims.media_type = 'VIDEO'
    ims.file_format = 'FFMPEG'
    ff = sc.render.ffmpeg
    ff.format = 'MPEG4'
    ff.codec = 'H264'
    ff.constant_rate_factor = 'HIGH'
    ims.color_mode = 'RGB'
    if has_audio:
        ff.audio_codec = 'AAC'
        ff.audio_bitrate = 192
    sc.render.filepath = mp4
    bpy.ops.render.render(animation=True)
    return mp4


def main():
    sc, letters, star, shake = build()
    animate(letters, star, shake)
    has_audio = add_audio(sc)
    mp4 = render(sc, has_audio)
    print("=== sting_gavel complete ===")
    print("frames %d-%d @ %d fps = %.4f s" % (F_START, F_END, FPS, (F_END - F_START + 1) / FPS))
    print("hit1 frame %d, hit2 frame %d, audio=%s" % (F_HIT1, F_HIT2, has_audio))
    print("mp4: %s" % mp4)


if __name__ == "__main__":
    main()
