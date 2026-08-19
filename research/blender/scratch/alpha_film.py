import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hx(h):
    return tuple(s2l(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


# Scale node socket discovery
bpy.ops.wm.read_factory_settings(use_empty=True)
ng = bpy.data.node_groups.new("t", "CompositorNodeTree")
for bid in ("CompositorNodeScale", "CompositorNodeAlphaOver", "CompositorNodeImage",
            "CompositorNodePremulKey", "CompositorNodeTransform"):
    n = ng.nodes.new(bid)
    print("%-32s in=%s" % (bid, [(s.name, s.type) for s in n.inputs]))
print()

# ---- render a HALF-TRANSPARENT brand-red card over transparent film ----
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = 64
sc.view_settings.view_transform = 'Standard'
sc.render.dither_intensity = 0.0
sc.render.film_transparent = True
sc.render.image_settings.color_mode = 'RGBA'
sc.render.image_settings.color_depth = '8'

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
mx = nt.nodes.new("ShaderNodeMixShader")
out = nt.nodes.new("ShaderNodeOutputMaterial")
em.inputs[0].default_value = (*hx("D42B2B"), 1.0)
em.inputs[1].default_value = 1.0
mx.inputs[0].default_value = 0.5            # 50% coverage
nt.links.new(tr.outputs[0], mx.inputs[1])
nt.links.new(em.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], out.inputs[0])
ob.data.materials.append(mat)

sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = os.path.join(OUT, "alpha_half_png8.png")
bpy.ops.render.render(write_still=True)

sc.render.image_settings.color_depth = '16'
sc.render.filepath = os.path.join(OUT, "alpha_half_png16.png")
bpy.ops.render.render(write_still=True)

sc.render.image_settings.file_format = 'OPEN_EXR'
sc.render.image_settings.color_depth = '32'
sc.render.filepath = os.path.join(OUT, "alpha_half.exr")
bpy.ops.render.render(write_still=True)

print()
print("EXPECTED if STRAIGHT (unassociated): RGB = full #D42B2B (212,43,43), A = 128")
print("EXPECTED if PREMULTIPLIED          : RGB ~= half  (~106,~21,~21),   A = 128")
