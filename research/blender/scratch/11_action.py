import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.mesh.primitive_cube_add()
ob = bpy.context.object
sc.frame_set(1); ob.scale=(0.2,0.2,0.2); ob.keyframe_insert("scale")
sc.frame_set(6); ob.scale=(1,1,1); ob.keyframe_insert("scale")

act = ob.animation_data.action
print("action:", act.name, type(act).__name__)
print("Action props:", [p.identifier for p in act.bl_rna.properties if p.identifier not in ('rna_type',)])
print("has fcurves attr:", hasattr(act,'fcurves'))
print("slots:", [(s.identifier, s.name_display) for s in act.slots])
print("layers:", [l.name for l in act.layers])
for l in act.layers:
    for st in l.strips:
        print("  strip:", st, st.type)
        print("  strip props:", [p.identifier for p in st.bl_rna.properties if p.identifier!='rna_type'])
        cb = st.channelbag(act.slots[0])
        print("  channelbag:", cb)
        print("  fcurves:", [(fc.data_path, fc.array_index, len(fc.keyframe_points)) for fc in cb.fcurves])
        for fc in cb.fcurves:
            print("    keys:", [(kp.co[0], round(kp.co[1],3)) for kp in fc.keyframe_points])

print("\n=== animation_data.action_slot ===")
print(ob.animation_data.action_slot)
print("\n=== does scale animate on frame change? ===")
for f in (1,3,6):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    print("  frame", f, "eval scale:", tuple(round(x,3) for x in ob.evaluated_get(dg).scale))
