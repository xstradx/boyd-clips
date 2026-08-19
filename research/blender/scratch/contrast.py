"""WCAG 2.x relative-luminance / contrast ratios for the TTT palette,
plus the ink-over-bg alpha ladder. Formula: WCAG 2.2 sec. 'relative luminance'
https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
"""
def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def lum(rgb):
    r, g, b = (srgb_to_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

def hx(c):
    return "#%02X%02X%02X" % tuple(int(round(v)) for v in c)

BG    = (0x15, 0x18, 0x1D)
INK   = (0xF2, 0xEE, 0xE3)
RED_A = (0xD0, 0x2D, 0x2E)   # measured in logo_transparent.png + star everywhere
RED_B = (0xD4, 0x2B, 0x2B)   # stated brand hex, used for the rule in banner_04
MUTED = (0xA8, 0xA4, 0x9C)   # measured in banner_03 tagline

pairs = [
    ("ink   on bg", INK, BG),
    ("muted on bg", MUTED, BG),
    ("redA  on bg", RED_A, BG),
    ("redB  on bg", RED_B, BG),
    ("red   on ink", RED_A, INK),
    ("redA vs redB", RED_A, RED_B),
]
print("WCAG contrast ratios (AA body text needs 4.5:1, AA large >=24px/18.7px-bold needs 3:1)")
for name, a, b in pairs:
    r = ratio(a, b)
    verdict = "AAA" if r >= 7 else "AA" if r >= 4.5 else "AA-large" if r >= 3 else "FAIL"
    print(f"  {name:14s} {hx(a)} / {hx(b)}  = {r:6.2f}:1   {verdict}")

print(f"\nrelative luminance: bg={lum(BG):.5f} ink={lum(INK):.5f} "
      f"redA={lum(RED_A):.5f} muted={lum(MUTED):.5f}")

# Is MUTED just ink composited over bg? solve per channel
print("\nis #A8A49C == ink over bg at alpha a?  solve per channel:")
for i, ch in enumerate("RGB"):
    a = (MUTED[i] - BG[i]) / (INK[i] - BG[i])
    print(f"   {ch}: a = {a:.4f}")
mean_a = sum((MUTED[i] - BG[i]) / (INK[i] - BG[i]) for i in range(3)) / 3
print(f"   mean alpha = {mean_a:.4f}  -> reconstructed = "
      f"{hx([BG[i] + mean_a*(INK[i]-BG[i]) for i in range(3)])} vs actual {hx(MUTED)}")

print("\nink-over-bg alpha ladder (a disciplined tone ramp from TWO colours):")
for a in (1.00, 0.72, 0.55, 0.40, 0.28, 0.18, 0.12, 0.08, 0.05):
    col = [BG[i] + a * (INK[i] - BG[i]) for i in range(3)]
    print(f"   ink @ {a*100:5.1f}%  -> {hx(col)}   contrast vs bg = {ratio(col, BG):5.2f}:1")

print("\nred-over-bg alpha ladder:")
for a in (1.00, 0.60, 0.35, 0.20, 0.12):
    col = [BG[i] + a * (RED_A[i] - BG[i]) for i in range(3)]
    print(f"   red @ {a*100:5.1f}%  -> {hx(col)}   contrast vs bg = {ratio(col, BG):5.2f}:1")
