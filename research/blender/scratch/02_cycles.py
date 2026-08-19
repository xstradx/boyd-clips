import bpy, addon_utils
print("=== all addon modules ===")
names = sorted(m.__name__ for m in addon_utils.modules())
print(names)
print("=== cycles in sys.modules / enabled? ===")
print("cycles addon check:", addon_utils.check("cycles"))
print("=== try enable cycles ===")
try:
    r = addon_utils.enable("cycles", default_set=True, persistent=True)
    print("enable returned:", r)
except Exception as e:
    print("ERR:", type(e).__name__, e)
print("=== engines after ===")
for it in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items:
    print(repr(it.identifier), "|", it.name)
print("=== try set engine CYCLES ===")
try:
    bpy.context.scene.render.engine = 'CYCLES'
    print("engine now:", bpy.context.scene.render.engine)
    print("cycles device enum:", [i.identifier for i in bpy.types.CyclesRenderSettings.bl_rna.properties['device'].enum_items])
except Exception as e:
    print("ERR:", type(e).__name__, e)
print("=== extensions/ prefs addons list ===")
print(sorted(bpy.context.preferences.addons.keys()))
