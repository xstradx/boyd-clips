"""Do the three render paths produce IDENTICAL pixels for the same frame?
(i.e. does motion blur survive a frame_set + write_still loop?)"""
import bpy, os
R = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\paths"
trip = {
    "A_anim":   os.path.join(R, "A", "a_0004.png"),
    "B_loop":   os.path.join(R, "B", "b_0004.png"),
    "C_cli":    os.path.join(R, "C", "c_0004.png"),
}
data = {}
for k, p in trip.items():
    img = bpy.data.images.load(p)
    data[k] = (list(img.pixels), img.size[0])
    px = data[k][0]
    lit = sum(1 for i in range(0, len(px), 4) if px[i] > 0.15)
    print(f"{k}: lit pixels(R>0.15) = {lit}")

keys = list(trip)
for i in range(len(keys)):
    for j in range(i+1, len(keys)):
        a, b = data[keys[i]][0], data[keys[j]][0]
        m = sum(abs(a[k]-b[k]) for k in range(len(a)))/len(a)
        mx = max(abs(a[k]-b[k]) for k in range(len(a)))
        print(f"{keys[i]} vs {keys[j]}: mean|d|={m:.8f} max|d|={mx:.6f} "
              f"-> {'IDENTICAL' if mx == 0 else 'DIFFERENT'}")
