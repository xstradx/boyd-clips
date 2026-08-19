
# CRITIC TEST 2: brand-colour fidelity. Agent1 left this as an "unknown" and
# shipped a sting anyway. If the delivered pixels are not #15181D / #D42B2B /
# #F2EEE3 the whole brand deliverable is silently wrong.
import bpy, os, numpy as np
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic"
os.makedirs(OUT, exist_ok=True)

BG, INK, RED = "15181D", "F2EEE3", "D42B2B"

def hex_srgb(h):
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def s2l(c):   # sRGB EOTF -> scene linear
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 64; sc.render.resolution_y = 64
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'
sc.render.dither_intensity = 0.0

print("available view_transform:",
      [e.identifier for e in sc.view_settings.bl_rna.properties['view_transform'].enum_items])
print("available look:", [e.identifier for e in sc.view_settings.bl_rna.properties['look'].enum_items][:6], "...")
print("default view_transform =", sc.view_settings.view_transform, "| look =", sc.view_settings.look,
      "| exposure =", sc.view_settings.exposure, "| gamma =", sc.view_settings.gamma)
print("display_settings.display_device =", sc.display_settings.display_device)
print("sequencer_colorspace =", sc.sequencer_colorspace_settings.name)

# world = flat brand background, nothing else in scene
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
bgn = w.node_tree.nodes['Background']
lin = tuple(s2l(c) for c in hex_srgb(BG))
bgn.inputs['Color'].default_value = (*lin, 1.0)
bgn.inputs['Strength'].default_value = 1.0
print(f"\n#{BG} sRGB {hex_srgb(BG)} -> scene-linear {tuple(round(v,6) for v in lin)}")

cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("Cam", cam_d)
sc.collection.objects.link(cam); sc.camera = cam; cam.location = (0, 0, 5)

def probe(tag):
    p = os.path.join(OUT, f"cm_{tag}.png"); sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(p, check_existing=False)
    a = np.empty(64*64*4, dtype=np.float32); im.pixels.foreach_get(a)
    c = a.reshape(64, 64, 4)[32, 32]
    bpy.data.images.remove(im)
    hx = "".join("%02X" % round(max(0, min(1, v)) * 255) for v in c[:3])
    return hx, c

print("\n%-34s %-8s %-8s %s" % ("view_transform / look", "got", "want", "MATCH"))
for vt in [e.identifier for e in sc.view_settings.bl_rna.properties['view_transform'].enum_items]:
    try:
        sc.view_settings.view_transform = vt
    except Exception as e:
        print("  skip", vt, e); continue
    try:
        sc.view_settings.look = 'None'
    except Exception:
        pass
    hx, c = probe(vt.replace(" ", "_"))
    print("%-34s #%-7s #%-7s %s" % (vt, hx, BG, "EXACT" if hx == BG else ""))

# the fix candidate, plus per-output override introduced for image_settings
print("\n--- does image_settings carry its own colour management override? ---")
ims = sc.render.image_settings
print("  has .color_management:", hasattr(ims, 'color_management'),
      "->", getattr(ims, 'color_management', None))
if hasattr(ims, 'color_management'):
    print("  enum:", [e.identifier for e in ims.bl_rna.properties['color_management'].enum_items])
    sc.view_settings.view_transform = 'AgX'       # deliberately wrong globally
    ims.color_management = 'OVERRIDE'
    ims.view_settings.view_transform = 'Standard'
    hx, c = probe("override")
    print(f"  scene=AgX but image_settings OVERRIDE->Standard  => #{hx}  (want #{BG})  {'EXACT' if hx==BG else 'MISMATCH'}")
    ims.color_management = 'FOLLOW_SCENE'

# and prove the same for the two ink colours through an emission surface
print("\n--- emissive brand swatches through Standard ---")
sc.view_settings.view_transform = 'Standard'
bgn.inputs['Strength'].default_value = 0.0
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
pl = bpy.context.object
pl.rotation_euler = (0, 0, 0)
for name, hx_want in (("INK", INK), ("RED", RED)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs['Color'].default_value = (*[s2l(c) for c in hex_srgb(hx_want)], 1.0)
    em.inputs['Strength'].default_value = 1.0
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs['Emission'], o.inputs['Surface'])
    pl.data.materials.clear(); pl.data.materials.append(m)
    got, c = probe("emis_" + name)
    print(f"  {name} emission -> #{got}  want #{hx_want}  {'EXACT' if got == hx_want else 'MISMATCH'}")
print("\nDONE")
