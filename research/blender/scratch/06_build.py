import bpy, os, math, sys, traceback

LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
OUT  = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"

def hexf(h):
    h = h.lstrip('#')
    srgb = [int(h[i:i+2],16)/255.0 for i in (0,2,4)]
    # sRGB -> linear
    lin = [c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4 for c in srgb]
    return (lin[0], lin[1], lin[2], 1.0)

BG     = hexf("15181D")
INK    = hexf("F2EEE3")
ACCENT = hexf("D42B2B")

def step(name):
    print("\n" + "="*8 + " " + name + " " + "="*8)

# ---------------- 1. SCENE FROM SCRATCH ----------------
step("1 SCENE FROM SCRATCH")
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
print("objects after empty load:", list(bpy.data.objects.keys()))
print("scene name:", sc.name, "| world:", sc.world)

sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.resolution_percentage = 100
sc.render.fps = 30
sc.render.fps_base = 1.0
sc.frame_start = 1
sc.frame_end = 12
print("res:", sc.render.resolution_x, "x", sc.render.resolution_y,
      "| fps:", sc.render.fps, "| frames:", sc.frame_start, "-", sc.frame_end)

w = bpy.data.worlds.new("BoydWorld")
sc.world = w
w.use_nodes = True
bgnode = w.node_tree.nodes["Background"]
bgnode.inputs["Color"].default_value = BG
bgnode.inputs["Strength"].default_value = 1.0
print("world bg color set to:", tuple(round(x,4) for x in bgnode.inputs["Color"].default_value))
# also verify the no-nodes fallback path
print("world.color attr:", tuple(w.color))

# camera + light
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
cam.location = (0, -6.0, 0)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam
print("camera:", sc.camera.name)

lamp_data = bpy.data.lights.new("Key", type='AREA')
lamp_data.energy = 800
lamp_data.size = 6
lamp = bpy.data.objects.new("Key", lamp_data)
sc.collection.objects.link(lamp)
lamp.location = (3, -4, 3)
lamp.rotation_euler = (math.radians(55), 0, math.radians(35))
print("light:", lamp.name, lamp_data.type, lamp_data.energy)

# ---------------- 4. MATERIALS ----------------
step("4 MATERIALS via node trees")
def make_emissive(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    print(f"  emissive '{name}': links={len(nt.links)} nodes={[n.bl_idname for n in nt.nodes]}")
    return m

def make_solid(name, color, rough=0.4, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    # 5.0 emission socket names
    b.inputs["Emission Color"].default_value = color
    b.inputs["Emission Strength"].default_value = 0.0
    print(f"  solid '{name}': BaseColor={tuple(round(x,3) for x in b.inputs['Base Color'].default_value)} Rough={b.inputs['Roughness'].default_value}")
    return m

mat_emis_red = make_emissive("BoydEmisRed", ACCENT, 6.0)
mat_ink      = make_solid("BoydInk", INK, rough=0.35)
mat_red      = make_solid("BoydRed", ACCENT, rough=0.25, metal=0.3)

# ---------------- 3. TEXT OBJECT ----------------
step("3 TEXT OBJECT + TTF FONT + EXTRUDE/BEVEL")
print("font file exists:", os.path.exists(FONT))
fnt = bpy.data.fonts.load(FONT)
print("loaded font:", fnt.name, "| filepath:", fnt.filepath)

tc = bpy.data.curves.new("BoydTxt", type='FONT')
tob = bpy.data.objects.new("BoydTxt", tc)
sc.collection.objects.link(tob)
tc.body = "BOYD"
tc.font = fnt
tc.size = 1.6
tc.align_x = 'CENTER'
tc.align_y = 'CENTER'
tc.extrude = 0.12
tc.bevel_depth = 0.02
tc.bevel_resolution = 3
tob.location = (0, 0, -0.9)
tob.data.materials.append(mat_ink)
print("text body:", tc.body, "| font:", tc.font.name, "| extrude:", tc.extrude,
      "| bevel_depth:", tc.bevel_depth, "| mats:", [m.name for m in tc.materials])
# prove the font actually generated geometry
dg = bpy.context.evaluated_depsgraph_get()
ev = tob.evaluated_get(dg)
me = ev.to_mesh()
print("evaluated text mesh verts:", len(me.vertices), "polys:", len(me.polygons))
ev.to_mesh_clear()

# ---------------- 2. LOGO IMPORT ----------------
step("2a LOGO -> bpy.ops.image.import_as_mesh_planes")
print("logo exists:", os.path.exists(LOGO))
before = set(bpy.data.objects.keys())
try:
    _d, _f = os.path.split(LOGO)
    r = bpy.ops.image.import_as_mesh_planes(
        directory=_d, files=[{"name": _f}],
        shader='EMISSION',
        emit_strength=1.5,
        use_transparency=True,
        render_method='BLENDED',
        size_mode='ABSOLUTE',
        height=1.4,
        align_axis='+Y',
        location=(0.0, 0.0, 0.9),
    )
    print("operator returned:", r)
    new = set(bpy.data.objects.keys()) - before
    print("NEW OBJECTS:", new)
    for n in new:
        o = bpy.data.objects[n]
        print("  ", n, "type:", o.type, "verts:", len(o.data.vertices),
              "dims:", tuple(round(x,3) for x in o.dimensions),
              "mats:", [m.name for m in o.data.materials])
        mm = o.data.materials[0]
        print("   nodes:", [(nd.bl_idname, nd.name) for nd in mm.node_tree.nodes])
        for lk in mm.node_tree.links:
            print("   link:", lk.from_node.bl_idname, lk.from_socket.name, "->", lk.to_node.bl_idname, lk.to_socket.name)
        print("   blend_method:", getattr(mm, 'blend_method', '<no blend_method attr>'))
        print("   surface_render_method:", getattr(mm, 'surface_render_method', '<missing>'))
        PLANE = o
except Exception as e:
    print("ERR import_as_mesh_planes:", type(e).__name__, e)
    traceback.print_exc()
    PLANE = None

step("2b LOGO -> manual image texture on a mesh")
img = bpy.data.images.load(LOGO)
print("bpy.data.images.load ok:", img.name, "size:", tuple(img.size), "channels:", img.channels,
      "has_data:", img.has_data, "alpha_mode:", img.alpha_mode, "colorspace:", img.colorspace_settings.name)
bpy.ops.mesh.primitive_plane_add(size=1.0, location=(2.6, 0, 0.9), rotation=(math.radians(90),0,0))
mp = bpy.context.object
mp.name = "LogoManualPlane"
ar = img.size[0]/img.size[1]
mp.scale = (ar*1.2, 1.2, 1.0)
mtex = bpy.data.materials.new("LogoTexMat")
mtex.use_nodes = True
nt = mtex.node_tree
for n in list(nt.nodes): nt.nodes.remove(n)
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
tex.interpolation = 'Linear'
tex.extension = 'CLIP'
em = nt.nodes.new("ShaderNodeEmission")
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
mx = nt.nodes.new("ShaderNodeMixShader")
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tex.outputs["Color"], em.inputs["Color"])
nt.links.new(tex.outputs["Alpha"], mx.inputs["Factor"])
nt.links.new(tr.outputs["BSDF"], mx.inputs[1])
nt.links.new(em.outputs["Emission"], mx.inputs[2])
nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
mtex.surface_render_method = 'BLENDED'
mp.data.materials.append(mtex)
print("manual plane:", mp.name, "dims:", tuple(round(x,3) for x in mp.dimensions))
print("  nodes:", [n.bl_idname for n in nt.nodes], "links:", len(nt.links))
print("  surface_render_method:", mtex.surface_render_method)

step("2c LOGO -> compositor input (CompositorNodeImage in a node group)")
ng = bpy.data.node_groups.new("BoydComp", "CompositorNodeTree")
print("node group:", ng.name, type(ng).__name__)
try:
    sock = ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    print("interface output socket created:", sock.name, sock.socket_type)
except Exception as e:
    print("ERR interface.new_socket:", type(e).__name__, e)
rl  = ng.nodes.new("CompositorNodeRLayers"); rl.location = (-600, 200)
cim = ng.nodes.new("CompositorNodeImage");   cim.location = (-600, -200)
cim.image = img
print("CompositorNodeImage.image =", cim.image.name if cim.image else None)
scl = ng.nodes.new("CompositorNodeScale");   scl.location = (-380, -200)
scl.inputs["X"].default_value = 0.35
scl.inputs["Y"].default_value = 0.35
ao  = ng.nodes.new("CompositorNodeAlphaOver"); ao.location = (-120, 0)
gout= ng.nodes.new("NodeGroupOutput");       gout.location = (150, 0)
ng.links.new(cim.outputs["Image"], scl.inputs["Image"])
ng.links.new(rl.outputs["Image"], ao.inputs["Background"])
ng.links.new(scl.outputs["Image"], ao.inputs["Foreground"])
ng.links.new(ao.outputs["Image"], gout.inputs[0])
sc.compositing_node_group = ng
print("scene.compositing_node_group =", sc.compositing_node_group.name)
print("comp links:", [(l.from_node.bl_idname, l.from_socket.name, '->', l.to_node.bl_idname, l.to_socket.name) for l in ng.links])
print("render.use_compositing:", sc.render.use_compositing)

# emissive accent bar to prove emissive mat renders
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0,0,-2.0))
bar = bpy.context.object; bar.name="AccentBar"; bar.scale=(2.2,0.2,0.05)
bar.data.materials.append(mat_emis_red)
print("accent bar mat:", bar.data.materials[0].name)

# ---------------- 7. FILM TRANSPARENT ----------------
step("7 FILM TRANSPARENT")
print("film_transparent default:", sc.render.film_transparent)
sc.render.film_transparent = False
print("set False ->", sc.render.film_transparent)

blend = os.path.join(OUT, "boyd_scene.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
print("\nSAVED BLEND:", blend, os.path.getsize(blend), "bytes")
print("FINAL OBJECT LIST:", sorted(bpy.data.objects.keys()))
