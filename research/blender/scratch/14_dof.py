"""ITEM 5: depth of field via camera settings."""
import bpy, os, sys
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\dof"
os.makedirs(OUT, exist_ok=True)
ENGINE = sys.argv[sys.argv.index("--") + 1]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = ENGINE
sc.render.resolution_x, sc.render.resolution_y = 640, 360
sc.render.image_settings.file_format = 'PNG'
if ENGINE == 'BLENDER_EEVEE':
    sc.eevee.taa_render_samples = 64
else:
    sc.cycles.samples = 64; sc.cycles.device = 'CPU'

w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.082, 0.094, 0.114, 1)
bpy.ops.object.light_add(type='AREA', location=(4, -6, 6)); bpy.context.object.data.energy = 3000

# a receding row of cubes: near y=-2, far y=+16
objs = []
for i in range(7):
    y = -2 + i * 3.0
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(i * 0.9 - 2.5, y, 0))
    o = bpy.context.object
    m = bpy.data.materials.new(f"M{i}"); m.use_nodes = True; o.data.materials.append(m)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.95, 0.93, 0.89, 1) if i % 2 else (0.831, 0.169, 0.169, 1)
    b.inputs["Roughness"].default_value = 0.4
    objs.append(o)

bpy.ops.object.camera_add(location=(0, -10, 1.2), rotation=(1.50, 0, 0))
cam = bpy.context.object; sc.camera = cam
cam.data.lens = 55

d = cam.data.dof
print("DOF props:", {p: getattr(d, p) for p in
      ['use_dof', 'focus_distance', 'aperture_fstop', 'aperture_blades', 'aperture_rotation', 'aperture_ratio']})

# OFF
d.use_dof = False
sc.render.filepath = os.path.join(OUT, f"{ENGINE}_dof_off_")
bpy.ops.render.render(write_still=True)

# ON, focused on the NEAREST cube via focus_object
d.use_dof = True
d.focus_object = objs[0]
d.aperture_fstop = 0.7
d.aperture_blades = 6
d.aperture_rotation = 0.2
d.aperture_ratio = 1.0
print("use_dof:", d.use_dof, "focus_object:", d.focus_object.name, "fstop:", d.aperture_fstop)
sc.render.filepath = os.path.join(OUT, f"{ENGINE}_dof_near_")
bpy.ops.render.render(write_still=True)

# ON, focused on the FARTHEST cube (focus_distance instead of object)
d.focus_object = None
d.focus_distance = 24.0
print("focus_distance:", d.focus_distance)
sc.render.filepath = os.path.join(OUT, f"{ENGINE}_dof_far_")
bpy.ops.render.render(write_still=True)

# quantify: local contrast (sum of |gradient|) in a near strip vs far strip
def load(p):
    img = bpy.data.images.load(p); return list(img.pixels), img.size[0], img.size[1]

def contrast(px, W, x0, x1, y0, y1):
    t = 0.0
    for y in range(y0, y1):
        for x in range(x0, x1 - 1):
            i = (y*W + x)*4; j = (y*W + x + 1)*4
            t += abs(px[i] - px[j])
    return t

for tag in ("off", "near", "far"):
    p = os.path.join(OUT, f"{ENGINE}_dof_{tag}_.png")
    px, W, H = load(p)
    near = contrast(px, W, 20, 300, 120, 260)    # bottom-left = nearest cubes
    far = contrast(px, W, 340, 620, 150, 230)    # centre-right = far cubes
    print(f"{ENGINE} dof_{tag:4s}: near-strip contrast={near:9.1f}  far-strip contrast={far:9.1f}")
