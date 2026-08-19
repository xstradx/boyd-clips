"""ITEM 6 (hardened): three background render paths, do all produce distinct frames?
  A) bpy.ops.render.render(animation=True)
  B) frame_set() + render(write_still=True) loop      <-- classic freeze suspect
  C) CLI: blender -b file.blend -s 1 -e 8 -a          (driven externally)
Also checks whether motion blur survives path B.
"""
import bpy, os, sys, hashlib

ROOT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\paths"
os.makedirs(ROOT, exist_ok=True)
MODE = sys.argv[sys.argv.index("--") + 1]
NF = 8


def build(mblur):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 240, 135
    sc.render.image_settings.file_format = 'PNG'
    sc.eevee.taa_render_samples = 8
    sc.eevee.motion_blur_steps = 8
    sc.render.use_motion_blur = mblur
    sc.render.motion_blur_shutter = 1.0
    sc.frame_start, sc.frame_end = 1, NF
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.03, 0.04, 1)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.7)
    ob = bpy.context.object
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.new("M"); m.use_nodes = True; ob.data.materials.append(m)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Emission Color"].default_value = (1, 0.3, 0.25, 1)
    b.inputs["Emission Strength"].default_value = 10.0
    ob.location = (-6, 0, 0); ob.keyframe_insert("location", frame=1)
    ob.location = (6, 0, 0);  ob.keyframe_insert("location", frame=NF)
    ad = ob.animation_data
    for fc in ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()
    bpy.ops.object.camera_add(location=(0, -14, 0), rotation=(1.5708, 0, 0))
    sc.camera = bpy.context.object
    return sc, ob


def report(d, label):
    files = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    hs = []
    for fn in files:
        hs.append((fn, hashlib.sha256(open(os.path.join(d, fn), 'rb').read()).hexdigest()[:12]))
    for fn, h in hs:
        print(f"    {fn}  {h}")
    u = len(set(h for _, h in hs))
    print(f"  {label}: {len(files)} frames, {u} unique -> {'PASS' if u == len(files) and len(files) == NF else 'FAIL'}")


if MODE == "A":
    d = os.path.join(ROOT, "A"); os.makedirs(d, exist_ok=True)
    [os.remove(os.path.join(d, f)) for f in os.listdir(d)]
    sc, ob = build(True)
    sc.render.filepath = os.path.join(d, "a_")
    bpy.ops.render.render(animation=True)
    report(d, "A render(animation=True)")

elif MODE == "B":
    d = os.path.join(ROOT, "B"); os.makedirs(d, exist_ok=True)
    [os.remove(os.path.join(d, f)) for f in os.listdir(d)]
    sc, ob = build(True)
    for f in range(1, NF + 1):
        sc.frame_set(f)
        print(f"    frame_set({f}) -> scene.frame_current={sc.frame_current} obj.x={ob.location.x:.3f}")
        sc.render.filepath = os.path.join(d, f"b_{f:04d}")
        bpy.ops.render.render(write_still=True)
    report(d, "B frame_set+write_still loop")

elif MODE == "MAKEBLEND":
    sc, ob = build(True)
    sc.render.filepath = os.path.join(ROOT, "C", "c_")
    os.makedirs(os.path.join(ROOT, "C"), exist_ok=True)
    bp = os.path.join(ROOT, "scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=bp)
    print("saved", bp)

elif MODE == "REPORTC":
    report(os.path.join(ROOT, "C"), "C CLI -s 1 -e 8 -a")
