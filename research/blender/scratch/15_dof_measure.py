"""Measure sharpness of the already-rendered DOF frames."""
import bpy, os, sys
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\dof"
ENGINE = sys.argv[sys.argv.index("--") + 1]

def sharp(px, W, x0, x1, y0, y1):
    """Sum of |Laplacian|-ish horizontal+vertical gradient over a box."""
    t = 0.0; n = 0
    for y in range(y0, y1):
        for x in range(x0, x1 - 1):
            i = (y*W + x)*4; j = (y*W + x + 1)*4; k = ((y+1)*W + x)*4
            t += abs(px[i]-px[j]) + abs(px[i]-px[k]); n += 1
    return t/max(n, 1)

# blender images are bottom-up; y=0 is the BOTTOM row
BOXES = {
    "NEAR cube (bottom-left, img y 40..170)":  (10, 110, 40, 170),
    "FAR cubes (centre-right, img y 200..250)": (300, 470, 200, 250),
}

for tag in ("off", "near", "far"):
    p = os.path.join(OUT, f"{ENGINE}_dof_{tag}_.png")
    if not os.path.exists(p):
        print("missing", p); continue
    img = bpy.data.images.load(p)
    px = list(img.pixels); W, H = img.size
    row = [f"{tag:5s}"]
    for name, (x0, x1, y0, y1) in BOXES.items():
        row.append(f"{name.split('(')[0].strip()}={sharp(px, W, x0, x1, y0, y1):.5f}")
    print("  ".join(row))
print("(higher = sharper edges inside that box)")
