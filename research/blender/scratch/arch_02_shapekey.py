# arch_02_shapekey.py -- shape-key shear on an image plane, correct axis this time.
import bpy, os, math

LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def fcurves_of(idb):
    ad = idb.animation_data
    return list(ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves) if ad and ad.action else []


d, f = os.path.split(LOGO)
before = set(bpy.data.objects.keys())
bpy.ops.image.import_as_mesh_planes(directory=d, files=[{"name": f}], shader='EMISSION',
                                    use_transparency=True, render_method='BLENDED',
                                    size_mode='ABSOLUTE', height=1.0, align_axis='+Y')
plane = bpy.data.objects[list(set(bpy.data.objects.keys()) - before)[0]]
print("plane:", plane.name, "| object rotation_euler:",
      tuple(round(math.degrees(a), 2) for a in plane.rotation_euler))
print("LOCAL verts:", [tuple(round(c, 4) for c in v.co) for v in plane.data.vertices])

plane.shape_key_add(name="Basis", from_mix=False)
sk = plane.shape_key_add(name="Shear", from_mix=False)
K = math.tan(math.radians(12.0))
for v in sk.data:                      # local plane lies in XY -> shear x by y
    v.co.x += v.co.y * K
sk.value = 0.0; sk.keyframe_insert('value', frame=1)
sk.value = 1.0; sk.keyframe_insert('value', frame=10)
print("fcurves:", [(fc.data_path, len(fc.keyframe_points)) for fc in fcurves_of(plane.data.shape_keys)])

for fr in (1, 4, 7, 10):
    sc.frame_set(fr)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = plane.evaluated_get(dg); m = ev.to_mesh()
    co = sorted([(round(v.co.x, 4), round(v.co.y, 4)) for v in m.vertices], key=lambda t: (t[1], t[0]))
    top = [c for c in co if c[1] > 0]; bot = [c for c in co if c[1] < 0]
    lean = math.degrees(math.atan2(top[0][0] - bot[0][0], top[0][1] - bot[0][1]))
    print("  frame %2d value=%.4f  lean=%6.3f deg   verts=%s"
          % (fr, plane.data.shape_keys.key_blocks["Shear"].value, lean, co))
    ev.to_mesh_clear()
print("target tan(12 deg) shear -> 12.000 deg at value 1.0")
