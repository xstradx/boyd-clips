# arch_06_grain.py -- is there a proven route to per-frame film GRAIN in 5.0?
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
ng = bpy.data.node_groups.new("G", "CompositorNodeTree")

print("--- compositor node types containing noise/grain/dither/random ---")
cands = [t for t in dir(bpy.types) if t.startswith("CompositorNode")
         and any(k in t.lower() for k in ("noise", "grain", "dither", "random", "texture", "seed"))]
print(" ", cands)

print("\n--- can SHADER noise nodes live inside a CompositorNodeTree? ---")
for n in ("ShaderNodeTexNoise", "ShaderNodeTexWhiteNoise", "ShaderNodeTexVoronoi",
          "ShaderNodeMix", "ShaderNodeValToRGB", "ShaderNodeMath", "ShaderNodeValue",
          "ShaderNodeTexCoord", "ShaderNodeSeparateColor", "ShaderNodeCombineColor",
          "ShaderNodeRGBCurve", "ShaderNodeHueSaturation", "ShaderNodeGamma",
          "ShaderNodeBrightContrast", "ShaderNodeInvert", "ShaderNodeClamp",
          "ShaderNodeMapRange", "ShaderNodeVectorMath"):
    try:
        node = ng.nodes.new(n)
        print("  OK  ", n, "| in:", [s.name for s in node.inputs][:8],
              "| out:", [s.name for s in node.outputs][:4])
    except RuntimeError:
        print("  --  ", n, "UNDEFINED in compositor tree")

print("\n--- ShaderNodeTexNoise sockets (for a grain plate) ---")
try:
    tn = ng.nodes.new("ShaderNodeTexNoise")
    print("  inputs :", [(s.name, s.type) for s in tn.inputs])
    print("  outputs:", [(s.name, s.type) for s in tn.outputs])
    print("  noise_dimensions:", [e.identifier for e in
          tn.bl_rna.properties['noise_dimensions'].enum_items])
except Exception as e:
    print("  ERR", e)

print("\n--- CompositorNodeTexture (classic texture input node) ---")
try:
    ct = ng.nodes.new("CompositorNodeTexture")
    print("  OK inputs:", [s.name for s in ct.inputs], "outputs:", [s.name for s in ct.outputs])
    print("  has .texture:", hasattr(ct, "texture"))
    tex = bpy.data.textures.new("grain", type='NOISE')
    ct.texture = tex
    print("  assigned bpy.data.textures NOISE ->", ct.texture.name, ct.texture.type)
    print("  texture types:", [e.identifier for e in
          bpy.types.Texture.bl_rna.properties['type'].enum_items])
except Exception as e:
    print("  ERR", type(e).__name__, e)

print("\n--- render.dither_intensity (the built-in 8-bit dither) ---")
p = sc.render.bl_rna.properties['dither_intensity']
print("  default:", sc.render.dither_intensity, "| range", p.hard_min, p.hard_max)
print("  desc:", p.description)

print("\n--- full CompositorNode* inventory (count) ---")
allc = sorted(t for t in dir(bpy.types) if t.startswith("CompositorNode"))
print("  count:", len(allc))
print("  ", allc)
