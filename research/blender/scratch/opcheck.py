import bpy
print("scene.node_tree exists      :", hasattr(bpy.context.scene,'node_tree'))
print("scene.compositing_node_group:", hasattr(bpy.context.scene,'compositing_node_group'))
cands=[n for n in dir(bpy.ops.node) if 'composit' in n.lower() or 'group' in n.lower()]
print("bpy.ops.node.* group/comp ops:", cands)
print("has new_compositing_node_group:", hasattr(bpy.ops.node,'new_compositing_node_group'))
import bpy.types
print("ShaderNodeGamma present:", hasattr(bpy.types,'ShaderNodeGamma'))
print("CompositorNodeGamma present:", hasattr(bpy.types,'CompositorNodeGamma'))
