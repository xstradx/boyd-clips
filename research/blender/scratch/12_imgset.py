import bpy
sc = bpy.context.scene
ims = sc.render.image_settings
print("=== ImageFormatSettings properties on live instance ===")
for p in ims.bl_rna.properties:
    if p.identifier=='rna_type': continue
    val = getattr(ims, p.identifier, '<?>')
    if p.type=='POINTER': val = type(val).__name__
    print(f"  {p.identifier:28s} {p.type:8s} ro={int(p.is_readonly)}  = {val!r}")

print("\n=== media_type present? ===")
if 'media_type' in ims.bl_rna.properties:
    print("  media_type enum:", [i.identifier for i in ims.bl_rna.properties['media_type'].enum_items])
    print("  current:", ims.media_type)
    print("  file_format options NOW:", [i.identifier for i in ims.bl_rna.properties['file_format'].enum_items])
    print("\n  -> switching media_type to VIDEO")
    ims.media_type = 'VIDEO'
    print("  media_type =", ims.media_type)
    print("  file_format options NOW:", [i.identifier for i in ims.bl_rna.properties['file_format'].enum_items])
    print("  file_format current:", ims.file_format)
    ims.file_format = 'FFMPEG'
    print("  set FFMPEG ok ->", ims.file_format)
    print("  ffmpeg.format:", sc.render.ffmpeg.format, "codec:", sc.render.ffmpeg.codec)
else:
    print("  NO media_type property")
    print("  file_format options:", [i.identifier for i in ims.bl_rna.properties['file_format'].enum_items])

print("\n=== is_movie_format ===")
print(" ", getattr(ims, 'is_movie_format', '<missing>'))
