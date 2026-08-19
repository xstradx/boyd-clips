import bpy, os, time, sys

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
sc = bpy.context.scene

def banner(t): print("\n" + "#"*10 + " " + t + " " + "#"*10)

def report(path):
    ok = os.path.exists(path)
    sz = os.path.getsize(path) if ok else -1
    line = f"  FILE {path} exists={ok} bytes={sz}"
    if ok and path.lower().endswith(".png"):
        im = bpy.data.images.load(path, check_existing=False)
        line += f" | dims={tuple(im.size)} channels={im.channels} depth={im.depth}"
        # sample corner pixel alpha
        px = im.pixels[:]
        if im.channels == 4:
            corner_a = px[3]                       # pixel (0,0) alpha
            n = len(px)
            mid = ((im.size[1]//2)*im.size[0] + im.size[0]//2)*4
            line += f" | corner_alpha={corner_a:.3f} center_rgba=({px[mid]:.3f},{px[mid+1]:.3f},{px[mid+2]:.3f},{px[mid+3]:.3f})"
        bpy.data.images.remove(im)
    print(line)
    return ok

print("loaded blend:", bpy.data.filepath)
print("res:", sc.render.resolution_x, "x", sc.render.resolution_y, "fps:", sc.render.fps)
print("objects:", sorted(bpy.data.objects.keys()))
print("compositing_node_group:", sc.compositing_node_group)

# ---------- 5. EEVEE STILL ----------
banner("5a EEVEE STILL 1920x1080")
sc.render.engine = 'BLENDER_EEVEE'
print("engine =", sc.render.engine)
print("eevee taa_render_samples =", sc.eevee.taa_render_samples)
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'
sc.render.image_settings.color_depth = '8'
sc.render.film_transparent = False
sc.frame_set(1)
p = os.path.join(OUT, "eevee_still.png")
sc.render.filepath = p
t0 = time.perf_counter()
bpy.ops.render.render(write_still=True)
t1 = time.perf_counter()
print(f"  EEVEE WALL CLOCK = {t1-t0:.3f} s")
report(p)

# ---------- 5b CYCLES STILL ----------
banner("5b CYCLES STILL 1920x1080")
sc.render.engine = 'CYCLES'
print("engine =", sc.render.engine)
sc.cycles.device = 'CPU'
sc.cycles.samples = 32
sc.cycles.use_denoising = True
print("cycles device:", sc.cycles.device, "samples:", sc.cycles.samples, "denoise:", sc.cycles.use_denoising)
p = os.path.join(OUT, "cycles_still.png")
sc.render.filepath = p
t0 = time.perf_counter()
bpy.ops.render.render(write_still=True)
t1 = time.perf_counter()
print(f"  CYCLES WALL CLOCK = {t1-t0:.3f} s")
report(p)

# ---------- 5c WORKBENCH ----------
banner("5c WORKBENCH STILL")
sc.render.engine = 'BLENDER_WORKBENCH'
p = os.path.join(OUT, "workbench_still.png")
sc.render.filepath = p
t0 = time.perf_counter()
bpy.ops.render.render(write_still=True)
t1 = time.perf_counter()
print(f"  WORKBENCH WALL CLOCK = {t1-t0:.3f} s")
report(p)

# ---------- 7. FILM TRANSPARENT ----------
banner("7 FILM TRANSPARENT (EEVEE, RGBA PNG)")
sc.render.engine = 'BLENDER_EEVEE'
sc.render.film_transparent = True
print("film_transparent =", sc.render.film_transparent)
sc.render.image_settings.color_mode = 'RGBA'
p = os.path.join(OUT, "eevee_transparent.png")
sc.render.filepath = p
t0 = time.perf_counter()
bpy.ops.render.render(write_still=True)
t1 = time.perf_counter()
print(f"  wall clock = {t1-t0:.3f} s")
report(p)

banner("7b FILM TRANSPARENT (CYCLES)")
sc.render.engine = 'CYCLES'
p = os.path.join(OUT, "cycles_transparent.png")
sc.render.filepath = p
t0 = time.perf_counter()
bpy.ops.render.render(write_still=True)
t1 = time.perf_counter()
print(f"  wall clock = {t1-t0:.3f} s")
report(p)
sc.render.film_transparent = False
