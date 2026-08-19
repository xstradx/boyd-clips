# arch_07_graintest.py -- PROVE per-frame film grain in the 5.0 compositor.
# RLayers -> add (WhiteNoise * amount) -> NodeGroupOutput, noise W driven by scene time.
import bpy, os, math

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"
os.makedirs(OUT, exist_ok=True)


def sock(node, ident):
    return [s for s in node.inputs if s.identifier == ident][0]


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 320; sc.render.resolution_y = 180
sc.render.dither_intensity = 0.0
sc.frame_start = 1; sc.frame_end = 2
ims = sc.render.image_settings
ims.media_type = 'IMAGE'; ims.file_format = 'PNG'; ims.color_mode = 'RGB'; ims.color_depth = '8'
ims.color_management = 'OVERRIDE'
ims.view_settings.view_transform = 'Standard'; ims.view_settings.look = 'None'


def s2l(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (
    s2l(0x15), s2l(0x18), s2l(0x1D), 1.0)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam

ng = bpy.data.node_groups.new("Grain", "CompositorNodeTree")
ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
ic = ng.nodes.new("CompositorNodeImageCoordinates")
print("ImageCoordinates outputs:", [s.name for s in ic.outputs])
st = ng.nodes.new("CompositorNodeSceneTime")
print("SceneTime outputs:", [s.name for s in st.outputs])
wn = ng.nodes.new("ShaderNodeTexWhiteNoise")
wn.noise_dimensions = '4D'
print("WhiteNoise 4D inputs:", [s.name for s in wn.inputs], "outputs:", [s.name for s in wn.outputs])
# scale the 0..1 uniform coords up so every pixel gets its own cell
vm = ng.nodes.new("ShaderNodeVectorMath"); vm.operation = 'SCALE'
mix = ng.nodes.new("ShaderNodeMix")
mix.data_type = 'RGBA'; mix.blend_type = 'ADD'; mix.clamp_result = True
go = ng.nodes.new("NodeGroupOutput")

ng.links.new(rl.outputs['Image'], ic.inputs['Image'])   # <-- DOMAIN. without this it is a constant.
ng.links.new(ic.outputs['Pixel'], vm.inputs[0])
vm.inputs['Scale'].default_value = 1.0
ng.links.new(vm.outputs['Vector'], wn.inputs['Vector'])
ng.links.new(st.outputs['Frame'], wn.inputs['W'])
ng.links.new(rl.outputs['Image'], sock(mix, 'A_Color'))
ng.links.new(wn.outputs['Color'], sock(mix, 'B_Color'))   # per-channel grain, 0..1
sock(mix, 'Factor_Float').default_value = 0.02            # ADD: A + 0.02*B -> +0..2% lift
res = [s for s in mix.outputs if s.identifier == 'Result_Color'][0]
ng.links.new(res, go.inputs['Image'])
sc.compositing_node_group = ng

for fr in (1, 2):
    sc.frame_set(fr)
    sc.render.filepath = os.path.join(OUT, "grain_f%d.png" % fr)
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath)

# control: same scene, no compositor
sc.compositing_node_group = None
sc.frame_set(1)
sc.render.filepath = os.path.join(OUT, "grain_off.png")
bpy.ops.render.render(write_still=True)
print("wrote", sc.render.filepath)
