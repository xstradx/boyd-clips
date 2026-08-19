import bpy, os, sys, math

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
HEX = "D42B2B"

def hex_srgb(h):
    return tuple(int(h[i:i+2],16)/255.0 for i in (0,2,4))

def s2l(c):  # sRGB EOTF -> linear (the exact transfer Blender/OCIO uses for sRGB)
    return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4

srgb = hex_srgb(HEX)
lin  = tuple(s2l(c) for c in srgb)
print("TARGET hex   :", "#"+HEX)
print("sRGB 0-1     :", tuple(round(v,6) for v in srgb))
print("LINEAR (Rec709/scene_linear):", tuple(round(v,6) for v in lin))
print()

# ---- build scene from scratch ----
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x = 64
sc.render.resolution_y = 64
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'
sc.render.image_settings.color_depth = '8'

# world = pure black so nothing contaminates
w = bpy.data.worlds.new("W"); sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0,0,0,1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.0

cam_d = bpy.data.cameras.new("C"); cam_d.type='ORTHO'; cam_d.ortho_scale = 2.0
cam = bpy.data.objects.new("Cam", cam_d); sc.collection.objects.link(cam)
cam.location = (0,0,5)
sc.camera = cam

mesh = bpy.data.meshes.new("P")
verts=[(-5,-5,0),(5,-5,0),(5,5,0),(-5,5,0)]
mesh.from_pydata(verts, [], [(0,1,2,3)]); mesh.update()
plane = bpy.data.objects.new("Plane", mesh); sc.collection.objects.link(plane)

mat = bpy.data.materials.new("M"); mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes): nt.nodes.remove(n)
emit = nt.nodes.new("ShaderNodeEmission")
outn = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(emit.outputs[0], outn.inputs[0])
emit.inputs[1].default_value = 1.0
plane.data.materials.append(mat)

print("engine:", sc.render.engine)
try:
    sc.render.engine = 'CYCLES'
    print("  CYCLES available -> reverting to EEVEE for matrix")
    sc.render.engine = 'BLENDER_EEVEE'
except Exception as e:
    print("  CYCLES set FAILED:", e)

def shot(vt, look, colour, tag):
    sc.view_settings.view_transform = vt
    sc.view_settings.look = look
    emit.inputs[0].default_value = (*colour, 1.0)
    path = os.path.join(OUT, f"sw_{tag}.png")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path

results = []
for vt in ['AgX','Standard','Filmic','Khronos PBR Neutral','ACES 2.0','Raw']:
    safe = vt.replace(' ','_').replace('.','')
    results.append(shot(vt,'None', lin,   f"{safe}_LINfeed"))
results.append(shot('Standard','None', srgb, "Standard_NAIVEfeed"))
results.append(shot('AgX','AgX - Punchy', lin, "AgX_Punchy_LINfeed"))
print("\nWROTE:")
for r in results: print("  ", r)
