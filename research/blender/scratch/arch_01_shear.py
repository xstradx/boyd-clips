# arch_01_shear.py -- can Blender 5.0.1 keyframe a SHEAR? (the mark's own operator)
# Also: does the default AgX view transform miss the brand hex?
import bpy, os, math

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"
os.makedirs(OUT, exist_ok=True)
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"


def hdr(s): print("\n########## %s ##########" % s)


def fcurves_of(idblock):
    ad = idblock.animation_data
    if not ad or not ad.action:
        return []
    return list(ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves)


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

hdr("A TextCurve.shear -- native italic/shear on FONT objects")
print("  TextCurve has 'shear':", 'shear' in bpy.types.TextCurve.bl_rna.properties)
p = bpy.types.TextCurve.bl_rna.properties.get('shear')
if p:
    print("  name:", p.name, "| desc:", p.description, "| soft range:",
          p.soft_min, p.soft_max, "| hard:", p.hard_min, p.hard_max)
fnt = bpy.data.fonts.load(FONT)
tc = bpy.data.curves.new("T", type='FONT'); tc.body = "TTT"; tc.font = fnt
tob = bpy.data.objects.new("T", tc); sc.collection.objects.link(tob)
tc.shear = 0.0
tc.keyframe_insert('shear', frame=1)
tc.shear = 0.16
tc.keyframe_insert('shear', frame=20)
print("  keyframed shear fcurves:", [(f.data_path, len(f.keyframe_points)) for f in fcurves_of(tc)])
dg = bpy.context.evaluated_depsgraph_get()
for fr in (1, 5, 10, 15, 20):
    sc.frame_set(fr)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = tob.evaluated_get(dg)
    m = ev.to_mesh()
    xs = [v.co.x for v in m.vertices]; ys = [v.co.y for v in m.vertices]
    # shear angle recovered from top vs bottom extents of the glyph run
    top = [v.co.x for v in m.vertices if v.co.y > max(ys) * 0.9]
    bot = [v.co.x for v in m.vertices if v.co.y < max(ys) * 0.1]
    lean = (min(top) - min(bot)) if top and bot else float('nan')
    print("   frame %2d shear=%.4f  verts=%4d  x-range=%.4f  top-vs-bottom lean=%.4f  deg=%.2f"
          % (fr, tc.shear, len(m.vertices), max(xs) - min(xs), lean,
             math.degrees(math.atan2(lean, max(ys) - min(ys))) if lean == lean else float('nan')))
    ev.to_mesh_clear()

hdr("B shear value that yields 9.08 deg")
target = math.tan(math.radians(9.08))
print("  tan(9.08 deg) =", round(target, 6))
for s in (0.10, 0.1598, 0.16, 0.20):
    sc.frame_set(1)
    tc.animation_data_clear()
    tc.shear = s
    dg = bpy.context.evaluated_depsgraph_get()
    ev = tob.evaluated_get(dg); m = ev.to_mesh()
    ys = [v.co.y for v in m.vertices]
    top = [v.co.x for v in m.vertices if v.co.y > max(ys) * 0.9]
    bot = [v.co.x for v in m.vertices if v.co.y < max(ys) * 0.1]
    lean = min(top) - min(bot)
    print("   shear=%.4f -> measured %.3f deg" % (s, math.degrees(math.atan2(lean, max(ys) - min(ys)))))
    ev.to_mesh_clear()

hdr("C SHAPE KEY shear on an image plane (keyframable, textured)")
d, f = os.path.split(LOGO)
before = set(bpy.data.objects.keys())
r = bpy.ops.image.import_as_mesh_planes(directory=d, files=[{"name": f}], shader='EMISSION',
                                        use_transparency=True, render_method='BLENDED',
                                        size_mode='ABSOLUTE', height=1.0, align_axis='+Y')
plane = bpy.data.objects[list(set(bpy.data.objects.keys()) - before)[0]]
print("  plane:", plane.name, r)
basis = plane.shape_key_add(name="Basis", from_mix=False)
sheared = plane.shape_key_add(name="Shear", from_mix=False)
# plane lies in XZ (align +Y): shear x by z
for v in sheared.data:
    v.co.x += v.co.z * math.tan(math.radians(12.0))
sheared.value = 0.0
sheared.keyframe_insert('value', frame=1)
sheared.value = 1.0
sheared.keyframe_insert('value', frame=10)
kd = plane.data.shape_keys
print("  shape_keys anim fcurves:", [(fc.data_path, len(fc.keyframe_points)) for fc in fcurves_of(kd)])
for fr in (1, 4, 7, 10):
    sc.frame_set(fr)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = plane.evaluated_get(dg); m = ev.to_mesh()
    co = sorted([(round(v.co.x, 4), round(v.co.z, 4)) for v in m.vertices], key=lambda t: t[1])
    print("   frame %2d  verts(x,z) sorted by z: %s" % (fr, co))
    ev.to_mesh_clear()

hdr("D CompositorNodeCornerPin / Transform availability")
ng = bpy.data.node_groups.new("Probe", "CompositorNodeTree")
for n in ("CompositorNodeCornerPin", "CompositorNodeTransform", "CompositorNodeTranslate",
          "CompositorNodeRotate", "CompositorNodeScale", "CompositorNodeDisplace",
          "CompositorNodeMovieDistortion", "CompositorNodePlaneTrackDeform",
          "CompositorNodeEllipseMask", "CompositorNodeBoxMask", "CompositorNodeSetAlpha",
          "CompositorNodeAlphaOver", "CompositorNodeBlur", "CompositorNodeGlare",
          "CompositorNodeLensdist", "CompositorNodeColorBalance", "CompositorNodeConvolve"):
    try:
        node = ng.nodes.new(n)
        print("  ", n, "OK inputs:", [s.name for s in node.inputs])
    except RuntimeError as e:
        print("  ", n, "UNDEFINED")

hdr("E CONTROL: what the DEFAULT AgX ships for the brand hex")


def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_lin(h):
    return tuple(srgb_to_lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))


for name, hx, override in (("agx_bg", "15181D", False), ("agx_red", "D42B2B", False),
                           ("agx_ink", "F2EEE3", False)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = 'BLENDER_EEVEE'
    s.render.resolution_x = 64; s.render.resolution_y = 64
    s.render.dither_intensity = 0.0
    ii = s.render.image_settings
    ii.file_format = 'PNG'; ii.color_mode = 'RGB'; ii.color_depth = '8'
    w = bpy.data.worlds.new("W"); s.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Color'].default_value = hex_to_lin(hx) + (1.0,)
    cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
    s.collection.objects.link(cam); s.camera = cam
    s.render.filepath = os.path.join(OUT, "%s.png" % name)
    bpy.ops.render.render(write_still=True)
    print("  wrote", name, "target #%s  (scene view_transform=%s)" % (hx, s.view_settings.view_transform))

print("\n########## DONE ##########")
