import bpy, os, time

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"

print("=== 1. CYCLES device in background: what does it actually use? ===")
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
print("   scene.cycles.device                 =", sc.cycles.device)
prefs = bpy.context.preferences.addons.get('cycles')
if prefs:
    cp = prefs.preferences
    print("   prefs.compute_device_type           =", repr(cp.compute_device_type))
    try:
        cp.get_devices()
    except Exception as e:
        print("   get_devices() ->", e)
    for d in cp.devices:
        print("      device: %-40s type=%-8s use=%s" % (d.name[:40], d.type, d.use))
else:
    print("   cycles addon NOT registered")
print("   -> scene.cycles.device='GPU' alone does NOT enable GPU; compute_device_type must be set")

print()
print("=== 2. --factory-startup and add-ons ===")
import addon_utils
enabled = [m.__name__ for m in addon_utils.modules() if addon_utils.check(m.__name__)[1]]
print("   enabled add-ons in this session (%d):" % len(enabled))
print("     ", enabled[:14])
for probe in ('io_scene_gltf2', 'io_scene_fbx', 'cycles'):
    print("   %-18s enabled=%s" % (probe, addon_utils.check(probe)[1]))

print()
print("=== 3. FFMPEG video output in background ===")
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = sc.render.resolution_y = 64
sc.frame_start, sc.frame_end = 1, 6
sc.render.image_settings.media_type = 'VIDEO'
sc.render.image_settings.file_format = 'FFMPEG'
sc.render.ffmpeg.format = 'MPEG4'
sc.render.ffmpeg.codec = 'H264'
sc.render.ffmpeg.constant_rate_factor = 'HIGH'
cd = bpy.data.cameras.new("C")
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.filepath = os.path.join(OUT, "vid_test_")
try:
    bpy.ops.render.render(animation=True)
    made = [f for f in os.listdir(OUT) if f.startswith("vid_test_")]
    print("   FFMPEG render OK. files:", made)
    for f in made:
        print("      %s  %d bytes" % (f, os.path.getsize(os.path.join(OUT, f))))
except Exception as e:
    print("   FFMPEG FAILED:", type(e).__name__, str(e)[:150])

print()
print("=== 4. write_still vs animation: does render() without write_still save anything? ===")
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = os.path.join(OUT, "nowrite_test.png")
if os.path.exists(sc.render.filepath):
    os.remove(sc.render.filepath)
bpy.ops.render.render()          # NOTE: no write_still
print("   after bpy.ops.render.render() with NO write_still, file exists:",
      os.path.exists(os.path.join(OUT, "nowrite_test.png")))

print()
print("=== 5. text object alignment props (5.0) ===")
cu = bpy.data.curves.new("t", type='FONT')
print("   align_x default:", cu.align_x, " align_y default:", cu.align_y)
try:
    cu.align_x = '@@@x@@@'
except TypeError as e:
    print("   align_x enum:", str(e).split("not found in")[-1].strip())
try:
    cu.align_y = '@@@x@@@'
except TypeError as e:
    print("   align_y enum:", str(e).split("not found in")[-1].strip())

print()
print("=== 6. render filepath: '#' frame padding and trailing separators ===")
for fp in (r"C:\tmp\out", r"C:\tmp\out_", r"C:\tmp\out####", r"C:\tmp\out.png"):
    sc.render.filepath = fp
    print("   set %-22r -> readback %r  frame_path(1)=%r" % (fp, sc.render.filepath, sc.render.frame_path(frame=1)))
