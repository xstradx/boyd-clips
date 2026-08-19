import bpy, os, statistics

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hx(h):
    return tuple(s2l(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


bpy.ops.wm.read_factory_settings(use_empty=True)
m = bpy.data.materials.new("probe")
print("=== EEVEE material transparency props in 5.0 ===")
for a in ("surface_render_method", "blend_method", "shadow_method", "use_backface_culling",
          "use_transparent_shadow", "use_raytrace_refraction"):
    print("   material.%-26s = %r" % (a, getattr(m, a, "<ABSENT>")))
try:
    m.surface_render_method = '@@@x@@@'
except TypeError as e:
    print("   surface_render_method enum:", str(e).split("not found in")[-1].strip())
print("   scene.eevee.taa_render_samples default =", bpy.context.scene.eevee.taa_render_samples)
print()


def build(method, samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = sc.render.resolution_y = 64
    sc.view_settings.view_transform = 'Standard'
    sc.render.dither_intensity = 0.0
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'OPEN_EXR'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.eevee.taa_render_samples = samples
    cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 2.0
    cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam)
    cam.location = (0, 0, 5); sc.camera = cam
    me = bpy.data.meshes.new("p")
    me.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)]); me.update()
    ob = bpy.data.objects.new("p", me); sc.collection.objects.link(ob)
    mat = bpy.data.materials.new("m"); mat.use_nodes = True
    mat.surface_render_method = method
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mxs = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em.inputs[0].default_value = (*hx("D42B2B"), 1.0)
    mxs.inputs[0].default_value = 0.5
    nt.links.new(tr.outputs[0], mxs.inputs[1])
    nt.links.new(em.outputs[0], mxs.inputs[2])
    nt.links.new(mxs.outputs[0], out.inputs[0])
    ob.data.materials.append(mat)
    return sc


print("TARGET alpha = 0.5 at EVERY pixel")
print("%-30s %-10s %-10s %-10s" % ("material.surface_render_method", "mean A", "min A", "max A"))
print("-" * 62)
for method in ('DITHERED', 'BLENDED'):
    for samples in (1, 64):
        sc = build(method, samples)
        p = os.path.join(OUT, "eb_%s_%d.exr" % (method, samples))
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(p)
        al = list(img.pixels)[3::4]
        print("%-30s %-10.5f %-10.5f %-10.5f" % (
            "%s / %d spp" % (method, samples), statistics.fmean(al), min(al), max(al)))
        bpy.data.images.remove(img)
