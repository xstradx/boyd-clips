import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
ims = sc.render.image_settings

print("=== media_type is STICKY: switching back to stills after a video render ===")
ims.media_type = 'VIDEO'
ims.file_format = 'FFMPEG'
print("   now media_type=%s file_format=%s" % (ims.media_type, ims.file_format))
try:
    ims.file_format = 'PNG'
    print("   set file_format='PNG' directly -> OK")
except TypeError as e:
    print("   set file_format='PNG' directly -> TypeError: %s" % str(e)[:120])
ims.media_type = 'IMAGE'
ims.file_format = 'PNG'
print("   after media_type='IMAGE' first -> file_format=%s  OK" % ims.file_format)

print()
print("=== write_still: does render() save without it? ===")
cd = bpy.data.cameras.new("C")
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x = sc.render.resolution_y = 32
p = os.path.join(OUT, "nowrite_test.png")
if os.path.exists(p):
    os.remove(p)
sc.render.filepath = p
bpy.ops.render.render()
print("   after render() with NO write_still -> file exists:", os.path.exists(p))
bpy.ops.render.render(write_still=True)
print("   after render(write_still=True)     -> file exists:", os.path.exists(p))

print()
print("=== text alignment defaults (5.0) ===")
cu = bpy.data.curves.new("t", type='FONT')
print("   align_x default =", cu.align_x, "  align_y default =", cu.align_y)
for a in ('align_x', 'align_y'):
    try:
        setattr(cu, a, '@@@x@@@')
    except TypeError as e:
        print("   %s enum: %s" % (a, str(e).split("not found in")[-1].strip()))

print()
print("=== render.filepath handling ===")
for fp in (r"C:\tmp\out", r"C:\tmp\out_", r"C:\tmp\out####", r"C:\tmp\out.png", r"C:\tmp\shots\\"):
    sc.render.filepath = fp
    print("   set %-20s -> frame_path(1) = %s" % (repr(fp), sc.render.frame_path(frame=1)))

print()
print("=== does a render loop leak Images? (batch pipelines) ===")
sc.render.filepath = os.path.join(OUT, "leak")
n0 = len(bpy.data.images)
for i in range(5):
    bpy.ops.render.render(write_still=True)
print("   bpy.data.images before=%d after 5 renders=%d -> %s"
      % (n0, len(bpy.data.images), [i.name for i in bpy.data.images]))

print()
print("=== relative paths with an UNSAVED .blend ===")
print("   bpy.data.filepath =", repr(bpy.data.filepath))
sc.render.filepath = "//renders/out.png"
print("   filepath '//renders/out.png' -> frame_path:", sc.render.frame_path(frame=1))
print("   bpy.path.abspath('//x.png') :", bpy.path.abspath('//x.png'))
