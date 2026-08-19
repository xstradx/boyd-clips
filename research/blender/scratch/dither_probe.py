import bpy, os
sc = bpy.context.scene
print("render.dither_intensity DEFAULT =", sc.render.dither_intensity)
print("render.filter_size      DEFAULT =", sc.render.filter_size)
print("image_settings.color_depth      =", sc.render.image_settings.color_depth)
