"""TTT sting v2 — the gavel strike LAUNCHES the star.

Run:  blender -b --python sting_v2.py

CONCEPT (Nathan's second option, chosen over the first on jury evidence).
The three Ts track in from the left. The star is already there, lying flat on
the ground to the left of the first T. The first T lifts and strikes twice; the
second blow catches the star, which flips up, spins across the mark and lands in
its place. Then everything fades for the cut into the video.

Why this one and not "everything flies in, then a gavel hits": every published
award citation for an ident names ONE mechanism, and the Motion Awards rubric
bands 5-6 as "competent but nothing distinctive - does not advance". Things
arriving and a gavel sounding are two events that merely co-occur. A strike that
LAUNCHES something is one event with a cause. Causation is an idea; accompaniment
is a beat.

TIMING IS MEASURED, NOT INVENTED. Nine broadcast idents were pulled frame by
frame (Netflix, 20th Century, HBO Max, Court TV, ID, Law & Order, Dateline,
ESPN, Marvel). What that measurement changed versus v1:

  * NO OVERSHOOT. 0 of 7 references with a trackable settle overshoot at all.
    They decelerate exponentially with a long asymptotic tail (per-frame delta
    ratio ~0.87). Snap-back is a template tell, not broadcast practice.
  * NO MOTION BLUR. The two pure-letterform references (Dateline, ESPN) render
    a 3px edge whether moving 31px/frame or standing still. Only Court TV's
    PHOTOGRAPHIC card blurs. v1's real fault was not missing blur - it was
    moving 125px/frame at 60fps, roughly 8x faster in absolute screen speed than
    any professional reference.
  * STAGGER +5 FRAMES between elements (measured +4,+5,+8,+5), each travelling
    4-6 frames. v1 had no stagger, so the letters read as one rigid object.
  * HOLD ~20f, EXIT fade ~14f. v1 dead-held to the end with no exit at all.

30 fps, not 60: every reference measured came in at 24-30, and the channel's own
longform renders at 30, so this concatenates without a rate conversion.

THE AUDIO LEADS THE PICTURE, not the other way round. We use a real CC0 gavel
recording whose two strikes are 322 ms apart - measured, and its two blows are
within 1.1 dB of each other, so the "second hit is softer" bounce model is
simply wrong for a deliberate double strike. 322 ms at 30 fps is 9.66 frames; we
place contacts 10 frames apart, an 11 ms drift that sits far inside the 45 ms
ITU-R BT.1359 detectability window for audio leading picture.

Geometry, colour management, slotted-action and alpha idioms are lifted verbatim
from sting_gavel.py / BLENDER-CAPABILITY.md - proven on this 5.0.1 build.
Colour management is forced to Standard: Blender 5 defaults to AgX, which renders
pure red as R0.855 G0.220 B0.125 and pushes it toward pale salmon as it
brightens. The star would get pinker the harder we emphasised it.
"""
import math
import os
import sys

import bpy

# ---------------------------------------------------------------- timing (30 fps, 1-based)
FPS = 30
F_START, F_END = 1, 78                  # 78 f = 2.600 s

# letters track in from the left, staggered +5, travelling 6 each
F_T_IN = ((1, 7), (6, 12), (11, 17))

F_LIFT1_START = 18                      # anticipation - without a lift the
F_LIFT1_TOP   = 23                      # strike reads as a dropped frame
F_HIT1        = 26                      # CONTACT 1
F_LIFT2_START = 28
F_LIFT2_TOP   = 34                      # second lift is higher
F_HIT2        = 36                      # CONTACT 2 - 10f after hit 1 (322 ms)

F_STAR_LAND   = 54                      # 18f flight
F_HOLD_TO     = 64                      # ~20f lock (median of the references)
F_FADE_TO     = 78                      # 14f fade (median exit)

LIFT1_PX = 96.0
LIFT2_PX = 168.0

# SHORT travel, and this is the correction that matters most.
# v1 flew elements 1500px in a handful of frames — 125 px/frame, roughly 8x the
# absolute screen speed of any professional reference. Re-reading the reference
# data there are two distinct regimes, and conflating them is what produced that
# number: Netflix's individual elements travel ~56px in 4 frames (~19 px/frame),
# while the 15-32 frame moves are whole-LOCKUP settles, not element entrances.
# Elements enter from just outside their resting place; they do not cross the
# frame. Paired with an alpha fade over the same window so a short move reads as
# an arrival rather than a pop.
IN_FROM_PX = 150.0

# ---------------------------------------------------------------- easing
# Measured against the references: peak velocity at frame 0, 50% of distance by
# ~21% of time. Blender's factory AUTO_CLAMPED puts peak velocity at 52% - dead
# centre - with a peak/average ratio of 1.50; an asymmetric ease-out reaches
# 4.84. That difference in attack is the whole distance between a snap and a
# drift.
#
# easeOutCubic rather than easeOutExpo: expo's peak/average of ~4.8 over a
# 6-frame entrance would put instantaneous speed back above 100 px/frame, which
# is the exact fault being fixed. Cubic keeps the asymmetric attack while
# holding the peak near the measured range.
EASE_ARRIVE = (0.33, 1.0, 0.68, 1.0)
EASE_STRIKE = (0.70, 0.0, 1.0, 1.0)     # accelerate INTO the block, no ease-out
EASE_LIFT   = (0.25, 0.0, 0.35, 1.0)
EASE_FLIGHT = (0.22, 0.9, 0.35, 1.0)

LEAN_DEG = 9.08
K_REST = math.tan(math.radians(LEAN_DEG))

RES_X, RES_Y = 1920, 1080
MARK_W_PX = 680.0
STEM_W, BAR_W = 123.0, 373.7
Z_BAR_BOT, Z_BAR_TOP = 284.0, 382.0
STEM_CX = (249.2, 646.2, 1043.2)
STAR_CX, STAR_CZ, STAR_R = 1247.0, 364.5, 173.0

# Where the star lies before it is struck: on the ground at the foot of the first
# T, tucked just left of its stem. It has to sit UNDER T1's descent path or the
# strike and the launch are two unrelated events happening near each other —
# which is exactly the accompaniment-instead-of-causation failure this concept
# exists to avoid. Parked further left it never gets hit.
STAR_REST_X = 175.0
STAR_REST_Z = 44.0
STAR_LIE_DEG = 68.0                     # foreshortened, still readable as a star
STAR_SPINS = 2

OUT = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(OUT, "renders", "seq_v2")
WAV = os.path.join(OUT, "renders", "sting_v2.wav")
MP4 = os.path.join(OUT, "renders", "sting_v2.mp4")


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    return tuple(srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4))


GROUND = hex_lin("15181D")
INK = hex_lin("F2EEE3")
RED = hex_lin("D42B2B")


# ---------------------------------------------------------------- fcurve helpers (capability 2.5)
def get_fcurves(idd):
    ad = idd.animation_data
    return ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves


def find_fc(idd, path, index=-1):
    for fc in get_fcurves(idd):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            return fc
    raise RuntimeError("fcurve not found: %s[%d]" % (path, index))


def css_ease(fc, seg, x1, y1, x2, y2):
    """Apply a CSS cubic-bezier to ONE segment without disturbing its neighbours.

    BUG THIS FIXES: the original set `handle_left_type = handle_right_type =
    'FREE'` on BOTH keys, but only ever assigned two of the four handles. The two
    it left alone kept whatever stale position they held — and because FREE stops
    Blender recomputing them, that stale handle then bent the ADJACENT segment.
    On a long hold it can swing the value far enough to push an element out of
    frame, which is exactly what happened in the graphics kit (text vanished for
    a 100-frame hold).

    So: only mark FREE the two handles actually being authored, and level the
    outer handles at the key's own value so a hold stays a hold.
    """
    k0, k1 = fc.keyframe_points[seg], fc.keyframe_points[seg + 1]
    k0.interpolation = 'BEZIER'
    f0, v0 = k0.co
    f1, v1 = k1.co
    df, dv = f1 - f0, v1 - v0

    k0.handle_right_type = 'FREE'
    k0.handle_right = (f0 + x1 * df, v0 + y1 * dv)
    k1.handle_left_type = 'FREE'
    k1.handle_left = (f0 + x2 * df, v0 + y2 * dv)

    # outer handles: flat at the key value, so an untouched neighbouring segment
    # holds instead of swinging
    if k0.handle_left_type == 'FREE':
        k0.handle_left = (f0 - max(1.0, df * 0.25), v0)
    if k1.handle_right_type == 'FREE':
        k1.handle_right = (f1 + max(1.0, df * 0.25), v1)
    fc.update()


def key_chan(ob, path, index, keys, eases):
    """Key one channel, then apply a CSS-style ease per SEGMENT.

    Keys on the same frame collapse (T1 launches on F_START, so its hold key and
    its launch key are the same frame). A collapsed segment has no duration and
    therefore no ease, so the ease list has to be re-aligned to the surviving
    segments — otherwise every ease lands one segment late and the travel curve
    silently gets the hold's easing.
    """
    eases = list(eases) + [None] * max(0, len(keys) - 1 - len(eases))
    dk, de = [keys[0]], []
    for i in range(1, len(keys)):
        f, v = keys[i]
        if f == dk[-1][0]:
            dk[-1] = (f, v)          # same frame: last value wins, ease dropped
            continue
        dk.append((f, v))
        de.append(eases[i - 1])

    for f, v in dk:
        if path == "location":
            ob.location[index] = v
        elif path == "rotation_euler":
            ob.rotation_euler[index] = v
        else:
            ob.scale[index] = v
        ob.keyframe_insert(path, index=index, frame=f)

    fc = find_fc(ob, path, index)
    for seg, e in enumerate(de):
        if e and seg + 1 < len(fc.keyframe_points):
            css_ease(fc, seg, *e)
    return fc


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
    """Star built around its OWN origin so it can spin about its centre."""
    r_in = STAR_R * math.cos(math.radians(72)) / math.cos(math.radians(36))
    verts, faces = [(0.0, 0.0, 0.0)], []
    for i in range(10):
        ang = math.radians(90 + i * 36)
        rad = STAR_R if i % 2 == 0 else r_in
        verts.append((rad * math.cos(ang) * SCALE, 0.0, rad * math.sin(ang) * SCALE))
    for i in range(10):
        faces.append((0, 1 + i, 1 + (i + 1) % 10))
    return verts, faces


def new_obj(name, verts, faces, y, sc, loc=(0.0, 0.0)):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = (loc[0], y, loc[1])
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


def fade_mat(name, rgb):
    """Flat emission that can also be faded in. Returns (material, fac socket).

    A 150px entrance is short enough that a hard-edged element would read as
    popping into existence rather than arriving, so opacity carries the entrance
    alongside the translation — which is what the Netflix reference does (its
    elements are a mask reveal, not a long move). EEVEE needs BLENDED rather than
    DITHERED for the alpha to composite smoothly instead of stippling.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    e = nt.nodes.new('ShaderNodeEmission')
    e.inputs['Color'].default_value = (*rgb, 1.0)
    mx = nt.nodes.new('ShaderNodeMixShader')
    o = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(e.outputs['Emission'], mx.inputs[2])
    nt.links.new(mx.outputs[0], o.inputs['Surface'])
    mat.surface_render_method = 'BLENDED'
    return mat, mx.inputs[0]


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
    cam.rotation_euler = (math.radians(90), 0, 0)   # '-Y' align; '+Y' mirrors (capability 4.1)
    sc.collection.objects.link(cam)
    sc.camera = cam

    g = new_obj("GROUND", [(-RES_X, 0, -RES_Y), (RES_X, 0, -RES_Y),
                           (RES_X, 0, RES_Y), (-RES_X, 0, RES_Y)],
                [(0, 1, 2, 3)], 400.0, sc)
    g.data.materials.append(flat_mat("M_GROUND", GROUND))

    red = flat_mat("M_RED", RED)

    # one material PER letter — they fade in on their own stagger, so they
    # cannot share a single material's alpha
    letters, facs = [], []
    for i, cx in enumerate(STEM_CX):
        v, f = build_letter(cx)
        ob = new_obj("T%d" % (i + 1), v, f, 0.0, sc)
        mat, fac = fade_mat("M_INK_%d" % (i + 1), INK)
        ob.data.materials.append(mat)
        letters.append(ob)
        facs.append(fac)

    sv, sf = build_star()
    home_x, home_z = r2w(STAR_CX, STAR_CZ, 0.0)
    star = new_obj("STAR", sv, sf, -1.0, sc, loc=(home_x, home_z))
    star.data.materials.append(red)

    shake = bpy.data.objects.new("SHAKE", None)
    sc.collection.objects.link(shake)
    for ob in letters + [star]:
        ob.parent = shake

    return sc, letters, star, shake, (home_x, home_z), facs


# ---------------------------------------------------------------- animation
def animate(letters, star, shake, home, facs):
    T1, T2, T3 = letters
    home_x, home_z = home

    # --- letters track in from the left, staggered ---------------------------
    # Travel 6 frames each at +5 stagger, so the last locks at f17 (~22% of the
    # piece). Under 80ms of stagger they stick together as one object; over
    # 150ms they disintegrate into unrelated parts.
    for ob, fac, (f_in, f_land) in zip(letters, facs, F_T_IN):
        key_chan(ob, "location", 0,
                 [(F_START, -IN_FROM_PX), (f_in, -IN_FROM_PX), (f_land, 0.0)],
                 [None, EASE_ARRIVE])
        # opacity carries the entrance with the translation
        for f, v in ((F_START, 0.0), (f_in, 0.0), (f_land, 1.0), (F_END, 1.0)):
            fac.default_value = v
            fac.keyframe_insert("default_value", frame=f)

    # --- the gavel: lift, STRIKE, lift higher, STRIKE ------------------------
    # The strike is 3 frames and eases IN only. Faster than the eye tracks is
    # what makes it read as a blow rather than an animation.
    key_chan(T1, "location", 2, [
        (F_LIFT1_START, 0.0),
        (F_LIFT1_TOP, LIFT1_PX),
        (F_HIT1, 0.0),
        (F_LIFT2_START, 0.0),
        (F_LIFT2_TOP, LIFT2_PX),
        (F_HIT2, 0.0),
        (F_END, 0.0),
    ], [EASE_LIFT, EASE_STRIKE, None, EASE_LIFT, EASE_STRIKE, None])

    # --- the star: lying flat, struck, flips and spins into place ------------
    # key_chan writes these straight onto ob.location, so they are ABSOLUTE world
    # positions, not offsets from the rest pose. Passing 0.0 as the "home" value
    # parks the star at the world origin — the centre of the mark — instead of
    # its slot to the right of T3.
    star_rest_wx, star_rest_wz = r2w(STAR_REST_X, STAR_REST_Z, 0.0)

    # horizontal travel: launched hard by the blow, decelerating into its slot
    key_chan(star, "location", 0,
             [(F_START, star_rest_wx), (F_HIT2, star_rest_wx),
              (F_STAR_LAND, home_x), (F_END, home_x)],
             [None, EASE_FLIGHT, None])

    # vertical: a real arc, peaking a little past halfway through the flight
    apex_f = F_HIT2 + int((F_STAR_LAND - F_HIT2) * 0.55)
    key_chan(star, "location", 2,
             [(F_START, star_rest_wz), (F_HIT2, star_rest_wz),
              (apex_f, home_z + 230.0),
              (F_STAR_LAND, home_z), (F_END, home_z)],
             [None, (0.15, 0.85, 0.4, 1.0), (0.6, 0.0, 0.85, 1.0), None])

    # flip up out of the ground plane: foreshortened -> facing camera
    key_chan(star, "rotation_euler", 0,
             [(F_START, math.radians(STAR_LIE_DEG)),
              (F_HIT2, math.radians(STAR_LIE_DEG)),
              (F_STAR_LAND, 0.0), (F_END, 0.0)],
             [None, EASE_FLIGHT, None])

    # and spin in the screen plane while it travels
    key_chan(star, "rotation_euler", 1,
             [(F_START, 0.0), (F_HIT2, 0.0),
              (F_STAR_LAND, math.radians(360 * STAR_SPINS)),
              (F_END, math.radians(360 * STAR_SPINS))],
             [None, EASE_FLIGHT, None])

    # --- frame shake on each contact -----------------------------------------
    # This sells the weight far more than the strike does. Decays over ~5 frames
    # at 30fps. Amplitudes are EQUAL because the measured recording's two blows
    # are within 1.1 dB - a judge's double strike is deliberate, not a bounce.
    shake_keys = [(F_START, 0.0)]
    for hit in (F_HIT1, F_HIT2):
        amp = 11.0
        shake_keys.append((hit, 0.0))
        for i, mult in enumerate((1.0, -0.55, 0.28, -0.12), start=1):
            shake_keys.append((hit + i, amp * mult))
        shake_keys.append((hit + 5, 0.0))
    shake_keys.append((F_END, 0.0))
    seen = set()
    ded = []
    for f, v in shake_keys:
        if f not in seen:
            seen.add(f)
            ded.append((f, v))
    for f, v in ded:
        shake.location.z = v
        shake.keyframe_insert("location", index=2, frame=f)
    for k in find_fc(shake, "location", 2).keyframe_points:
        k.interpolation = 'LINEAR'       # linear = snap; bezier would float it


def add_fade(sc):
    """14-frame fade to black - the median exit across the measured references.

    Done in the compositor rather than by animating material alpha, so it fades
    the ground plane with everything else and leaves a clean black frame to cut
    from.
    """
    # Blender 5.0 compositor shape: a node GROUP assigned to
    # scene.compositing_node_group. Scene.node_tree and CompositorNodeMixRGB
    # are both gone (capability doc 1.12).
    ng = bpy.data.node_groups.new("Fade", "CompositorNodeTree")
    ng.interface.new_socket(name="Image", in_out='OUTPUT',
                            socket_type='NodeSocketColor')
    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.scene = sc                                    # mandatory in 5.0
    go = ng.nodes.new("NodeGroupOutput")

    mix = ng.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.blend_type = 'MIX'

    def sock(node, ident, outputs=False):
        pool = node.outputs if outputs else node.inputs
        return [s for s in pool if s.identifier == ident][0]

    ng.links.new(rl.outputs['Image'], sock(mix, 'A_Color'))
    sock(mix, 'B_Color').default_value = (0.0, 0.0, 0.0, 1.0)
    ng.links.new(sock(mix, 'Result_Color', outputs=True), go.inputs['Image'])
    sc.compositing_node_group = ng

    fac = sock(mix, 'Factor_Float')
    for f, v in ((F_START, 0.0), (F_HOLD_TO, 0.0), (F_FADE_TO, 1.0)):
        fac.default_value = v
        fac.keyframe_insert("default_value", frame=f)


def render(sc, seq_dir, mp4_path):
    os.makedirs(os.path.dirname(seq_dir), exist_ok=True)
    ims = sc.render.image_settings

    # Force Standard: AgX (the 5.x default) desaturates saturated reds toward
    # white as they brighten, so the star would render salmon, not D42B2B.
    ims.color_management = 'OVERRIDE'
    ims.view_settings.view_transform = 'Standard'
    ims.view_settings.look = 'None'

    ims.media_type = 'IMAGE'
    ims.file_format = 'PNG'
    ims.color_mode = 'RGB'
    sc.render.filepath = os.path.join(seq_dir, "v_")
    bpy.ops.render.render(animation=True)
    return seq_dir


def main():
    sc, letters, star, shake, home, facs = build()
    animate(letters, star, shake, home, facs)
    add_fade(sc)
    render(sc, SEQ, MP4)
    print("=" * 60)
    print("frames %d-%d @ %d fps = %.3f s" % (F_START, F_END, FPS,
                                              (F_END - F_START + 1) / FPS))
    print("letters land: %s" % (", ".join("f%d" % b for _, b in F_T_IN),))
    print("hit1 f%d  hit2 f%d  (delta %d f = %.0f ms)" % (
        F_HIT1, F_HIT2, F_HIT2 - F_HIT1, (F_HIT2 - F_HIT1) / FPS * 1000))
    print("star lands f%d   hold to f%d   fade to f%d" % (
        F_STAR_LAND, F_HOLD_TO, F_FADE_TO))
    print("sequence -> %s" % SEQ)


main()
