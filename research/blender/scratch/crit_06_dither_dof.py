
# CRITIC TEST 6
#  (a) I proved "#15181D delivers EXACTLY" with dither_intensity forced to 0.
#      Blender's DEFAULT is 1.0. Does the flat brand background survive at the
#      default? If not, "exact brand hex" is only true because I disabled a
#      setting nobody mentioned.
#  (b) EEVEE DOF/motion blur are STOCHASTIC in EEVEE Next. Agent2 proved DOF
#      "works" at whatever sample count was default. Does it silently degrade
#      into noise at low taa_render_samples -- the classic "it rendered so it's
#      fine" trap?
import bpy, os, numpy as np

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic"
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'
sc.view_settings.view_transform = 'Standard'

def s2l(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def read(p):
    im = bpy.data.images.load(p, check_existing=False)
    a = np.empty(im.size[0]*im.size[1]*4, dtype=np.float32); im.pixels.foreach_get(a)
    a = a.reshape(im.size[1], im.size[0], 4)[..., :3].copy()
    bpy.data.images.remove(im)
    return a

print("########## (a) DITHER vs flat brand background ##########")
print("  default render.dither_intensity =", sc.render.dither_intensity)
sc.render.resolution_x, sc.render.resolution_y = 200, 200
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (*[s2l(c) for c in (0x15, 0x18, 0x1D)], 1)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("C")); sc.collection.objects.link(cam)
sc.camera = cam; cam.location = (0, 0, 5)

for depth in ('8', '16'):
    sc.render.image_settings.color_depth = depth
    for dith in (1.0, 0.0):
        sc.render.dither_intensity = dith
        sc.render.filepath = os.path.join(OUT, f"dith_{depth}_{dith}.png")
        bpy.ops.render.render(write_still=True)
        a = read(sc.render.filepath)
        q = np.round(a * 255).astype(int)
        uniq = {c: len(np.unique(q[..., c])) for c in range(3)}
        hexes = sorted({"%02X%02X%02X" % tuple(px) for px in q.reshape(-1, 3)[::37]})
        print(f"  depth={depth} dither={dith}: distinct 8-bit values per channel={uniq} "
              f"| distinct hexes(sampled)={len(hexes)} | e.g. {hexes[:4]}")
        print(f"      all-pixels-exactly-#15181D: {bool((q == [0x15,0x18,0x1D]).all())}")

print("\n########## (b) EEVEE DOF vs taa_render_samples ##########")
ee = sc.eevee
print("  has taa_render_samples:", hasattr(ee, 'taa_render_samples'),
      "default =", getattr(ee, 'taa_render_samples', None))
print("  eevee props matching 'jitter|sampl':",
      [p.identifier for p in ee.bl_rna.properties if any(k in p.identifier for k in ('jitter', 'sampl'))])

sc.render.resolution_x, sc.render.resolution_y = 240, 160
sc.render.dither_intensity = 0.0
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.02, 0.02, 0.025, 1)
# bright small emitters at several depths -> DOF turns each into a bokeh disc
for i, z in enumerate((-1.0, -4.0, -9.0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(-1.2 + 1.2*i, 0, z))
    ob = bpy.context.object
    m = bpy.data.materials.new("e%d" % i); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs['Strength'].default_value = 12.0
    em.inputs['Color'].default_value = (1, .9, .8, 1)
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs['Emission'], o.inputs['Surface'])
    ob.data.materials.append(m)
cam.location = (0, 0, 2.0); cam.rotation_euler = (0, 0, 0)
cd = cam.data
cd.dof.use_dof = True
cd.dof.focus_distance = 3.0          # focus on the NEAR sphere
cd.dof.aperture_fstop = 0.4
cd.lens = 50

shots = {}
for n in (1, 4, 16, 64, 256):
    ee.taa_render_samples = n
    sc.render.filepath = os.path.join(OUT, "dof_%03d.png" % n)
    bpy.ops.render.render(write_still=True)
    shots[n] = read(sc.render.filepath)
gt = shots[256]
print("\n  %-6s %-12s %-12s %s" % ("samples", "mean|d| vs 256", "max|d|", "verdict"))
for n in (1, 4, 16, 64):
    d = np.abs(shots[n] - gt)
    print("  %-6d %-12.5f %-12.4f %s" % (n, d.mean(), d.max(),
          "converged" if d.mean() < 0.002 else "NOISY / not converged"))

# DOF on vs off at the converged setting, measured on the FAR sphere region
ee.taa_render_samples = 256
cd.dof.use_dof = False
sc.render.filepath = os.path.join(OUT, "dof_off.png"); bpy.ops.render.render(write_still=True)
off = read(sc.render.filepath)
d = np.abs(gt - off)
print("\n  DOF on vs off at 256 spp: mean|d|=%.5f max=%.4f -> DOF is applying: %s"
      % (d.mean(), d.max(), d.mean() > 1e-3))
def sharp(a, x0, x1):
    reg = a[:, x0:x1, 0]
    return float(np.abs(np.diff(reg, axis=1)).mean())
print("  horizontal-gradient sharpness (higher=sharper):")
print("    near sphere (in focus)  dof_off=%.5f  dof_on=%.5f" % (sharp(off, 10, 80), sharp(gt, 10, 80)))
print("    far  sphere (defocused) dof_off=%.5f  dof_on=%.5f" % (sharp(off, 160, 230), sharp(gt, 160, 230)))
print("\nDONE")
