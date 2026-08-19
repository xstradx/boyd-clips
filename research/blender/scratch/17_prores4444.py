import bpy, os, glob
OUT=r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc=bpy.context.scene
sc.frame_start, sc.frame_end = 1, 4
sc.render.engine='BLENDER_EEVEE'; sc.render.use_compositing=False
sc.render.film_transparent=True
sc.render.image_settings.media_type='VIDEO'
sc.render.image_settings.file_format='FFMPEG'
ff=sc.render.ffmpeg
ff.format='QUICKTIME'; ff.codec='PRORES'; ff.audio_codec='NONE'
ff.ffmpeg_prores_profile='4444'                     # MUST be set before color_mode
sc.render.image_settings.color_mode='RGBA'
print("profile:",ff.ffmpeg_prores_profile,"color_mode:",sc.render.image_settings.color_mode)
p=os.path.join(OUT,"prores4444_alpha"); sc.render.filepath=p
bpy.ops.render.render(animation=True)
c=[x for x in glob.glob(p+"*") if os.path.isfile(x)]
print("wrote:", os.path.basename(c[0]), os.path.getsize(c[0]), "bytes")
