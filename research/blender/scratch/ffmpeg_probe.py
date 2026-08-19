import bpy, os

sc = bpy.context.scene
ims = sc.render.image_settings
print("=== is video output available in this build? ===")
bo = bpy.app.build_options
print("build_options attrs:", [a for a in dir(bo) if not a.startswith('_')])
for k in ('ffmpeg', 'codec_ffmpeg', 'codec_avi', 'audaspace', 'sdl'):
    print("   %-16s = %r" % (k, getattr(bo, k, '<absent>')))
print()
try:
    ims.file_format = '@@@x@@@'
except TypeError as e:
    print("file_format enum:", str(e).split("not found in")[-1].strip())
print()
print("has scene.render.ffmpeg struct :", hasattr(sc.render, 'ffmpeg'))
if hasattr(sc.render, 'ffmpeg'):
    f = sc.render.ffmpeg
    print("   ffmpeg.format:", f.format, " codec:", f.codec, " audio_codec:", f.audio_codec)
    try:
        f.format = '@@@x@@@'
    except TypeError as e:
        print("   ffmpeg.format enum:", str(e).split("not found in")[-1].strip())
print()
for cand in ('FFMPEG', 'AVI_JPEG', 'AVI_RAW', 'H264', 'MPEG4', 'THEORA'):
    try:
        ims.file_format = cand
        print("   OK   file_format=%s" % cand)
    except TypeError:
        print("   FAIL file_format=%s" % cand)
print()
print("=== all build options that are ON ===")
bo = bpy.app.build_options
on = [a for a in dir(bo) if not a.startswith('_') and getattr(bo, a) is True]
print("  ", on)
print()
off = [a for a in dir(bo) if not a.startswith('_') and getattr(bo, a) is False]
print("=== build options OFF ===")
print("  ", off)
