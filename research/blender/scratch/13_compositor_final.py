"""ITEM 4 (working): full compositor grade in Blender 5.0 from Python.
bloom + chromatic aberration + colour grade + vignette. Renders OFF then ON."""
import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\comp"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 640, 360
sc.render.image_settings.file_format = 'PNG'
sc.eevee.taa_render_samples = 32

w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.082, 0.094, 0.114, 1)

for i, x in enumerate((-3.2, 0, 3.2)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, location=(x, 0, 0))
    o = bpy.context.object
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.new(f"M{i}"); m.use_nodes = True; o.data.materials.append(m)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.831, 0.169, 0.169, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.25, 0.2, 1)
    b.inputs["Emission Strength"].default_value = 14.0

bpy.ops.object.camera_add(location=(0, -12, 0), rotation=(1.5708, 0, 0))
sc.camera = bpy.context.object; sc.camera.data.lens = 50

sc.render.filepath = os.path.join(OUT, "final_off_")
bpy.ops.render.render(write_still=True)


def sock(node, name, stype):
    m = [s for s in node.inputs if s.name == name and s.type == stype]
    assert m, f"{node.bl_idname}: no {name!r}/{stype}; have {[(s.name, s.type) for s in node.inputs]}"
    return m[0]


ng = bpy.data.node_groups.new("BoydGrade", "CompositorNodeTree")
sc.compositing_node_group = ng
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
N, L = ng.nodes, ng.links

rl = N.new("CompositorNodeRLayers"); rl.scene = sc; rl.location = (-1100, 0)
gout = N.new("NodeGroupOutput"); gout.location = (500, 0)

glare = N.new("CompositorNodeGlare"); glare.location = (-880, 0)
glare.inputs["Type"].default_value = 'Bloom'
glare.inputs["Quality"].default_value = 'High'
glare.inputs["Threshold"].default_value = 0.7
glare.inputs["Strength"].default_value = 0.8
glare.inputs["Size"].default_value = 0.7

lens = N.new("CompositorNodeLensdist"); lens.location = (-660, 0)
lens.inputs["Type"].default_value = 'Radial'
lens.inputs["Distortion"].default_value = 0.02
lens.inputs["Dispersion"].default_value = 0.5
lens.inputs["Fit"].default_value = True

cb = N.new("CompositorNodeColorBalance"); cb.location = (-440, 0)
cb.inputs["Type"].default_value = 'Lift/Gamma/Gain'
sock(cb, "Lift", 'RGBA').default_value = (0.03, 0.05, 0.10, 1.0)
sock(cb, "Gamma", 'RGBA').default_value = (1.0, 0.97, 0.93, 1.0)
sock(cb, "Gain", 'RGBA').default_value = (1.08, 1.00, 0.92, 1.0)

hs = N.new("CompositorNodeHueSat"); hs.location = (-220, 0)
hs.inputs["Saturation"].default_value = 1.3

# vignette: ellipse mask -> blur -> multiply
ell = N.new("CompositorNodeEllipseMask"); ell.location = (-440, -340)
ell.inputs["Position"].default_value = (0.5, 0.5)
ell.inputs["Size"].default_value = (0.60, 0.68)
blur = N.new("CompositorNodeBlur"); blur.location = (-220, -340)
blur.inputs["Type"].default_value = 'Fast Gaussian'
blur.inputs["Size"].default_value = (0.20, 0.20)

mix = N.new("ShaderNodeMix"); mix.location = (200, 0)
mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
def by_id(node, ident):
    """node.inputs[...] keys by NAME (which is ambiguous on 5.0 multi-type
    nodes). This looks up the unique socket *identifier* instead."""
    m = [s for s in node.inputs if s.identifier == ident]
    assert m, f"{node.bl_idname}: no socket id {ident!r}; have {[s.identifier for s in node.inputs]}"
    return m[0]


by_id(mix, 'Factor_Float').default_value = 0.9

L.new(rl.outputs["Image"], glare.inputs["Image"])
L.new(glare.outputs["Image"], lens.inputs["Image"])
L.new(lens.outputs["Image"], cb.inputs["Image"])
L.new(cb.outputs["Image"], hs.inputs["Image"])
L.new(ell.outputs["Mask"], blur.inputs["Image"])
L.new(hs.outputs["Image"], by_id(mix,'A_Color'))
L.new(blur.outputs["Image"], by_id(mix,'B_Color'))
L.new(mix.outputs["Result"], gout.inputs["Image"])
print("nodes:", [n.bl_idname for n in N], "links:", len(L))

sc.render.filepath = os.path.join(OUT, "final_on_")
bpy.ops.render.render(write_still=True)

a = bpy.data.images.load(os.path.join(OUT, "final_off_.png"))
b = bpy.data.images.load(os.path.join(OUT, "final_on_.png"))
pa, pb = list(a.pixels), list(b.pixels)
W = a.size[0]
def at(p, x, y):
    i = (y*W + x)*4
    return [round(p[i+k], 4) for k in range(3)]
print("mean |d| =", round(sum(abs(pa[i]-pb[i]) for i in range(len(pa)))/len(pa), 5))
print("corner (6,6)      off:", at(pa,6,6),      "on:", at(pb,6,6))
print("centre (320,180)  off:", at(pa,320,180),  "on:", at(pb,320,180))
print("gap    (160,180)  off:", at(pa,160,180),  "on:", at(pb,160,180))
