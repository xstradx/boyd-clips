"""v2: fix the overflow proven by v1, and derive the hard limits.

v1 failure (rendered, looked at): logo at 900px wide -> 344px tall + 96px top pad = 440px
in a 423px-tall safe area. Mark got clipped on mobile; wordmark+tagline fell outside
the safe band entirely.
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT  = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
FONT = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\BebasNeue-Regular.ttf"
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"

W, H = 2560, 1440
BG, INK, RED = (0x15,0x18,0x1D), (0xF2,0xEE,0xE3), (0xD0,0x2D,0x2E)
def mix(a,t): return tuple(int(round(BG[i]+t*(a[i]-BG[i]))) for i in range(3))
HAIR_F, HAIR, TICK = mix(INK,0.05), mix(INK,0.08), mix(INK,0.22)
MUTED = mix(INK, 0.55)

SAFE_W, SAFE_H = 1546, 423
sx0, sy0 = (W-SAFE_W)//2, (H-SAFE_H)//2
sx1, sy1 = sx0+SAFE_W, sy0+SAFE_H
tx0, tx1 = (W-1855)//2, (W-1855)//2+1855

# ---- legibility floor -------------------------------------------------------
MOBILE_CSS = 412                      # phone renders the 1546-wide crop at ~412 CSS px
S = MOBILE_CSS / SAFE_W
print(f"mobile scale factor = {MOBILE_CSS}/{SAFE_W} = {S:.4f}")
for px in (40, 53, 64, 92, 120):
    print(f"  {px:3d}px on canvas -> {px*S:5.1f} CSS px on phone"
          f"{'   ILLEGIBLE' if px*S < 12 else '   ok' if px*S >= 14 else '   marginal'}")
print(f"  -> floor for legible type in the safe area = {12/S:.0f}px canvas (12 CSS px),")
print(f"     comfortable = {14/S:.0f}px canvas\n")

# ---- vertical budget --------------------------------------------------------
logo0 = Image.open(LOGO).convert("RGBA")
AR = logo0.width / logo0.height
budget = [("top pad",40), ("mark",196), ("gap",26), ("wordmark cap",74),
          ("gap",18), ("tagline cap",56), ("bottom pad",13)]
tot = sum(v for _, v in budget)
print(f"safe-area vertical budget ({SAFE_H}px available):")
for n, v in budget: print(f"   {n:14s} {v:4d}px")
print(f"   {'TOTAL':14s} {tot:4d}px  -> {'FITS' if tot <= SAFE_H else 'OVERFLOW'}")
mark_h = 196
mark_w = int(mark_h * AR)
print(f"   mark at {mark_h}px tall -> {mark_w}px wide "
      f"({100*mark_w/SAFE_W:.1f}% of safe width, aspect {AR:.3f})\n")

img = Image.new("RGB",(W,H),BG); d = ImageDraw.Draw(img)
LW = 3   # authored 3px == ~1.2px after YouTube's ~2.4x desktop downscale

# ---- edge treatment: ALL detail lives OUTSIDE the safe area ----------------
d.line([0, sy0, W, sy0], fill=HAIR, width=LW)
d.line([0, sy1, W, sy1], fill=HAIR, width=LW)

# corner marks sit on the safe boundary but open OUTWARD, into the gutter
L = 52
for cx, cy, dx, dy in [(sx0,sy0,-1,-1),(sx1,sy0,1,-1),(sx0,sy1,-1,1),(sx1,sy1,1,1)]:
    d.line([cx, cy, cx+dx*L, cy], fill=TICK, width=LW)
    d.line([cx, cy, cx, cy+dy*L], fill=TICK, width=LW)

# tick strip lives in the TV-only band ABOVE the top rule, where there is room
for i in range(41):
    x = int(sx0 + i*(SAFE_W/40))
    h = 14 if i % 5 else 30
    d.line([x, sy0-8, x, sy0-8-h], fill=HAIR_F if i % 5 else HAIR, width=2)

# tablet-boundary marks, in the tablet gutter only
for x in (tx0, tx1):
    d.line([x, sy0, x, sy0+26], fill=HAIR, width=LW)
    d.line([x, sy1-26, x, sy1], fill=HAIR, width=LW)

# ONE red element besides the star: a rule segment, not a stray tick.
# 1/8 of the safe width, sitting on the top rule, aligned to the safe left edge.
d.line([sx0, sy0, sx0 + SAFE_W//8, sy0], fill=RED, width=LW+1)

# outer frame, faintest tier, TV only
d.rectangle([64,64,W-65,H-65], outline=HAIR_F, width=LW)

# ---- content ---------------------------------------------------------------
logo = logo0.resize((mark_w, mark_h), Image.LANCZOS)
y = sy0 + 40
img.paste(logo, (sx0+(SAFE_W-mark_w)//2, y), logo)
y += mark_h + 26
def centred(t, f, yy, fill):
    bb = d.textbbox((0,0), t, font=f)
    d.text((sx0+(SAFE_W-(bb[2]-bb[0]))//2-bb[0], yy), t, font=f, fill=fill)
centred("TEXAS TRIAL TRACKER", ImageFont.truetype(FONT, 96), y, INK)
y += 74 + 18
centred("187TH DISTRICT COURT  ·  BEXAR COUNTY  ·  NEW CASES DAILY",
        ImageFont.truetype(FONT, 72), y, MUTED)

img.save(os.path.join(OUT,"edge_v2_2560x1440.png"))
for k,(a,b,c,e),rw in [("mobile",(sx0,sy0,sx1,sy1),412),
                       ("desktop",(0,sy0,W,sy1),1060),
                       ("tv",(0,0,W,H),1280)]:
    cr = img.crop((a,b,c,e)); rw2 = rw
    cr = cr.resize((rw2, max(1,int(cr.height*rw2/cr.width))), Image.LANCZOS)
    cr.save(os.path.join(OUT,f"edge_v2_{k}.png"))
    print(f"wrote edge_v2_{k}.png -> {cr.size}")
