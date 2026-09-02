"""Boyd sting: build from scratch + render, ONE headless blender invocation, no GUI.
Verified against Blender 5.0.1."""
import bpy, os, math, time, glob, shutil

LOGO = r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\logo_transparent.png"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
OUT  = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\e2e"
if os.path.isdir(OUT): shutil.rmtree(OUT)
os.makedirs(OUT, exist_ok=True)

def srgb(h):
    h=h.lstrip('#'); c=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    return tuple([x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in c])+(1.0,)
BG, INK, ACC = srgb("15181D"), srgb("F2EEE3"), srgb("D42B2B")

T0 = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.fps, sc.render.fps_base = 30, 1.0
sc.frame_start, sc.frame_end = 1, 30

sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = BG

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -9.0, 0); cam.rotation_euler = (math.radians(90),0,0); cam.data.lens = 50

lt = bpy.data.lights.new("Key", type='AREA'); lt.energy, lt.size = 1200, 8
lo = bpy.data.objects.new("Key", lt); sc.collection.objects.link(lo)
lo.location = (4,-5,4); lo.rotation_euler = (math.radians(50),0,math.radians(40))

# materials
def emissive(n,c,s):
    m=bpy.data.materials.new(n); m.use_nodes=True; nt=m.node_tree
    for x in list(nt.nodes): nt.nodes.remove(x)
    e=nt.nodes.new("ShaderNodeEmission"); o=nt.nodes.new("ShaderNodeOutputMaterial")
    e.inputs["Color"].default_value=c; e.inputs["Strength"].default_value=s
    nt.links.new(e.outputs["Emission"], o.inputs["Surface"]); return m
def solid(n,c,r=.35,mt=0.):
    m=bpy.data.materials.new(n); m.use_nodes=True; b=m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value=c; b.inputs["Roughness"].default_value=r
    b.inputs["Metallic"].default_value=mt; return m
m_ink, m_acc = solid("Ink", INK), emissive("Acc", ACC, 5.0)

# logo plane (images-as-planes)
d,f = os.path.split(LOGO)
bpy.ops.image.import_as_mesh_planes(directory=d, files=[{"name":f}], shader='EMISSION',
    emit_strength=1.6, use_transparency=True, render_method='BLENDED',
    size_mode='ABSOLUTE', height=1.05, align_axis='+Y')
logo = bpy.context.object; logo.location = (0, 0, 1.05)

# text
tc = bpy.data.curves.new("T", type='FONT'); tob = bpy.data.objects.new("T", tc)
sc.collection.objects.link(tob)
tc.font = bpy.data.fonts.load(FONT); tc.body = "CLIPS"
tc.size, tc.align_x, tc.align_y = 0.9, 'CENTER', 'CENTER'
tc.extrude, tc.bevel_depth, tc.bevel_resolution = 0.06, 0.012, 3
tc.space_character = 1.35
tob.location = (0, 0, -0.35)
# GOTCHA: FONT curves are generated flat in the XY plane (facing +Z).
# Camera looks along +Y, so the text must be stood up 90deg about X or it renders edge-on.
tob.rotation_euler = (math.radians(90), 0, 0)
tc.materials.append(m_ink)

# accent rule
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0,0,-1.15))
bar = bpy.context.object; bar.scale = (2.6, 0.06, 0.014); bar.data.materials.append(m_acc)

# animation: logo drops in, bar wipes out, text rises
for fr, z, sx in ((1, 1.9, 0.0), (14, 1.05, 1.0)):
    sc.frame_set(fr); logo.location.z = z; logo.keyframe_insert("location")
for fr, s in ((8, 0.0), (22, 2.6)):
    sc.frame_set(fr); bar.scale.x = s; bar.keyframe_insert("scale")
for fr, z in ((12, -0.7), (26, -0.35)):
    sc.frame_set(fr); tob.location.z = z; tob.keyframe_insert("location")
sc.frame_set(1)

BUILD = time.perf_counter()-T0
print(f"\n[BUILD] scene constructed in {BUILD:.2f}s | objects={sorted(bpy.data.objects.keys())}")

sc.render.engine = 'BLENDER_EEVEE'
sc.eevee.taa_render_samples = 32

# --- A) transparent PNG sequence (for compositing over footage) ---
sc.render.film_transparent = True
sc.render.image_settings.media_type = 'IMAGE'
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'
sc.render.filepath = os.path.join(OUT, "png", "sting_")
t=time.perf_counter(); bpy.ops.render.render(animation=True); tA=time.perf_counter()-t
pngs = sorted(glob.glob(os.path.join(OUT,"png","*.png")))
print(f"[A] transparent PNG seq: {len(pngs)} frames in {tA:.2f}s")

# --- B) alpha-preserving QuickTime (QTRLE) ---
sc.render.image_settings.media_type = 'VIDEO'
sc.render.image_settings.file_format = 'FFMPEG'
# NOTE: codec MUST be set before color_mode - color_mode's enum is filtered by the active codec
sc.render.ffmpeg.format = 'QUICKTIME'; sc.render.ffmpeg.codec = 'QTRLE'
sc.render.ffmpeg.audio_codec = 'NONE'
sc.render.image_settings.color_mode = 'RGBA'
sc.render.filepath = os.path.join(OUT, "sting_alpha")
t=time.perf_counter(); bpy.ops.render.render(animation=True); tB=time.perf_counter()-t
movs = [x for x in glob.glob(os.path.join(OUT,"sting_alpha*")) if os.path.isfile(x)]
print(f"[B] QTRLE alpha mov: {os.path.basename(movs[0])} {os.path.getsize(movs[0])}b in {tB:.2f}s")

# --- C) opaque H.264 mp4 over brand background ---
sc.render.film_transparent = False
sc.render.ffmpeg.format = 'MPEG4'; sc.render.ffmpeg.codec = 'H264'
sc.render.image_settings.color_mode = 'RGB'
sc.render.ffmpeg.constant_rate_factor = 'HIGH'; sc.render.ffmpeg.ffmpeg_preset = 'GOOD'
sc.render.filepath = os.path.join(OUT, "sting_h264")
t=time.perf_counter(); bpy.ops.render.render(animation=True); tC=time.perf_counter()-t
mp4s = [x for x in glob.glob(os.path.join(OUT,"sting_h264*")) if os.path.isfile(x)]
print(f"[C] H264 mp4: {os.path.basename(mp4s[0])} {os.path.getsize(mp4s[0])}b in {tC:.2f}s")

print(f"\n[TOTAL] {time.perf_counter()-T0:.2f}s wall clock, single headless process, 3 deliverables, 30 frames each")
