
# CRITIC TEST 4: the DELIVERABLE, checked from outside Blender.
#  (a) Does image_settings.color_management='OVERRIDE' actually apply to FFMPEG
#      video, or only to stills?  (silent brand-colour drift if not)
#  (b) Is ProRes 4444's alpha actually POPULATED, or just an all-opaque plane?
#      Agent1 only checked ffprobe pix_fmt = "container has alpha", not content.
#  (c) Straight vs premultiplied alpha in the video containers.
import bpy, os, subprocess, numpy as np

FF  = r"C:\ffmpeg\ffmpeg.exe"
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic\vid"
os.makedirs(OUT, exist_ok=True)
W, H = 320, 180
RED = (0xD4, 0x2B, 0x2B)

def s2l(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.film_transparent = True
sc.frame_start, sc.frame_end = 1, 3
sc.render.fps = 30
sc.render.dither_intensity = 0.0
sc.view_settings.view_transform = 'AgX'          # leave scene WRONG on purpose

cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 2.0
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, 0, 5)

def emis_plane(x, colour, fac=None):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(x, 0, 0))
    p = bpy.context.object
    m = bpy.data.materials.new("m%s" % x); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs['Color'].default_value = (*colour, 1.0); em.inputs['Strength'].default_value = 1.0
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    if fac is None:
        nt.links.new(em.outputs['Emission'], o.inputs['Surface'])
    else:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs['Fac'].default_value = fac
        nt.links.new(tr.outputs['BSDF'], mx.inputs[1]); nt.links.new(em.outputs['Emission'], mx.inputs[2])
        nt.links.new(mx.outputs['Shader'], o.inputs['Surface'])
    m.surface_render_method = 'BLENDED'
    p.data.materials.append(m)
    return p

emis_plane(-0.5, (1, 1, 1), fac=0.5)                                  # left: 50% alpha white
emis_plane(0.5, tuple(s2l(c) for c in RED))                           # right: opaque brand red

ims = sc.render.image_settings
ims.color_management = 'OVERRIDE'
ims.view_settings.view_transform = 'Standard'
print("scene view_transform =", sc.view_settings.view_transform,
      "| image_settings override =", ims.color_management, ims.view_settings.view_transform)

jobs = [
    ("png",      dict(media='IMAGE', fmt='PNG')),
    ("qtrle",    dict(media='VIDEO', container='QUICKTIME', codec='QTRLE')),
    ("prores44", dict(media='VIDEO', container='QUICKTIME', codec='PRORES', profile='4444')),
]
written = {}
for tag, j in jobs:
    if j['media'] == 'IMAGE':
        ims.media_type = 'IMAGE'; ims.file_format = 'PNG'; ims.color_mode = 'RGBA'
    else:
        ims.media_type = 'VIDEO'; ims.file_format = 'FFMPEG'
        ff = sc.render.ffmpeg
        ff.format = j['container']; ff.codec = j['codec']
        if 'profile' in j: ff.ffmpeg_prores_profile = j['profile']
        ims.color_mode = 'RGBA'
        print(f"  {tag}: format={ff.format} codec={ff.codec} color_mode={ims.color_mode}")
    sc.render.filepath = os.path.join(OUT, tag + "_")
    bpy.ops.render.render(animation=True)
    if j['media'] == 'IMAGE':
        written[tag] = os.path.join(OUT, "png_0002.png")
    else:
        cand = [f for f in os.listdir(OUT) if f.startswith(tag + "_") and not f.endswith(".png")]
        written[tag] = os.path.join(OUT, sorted(cand)[-1])
    print("   ->", os.path.basename(written[tag]), os.path.getsize(written[tag]), "bytes")

print("\n########## EXTERNAL (ffmpeg) DECODE — no Blender in the loop ##########")
for tag, path in written.items():
    raw = os.path.join(OUT, tag + ".raw")
    cmd = [FF, "-y", "-v", "error", "-i", path]
    if tag != "png":
        cmd += ["-vf", "select=eq(n\\,1)", "-vsync", "0", "-vframes", "1"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgba", raw]
    subprocess.run(cmd, check=True)
    a = np.fromfile(raw, dtype=np.uint8)
    a = a[:W*H*4].reshape(H, W, 4)
    left  = a[H//2, W//4]      # 50%-alpha white region
    right = a[H//2, 3*W//4]    # opaque brand red region
    alpha = a[..., 3]
    print(f"\n--- {tag} ---")
    print(f"  opaque brand-red px  RGB = #{right[0]:02X}{right[1]:02X}{right[2]:02X}  A={right[3]}"
          f"   want #D42B2B  ->  {'EXACT' if tuple(right[:3])==RED else 'DRIFT'}")
    print(f"  50%-alpha white px   RGBA = ({left[0]},{left[1]},{left[2]},{left[3]})"
          f"  -> {'STRAIGHT' if left[0] > 230 else 'PREMULTIPLIED' if abs(int(left[0])-int(left[3])) < 20 else '?'}")
    print(f"  alpha channel: min={alpha.min()} max={alpha.max()} mean={alpha.mean():.1f} "
          f"unique={len(np.unique(alpha))}")
    print(f"  alpha ACTUALLY POPULATED (not all-opaque): {alpha.min() < 250}")

print("\n########## CONTROL: same render WITHOUT the override (scene AgX) ##########")
ims.color_management = 'FOLLOW_SCENE'
ims.media_type = 'VIDEO'; sc.render.ffmpeg.format = 'QUICKTIME'
sc.render.ffmpeg.codec = 'QTRLE'; ims.color_mode = 'RGBA'
sc.render.filepath = os.path.join(OUT, "agx_")
bpy.ops.render.render(animation=True)
cand = sorted([f for f in os.listdir(OUT) if f.startswith("agx_")])[-1]
raw = os.path.join(OUT, "agx.raw")
subprocess.run([FF, "-y", "-v", "error", "-i", os.path.join(OUT, cand),
                "-vf", "select=eq(n\\,1)", "-vsync", "0", "-vframes", "1",
                "-f", "rawvideo", "-pix_fmt", "rgba", raw], check=True)
a = np.fromfile(raw, dtype=np.uint8)[:W*H*4].reshape(H, W, 4)
r = a[H//2, 3*W//4]
print(f"  AgX (default) brand-red delivers #{r[0]:02X}{r[1]:02X}{r[2]:02X} instead of #D42B2B")
print("\nDONE")
