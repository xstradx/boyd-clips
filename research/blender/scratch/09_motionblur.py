"""ITEM 3: motion blur, EEVEE vs Cycles, on vs off, with numeric pixel proof."""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\mblur"
os.makedirs(OUT, exist_ok=True)
ENGINE = sys.argv[sys.argv.index("--") + 1]
STEPS = 16


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 480, 270
    sc.render.image_settings.file_format = 'PNG'
    sc.render.film_transparent = False
    sc.frame_start, sc.frame_end = 1, 20

    w = bpy.data.worlds.new("W"); sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.024, 0.03, 1)

    # fast object: crosses the whole frame in 2 frames
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.8, location=(0, 0, 0))
    ob = bpy.context.object
    bpy.ops.object.shade_smooth()
    ob.location = (-9, 0, 0); ob.keyframe_insert("location", frame=1)
    ob.location = (9, 0, 0);  ob.keyframe_insert("location", frame=5)
    # LINEAR so speed at frame 3 is constant and high (~4.5 units/frame)
    ad = ob.animation_data
    cb = ad.action.layers[0].strips[0].channelbag(ad.action_slot)
    for fc in cb.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()

    mat = bpy.data.materials.new("M"); mat.use_nodes = True
    ob.data.materials.append(mat)
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.831, 0.169, 0.169, 1)
    b.inputs["Emission Color"].default_value = (0.95, 0.30, 0.25, 1)
    b.inputs["Emission Strength"].default_value = 6.0

    bpy.ops.object.camera_add(location=(0, -18, 0), rotation=(1.5708, 0, 0))
    sc.camera = bpy.context.object
    sc.camera.data.lens = 50
    return sc, ob


def render(sc, tag, blur):
    sc.render.engine = ENGINE
    if ENGINE == 'CYCLES':
        sc.cycles.samples = 24
        sc.cycles.device = 'CPU'
    else:
        sc.eevee.taa_render_samples = 32
        sc.eevee.motion_blur_steps = STEPS
    sc.render.use_motion_blur = blur
    sc.render.motion_blur_shutter = 1.0
    sc.render.motion_blur_position = 'CENTER'
    sc.frame_set(3)
    sc.render.filepath = os.path.join(OUT, f"{tag}_")
    bpy.ops.render.render(write_still=True)
    p = os.path.join(OUT, f"{tag}_.png")
    return p


sc, ob = build()
print(f"ENGINE={ENGINE}  use_motion_blur prop exists:", 'use_motion_blur' in sc.render.bl_rna.properties)
if ENGINE == 'BLENDER_EEVEE':
    print("eevee.motion_blur_steps:", sc.eevee.motion_blur_steps,
          "motion_blur_max:", sc.eevee.motion_blur_max,
          "motion_blur_depth_scale:", sc.eevee.motion_blur_depth_scale)

p_off = render(sc, f"{ENGINE}_off", False)
p_on = render(sc, f"{ENGINE}_on", True)
print("shutter =", sc.render.motion_blur_shutter, "position =", sc.render.motion_blur_position)

# numeric comparison
a = bpy.data.images.load(p_off)
b = bpy.data.images.load(p_on)
pa, pb = list(a.pixels), list(b.pixels)
n = len(pa)
diff = sum(abs(pa[i] - pb[i]) for i in range(0, n, 4))  # R channel only
maxd = max(abs(pa[i] - pb[i]) for i in range(0, n, 4))
# count lit pixels (R > 0.15) as a proxy for smear width
lit_off = sum(1 for i in range(0, n, 4) if pa[i] > 0.15)
lit_on = sum(1 for i in range(0, n, 4) if pb[i] > 0.15)
print(f"\n--- {ENGINE} frame 3 (object speed 4.5 u/frame) ---")
print(f"off: {p_off}")
print(f"on : {p_on}")
print(f"mean |dR| = {diff/(n/4):.6f}   max |dR| = {maxd:.4f}")
print(f"lit pixels (R>0.15): OFF={lit_off}  ON={lit_on}  ratio={lit_on/max(lit_off,1):.2f}x")
print("VERDICT:", "MOTION BLUR VISIBLE" if lit_on > lit_off * 1.3 else "NO SIGNIFICANT BLUR")
