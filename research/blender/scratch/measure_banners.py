"""Audit the four banner variants: exact tones used, how many, and safe-area geometry."""
from PIL import Image
from collections import Counter
import os, math

D = r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand"
STATED = {"bg": (0x15, 0x18, 0x1D), "ink": (0xF2, 0xEE, 0xE3), "red": (0xD4, 0x2B, 0x2B)}

def hexs(c):
    return "#%02X%02X%02X" % c

def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

for fn in sorted(os.listdir(D)):
    if not fn.endswith(".png"):
        continue
    im = Image.open(os.path.join(D, fn)).convert("RGB")
    W, H = im.size
    # quantise to find distinct flat tones
    c = Counter(im.getdata())
    tot = W * H
    flats = [(col, n) for col, n in c.most_common(40) if n / tot > 0.0015]
    print(f"\n=== {fn}  {W}x{H} ===")
    for col, n in flats[:8]:
        tag = ""
        for k, v in STATED.items():
            d = dist(col, v)
            if d < 30:
                tag = f"  ~= stated {k} {hexs(v)} (dE_rgb={d:.1f})"
        print(f"   {hexs(col)}  {100*n/tot:6.2f}%{tag}")
    print(f"   distinct colours >0.15% of frame: {len(flats)}")

# exact red + bg in the logo file vs stated
im = Image.open(os.path.join(D, "logo_transparent.png")).convert("RGBA")
px = im.load()
reds = Counter()
for y in range(0, im.size[1], 2):
    for x in range(0, im.size[0], 2):
        r, g, b, a = px[x, y]
        if a > 250 and r > 120 and r - g > 60:
            reds[(r, g, b)] += 1
top_red = reds.most_common(1)[0]
print(f"\nlogo red actual = {hexs(top_red[0])}   stated = #D42B2B   "
      f"delta_rgb = {dist(top_red[0], STATED['red']):.1f}")
