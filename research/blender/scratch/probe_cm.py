import bpy, sys
s = bpy.context.scene
vs = s.view_settings
ds = s.display_settings
print("=== DEFAULTS (factory startup) ===")
print("display_device      :", ds.display_device)
print("view_transform      :", vs.view_transform)
print("look                :", vs.look)
print("exposure            :", vs.exposure)
print("gamma               :", vs.gamma)
print("use_curve_mapping   :", vs.use_curve_mapping)
try:
    print("use_white_balance   :", vs.use_white_balance)
except Exception as e:
    print("use_white_balance   : ABSENT", e)
print("sequencer_colorspace:", s.sequencer_colorspace_settings.name)
print()
print("=== AVAILABLE view_transform enum ===")
prop = vs.bl_rna.properties['view_transform']
for i in prop.enum_items:
    print("  ", repr(i.identifier))
print()
print("=== AVAILABLE look enum ===")
for i in vs.bl_rna.properties['look'].enum_items:
    print("  ", repr(i.identifier))
print()
print("=== display_device enum ===")
for i in ds.bl_rna.properties['display_device'].enum_items:
    print("  ", repr(i.identifier))
print()
print("=== image_settings colour props ===")
ims = s.render.image_settings
for p in ims.bl_rna.properties:
    if p.identifier in ('color_management','color_depth','color_mode','file_format','compression'):
        print("  ", p.identifier, "=", getattr(ims,p.identifier))
print("  has linear_colorspace_settings:", hasattr(ims,'linear_colorspace_settings'))
if hasattr(ims,'linear_colorspace_settings'):
    print("    linear_colorspace_settings.name =", ims.linear_colorspace_settings.name)
print("  has display_settings:", hasattr(ims,'display_settings'))
print("  has view_settings:", hasattr(ims,'view_settings'))
print()
print("=== render engine enum ===")
for i in s.render.bl_rna.properties['engine'].enum_items:
    print("  ", repr(i.identifier))
print("current engine:", s.render.engine)
