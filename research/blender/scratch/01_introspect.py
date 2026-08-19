import bpy, sys, addon_utils

print("=== VERSION ===")
print(bpy.app.version_string, bpy.app.version)

print("=== RENDER ENGINES (RenderEngine.engine enum) ===")
for it in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items:
    print(repr(it.identifier), "|", it.name)

print("=== ADDONS matching image/plane/import ===")
for mod in addon_utils.modules():
    n = mod.__name__
    if any(k in n.lower() for k in ("image", "plane", "import")):
        print(n, "enabled=", addon_utils.check(n))

print("=== bpy.ops.image members ===")
print([m for m in dir(bpy.ops.image)])

print("=== bpy.ops.import_image members ===")
try:
    print([m for m in dir(bpy.ops.import_image)])
except Exception as e:
    print("ERR import_image:", type(e).__name__, e)

print("=== bpy.ops.object.* containing 'image' or 'empty' ===")
print([m for m in dir(bpy.ops.object) if 'image' in m or 'empty' in m])

print("=== FFMPEG format enum ===")
for it in bpy.types.FFmpegSettings.bl_rna.properties['format'].enum_items:
    print(repr(it.identifier), "|", it.name)

print("=== FFMPEG codec enum ===")
for it in bpy.types.FFmpegSettings.bl_rna.properties['codec'].enum_items:
    print(repr(it.identifier), "|", it.name)

print("=== FFMPEG audio_codec enum ===")
for it in bpy.types.FFmpegSettings.bl_rna.properties['audio_codec'].enum_items:
    print(repr(it.identifier), "|", it.name)

print("=== ImageFormatSettings.file_format enum ===")
for it in bpy.types.ImageFormatSettings.bl_rna.properties['file_format'].enum_items:
    print(repr(it.identifier), "|", it.name)

print("=== film_transparent exists? ===")
print('film_transparent' in bpy.types.RenderSettings.bl_rna.properties)
