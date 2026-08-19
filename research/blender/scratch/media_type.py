import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc = bpy.context.scene
ims = sc.render.image_settings

print("=== ImageFormatSettings properties in 5.0 ===")
print([p.identifier for p in ims.bl_rna.properties if not p.is_readonly][:40])
print()
print("media_type present:", hasattr(ims, 'media_type'))
if hasattr(ims, 'media_type'):
    print("media_type default:", ims.media_type)
    try:
        ims.media_type = '@@@x@@@'
    except TypeError as e:
        print("media_type enum:", str(e).split("not found in")[-1].strip())
    for mt in ('IMAGE', 'MULTI_LAYER_IMAGE', 'VIDEO'):
        try:
            ims.media_type = mt
            try:
                ims.file_format = '@@@x@@@'
            except TypeError as e:
                print("  media_type=%-20s file_format enum -> %s" % (mt, str(e).split("not found in")[-1].strip()))
        except TypeError:
            print("  media_type=%s invalid" % mt)

print()
print("=== THE 5.0 WAY to render an mp4 ===")
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = sc.render.resolution_y = 64
sc.frame_start, sc.frame_end = 1, 6
sc.render.image_settings.media_type = 'VIDEO'          # <-- new in 5.0, required first
sc.render.image_settings.file_format = 'FFMPEG'
sc.render.ffmpeg.format = 'MPEG4'
sc.render.ffmpeg.codec = 'H264'
cd = bpy.data.cameras.new("C")
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.filepath = os.path.join(OUT, "vid_test")
try:
    bpy.ops.render.render(animation=True)
    for f in sorted(os.listdir(OUT)):
        if f.startswith("vid_test"):
            print("   WROTE %s  %d bytes" % (f, os.path.getsize(os.path.join(OUT, f))))
except Exception as e:
    print("   FAILED:", type(e).__name__, str(e)[:200])
