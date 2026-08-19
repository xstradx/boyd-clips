import bpy

# Build a scene with an animated object so we get a real Keyframe RNA struct
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
ob = bpy.context.object
ob.location = (0, 0, 0)
ob.keyframe_insert("location", frame=1)
ob.location = (5, 0, 0)
ob.keyframe_insert("location", frame=25)

kp = ob.animation_data.action.fcurves[0].keyframe_points[0]

def enums(struct, prop):
    return [i.identifier for i in struct.bl_rna.properties[prop].enum_items]

print("KEYFRAME RNA path :", kp.bl_rna.identifier)
print("interpolation     :", enums(kp, "interpolation"))
print("easing            :", enums(kp, "easing"))
print("handle_left_type  :", enums(kp, "handle_left_type"))
print("type (keyframe)   :", enums(kp, "type"))

fc = ob.animation_data.action.fcurves[0]
print("fcurve extrapolation:", enums(fc, "extrapolation"))
print("fcurve auto_smoothing:", enums(fc, "auto_smoothing") if "auto_smoothing" in fc.bl_rna.properties else "N/A")

# keyframe_insert options enum (used to control default interp)
print("keyframe_insert sig props:", [p for p in dir(ob) if "keyframe" in p])

# Modifiers on fcurves
m = fc.modifiers
print("fcurve modifier types:", enums(bpy.types.FModifier.bl_rna_get_subclass_py("FModifier") or bpy.types.FModifier, "type") if False else [c.__name__ for c in bpy.types.FModifier.__subclasses__()])

# Data-block animation: slots (4.4+ layered action system)
act = ob.animation_data.action
print("Action type:", act.bl_rna.identifier)
print("Action has 'slots':", hasattr(act, "slots"))
print("Action has 'layers':", hasattr(act, "layers"))
if hasattr(act, "slots"):
    print("slots:", [s.identifier for s in act.slots])
print("Action.fcurves accessible directly:", len(act.fcurves))
