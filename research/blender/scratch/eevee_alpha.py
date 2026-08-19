import bpy, os, statistics

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hx(h):
    return tuple(s2l(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def build(engine, samples):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x = sc.render.resolution_y = 64
    sc.view_settings.view_transform = 'Standard'
    sc.render.dither_intensity = 0.0
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'OPEN_EXR'
    sc.render.image_settings.color_mode = 'RGBA'
    if engine == 'BLENDER_EEVEE':
        sc.eevee.taa_render_samples = samples
    else:
        sc.cycles.samples = samples
        sc.cycles.use_denoising = False
    cd = bpy.data.cameras.new("C"); cd.type = 'ORTHO'; cd.ortho_scale = 2.0
    cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam)
    cam.location = (0, 0, 5); sc.camera = cam
    me = bpy.data.meshes.new("p")
    me.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)]); me.update()
    ob = bpy.data.objects.new("p", me); sc.collection.objects.link(ob)
    mat = bpy.data.materials.new("m"); mat.use_nodes = True
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


print("TARGET film alpha = 0.500000   (Mix Shader factor 0.5 over transparent film)")
print("%-26s %-10s %-10s %-10s %-10s" % ("engine/samples", "mean A", "min A", "max A", "spread"))
print("-" * 70)
for engine, samples in (('BLENDER_EEVEE', 1), ('BLENDER_EEVEE', 16), ('BLENDER_EEVEE', 64),
                        ('BLENDER_EEVEE', 256), ('CYCLES', 16), ('CYCLES', 128)):
    try:
        sc = build(engine, samples)
    except Exception as e:
        print("%-26s SETUP FAIL %s" % ("%s/%d" % (engine, samples), e)); continue
    p = os.path.join(OUT, "ea_%s_%d.exr" % (engine, samples))
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(p)
    px = list(img.pixels)
    al = px[3::4]
    print("%-26s %-10.5f %-10.5f %-10.5f %-10.5f" % (
        "%s/%d" % (engine, samples), statistics.fmean(al), min(al), max(al), max(al) - min(al)))
    bpy.data.images.remove(img)
