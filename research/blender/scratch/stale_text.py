import bpy, os
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
def s2l(c): return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
def hx(h): return tuple(s2l(int(h[i:i+2],16)/255.) for i in (0,2,4))

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 480, 270
    sc.render.image_settings.file_format='PNG'
    sc.view_settings.view_transform='Standard'; sc.render.dither_intensity=0.0
    sc.render.film_transparent = False
    w=bpy.data.worlds.new("W"); sc.world=w; w.use_nodes=True
    bg=w.node_tree.nodes["Background"]; bg.inputs[0].default_value=(*hx("15181D"),1); bg.inputs[1].default_value=1.0
    cd=bpy.data.cameras.new("C"); cd.type='ORTHO'; cd.ortho_scale=8.0
    cam=bpy.data.objects.new("Cam",cd); sc.collection.objects.link(cam); cam.location=(0,0,10); sc.camera=cam
    return sc

def make_text(sc, body):
    cu = bpy.data.curves.new("T", type='FONT')
    cu.body = body
    cu.font = bpy.data.fonts.load(FONT)
    cu.size = 1.0
    ob = bpy.data.objects.new("Txt", cu); sc.collection.objects.link(ob)
    m = bpy.data.materials.new("Mi"); m.use_nodes=True
    nt=m.node_tree
    for n in list(nt.nodes): nt.nodes.remove(n)
    e=nt.nodes.new("ShaderNodeEmission"); o=nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0],o.inputs[0]); e.inputs[0].default_value=(*hx("F2EEE3"),1)
    ob.data.materials.append(m)
    return ob

BODY = "BOYD CLIPS"

# ---------- NAIVE: read dimensions immediately, centre the text ----------
sc = build(); ob = make_text(sc, BODY)
d_naive = tuple(round(v,4) for v in ob.dimensions)
ob.location.x = -ob.dimensions.x/2.0
loc_naive = round(ob.location.x,4)
sc.render.filepath = os.path.join(OUT,"stale_text_NAIVE.png")
bpy.ops.render.render(write_still=True)

# ---------- CORRECT: flush depsgraph first ----------
sc = build(); ob = make_text(sc, BODY)
bpy.context.view_layer.update()               # <-- the missing line
d_ok = tuple(round(v,4) for v in ob.dimensions)
ob.location.x = -ob.dimensions.x/2.0
loc_ok = round(ob.location.x,4)
sc.render.filepath = os.path.join(OUT,"stale_text_CORRECT.png")
bpy.ops.render.render(write_still=True)

print("NAIVE   ob.dimensions right after creation :", d_naive, " -> centred at x =", loc_naive)
print("CORRECT after view_layer.update()          :", d_ok,    " -> centred at x =", loc_ok)
print("dimension error:", round(d_ok[0]-d_naive[0],4), "blender units")
