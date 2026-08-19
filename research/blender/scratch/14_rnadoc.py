import bpy
def doc(t, p):
    pr = t.bl_rna.properties[p]
    print(f"{t.__name__}.{p}")
    print(f"   name: {pr.name}")
    print(f"   description: {pr.description}")
    if pr.type=='ENUM':
        for i in pr.enum_items:
            print(f"     - {i.identifier}: {i.name} :: {i.description}")
    print()

doc(bpy.types.ImageFormatSettings, 'media_type')
doc(bpy.types.Scene, 'compositing_node_group')
doc(bpy.types.RenderSettings, 'film_transparent')
print("Scene has node_tree property:", 'node_tree' in bpy.types.Scene.bl_rna.properties)
print("Scene.use_nodes description:", bpy.types.Scene.bl_rna.properties['use_nodes'].description)
print()
print("bpy.ops.image.import_as_mesh_planes doc:")
print("  ", bpy.ops.image.import_as_mesh_planes.get_rna_type().description)
print("  idname:", bpy.ops.image.import_as_mesh_planes.idname())
print()
print("Action.is_action_layered desc:", bpy.types.Action.bl_rna.properties['is_action_layered'].description)
print("Action.slots desc:", bpy.types.Action.bl_rna.properties['slots'].description)
print()
print("Material.blend_method exists:", 'blend_method' in bpy.types.Material.bl_rna.properties)
print("Material.surface_render_method:", bpy.types.Material.bl_rna.properties['surface_render_method'].description)
for i in bpy.types.Material.bl_rna.properties['surface_render_method'].enum_items:
    print("   -", i.identifier, "::", i.description)
