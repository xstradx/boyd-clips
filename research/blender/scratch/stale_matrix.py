import bpy, os
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
def s2l(c): return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
def hx(h): return tuple(s2l(int(h[i:i+2],16)/255.) for i in (0,2,4))

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc=bpy.context.scene
    sc.render.resolution_x,sc.render.resolution_y=640,360
    sc.render.image_settings.file_format='PNG'
    sc.view_settings.view_transform='Standard'; sc.render.dither_intensity=0.0
    w=bpy.data.worlds.new("W");sc.world=w;w.use_nodes=True
    b=w.node_tree.nodes["Background"];b.inputs[0].default_value=(*hx("15181D"),1);b.inputs[1].default_value=1.0
    cd=bpy.data.cameras.new("C");cd.type='ORTHO';cd.ortho_scale=8.0
    c=bpy.data.objects.new("Cam",cd);sc.collection.objects.link(c);c.location=(0,0,10);sc.camera=c
    return sc
def emat(h):
    m=bpy.data.materials.new("m");m.use_nodes=True;nt=m.node_tree
    for n in list(nt.nodes):nt.nodes.remove(n)
    e=nt.nodes.new("ShaderNodeEmission");o=nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0],o.inputs[0]);e.inputs[0].default_value=(*hx(h),1);return m
def quad(sc,name,sz,mat):
    me=bpy.data.meshes.new(name)
    me.from_pydata([(-sz,-sz,0),(sz,-sz,0),(sz,sz,0),(-sz,sz,0)],[],[(0,1,2,3)]);me.update()
    o=bpy.data.objects.new(name,me);sc.collection.objects.link(o);o.data.materials.append(mat);return o

print("=== F. child.matrix_world after moving the PARENT ===")
for label, flush in (("NAIVE",False),("CORRECT",True)):
    sc=build()
    parent=bpy.data.objects.new("Rig",None); sc.collection.objects.link(parent)
    card=quad(sc,"Card",1.0,emat("F2EEE3")); card.parent=parent
    bpy.context.view_layer.update()                    # baseline eval, parent at origin
    parent.location=(2.5,1.0,0)                        # move the rig
    if flush: bpy.context.view_layer.update()
    mw = card.matrix_world.translation
    print(f"  {label:8} card.matrix_world.translation = {tuple(round(v,3) for v in mw)}")
    badge=quad(sc,"Badge",0.35,emat("D42B2B"))
    badge.location=(mw.x, mw.y-1.5, 0.1)               # script places badge under the card
    sc.render.filepath=os.path.join(OUT,f"stale_parent_{label}.png")
    bpy.ops.render.render(write_still=True)

print()
print("=== G. dimensions AFTER mutating an already-evaluated text object ===")
sc=build()
cu=bpy.data.curves.new("T",type='FONT'); cu.font=bpy.data.fonts.load(FONT)
cu.body="HI"; ob=bpy.data.objects.new("T",cu); sc.collection.objects.link(ob)
bpy.context.view_layer.update()
print("  body='HI'  dimensions =", tuple(round(v,4) for v in ob.dimensions))
cu.body="BOYD CLIPS EPISODE 12"
print("  body=long  dimensions =", tuple(round(v,4) for v in ob.dimensions), " <- STALE?")
bpy.context.view_layer.update()
print("  after update()        =", tuple(round(v,4) for v in ob.dimensions))
cu.size = 3.0
print("  size=3.0  dimensions  =", tuple(round(v,4) for v in ob.dimensions), " <- STALE?")
bpy.context.view_layer.update()
print("  after update()        =", tuple(round(v,4) for v in ob.dimensions))
