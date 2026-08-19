import bpy

# dynamic engine enum as seen on a live scene
sc = bpy.context.scene
print("=== dynamic engine enum (scene.render RNA on instance) ===")
prop = sc.render.bl_rna.properties['engine']
print([i.identifier for i in prop.enum_items])
try:
    print("enum_items_static:", [i.identifier for i in prop.enum_items_static])
except Exception as e:
    print("no static:", e)
# brute force: try assigning known ids
for cand in ['BLENDER_EEVEE','BLENDER_EEVEE_NEXT','CYCLES','BLENDER_WORKBENCH','HYDRA_STORM']:
    try:
        sc.render.engine = cand
        print("OK assign", cand, "->", sc.render.engine)
    except Exception as e:
        print("FAIL assign", cand, ":", type(e).__name__, e)

print()
print("=== scene.cycles present? ===")
print(hasattr(sc, 'cycles'), type(sc.cycles).__name__ if hasattr(sc,'cycles') else None)
if hasattr(sc,'cycles'):
    print("device enum:", [i.identifier for i in sc.cycles.bl_rna.properties['device'].enum_items])
    print("samples attr:", sc.cycles.samples)

print()
print("=== scene.eevee type + key props ===")
print(type(sc.eevee).__name__)
ee = [p.identifier for p in sc.eevee.bl_rna.properties if not p.is_readonly]
print(ee)

print()
mat = bpy.data.materials.new("probe")
mat.use_nodes = True
nt = mat.node_tree
print("=== default material nodes ===")
for n in nt.nodes:
    print(" node:", n.name, "| bl_idname:", n.bl_idname)

bsdf = nt.nodes.get("Principled BSDF")
print()
print("=== Principled BSDF INPUT sockets (index: name : type : default) ===")
for i, s in enumerate(bsdf.inputs):
    try:
        dv = s.default_value
        if hasattr(dv, '__len__'):
            dv = tuple(round(float(x),3) for x in dv)
    except Exception:
        dv = "<none>"
    print(f"  [{i:2d}] {s.name!r} :: {s.type} = {dv}")

print()
print("=== Principled BSDF OUTPUTS ===")
print([s.name for s in bsdf.outputs])

print()
print("=== Emission-ish node bl_idnames available ===")
cands = ['ShaderNodeEmission','ShaderNodeBsdfPrincipled','ShaderNodeOutputMaterial',
         'ShaderNodeTexImage','ShaderNodeBackground','ShaderNodeMixShader',
         'ShaderNodeBsdfDiffuse','ShaderNodeAttribute','ShaderNodeValue']
for c in cands:
    try:
        n = nt.nodes.new(c)
        print("OK", c, "-> inputs:", [s.name for s in n.inputs], "outputs:", [s.name for s in n.outputs])
        nt.nodes.remove(n)
    except Exception as e:
        print("FAIL", c, type(e).__name__, e)

print()
print("=== World node tree / Background node ===")
w = bpy.data.worlds.new("probeW")
w.use_nodes = True
for n in w.node_tree.nodes:
    print(" world node:", n.name, n.bl_idname, [s.name for s in n.inputs])

print()
print("=== compositor: scene.use_nodes / node_tree ===")
print("has use_nodes:", hasattr(sc,'use_nodes'))
try:
    sc.use_nodes = True
    print("scene.node_tree:", sc.node_tree, type(sc.node_tree).__name__)
    print("comp nodes:", [(n.name,n.bl_idname) for n in sc.node_tree.nodes])
except Exception as e:
    print("ERR comp:", type(e).__name__, e)
print("bpy.data.node_groups:", [(g.name, g.bl_idname if hasattr(g,'bl_idname') else '?', g.type) for g in bpy.data.node_groups])
