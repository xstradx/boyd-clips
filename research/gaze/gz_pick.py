# What gaze is ACTUALLY AVAILABLE in each hearing, and what did we pick?
# Denser sampling of the defendant tile (the frame we actually get to choose),
# plus a pitch proxy for the judge ("eyes level and directed", never looking down).
import cv2, numpy as np, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gz_measure import detect_faces, face_metrics

ROOT = "C:/Users/natha/Projects/boyd-clips"
HEAR = {
    "CARTHIEF": dict(mp4=ROOT + "/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4",
                     judge=(612, 338, 18, 190), defendant=(620, 338, 644, 190)),
    "SANCHEZ":  dict(mp4=ROOT + "/work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4",
                     judge=(468, 348, 726, 6), defendant=(628, 348, 6, 6)),
    "OFFERUP":  dict(mp4=ROOT + "/work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4",
                     judge=(628, 348, 646, 186), defendant=(628, 348, 6, 186)),
}
N = 200


def dur(m):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", m], capture_output=True, text=True).stdout.strip())


def grab(mp4, t):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", mp4, "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    return cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR) if p.stdout else None


res = {}
for name, cfg in HEAR.items():
    D = dur(cfg["mp4"])
    res[name] = {}
    for role in ("defendant", "judge"):
        w, h, x, y = cfg[role]
        rows = []
        for i in range(N):
            t = D * (i + 0.5) / N
            fr = grab(cfg["mp4"], t)
            if fr is None: continue
            tile = fr[y:y + h, x:x + w]
            s = 640.0 / tile.shape[1]
            big = cv2.resize(tile, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
            fs = detect_faces(big, score=0.6)
            if not fs: continue
            fs = sorted(fs, key=lambda r: -r[3])
            m = face_metrics(fs[0], big.shape[0], big.shape[1])
            rows.append(dict(t=t, nd=m["nose_dev"], nose_v=m["nose_v"], roll=abs(m["roll_img"]),
                             cx=m["cx"], cy=m["cy"], h=m["hfrac"], score=m["score"]))
        nd = np.array([r["nd"] for r in rows]); nv = np.array([r["nose_v"] for r in rows])
        res[name][role] = dict(n=len(rows), rows=rows)
        print("%-9s %-9s n=%3d | nd  p10 %+.3f  med %+.3f  p90 %+.3f  max %+.3f  min %+.3f"
              % (name, role, len(rows), *np.percentile(nd, [10, 50, 90]), nd.max(), nd.min()), flush=True)
        print("%-9s %-9s        | nose_v (pitch proxy, LOWER = looking DOWN)  p10 %+.3f med %+.3f p90 %+.3f"
              % ("", "", *np.percentile(nv, [10, 50, 90])), flush=True)
        if role == "defendant":
            best = sorted(rows, key=lambda r: -r["nd"])[:6]
            print("           best-turned-toward-a-right-side-judge frames: " +
                  ", ".join("t=%.1fs nd=%+.3f" % (b["t"], b["nd"]) for b in best), flush=True)
json.dump(res, open(ROOT + "/research/gaze/gz_pick.json", "w"), indent=1)

# contact sheet of the best available defendant frames vs a median one
tiles = []
for name, cfg in HEAR.items():
    w, h, x, y = cfg["defendant"]
    rows = sorted(res[name]["defendant"]["rows"], key=lambda r: -r["nd"])
    med = sorted(res[name]["defendant"]["rows"], key=lambda r: r["nd"])[len(rows) // 2]
    for tag, r in (("BEST", rows[0]), ("2nd", rows[1]), ("3rd", rows[2]), ("MEDIAN", med)):
        fr = grab(cfg["mp4"], r["t"])
        tl = fr[y:y + h, x:x + w].copy()
        tl = cv2.resize(tl, (420, int(420 * tl.shape[0] / tl.shape[1])))
        cv2.putText(tl, "%s %s nd=%+.3f t=%.1f" % (name, tag, r["nd"], r["t"]),
                    (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
        cv2.putText(tl, "%s %s nd=%+.3f t=%.1f" % (name, tag, r["nd"], r["t"]),
                    (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
        tiles.append(tl)
ch = max(t.shape[0] for t in tiles)
rws = []
for i in range(0, len(tiles), 4):
    ck = [cv2.copyMakeBorder(t, 0, ch - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20)) for t in tiles[i:i + 4]]
    rws.append(np.hstack(ck))
cv2.imwrite(ROOT + "/research/gaze/SHEET_defendant_gaze.png", np.vstack(rws))
print("WROTE SHEET_defendant_gaze.png")
