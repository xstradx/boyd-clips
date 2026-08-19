
# CRITIC TEST 3: silent no-op hunt.
# Agent2 proved frame_set()+write_still animates OBJECT TRANSFORMS, and proved
# animated COMPOSITOR values work under render(animation=True) -- but never
# crossed the two. In 5.0 the compositor is a STANDALONE node_group datablock
# (bpy.data.node_groups), not owned by the Scene like the old scene.node_tree.
# Standalone IDs are a classic depsgraph-miss under manual frame_set().
import bpy, os, numpy as np

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic\fp"
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 160; sc.render.resolution_y = 90
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'
sc.view_settings.view_transform = 'Standard'
sc.frame_start, sc.frame_end = 1, 5
sc.render.dither_intensity = 0.0

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("C"))
sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, 0, 6)

bpy.ops.mesh.primitive_plane_add(size=4)
pl = bpy.context.object
m = bpy.data.materials.new("Emis"); m.use_nodes = True
nt = m.node_tree; nt.nodes.clear()
em = nt.nodes.new("ShaderNodeEmission"); em.inputs['Color'].default_value = (1, 1, 1, 1)
o = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(em.outputs['Emission'], o.inputs['Surface'])
pl.data.materials.append(m)

# (a) animate MATERIAL node socket: Emission Strength 0.1 -> 0.5
st = em.inputs['Strength']
st.default_value = 0.1; st.keyframe_insert('default_value', frame=1)
st.default_value = 0.5; st.keyframe_insert('default_value', frame=5)
for fc in m.node_tree.animation_data.action.layers[0].strips[0].channelbag(
        m.node_tree.animation_data.action_slot).fcurves:
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    fc.update()
print("MATERIAL fcurve:", [fc.data_path for fc in m.node_tree.animation_data.action.layers[0]
      .strips[0].channelbag(m.node_tree.animation_data.action_slot).fcurves])

# (b) animate COMPOSITOR node socket in the standalone node group
ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
bc = ng.nodes.new("CompositorNodeBrightContrast")
gout = ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs['Image'], bc.inputs['Image'])
ng.links.new(bc.outputs['Image'], gout.inputs[0])
sc.compositing_node_group = ng
sc.render.use_compositing = True

bright = bc.inputs['Bright']
bright.default_value = 0.0; bright.keyframe_insert('default_value', frame=1)
bright.default_value = 0.4; bright.keyframe_insert('default_value', frame=5)
for fc in ng.animation_data.action.layers[0].strips[0].channelbag(
        ng.animation_data.action_slot).fcurves:
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    fc.update()
print("COMPOSITOR fcurve:", [fc.data_path for fc in ng.animation_data.action.layers[0]
      .strips[0].channelbag(ng.animation_data.action_slot).fcurves])

# (c) control: animate object transform
pl.location.x = -1.0; pl.keyframe_insert('location', frame=1)
pl.location.x = 1.0;  pl.keyframe_insert('location', frame=5)


def mean_of(p):
    im = bpy.data.images.load(p, check_existing=False)
    a = np.empty(im.size[0]*im.size[1]*4, dtype=np.float32); im.pixels.foreach_get(a)
    v = a.reshape(-1, 4)[:, 0].mean(); bpy.data.images.remove(im)
    return float(v)


print("\n=== PATH A: bpy.ops.render.render(animation=True) ===")
sc.render.filepath = os.path.join(OUT, "A_")
bpy.ops.render.render(animation=True)
A = [mean_of(os.path.join(OUT, "A_%04d.png" % f)) for f in range(1, 6)]
print("  meanR per frame:", [round(v, 5) for v in A])

print("\n=== PATH B: frame_set(n) + render(write_still=True) ===")
B = []
for f in range(1, 6):
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, "B_%04d" % f)
    bpy.ops.render.render(write_still=True)
    B.append(mean_of(os.path.join(OUT, "B_%04d.png" % f)))
    # what does python THINK the values are at this frame?
    print("    f%d  py: emis_strength=%.4f  comp_bright=%.4f  obj.x=%.4f  meanR=%.5f"
          % (f, st.default_value, bright.default_value, pl.location.x, B[-1]))
print("  meanR per frame:", [round(v, 5) for v in B])

print("\n=== VERDICT ===")
same = all(abs(a - b) < 1e-6 for a, b in zip(A, B))
print("  A == B :", same)
print("  A monotonic rising:", all(A[i] < A[i+1] for i in range(4)))
print("  B monotonic rising:", all(B[i] < B[i+1] for i in range(4)))
print("  per-frame |A-B|:", [round(abs(a-b), 6) for a, b in zip(A, B)])

# isolate WHICH of the three animated things (if any) froze under path B
print("\n=== ISOLATION: compositor OFF, so only material+object animate ===")
sc.render.use_compositing = False
C = []
for f in range(1, 6):
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, "C_%04d" % f)
    bpy.ops.render.render(write_still=True)
    C.append(mean_of(os.path.join(OUT, "C_%04d.png" % f)))
print("  meanR per frame (no comp):", [round(v, 5) for v in C])
sc.render.use_compositing = True

print("\n=== ISOLATION: does the COMP group evaluate at all under frame_set? ===")
# render frame 1 and frame 5 with the object+material pinned by muting their action
pl.animation_data.action = None
m.node_tree.animation_data.action = None
D = []
for f in (1, 5):
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, "D_%04d" % f)
    bpy.ops.render.render(write_still=True)
    D.append(mean_of(os.path.join(OUT, "D_%04d.png" % f)))
print("  comp-only, frame1 meanR=%.5f  frame5 meanR=%.5f  delta=%.5f" % (D[0], D[1], D[1]-D[0]))
print("  -> compositor animates under frame_set():", abs(D[1]-D[0]) > 1e-4)
print("\nDONE")
