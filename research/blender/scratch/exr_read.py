import bpy

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def l2s(c):
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


tgt = tuple(s2l(int("D42B2B"[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
print("brand red, LINEAR reference :", tuple(round(v, 6) for v in tgt))
print()

img = bpy.data.images.load(OUT + r"\alpha_half.exr")
img.colorspace_settings.name = 'Linear Rec.709'
w, h = img.size
px = list(img.pixels)
i = ((h // 2) * w + (w // 2)) * 4
r, g, b, a = px[i:i + 4]
print("EXR centre pixel (raw float):")
print("   R=%.6f G=%.6f B=%.6f A=%.6f" % (r, g, b, a))
print()
print("   R/A = %.6f   <- if this equals the linear reference, EXR is PREMULTIPLIED" % (r / a if a else 0))
print("   R   = %.6f   <- if this equals the linear reference, EXR is STRAIGHT" % r)
print()
if abs(r - tgt[0]) < 1e-4:
    print("   VERDICT: EXR alpha is STRAIGHT (unassociated)")
elif abs(r / a - tgt[0]) < 1e-3:
    print("   VERDICT: EXR alpha is PREMULTIPLIED (associated)")
else:
    print("   VERDICT: neither cleanly - r=%.6f r/a=%.6f ref=%.6f" % (r, r / a, tgt[0]))

print()
print("=== where did alpha=0.5 go? ===")
print("   film alpha actually rendered:", round(a, 6), " (Mix Shader factor was 0.5)")
print("   8-bit encode of that alpha  :", round(a * 255))
print("   sRGB-encoded alpha would be :", round(l2s(a) * 255))
