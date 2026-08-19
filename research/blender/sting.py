#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sting.py -- Texas Trial Tracker channel sting (T2 tier), Blender 5.0.1 headless.

    blender.exe -b --python sting.py -- --pass all

Passes:  geom | flat | alpha | verify | audio | all
Written against STING-SPEC.md and BLENDER-CAPABILITY.md.

--------------------------------------------------------------------------------------
WHAT THIS SCRIPT DOES NOT DO: it does not import logo_transparent.png.
STING-SPEC.md sec 12 declares that file a production blocker (0 antialiased pixels,
4245 distinct opaque RGB values, a 1-2 px JPEG keyline fringe). Independently
re-confirmed by scratch/sting_00_measure.py. Instead the mark is REBUILT here as flat
polygons from geometry measured off that PNG (scratch/sting_01_measure2.py), which is
the sec 12 "redraw as vector" requirement satisfied procedurally: two separately
transformable objects, exactly two colours, no keyline, real antialiasing from EEVEE.
--------------------------------------------------------------------------------------

HOW TO RETIME THIS PIECE
========================
Everything a human needs to change timing lives in the TIMING and LAYOUT blocks
directly below. Nothing else in the file contains a frame number or a coordinate.
All frames are 60 fps, 1-based, matching STING-SPEC.md sec 2.
"""

import bpy, os, sys, math, argparse, subprocess

# ======================================================================================
# TIMING  -- STING-SPEC.md sec 2 beat sheet.  Edit here, nowhere else.
# ======================================================================================
FPS            = 60          # master frame rate (spec sec 1)
F_START        = 1           # first frame of the sting
F_END          = 84          # last frame  -> 84/60 = 1.400 s exactly (spec sec 1)

F_GROUND_ONLY  = 24          # beat A ends here: ground + grain + audio riser alone
F_STAR_ON      = 25          # beat B1: star hard-cuts on at full opacity, 1 frame
F_TYPE_FADE_IN = 25          # beat B2 start: wordmark alpha 0
F_TYPE_FADE_UP = 36          # beat B2 end:   wordmark alpha 1   (12 f / 200 ms)
F_SHEAR_START  = 25          # beat B3 start: shear at K_START
F_SHEAR_LOCK   = 48          # beat B3 end:   shear at K_REST    (24 f / 400 ms)
# beat C (lock) is F_SHEAR_LOCK+1 = 49; beat D (hold) is 50..84; beat E (cut) is 85.

# ======================================================================================
# MOTION  -- STING-SPEC.md sec 3.1 / sec 5
# ======================================================================================
LEAN_DEG      = 9.08                              # the mark's own built-in stem lean
K_REST        = math.tan(math.radians(LEAN_DEG))  # 0.159816  (spec sec 3.1)
OVERSHEAR_MUL = 3.0                               # spec sec 3.1: raise to 4.0 if too subtle
K_START       = OVERSHEAR_MUL * K_REST            # 0.479448
EASE          = (0.42, 0.0, 0.58, 1.0)            # cubic-bezier, spec sec 5 (one curve, everywhere)

# NOTE ON SIGN: measured off the artwork, the stems lean LEFT going up (top-left /
# bottom-right back-slant -- see the rendered logo). So shear is x' = x - K*z with the
# baseline (z=0) as pivot. Over-shearing therefore slides the third T's crossbar OUT
# from under the star, and the settle slides it back IN. That closing of the star/T
# register is the lock (spec sec 3.3).

# ======================================================================================
# LAYOUT  -- spec sec 4.  Reference units = the 1413 x 540 logo pixel grid,
# z measured UP from the stem baseline.  Values measured by scratch/sting_01_measure2.py.
# ======================================================================================
RES_X, RES_Y  = 1920, 1080
MARK_W_PX     = 680.0        # spec sec 4: mark bounding box 680 px wide, optically centred

STEM_W        = 123.0        # measured 122.95 (spec sec 12 item 4: "122-123 px")
BAR_W         = 373.7        # measured crossbar width, constant
Z_BAR_BOT     = 284.0        # top of stem / bottom of crossbar
Z_BAR_TOP     = 382.0        # top of crossbar  -> crossbar is 98 units tall
STEM_CX       = (249.2, 646.2, 1043.2)   # unsheared stem centres at the baseline
                                         # measured pitch 397.0 (spec sec 9 says 396.5 -- see critique)
STAR_CX       = 1247.0       # star centre x (star is NOT sheared, spec sec 3.3)
STAR_CZ       = 364.5        # star centre z above baseline
STAR_R        = 173.0        # outer radius; regular 5-point star (329 x 313 -> spec sec 12 item 6)

# ======================================================================================
# COLOUR -- spec sec 6, fed LINEAR (BLENDER-CAPABILITY.md sec 5.3)
# ======================================================================================
def srgb_to_linear(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def hex_lin(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(float(int(h[i:i + 2], 16))) for i in (0, 2, 4))

GROUND_HEX, INK_HEX, ACCENT_HEX = "#15181D", "#F2EEE3", "#D42B2B"
GROUND_L, INK_L, ACCENT_L = hex_lin(GROUND_HEX), hex_lin(INK_HEX), hex_lin(ACCENT_HEX)

GRAIN_AMPLITUDE = 0.0015     # spec sec 3.4, linear. 0.02 is ~10x too strong.

# ======================================================================================
# AUDIO -- spec sec 7
# ======================================================================================
SR            = 48000
RISER_F0      = 45.0         # Hz, exponential sweep start
RISER_F1      = 165.0        # Hz, at the lock
RISER_END_F   = 48           # riser envelope reaches its top at this frame
RISER_RMS_DB  = -38.0        # dBFS RMS at f48
TRANSIENT_F   = 49           # peak frame (spec sec 7.2: must land in f47-49, never earlier)
PEAK_RMS_DB   = -17.6        # dBFS RMS over the transient frame
BED_RMS_DB    = -36.0        # dBFS RMS bed under the cut into content

# ======================================================================================
# PATHS
# ======================================================================================
ROOT     = r"C:\Users\natha\Projects\boyd-clips\research\blender"
RENDERS  = os.path.join(ROOT, "renders")
SEQ_FLAT = os.path.join(RENDERS, "seq_flat")
SEQ_ALFA = os.path.join(RENDERS, "seq_alpha")
VERIFY   = os.path.join(RENDERS, "verify")
CONTACT  = os.path.join(RENDERS, "contact")
WAV_MAIN = os.path.join(RENDERS, "sting_audio.wav")       # exactly 84 frames
WAV_TAIL = os.path.join(RENDERS, "sting_audio_tail.wav")  # + bed running past the cut
for d in (RENDERS, SEQ_FLAT, SEQ_ALFA, VERIFY, CONTACT):
    os.makedirs(d, exist_ok=True)


# ======================================================================================
# ANIMATION HELPERS -- Blender 5.0 slotted actions (BLENDER-CAPABILITY.md sec 1.7, 2.5)
# ======================================================================================
def get_fcurves(id_data):
    """Action.fcurves is GONE in 5.0. Curves live on the channelbag of the action slot."""
    ad = id_data.animation_data
    return ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves


def find_fcurve(id_data, path, index=-1):
    for fc in get_fcurves(id_data):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            return fc
    raise RuntimeError("fcurve not found: %s[%d]" % (path, index))


def css_ease(fc, seg, x1, y1, x2, y2):
    """Map CSS cubic-bezier(x1,y1,x2,y2) onto F-curve segment `seg`.
    Blender handles live in (frame, value) space so the mapping is direct.
    BLENDER-CAPABILITY.md sec 1.8. Works for descending segments too."""
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


# ======================================================================================
# GEOMETRY -- the redrawn mark (spec sec 12)
# ======================================================================================
def mark_extent(K):
    """Bounding box of the whole mark (wordmark + star) at shear K, in reference units."""
    xs, zs = [], []
    for cx in STEM_CX:
        for (x0, z0) in ((cx - BAR_W / 2, Z_BAR_TOP), (cx + BAR_W / 2, Z_BAR_TOP),
                         (cx - BAR_W / 2, Z_BAR_BOT), (cx + BAR_W / 2, Z_BAR_BOT),
                         (cx - STEM_W / 2, 0.0), (cx + STEM_W / 2, 0.0)):
            xs.append(x0 - K * z0); zs.append(z0)
    xs += [STAR_CX - STAR_R * math.sin(math.radians(72)),
           STAR_CX + STAR_R * math.sin(math.radians(72))]
    zs += [STAR_CZ - STAR_R * math.cos(math.radians(36)), STAR_CZ + STAR_R]
    return min(xs), max(xs), min(zs), max(zs)


# The mark is framed on its REST pose, so the rest pose is what is optically centred.
_X0, _X1, _Z0, _Z1 = mark_extent(K_REST)
SCALE   = MARK_W_PX / (_X1 - _X0)            # reference units -> screen pixels
OFF_X   = (_X0 + _X1) / 2.0
OFF_Z   = (_Z0 + _Z1) / 2.0


def ref_to_world(x0, z0, K):
    """Unsheared reference coords -> world pixels, with shear K about the baseline."""
    return ((x0 - K * z0) - OFF_X) * SCALE, (z0 - OFF_Z) * SCALE


def build_wordmark(K):
    """Three T's as flat quads. Each T = crossbar quad + stem quad sharing an edge
    (adjacent, never overlapping -> no coplanar z-fighting)."""
    verts, faces = [], []
    for cx in STEM_CX:
        for (xl, xr, zb, zt) in ((cx - STEM_W / 2, cx + STEM_W / 2, 0.0, Z_BAR_BOT),
                                 (cx - BAR_W / 2, cx + BAR_W / 2, Z_BAR_BOT, Z_BAR_TOP)):
            i = len(verts)
            for (x0, z0) in ((xl, zb), (xr, zb), (xr, zt), (xl, zt)):
                wx, wz = ref_to_world(x0, z0, K)
                verts.append((wx, 0.0, wz))
            faces.append((i, i + 1, i + 2, i + 3))
    return verts, faces


def build_star():
    """Regular 5-point star, triangle fan from the centre. Never sheared (spec sec 3.3)."""
    r_in = STAR_R * math.cos(math.radians(72)) / math.cos(math.radians(36))
    verts, faces = [], []
    cwx, cwz = ref_to_world(STAR_CX, STAR_CZ, 0.0)
    verts.append((cwx, 0.0, cwz))
    pts = []
    for i in range(10):
        ang = math.radians(90 + i * 36)                 # first point straight up
        rad = STAR_R if i % 2 == 0 else r_in
        pts.append((STAR_CX + rad * math.cos(ang), STAR_CZ + rad * math.sin(ang)))
    for (x0, z0) in pts:
        wx, wz = ref_to_world(x0, z0, 0.0)
        verts.append((wx, 0.0, wz))
    for i in range(10):
        faces.append((0, 1 + i, 1 + (i + 1) % 10))
    return verts, faces


def new_mesh_object(name, verts, faces, y_depth, scene):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = (0.0, y_depth, 0.0)
    scene.collection.objects.link(ob)
    return ob


# ======================================================================================
# MATERIAL -- flat emission, alpha driven by a keyframable Value node
# ======================================================================================
def flat_emissive(name, linear_rgb, animatable_alpha):
    """Emission mixed against Transparent. The Mix factor IS the output alpha, so the
    same node drives both the fade over the ground and the alpha of the alpha master.
    BLENDER-CAPABILITY.md sec 1.11 / sec 5.4 item 3."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emis  = nt.nodes.new('ShaderNodeEmission')
    emis.inputs['Color'].default_value = (*linear_rgb, 1.0)
    emis.inputs['Strength'].default_value = 1.0
    out   = nt.nodes.new('ShaderNodeOutputMaterial')
    if not animatable_alpha:
        nt.links.new(emis.outputs['Emission'], out.inputs['Surface'])
        mat.surface_render_method = 'DITHERED'
        return mat
    trans = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix   = nt.nodes.new('ShaderNodeMixShader')
    val   = nt.nodes.new('ShaderNodeValue'); val.name = "ALPHA"; val.label = "ALPHA"
    val.outputs[0].default_value = 0.0
    nt.links.new(val.outputs[0],        mix.inputs['Fac'])
    nt.links.new(trans.outputs['BSDF'], mix.inputs[1])
    nt.links.new(emis.outputs['Emission'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    mat.surface_render_method = 'BLENDED'      # required for real alpha (sec 1.5)
    return mat


def key_alpha(mat, keys, ease_segments=()):
    """keys = [(frame, value, interpolation), ...] on the material's ALPHA Value node."""
    nt = mat.node_tree
    val = nt.nodes["ALPHA"]
    path = 'nodes["ALPHA"].outputs[0].default_value'
    for (f, v, interp) in keys:
        val.outputs[0].default_value = v
        nt.keyframe_insert(path, frame=f)
    fc = find_fcurve(nt, path)
    for i, (f, v, interp) in enumerate(keys):
        fc.keyframe_points[i].interpolation = interp   # sec 2.8: must be set explicitly
    for seg in ease_segments:
        css_ease(fc, seg, *EASE)
    fc.update()
    return fc


# ======================================================================================
# SCENE
# ======================================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y
    sc.render.resolution_percentage = 100
    sc.render.fps, sc.render.fps_base = FPS, 1.0
    sc.frame_start, sc.frame_end = F_START, F_END
    sc.render.engine = 'BLENDER_EEVEE'            # EEVEE Next IS BLENDER_EEVEE in 5.0 (sec 1.2)
    if hasattr(sc.eevee, "taa_render_samples"):
        sc.eevee.taa_render_samples = 64
    sc.render.filter_size = 1.50                  # the real antialiasing the source PNG lacks

    # world must be created by hand after read_factory_settings(use_empty=True) (sec 1.1)
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    sc.world = w

    # ---- camera: orthographic, 1 Blender unit == 1 screen pixel -----------------------
    cam_d = bpy.data.cameras.new("Cam")
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = float(RES_X)              # ortho_scale spans the LARGER dimension
    cam_d.clip_start, cam_d.clip_end = 1.0, 20000.0
    cam = bpy.data.objects.new("Cam", cam_d)
    cam.location = (0.0, -3000.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)   # look toward +Y (sec 4.7 / 4.8)
    sc.collection.objects.link(cam)
    sc.camera = cam

    # ---- ground: full-frame emissive plane, hidden for the alpha pass -----------------
    gx, gz = RES_X, RES_Y
    ground = new_mesh_object("GROUND",
                             [(-gx, 0, -gz), (gx, 0, -gz), (gx, 0, gz), (-gx, 0, gz)],
                             [(0, 1, 2, 3)], 500.0, sc)
    ground.data.materials.append(flat_emissive("M_GROUND", GROUND_L, False))

    # ---- WORDMARK: built at REST, shape key carries it to the over-sheared pose -------
    v_rest, faces = build_wordmark(K_REST)
    v_start, _    = build_wordmark(K_START)
    wm = new_mesh_object("WORDMARK", v_rest, faces, 0.0, sc)
    wm.data.materials.append(flat_emissive("M_INK", INK_L, True))

    # Shape-key shear (sec 1.9). Exact: both poses are generated by the same builder,
    # so the key is the literal difference between K_START and K_REST geometry.
    wm.shape_key_add(name="Basis", from_mix=False)
    sk = wm.shape_key_add(name="OverShear", from_mix=False)
    for i, co in enumerate(v_start):
        sk.data[i].co = co

    # ---- STAR: separate object, never transformed (spec sec 3.3 / sec 12 item 1) ------
    sv, sf = build_star()
    star = new_mesh_object("STAR", sv, sf, -1.0, sc)     # -1 => in front of the wordmark
    star.data.materials.append(flat_emissive("M_ACCENT", ACCENT_L, True))

    return sc, wm, sk, star, ground


def animate(wm, sk, star):
    """Beat sheet -> F-curves. All frame numbers come from the TIMING block."""
    key_data = wm.data.shape_keys

    # --- B3 SHEAR SETTLE: shape key 1.0 (over-sheared) -> 0.0 (rest) -----------------
    # value = 1 - bezier(t)  =>  K(t) = K_START + (K_REST-K_START)*bezier(t). Spec sec 3.1.
    sk.value = 1.0; sk.keyframe_insert('value', frame=F_START)
    sk.value = 1.0; sk.keyframe_insert('value', frame=F_SHEAR_START)
    sk.value = 0.0; sk.keyframe_insert('value', frame=F_SHEAR_LOCK)
    fc = find_fcurve(key_data, 'key_blocks["OverShear"].value')
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    css_ease(fc, 1, *EASE)              # segment 1 = F_SHEAR_START -> F_SHEAR_LOCK
    fc.update()

    # --- B2 TYPE FADE-UP: wordmark alpha 0 -> 1, eased, under the shear --------------
    key_alpha(wm.data.materials[0],
              [(F_START,        0.0, 'CONSTANT'),
               (F_TYPE_FADE_IN, 0.0, 'BEZIER'),
               (F_TYPE_FADE_UP, 1.0, 'BEZIER')],
              ease_segments=(1,))

    # --- B1 STAR ON: hard cut, one frame, no fade (spec sec 2) ------------------------
    key_alpha(star.data.materials[0],
              [(F_START,       0.0, 'CONSTANT'),
               (F_STAR_ON - 1, 0.0, 'CONSTANT'),
               (F_STAR_ON,     1.0, 'CONSTANT')])


# ======================================================================================
# COMPOSITOR GRAIN -- spec sec 3.4 / BLENDER-CAPABILITY.md sec 1.13
# ======================================================================================
def build_grain(sc, amplitude):
    ng = bpy.data.node_groups.new("Grain", "CompositorNodeTree")
    ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc     # MANDATORY (sec 2.3)
    go = ng.nodes.new("NodeGroupOutput")
    if amplitude <= 0.0:
        ng.links.new(rl.outputs['Image'], go.inputs['Image'])
        sc.compositing_node_group = ng
        return ng
    ic = ng.nodes.new("CompositorNodeImageCoordinates")
    ng.links.new(rl.outputs['Image'], ic.inputs['Image'])         # DOMAIN, else flat (sec 4.6)
    st = ng.nodes.new("CompositorNodeSceneTime")
    wn = ng.nodes.new("ShaderNodeTexWhiteNoise"); wn.noise_dimensions = '4D'
    ng.links.new(ic.outputs['Pixel'], wn.inputs['Vector'])
    ng.links.new(st.outputs['Frame'], wn.inputs['W'])             # reseeds every frame
    mix = ng.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'ADD'
    sel = lambda n, i: [s for s in n.inputs if s.identifier == i][0]   # by identifier (sec 2.12)
    ng.links.new(rl.outputs['Image'], sel(mix, 'A_Color'))
    ng.links.new(wn.outputs['Color'], sel(mix, 'B_Color'))
    sel(mix, 'Factor_Float').default_value = amplitude
    res = [s for s in mix.outputs if s.identifier == 'Result_Color'][0]
    ng.links.new(res, go.inputs['Image'])
    sc.compositing_node_group = ng
    return ng


# ======================================================================================
# OUTPUT SETTINGS
# ======================================================================================
def set_png(sc, depth, rgba, dither):
    ims = sc.render.image_settings
    ims.media_type = 'IMAGE'                       # sec 1.3: gates file_format
    ims.file_format = 'PNG'
    ims.color_depth = depth
    ims.color_mode = 'RGBA' if rgba else 'RGB'
    ims.compression = 15
    # Brand-exact colour. The scene keeps its default AgX; only the OUTPUT is overridden.
    ims.color_management = 'OVERRIDE'              # new in 5.0 (sec 5.2)
    ims.view_settings.view_transform = 'Standard'
    ims.view_settings.look = 'None'
    sc.render.dither_intensity = dither            # 1.0 delivery, 0.0 verification (sec 4.10)


# ======================================================================================
# PASSES
# ======================================================================================
def pass_geom():
    """Print the derived geometry so the numbers can be checked against the spec."""
    print("\n=== DERIVED GEOMETRY ===")
    print("K_REST  = %.6f  (%.2f deg)" % (K_REST, LEAN_DEG))
    print("K_START = %.6f  (%.4f deg)  = %.1f x K_REST"
          % (K_START, math.degrees(math.atan(K_START)), OVERSHEAR_MUL))
    print("dK      = %.6f" % (K_START - K_REST))
    print("rest extent (ref units): x %.2f..%.2f (w %.2f)  z %.2f..%.2f (h %.2f)  aspect %.4f"
          % (_X0, _X1, _X1 - _X0, _Z0, _Z1, _Z1 - _Z0, (_X1 - _X0) / (_Z1 - _Z0)))
    print("SCALE   = %.6f ref-units -> px" % SCALE)
    print("mark on screen: %.1f x %.1f px  (%.2f%% w, %.2f%% h of frame)"
          % (MARK_W_PX, (_Z1 - _Z0) * SCALE,
             100 * MARK_W_PX / RES_X, 100 * (_Z1 - _Z0) * SCALE / RES_Y))
    trav_bar = (K_START - K_REST) * Z_BAR_TOP * SCALE
    trav_stem = (K_START - K_REST) * Z_BAR_BOT * SCALE
    print("shear travel @ crossbar top (z=%.0f): %.2f px  -> %.3f px/frame"
          % (Z_BAR_TOP, trav_bar, trav_bar / (F_SHEAR_LOCK - F_SHEAR_START)))
    print("shear travel @ stem top    (z=%.0f): %.2f px" % (Z_BAR_BOT, trav_stem))
    for K, lbl in ((K_START, "over-sheared"), (K_REST, "rest")):
        bar2_r = (STEM_CX[2] + BAR_W / 2) - K * Z_BAR_TOP
        star_l = STAR_CX - STAR_R * math.sin(math.radians(72))
        print("  star/T3 register @ %-12s overlap = %.1f ref px (%.1f screen px)"
              % (lbl, bar2_r - star_l, (bar2_r - star_l) * SCALE))
    print("duration: %d frames / %d fps = %.4f s" % (F_END - F_START + 1, FPS,
                                                     (F_END - F_START + 1) / float(FPS)))


def pass_render(kind):
    sc, wm, sk, star, ground = build_scene()
    animate(wm, sk, star)

    if kind == 'flat':
        sc.render.film_transparent = False
        build_grain(sc, GRAIN_AMPLITUDE)
        set_png(sc, '8', False, 1.0)               # delivery: dither ON
        sc.render.filepath = os.path.join(SEQ_FLAT, "f_")
        bpy.ops.render.render(animation=True)

    elif kind == 'alpha':
        # Alpha master: ground hidden, film transparent. Grain is deliberately OFF here --
        # an ADD-blend grain would deposit noise into fully transparent pixels and dirty
        # the composite over footage. Grain belongs to the ground (spec sec 3.4).
        ground.hide_render = True
        sc.render.film_transparent = True
        build_grain(sc, 0.0)
        set_png(sc, '16', True, 0.0)
        sc.render.filepath = os.path.join(SEQ_ALFA, "a_")
        bpy.ops.render.render(animation=True)

    elif kind == 'verify':
        # Hex-verification control: no grain, no dither, so exact brand values can be read.
        sc.render.film_transparent = False
        build_grain(sc, 0.0)
        set_png(sc, '8', False, 0.0)
        for f in (24, 25, 30, 36, 49, 60, 84):
            sc.frame_set(f)
            sc.render.filepath = os.path.join(VERIFY, "ctrl_%04d" % f)
            bpy.ops.render.render(write_still=True)


# ======================================================================================
# AUDIO -- spec sec 7. Synthesized, never licensed (spec sec 7.3).
# ======================================================================================
def pass_audio():
    import numpy as np, wave, struct

    def db(x):    return 10.0 ** (x / 20.0)
    def rms(x):   return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
    def frame_slice(x, f):
        a = int(round((f - 1) / FPS * SR)); b = int(round(f / FPS * SR))
        return x[a:min(b, len(x))]

    TAIL_F = 130                                    # bed runs past the cut (spec sec 8)
    n = int(round(TAIL_F / FPS * SR))
    t = np.arange(n) / SR

    # ---- layer 1: exponential sine sweep 45 -> 165 Hz across frames 1..48 -------------
    T = RISER_END_F / FPS
    k = RISER_F1 / RISER_F0
    tr = np.clip(t, 0, T)
    phase = 2 * np.pi * RISER_F0 * T / math.log(k) * (k ** (tr / T) - 1.0)
    riser = np.sin(phase)
    env = (tr / T) ** 2.0                           # silence -> full, quadratic
    env[t > T] = 0.0
    riser *= env
    riser *= db(RISER_RMS_DB) / max(rms(frame_slice(riser, RISER_END_F)), 1e-12)

    # ---- layer 2: transient at f49 ---------------------------------------------------
    t0 = (TRANSIENT_F - 1) / FPS                    # attack begins at the top of f49
    td = np.maximum(t - t0, 0.0)
    live = (t >= t0).astype(float)

    def ar(attack_ms, decay_ms):
        """linear attack then -60 dB exponential decay"""
        a = attack_ms / 1000.0
        atk = np.clip(td / a, 0, 1)
        dec = np.exp(-np.maximum(td - a, 0.0) / (decay_ms / 1000.0 / math.log(1000.0)))
        return atk * dec * live

    body = np.sin(2 * np.pi * 55.0 * td) * ar(8, 220)

    rng = np.random.default_rng(20260809)
    noise = rng.standard_normal(n)
    F = np.fft.rfft(noise); fr = np.fft.rfftfreq(n, 1.0 / SR)
    g = np.zeros_like(fr)
    band = (fr >= 800) & (fr <= 4000)
    g[band] = 1.0
    edge = (fr > 4000) & (fr <= 6000)               # gentle upper roll-off
    g[edge] = 0.5 * (1 + np.cos(np.pi * (fr[edge] - 4000) / 2000.0))
    edge = (fr >= 500) & (fr < 800)
    g[edge] = 0.5 * (1 - np.cos(np.pi * (fr[edge] - 500) / 300.0))
    click = np.fft.irfft(F * g, n=n)
    click /= max(np.abs(click).max(), 1e-12)
    click *= ar(2, 60) * db(-12.0)                  # -12 dB relative to the body

    transient = body + click
    transient *= db(PEAK_RMS_DB) / max(rms(frame_slice(transient, TRANSIENT_F)), 1e-12)

    # ---- layer 3: bed, fades in over 20 frames, runs under the cut -------------------
    bn = rng.standard_normal(n)
    Fb = np.fft.rfft(bn)
    gb = np.exp(-(fr / 180.0) ** 2)                 # low, dark bed
    bed = np.fft.irfft(Fb * gb, n=n)
    bed /= max(rms(bed), 1e-12)
    bed *= db(BED_RMS_DB)
    fade = np.clip((t - t0) / (20.0 / FPS), 0, 1) * live
    bed *= fade

    mix = riser + transient + bed
    tp = float(np.abs(mix).max())
    print("true peak      : %.2f dBFS" % (20 * math.log10(max(tp, 1e-12))))
    print("f%-3d RMS       : %.2f dBFS   (riser target %.1f)"
          % (RISER_END_F, 20 * math.log10(max(rms(frame_slice(mix, RISER_END_F)), 1e-12)), RISER_RMS_DB))
    print("f%-3d RMS       : %.2f dBFS   (peak  target %.1f)"
          % (TRANSIENT_F, 20 * math.log10(max(rms(frame_slice(mix, TRANSIENT_F)), 1e-12)), PEAK_RMS_DB))
    for f in (60, 70, 84, 100):
        print("f%-3d RMS       : %.2f dBFS" % (f, 20 * math.log10(max(rms(frame_slice(mix, f)), 1e-12))))
    print("dynamic range f%d -> f84: %.1f dB"
          % (TRANSIENT_F, 20 * math.log10(rms(frame_slice(mix, TRANSIENT_F)) / rms(frame_slice(mix, 84)))))

    def write_wav(path, data):
        d = np.clip(data, -1.0, 1.0)
        pcm = (d * 32767.0).astype('<i2')
        with wave.open(path, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        print("wrote %s  (%d samples, %.4f s)" % (path, len(pcm), len(pcm) / float(SR)))

    write_wav(WAV_MAIN, mix[:int(round(F_END / FPS * SR))])
    write_wav(WAV_TAIL, mix)


# ======================================================================================
# MAIN
# ======================================================================================
if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="p", default="all",
                    choices=["geom", "flat", "alpha", "verify", "audio", "all"])
    args = ap.parse_args(argv)

    if args.p in ("geom", "all"):
        pass_geom()
    if args.p in ("audio", "all"):
        pass_audio()
    if args.p in ("verify", "all"):
        pass_render('verify')
    if args.p in ("flat", "all"):
        pass_render('flat')
    if args.p in ("alpha", "all"):
        pass_render('alpha')
    print("\n=== sting.py pass '%s' complete ===" % args.p)
