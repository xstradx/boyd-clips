"""Map Linear.app's measured hairline ladder onto the TTT ground (#15181D / ink #F2EEE3).
Linear values measured live from https://linear.app on 2026-08-11 via Playwright
(computed styles + :root custom properties). Ground there is rgb(8,9,10) = #08090A.
"""
def lin(c):
    c /= 255.0
    return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def lum(rgb):
    r,g,b = (lin(v) for v in rgb)
    return 0.2126*r + 0.7152*g + 0.0722*b
def ratio(a,b):
    la,lb = lum(a),lum(b); hi,lo = max(la,lb),min(la,lb)
    return (hi+0.05)/(lo+0.05)
def hx(c): return "#%02X%02X%02X" % tuple(int(round(v)) for v in c)
def unhex(s):
    s = s.lstrip('#'); return tuple(int(s[i:i+2],16) for i in (0,2,4))

LINEAR_BG = unhex("08090A")
print("=== Linear.app measured line/border tokens vs its own #08090A ground ===")
for name, h in [
    ("--color-line-tint",        "141516"),
    ("--color-line-quaternary",  "141515"),
    ("--color-line-tertiary",    "18191A"),
    ("--color-line-secondary",   "202122"),
    ("--color-border-primary",   "23252A"),
    ("--color-border-secondary", "34343A"),
    ("--color-line-primary",     "37393A"),
    ("--color-border-tertiary",  "3E3E44"),
]:
    c = unhex(h)
    print(f"  {name:26s} #{h}  contrast vs ground = {ratio(c, LINEAR_BG):.3f}:1")

print("\n  most-used rendered borders (count from live DOM):")
for a, n in [(0.05, 220), (0.08, 73), (0.10, 12), (0.12, 4)]:
    c = [LINEAR_BG[i] + a*(255-LINEAR_BG[i]) for i in range(3)]
    print(f"    1px rgba(255,255,255,{a:.2f})  x{n:<4} -> {hx(c)}  contrast = {ratio(c, LINEAR_BG):.3f}:1")

print("\n=== Same ladder rebuilt on the TTT ground, using INK not pure white ===")
BG  = unhex("15181D")
INK = unhex("F2EEE3")
print(f"  ground #15181D, ink #F2EEE3")
for a in (0.05, 0.08, 0.10, 0.12, 0.16, 0.22, 0.30):
    c = [BG[i] + a*(INK[i]-BG[i]) for i in range(3)]
    r = ratio(c, BG)
    note = ""
    if 0.045 <= a <= 0.09: note = "  <- Linear's working range for structural hairlines"
    print(f"    ink @ {a*100:4.0f}%  -> {hx(c)}   contrast vs bg = {r:.3f}:1{note}")

print("\n=== Red used as a hairline / tick rather than a fill ===")
RED = unhex("D02D2E")
for a in (1.0, 0.55, 0.30):
    c = [BG[i] + a*(RED[i]-BG[i]) for i in range(3)]
    print(f"    red @ {a*100:4.0f}% -> {hx(c)}   contrast vs bg = {ratio(c,BG):.2f}:1")

print("\n=== Hairline weight at banner scale ===")
for w_css in (1, 2, 3):
    print(f"  {w_css}px on a 1546-wide safe area = {w_css/1546*100:.3f}% of safe width; "
          f"on the 2560 canvas = {w_css/2560*100:.3f}%")
print("  NOTE: a 2560x1440 banner is displayed on desktop at roughly 1060-1280 CSS px wide,")
print("  i.e. downscaled ~2.0-2.4x. A 1px line authored at 2560 renders as ~0.4-0.5px ->")
print("  it will alias/shimmer. Author edge rules at 2-3px on the 2560 canvas so they")
print("  land on ~1px after YouTube's downscale.")
for w in (2, 3, 4):
    print(f"    {w}px authored -> {w/2.42:.2f}px at 1060px-wide desktop render; "
          f"{w/2.0:.2f}px at 1280px-wide render")
