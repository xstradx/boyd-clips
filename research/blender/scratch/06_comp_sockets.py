import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
ng = bpy.data.node_groups.new("BoydComp", "CompositorNodeTree")
sc.compositing_node_group = ng

# Enumerate every registerable node id that starts with CompositorNode
ids = sorted([t for t in dir(bpy.types) if t.startswith("CompositorNode")])
print("bpy.types CompositorNode* count:", len(ids))
print(ids)

def dump(idname):
    try:
        n = ng.nodes.new(idname)
    except Exception as e:
        print(f"\n{idname}: CANNOT CREATE -> {e}")
        return
    print(f"\n### {idname}  (label={n.bl_label})")
    # non-base RNA props
    base = set(p.identifier for p in bpy.types.CompositorNode.bl_rna.properties)
    own = [p for p in n.bl_rna.properties if p.identifier not in base]
    for p in own:
        val = getattr(n, p.identifier, None)
        if p.type == 'ENUM':
            print(f"   PROP {p.identifier} (ENUM) = {val} :: {[i.identifier for i in p.enum_items]}")
        else:
            print(f"   PROP {p.identifier} ({p.type}) = {val}")
    for s in n.inputs:
        dv = getattr(s, 'default_value', None)
        extra = ""
        if hasattr(s, 'bl_rna') and 'default_value' in s.bl_rna.properties and s.bl_rna.properties['default_value'].type == 'ENUM':
            extra = " :: " + str([i.identifier for i in s.bl_rna.properties['default_value'].enum_items])
        try:
            dvs = list(dv) if hasattr(dv, '__len__') and not isinstance(dv, str) else dv
        except Exception:
            dvs = dv
        print(f"   IN  '{s.name}' type={s.type} default={dvs}{extra}")
    for s in n.outputs:
        print(f"   OUT '{s.name}' type={s.type}")

for t in ["CompositorNodeGlare","CompositorNodeLensdist","CompositorNodeVignette",
          "CompositorNodeColorBalance","CompositorNodeExposure","CompositorNodeBlur",
          "CompositorNodeTonemap","CompositorNodeHueSat","CompositorNodeRGB",
          "CompositorNodeRLayers","CompositorNodeComposite","CompositorNodeMixRGB",
          "CompositorNodeCurveRGB","CompositorNodeEllipseMask","CompositorNodeKuwahara"]:
    dump(t)
