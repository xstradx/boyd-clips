"""Build a 2560x1440 TTT banner with the edge treatment set to the MEASURED values
(hairlines at ink 5-8%, one 1px-equivalent weight, corner marks, one red tick),
then emit the four device crops so the result can actually be looked at.

Ground truth used:
  - device crops: TV 2560x1440 / desktop 2560x423 / tablet 1855x423 / mobile 1546x423
  - hairline alpha ladder: measured live from linear.app (1px rgba(255,255,255,.05) x220,
    .08 x73) -> rebuilt here against ink #F2EEE3 over bg #15181D
  - mark shear: measured 9.08 deg from logo_transparent.png (stems), crossbars 0.00 deg
"""
from PIL import Image, ImageDraw, ImageFont
import os, math

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
os.makedirs(OUT, exist_ok=True)
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\BebasNeue-Regular.ttf"
LOGO = r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\logo_transparent.png"

W, H = 2560, 1440
BG   = (0x15, 0x18, 0x1D)
INK  = (0xF2, 0xEE, 0xE3)
RED  = (0xD0, 0x2D, 0x2E)

def mix(a, t):            # ink/red over bg at alpha t
    return tuple(int(round(BG[i] + t*(a[i]-BG[i]))) for i in range(3))

HAIR   = mix(INK, 0.08)   # structural hairline  -> #27292D, 1.22:1
HAIR_F = mix(INK, 0.05)   # faintest tier        -> #202327, 1.13:1
TICK   = mix(INK, 0.22)   # corner marks         -> #464749, 1.91:1
MUTED  = (0xA8, 0xA4, 0x9C)

# device crop rects (left, top, right, bottom)
SAFE_W, SAFE_H = 1546, 423
TAB_W, DESK_W  = 1855, 2560
cy0, cy1 = (H - SAFE_H)//2, (H - SAFE_H)//2 + SAFE_H
ZONES = {
    "mobile":  ((W-SAFE_W)//2, cy0, (W-SAFE_W)//2 + SAFE_W, cy1),
    "tablet":  ((W-TAB_W)//2,  cy0, (W-TAB_W)//2  + TAB_W,  cy1),
    "desktop": (0,             cy0, DESK_W,                 cy1),
    "tv":      (0, 0, W, H),
}
for k, v in ZONES.items():
    print(f"{k:8s} crop = x {v[0]}..{v[2]}  y {v[1]}..{v[3]}   ({v[2]-v[0]}x{v[3]-v[1]})")

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

sx0, sy0, sx1, sy1 = ZONES["mobile"]
tx0, _, tx1, _     = ZONES["tablet"]

# --- edge treatment -------------------------------------------------------
# 3px authored == ~1px after YouTube's ~2.0-2.4x downscale on desktop
LW = 3
M  = 64                                   # margin from canvas edge (TV-only band)

# 1. outer frame hairline, faintest tier, TV-only territory
d.rectangle([M, M, W-M-1, H-M-1], outline=HAIR_F, width=LW)

# 2. the two horizontal rules that mark the desktop strip -> structural hairline
d.line([0, sy0, W, sy0], fill=HAIR, width=LW)
d.line([0, sy1, W, sy1], fill=HAIR, width=LW)

# 3. corner registration marks at the SAFE-AREA corners (crop marks, not decoration:
#    they annotate the real boundary). Length = 48px, gap = 0.
L = 48
for (cx, cy, dx, dy) in [(sx0,sy0,1,1), (sx1,sy0,-1,1), (sx0,sy1,1,-1), (sx1,sy1,-1,-1)]:
    d.line([cx, cy, cx + dx*L, cy], fill=TICK, width=LW)
    d.line([cx, cy, cx, cy + dy*L], fill=TICK, width=LW)

# 4. ONE red tick - the only red that is not the star. Left edge of safe area, top rule.
d.line([sx0, sy0-18, sx0, sy0+18], fill=RED, width=LW+2)

# 5. tablet-boundary ticks: tiny, faint, only in the tablet gutter
for x in (tx0, tx1):
    d.line([x, sy0, x, sy0+22], fill=HAIR, width=LW)
    d.line([x, sy1-22, x, sy1], fill=HAIR, width=LW)

# 6. a measured tick-strip along the bottom rule (ticker motif), inside desktop band only
f_small = ImageFont.truetype(FONT, 30)
for i in range(0, 41):
    x = int(sx0 + i*(SAFE_W/40))
    h = 16 if i % 5 else 28
    d.line([x, sy1, x, sy1 - h], fill=HAIR_F if i % 5 else HAIR, width=2)

# --- content in the safe area --------------------------------------------
logo = Image.open(LOGO).convert("RGBA")
lw = 900
logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
lx = sx0 + (SAFE_W - lw)//2
ly = sy0 + 96
img.paste(logo, (lx, ly), logo)

f_word = ImageFont.truetype(FONT, 92)
f_tag  = ImageFont.truetype(FONT, 40)
def centred(text, font, y, fill):
    bb = d.textbbox((0,0), text, font=font)
    d.text((sx0 + (SAFE_W - (bb[2]-bb[0]))//2 - bb[0], y), text, font=font, fill=fill)
centred("TEXAS TRIAL TRACKER", f_word, ly + logo.height + 30, INK)
centred("187TH DISTRICT COURT  ·  BEXAR COUNTY  ·  NEW CASES DAILY",
        f_tag, ly + logo.height + 142, MUTED)

img.save(os.path.join(OUT, "edge_test_2560x1440.png"))

# emit crops, each downscaled to the width it is actually SEEN at
render_w = {"mobile": 412, "tablet": 780, "desktop": 1060, "tv": 1280}
for k, box in ZONES.items():
    c = img.crop(box)
    rw = render_w[k]
    c2 = c.resize((rw, max(1, int(c.height * rw / c.width))), Image.LANCZOS)
    c2.save(os.path.join(OUT, f"edge_test_{k}.png"))
    print(f"wrote edge_test_{k}.png  {c.size} -> {c2.size}")

print("\nhairline colours actually used:")
for n, c in [("HAIR_F ink@5%", HAIR_F), ("HAIR ink@8%", HAIR), ("TICK ink@22%", TICK), ("RED", RED)]:
    print(f"  {n:16s} #%02X%02X%02X" % c)
