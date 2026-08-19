import bpy, os
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
im = sc.render.image_settings
print("ImageFormatSettings props:", [p.identifier for p in im.bl_rna.properties if p.identifier != 'rna_type'])
if 'media_type' in im.bl_rna.properties:
    print("media_type =", im.media_type, "::",
          [i.identifier for i in im.bl_rna.properties['media_type'].enum_items])
    im.media_type = 'VIDEO'
    print("after media_type=VIDEO, file_format =", im.file_format)
    print("file_format enum now:", [i.identifier for i in im.bl_rna.properties['file_format'].enum_items])
    im.file_format = 'FFMPEG'
    print("set FFMPEG OK ->", im.file_format)

ff = sc.render.ffmpeg
print("ffmpeg format:", [i.identifier for i in ff.bl_rna.properties['format'].enum_items])
print("ffmpeg codec :", [i.identifier for i in ff.bl_rna.properties['codec'].enum_items])
print("crf enum     :", [i.identifier for i in ff.bl_rna.properties['constant_rate_factor'].enum_items])
print("preset enum  :", [i.identifier for i in ff.bl_rna.properties['ffmpeg_preset'].enum_items])
