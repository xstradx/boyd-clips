
# CRITIC TEST 1: does EEVEE BLENDED actually write correct ALPHA to a
# film_transparent render?  Agent1's whole alpha deliverable depends on it.
# Method: ortho camera framing the logo plane EXACTLY, render at the logo's
# native 1413x540, so rendered pixel (i,j) == source PNG texel (i,j).
# Then compare rendered alpha to SOURCE alpha per-pixel.
import bpy, os, sys, numpy as np, hashlib

LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"
OUT  = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

src = bpy.data.images.load(LOGO)
W, H = src.size
print("SOURCE", W, H, "channels", src.channels, "alpha_mode", src.alpha_mode, "cs", src.colorspace_settings.name)
sp = np.empty(W*H*4, dtype=np.float32); src.pixels.foreach_get(sp); sp = sp.reshape(H, W, 4)
src_a = sp[..., 3].copy()
print("SOURCE alpha: min %.4f max %.4f  frac<0.01 %.4f  frac>0.99 %.4f"
      % (src_a.min(), src_a.max(), (src_a < .01).mean(), (src_a > .99).mean()))

sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = W; sc.render.resolution_y = H; sc.render.resolution_percentage = 100
sc.render.film_transparent = True
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'
sc.render.image_settings.color_depth = '16'
sc.render.dither_intensity = 0.0            # dither would perturb the diff
sc.render.filter_size = 0.0                 # no reconstruction filter -> 1:1 texel mapping

aspect = W / H
cam_d = bpy.data.cameras.new("C"); cam_d.type = 'ORTHO'; cam_d.ortho_scale = 2.0 * aspect
cam = bpy.data.objects.new("Cam", cam_d); sc.collection.objects.link(cam)
cam.location = (0, 0, 5); cam.rotation_euler = (0, 0, 0)
sc.camera = cam

bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0))
plane = bpy.context.object
plane.scale = (aspect, 1.0, 1.0)


def build_mat(name, mode, kind):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = src
    tex.interpolation = 'Closest'; tex.extension = 'CLIP'
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if kind == 'EMIS_MIX':                       # agent1 06_build.py manual plane
        em = nt.nodes.new("ShaderNodeEmission"); em.inputs['Strength'].default_value = 1.0
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tex.outputs['Color'], em.inputs['Color'])
        nt.links.new(tex.outputs['Alpha'], mx.inputs['Fac'])
        nt.links.new(tr.outputs['BSDF'], mx.inputs[1])
        nt.links.new(em.outputs['Emission'], mx.inputs[2])
        nt.links.new(mx.outputs['Shader'], out.inputs['Surface'])
    else:                                        # import_as_mesh_planes EMISSION style
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs['Base Color'].default_value = (0, 0, 0, 1)
        b.inputs['Emission Strength'].default_value = 1.0
        nt.links.new(tex.outputs['Color'], b.inputs['Emission Color'])
        nt.links.new(tex.outputs['Alpha'], b.inputs['Alpha'])
        nt.links.new(b.outputs['BSDF'], out.inputs['Surface'])
    m.surface_render_method = mode
    return m


def render_read(tag):
    p = os.path.join(OUT, tag + ".png"); sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(p, check_existing=False)
    a = np.empty(im.size[0]*im.size[1]*4, dtype=np.float32)
    im.pixels.foreach_get(a); a = a.reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    return p, a


results = {}
for kind in ('EMIS_MIX', 'PRINCIPLED'):
    for mode in ('BLENDED', 'DITHERED'):
        tag = f"{kind}_{mode}"
        plane.data.materials.clear()
        plane.data.materials.append(build_mat(tag, mode, kind))
        p, img = render_read(tag)
        ra = img[..., 3]
        err = np.abs(ra - src_a)
        # the money question: in regions where the SOURCE is fully transparent,
        # what did EEVEE write to alpha?
        holes = src_a < 0.01
        solid = src_a > 0.99
        print(f"\n--- {tag} ---")
        print(f"  rendered alpha  min {ra.min():.4f}  max {ra.max():.4f}  mean {ra.mean():.4f}")
        print(f"  SOURCE-transparent px ({holes.sum()}): rendered alpha mean {ra[holes].mean():.4f}  max {ra[holes].max():.4f}")
        print(f"  SOURCE-opaque      px ({solid.sum()}): rendered alpha mean {ra[solid].mean():.4f}  min {ra[solid].min():.4f}")
        print(f"  mean|alpha err| vs source = {err.mean():.5f}   max {err.max():.5f}")
        print(f"  VERDICT alpha passthrough: {'OK' if err.mean() < 0.02 else 'BROKEN'}")
        results[tag] = err.mean()

# ---- determinism control: agent1 concluded 'compositor IS affecting output'
# from 31715 differing px vs a hand-picked >1000 threshold, with NO null control.
print("\n########## DETERMINISM CONTROL (same scene rendered twice) ##########")
p1, i1 = render_read("det_a")
p2, i2 = render_read("det_b")
d = np.abs(i1 - i2)
npx = (np.max(d[..., :3], axis=2) > 0.01).sum()
print(f"  identical-config re-render: differing px (>0.01) = {npx}  max|d| = {d.max():.6f}")
print(f"  sha256 a={hashlib.sha256(open(p1,'rb').read()).hexdigest()[:16]} b={hashlib.sha256(open(p2,'rb').read()).hexdigest()[:16]}")
print(f"  -> EEVEE deterministic: {npx == 0}")

# ---- premultiplied vs straight alpha (agent1 asserted 'correct straight alpha'
# from a white-on-black matte, which cannot distinguish the two)
print("\n########## PREMULTIPLIED vs STRAIGHT ##########")
sc.render.resolution_x = 64; sc.render.resolution_y = 64
m = bpy.data.materials.new("Half"); m.use_nodes = True
nt = m.node_tree; nt.nodes.clear()
em = nt.nodes.new("ShaderNodeEmission"); em.inputs['Color'].default_value = (1, 1, 1, 1); em.inputs['Strength'].default_value = 1.0
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs['Fac'].default_value = 0.5
o = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tr.outputs['BSDF'], mx.inputs[1]); nt.links.new(em.outputs['Emission'], mx.inputs[2])
nt.links.new(mx.outputs['Shader'], o.inputs['Surface'])
m.surface_render_method = 'BLENDED'
plane.data.materials.clear(); plane.data.materials.append(m)
sc.view_settings.view_transform = 'Standard'      # so 1.0 emission stays 1.0
p, img = render_read("premul")
c = img[32, 32]
print(f"  50%% white emission over transparent film -> RGBA = ({c[0]:.4f},{c[1]:.4f},{c[2]:.4f},{c[3]:.4f})")
print(f"  RGB~=1.0 => STRAIGHT/unassociated ; RGB~=alpha => PREMULTIPLIED/associated")
print(f"  -> PNG on disk is: {'STRAIGHT' if c[0] > 0.9 else ('PREMULTIPLIED' if abs(c[0]-c[3]) < 0.06 else 'NEITHER/odd')}")
print("\nDONE")
