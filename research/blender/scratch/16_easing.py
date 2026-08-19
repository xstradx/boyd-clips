"""ITEM 2: custom numeric bezier handles = real custom easing.
Compares default AUTO_CLAMPED vs LINEAR vs hand-set cubic-bezier handles."""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boyd_anim import find_fcurve, cubic_bezier_ease, set_interp

bpy.ops.wm.read_factory_settings(use_empty=True)
F0, F1 = 1, 25


def make(name, setup):
    bpy.ops.object.empty_add()
    ob = bpy.context.object
    ob.name = name
    ob.location = (0, 0, 0); ob.keyframe_insert("location", frame=F0)
    ob.location = (0, 0, 1); ob.keyframe_insert("location", frame=F1)
    fc = find_fcurve(ob, "location", 2)
    setup(fc)
    return name, fc


curves = []

curves.append(make("default_bezier", lambda fc: None))

def _lin(fc):
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.update()
curves.append(make("linear", _lin))

# CSS ease-out  cubic-bezier(0.00, 0.90, 0.20, 1.00)
curves.append(make("custom_ease_out", lambda fc: cubic_bezier_ease(fc, 0, (0.00, 0.90), (0.20, 1.00))))
# CSS ease-in   cubic-bezier(0.80, 0.00, 1.00, 0.10)
curves.append(make("custom_ease_in", lambda fc: cubic_bezier_ease(fc, 0, (0.80, 0.00), (1.00, 0.10))))
# CSS ease-in-out cubic-bezier(0.65,0.00,0.35,1.00)
curves.append(make("custom_in_out", lambda fc: cubic_bezier_ease(fc, 0, (0.65, 0.00), (0.35, 1.00))))
# overshoot via handles beyond 1.0
curves.append(make("custom_overshoot", lambda fc: cubic_bezier_ease(fc, 0, (0.30, 1.45), (0.55, 1.25))))
# built-in BACK/EASE_OUT for comparison
def _back(fc):
    for kp in fc.keyframe_points:
        kp.interpolation = 'BACK'; kp.easing = 'EASE_OUT'; kp.back = 1.7
    fc.update()
curves.append(make("builtin_BACK_out", _back))

# verify handles persisted (Blender re-solves AUTO handles; FREE must survive)
fc = curves[2][1]
print("custom_ease_out handle types:",
      fc.keyframe_points[0].handle_right_type, fc.keyframe_points[1].handle_left_type)
print("custom_ease_out handles:", tuple(round(v, 4) for v in fc.keyframe_points[0].handle_right),
      tuple(round(v, 4) for v in fc.keyframe_points[1].handle_left))
fcd = curves[0][1]
print("default handle types:", fcd.keyframe_points[0].handle_right_type,
      fcd.keyframe_points[1].handle_left_type)

hdr = "frame   t   " + "".join(f"{n[:16]:>17s}" for n, _ in curves)
print("\n" + hdr)
print("-" * len(hdr))
for f in range(F0, F1 + 1, 2):
    t = (f - F0) / (F1 - F0)
    row = f"{f:5d} {t:5.2f}  "
    for _, fc in curves:
        row += f"{fc.evaluate(f):17.4f}"
    print(row)

print("\nsanity: value at t=0.25 (frame 7)")
for n, fc in curves:
    print(f"  {n:18s} {fc.evaluate(7):.4f}")
print("\nlinear at t=0.25 should be 0.25; ease_out should be much HIGHER; ease_in much LOWER.")
