# -*- coding: utf-8 -*-
"""Group statistics: top_ (winners) vs bot_ (losers), @courtroomtime, one channel.
Machine measurements from ct_measure3.json + eye-coded categoricals verified by
reading all 25 originals at full resolution and all 25 debug overlays."""
import io, json, os
import numpy as np
from scipy import stats

OUT = r"C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime/_ctmeas"
rows = json.load(io.open(os.path.join(OUT, "ct_measure3.json"), encoding="utf-8"))
by = {r["file"]: r for r in rows}

# ---- eye-coded, from viewing every original at 1280x720 and every debug overlay ----
# construction : torn2 | hard2 | bleed (full-bleed, subject composited) | grid3
# boyd         : real_still | real_zoom | synthetic | none
# rightsrc     : real | ai   (source of the NON-Boyd hero imagery)
# arrow        : red | yellow | magenta | none
# stamp        : red rubber-stamp badge present
# textanchor   : bottom | top | centre
CODE = {
 "top_00891000_ERPX6JpX5OU": ("torn2", "real_still", "ai",   "red",     1, "bottom"),
 "top_00790000__-WRN7q01OY": ("torn2", "real_still", "ai",   "none",    0, "bottom"),
 "top_00553000_rcub_Jev9NE": ("bleed", "real_still", "real", "red",     0, "bottom"),
 "top_00529000_6Tp2eiBjGB8": ("bleed", "real_still", "ai",   "red",     0, "bottom"),
 "top_00379000_urZza-9kdP0": ("torn2", "real_still", "ai",   "red",     1, "bottom"),
 "top_00354000_ePdAxp1Zs8Y": ("torn2", "real_still", "ai",   "none",    1, "bottom"),
 "top_00335000_aH0fnO4w-dg": ("torn2", "real_still", "ai",   "none",    0, "bottom"),
 "top_00308000_lfAlCDsEQZ4": ("torn2", "real_still", "ai",   "none",    0, "bottom"),
 "top_00305000_8n5raFtKul8": ("hard2", "real_zoom",  "real", "magenta", 0, "bottom"),
 "top_00277000_k69GmELAgVw": ("torn2", "real_still", "ai",   "none",    0, "bottom"),
 "top_00241000_8lxIY35zb6Q": ("torn2", "real_zoom",  "ai",   "none",    0, "top"),
 "top_00233000_-iPnSFl434E": ("grid3", "real_zoom",  "real", "red",     0, "bottom"),
 "top_00214000__eMKRoRaE_w": ("torn2", "real_still", "ai",   "red",     1, "bottom"),
 "top_00209000_z05aWSTzw0k": ("torn2", "real_still", "ai",   "none",    0, "bottom"),
 "top_00204000_J3LdwHAZR2E": ("bleed", "real_still", "real", "red",     0, "bottom"),
 "bot_00001700_-YRHSSLanxk": ("torn2", "synthetic",  "ai",   "yellow",  0, "bottom"),
 "bot_00001500_gVVI_SdlsvA": ("torn2", "synthetic",  "ai",   "yellow",  0, "bottom"),
 "bot_00001300_rUJ__Sb3Y8w": ("torn2", "none",       "ai",   "red",     1, "bottom"),
 "bot_00001200_qlDoZCJs620": ("torn2", "real_still", "ai",   "none",    0, "bottom"),
 "bot_00001100_--Mpaln4jx8": ("bleed", "none",       "real", "yellow",  0, "top"),
 "bot_00001100_U204YIfp-rc": ("torn2", "real_still", "ai",   "red",     0, "bottom"),
 "bot_00001000_95HqsmyM-zI": ("bleed", "none",       "ai",   "red",     1, "bottom"),
 "bot_00000988_79nw7lP0jm0": ("torn2", "real_still", "ai",   "red",     1, "bottom"),
 "bot_00000749_RfF0ouKeE0w": ("torn2", "synthetic",  "real", "yellow",  0, "centre"),
 "bot_00000388_q1Fo7x_0ItI": ("hard2", "none",       "real", "yellow",  0, "centre"),
}
for r in rows:
    key = r["file"].replace("_maxresdefault.jpg", "")
    c = CODE[key]
    r["construction"], r["boyd"], r["rightsrc"], r["arrow"], r["stamp"], r["textanchor"] = c

TOP = [r for r in rows if r["grp"] == "top"]
BOT = [r for r in rows if r["grp"] == "bot"]
TOP.sort(key=lambda r: -r["views"]); BOT.sort(key=lambda r: -r["views"])


def cont(name, fn, fmt="%.3f"):
    a = [fn(r) for r in TOP]; b = [fn(r) for r in BOT]
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    # rank-biserial effect size
    rb = 2 * u / (len(a) * len(b)) - 1
    print("\n== %s ==" % name)
    print("  top n=%d  med=%s  mean=%s  [%s]" % (
        len(a), fmt % np.median(a), fmt % np.mean(a), " ".join(fmt % v for v in sorted(a))))
    print("  bot n=%d  med=%s  mean=%s  [%s]" % (
        len(b), fmt % np.median(b), fmt % np.mean(b), " ".join(fmt % v for v in sorted(b))))
    print("  MannWhitneyU=%.1f  p=%.4f  rank-biserial=%+.2f" % (u, p, rb))
    return p, rb


def binary(name, fn):
    a = sum(1 for r in TOP if fn(r)); b = sum(1 for r in BOT if fn(r))
    tbl = [[a, len(TOP) - a], [b, len(BOT) - b]]
    odds, p = stats.fisher_exact(tbl)
    print("\n== %s ==  top %d/%d (%.0f%%)   bot %d/%d (%.0f%%)   Fisher p=%.4f" % (
        name, a, len(TOP), 100.0 * a / len(TOP), b, len(BOT), 100.0 * b / len(BOT), p))
    for r in TOP + BOT:
        if fn(r): print("     hit: %-8s %8d  %s" % (r["grp"], r["views"], r["file"][:44]))
    return p


print("=" * 100)
print("PER-FILE TABLE  (cap/cy/ink are machine-measured; construction..anchor are eye-coded)")
print("=" * 100)
hdr = ("%-40s %-4s %8s %5s %4s %-6s %-11s %-5s %-8s %-6s %5s %5s %5s %5s %5s %5s %5s" %
       ("file", "grp", "views", "dur", "idx", "constr", "boyd", "src", "arrow", "anchor",
        "nln", "capX", "capM", "txtcy", "a020", "botY", "frm"))
print(hdr)
for r in TOP + BOT:
    tb = r["tbox"] or {}
    print("%-40s %-4s %8d %5d %4d %-6s %-11s %-5s %-8s %-6s %5d %5.3f %5.3f %5.2f %5.3f %5.3f %5.2f" % (
        r["file"].replace("_maxresdefault.jpg", "")[:40], r["grp"], r["views"], r["dur"], r["idx"],
        r["construction"], r["boyd"], r["rightsrc"], r["arrow"], r["textanchor"],
        r["nline"], r["capmax"], r["capmed"], tb.get("cyf", -1), tb.get("above020", -1),
        r["bars"]["bottom_yellow_hf"], r["border"]["yellow_lrt"]))

print("\n" + "=" * 100)
print("CONFOUND CHECK FIRST")
print("=" * 100)
cont("video duration (s)  <-- CONFOUND", lambda r: r["dur"], "%7.0f")
cont("channel position idx (lower = older upload)", lambda r: r["idx"], "%5.0f")

print("\n" + "=" * 100)
print("TEXT GEOMETRY")
print("=" * 100)
cont("largest text-line cap height / H", lambda r: r["capmax"])
cont("median text-line cap height / H", lambda r: r["capmed"])
cont("detected text lines", lambda r: r["nline"], "%3.0f")
cont("text-block vertical centroid (0=top,1=bottom)", lambda r: (r["tbox"] or {}).get("cyf", 0.0))
cont("frac of text pixels above y=0.20H", lambda r: (r["tbox"] or {}).get("above020", 0.0))
cont("frac of text pixels below y=0.60H", lambda r: (r["tbox"] or {}).get("below060", 0.0))
cont("text bbox area / frame", lambda r: (r["tbox"] or {}).get("boxf", 0.0))
cont("text bbox width / W", lambda r: (r["tbox"] or {}).get("x1f", 0.0) - (r["tbox"] or {}).get("x0f", 0.0))

print("\n" + "=" * 100)
print("PLATES, FRAMES, CALLOUTS")
print("=" * 100)
cont("bottom yellow text-plate height / H", lambda r: r["bars"]["bottom_yellow_hf"])
cont("yellow coverage of left/right/top 9px border", lambda r: r["border"]["yellow_lrt"])
cont("rows with >25%% red coverage / H (red name plate)", lambda r: r["bars"]["red_partial_hf"])
binary("yellow FRAME around whole image (border yellow_lrt > 0.30)",
       lambda r: r["border"]["yellow_lrt"] > 0.30)
binary("bottom yellow plate present (>=4% of H)", lambda r: r["bars"]["bottom_yellow_hf"] >= 0.04)
binary("red name-plate bar present", lambda r: r["bars"]["red_partial_hf"] >= 0.04)

print("\n" + "=" * 100)
print("COLOUR")
print("=" * 100)
cont("mean HSV saturation", lambda r: r["colour"]["sat"])
cont("mean HSV value", lambda r: r["colour"]["val"])
cont("clipped-highlight fraction (max(RGB)>=250)", lambda r: r["colour"]["clip250"])
cont("mean luma", lambda r: r["colour"]["lum"], "%6.1f")
cont("luma std dev", lambda r: r["colour"]["lum_sd"], "%6.1f")
cont("fraction of frame darker than luma 40", lambda r: r["colour"]["dark40"])

print("\n" + "=" * 100)
print("EYE-CODED CATEGORICALS")
print("=" * 100)
binary("REAL Judge Boyd in the frame (court still or Zoom tile)",
       lambda r: r["boyd"] in ("real_still", "real_zoom"))
binary("SYNTHETIC / re-rendered Boyd", lambda r: r["boyd"] == "synthetic")
binary("no Boyd at all", lambda r: r["boyd"] == "none")
binary("locked reusable real-Boyd court still (the cream-wall nameplate frame)",
       lambda r: r["boyd"] == "real_still")
binary("YELLOW arrow", lambda r: r["arrow"] == "yellow")
binary("RED/magenta arrow", lambda r: r["arrow"] in ("red", "magenta"))
binary("any arrow", lambda r: r["arrow"] != "none")
binary("red rubber-stamp badge", lambda r: r["stamp"] == 1)
binary("AI-generated hero imagery anywhere", lambda r: r["rightsrc"] == "ai")
binary("torn-paper 2-panel construction", lambda r: r["construction"] == "torn2")
binary("text anchored BOTTOM", lambda r: r["textanchor"] == "bottom")
binary("text NOT anchored bottom (top or centre)", lambda r: r["textanchor"] != "bottom")

print("\n" + "=" * 100)
print("TITLE (thumbmeta) vs TEXT BURNED INTO THE IMAGE")
print("=" * 100)
for r in TOP + BOT:
    print("%-4s %8d  %s" % (r["grp"], r["views"], (r["title"] or "").encode("ascii", "replace").decode()))
