# arch_03_shearrender.py -- does the TEXTURE actually shear with the shape key,
# and what is the alpha quality of logo_transparent.png?
import bpy, os, math

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"
os.makedirs(OUT, exist_ok=True)
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 1280; sc.render.resolution_y = 720
sc.render.film_transparent = True
sc.render.dither_intensity = 0.0
ims = sc.render.image_settings
ims.media_type = 'IMAGE'; ims.file_format = 'PNG'; ims.color_mode = 'RGBA'; ims.color_depth = '8'
ims.color_management = 'OVERRIDE'
ims.view_settings.view_transform = 'Standard'
ims.view_settings.look = 'None'

d, f = os.path.split(LOGO)
before = set(bpy.data.objects.keys())
bpy.ops.image.import_as_mesh_planes(directory=d, files=[{"name": f}], shader='EMISSION',
                                    emit_strength=1.0, use_transparency=True,
                                    render_method='BLENDED', size_mode='ABSOLUTE',
                                    height=1.0, align_axis='+Y')
plane = bpy.data.objects[list(set(bpy.data.objects.keys()) - before)[0]]
plane.shape_key_add(name="Basis", from_mix=False)
sk = plane.shape_key_add(name="Shear", from_mix=False)
K = math.tan(math.radians(20.0))
for v in sk.data:
    v.co.x += v.co.y * K
sk.value = 0.0; sk.keyframe_insert('value', frame=1)
sk.value = 1.0; sk.keyframe_insert('value', frame=2)

cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -4, 0); cam.rotation_euler = (math.radians(90), 0, 0)
cd.type = 'ORTHO'; cd.ortho_scale = 4.0

for fr, tag in ((1, "noshear"), (2, "shear20")):
    sc.frame_set(fr)
    sc.render.filepath = os.path.join(OUT, "shr_%s.png" % tag)
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath, "shape key value:",
          plane.data.shape_keys.key_blocks["Shear"].value)

print("\n########## LOGO ALPHA AUDIT (source PNG, read via Blender) ##########")
img = bpy.data.images.load(LOGO)
px = list(img.pixels)
n = len(px) // 4
a = px[3::4]
zero = sum(1 for v in a if v <= 0.0)
one = sum(1 for v in a if v >= 1.0)
part = n - zero - one
print("  size:", tuple(img.size), "channels:", img.channels, "total px:", n)
print("  alpha == 0 :", zero)
print("  alpha == 1 :", one)
print("  0 < alpha < 1 (antialiased edge pixels):", part,
      "-> %.4f%%" % (100.0 * part / n))
