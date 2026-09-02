import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hx(h):
    return tuple(s2l(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def build_scene(w, h):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.image_settings.color_depth = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.dither_intensity = 0.0
    sc.render.film_transparent = True
    # a camera is mandatory even for a pure-compositor render
    cd = bpy.data.cameras.new("C")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc


def make_comp(sc, alpha_mode, bg_hex):
    """THE BLENDER 5.0 COMPOSITOR IDIOM."""
    ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    # 5.0: group interface sockets, not a Composite node
    ng.interface.new_socket("Image", in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    sc.compositing_node_group = ng
    n = ng.nodes
    gin = n.new("NodeGroupInput")
    gout = n.new("NodeGroupOutput")

    img = n.new("CompositorNodeImage")
    bimg = bpy.data.images.load(LOGO, check_existing=True)
    bimg.alpha_mode = alpha_mode
    img.image = bimg

    rgb = n.new("CompositorNodeRGB")
    rgb.outputs[0].default_value = (*hx(bg_hex), 1.0)

    ao = n.new("CompositorNodeAlphaOver")
    # AlphaOver sockets in 5.0
    socknames = [s.name for s in ao.inputs]
    ng.links.new(rgb.outputs[0], ao.inputs[socknames.index("Background")])
    ng.links.new(img.outputs["Image"], ao.inputs[socknames.index("Foreground")])
    ng.links.new(ao.outputs[0], gout.inputs[0])
    return ng, ao, socknames


sc = build_scene(1413, 540)
ng, ao, socknames = make_comp(sc, 'STRAIGHT', "D42B2B")
print("AlphaOver input sockets in 5.0:", socknames)
print("compositing_node_group set:", sc.compositing_node_group)
print("scene.use_nodes (deprecated):", sc.use_nodes)
print()

for mode in ('STRAIGHT', 'PREMUL'):
    sc = build_scene(1413, 540)
    make_comp(sc, mode, "D42B2B")
    sc.render.filepath = os.path.join(OUT, "logo_over_red_%s.png" % mode)
    bpy.ops.render.render(write_still=True)

# scaled-down version, where resampling exposes bad alpha handling
for mode in ('STRAIGHT', 'PREMUL'):
    sc = build_scene(1413, 540)
    ng, ao, sn = make_comp(sc, mode, "D42B2B")
    img_node = [x for x in ng.nodes if x.bl_idname == 'CompositorNodeImage'][0]
    sca = ng.nodes.new("CompositorNodeScale")
    sca.inputs[1].default_value = 0.33
    sca.inputs[2].default_value = 0.33
    ng.links.new(img_node.outputs["Image"], sca.inputs[0])
    ao_node = [x for x in ng.nodes if x.bl_idname == 'CompositorNodeAlphaOver'][0]
    ng.links.new(sca.outputs[0], ao_node.inputs[sn.index("Foreground")])
    sc.render.filepath = os.path.join(OUT, "logo_scaled_%s.png" % mode)
    bpy.ops.render.render(write_still=True)

print("done")
