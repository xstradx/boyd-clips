import bpy

sc = bpy.context.scene
print("=== compositor scene settings (5.0) ===")
for attr in ("use_nodes", "compositor_device", "compositor_precision",
             "compositor_denoise_preview_quality", "compositor_denoise_final_quality"):
    print("   scene.render.%-34s = %r" % (attr, getattr(sc.render, attr, "<ABSENT>")))
print("   scene.use_nodes                            =", getattr(sc, "use_nodes", "<ABSENT>"))
print("   scene.compositing_node_group               =", getattr(sc, "compositing_node_group", "<ABSENT>"))
print("   scene.node_tree                            =", getattr(sc, "node_tree", "<ABSENT>"))

try:
    sc.render.compositor_device = '@@@bogus@@@'
except TypeError as e:
    print("   compositor_device enum:", str(e).split("not found in")[-1].strip())
try:
    sc.render.compositor_precision = '@@@bogus@@@'
except TypeError as e:
    print("   compositor_precision enum:", str(e).split("not found in")[-1].strip())

print()
print("=== compositor node types present in 5.0 ===")
import bpy.types
names = sorted(n for n in dir(bpy.types) if n.startswith("CompositorNode"))
want = ("Image", "AlphaOver", "Composite", "Viewer", "RLayers", "MixRGB", "Mix",
        "Transform", "Scale", "Translate", "SetAlpha", "PremulKey", "Convert",
        "ConvertColorSpace", "Blur", "Glare", "ColorBalance")
for w in want:
    full = "CompositorNode" + w
    print("   %-34s %s" % (full, "OK" if full in names else "ABSENT"))
print()
print("   total CompositorNode* classes:", len(names))
print("   alpha-related:", [n for n in names if any(k in n for k in ("Alpha", "Premul", "Key", "Mask"))])

print()
print("=== image alpha_mode enum ===")
img = bpy.data.images.new("probe", 4, 4, alpha=True)
print("   default alpha_mode :", img.alpha_mode)
try:
    img.alpha_mode = '@@@bogus@@@'
except TypeError as e:
    print("   alpha_mode enum:", str(e).split("not found in")[-1].strip())
print("   default colorspace :", img.colorspace_settings.name)

print()
print("=== what alpha_mode does a freshly LOADED png get? ===")
lg = bpy.data.images.load(r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\logo_transparent.png")
print("   loaded logo alpha_mode :", lg.alpha_mode)
print("   loaded logo colorspace :", lg.colorspace_settings.name)
print("   size                   :", tuple(lg.size), " channels:", lg.channels, " is_float:", lg.is_float)
print("   file_format            :", lg.file_format, " depth:", lg.depth)
