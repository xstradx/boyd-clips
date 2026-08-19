import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
ob = bpy.context.object
ob.location = (0, 0, 0)
ob.keyframe_insert("location", frame=1)
ob.location = (5, 0, 0)
ob.keyframe_insert("location", frame=25)

act = ob.animation_data.action
print("Action props:", [p.identifier for p in act.bl_rna.properties if not p.is_readonly or p.type == 'COLLECTION'])
print("--- dir(act) filtered ---")
print([d for d in dir(act) if not d.startswith("_")])

print("slots:", [(s.identifier, s.handle, s.name_display) for s in act.slots])
print("layers:", [l.name for l in act.layers])
lay = act.layers[0]
print("layer strips:", [(s.type,) for s in lay.strips])
strip = lay.strips[0]
print("strip dir:", [d for d in dir(strip) if not d.startswith("_")])

slot = ob.animation_data.action_slot
print("anim_data.action_slot:", slot.identifier)
cb = strip.channelbag(slot)
print("channelbag:", cb)
print("channelbag dir:", [d for d in dir(cb) if not d.startswith("_")])
print("fcurves:", [(f.data_path, f.array_index) for f in cb.fcurves])

fc = cb.fcurves[0]
kp = fc.keyframe_points[0]

def enums(struct, prop):
    return [i.identifier for i in struct.bl_rna.properties[prop].enum_items]

print("=== ENUMS ===")
print("interpolation    :", enums(kp, "interpolation"))
print("easing           :", enums(kp, "easing"))
print("handle_left_type :", enums(kp, "handle_left_type"))
print("keyframe type    :", enums(kp, "type"))
print("fcurve extrap    :", enums(fc, "extrapolation"))
print("kp props:", [p.identifier for p in kp.bl_rna.properties if p.identifier != 'rna_type'])
