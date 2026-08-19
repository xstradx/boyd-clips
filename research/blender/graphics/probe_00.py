"""Probe: everything the graphics kit needs, verified on THIS 5.0.1 build before
any production code is written.

Run: blender -b --python probe_00.py

Answers:
  A  which shader nodes exist for a per-object WIPE mask (Geometry->Position)
  B  can we keyframe a MapRange input socket inside a MATERIAL node tree
  C  text metrics: em size -> cap height -> advance width, per font, measured
     from evaluated geometry (needed for wrapping and for optical alignment)
  D  do the variable fonts load, and WHICH instance do we get
  E  RGBA PNG + film_transparent + colour override -> exact brand hex on disk
  F  does a shader-threshold edge antialias under EEVEE TAA, or does it stair-step
"""
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders", "probe")
FONTS = r"C:\Users\natha\Projects\boyd-clips\assets\fonts"
os.makedirs(OUT, exist_ok=True)

RES_X, RES_Y = 1920, 1080


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    return tuple(srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4))


GROUND, INK, RED = hex_lin("15181D"), hex_lin("F2EEE3"), hex_lin("D42B2B")

print("=" * 72)
print("A. shader node availability")
print("=" * 72)
mat = bpy.data.materials.new("probe")
mat.use_nodes = True
nt = mat.node_tree
for t in ("ShaderNodeNewGeometry", "ShaderNodeMapRange", "ShaderNodeMath",
          "ShaderNodeSeparateXYZ", "ShaderNodeObjectInfo", "ShaderNodeTexCoord",
          "ShaderNodeValue", "ShaderNodeMix", "ShaderNodeBsdfTransparent",
          "ShaderNodeEmission", "ShaderNodeMixShader", "ShaderNodeClamp",
          "ShaderNodeAttribute", "ShaderNodeVectorMath"):
    try:
        n = nt.nodes.new(t)
        outs = [s.name for s in n.outputs]
        ins = [s.name for s in n.inputs]
        print("  OK   %-26s out=%s in=%s" % (t, outs[:6], ins[:6]))
    except RuntimeError as e:
        print("  FAIL %-26s %s" % (t, e))

# MapRange interpolation / data_type enums, probed by junk assignment
mr = nt.nodes.new("ShaderNodeMapRange")
for prop in ("data_type", "interpolation_type", "clamp"):
    try:
        setattr(mr, prop, "__junk__")
    except TypeError as e:
        s = str(e)
        print("  %-20s %s" % (prop, s[s.find("in ("):] if "in (" in s else s))
    except Exception as e:
        print("  %-20s %s" % (prop, type(e).__name__))
print("  MapRange input identifiers:", [s.identifier for s in mr.inputs])

print()
print("=" * 72)
print("B. keyframing a MapRange socket INSIDE a material node tree")
print("=" * 72)
mr.inputs[1].default_value = 0.0
mr.inputs[1].keyframe_insert("default_value", frame=1)
mr.inputs[1].default_value = 100.0
mr.inputs[1].keyframe_insert("default_value", frame=10)
ad = nt.animation_data
print("  node_tree has animation_data:", ad is not None)
if ad:
    try:
        fcs = ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves
        for fc in fcs:
            print("  fcurve:", fc.data_path, fc.array_index,
                  [tuple(k.co) for k in fc.keyframe_points])
    except Exception as e:
        print("  FAIL reading channelbag:", type(e).__name__, e)

print()
print("=" * 72)
print("C/D. fonts: load, instance name, measured metrics")
print("=" * 72)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y

metrics = {}
for fn in sorted(os.listdir(FONTS)):
    if not fn.lower().endswith((".ttf", ".otf")):
        continue
    p = os.path.join(FONTS, fn)
    try:
        f = bpy.data.fonts.load(p)
    except Exception as e:
        print("  FAIL load %s: %s" % (fn, e))
        continue
    tc = bpy.data.curves.new("T_" + fn, type='FONT')
    tc.font = f
    tc.size = 100.0            # em = 100 world units
    tc.align_x = 'LEFT'
    tc.align_y = 'BOTTOM_BASELINE'   # 5.0: 'BASELINE' does not exist
    tc.body = "HXQ"
    ob = bpy.data.objects.new("T_" + fn, tc)
    sc.collection.objects.link(ob)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    if len(me.vertices) == 0:
        print("  %-24s NO GEOMETRY" % fn)
        ev.to_mesh_clear()
        continue
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    cap = max(ys) - min(0.0, min(ys))
    ev.to_mesh_clear()

    # advance width of a reference string, and of a space
    def adv(body):
        tc.body = body
        bpy.context.view_layer.update()
        d = bpy.context.evaluated_depsgraph_get()
        e2 = ob.evaluated_get(d)
        m2 = e2.to_mesh()
        w = (max(v.co.x for v in m2.vertices) - min(v.co.x for v in m2.vertices)
             if len(m2.vertices) else 0.0)
        e2.to_mesh_clear()
        return w

    w_hxq = max(xs) - min(xs)
    w_n = adv("N")
    w_nn = adv("NN")
    metrics[fn] = dict(font_name=f.name, cap_height_per_100em=round(cap, 3),
                       ink_w_HXQ=round(w_hxq, 2), ink_w_N=round(w_n, 2),
                       advance_N=round(w_nn - w_n, 3))
    print("  %-24s blender_name=%-28s cap=%.2f  advance('N')=%.2f" % (
        fn, f.name, cap, w_nn - w_n))
    bpy.data.objects.remove(ob)

print()
print("  metrics json:", json.dumps(metrics))

print()
print("=" * 72)
print("E/F. render: RGBA + film_transparent + colour override + shader wipe AA")
print("=" * 72)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y
sc.render.resolution_percentage = 100
sc.render.fps, sc.render.fps_base = 30, 1
sc.frame_start = sc.frame_end = 1
sc.render.engine = 'BLENDER_EEVEE'
sc.eevee.taa_render_samples = 64
sc.render.filter_size = 1.50
sc.render.film_transparent = True
sc.render.dither_intensity = 0.0        # verification render

w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.0
sc.world = w

cd = bpy.data.cameras.new("Cam")
cd.type = 'ORTHO'
cd.ortho_scale = float(RES_X)            # 1 world unit == 1 pixel
cd.clip_start, cd.clip_end = 1.0, 20000.0
cam = bpy.data.objects.new("Cam", cd)
cam.location = (0.0, -1000.0, 0.0)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(cam)
sc.camera = cam


def quad(name, x0, x1, z0, z1, y=0.0):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)],
                   [], [(0, 1, 2, 3)])
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = (0, y, 0)
    sc.collection.objects.link(ob)
    return ob


def wipe_mat(name, rgb, edge_x, feather):
    """Emission clipped by WORLD X position -> the broadcast wipe, per object."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    geo = t.nodes.new('ShaderNodeNewGeometry')
    sep = t.nodes.new('ShaderNodeSeparateXYZ')
    mr = t.nodes.new('ShaderNodeMapRange')
    tr = t.nodes.new('ShaderNodeBsdfTransparent')
    em = t.nodes.new('ShaderNodeEmission')
    mx = t.nodes.new('ShaderNodeMixShader')
    o = t.nodes.new('ShaderNodeOutputMaterial')
    em.inputs['Color'].default_value = (*rgb, 1.0)
    t.links.new(geo.outputs['Position'], sep.inputs['Vector'])
    t.links.new(sep.outputs['X'], mr.inputs[0])
    mr.inputs[1].default_value = edge_x            # From Min
    mr.inputs[2].default_value = edge_x - feather  # From Max
    mr.inputs[3].default_value = 1.0               # To Min
    mr.inputs[4].default_value = 0.0               # To Max
    mr.clamp = True
    t.links.new(mr.outputs[0], mx.inputs[0])
    t.links.new(tr.outputs[0], mx.inputs[1])
    t.links.new(em.outputs['Emission'], mx.inputs[2])
    t.links.new(mx.outputs[0], o.inputs['Surface'])
    m.surface_render_method = 'BLENDED'
    return m


# three swatches: brand-exact colour check
for i, (nm, col) in enumerate((("g", GROUND), ("k", INK), ("r", RED))):
    q = quad("SW_" + nm, -900 + i * 300, -700 + i * 300, 300, 500)
    mm = bpy.data.materials.new("M" + nm)
    mm.use_nodes = True
    tt = mm.node_tree
    tt.nodes.clear()
    e = tt.nodes.new('ShaderNodeEmission')
    e.inputs['Color'].default_value = (*col, 1.0)
    oo = tt.nodes.new('ShaderNodeOutputMaterial')
    tt.links.new(e.outputs['Emission'], oo.inputs['Surface'])
    mm.surface_render_method = 'DITHERED'
    q.data.materials.append(mm)

# wipe-edge AA test: HARD (feather 0.001) vs SOFT (feather 1.5), plus a plain
# GEOMETRY edge as the control for what EEVEE's own AA looks like
hard = quad("HARD", -900, 900, 0, 160)
hard.data.materials.append(wipe_mat("M_HARD", INK, 0.0, 0.001))
soft = quad("SOFT", -900, 900, -200, -40)
soft.data.materials.append(wipe_mat("M_SOFT", INK, 0.0, 1.5))
ctrl = quad("CTRL", -900, 0, -400, -240)
mc = bpy.data.materials.new("M_CTRL")
mc.use_nodes = True
tc2 = mc.node_tree
tc2.nodes.clear()
e2 = tc2.nodes.new('ShaderNodeEmission')
e2.inputs['Color'].default_value = (*INK, 1.0)
o2 = tc2.nodes.new('ShaderNodeOutputMaterial')
tc2.links.new(e2.outputs['Emission'], o2.inputs['Surface'])
mc.surface_render_method = 'BLENDED'
ctrl.data.materials.append(mc)

ims = sc.render.image_settings
ims.color_management = 'OVERRIDE'
ims.view_settings.view_transform = 'Standard'
ims.view_settings.look = 'None'
ims.media_type = 'IMAGE'
ims.file_format = 'PNG'
ims.color_mode = 'RGBA'
ims.color_depth = '8'
sc.render.filepath = os.path.join(OUT, "probe_")
bpy.ops.render.render(animation=True)
print("  rendered ->", OUT)
print("PROBE DONE")
