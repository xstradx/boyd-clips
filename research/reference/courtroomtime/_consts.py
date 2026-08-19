import cv2, numpy as np, json, os
D = os.path.dirname(os.path.abspath(__file__)); TH = os.path.join(D, "thumbs")
rows = json.load(open(os.path.join(D, "measurements.json"), encoding="utf-8"))
T = [r for r in rows if r["grp"] == "top"]; B = [r for r in rows if r["grp"] == "bot"]

def px(S, pred):
    acc = []
    for r in S:
        bgr = cv2.imread(os.path.join(TH, r["file"]))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        m = pred(hsv)
        if m.sum() > 500:
            acc.append(np.median(rgb[m], axis=0))
    a = np.array(acc)
    return a, np.median(a, axis=0)

def hx(c): return "#%02X%02X%02X" % tuple(int(round(v)) for v in c)

yel = lambda h: (h[:,:,0]>=18)&(h[:,:,0]<=36)&(h[:,:,1]>=170)&(h[:,:,2]>=190)
red = lambda h: ((h[:,:,0]<=6)|(h[:,:,0]>=172))&(h[:,:,1]>=180)&(h[:,:,2]>=120)
wht = lambda h: (h[:,:,1]<=25)&(h[:,:,2]>=240)
for nm, f in (("YELLOW", yel), ("RED", red), ("WHITE", wht)):
    a, m = px(T, f)
    print(f"{nm:7s} TOP n={len(a):2d} median {hx(m)}  per-image spread +/-{a.std(axis=0).round(1)}")
    a2, m2 = px(B, f); print(f"{'':7s} BOT n={len(a2):2d} median {hx(m2)}")

print("\n--- two-tier text geometry (winners, n=15) ---")
disp, banner = [], []
for r in T:
    rc = sorted(zip(r["row_cys"], [None]*len(r["row_cys"])))
for g, S in (("TOP", T), ("BOT", B)):
    caps_max = [r["cap_frac_max"] for r in S if r["cap_frac_max"]]
    caps_med = [r["cap_frac_med"] for r in S if r["cap_frac_med"]]
    print(g, "cap p95(display)", round(float(np.median(caps_max)),4),
          "  cap median(banner)", round(float(np.median(caps_med)),4),
          "  ratio", round(float(np.median(caps_max))/float(np.median(caps_med)),2))

print("\n--- solid banner bars: y-extent of every detected bar (winners) ---")
ally = []
for r in T:
    for a, b in r["bars"]["yellow"]: ally.append((a, b, "y"))
    for a, b in r["bars"]["red"]: ally.append((a, b, "r"))
    for a, b in r["bars"]["black"]: ally.append((a, b, "k"))
for c in ("y", "r", "k"):
    v = [(a, b) for a, b, k in ally if k == c]
    if v:
        tops = np.array([a for a, b in v]); hts = np.array([b-a for a, b in v])
        print(f"  {c}: n={len(v):2d} top_y med={np.median(tops):.3f} height med={np.median(hts):.3f} "
              f"frac_in_bottom_third={np.mean(tops>0.66):.2f}")

print("\n--- seam / panel split (winners vs losers) ---")
for g, S in (("TOP", T), ("BOT", B)):
    sx = np.array([r["seam_x_frac"] for r in S])
    print(g, "seam_x pct[10,25,50,75,90]", np.percentile(sx,[10,25,50,75,90]).round(3),
          " frac in 0.40-0.60:", round(float(((sx>=.40)&(sx<=.60)).mean()),2))

print("\n--- hero face box (largest face) ---")
for g, S in (("TOP", T), ("BOT", B)):
    fs = [(r["face_max_hfrac"], r["face_max_cx"], r["face_max_cy"]) for r in S if r["face_max_hfrac"]]
    a = np.array(fs)
    print(g, "n", len(fs), "h_frac pct[25,50,75]", np.percentile(a[:,0],[25,50,75]).round(3),
          "cx pct[25,50,75]", np.percentile(a[:,1],[25,50,75]).round(3),
          "cy med", round(float(np.median(a[:,2])),3))
    # second largest face (the antagonist)
    sec = []
    for r in S:
        f = sorted(r["faces"], key=lambda q: -q["h_frac"])
        if len(f) >= 2: sec.append((f[1]["h_frac"], f[1]["cx"]))
    if sec:
        s = np.array(sec); print("   2nd face h_frac med", round(float(np.median(s[:,0])),3),
                                 "cx med", round(float(np.median(s[:,1])),3))
