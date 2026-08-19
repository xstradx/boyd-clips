"""boyd_gfx - broadcast 2D graphics kit for Blender 5.0.1, headless, RGBA out.

    import boyd_gfx as G
    st = G.Stage(width=1920, height=1080, fps=30, frames=150)
    st.rect(x=118, y=764, w=10, h=124, color=G.RED)
    st.text("MARCUS BOYD", font="Anton", cap=42, x=156, baseline=818)
    st.render(outdir)

DESIGN RULES BAKED IN, EACH ONE MEASURED
----------------------------------------
1  World units ARE pixels. Ortho camera, ortho_scale = width, camera down -Y.
   Layout is written in top-left pixel coordinates like every other 2D tool;
   px_to_world() does the flip. Blender images are bottom-up (capability 4.12)
   and hand-converting per call is how sample boxes end up in the wrong place.

2  Reveals are WIPES driven by a shader position threshold, not object scaling
   and not opacity ramps. Measured on this build (probe_00): a shader threshold
   antialiases to a 2-pixel alpha ramp [31,225] which is indistinguishable from
   a true geometry edge [224,30] at the same place, because EEVEE's TAA
   supersamples the shader too. So a wipe costs nothing in edge quality and can
   cut through the middle of a glyph, which object scaling cannot.

3  A text element's wipe edge is DRIVEN FROM the plate's wipe edge, offset by
   the padding. The plate reveals the text. One mechanism with a cause, rather
   than two things that happen to start together.

4  Type is sized by CAP HEIGHT in pixels, never by TextCurve.size. On this build
   size is not the em square: measured cap at size=100 is 49.70 for Anton whose
   font file declares sCapHeight/upm = 0.859. Four normalisation hypotheses
   (upm, hhea asc-desc, OS/2 typo, OS/2 win) were tested against five faces and
   none fits all of them, so the kit uses the MEASURED ratio from metrics.json
   and does not care what the mechanism is.

5  Variable fonts are pre-instanced to static TTFs by make_static_fonts.py.
   Blender 5.0 has no fvar axis API anywhere (VectorFont, TextCurve and
   TextCharacterFormat were all enumerated - see that file's docstring), so
   Montserrat-Var loads as Thin and cannot be moved off it.

6  Timing constants come from the nine broadcast idents already measured for
   this channel (see sting_v2.py header): no overshoot, asymmetric ease-out,
   +5 frame stagger, 4-7 frame travel. Blender's factory AUTO_CLAMPED puts peak
   velocity dead centre and reads as a drift.
"""
import json
import math
import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts_static"),
             r"C:\Users\natha\Projects\boyd-clips\assets\fonts"]
METRICS = json.load(open(os.path.join(HERE, "metrics.json")))

# ------------------------------------------------------------------ brand
def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexlin(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4))


GROUND = hexlin("15181D")
INK = hexlin("F2EEE3")
RED = hexlin("D42B2B")

# ------------------------------------------------------------------ easing
# CSS cubic-bezier control points. See BLENDER-CAPABILITY 1.8 for why these map
# 1:1 onto F-curve handles: Blender handles live in (frame, value) space.
EASE_OUT = (0.33, 1.00, 0.68, 1.00)    # the entrance curve, ~ easeOutCubic
EASE_OUT_HARD = (0.16, 1.00, 0.30, 1.00)   # faster attack, for exits
EASE_IN = (0.70, 0.00, 1.00, 1.00)     # accelerate into a stop: impacts
EASE_INOUT = (0.42, 0.00, 0.58, 1.00)
LINEAR = None

STAGGER = 5        # frames between sibling elements (measured +4,+5,+8,+5)
TRAVEL = 7         # frames an entrance wipe takes


# ------------------------------------------------------------------ fcurves
def _fcurves(idd):
    ad = idd.animation_data
    if ad is None:
        return []
    return ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves


def find_fc(idd, path, index=-1):
    for fc in _fcurves(idd):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            return fc
    raise RuntimeError("fcurve not found on %r: %s[%d]" % (idd, path, index))


def css_ease(fc, seg, pts):
    """Apply a CSS cubic-bezier to ONE segment.

    ONLY the two handles that bound this segment are set FREE. Setting all four
    (which is what sting_v2.py does) leaves the far handle of each keyframe
    frozen at whatever AUTO_CLAMPED computed when the curve had fewer keys - and
    once a later key is appended, that stale handle swings the NEXT segment.

    Measured: the lower third's charge text vanished for the whole 100-frame
    hold because its wipe keyframe at f17 kept a stale FREE right handle from
    when f17 was the last key on the curve. Segment f17->f119 held the same
    value at both ends but bowed off-screen in between. Silent - no error, and
    the entrance frames looked perfect.
    """
    if pts is None or seg + 1 >= len(fc.keyframe_points):
        return
    x1, y1, x2, y2 = pts
    k0, k1 = fc.keyframe_points[seg], fc.keyframe_points[seg + 1]
    k0.interpolation = 'BEZIER'
    k0.handle_right_type = 'FREE'
    k1.handle_left_type = 'FREE'
    f0, v0 = k0.co
    f1, v1 = k1.co
    df, dv = f1 - f0, v1 - v0
    k0.handle_right = (f0 + x1 * df, v0 + y1 * dv)
    k1.handle_left = (f0 + x2 * df, v0 + y2 * dv)
    fc.update()


def flatten_holds(fc, eps=1e-6):
    """Any segment whose two keys hold the SAME value must be dead flat.

    AUTO_CLAMPED already does this, but a keyframe that also terminates an eased
    segment has a FREE handle on the other side which does not. Call after all
    easing. Cheap insurance against the class of bug above.
    """
    kps = fc.keyframe_points
    for i in range(len(kps) - 1):
        a, b = kps[i], kps[i + 1]
        if abs(a.co[1] - b.co[1]) < eps:
            if a.handle_right_type == 'FREE':
                a.handle_right = (a.co[0] + (b.co[0] - a.co[0]) / 3.0, a.co[1])
            if b.handle_left_type == 'FREE':
                b.handle_left = (b.co[0] - (b.co[0] - a.co[0]) / 3.0, b.co[1])
    fc.update()


def _collapse(keys, eases):
    """Keys landing on the same frame collapse; the ease list must collapse with
    them or every ease lands one segment late (sting_v2 paid for this once)."""
    eases = list(eases) + [None] * max(0, len(keys) - 1 - len(eases))
    dk, de = [keys[0]], []
    for i in range(1, len(keys)):
        f, v = keys[i]
        if f == dk[-1][0]:
            dk[-1] = (f, v)
            continue
        dk.append((f, v))
        de.append(eases[i - 1])
    return dk, de


def _apply_eases(fc, dk, de):
    """Map this CALL's eases onto the curve's ACTUAL segment indices.

    A socket is routinely keyed more than once - entrance in one call, exit in
    another. enumerate(de) numbers segments from 0 within the call, but the
    curve already holds the earlier keys, so on the second call every ease
    landed on the ENTRANCE segment instead of the exit. Silent: the exit still
    moved, just with factory easing, and the entrance quietly got the exit's
    curve. Look the frame up instead of counting.
    """
    idx = {round(k.co[0], 4): i for i, k in enumerate(fc.keyframe_points)}
    for j, e in enumerate(de):
        seg = idx.get(round(float(dk[j][0]), 4))
        if seg is not None:
            css_ease(fc, seg, e)
    flatten_holds(fc)


def key_socket(nt, node, idx, keys, eases=()):
    """Keyframe a node socket inside a material/compositor node tree.

    Verified on this build (probe_00 B): the fcurve lands on the NODE TREE's
    animation_data, data_path 'nodes["Name"].inputs[N].default_value'.
    """
    s = node.inputs[idx]
    dk, de = _collapse(list(keys), eases)
    for f, v in dk:
        s.default_value = v
        s.keyframe_insert("default_value", frame=f)
    fc = find_fc(nt, 'nodes["%s"].inputs[%d].default_value' % (node.name, idx))
    _apply_eases(fc, dk, de)
    return fc


def key_obj(ob, path, index, keys, eases=()):
    dk, de = _collapse(list(keys), eases)
    for f, v in dk:
        getattr(ob, path)[index] = v
        ob.keyframe_insert(path, index=index, frame=f)
    fc = find_fc(ob, path, index)
    _apply_eases(fc, dk, de)
    return fc


# ------------------------------------------------------------------ fonts
_FONT_CACHE = {}


def font_file(name):
    """'Anton' / 'Archivo-Bold' / 'Oswald-Medium' -> path, preferring statics."""
    for d in FONT_DIRS:
        for ext in (".ttf", ".otf"):
            for cand in (name + ext, name + "-Regular" + ext):
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    return p
    raise FileNotFoundError("font %r not in %s" % (name, FONT_DIRS))


def load_font(name):
    if name not in _FONT_CACHE:
        _FONT_CACHE[name] = bpy.data.fonts.load(font_file(name))
    return _FONT_CACHE[name]


def cap_ratio(name):
    """Measured cap height per 1.0 of TextCurve.size, from metrics.json."""
    base = os.path.basename(font_file(name))
    return METRICS[base]["cap"] / 100.0


# ------------------------------------------------------------------ elements
class Elem:
    """One drawable. Owns its own material so its alpha and its two clip bands
    animate independently of every sibling."""

    def __init__(self, stage, obj, nt, n_op, n_cx, n_cz, n_cz2, depth):
        self.stage = stage
        self.obj = obj
        self.nt = nt
        self._op = n_op       # ShaderNodeMath MULTIPLY: opacity  * maskX
        self._cx = n_cx       # SUBTRACT carrying the x edge (inputs[1])
        self._cz = n_cz       # SUBTRACT carrying the LOWER z edge
        self._cz2 = n_cz2     # SUBTRACT carrying the UPPER z edge
        self.depth = depth
        self.width = 0.0
        self.height = 0.0
        self.base_opacity = 1.0

    # -- opacity ---------------------------------------------------------
    def opacity(self, keys, eases=()):
        return key_socket(self.nt, self._op, 1, keys, eases)

    def set_opacity(self, v):
        self._op.inputs[1].default_value = v

    # -- wipes -----------------------------------------------------------
    # clip_x keeps the region  x <= edge  (a left-to-right reveal)
    # clip_z keeps the region  z >= edge  (a bottom-up reveal)
    def wipe_x(self, keys, eases=()):
        """keys are (frame, screen_x_px) of the leading edge."""
        wk = [(f, self.stage.wx(x)) for f, x in keys]
        return key_socket(self.nt, self._cx, 1, wk, eases)

    def set_wipe_x(self, x_px):
        self._cx.inputs[1].default_value = self.stage.wx(x_px)

    def wipe_z(self, keys, eases=()):
        """keys are (frame, screen_y_px) of the edge; region BELOW y is hidden."""
        wk = [(f, self.stage.wy(y)) for f, y in keys]
        return key_socket(self.nt, self._cz, 1, wk, eases)

    def set_wipe_z(self, y_px):
        self._cz.inputs[1].default_value = self.stage.wy(y_px)

    def band(self, y_top, y_bottom):
        """Hard-clip this element to a horizontal band, in screen pixels.

        Static. Combined with slide_y() this is the odometer roll: the old and
        the new value both live inside the band and travel through it, so
        neither is ever seen outside the row."""
        self._cz.inputs[1].default_value = self.stage.wy(y_bottom)
        self._cz2.inputs[1].default_value = self.stage.wy(y_top)
        return self

    def wipe_z_top(self, keys, eases=()):
        wk = [(f, self.stage.wy(y)) for f, y in keys]
        return key_socket(self.nt, self._cz2, 1, wk, eases)

    # -- transform -------------------------------------------------------
    def move_x(self, keys, eases=()):
        """keys are (frame, offset_px) from the element's authored position."""
        base = self.obj.location[0]
        return key_obj(self.obj, "location", 0,
                       [(f, base + v) for f, v in keys], eases)

    def slide_y(self, keys, eases=()):
        """keys are (frame, offset_px) where +offset moves the element DOWN.

        Offsets are from the position the element was AUTHORED at, captured on
        the first call - so call this before any other location-2 keying.
        """
        if not hasattr(self, "_base_z"):
            self._base_z = self.obj.location[2]
        return key_obj(self.obj, "location", 2,
                       [(f, self._base_z - v) for f, v in keys], eases)

    def layer(self, n):
        """Explicit stacking order. 0 = backmost, higher = nearer the camera.

        The camera sits at y=-1000 looking toward +Y, so NEARER means MORE
        NEGATIVE y. Getting this backwards is silent and looks like a colour
        bug, not a depth bug: the lower third's ink name rendered grey because
        it sat behind a 93%-opaque ground plate, and the charge text vanished
        entirely behind a 100%-opaque red one. Nothing errors - EEVEE just
        alpha-blends them in the wrong order.
        """
        self.obj.location[1] = -1.0 - float(n)
        return self

    def scale(self, keys, eases=()):
        for i in (0, 2):
            key_obj(self.obj, "scale", i, keys, eases)


# ------------------------------------------------------------------ stage
class Stage:
    def __init__(self, width=1920, height=1080, fps=30, frames=150,
                 samples=64, dither=1.0):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        self.sc = sc
        self.W, self.H = width, height
        self.fps = fps
        sc.render.resolution_x, sc.render.resolution_y = width, height
        sc.render.resolution_percentage = 100
        sc.render.fps, sc.render.fps_base = fps, 1
        sc.frame_start, sc.frame_end = 1, frames
        sc.render.engine = 'BLENDER_EEVEE'
        sc.eevee.taa_render_samples = samples
        sc.render.filter_size = 1.50
        sc.render.film_transparent = True          # capability 1.5
        sc.render.dither_intensity = dither

        w = bpy.data.worlds.new("W")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[1].default_value = 0.0
        sc.world = w

        cd = bpy.data.cameras.new("Cam")
        cd.type = 'ORTHO'
        cd.ortho_scale = float(width)              # 1 world unit == 1 pixel
        cd.clip_start, cd.clip_end = 1.0, 20000.0
        cam = bpy.data.objects.new("Cam", cd)
        cam.location = (0.0, -1000.0, 0.0)
        # -Y look direction. '+Y' silently MIRRORS everything (capability 4.8).
        cam.rotation_euler = (math.radians(90), 0, 0)
        sc.collection.objects.link(cam)
        sc.camera = cam

        self.root = bpy.data.objects.new("ROOT", None)
        sc.collection.objects.link(self.root)
        self._depth = 0.0
        self._n = 0

    # -- coordinates: layout is top-left pixels, world is centre-origin ----
    def wx(self, x_px):
        return x_px - self.W / 2.0

    def wy(self, y_px):
        return self.H / 2.0 - y_px

    def _next_depth(self):
        self._depth -= 1.0        # each new element sits nearer the camera
        return self._depth

    # -- material ---------------------------------------------------------
    def _material(self, name, rgb, opacity):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        t = m.node_tree
        t.nodes.clear()

        geo = t.nodes.new('ShaderNodeNewGeometry'); geo.name = "GEO"
        sep = t.nodes.new('ShaderNodeSeparateXYZ'); sep.name = "SEP"
        t.links.new(geo.outputs['Position'], sep.inputs['Vector'])

        # THE EDGE LIVES IN A SUBTRACT NODE, NOT IN THE MAP RANGE.
        #
        # The obvious build - MapRange(from_min=edge, from_max=edge+F) - needs
        # BOTH from-sockets to move together. Animating only From Min (easy to
        # do, and what the first version of this file did) silently turns the
        # hard clip into a 2280-pixel gradient: measured, a bar with its "edge"
        # at x=600 rendered fully opaque from 200 to 1399 because the far socket
        # was still pinned at 1920. No error, and the result looks deliberate.
        #
        # Subtracting first means ONE socket carries the edge and the MapRange
        # window is a compile-time constant, so the two can never desynchronise.
        #
        # F = 0.02 px, i.e. effectively a hard cut. Measured in probe_00: a
        # shader threshold antialiases to a 2px ramp [31,225] against a true
        # geometry edge's [224,30]. EEVEE's TAA supersamples the shader, so a
        # deliberate feather only makes the edge SOFTER than geometry, not
        # smoother.
        F = 0.02
        cx = t.nodes.new('ShaderNodeMath'); cx.name = "EDGEX"
        cx.operation = 'SUBTRACT'
        cx.inputs[1].default_value = float(self.W)      # off-frame = fully open
        t.links.new(sep.outputs['X'], cx.inputs[0])
        mrx = t.nodes.new('ShaderNodeMapRange'); mrx.name = "MRX"
        mrx.clamp = True
        mrx.inputs[1].default_value = 0.0
        mrx.inputs[2].default_value = F                 # opaque where x <= edge
        mrx.inputs[3].default_value = 1.0
        mrx.inputs[4].default_value = 0.0
        t.links.new(cx.outputs[0], mrx.inputs[0])

        cz = t.nodes.new('ShaderNodeMath'); cz.name = "EDGEZ"
        cz.operation = 'SUBTRACT'
        cz.inputs[1].default_value = float(-self.H)
        t.links.new(sep.outputs['Z'], cz.inputs[0])
        # NOTE THE RANGE DIRECTION. The From range must ASCEND. Writing
        # (from_min=0, from_max=-F) to express "opaque above the edge" is the
        # algebraically obvious form and it does NOT work on this build: a rule
        # that should have been fully clipped rendered at a flat alpha of 237/255
        # over its whole height. Measured, not deduced - and no error was raised.
        # Keep From ascending and invert the To range instead.
        mrz = t.nodes.new('ShaderNodeMapRange'); mrz.name = "MRZ"
        mrz.clamp = True
        mrz.inputs[1].default_value = -F
        mrz.inputs[2].default_value = 0.0               # opaque where z >= edge
        mrz.inputs[3].default_value = 0.0
        mrz.inputs[4].default_value = 1.0
        t.links.new(cz.outputs[0], mrz.inputs[0])

        # a SECOND z edge, so a row can be clipped to a BAND. This is what makes
        # an odometer roll possible: old and new values both live inside the
        # band and slide through it.
        cz2 = t.nodes.new('ShaderNodeMath'); cz2.name = "EDGEZ2"
        cz2.operation = 'SUBTRACT'
        cz2.inputs[1].default_value = float(self.H)
        t.links.new(sep.outputs['Z'], cz2.inputs[0])
        mrz2 = t.nodes.new('ShaderNodeMapRange'); mrz2.name = "MRZ2"
        mrz2.clamp = True
        mrz2.inputs[1].default_value = 0.0
        mrz2.inputs[2].default_value = F                # opaque where z <= edge
        mrz2.inputs[3].default_value = 1.0
        mrz2.inputs[4].default_value = 0.0
        t.links.new(cz2.outputs[0], mrz2.inputs[0])

        mz = t.nodes.new('ShaderNodeMath'); mz.name = "MASK"
        mz.operation = 'MULTIPLY'
        t.links.new(mrx.outputs[0], mz.inputs[0])
        t.links.new(mrz.outputs[0], mz.inputs[1])

        mz2 = t.nodes.new('ShaderNodeMath'); mz2.name = "MASK2"
        mz2.operation = 'MULTIPLY'
        t.links.new(mz.outputs[0], mz2.inputs[0])
        t.links.new(mrz2.outputs[0], mz2.inputs[1])

        op = t.nodes.new('ShaderNodeMath'); op.name = "OPACITY"
        op.operation = 'MULTIPLY'
        op.inputs[1].default_value = opacity
        t.links.new(mz2.outputs[0], op.inputs[0])

        em = t.nodes.new('ShaderNodeEmission'); em.name = "EMIT"
        em.inputs['Color'].default_value = (*rgb, 1.0)
        tr = t.nodes.new('ShaderNodeBsdfTransparent'); tr.name = "TRANS"
        mx = t.nodes.new('ShaderNodeMixShader'); mx.name = "MIX"
        out = t.nodes.new('ShaderNodeOutputMaterial'); out.name = "OUT"
        t.links.new(op.outputs[0], mx.inputs[0])
        t.links.new(tr.outputs[0], mx.inputs[1])
        t.links.new(em.outputs['Emission'], mx.inputs[2])
        t.links.new(mx.outputs[0], out.inputs['Surface'])
        m.surface_render_method = 'BLENDED'
        return m, t, op, cx, cz, cz2

    # -- primitives -------------------------------------------------------
    def rect(self, x, y, w, h, color=INK, opacity=1.0, name=None):
        """Top-left anchored rectangle in screen pixels."""
        self._n += 1
        name = name or "RECT%02d" % self._n
        x0, x1 = self.wx(x), self.wx(x + w)
        z0, z1 = self.wy(y + h), self.wy(y)
        me = bpy.data.meshes.new(name)
        me.from_pydata([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)],
                       [], [(0, 1, 2, 3)])
        me.update()
        ob = bpy.data.objects.new(name, me)
        d = self._next_depth()
        ob.location = (0.0, d, 0.0)
        ob.parent = self.root
        self.sc.collection.objects.link(ob)
        mat, nt, op, cx, cz, cz2 = self._material("M_" + name, color, opacity)
        ob.data.materials.append(mat)
        e = Elem(self, ob, nt, op, cx, cz, cz2, d)
        e.width, e.height = w, h
        e.base_opacity = opacity
        return e

    def text(self, body, font="Anton", cap=42, x=0, baseline=0, color=INK,
             opacity=1.0, align="LEFT", tracking=0.0, leading=None, name=None):
        """Text anchored by BASELINE and CAP HEIGHT, both in screen pixels.

        tracking is in 1/1000 em, the units type designers actually use.
        """
        self._n += 1
        name = name or "TXT%02d" % self._n
        tc = bpy.data.curves.new(name, type='FONT')
        tc.font = load_font(font)
        tc.size = cap / cap_ratio(font)
        tc.align_x = align
        # 5.0 enum is ('TOP','TOP_BASELINE','CENTER','BOTTOM_BASELINE','BOTTOM').
        # 'BASELINE' does not exist. TOP_BASELINE puts the FIRST line's baseline
        # on the anchor, which is what a layout spec means by "baseline at y".
        tc.align_y = 'TOP_BASELINE'
        tc.body = body
        tc.extrude = 0.0
        tc.bevel_depth = 0.0
        # 5.0 fill_mode enum is ('NONE','BACK','FRONT','BOTH'), default 'BOTH'.
        # BLENDER-CAPABILITY 1.14 lists 'FULL BACK FRONT HALF' - that is wrong
        # for this build. BOTH is correct for a flat, zero-extrude glyph.
        tc.fill_mode = 'BOTH'

        ob = bpy.data.objects.new(name, tc)
        self.sc.collection.objects.link(ob)
        if tracking:
            self._apply_tracking(ob, tc, tracking)
        if leading:
            tc.space_line = leading / tc.size
        self.sc.collection.objects.unlink(ob)
        d = self._next_depth()
        ob.location = (self.wx(x), d, self.wy(baseline))
        ob.rotation_euler = (math.radians(90), 0, 0)   # capability 4.7
        ob.parent = self.root
        self.sc.collection.objects.link(ob)
        mat, nt, op, cx, cz, cz2 = self._material("M_" + name, color, opacity)
        ob.data.materials.append(mat)
        e = Elem(self, ob, nt, op, cx, cz, cz2, d)
        e.width, e.height = self.measure(ob)
        e.base_opacity = opacity
        return e

    def _apply_tracking(self, ob, tc, tracking):
        """Letterspacing in 1/1000 em, the unit type designers actually use.

        TextCurve.space_character is a MULTIPLIER on every advance, not an
        additive letterspace, so 'tracking = 120/1000 em' has no direct setting.
        Calibrate instead: measure the string at two multiplier values, get
        px-per-unit-of-multiplier, and solve. Exact, and costs two depsgraph
        evaluations. Verified against a rendered measurement in probe_02.
        """
        n = max(len(tc.body) - 1, 1)
        want = tracking / 1000.0 * tc.size * n
        tc.space_character = 1.0
        w1 = self.measure(ob)[0]
        tc.space_character = 2.0
        w2 = self.measure(ob)[0]
        per_unit = (w2 - w1)
        tc.space_character = 1.0 + (want / per_unit if per_unit > 1e-6 else 0.0)

    def measure(self, ob):
        """Evaluated ink extent in pixels. capability 4.9: dimensions is stale
        after scale, and for a FONT curve it is the pre-tessellation box."""
        bpy.context.view_layer.update()
        ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        if not len(me.vertices):
            ev.to_mesh_clear()
            return 0.0, 0.0
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        r = (max(xs) - min(xs), max(ys) - min(ys))
        ev.to_mesh_clear()
        return r

    def wrap(self, body, font, cap, max_px):
        """Greedy wrap measured in Blender, so it matches what renders exactly."""
        tc = bpy.data.curves.new("_probe", type='FONT')
        tc.font = load_font(font)
        tc.size = cap / cap_ratio(font)
        tc.align_x = 'LEFT'
        tc.align_y = 'BOTTOM_BASELINE'
        ob = bpy.data.objects.new("_probe", tc)
        self.sc.collection.objects.link(ob)

        def w(s):
            tc.body = s
            return self.measure(ob)[0]

        lines, cur = [], ""
        for word in body.split():
            trial = (cur + " " + word).strip()
            if cur and w(trial) > max_px:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        bpy.data.objects.remove(ob)
        return lines

    # -- global shake (weight, not motion) --------------------------------
    def shake(self, hits, amp=11.0):
        """Impact decay on the whole stage. Amplitudes EQUAL per hit: the
        measured gavel reference's two blows are within 1.1 dB, so the
        'second one is softer' bounce model is wrong for a deliberate strike."""
        keys, seen = [(1, 0.0)], set()
        for hit in hits:
            keys.append((hit, 0.0))
            for i, m in enumerate((1.0, -0.55, 0.28, -0.12), start=1):
                keys.append((hit + i, amp * m))
            keys.append((hit + 5, 0.0))
        keys.append((self.sc.frame_end, 0.0))
        ded = []
        for f, v in keys:
            if f not in seen:
                seen.add(f)
                ded.append((f, v))
        for f, v in ded:
            self.root.location[2] = v
            self.root.keyframe_insert("location", index=2, frame=f)
        for k in find_fc(self.root, "location", 2).keyframe_points:
            k.interpolation = 'LINEAR'      # bezier would float an impact

    # -- output -----------------------------------------------------------
    def render(self, outdir, prefix="f_", dither=None):
        os.makedirs(outdir, exist_ok=True)
        sc = self.sc
        if dither is not None:
            sc.render.dither_intensity = dither
        ims = sc.render.image_settings
        # capability 5.1: scene default is AgX and would ship #F2EEE3 as
        # #C0BFBB. OVERRIDE keeps the scene alone and fixes the OUTPUT.
        ims.color_management = 'OVERRIDE'
        ims.view_settings.view_transform = 'Standard'
        ims.view_settings.look = 'None'
        ims.media_type = 'IMAGE'
        ims.file_format = 'PNG'
        ims.color_mode = 'RGBA'
        ims.color_depth = '8'
        ims.compression = 15
        sc.render.filepath = os.path.join(outdir, prefix)
        bpy.ops.render.render(animation=True)
        return outdir
