# Per-GLYPH text/face collision. A union bbox spans inter-word gaps and overstates the hit;
# what matters is whether an actual letter lands on a face.
import cv2, numpy as np, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gz_text import glyph_mask, stroked_glyphs

ROOT = "C:/Users/natha/Projects/boyd-clips"
raw = json.load(open(ROOT + "/research/gaze/gz_raw2.json", encoding="utf-8"))


def grp(f):
    if f.startswith("top_"): return "CT_TOP"
    if f.startswith("bot_"): return "CT_BOT"
    if f[0].isdigit(): return "AUDIT"
    return "OURS"


out = {}
for rec in raw:
    bgr = cv2.imread(rec["path"])
    H, W = bgr.shape[:2]
    gl = []
    for nm, mk in glyph_mask(bgr).items():
        gl += stroked_glyphs(bgr, mk, H, W)
    if len(gl) < 4:
        continue
    fs = [f for f in rec["faces"] if f["hfrac"] >= 0.12 and f["score"] >= 0.6]
    faces = np.zeros((H, W), np.uint8)
    for F in fs:
        cv2.rectangle(faces, (int(F["x"]), int(F["y"])),
                      (int(F["x"] + F["w"]), int(F["y"] + F["h"])), 1, -1)
    tm = np.zeros((H, W), np.uint8)
    for x, y, w, h, a, d in gl:
        cv2.rectangle(tm, (x, y), (x + w, y + h), 1, -1)
    tot = int(tm.sum())
    hit = int((tm & faces).sum())
    # how far is the nearest glyph from the nearest face box, horizontally?
    gaps = []
    for F in fs:
        fx0, fx1 = F["x"], F["x"] + F["w"]
        for x, y, w, h, a, d in gl:
            if y + h < F["y"] or y > F["y"] + F["h"]:
                continue                      # not on the same rows
            if x + w <= fx0: gaps.append((fx0 - (x + w)) / W)
            elif x >= fx1:   gaps.append((x - fx1) / W)
            else:            gaps.append(0.0)
    o = dict(grp=grp(rec["file"]), glyph_px=tot, on_face_px=hit,
             frac_on_face=hit / tot if tot else 0.0,
             min_gap_W=float(min(gaps)) if gaps else None,
             n_faces=len(fs))
    out[rec["file"]] = o
    print("%-7s %-44s glyph %6d px  on-face %6d (%5.1f%%)  min horiz gap %s" %
          (o["grp"], rec["file"][:44], tot, hit, 100 * o["frac_on_face"],
           ("%.3f W" % o["min_gap_W"]) if o["min_gap_W"] is not None else "-"), flush=True)

print()
print("=" * 96)
for g in ("AUDIT", "CT_TOP", "CT_BOT", "OURS"):
    v = [o for o in out.values() if o["grp"] == g]
    if not v: continue
    fr = np.array([o["frac_on_face"] for o in v])
    gaps = np.array([o["min_gap_W"] for o in v if o["min_gap_W"] is not None])
    print("%-7s n=%2d  glyph-pixels-on-a-face: median %.1f%%  mean %.1f%%  ZERO in %d/%d  |  min horiz gap median %.3f W"
          % (g, len(v), 100 * np.median(fr), 100 * fr.mean(),
             int((fr < 0.005).sum()), len(v), np.median(gaps) if len(gaps) else float("nan")))
json.dump(out, open(ROOT + "/research/gaze/gz_collide.json", "w"), indent=1)
