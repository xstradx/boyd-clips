import bpy, bpy.types

names = sorted(n for n in dir(bpy.types) if n.startswith("CompositorNode"))
print("=== all CompositorNode* classes in 5.0 (%d) ===" % len(names))
for i in range(0, len(names), 3):
    print("   " + "".join("%-38s" % n for n in names[i:i + 3]))

print()
print("=== scene.compositing_node_group ===")
sc = bpy.context.scene
print("   value:", sc.compositing_node_group)
print("   rna type:", sc.bl_rna.properties['compositing_node_group'].fixed_type.identifier)

print()
print("=== node_groups .new() bl_idname for compositor ===")
ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
print("   created:", ng, ng.bl_idname)
sc.compositing_node_group = ng
print("   assigned to scene ->", sc.compositing_node_group)
print("   interface API present:", hasattr(ng, "interface"))

# a fresh compositor group: what's in it?
print("   nodes in fresh group:", [n.bl_idname for n in ng.nodes])

print()
print("=== how do you get the render OUT? try the candidates ===")
for cand in ("CompositorNodeComposite", "NodeGroupOutput", "CompositorNodeOutputFile",
             "CompositorNodeViewer", "CompositorNodeRLayers", "NodeGroupInput"):
    try:
        n = ng.nodes.new(cand)
        print("   OK     %-28s inputs=%s outputs=%s" % (
            cand, [s.name for s in n.inputs], [s.name for s in n.outputs]))
    except Exception as e:
        print("   FAIL   %-28s %s" % (cand, str(e).splitlines()[0][:80]))

print()
print("=== group interface sockets (the 5.0 way in/out) ===")
print("   ng.interface.items_tree:", [(i.item_type, getattr(i, 'in_out', '?'), i.name) for i in ng.interface.items_tree])
