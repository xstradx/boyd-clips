import bpy, os, glob
OUT=r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc=bpy.context.scene
sc.render.image_settings.media_type='VIDEO'
sc.render.image_settings.file_format='FFMPEG'
ff=sc.render.ffmpeg
print("prores profile enum:", [i.identifier for i in ff.bl_rna.properties['ffmpeg_prores_profile'].enum_items])
ff.format='QUICKTIME'; ff.codec='PRORES'; ff.audio_codec='NONE'
for prof in [i.identifier for i in ff.bl_rna.properties['ffmpeg_prores_profile'].enum_items]:
    ff.ffmpeg_prores_profile = prof
    allowed = [i.identifier for i in sc.render.image_settings.bl_rna.properties['color_mode'].enum_items]
    try:
        sc.render.image_settings.color_mode='RGBA'; got='RGBA-ACCEPTED'
    except Exception as e:
        got='RGBA-REJECTED'
    print(f"  profile={prof:10s} color_mode enum={allowed} -> {got}")
print("\nconstant_rate_factor enum:", [i.identifier for i in ff.bl_rna.properties['constant_rate_factor'].enum_items])
print("ffmpeg_preset enum:", [i.identifier for i in ff.bl_rna.properties['ffmpeg_preset'].enum_items])
