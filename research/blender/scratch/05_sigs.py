import bpy
print("=== bpy.ops.image.import_as_mesh_planes props ===")
rna = bpy.ops.image.import_as_mesh_planes.get_rna_type()
print("desc:", rna.description)
for p in rna.properties:
    if p.identifier == 'rna_type': continue
    extra = ""
    if p.type == 'ENUM':
        extra = " enum=" + str([i.identifier for i in p.enum_items])
    print(f"  {p.identifier} :: {p.type}{extra}")

print()
print("=== bpy.ops.object.text_add props ===")
for p in bpy.ops.object.text_add.get_rna_type().properties:
    if p.identifier!='rna_type': print("  ", p.identifier, p.type)

print()
print("=== bpy.data.fonts.load exists ===")
print(bpy.data.fonts.load)

print()
print("=== TextCurve writable props (subset) ===")
bpy.ops.object.text_add()
ob = bpy.context.object
print("object:", ob.name, "type:", ob.type, "data type:", type(ob.data).__name__)
want = ['body','extrude','bevel_depth','bevel_resolution','size','align_x','align_y','font','font_bold','space_character','offset','fill_mode']
for w in want:
    print("  ", w, "=", repr(getattr(ob.data, w, "<MISSING>")))
print("  fill_mode enum:", [i.identifier for i in ob.data.bl_rna.properties['fill_mode'].enum_items])
print("  align_x enum:", [i.identifier for i in ob.data.bl_rna.properties['align_x'].enum_items])

print()
print("=== bpy.ops.wm.read_factory_settings props ===")
for p in bpy.ops.wm.read_factory_settings.get_rna_type().properties:
    if p.identifier!='rna_type': print("  ", p.identifier, p.type)

print()
print("=== CompositorNodeMix* probe ===")
ng = bpy.data.node_groups.new("t","CompositorNodeTree")
for c in ['CompositorNodeMix','CompositorNodeMixRGB','ShaderNodeMix','CompositorNodeZcombine','CompositorNodeSetAlpha','CompositorNodeConvertColorSpace','CompositorNodeTransform','CompositorNodeRotate','CompositorNodeInvert']:
    try:
        n=ng.nodes.new(c); print("OK ",c,"| in:",[s.name for s in n.inputs],"| out:",[s.name for s in n.outputs])
    except Exception as e: print("FAIL",c,e)
