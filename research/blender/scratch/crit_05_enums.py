
# CRITIC TEST 5
#  (a) How WIDESPREAD is the "enum_items lies" pattern?  Both agents framed it as
#      a render-engine quirk. If it is systemic, every capability-detection
#      routine an AI writes is unreliable.
#  (b) Agent2: "No way found to programmatically enumerate legal MENU socket
#      values ... There may be a proper API that I did not find." Look properly.
#  (c) Does assigning a MENU socket actually CHANGE THE RENDER, or is 'Bloom'
#      merely the default so the assignment could be a silent no-op?
import bpy, os, numpy as np

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic"
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

print("########## (a) enum_items vs the set actually accepted ##########")
def real_set(owner, prop):
    try:
        setattr(owner, prop, "@@junk@@")
    except TypeError as e:
        s = str(e)
        if "not found in (" in s:
            return s.split("not found in (", 1)[1].rstrip(")").replace("'", "").split(", ")
    except Exception as e:
        return ["<%s>" % type(e).__name__]
    return None

img = bpy.data.images.new("probe", 4, 4)
targets = [
    ("scene.render.engine",                    sc.render, "engine"),
    ("scene.view_settings.view_transform",     sc.view_settings, "view_transform"),
    ("scene.view_settings.look",               sc.view_settings, "look"),
    ("scene.display_settings.display_device",  sc.display_settings, "display_device"),
    ("image.colorspace_settings.name",         img.colorspace_settings, "name"),
    ("sequencer_colorspace_settings.name",     sc.sequencer_colorspace_settings, "name"),
    ("image_settings.file_format",             sc.render.image_settings, "file_format"),
    ("image_settings.media_type",              sc.render.image_settings, "media_type"),
    ("ffmpeg.codec",                           sc.render.ffmpeg, "codec"),
    ("cycles.device",                          getattr(sc, "cycles", None), "device"),
]
print("%-42s %-6s %-6s %s" % ("property", "intro", "real", "verdict"))
for label, owner, prop in targets:
    if owner is None:
        print("%-42s  (absent)" % label); continue
    try:
        intro = [e.identifier for e in owner.bl_rna.properties[prop].enum_items]
    except Exception as e:
        intro = ["<err>"]
    real = real_set(owner, prop)
    if real is None:
        print("%-42s %-6d  ?     (no TypeError raised)" % (label, len(intro))); continue
    ok = set(intro) == set(real)
    print("%-42s %-6d %-6d %s" % (label, len(intro), len(real),
          "match" if ok else "LIES  intro=%s real=%s" % (intro if len(intro) < 5 else intro[:4]+['...'],
                                                          real if len(real) < 12 else real[:10]+['...'])))

print("\n########## (b) MENU socket value discovery ##########")
ng = bpy.data.node_groups.new("G", "CompositorNodeTree")
gl = ng.nodes.new("CompositorNodeGlare")
sock = gl.inputs['Type']
print("socket:", sock.name, "| bl_idname:", sock.bl_idname, "| type:", sock.type)
p = sock.bl_rna.properties['default_value']
print("  prop type:", p.type, "| enum_items:", [e.identifier for e in p.enum_items],
      "| enum_items_static:", [e.identifier for e in p.enum_items_static])
# candidate discovery routes an AI would not try
for route in ("enum_items_static_ui", "enum_items_ui"):
    print("  %-22s ->" % route, [e.identifier for e in getattr(p, route)] if hasattr(p, route) else "(absent)")
print("  socket attrs w/ 'menu'/'enum'/'item':",
      [a for a in dir(sock) if any(k in a.lower() for k in ('menu', 'enum', 'item'))])
# the real answer: the node's own RNA / the socket's default_value as a path
try:
    print("  sock.path_resolve trick:", sock.bl_rna.properties['default_value'].enum_items.keys())
except Exception as e:
    print("  keys() ->", type(e).__name__, e)
# does the ITEMS live on the interface / a NodeTreeInterfaceSocketMenu?
print("  bpy.types has NodeSocketMenu:", hasattr(bpy.types, 'NodeSocketMenu'))
if hasattr(bpy.types, 'NodeSocketMenu'):
    pp = bpy.types.NodeSocketMenu.bl_rna.properties.get('default_value')
    print("  NodeSocketMenu.default_value enum_items:",
          [e.identifier for e in pp.enum_items] if pp else None)
# rna_type route
print("  sock.rna_type.properties['default_value'].enum_items:",
      [e.identifier for e in sock.rna_type.properties['default_value'].enum_items])

print("\n########## (c) does setting a MENU socket actually change pixels? ##########")
print("  DEFAULT Type value =", repr(sock.default_value))
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 200, 120
sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGB'
sc.view_settings.view_transform = 'Standard'
sc.render.dither_intensity = 0.0
cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 2.0
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, 0, 5)
bpy.ops.mesh.primitive_plane_add(size=0.28, location=(0, 0, 0))
pl = bpy.context.object
m = bpy.data.materials.new("E"); m.use_nodes = True
nt = m.node_tree; nt.nodes.clear()
em = nt.nodes.new("ShaderNodeEmission"); em.inputs['Color'].default_value = (1, .95, .9, 1)
em.inputs['Strength'].default_value = 40.0
o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs['Emission'], o.inputs['Surface'])
pl.data.materials.append(m)

ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
gout = ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
ng.links.new(gl.outputs['Image'], gout.inputs[0])
sc.compositing_node_group = ng
gl.inputs['Strength'].default_value = 1.0
gl.inputs['Threshold'].default_value = 0.5

def shot(tag):
    sc.render.filepath = os.path.join(OUT, "glare_" + tag + ".png")
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath + ".png" if not sc.render.filepath.endswith(".png")
                              else sc.render.filepath, check_existing=False)
    a = np.empty(im.size[0]*im.size[1]*4, dtype=np.float32); im.pixels.foreach_get(a)
    a = a.reshape(im.size[1], im.size[0], 4)[..., :3].copy()
    bpy.data.images.remove(im)
    return a

sc.render.use_compositing = False
base = shot("nocomp")
sc.render.use_compositing = True
imgs = {}
for t in ('Bloom', 'Ghosts', 'Streaks', 'Fog Glow', 'Simple Star', 'Sun Beams'):
    try:
        gl.inputs['Type'].default_value = t
    except Exception as e:
        print("  set %-12s FAILED %s" % (t, e)); continue
    imgs[t] = shot(t.replace(" ", "_"))
    d = np.abs(imgs[t] - base)
    print("  %-12s  read-back=%-12r meanR=%.5f  mean|d| vs no-comp=%.5f  changed=%s"
          % (t, gl.inputs['Type'].default_value, imgs[t][..., 0].mean(), d.mean(), d.mean() > 1e-4))
ks = list(imgs)
print("\n  pairwise mean|d| between glare types (0 => the setting did nothing):")
for i in range(len(ks)):
    for j in range(i+1, len(ks)):
        dd = np.abs(imgs[ks[i]] - imgs[ks[j]]).mean()
        print("    %-12s vs %-12s %.6f %s" % (ks[i], ks[j], dd, "" if dd > 1e-5 else "<-- IDENTICAL"))
print("\nDONE")
