"""ITEM 4: compositor from Python in Blender 5.0 -- glow/bloom, chromatic
aberration, vignette, colour grading. Renders with comp OFF then ON."""
import bpy, os, sys

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\comp"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 640, 360
sc.render.image_settings.file_format = 'PNG'
sc.eevee.taa_render_samples = 32

w = bpy.data.worlds.new("W"); sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.082, 0.094, 0.114, 1)

# bright emissive shapes so glare has something to grab
for i, x in enumerate((-3.2, 0, 3.2)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, location=(x, 0, 0))
    o = bpy.context.object
    bpy.ops.object.shade_smooth()
    m = bpy.data.materials.new(f"M{i}"); m.use_nodes = True
    o.data.materials.append(m)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.831, 0.169, 0.169, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.25, 0.2, 1)
    b.inputs["Emission Strength"].default_value = 14.0

bpy.ops.object.camera_add(location=(0, -12, 0), rotation=(1.5708, 0, 0))
sc.camera = bpy.context.object
sc.camera.data.lens = 50

# ---------- render WITHOUT compositor ----------
sc.render.filepath = os.path.join(OUT, "comp_off_")
bpy.ops.render.render(write_still=True)
print("rendered comp_off")

# ---------- build the compositing node group ----------
ng = bpy.data.node_groups.new("BoydGrade", "CompositorNodeTree")
sc.compositing_node_group = ng
ng.interface.new_socket("Image", in_out='INPUT', socket_type='NodeSocketColor')
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')

N = ng.nodes
L = ng.links
gin = N.new("NodeGroupInput");  gin.location = (-1000, 0)
gout = N.new("NodeGroupOutput"); gout.location = (1000, 0)

# 1) BLOOM  (EEVEE has no bloom property in 5.0 -- it is compositor-only)
glare = N.new("CompositorNodeGlare"); glare.location = (-760, 0)
glare.inputs["Type"].default_value = 'Bloom'
glare.inputs["Quality"].default_value = 'High'
glare.inputs["Threshold"].default_value = 0.6
glare.inputs["Strength"].default_value = 1.0
glare.inputs["Size"].default_value = 0.6

# 2) CHROMATIC ABERRATION  (Lens Distortion 'Dispersion')
lens = N.new("CompositorNodeLensdist"); lens.location = (-500, 0)
lens.inputs["Type"].default_value = 'Radial'
lens.inputs["Distortion"].default_value = 0.015
lens.inputs["Dispersion"].default_value = 0.35
lens.inputs["Fit"].default_value = True

# 3) COLOUR GRADE  (lift/gamma/gain + temperature)
cb = N.new("CompositorNodeColorBalance"); cb.location = (-240, 0)


def sock(node, name, stype):
    """Compositor nodes in 5.0 reuse socket NAMES across types (e.g. 'Lift'
    exists as both VALUE and RGBA). Always disambiguate by type."""
    m = [s for s in node.inputs if s.name == name and s.type == stype]
    assert m, f"{node.bl_idname}: no input {name!r} of type {stype}; have " \
              f"{[(s.name, s.type) for s in node.inputs]}"
    return m[0]


print("ColorBalance sockets:", [(s.name, s.type, s.identifier) for s in cb.inputs])
cb.inputs["Type"].default_value = 'Lift/Gamma/Gain'
sock(cb, "Lift", 'RGBA').default_value = (0.04, 0.05, 0.09, 1.0)   # cool shadows
sock(cb, "Gamma", 'RGBA').default_value = (1.0, 0.98, 0.95, 1.0)
sock(cb, "Gain", 'RGBA').default_value = (1.06, 1.00, 0.94, 1.0)   # warm highlights

hs = N.new("CompositorNodeHueSat"); hs.location = (0, 0)
hs.inputs["Saturation"].default_value = 1.25

# 4) VIGNETTE  (no Vignette node in 5.0 -- build from EllipseMask + Blur + Multiply)
ell = N.new("CompositorNodeEllipseMask"); ell.location = (-240, -320)
ell.inputs["Position"].default_value = (0.5, 0.5)
ell.inputs["Size"].default_value = (0.62, 0.72)
blur = N.new("CompositorNodeBlur"); blur.location = (0, -320)
blur.inputs["Type"].default_value = 'Fast Gaussian'
blur.inputs["Size"].default_value = (0.18, 0.18)

mix = N.new("ShaderNodeMix"); mix.location = (300, 0)
mix.data_type = 'RGBA'
mix.blend_type = 'MULTIPLY'
# ShaderNodeMix has same-named sockets per data type -> pick by index
rgba_in = [s for s in mix.inputs if s.type == 'RGBA']
fac_in = [s for s in mix.inputs if s.name == 'Factor'][0]
fac_in.default_value = 0.85
print("ShaderNodeMix RGBA sockets:", [(s.name, s.identifier) for s in rgba_in])
print("ShaderNodeMix Factor identifiers:", [(s.name, s.identifier, s.type) for s in mix.inputs if s.name == 'Factor'])

L.new(gin.outputs["Image"], glare.inputs["Image"])
L.new(glare.outputs["Image"], lens.inputs["Image"])
L.new(lens.outputs["Image"], cb.inputs["Image"])
L.new(cb.outputs["Image"], hs.inputs["Image"])
L.new(ell.outputs["Mask"], blur.inputs["Image"])
L.new(hs.outputs["Image"], rgba_in[0])
L.new(blur.outputs["Image"], rgba_in[1])
L.new(mix.outputs["Result"], gout.inputs["Image"])

print("nodes:", [n.bl_idname for n in N])
print("links:", len(L))

sc.render.filepath = os.path.join(OUT, "comp_on_")
bpy.ops.render.render(write_still=True)
print("rendered comp_on")

a = bpy.data.images.load(os.path.join(OUT, "comp_off_.png"))
b = bpy.data.images.load(os.path.join(OUT, "comp_on_.png"))
pa, pb = list(a.pixels), list(b.pixels)
n = len(pa)
mean = sum(abs(pa[i]-pb[i]) for i in range(n)) / n
print(f"mean |dRGBA| off vs on = {mean:.6f}")
# corner darkness = vignette proof
def px(img, x, y):
    W = img.size[0]; i = (y*W + x)*4
    return img.pixels[i], img.pixels[i+1], img.pixels[i+2]
print("corner(4,4)   off:", [round(v,4) for v in px(a,4,4)],   "on:", [round(v,4) for v in px(b,4,4)])
print("centre(320,180) off:", [round(v,4) for v in px(a,320,180)], "on:", [round(v,4) for v in px(b,320,180)])
print("VERDICT:", "COMPOSITOR APPLIED" if mean > 0.005 else "NO EFFECT")
