"""Render the rectified mouth crop the expression metric actually measures,
labelled with its own numbers, so the metric can be checked by eye."""
import cv2, numpy as np, json, math

ROOT = "C:/Users/natha/Projects/boyd-clips/research/reference"
OUT = ROOT + "/_facemeas"
R = json.load(open(OUT + "/metrics.json", encoding="utf-8"))


def pathof(r):
    return (ROOT + "/competitor/thumbs/" + r["file"]) if r["grp"] == "ATC" \
        else (ROOT + "/courtroomtime/thumbs/" + r["file"])


def crop(img, p, half):
    mmid = np.array(p["mmid"]); ev = np.array(p["ev"]); perp = np.array(p["perp"])
    N = 120
    u = np.linspace(-half, half, N); v = np.linspace(-half, half, N)
    UU, VV = np.meshgrid(u, v)
    X = mmid[0] + UU * ev[0] + VV * perp[0]
    Y = mmid[1] + UU * ev[1] + VV * perp[1]
    return cv2.remap(img, X.astype(np.float32), Y.astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def sheet(sub, name, cols=8):
    C = 150
    rows = (len(sub) + cols - 1) // cols
    canv = np.full((rows * (C + 34), cols * C, 3), 25, np.uint8)
    for i, (lab, im, g, t) in enumerate(sub):
        rr, cc = divmod(i, cols)
        canv[rr * (C + 34) + 34:(rr + 1) * (C + 34), cc * C:(cc + 1) * C] = cv2.resize(im, (C, C))
        cv2.putText(canv, lab, (cc * C + 3, rr * (C + 34) + 12), 0, 0.33, (200, 200, 200), 1, cv2.LINE_AA)
        col = (0, 255, 255) if t > 0.10 else (255, 255, 255)
        cv2.putText(canv, "gape %.2f" % g, (cc * C + 3, rr * (C + 34) + 24), 0, 0.36, (100, 160, 255), 1, cv2.LINE_AA)
        cv2.putText(canv, "teeth %.2f" % t, (cc * C + 72, rr * (C + 34) + 24), 0, 0.36, col, 1, cv2.LINE_AA)
    cv2.imwrite(OUT + "/" + name, canv, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(name, canv.shape)


for grp, fn in (("CT_top", "expr_top.jpg"), ("CT_bot", "expr_bot.jpg"), ("ATC", "expr_atc.jpg")):
    sub = []
    for r in [x for x in R if x["grp"] == grp]:
        img = cv2.imread(pathof(r))
        for f in [x for x in r["faces"] if x["conf"] >= 0.70 and x.get("expr")][:2]:
            p = f["pose"]
            sub.append((("%s v%d" % (r["file"][:9], r["views"]))[:24],
                        crop(img, p, 0.62 * p["eyed"]),
                        f["expr"]["gape_h"], f["expr"]["teeth_frac"]))
    sheet(sub, fn)
