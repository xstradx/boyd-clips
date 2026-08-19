"""ITEM 6 + 1 + 2 + 5: prove animation evaluates per-frame in -b mode.

Keyframes object transform, material value and camera; sets per-keyframe
interpolation/easing; renders frames 1..N; hashes each PNG.
"""
import bpy, sys, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boyd_anim import get_fcurves, find_fcurve, set_interp, cubic_bezier_ease

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\frames"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 320, 180
sc.render.image_settings.file_format = 'PNG'
sc.eevee.taa_render_samples = 8
sc.frame_start, sc.frame_end = 1, 12

# --- world ---
w = bpy.data.worlds.new("W"); sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.082, 0.094, 0.114, 1)  # #15181D

# --- object ---
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(-4, 0, 0))
ob = bpy.context.object
ob.location = (-4, 0, 0); ob.keyframe_insert("location", frame=1)
ob.location = (4, 0, 0);  ob.keyframe_insert("location", frame=12)
ob.rotation_euler = (0, 0, 0); ob.keyframe_insert("rotation_euler", frame=1)
ob.rotation_euler = (0, 0, 3.14159); ob.keyframe_insert("rotation_euler", frame=12)

# --- material with animated emission strength ---
mat = bpy.data.materials.new("M"); mat.use_nodes = True
ob.data.materials.append(mat)
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.831, 0.169, 0.169, 1)  # #D42B2B
em = bsdf.inputs["Emission Strength"]
em.default_value = 0.0
em.keyframe_insert("default_value", frame=1)
em.default_value = 8.0
em.keyframe_insert("default_value", frame=12)

# --- camera with DOF (item 5) ---
bpy.ops.object.camera_add(location=(0, -12, 2), rotation=(1.4, 0, 0))
cam = bpy.context.object
sc.camera = cam
cam.data.dof.use_dof = True
cam.data.dof.focus_object = ob
cam.data.dof.aperture_fstop = 0.6
cam.data.lens = 50.0
cam.data.keyframe_insert("lens", frame=1)
cam.data.lens = 85.0
cam.data.keyframe_insert("lens", frame=12)

# --- item 1: per-keyframe interpolation + easing ---
set_interp(ob, "location", 0, interpolation='BACK', easing='EASE_OUT', back=2.5)
set_interp(ob, "rotation_euler", 2, interpolation='EXPO', easing='EASE_IN_OUT')

print("MATERIAL fcurves:", [(f.data_path, f.array_index) for f in (get_fcurves(mat.node_tree) or [])])
EM_PATH = get_fcurves(mat.node_tree)[0].data_path
print("discovered emission data_path:", EM_PATH)
set_interp(mat.node_tree, EM_PATH, 0,
           interpolation='ELASTIC', easing='EASE_OUT', amplitude=1.2, period=4.0)
print("CAMERA DATA fcurves:", [(f.data_path, f.array_index) for f in (get_fcurves(cam.data) or [])])

fl = find_fcurve(ob, "location", 0)
print("loc.x kf0 interp/easing/back:", fl.keyframe_points[0].interpolation,
      fl.keyframe_points[0].easing, round(fl.keyframe_points[0].back, 3))

# --- item 2: custom bezier ease-out on camera lens ---
fcl = find_fcurve(cam.data, "lens", 0)
h = cubic_bezier_ease(fcl, 0, p1=(0.0, 0.9), p2=(0.2, 1.0))  # strong ease-out
print("lens handles set:", h)

# --- sample the evaluated fcurves analytically ---
print("\n=== fcurve.evaluate() per frame ===")
print("frame | loc.x(BACK/OUT) | lens(custom ease-out) | emission(ELASTIC)")
fem = find_fcurve(mat.node_tree, EM_PATH, 0)
for f in range(1, 13):
    print(f"  {f:2d}  | {fl.evaluate(f):9.4f} | {fcl.evaluate(f):9.4f} | {fem.evaluate(f):9.4f}")

# --- also sample the DEPSGRAPH (real evaluated state), not just the curve ---
print("\n=== depsgraph evaluated object matrix per frame ===")
dg = bpy.context.evaluated_depsgraph_get()
for f in range(1, 13):
    sc.frame_set(f)
    dg.update()
    obe = ob.evaluated_get(dg)
    print(f"  frame {f:2d}: world x={obe.matrix_world.translation.x:8.4f}  camlens={cam.data.evaluated_get(dg).lens:7.3f}")

# --- render the sequence ---
sc.render.filepath = os.path.join(OUT, "f_")
print("\n=== rendering frames 1..12 ===")
bpy.ops.render.render(animation=True)

files = sorted(f for f in os.listdir(OUT) if f.endswith(".png"))
print("\n=== FRAME HASHES ===")
hashes = {}
for fn in files:
    p = os.path.join(OUT, fn)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    hashes[fn] = h
    print(f"  {fn}  {os.path.getsize(p):7d} bytes  sha256:{h}")
uniq = len(set(hashes.values()))
print(f"\nRESULT: {len(files)} frames, {uniq} unique hashes -> "
      f"{'PASS (animation evaluated)' if uniq == len(files) else 'FAIL (frozen frames)'}")
