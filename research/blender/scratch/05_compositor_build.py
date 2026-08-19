import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# What compositor node types exist?
allnodes = sorted([c.bl_rna.identifier for c in bpy.types.CompositorNode.__subclasses__()])
print("N compositor nodes:", len(allnodes))
for want in ['Glare','Lens','Vignette','Blur','ColorBalance','Tonemap','Exposure','RGBCurve','HueSat','Group','Viewer','Composite','Ellipse','Mix']:
    print(f"  ~{want}:", [n for n in allnodes if want.lower() in n.lower()])

print("\n=== CREATE COMPOSITING NODE GROUP ===")
ng = bpy.data.node_groups.new("BoydComp", "CompositorNodeTree")
print("created:", ng, ng.bl_rna.identifier)
sc.compositing_node_group = ng
print("assigned:", sc.compositing_node_group)

# Group interface (4.x+ style: ng.interface)
print("ng.interface:", ng.interface)
i_in = ng.interface.new_socket("Image", in_out='INPUT', socket_type='NodeSocketColor')
i_out = ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
print("sockets made:", i_in.name, i_out.name)

gin = ng.nodes.new("NodeGroupInput")
gout = ng.nodes.new("NodeGroupOutput")
gin.location = (-600, 0); gout.location = (600, 0)

glare = ng.nodes.new("CompositorNodeGlare")
print("\nGlare props:", [p.identifier for p in glare.bl_rna.properties if p.identifier not in ('rna_type',)])
print("glare_type enum:", [i.identifier for i in glare.bl_rna.properties['glare_type'].enum_items])
print("glare inputs:", [(s.name, s.type) for s in glare.inputs])

lens = ng.nodes.new("CompositorNodeLensdist")
print("\nLensdist props:", [p.identifier for p in lens.bl_rna.properties if p.identifier not in ('rna_type',)])
print("lensdist inputs:", [(s.name, s.type) for s in lens.inputs])

cb = ng.nodes.new("CompositorNodeColorBalance")
print("\nColorBalance correction_method:", [i.identifier for i in cb.bl_rna.properties['correction_method'].enum_items])
print("cb inputs:", [(s.name, s.type) for s in cb.inputs])

print("\nAll node identifiers:")
print(allnodes)
