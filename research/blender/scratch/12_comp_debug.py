"""Find how the render result actually enters scene.compositing_node_group."""
import bpy, os, sys
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\compdbg"
os.makedirs(OUT, exist_ok=True)
MODE = sys.argv[sys.argv.index("--") + 1]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 320, 180
sc.render.image_settings.file_format = 'PNG'
sc.eevee.taa_render_samples = 8
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.1, 0.12, 0.15, 1)
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.2)
o = bpy.context.object
m = bpy.data.materials.new("M"); m.use_nodes = True; o.data.materials.append(m)
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Emission Color"].default_value = (1, 0.3, 0.25, 1)
b.inputs["Emission Strength"].default_value = 12.0
bpy.ops.object.camera_add(location=(0, -6, 0), rotation=(1.5708, 0, 0))
sc.camera = bpy.context.object

ng = bpy.data.node_groups.new("G", "CompositorNodeTree")
sc.compositing_node_group = ng
N, L = ng.nodes, ng.links

if MODE == "passthrough":
    ng.interface.new_socket("Image", in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    gin = N.new("NodeGroupInput"); gout = N.new("NodeGroupOutput")
    L.new(gin.outputs["Image"], gout.inputs["Image"])

elif MODE == "rlayers":
    ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = N.new("CompositorNodeRLayers"); rl.scene = sc
    gout = N.new("NodeGroupOutput")
    L.new(rl.outputs["Image"], gout.inputs["Image"])

elif MODE == "rlayers_glare":
    ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = N.new("CompositorNodeRLayers"); rl.scene = sc
    g = N.new("CompositorNodeGlare")
    g.inputs["Type"].default_value = 'Bloom'
    g.inputs["Threshold"].default_value = 0.5
    g.inputs["Strength"].default_value = 1.0
    g.inputs["Size"].default_value = 0.7
    gout = N.new("NodeGroupOutput")
    L.new(rl.outputs["Image"], g.inputs["Image"])
    L.new(g.outputs["Image"], gout.inputs["Image"])

elif MODE == "none":
    sc.compositing_node_group = None

print("MODE:", MODE)
print("group inputs :", [(s.name, s.in_out) for s in ng.interface.items_tree])
print("nodes:", [n.bl_idname for n in N], "links:", len(L))

sc.render.filepath = os.path.join(OUT, f"{MODE}_")
bpy.ops.render.render(write_still=True)
img = bpy.data.images.load(os.path.join(OUT, f"{MODE}_.png"))
px = list(img.pixels)
W = img.size[0]
def at(x, y):
    i = (y*W + x)*4
    return [round(px[i+k], 4) for k in range(4)]
print("centre:", at(160, 90), " edge:", at(8, 8), " mid-left:", at(40, 90))
print("max R:", round(max(px[0::4]), 4), " mean R:", round(sum(px[0::4])/(len(px)//4), 5))
