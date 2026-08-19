import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
ng = bpy.data.node_groups.new("C", "CompositorNodeTree")
glare = ng.nodes.new("CompositorNodeGlare")
s = glare.inputs['Type']
print("socket class:", s.bl_rna.identifier)
print("socket props:", [p.identifier for p in s.bl_rna.properties if p.identifier != 'rna_type'])
dv = s.bl_rna.properties['default_value']
print("default_value type:", dv.type)
try:
    print("enum items:", [(i.identifier, i.name) for i in dv.enum_items])
    print("enum items_static:", [(i.identifier, i.name) for i in dv.enum_items_static])
except Exception as e:
    print("enum read err:", e)

# brute force: try known strings
for cand in ['FOG_GLOW','STREAKS','GHOSTS','SIMPLE_STAR','BLOOM','GLOW','Fog Glow','Streaks']:
    try:
        s.default_value = cand
        print(f"  ACCEPTED '{cand}' -> now {s.default_value}")
    except Exception as e:
        print(f"  rejected '{cand}': {str(e)[:120]}")

# What mix nodes exist anywhere?
print("\nMix-ish in bpy.types:", [t for t in dir(bpy.types) if 'Mix' in t])
for cand in ["ShaderNodeMix","CompositorNodeMix","CompositorNodeAlphaOver"]:
    try:
        n = ng.nodes.new(cand); print(f"  {cand}: OK inputs={[i.name for i in n.inputs]}")
    except Exception as e:
        print(f"  {cand}: FAIL {e}")

# Output: group output
print("\nGroup output test")
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
go = ng.nodes.new("NodeGroupOutput")
print("group output inputs:", [i.name for i in go.inputs])
for cand in ["CompositorNodeComposite","CompositorNodeViewer","CompositorNodeOutputFile"]:
    try:
        n = ng.nodes.new(cand); print(f"  {cand}: OK")
    except Exception as e:
        print(f"  {cand}: FAIL {e}")
