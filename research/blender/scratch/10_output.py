import bpy, os, time, math, glob, shutil
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc = bpy.context.scene

# reframe camera so the sting is legible
cam = bpy.data.objects['Cam']
cam.location = (0, -14.0, 0.2)
cam.rotation_euler = (math.radians(90), 0, 0)
cam.data.lens = 50
bpy.data.objects['LogoManualPlane'].location = (0, 0, -2.6)
bpy.data.objects['logo_transparent'].location = (0, 0, 1.3)
bpy.data.objects['BoydTxt'].location = (0, 0, -0.9)
bpy.data.objects['AccentBar'].location = (0, 0, -1.9)

# simple animation so a sequence is meaningful
tob = bpy.data.objects['BoydTxt']
sc.frame_start, sc.frame_end = 1, 6
for f, sx in ((1, 0.2), (6, 1.0)):
    sc.frame_set(f)
    tob.scale = (sx, sx, sx)
    tob.keyframe_insert("scale")
sc.frame_set(1)
_act = tob.animation_data.action
_cb = _act.layers[0].strips[0].channelbag(tob.animation_data.action_slot)
print("keyframed fcurves on BoydTxt:", [(fc.data_path, fc.array_index, len(fc.keyframe_points)) for fc in _cb.fcurves])

sc.render.engine = 'BLENDER_EEVEE'
sc.render.use_compositing = False
sc.render.film_transparent = False

# ---------- 6a PNG SEQUENCE ----------
print("\n########## 6a PNG SEQUENCE ##########")
seq = os.path.join(OUT, "seq")
if os.path.isdir(seq): shutil.rmtree(seq)
os.makedirs(seq, exist_ok=True)
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'
sc.render.image_settings.compression = 15
sc.render.filepath = os.path.join(seq, "boyd_")
print("filepath prefix:", sc.render.filepath, "| frames", sc.frame_start, "-", sc.frame_end)
t0 = time.perf_counter()
bpy.ops.render.render(animation=True)
t1 = time.perf_counter()
files = sorted(glob.glob(os.path.join(seq, "*.png")))
print(f"  wall clock {t1-t0:.2f}s | {len(files)} files written")
for fp in files:
    print("   ", os.path.basename(fp), os.path.getsize(fp), "bytes")
im = bpy.data.images.load(files[0], check_existing=False)
print("  first frame dims:", tuple(im.size), "channels:", im.channels)
bpy.data.images.remove(im)

# ---------- 6b FFMPEG VIDEO: codec matrix ----------
print("\n########## 6b FFMPEG VIDEO CODEC MATRIX ##########")
sc.render.image_settings.media_type = 'VIDEO'   # NEW IN 5.0 - gates file_format
sc.render.image_settings.file_format = 'FFMPEG'
print("media_type:", sc.render.image_settings.media_type, "file_format:", sc.render.image_settings.file_format)
ff = sc.render.ffmpeg

MATRIX = [
    ("MPEG4",     "H264",   "mp4",  'AAC'),
    ("MPEG4",     "H265",   "mp4",  'AAC'),
    ("MPEG4",     "AV1",    "mp4",  'AAC'),
    ("MPEG4",     "MPEG4",  "mp4",  'MP3'),
    ("MKV",       "H264",   "mkv",  'AAC'),
    ("MKV",       "FFV1",   "mkv",  'FLAC'),
    ("MKV",       "PRORES", "mkv",  'PCM'),
    ("MKV",       "HUFFYUV","mkv",  'PCM'),
    ("WEBM",      "WEBM",   "webm", 'OPUS'),
    ("QUICKTIME", "PRORES", "mov",  'PCM'),
    ("QUICKTIME", "QTRLE",  "mov",  'PCM'),
    ("QUICKTIME", "H264",   "mov",  'AAC'),
    ("AVI",       "PNG",    "avi",  'PCM'),
    ("AVI",       "DNXHD",  "avi",  'PCM'),
    ("OGG",       "THEORA", "ogv",  'VORBIS'),
]

results = []
for container, codec, ext, acodec in MATRIX:
    tag = f"{container}+{codec}"
    path = os.path.join(OUT, f"vid_{container}_{codec}")
    try:
        ff.format = container
        ff.codec = codec
        ff.audio_codec = acodec
        ff.constant_rate_factor = 'HIGH'
        ff.ffmpeg_preset = 'GOOD'
        ff.gopsize = 6
    except Exception as e:
        print(f"  {tag:22s} SETUP-FAIL {type(e).__name__}: {e}")
        results.append((tag, "SETUP-FAIL", str(e)))
        continue
    sc.render.filepath = path
    t0 = time.perf_counter()
    try:
        bpy.ops.render.render(animation=True)
        t1 = time.perf_counter()
        # blender appends frame range + ext
        cand = glob.glob(path + "*")
        cand = [c for c in cand if os.path.isfile(c)]
        if cand:
            c = cand[0]
            print(f"  {tag:22s} OK   {t1-t0:5.2f}s -> {os.path.basename(c)} ({os.path.getsize(c)} bytes)")
            results.append((tag, "OK", os.path.basename(c), os.path.getsize(c)))
        else:
            print(f"  {tag:22s} NOFILE (render returned but no file)")
            results.append((tag, "NOFILE", ""))
    except Exception as e:
        print(f"  {tag:22s} RENDER-FAIL {type(e).__name__}: {e}")
        results.append((tag, "RENDER-FAIL", str(e)))

print("\n########## SUMMARY ##########")
for r in results:
    print("  ", r)
