# arch_08_graindiag.py -- WHY is the compositor grain flat? Isolate each stage.
import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"


def sock(n, i):
    return [s for s in n.inputs if s.identifier == i][0]


def build(tag, wire):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = 200; sc.render.resolution_y = 120
    sc.render.dither_intensity = 0.0
    ii = sc.render.image_settings
    ii.file_format = 'PNG'; ii.color_mode = 'RGB'; ii.color_depth = '8'
    ii.color_management = 'OVERRIDE'
    ii.view_settings.view_transform = 'Standard'; ii.view_settings.look = 'None'
    cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
    sc.collection.objects.link(cam); sc.camera = cam
    ng = bpy.data.node_groups.new("T" + tag, "CompositorNodeTree")
    ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
    go = ng.nodes.new("NodeGroupOutput")
    wire(ng, rl, go)
    sc.compositing_node_group = ng
    sc.render.filepath = os.path.join(OUT, "gd_%s.png" % tag)
    bpy.ops.render.render(write_still=True)
    print("wrote gd_%s.png" % tag)


def w_coords_uniform(ng, rl, go):
    ic = ng.nodes.new("CompositorNodeImageCoordinates")
    ng.links.new(ic.outputs['Uniform'], go.inputs['Image'])


def w_coords_pixel(ng, rl, go):
    ic = ng.nodes.new("CompositorNodeImageCoordinates")
    ng.links.new(ic.outputs['Pixel'], go.inputs['Image'])


def w_noise_from_uniform(ng, rl, go):
    ic = ng.nodes.new("CompositorNodeImageCoordinates")
    wn = ng.nodes.new("ShaderNodeTexWhiteNoise"); wn.noise_dimensions = '3D'
    ng.links.new(ic.outputs['Uniform'], wn.inputs['Vector'])
    ng.links.new(wn.outputs['Color'], go.inputs['Image'])


def w_noise_from_pixel(ng, rl, go):
    ic = ng.nodes.new("CompositorNodeImageCoordinates")
    wn = ng.nodes.new("ShaderNodeTexWhiteNoise"); wn.noise_dimensions = '3D'
    ng.links.new(ic.outputs['Pixel'], wn.inputs['Vector'])
    ng.links.new(wn.outputs['Color'], go.inputs['Image'])


def w_texnoise_from_pixel(ng, rl, go):
    ic = ng.nodes.new("CompositorNodeImageCoordinates")
    tn = ng.nodes.new("ShaderNodeTexNoise"); tn.noise_dimensions = '3D'
    tn.inputs['Scale'].default_value = 200.0
    tn.inputs['Detail'].default_value = 0.0
    ng.links.new(ic.outputs['Uniform'], tn.inputs['Vector'])
    ng.links.new(tn.outputs['Color'], go.inputs['Image'])


for tag, fn in (("coords_uniform", w_coords_uniform),
                ("coords_pixel", w_coords_pixel),
                ("wnoise_uniform", w_noise_from_uniform),
                ("wnoise_pixel", w_noise_from_pixel),
                ("texnoise_uniform", w_texnoise_from_pixel)):
    try:
        build(tag, fn)
    except Exception as e:
        print("FAIL", tag, type(e).__name__, e)
