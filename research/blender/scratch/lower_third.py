import bpy, os, sys

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"
MODE = sys.argv[-1]          # 'default' or 'correct'

BG, INK, RED = "15181D", "F2EEE3", "D42B2B"


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hx(h):
    return tuple(s2l(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.image_settings.media_type = 'IMAGE'
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'
sc.eevee.taa_render_samples = 64

if MODE == 'correct':
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.dither_intensity = 0.0
# else: leave factory defaults (AgX, dither 1.0)

# camera: ortho, 16 units wide
cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 16.0
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam)
cam.location = (0, 0, 10); sc.camera = cam

world = bpy.data.worlds.new("W"); sc.world = world; world.use_nodes = True
wb = world.node_tree.nodes["Background"]
wb.inputs[0].default_value = (*hx(BG), 1.0); wb.inputs[1].default_value = 1.0


def emission_mat(name, colour_hex, strength=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    m.surface_render_method = 'BLENDED'
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission"); o = nt.nodes.new("ShaderNodeOutputMaterial")
    e.inputs[0].default_value = (*hx(colour_hex), 1.0)
    e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def rect(name, x, y, w, h, mat, z=0.0):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x, y, z), (x + w, y, z), (x + w, y + h, z), (x, y + h, z)], [], [(0, 1, 2, 3)])
    me.update()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o)
    o.data.materials.append(mat)
    return o


# dark card
rect("card", -7.0, -3.6, 14.0, 3.2, emission_mat("mcard", BG), z=0.0)
# red accent bar
rect("bar", -7.0, -3.6, 0.28, 3.2, emission_mat("mbar", RED), z=0.01)

# headline text
cu = bpy.data.curves.new("hl", type='FONT')
cu.font = bpy.data.fonts.load(FONT, check_existing=True)
cu.body = "BOYD CLIPS"
cu.size = 1.15
cu.align_x = 'LEFT'
cu.align_y = 'BOTTOM_BASELINE'
tob = bpy.data.objects.new("hl", cu); sc.collection.objects.link(tob)
tob.data.materials.append(emission_mat("mtxt", INK))
tob.location = (-6.3, -2.05, 0.02)

# sub text
cu2 = bpy.data.curves.new("sb", type='FONT')
cu2.font = bpy.data.fonts.load(r"C:\Users\natha\Projects\boyd-clips\assets\fonts\BebasNeue-Regular.ttf",
                               check_existing=True)
cu2.body = "EPISODE 12  /  COLOUR PIPELINE"
cu2.size = 0.45
cu2.align_y = 'BOTTOM_BASELINE'
sob = bpy.data.objects.new("sb", cu2); sc.collection.objects.link(sob)
sob.data.materials.append(emission_mat("msub", RED))
sob.location = (-6.3, -3.05, 0.02)

# logo, right side, alpha-blended image texture
img = bpy.data.images.load(LOGO, check_existing=True)
img.alpha_mode = 'STRAIGHT'
img.colorspace_settings.name = 'sRGB'
lw, lh = img.size
aspect = lw / lh
lm = bpy.data.materials.new("mlogo"); lm.use_nodes = True
lm.surface_render_method = 'BLENDED'
nt = lm.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
tex.interpolation = 'Cubic'
em = nt.nodes.new("ShaderNodeEmission")
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
mx = nt.nodes.new("ShaderNodeMixShader")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tex.outputs["Color"], em.inputs[0])
nt.links.new(tex.outputs["Alpha"], mx.inputs[0])
nt.links.new(tr.outputs[0], mx.inputs[1])
nt.links.new(em.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], out.inputs[0])

LH = 1.0
lo = rect("logo", 6.3 - LH * aspect, -2.85, LH * aspect, LH, lm, z=0.02)
me = lo.data
me.uv_layers.new(name="UV")
uv = me.uv_layers[0].data
for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
    uv[i].uv = c

# MUST flush before measuring anything
bpy.context.view_layer.update()
print("headline width :", round(tob.dimensions.x, 3), " font:", cu.font.name)
print("sub width      :", round(sob.dimensions.x, 3), " font:", cu2.font.name)
print("view_transform :", sc.view_settings.view_transform, " look:", sc.view_settings.look,
      " dither:", sc.render.dither_intensity)

sc.render.filepath = os.path.join(OUT, "lower_third_%s.png" % MODE)
bpy.ops.render.render(write_still=True)
