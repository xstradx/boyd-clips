import bpy, addon_utils
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

print("=== ADDONS (cycles) ===")
for m in addon_utils.modules():
    if 'cycles' in m.__name__.lower():
        print(" module:", m.__name__, "enabled:", addon_utils.check(m.__name__))
print("cycles in bpy.context.preferences.addons:", 'cycles' in bpy.context.preferences.addons)

print("engine enum now:", [i.identifier for i in sc.render.bl_rna.properties['engine'].enum_items])
try:
    sc.render.engine = 'CYCLES'
    print("set CYCLES ok ->", sc.render.engine)
except Exception as e:
    print("set CYCLES FAILED:", type(e).__name__, e)

print("\n=== COMPOSITOR ===")
comp_props = [p.identifier for p in sc.bl_rna.properties if 'comp' in p.identifier.lower() or 'node' in p.identifier.lower()]
print("scene compositor/node props:", comp_props)
for p in comp_props:
    try:
        print("   ", p, "=", getattr(sc, p))
    except Exception as e:
        print("   ", p, "ERR", e)

print("\nbpy.data.node_groups types available:")
print([i.identifier for i in bpy.data.bl_rna.functions['node_groups'].parameters if False] if False else "")
# node group tree types
print("NodeTree subclasses:", [c.bl_rna.identifier for c in bpy.types.NodeTree.__subclasses__()])
