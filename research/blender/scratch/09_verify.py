import bpy, os
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc = bpy.context.scene

def stats(path, label):
    im = bpy.data.images.load(path, check_existing=False)
    px = list(im.pixels)
    w,h = im.size
    n = w*h
    a = px[3::4]
    r = px[0::4]; g = px[1::4]; b = px[2::4]
    opaque = sum(1 for v in a if v > 0.5)
    bright = sum(1 for i in range(n) if (r[i]+g[i]+b[i])/3 > 0.25 and a[i] > 0.5)
    print(f"  {label}: {w}x{h} opaque_px={opaque} ({100*opaque/n:.1f}%) bright_px={bright} ({100*bright/n:.2f}%) "
          f"max_rgb=({max(r):.3f},{max(g):.3f},{max(b):.3f})")
    bpy.data.images.remove(im)

print("=== A: render WITH compositor group (logo alpha-over) ===")
sc.render.engine = 'BLENDER_EEVEE'
sc.render.film_transparent = False
sc.render.use_compositing = True
print("use_compositing:", sc.render.use_compositing, "group:", sc.compositing_node_group.name)
p = os.path.join(OUT, "comp_ON.png"); sc.render.filepath = p
bpy.ops.render.render(write_still=True)
stats(p, "comp_ON")

print("=== B: render WITHOUT compositor ===")
sc.render.use_compositing = False
p = os.path.join(OUT, "comp_OFF.png"); sc.render.filepath = p
bpy.ops.render.render(write_still=True)
stats(p, "comp_OFF")

print("=== C: diff the two ===")
ia = bpy.data.images.load(os.path.join(OUT,"comp_ON.png"), check_existing=False)
ib = bpy.data.images.load(os.path.join(OUT,"comp_OFF.png"), check_existing=False)
pa = list(ia.pixels); pb = list(ib.pixels)
diff = sum(1 for i in range(0, len(pa), 4) if abs(pa[i]-pb[i])>0.01 or abs(pa[i+1]-pb[i+1])>0.01 or abs(pa[i+2]-pb[i+2])>0.01)
print(f"  pixels differing between comp ON/OFF: {diff} ({100*diff/(ia.size[0]*ia.size[1]):.2f}%)")
print("  -> compositor node group IS affecting output" if diff > 1000 else "  -> NO effect from compositor")

print("=== D: content check on scene renders ===")
sc.render.use_compositing = False
stats(os.path.join(OUT,"eevee_still.png"), "eevee_still (has comp)")
stats(os.path.join(OUT,"cycles_still.png"), "cycles_still (has comp)")
stats(os.path.join(OUT,"eevee_transparent.png"), "eevee_transparent")
