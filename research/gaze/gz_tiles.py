# Measure the SOURCE Zoom tiles of the three hearings: which way does each person
# actually face, over the whole hearing, and how stable is it?
# This is the input the parametric layout has to read.
import cv2, numpy as np, json, os, subprocess, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gz_measure import detect_faces, face_metrics

ROOT = "C:/Users/natha/Projects/boyd-clips"

HEARINGS = {
    "CARTHIEF": dict(mp4=ROOT + "/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4",
                     judge=(612, 338, 18, 190), defendant=(620, 338, 644, 190)),
    "SANCHEZ":  dict(mp4=ROOT + "/work/3FMy2Kvu3UA/3FMy2Kvu3UA_h_3703_3683-4448.mp4",
                     judge=(468, 348, 726, 6), defendant=(628, 348, 6, 6)),
    "OFFERUP":  dict(mp4=ROOT + "/work/l19Ijva3Rsk/l19Ijva3Rsk_h_10570_10550-11137.mp4",
                     judge=(628, 348, 646, 186), defendant=(628, 348, 6, 186)),
}

N = 60   # frames sampled evenly across each hearing


def grab(mp4, t):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % t, "-i", mp4,
                        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True)
    if not p.stdout:
        return None
    return cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR)


def dur(mp4):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", mp4], capture_output=True, text=True)
    return float(p.stdout.strip())


out = {}
for name, cfg in HEARINGS.items():
    D = dur(cfg["mp4"])
    rec = {"dur": D, "tiles": {}}
    for role in ("judge", "defendant"):
        w, h, x, y = cfg[role]
        samples = []
        for i in range(N):
            t = D * (i + 0.5) / N
            fr = grab(cfg["mp4"], t)
            if fr is None:
                continue
            tile = fr[y:y + h, x:x + w]
            # upscale so YuNet sees a big face
            s = 640.0 / tile.shape[1]
            big = cv2.resize(tile, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
            fs = detect_faces(big, score=0.6)
            if not fs:
                samples.append(dict(t=t, found=False))
                continue
            fs = sorted(fs, key=lambda r: -r[3])
            m = face_metrics(fs[0], big.shape[0], big.shape[1])
            samples.append(dict(t=t, found=True, nd=m["nose_dev"], asym=m["asym"],
                                cx=m["cx"], cy=m["cy"], hfrac=m["hfrac"],
                                roll=m["roll_img"], nose_v=m["nose_v"],
                                iod_over_dv=m["iod_over_dv"]))
        got = [s for s in samples if s["found"]]
        nd = np.array([s["nd"] for s in got])
        rec["tiles"][role] = dict(
            crop=[w, h, x, y], tile_cx_in_frame=float((x + w / 2) / 1280.0),
            n=len(samples), n_found=len(got),
            nd_median=float(np.median(nd)) if len(nd) else None,
            nd_mean=float(nd.mean()) if len(nd) else None,
            nd_p10=float(np.percentile(nd, 10)) if len(nd) else None,
            nd_p90=float(np.percentile(nd, 90)) if len(nd) else None,
            nd_std=float(nd.std()) if len(nd) else None,
            frac_turned_right=float((nd > 0.08).mean()) if len(nd) else None,
            frac_turned_left=float((nd < -0.08).mean()) if len(nd) else None,
            frac_frontal=float((abs(nd) <= 0.08).mean()) if len(nd) else None,
            cx_median=float(np.median([s["cx"] for s in got])) if got else None,
            cy_median=float(np.median([s["cy"] for s in got])) if got else None,
            hfrac_median=float(np.median([s["hfrac"] for s in got])) if got else None,
            iod_over_dv_median=float(np.median([s["iod_over_dv"] for s in got])) if got else None,
            samples=samples,
        )
        t = rec["tiles"][role]
        print("%-9s %-9s tile_cx=%.3f  found %d/%d  nd med %+.3f (p10 %+.3f p90 %+.3f sd %.3f) "
              "| turned L %.0f%% R %.0f%% frontal %.0f%% | face h %.2f of tile" %
              (name, role, t["tile_cx_in_frame"], t["n_found"], t["n"],
               t["nd_median"] or 0, t["nd_p10"] or 0, t["nd_p90"] or 0, t["nd_std"] or 0,
               100 * (t["frac_turned_left"] or 0), 100 * (t["frac_turned_right"] or 0),
               100 * (t["frac_frontal"] or 0), t["hfrac_median"] or 0), flush=True)
    out[name] = rec

json.dump(out, open(ROOT + "/research/gaze/gz_tiles.json", "w"), indent=1)
print("WROTE gz_tiles.json")
