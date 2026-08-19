import bpy
sc = bpy.context.scene
print("=== Scene props containing 'comp' or 'node' ===")
for p in bpy.types.Scene.bl_rna.properties:
    if 'comp' in p.identifier or 'node' in p.identifier:
        print(" ", p.identifier, "|", p.type, "|", getattr(p,'fixed_type',None) and p.fixed_type.identifier, "| readonly:", p.is_readonly)

print()
print("=== bpy.data.node_groups.new signature test: CompositorNodeTree ===")
try:
    ng = bpy.data.node_groups.new("BoydComp", "CompositorNodeTree")
    print("created:", ng, type(ng).__name__, "nodes:", len(ng.nodes))
except Exception as e:
    print("ERR:", type(e).__name__, e)

print()
print("=== assign to scene.compositing_node_group ===")
try:
    sc.compositing_node_group = ng
    print("assigned ok ->", sc.compositing_node_group)
except Exception as e:
    print("ERR:", type(e).__name__, e)

print()
print("=== compositor node bl_idnames probe ===")
cands = ['CompositorNodeRLayers','CompositorNodeComposite','CompositorNodeViewer',
         'CompositorNodeImage','CompositorNodeAlphaOver','CompositorNodeMixRGB',
         'CompositorNodeBlur','CompositorNodeGlare','CompositorNodeScale',
         'CompositorNodeTranslate','CompositorNodeOutputFile','CompositorNodeMovieClip',
         'NodeGroupInput','NodeGroupOutput']
for c in cands:
    try:
        n = ng.nodes.new(c)
        print("OK ", c, "| in:", [s.name for s in n.inputs], "| out:", [s.name for s in n.outputs])
    except Exception as e:
        print("FAIL", c, type(e).__name__, e)

print()
print("=== render.use_compositing / related ===")
for k in ('use_compositing','use_sequencer','film_transparent','filter_size'):
    print(" ", k, "=", getattr(sc.render, k, "<missing>"))
