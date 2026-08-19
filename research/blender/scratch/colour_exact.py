import bpy, os
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
BRAND = {"bg":"15181D", "ink":"F2EEE3", "red":"D42B2B"}
def s2l(c): return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def hex2lin(h): return tuple(s2l(int(h[i:i+2],16)/255.0) for i in (0,2,4))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = 64
sc.render.film_transparent = False
sc.render.image_settings.file_format='PNG'; sc.render.image_settings.color_depth='8'
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.0
cd = bpy.data.cameras.new("C"); cd.type='ORTHO'; cd.ortho_scale=2.0
cam = bpy.data.objects.new("Cam",cd); sc.collection.objects.link(cam); cam.location=(0,0,5); sc.camera=cam
me = bpy.data.meshes.new("P"); me.from_pydata([(-5,-5,0),(5,-5,0),(5,5,0),(-5,5,0)],[],[(0,1,2,3)]); me.update()
ob = bpy.data.objects.new("Pl",me); sc.collection.objects.link(ob)
mat = bpy.data.materials.new("M"); mat.use_nodes=True; nt=mat.node_tree
for n in list(nt.nodes): nt.nodes.remove(n)
em = nt.nodes.new("ShaderNodeEmission"); on = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(em.outputs[0], on.inputs[0]); em.inputs[1].default_value=1.0
ob.data.materials.append(mat)

# ---- THE RECIPE ----
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
sc.view_settings.exposure = 0.0
sc.view_settings.gamma = 1.0
sc.render.dither_intensity = 0.0          # <-- the one everybody forgets

for name, hx in BRAND.items():
    em.inputs[0].default_value = (*hex2lin(hx), 1.0)
    sc.render.filepath = os.path.join(OUT, f"exact_{name}_{hx}.png")
    bpy.ops.render.render(write_still=True)

# control: same but dither left at default
sc.render.dither_intensity = 1.0
em.inputs[0].default_value = (*hex2lin(BRAND["red"]),1.0)
sc.render.filepath = os.path.join(OUT, "ctrl_red_dither1.png")
bpy.ops.render.render(write_still=True)
