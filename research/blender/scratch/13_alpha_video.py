import bpy, os, glob, time
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, 6
sc.render.engine = 'BLENDER_EEVEE'
sc.render.use_compositing = False
sc.render.image_settings.media_type = 'VIDEO'
sc.render.image_settings.file_format = 'FFMPEG'
ff = sc.render.ffmpeg

print("=== color_mode enum when media_type=VIDEO ===")
print([i.identifier for i in sc.render.image_settings.bl_rna.properties['color_mode'].enum_items])

def run(label, container, codec, colmode, transparent, extra=None):
    ff.format = container; ff.codec = codec; ff.audio_codec = 'NONE'
    if extra:
        for k,v in extra.items():
            try:
                setattr(ff, k, v); print(f"    set ff.{k}={v}")
            except Exception as e: print(f"    FAIL set ff.{k}: {e}")
    try:
        sc.render.image_settings.color_mode = colmode
    except Exception as e:
        print(f"  {label}: color_mode {colmode} REJECTED: {e}"); return
    sc.render.film_transparent = transparent
    path = os.path.join(OUT, f"alpha_{label}")
    sc.render.filepath = path
    try:
        bpy.ops.render.render(animation=True)
        c = [x for x in glob.glob(path+"*") if os.path.isfile(x)]
        if c:
            print(f"  {label:26s} OK color_mode={colmode} transp={transparent} -> {os.path.basename(c[0])} ({os.path.getsize(c[0])} b)")
        else:
            print(f"  {label:26s} NOFILE")
    except Exception as e:
        print(f"  {label:26s} FAIL {type(e).__name__}: {e}")

print("\n=== ALPHA VIDEO ATTEMPTS ===")
run("QTRLE_mov_rgba",   "QUICKTIME", "QTRLE",  'RGBA', True)
run("PRORES_mov_rgba",  "QUICKTIME", "PRORES", 'RGBA', True)
run("WEBM_vp9_rgba",    "WEBM",      "WEBM",   'RGBA', True)
run("PNG_avi_rgba",     "AVI",       "PNG",    'RGBA', True)
run("FFV1_mkv_rgba",    "MKV",       "FFV1",   'RGBA', True)
run("H264_mp4_rgb",     "MPEG4",     "H264",   'RGB',  False)

print("\n=== DNXHD workarounds ===")
print("  ffmpeg settings props:", [p.identifier for p in ff.bl_rna.properties if p.identifier!='rna_type'])
sc.render.film_transparent = False
run("DNXHD_avi_default",  "AVI",       "DNXHD", 'RGB', False)
run("DNXHD_mov",          "QUICKTIME", "DNXHD", 'RGB', False)
run("DNXHD_mkv",          "MKV",       "DNXHD", 'RGB', False)
# DNxHD needs a legal bitrate for the frame size/rate
run("DNXHD_mov_br185",    "QUICKTIME", "DNXHD", 'RGB', False,
    extra={'use_autosplit': False, 'constant_rate_factor':'NONE', 'video_bitrate':185000, 'minrate':185000, 'maxrate':185000, 'buffersize':2000})
print("\n  -- retry at 25 fps --")
sc.render.fps = 25
run("DNXHD_mov_25fps_br185", "QUICKTIME", "DNXHD", 'RGB', False,
    extra={'constant_rate_factor':'NONE', 'video_bitrate':185000, 'minrate':185000, 'maxrate':185000, 'buffersize':2000})
