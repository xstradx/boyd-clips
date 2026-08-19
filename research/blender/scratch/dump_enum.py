import bpy
vs = bpy.context.scene.view_settings
for attr in ('view_transform','look'):
    try:
        setattr(vs, attr, '@@@bogus@@@')
    except TypeError as e:
        print(f"--- {attr} ---")
        print(str(e))
        print()
ds = bpy.context.scene.display_settings
try:
    ds.display_device = '@@@bogus@@@'
except TypeError as e:
    print("--- display_device ---"); print(str(e)); print()
img = bpy.data.images.new("t", 4, 4)
try:
    img.colorspace_settings.name = '@@@bogus@@@'
except TypeError as e:
    print("--- image colorspace ---"); print(str(e))
