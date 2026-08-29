# -*- coding: utf-8 -*-
"""Faces + text-safe-zone + title/burned-text relationship.
Faces: OpenCV Haar (offline, BSD-3 with cv2), strict settings, then hand-verified
against a rendered contact sheet. Burned text transcribed by reading each original."""
import io, json, os
import numpy as np, cv2
from scipy import stats

ROOT = r"C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime"
THUMBS = os.path.join(ROOT, "thumbs")
OUT = os.path.join(ROOT, "_ctmeas")
rows = json.load(io.open(os.path.join(OUT, "ct_measure3.json"), encoding="utf-8"))

# burned-in thumbnail copy, transcribed by reading each 1280x720 original
BURN = {
 "top_00891000_ERPX6JpX5OU": "PHONE CONFISCATED! | JUDGE BOYD HANDCUFFS A VISITOR MOM!",
 "top_00790000__-WRN7q01OY": "THE CRAZIEST | JUDGE BOYD | OWNS THE MOST DISRESPECTFUL ATTORNEY",
 "top_00553000_rcub_Jev9NE": "REFUSE TO | FACE JUDGE BOYD",
 "top_00529000_6Tp2eiBjGB8": "HIGH NURSE | CUFFED IN COURT",
 "top_00379000_urZza-9kdP0": "CAUGHT IN LIES ! | JUDGE BOYD UNSTOPPABLE!",
 "top_00354000_ePdAxp1Zs8Y": "VISITOR MOM CUFFED | JUDGE BOYD | OWNS THE CARZIEST ENTITLED PUNK IN COURT!",
 "top_00335000_aH0fnO4w-dg": "SMUG LAWYER EXPOSED | JUDGE BOYD | OWNS LAWYER WHO ATTACKED PROBATION OFFICER",
 "top_00308000_lfAlCDsEQZ4": "RAPPER PUNK EXPOSED | JUDGE BOYD | SENTENCES RAPPER PUNK TO 80 YEARS",
 "top_00305000_8n5raFtKul8": "FAKE DISABILITY",
 "top_00277000_k69GmELAgVw": "HIGH IN COURT | JUDGE BOYD | OWNS MOM SHOWED UP HIGH IN COURT!",
 "top_00241000_8lxIY35zb6Q": "BUSTED HAVING $EX IN COURT!!",
 "top_00233000_-iPnSFl434E": "I DO WHAT I WANT !!",
 "top_00214000__eMKRoRaE_w": "20 YEARS ?! | JUDGE BOYD'S TOUGH VERDICT!",
 "top_00209000_z05aWSTzw0k": "ENTITLED PUNK | JUDGE BOYD | OWNS THE CRAZIEST ENTITLED PUNK IN COURT!",
 "top_00204000_J3LdwHAZR2E": "UPDATE 2026 | NASTY VISITOR MOM",
 "bot_00001700_-YRHSSLanxk": "SNAPCHAT FOOL | FACES 20 YEARS",
 "bot_00001500_gVVI_SdlsvA": "JUDGE BOYD | DAD MADE IT WORSE | LAWYER GETS SHOCKED BY THE HONESTY",
 "bot_00001300_rUJ__Sb3Y8w": "JAIL FOR BEER & CANDY?! | JUDGE FLEISCHER'S TOUGH VERDICT!",
 "bot_00001200_qlDoZCJs620": "ENTITLED BRAT EXPOSED | JUDGE BOYD | OWNS AN ENTITLED MOM IN HER COURT",
 "bot_00001100_--Mpaln4jx8": "FAKE LAWYER",
 "bot_00001100_U204YIfp-rc": "MY SON CAN'T BE GAY! | 6 YEARS FOR THIS ?? | JUDGE BOYD REACTS!",
 "bot_00001000_95HqsmyM-zI": "JUDGE | EXPOSES STUPID KAREN | STUPID",
 "bot_00000988_79nw7lP0jm0": "JUDGE BOYD SHOCKED! | DEFENDANT CHOOSE PRISON OVER PROBATION !!",
 "bot_00000749_RfF0ouKeE0w": "CAUGHT ON CAMERA!! | CARYING PUNK CUFFED",
 "bot_00000388_q1Fo7x_0ItI": "JUDGE FIRES PROBATION OFFICER ??",
}

CASC = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
PROF = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")


def faces(bgr):
    g = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    H, W = g.shape
    boxes = []
    for (x, y, w, h) in CASC.detectMultiScale(g, 1.06, 10, minSize=(70, 70)):
        boxes.append([int(x), int(y), int(w), int(h)])
    gm = cv2.flip(g, 1)
    for c, flip in ((PROF, False), (PROF, True)):
        src = gm if flip else g
        for (x, y, w, h) in c.detectMultiScale(src, 1.06, 12, minSize=(90, 90)):
            bx = int(W - x - w) if flip else int(x)
            boxes.append([bx, int(y), int(w), int(h)])
    if not boxes:
        return []
    idx = np.array(cv2.dnn.NMSBoxes(boxes, [1.0] * len(boxes), 0.0, 0.25)).ravel()
    return [boxes[i] for i in idx]


DBG = os.path.join(OUT, "faces")
os.makedirs(DBG, exist_ok=True)
for r in rows:
    p = os.path.join(THUMBS, r["file"])
    bgr = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)
    H, W = bgr.shape[:2]
    fb = faces(bgr)
    r["faces"] = [dict(x=b[0], y=b[1], w=b[2], h=b[3], hf=b[3] / H,
                       areaf=b[2] * b[3] / float(W * H),
                       cxf=(b[0] + b[2] / 2) / W, cyf=(b[1] + b[3] / 2) / H) for b in fb]
    r["nface"] = len(fb)
    r["maxface_hf"] = max([f["hf"] for f in r["faces"]], default=0.0)
    r["maxface_areaf"] = max([f["areaf"] for f in r["faces"]], default=0.0)
    # text safe zone: geometry of the largest-cap text line
    if r["lines"]:
        big = max(r["lines"], key=lambda l: l["capf"])
        r["big_line"] = dict(capf=big["capf"], y0f=big["y0f"], y1f=big["y1f"],
                             x0f=big["x0f"], x1f=big["x1f"],
                             bottom_gap=1.0 - big["y1f"], bandf=big["y1f"] - big["y0f"])
        # does the biggest line sit on a detected face?
        ov = 0.0
        for f in r["faces"]:
            ix = max(0.0, min(big["x1f"], f["cxf"] + f["hf"] * 0.38) - max(big["x0f"], f["cxf"] - f["hf"] * 0.38))
            iy = max(0.0, min(big["y1f"], f["cyf"] + f["hf"] / 2) - max(big["y0f"], f["cyf"] - f["hf"] / 2))
            ov += ix * iy
        area = (big["x1f"] - big["x0f"]) * (big["y1f"] - big["y0f"])
        r["bigline_on_face"] = ov / area if area > 0 else 0.0
    else:
        r["big_line"] = None
        r["bigline_on_face"] = 0.0
    key = r["file"].replace("_maxresdefault.jpg", "")
    burn = BURN[key]
    r["burn"] = burn
    r["burn_words"] = len([w for w in burn.replace("|", " ").split() if w])
    r["burn_chars"] = len(burn.replace(" | ", " "))
    t = (r["title"] or "")
    r["title_words"] = len(t.split())
    r["title_chars"] = len(t)
    tw = set(w.strip("!?,'\u2019\u201c\u201d\"|.&").lower() for w in t.split())
    bw = set(w.strip("!?,'\u2019\u201c\u201d\"|.&").lower() for w in burn.replace("|", " ").split())
    bw = {w for w in bw if len(w) > 2}
    r["burn_title_overlap"] = (len(bw & tw) / len(bw)) if bw else 0.0
    r["title_starts_judge_boyd"] = t.lower().startswith("judge boyd")
    r["burn_has_judge_boyd"] = "judge boyd" in burn.lower()

    d = bgr.copy()
    for f in r["faces"]:
        cv2.rectangle(d, (f["x"], f["y"]), (f["x"] + f["w"], f["y"] + f["h"]), (0, 255, 255), 3)
        cv2.putText(d, "%.2fH" % f["hf"], (f["x"], max(22, f["y"] - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.imencode(".jpg", d)[1].tofile(os.path.join(DBG, r["file"]))

json.dump(rows, io.open(os.path.join(OUT, "ct_measure4.json"), "w", encoding="utf-8"), indent=1)

TOP = sorted([r for r in rows if r["grp"] == "top"], key=lambda r: -r["views"])
BOT = sorted([r for r in rows if r["grp"] == "bot"], key=lambda r: -r["views"])


def cont(name, fn, fmt="%.3f"):
    a = [fn(r) for r in TOP]; b = [fn(r) for r in BOT]
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    rb = 2 * u / (len(a) * len(b)) - 1
    print("\n== %s ==" % name)
    print("  top med=%s mean=%s [%s]" % (fmt % np.median(a), fmt % np.mean(a), " ".join(fmt % v for v in sorted(a))))
    print("  bot med=%s mean=%s [%s]" % (fmt % np.median(b), fmt % np.mean(b), " ".join(fmt % v for v in sorted(b))))
    print("  U=%.1f p=%.4f rb=%+.2f" % (u, p, rb))


def binary(name, fn):
    a = sum(1 for r in TOP if fn(r)); b = sum(1 for r in BOT if fn(r))
    odds, p = stats.fisher_exact([[a, len(TOP) - a], [b, len(BOT) - b]])
    print("\n== %s ==  top %d/15 (%.0f%%)  bot %d/10 (%.0f%%)  Fisher p=%.4f"
          % (name, a, 100.0 * a / 15, b, 100.0 * b / 10, p))


print("=" * 108)
print("%-40s %-4s %8s %4s %6s %6s %6s %6s %6s %6s %5s %5s %5s" % (
    "file", "grp", "views", "nfc", "fcHmax", "fcAmax", "bigCap", "big_y0", "big_y1", "botGap",
    "twrd", "bwrd", "ovlp"))
print("=" * 108)
for r in TOP + BOT:
    bl = r["big_line"] or {}
    print("%-40s %-4s %8d %4d %6.3f %6.4f %6.3f %6.3f %6.3f %6.3f %5d %5d %5.2f" % (
        r["file"].replace("_maxresdefault.jpg", "")[:40], r["grp"], r["views"], r["nface"],
        r["maxface_hf"], r["maxface_areaf"], bl.get("capf", 0), bl.get("y0f", 0), bl.get("y1f", 0),
        bl.get("bottom_gap", 0), r["title_words"], r["burn_words"], r["burn_title_overlap"]))

cont("largest face height / H", lambda r: r["maxface_hf"])
cont("largest face area / frame", lambda r: r["maxface_areaf"], "%.4f")
cont("faces detected", lambda r: r["nface"], "%3.0f")
cont("biggest text line: top edge y0/H", lambda r: (r["big_line"] or {}).get("y0f", 0.0))
cont("biggest text line: bottom edge y1/H", lambda r: (r["big_line"] or {}).get("y1f", 0.0))
cont("gap from biggest line to bottom of frame /H", lambda r: (r["big_line"] or {}).get("bottom_gap", 0.0))
cont("title word count", lambda r: r["title_words"], "%3.0f")
cont("burned-in thumbnail word count", lambda r: r["burn_words"], "%3.0f")
cont("burned-in thumbnail character count", lambda r: r["burn_chars"], "%4.0f")
cont("share of thumbnail words that also appear in the title", lambda r: r["burn_title_overlap"])
binary("title starts with the words 'Judge Boyd'", lambda r: r["title_starts_judge_boyd"])
binary("'JUDGE BOYD' burned into the thumbnail", lambda r: r["burn_has_judge_boyd"])
binary("thumbnail copy is <= 6 words", lambda r: r["burn_words"] <= 6)

print("\n--- burned text vs title, per file ---")
for r in TOP + BOT:
    print("%-4s %8d  THUMB: %s" % (r["grp"], r["views"], r["burn"]))
    print("%-4s %8s  TITLE: %s" % ("", "", (r["title"] or "").encode("ascii", "replace").decode()))
