# arch_04_mirror.py -- align_axis and the silent horizontal MIRROR.
# Camera sits at -Y looking toward +Y (the standard "flat graphic" rig).
import bpy, os, math

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"
LOGO = r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\logo_transparent.png"
d, f = os.path.split(LOGO)


def build(axis, tag):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = 800; sc.render.resolution_y = 400
    sc.render.film_transparent = True
    ims = sc.render.image_settings
    ims.file_format = 'PNG'; ims.color_mode = 'RGBA'
    ims.color_management = 'OVERRIDE'
    ims.view_settings.view_transform = 'Standard'; ims.view_settings.look = 'None'
    before = set(bpy.data.objects.keys())
    bpy.ops.image.import_as_mesh_planes(directory=d, files=[{"name": f}], shader='EMISSION',
                                        emit_strength=1.0, use_transparency=True,
                                        render_method='BLENDED', size_mode='ABSOLUTE',
                                        height=1.0, align_axis=axis)
    pl = bpy.data.objects[list(set(bpy.data.objects.keys()) - before)[0]]
    cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam); sc.camera = cam
    cam.location = (0, -4, 0); cam.rotation_euler = (math.radians(90), 0, 0)
    cd.type = 'ORTHO'; cd.ortho_scale = 3.2
    sc.render.filepath = os.path.join(OUT, "mir_%s.png" % tag)
    bpy.ops.render.render(write_still=True)
    print("axis=%-3s obj rot(deg)=%s -> %s" % (
        axis, tuple(round(math.degrees(a), 1) for a in pl.rotation_euler), sc.render.filepath))


print("align_axis enum:", [e.identifier for e in
      bpy.ops.image.import_as_mesh_planes.get_rna_type().properties['align_axis'].enum_items])
for axis, tag in (("+Y", "plusY"), ("-Y", "minusY")):
    build(axis, tag)
