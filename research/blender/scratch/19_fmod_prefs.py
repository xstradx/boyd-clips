"""Default interpolation preference + F-Modifiers (noise = camera shake) + drivers."""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boyd_anim import find_fcurve, get_fcurves

bpy.ops.wm.read_factory_settings(use_empty=True)

# --- default interpolation for newly inserted keys ---
e = bpy.context.preferences.edit
props = [p for p in e.bl_rna.properties if 'keyframe' in p.identifier or 'interp' in p.identifier]
for p in props:
    if p.type == 'ENUM':
        print(f"prefs.edit.{p.identifier} = {getattr(e,p.identifier)} :: {[i.identifier for i in p.enum_items]}")
    else:
        print(f"prefs.edit.{p.identifier} = {getattr(e,p.identifier)}")

e.keyframe_new_interpolation_type = 'LINEAR'
bpy.ops.object.empty_add(); ob = bpy.context.object
ob.location = (0,0,0); ob.keyframe_insert("location", frame=1)
ob.location = (0,0,5); ob.keyframe_insert("location", frame=10)
fc = find_fcurve(ob, "location", 2)
print("\nafter setting pref to LINEAR, new key interp =", fc.keyframe_points[0].interpolation)

# --- keyframe_insert with keytype ---
bpy.ops.object.empty_add(); ob2 = bpy.context.object
ob2.keyframe_insert("location", frame=1, keytype='EXTREME')
fc2 = find_fcurve(ob2, "location", 0)
print("keytype set via keyframe_insert:", fc2.keyframe_points[0].type)

# --- F-Modifiers: NOISE on a camera = handheld shake ---
print("\nFModifier types:", [i.identifier for i in
      bpy.types.FModifier.bl_rna.properties['type'].enum_items])
bpy.ops.object.camera_add(); cam = bpy.context.object
cam.rotation_euler = (1.5,0,0); cam.keyframe_insert("rotation_euler", frame=1)
cam.rotation_euler = (1.5,0,0.3); cam.keyframe_insert("rotation_euler", frame=48)
fcz = find_fcurve(cam, "rotation_euler", 2)
base = [round(fcz.evaluate(f),5) for f in range(1,49,8)]

nm = fcz.modifiers.new(type='NOISE')
print("NOISE modifier props:", [p.identifier for p in nm.bl_rna.properties
      if p.identifier not in ('rna_type',) and not p.is_readonly])
nm.scale = 6.0
nm.strength = 0.05
nm.phase = 3.0
nm.depth = 2
fcz.update()
noisy = [round(fcz.evaluate(f),5) for f in range(1,49,8)]
print("base :", base)
print("noisy:", noisy)
print("NOISE modifier changes curve:", base != noisy)

# --- drivers ---
bpy.ops.mesh.primitive_cube_add(); c = bpy.context.object
drv = c.driver_add("scale", 0)
print("\ndriver_add returned:", type(drv).__name__)
d = drv.driver
print("driver type enum:", [i.identifier for i in d.bl_rna.properties['type'].enum_items])
d.type = 'SCRIPTED'
v = d.variables.new(); v.name = 'z'
v.targets[0].id = cam
v.targets[0].data_path = 'location.z'
d.expression = '1 + z*0.5'
cam.location.z = 4.0
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
print("driven scale.x (cam.z=4 -> expect 3.0):", round(c.evaluated_get(dg).scale.x, 4))
