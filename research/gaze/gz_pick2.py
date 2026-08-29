# CORRECTION to gz_pick.py: "largest face in the defendant tile" is not the defendant.
# Viewing the rendered sheet showed the top-nose_dev frames were the attorney or a bystander.
# Here: keep ALL faces per frame, cluster them by position across the hearing, and identify
# the defendant cluster as the most temporally persistent one nearest the tile centre.
import cv2, numpy as np, json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gz_measure import detect_faces, face_metrics

ROOT = "C:/Users/natha/Projects/boyd-clips"
HEAR = {
    "CARTHIEF": dict(mp4=ROOT + "/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4", d=(620, 338, 644, 190)),
    "SANCHEZ":  dict(mp4=ROOT + "/work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4", d=(628, 348, 6, 6)),
    "OFFERUP":  dict(mp4=ROOT + "/work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4", d=(628, 348, 6, 186)),
}
N = 140


def dur(m):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", m], capture_output=True, text=True).stdout.strip())


def grab(mp4, t):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", mp4, "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    return cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR) if p.stdout else None


out = {}
for name, cfg in HEAR.items():
    D = dur(cfg["mp4"])
    w, h, x, y = cfg["d"]
    obs = []
    for i in range(N):
        t = D * (i + 0.5) / N
        fr = grab(cfg["mp4"], t)
        if fr is None: continue
        tile = fr[y:y + h, x:x + w]
        s = 640.0 / tile.shape[1]
        big = cv2.resize(tile, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        for r in detect_faces(big, score=0.7):
            m = face_metrics(r, big.shape[0], big.shape[1])
            if m["hfrac"] < 0.10 or abs(m["nose_dev"]) > 0.9: continue
            m["t"] = t
            obs.append(m)
    # cluster by (cx, hfrac): a person standing at the podium keeps both roughly constant
    cl = []
    for o in sorted(obs, key=lambda o: -o["hfrac"]):
        hit = None
        for c in cl:
            if abs(c["cx"] - o["cx"]) < 0.06 and abs(np.log(c["h"] / o["hfrac"])) < 0.35:
                hit = c; break
        if hit:
            hit["m"].append(o)
            hit["cx"] = float(np.median([q["cx"] for q in hit["m"]]))
            hit["h"] = float(np.median([q["hfrac"] for q in hit["m"]]))
        else:
            cl.append(dict(cx=o["cx"], h=o["hfrac"], m=[o]))
    cl = [c for c in cl if len(c["m"]) >= 8]
    cl.sort(key=lambda c: -len(c["m"]))
    print("=" * 96)
    print("%s  tile %dx%d at (%d,%d)  clusters found (persistence = how many of %d sampled frames):" % (name, w, h, x, y, N))
    for c in cl[:6]:
        nd = np.array([q["nose_dev"] for q in c["m"]])
        print("   cx=%.3f  face_h=%.3f of tile  seen in %3d frames | nd med %+.3f  p10 %+.3f  p90 %+.3f  max %+.3f | turned toward a RIGHT-side judge (nd>+0.08): %.0f%%"
              % (c["cx"], c["h"], len(c["m"]), np.median(nd), np.percentile(nd, 10), np.percentile(nd, 90), nd.max(),
                 100 * (nd > 0.08).mean()))
    # the defendant = the persistent cluster nearest the tile centre
    cand = sorted([c for c in cl if len(c["m"]) >= max(12, 0.10 * N)], key=lambda c: abs(c["cx"] - 0.5))
    if cand:
        d = cand[0]
        nd = np.array([q["nose_dev"] for q in d["m"]])
        best = sorted(d["m"], key=lambda q: -q["nose_dev"])[:6]
        print("   -> DEFENDANT cluster: cx=%.3f  n=%d  nd med %+.3f  p90 %+.3f  max %+.3f" %
              (d["cx"], len(d["m"]), np.median(nd), np.percentile(nd, 90), nd.max()))
        print("      best frames: " + ", ".join("t=%.1fs nd=%+.3f" % (b["t"], b["nose_dev"]) for b in best))
        out[name] = dict(cx=d["cx"], n=len(d["m"]), nd_med=float(np.median(nd)),
                         nd_p90=float(np.percentile(nd, 90)), nd_max=float(nd.max()),
                         frac_toward=float((nd > 0.08).mean()),
                         best=[dict(t=b["t"], nd=b["nose_dev"], nose_v=b["nose_v"], cx=b["cx"], h=b["hfrac"]) for b in best],
                         crop=[w, h, x, y])
json.dump(out, open(ROOT + "/research/gaze/gz_pick2.json", "w"), indent=1)

tiles = []
for name, cfg in HEAR.items():
    if name not in out: continue
    w, h, x, y = cfg["d"]
    for k, b in enumerate(out[name]["best"][:4]):
        fr = grab(cfg["mp4"], b["t"])
        tl = cv2.resize(fr[y:y + h, x:x + w], (430, int(430 * h / w)))
        cv2.circle(tl, (int(b["cx"] * 430), int(0.42 * 430 * h / w)), 8, (0, 0, 255), 2)
        lab = "%s #%d nd=%+.3f t=%.1f" % (name, k + 1, b["nd"], b["t"])
        cv2.putText(tl, lab, (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
        cv2.putText(tl, lab, (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
        tiles.append(tl)
if tiles:
    ch = max(t.shape[0] for t in tiles)
    rws = []
    for i in range(0, len(tiles), 4):
        ck = [cv2.copyMakeBorder(t, 0, ch - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20)) for t in tiles[i:i + 4]]
        while len(ck) < 4: ck.append(np.full((ch, 430, 3), 20, np.uint8))
        rws.append(np.hstack(ck))
    cv2.imwrite(ROOT + "/research/gaze/SHEET_defendant_gaze2.png", np.vstack(rws))
    print("WROTE SHEET_defendant_gaze2.png")
