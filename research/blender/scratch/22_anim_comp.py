"""Can compositor socket values be keyframed, and do they evaluate per-frame in -b?"""
import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boyd_anim import get_fcurves

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\animcomp"
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 320, 180
sc.render.image_settings.file_format = 'PNG'
sc.eevee.taa_render_samples = 8
sc.frame_start, sc.frame_end = 1, 6

w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.03, 0.04, 1)
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0)
o = bpy.context.object
m = bpy.data.materials.new("M"); m.use_nodes = True; o.data.materials.append(m)
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Emission Color"].default_value = (1, 0.3, 0.25, 1)
b.inputs["Emission Strength"].default_value = 10.0
bpy.ops.object.camera_add(location=(0, -7, 0), rotation=(1.5708, 0, 0))
sc.camera = bpy.context.object

ng = bpy.data.node_groups.new("G", "CompositorNodeTree")
sc.compositing_node_group = ng
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
gl = ng.nodes.new("CompositorNodeGlare")
gl.inputs["Type"].default_value = 'Fog Glow'
gl.inputs["Quality"].default_value = 'High'
gl.inputs["Threshold"].default_value = 0.3
gl.inputs["Size"].default_value = 0.8
go = ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
ng.links.new(gl.outputs["Image"], go.inputs["Image"])

# keyframe the glare Strength socket: 0 -> 4 over frames 1..6
st = gl.inputs["Strength"]
st.default_value = 0.0; st.keyframe_insert("default_value", frame=1)
st.default_value = 4.0; st.keyframe_insert("default_value", frame=6)
fcs = get_fcurves(ng)
print("node_group animated?", fcs is not None)
print("comp fcurves:", [(f.data_path, f.array_index) for f in (fcs or [])])
fc = fcs[0]
for kp in fc.keyframe_points:
    kp.interpolation = 'LINEAR'
fc.update()
print("glare strength per frame:", [round(fc.evaluate(f), 3) for f in range(1, 7)])

sc.render.filepath = os.path.join(OUT, "ac_")
bpy.ops.render.render(animation=True)

print("\nmeasured glow spread per rendered frame (lit pixels R>0.10):")
prev = None
ok = True
for f in range(1, 7):
    img = bpy.data.images.load(os.path.join(OUT, f"ac_{f:04d}.png"))
    px = list(img.pixels)
    lit = sum(1 for i in range(0, len(px), 4) if px[i] > 0.10)
    mean = sum(px[0::4]) / (len(px) // 4)
    print(f"  frame {f}: lit={lit:6d}  meanR={mean:.5f}")
    if prev is not None and lit < prev:
        ok = False
    prev = lit
print("VERDICT:", "ANIMATED COMPOSITOR EVALUATES PER FRAME" if ok and prev else "NOT ANIMATING")
