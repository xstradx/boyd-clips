# arch_00_verify.py -- architect's re-verification of every load-bearing idiom
# before it is written into BLENDER-CAPABILITY.md.
# Run: blender.exe -b --python arch_00_verify.py
import bpy, os, sys, math, time

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"
os.makedirs(OUT, exist_ok=True)
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"

def hdr(s): print("\n########## %s ##########" % s)

hdr("0 VERSION")
print("VER", bpy.app.version_string, bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else bpy.app.build_hash)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

hdr("1 ENGINE ENUM LIES")
try:
    print("enum_items:", [e.identifier for e in sc.render.bl_rna.properties['engine'].enum_items])
except Exception as e:
    print("ERR", e)
for cand in ("BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH", "BLENDER_EEVEE_NEXT"):
    try:
        sc.render.engine = cand
        print("  assign OK ->", cand)
    except TypeError as e:
        print("  assign FAIL", cand, "::", str(e)[:120])
sc.render.engine = 'BLENDER_EEVEE'

hdr("2 COLOUR MANAGEMENT ENUMS LIE TOO")
vs = sc.view_settings
print("view_transform enum_items:", [e.identifier for e in vs.bl_rna.properties['view_transform'].enum_items])
try:
    vs.view_transform = "__junk__"
except TypeError as e:
    print("true set:", str(e)[str(e).find("in ("):])
print("scene default view_transform:", vs.view_transform, "| look:", vs.look)

hdr("3 media_type GATES file_format")
ims = sc.render.image_settings
print("media_type default:", ims.media_type, "file_format:", ims.file_format)
try:
    ims.file_format = 'FFMPEG'
    print("  direct FFMPEG assign: OK (unexpected)")
except TypeError as e:
    print("  direct FFMPEG assign FAILED as documented:", str(e)[:110])
ims.media_type = 'VIDEO'
print("  after media_type='VIDEO':", ims.media_type, ims.file_format)
ims.media_type = 'IMAGE'
ims.file_format = 'PNG'
print("  back to IMAGE:", ims.media_type, ims.file_format)

hdr("4 color_mode ORDER DEPENDS ON CODEC")
ims.media_type = 'VIDEO'
ims.file_format = 'FFMPEG'
ff = sc.render.ffmpeg
ff.format = 'QUICKTIME'
ff.codec = 'H264'
try:
    ims.color_mode = 'RGBA'
    print("  RGBA under H264: accepted (unexpected)")
except TypeError as e:
    print("  RGBA under H264 REJECTED:", str(e)[:100])
ff.codec = 'QTRLE'
ims.color_mode = 'RGBA'
print("  RGBA under QTRLE:", ims.color_mode)
ff.codec = 'PRORES'
try:
    ims.color_mode = 'RGBA'
    print("  RGBA under PRORES default profile:", ims.color_mode)
except TypeError as e:
    print("  RGBA under PRORES default profile REJECTED:", str(e)[:90], "| profile was", ff.ffmpeg_prores_profile)
ff.ffmpeg_prores_profile = '4444'
ims.color_mode = 'RGBA'
print("  RGBA under PRORES 4444:", ims.color_mode)
ims.media_type = 'IMAGE'; ims.file_format = 'PNG'; ims.color_mode = 'RGBA'

hdr("5 SLOTTED ACTION FCURVE PATH")
bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.object
cube.scale = (0.2, 0.2, 0.2); cube.keyframe_insert('scale', frame=1)
cube.scale = (1.0, 1.0, 1.0); cube.keyframe_insert('scale', frame=6)
ad = cube.animation_data
act = ad.action
print("  Action has .fcurves attr:", hasattr(act, "fcurves"))
cb = act.layers[0].strips[0].channelbag(ad.action_slot)
fcs = list(cb.fcurves)
print("  channelbag fcurves:", [(f.data_path, f.array_index, len(f.keyframe_points)) for f in fcs])
kp = fcs[0].keyframe_points[0]
print("  default interpolation from keyframe_insert:", kp.interpolation, "| handles:", kp.handle_left_type, kp.handle_right_type)

hdr("6 CUSTOM BEZIER HANDLES IN (frame,value) SPACE")
fc = fcs[0]
k0, k1 = fc.keyframe_points[0], fc.keyframe_points[1]
k0.interpolation = 'BEZIER'
for k in (k0, k1):
    k.handle_left_type = 'FREE'; k.handle_right_type = 'FREE'
# emulate cubic-bezier(0.42,0,0.58,1) over frames 1..6, values 0.2..1.0
f0, v0 = k0.co; f1, v1 = k1.co
df, dv = f1 - f0, v1 - v0
k0.handle_right = (f0 + 0.42 * df, v0 + 0.0 * dv)
k1.handle_left = (f0 + 0.58 * df, v0 + 1.0 * dv)
fc.update()
print("  handle types survive:", k0.handle_right_type, k1.handle_left_type)
print("  evaluated:", [round(fc.evaluate(f), 4) for f in range(1, 7)])

hdr("7 COMPOSITOR NODE GROUP (RLayers REQUIRED)")
print("  Scene has node_tree prop:", 'node_tree' in bpy.types.Scene.bl_rna.properties)
ng = bpy.data.node_groups.new("ArchComp", "CompositorNodeTree")
ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
for bad in ("CompositorNodeComposite", "CompositorNodeMixRGB", "CompositorNodeMix", "CompositorNodeVignette"):
    try:
        ng.nodes.new(bad); print("  ", bad, "OK (unexpected)")
    except RuntimeError as e:
        print("  ", bad, "UNDEFINED ->", str(e)[:60])
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
gl = ng.nodes.new("CompositorNodeGlare")
print("  Glare DEFAULT Type socket value:", repr(gl.inputs['Type'].default_value))
try:
    gl.inputs['Type'].default_value = 'FOG_GLOW'
except TypeError as e:
    print("  identifier rejected, true set:", str(e)[str(e).find("in ("):])
gl.inputs['Type'].default_value = 'Bloom'
print("  set by display string ->", gl.inputs['Type'].default_value)
print("  MENU socket enum_items:", list(gl.inputs['Type'].bl_rna.properties['default_value'].enum_items))
go = ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
ng.links.new(gl.outputs['Image'], go.inputs['Image'])
sc.compositing_node_group = ng
print("  assigned:", sc.compositing_node_group.name)

hdr("8 IMAGE PLANE IMPORT: filepath= vs directory+files=")
d, f = os.path.split(LOGO)
r = bpy.ops.image.import_as_mesh_planes(filepath=LOGO, shader='EMISSION', use_transparency=True)
print("  filepath= only ->", r)
before = set(bpy.data.objects.keys())
r = bpy.ops.image.import_as_mesh_planes(
    directory=d, files=[{"name": f}], shader='EMISSION', emit_strength=1.0,
    use_transparency=True, render_method='BLENDED', size_mode='ABSOLUTE',
    height=1.0, align_axis='+Y')
new = set(bpy.data.objects.keys()) - before
print("  directory+files ->", r, "| new objects:", new)
plane = bpy.data.objects[list(new)[0]]
bpy.context.view_layer.update()
print("  dims:", tuple(round(x, 4) for x in plane.dimensions),
      "| surface_render_method:", plane.data.materials[0].surface_render_method)

hdr("9 FONT: loads, and is born flat in XY facing +Z")
fnt = bpy.data.fonts.load(FONT)
tc = bpy.data.curves.new("T", type='FONT'); tc.body = "TTT"; tc.font = fnt
tob = bpy.data.objects.new("T", tc); sc.collection.objects.link(tob)
bpy.context.view_layer.update()
print("  font:", fnt.name, "| text obj dims (pre-rotate):", tuple(round(x, 3) for x in tob.dimensions))
tob.rotation_euler = (math.radians(90), 0, 0)
bpy.context.view_layer.update()
print("  after rot X 90:", tuple(round(x, 3) for x in tob.dimensions))

hdr("10 BRAND-EXACT COLOUR: image_settings.color_management OVERRIDE")
print("  image_settings has color_management:", 'color_management' in ims.bl_rna.properties)
print("  color_management enum:", [e.identifier for e in ims.bl_rna.properties['color_management'].enum_items])
ims.color_management = 'OVERRIDE'
ims.view_settings.view_transform = 'Standard'
ims.view_settings.look = 'None'
print("  OVERRIDE set. scene view_transform still:", sc.view_settings.view_transform,
      "| output view_transform:", ims.view_settings.view_transform)

def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def hex_to_lin(h):
    return tuple(srgb_to_lin(int(h[i:i+2], 16)) for i in (0, 2, 4))

# flat emissive card render of each brand colour, output through Standard
for name, hx in (("bg", "15181D"), ("red", "D42B2B"), ("ink", "F2EEE3")):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = 'BLENDER_EEVEE'
    s.render.resolution_x = 64; s.render.resolution_y = 64
    s.render.film_transparent = False
    s.render.dither_intensity = 0.0
    ii = s.render.image_settings
    ii.media_type = 'IMAGE'; ii.file_format = 'PNG'; ii.color_mode = 'RGB'; ii.color_depth = '8'
    ii.color_management = 'OVERRIDE'
    ii.view_settings.view_transform = 'Standard'
    ii.view_settings.look = 'None'
    w = bpy.data.worlds.new("W"); s.world = w
    w.use_nodes = True
    bgn = w.node_tree.nodes['Background']
    bgn.inputs['Color'].default_value = hex_to_lin(hx) + (1.0,)
    bgn.inputs['Strength'].default_value = 1.0
    cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
    s.collection.objects.link(cam); s.camera = cam
    s.render.filepath = os.path.join(OUT, "brand_%s.png" % name)
    bpy.ops.render.render(write_still=True)
    print("  wrote", s.render.filepath, "target #%s" % hx)

print("\n########## DONE ##########")
