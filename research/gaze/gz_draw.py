import cv2, numpy as np, json, os, sys, math

ROOT = "C:/Users/natha/Projects/boyd-clips"
res = json.load(open(ROOT + "/research/gaze/gz_raw.json", encoding="utf-8"))


def annotate(rec, top_n=2):
    bgr = cv2.imread(rec["path"]).copy()
    H, W = bgr.shape[:2]
    t = rec.get("text")
    if t:
        x0, y0, x1, y1 = t["bbox"]
        cv2.rectangle(bgr, (x0, y0), (x1, y1), (255, 0, 255), 3)
        cv2.putText(bgr, "TEXT cx=%.2f" % t["cx"], (x0, max(20, y0 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
    for i, f in enumerate(rec["faces"][:top_n]):
        x, y, w, h = int(f["x"]), int(f["y"]), int(f["w"]), int(f["h"])
        col = (0, 255, 0) if i == 0 else (0, 200, 255)
        cv2.rectangle(bgr, (x, y), (x + w, y + h), col, 3)
        for j, (lx, ly) in enumerate(f["lm"]):
            cv2.circle(bgr, (int(lx), int(ly)), 4, (0, 0, 255) if j == 2 else (255, 255, 0), -1)
        ex = f["eyemid_x"] * W
        ey = f["eyemid_y"] * H
        nd = f["nose_dev"]
        L = max(60, 2.2 * w)
        # gaze arrow: +nose_dev means nose sits to image-RIGHT of eye midpoint -> head turned image-right
        dx = np.sign(nd) * L * min(1.0, abs(nd) / 0.45)
        cv2.arrowedLine(bgr, (int(ex), int(ey)), (int(ex + dx), int(ey)), (0, 0, 255), 5, tipLength=0.3)
        lbl = "nd%+.2f as%+.2f pnp%+.0f h%.2f cx%.2f" % (nd, f["asym"], f["pnp_yaw"] or 0, f["hfrac"], f["cx"])
        cv2.putText(bgr, lbl, (max(2, x), min(H - 6, y + h + 26)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 5)
        cv2.putText(bgr, lbl, (max(2, x), min(H - 6, y + h + 26)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
        p = f.get("profile") or {}
        cv2.putText(bgr, "prof o%d f%d" % (p.get("orig", 0), p.get("flipped", 0)),
                    (max(2, x), max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        cv2.putText(bgr, "prof o%d f%d" % (p.get("orig", 0), p.get("flipped", 0)),
                    (max(2, x), max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(bgr, rec["file"][:46], (8, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
    cv2.putText(bgr, rec["file"][:46], (8, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    return bgr


def sheet(recs, out, cols=3, cellw=620):
    tiles = []
    for r in recs:
        im = annotate(r)
        s = cellw / im.shape[1]
        tiles.append(cv2.resize(im, (cellw, int(im.shape[0] * s))))
    ch = max(t.shape[0] for t in tiles)
    rows = []
    for i in range(0, len(tiles), cols):
        chunk = tiles[i:i + cols]
        chunk = [cv2.copyMakeBorder(t, 0, ch - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20)) for t in chunk]
        while len(chunk) < cols:
            chunk.append(np.full((ch, cellw, 3), 20, np.uint8))
        rows.append(np.hstack(chunk))
    cv2.imwrite(out, np.vstack(rows))
    print("WROTE", out)


if __name__ == "__main__":
    comp = [r for r in res if r["file"][0].isdigit()]
    ct = [r for r in res if r["file"].startswith(("top_", "bot_"))]
    ours = [r for r in res if r not in comp and r not in ct]
    sheet(comp, ROOT + "/research/gaze/SHEET_competitor.png")
    sheet([r for r in ct if r["file"].startswith("top_")], ROOT + "/research/gaze/SHEET_ct_top.png")
    sheet([r for r in ct if r["file"].startswith("bot_")], ROOT + "/research/gaze/SHEET_ct_bot.png")
    sheet(ours, ROOT + "/research/gaze/SHEET_ours.png")
