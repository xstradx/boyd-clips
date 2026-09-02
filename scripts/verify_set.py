"""Check a folder of finished thumbnails against every rule Nathan has given.

Each check is a rule he stated, with the measurement that decides it. A check
that cannot fail is not a check, so every threshold here is calibrated against
either the shipped Thompson reference or a build he rejected.

    python scripts/verify_set.py --dir READY-TO-POST/Q3SET --check all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import scipy.ndimage as nd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

# All calibrated against 1_LONGFORM_thumbnail.jpg (the shipped Thompson) except
# where noted.
LUMA_TARGET = 122.0     # Thompson 124.9, the CARTHIEF build Nathan liked 118.6
LUMA_TOL = 12.0         # he rejected 147.1 and 155.9 as "really brifht"
CHROMA_MAX = 6.5        # Thompson 3.29; the build he called blocky measured 8.13
ARROW_MIN = 1500        # Thompson 3,904 px
ARROW_MAX = 6000
BYST_CLEAR = 0.12       # below this a bystander head is clear of her
BYST_HIDDEN = 0.88      # above this it is fully behind her; between = peeking


def alpha_of(img: Image.Image) -> np.ndarray:
    from rembg import new_session, remove
    if not hasattr(alpha_of, "_s"):
        alpha_of._s = new_session("birefnet-portrait")
    return np.asarray(remove(img.convert("RGBA"), session=alpha_of._s)
                      .getchannel("A"), dtype=np.uint8)


def arrow_mask(a: np.ndarray) -> np.ndarray:
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (r > 170) & (g < 45) & (b < 45)


def type_mask(a: np.ndarray) -> np.ndarray:
    """Caption/headline ink: a very bright core with a very dark pixel close by.

    Thresholding on brightness alone was tried and measured the ceiling and a
    white collar instead of the type — it called a correct render wrong 5 times
    out of 5. The stroke is the distinguishing feature, so it is what is keyed
    on.
    """
    L = np.asarray(Image.fromarray(a.astype(np.uint8)).convert("L"), dtype=np.uint8)
    return (L > 238) & (nd.maximum_filter((L < 45).astype(np.uint8), size=17) > 0)


def flat_chroma(img: Image.Image) -> float:
    y = np.asarray(img.convert("YCbCr"), dtype=float)
    L = np.asarray(img.convert("L"), dtype=float)
    H, W = L.shape
    best = None
    for yy in range(0, H - 100, 20):
        for xx in range(0, W - 100, 20):
            q = L[yy:yy + 90, xx:xx + 90]
            if q.std() > 12:
                continue
            if best is None or q.mean() > best[0]:
                best = (q.mean(), xx, yy)
    if best is None:
        return 0.0
    _, xx, yy = best
    cb = y[yy:yy + 90, xx:xx + 90, 1]
    cr = y[yy:yy + 90, xx:xx + 90, 2]
    return float(np.sqrt((cb - 128) ** 2 + (cr - 128) ** 2).mean())


def faces(img: Image.Image):
    import cv2
    cc = cv2.CascadeClassifier(cv2.data.haarcascades
                               + "haarcascade_frontalface_alt2.xml")
    g = cv2.equalizeHist(cv2.cvtColor(np.asarray(img.convert("RGB")),
                                      cv2.COLOR_RGB2GRAY))
    return [tuple(int(v) for v in f)
            for f in cc.detectMultiScale(g, 1.08, 5, minSize=(70, 70))]


def check(path: Path, which: str):
    """Return (list of failure strings, list of note strings)."""
    img = Image.open(path).convert("RGB")
    a = np.asarray(img, dtype=np.uint8)
    W, H = img.size
    fails, notes = [], []
    name = path.name

    if which in ("all", "size"):
        if (W, H) != (1280, 720):
            fails.append(f"SIZE {name}: {W}x{H}, not 1280x720")

    if which in ("all", "luma"):
        L = np.asarray(img.convert("L"), dtype=float).mean()
        notes.append(f"{name} luma {L:.1f}")
        if abs(L - LUMA_TARGET) > LUMA_TOL:
            fails.append(f"LUMA {name}: {L:.1f}, more than {LUMA_TOL:.0f} from "
                         f"{LUMA_TARGET:.0f}")

    if which in ("all", "pale"):
        # THE PALE CHECK, and it is measured INSIDE HER MATTE.
        #
        # Nathan, 2026-08-29: "in sanchez thumbnail boyd still looks so bright
        # and pale, same thing in offer up ... thats slop" -- on two files that
        # had already passed every check in this script.
        #
        # They passed because every check above is a CANVAS check and the canvas
        # cannot see her. Whole-image dynamic range is a full 0..255 on all four
        # reference files INCLUDING both he rejected, because the plate supplies
        # the deep blacks while her layer floats 24-37 code values above them.
        # Whole-canvas mean luma is worse than useless here: OFFERUP shipped at
        # 114.2, DARKER than both files he approved, and he still called it pale.
        #
        # Her silhouette cannot be recovered from the finished JPEG either --
        # re-matting the canvas merges her with whoever she overlaps; on SANCHEZ
        # that came back as ONE component spanning x=263..1279. So the BUILDER
        # writes her mask down and this reads it. No sidecar, no check, said out
        # loud rather than silently skipped.
        import json as _json
        sc = Path(str(path) + ".meta.json")
        if not sc.is_file():
            notes.append(f"{name} pale: NOT CHECKED - no {sc.name} beside it")
        else:
            meta = _json.loads(sc.read_text())
            jm = Path(meta.get("judge_mask", ""))
            if not jm.is_file():
                notes.append(f"{name} pale: NOT CHECKED - mask {jm} missing")
            else:
                import layer_metrics as LM
                m = LM.measure(np.asarray(img), np.asarray(Image.open(jm).convert("L")))
                notes.append(f"{name} " + LM.fmt("judge layer", m).split(None, 2)[2])
                for f in LM.verdict(m):
                    fails.append(f"{f}  [{name}]")

    if which in ("all", "chroma"):
        cd = flat_chroma(img)
        notes.append(f"{name} chroma {cd:.2f}")
        if cd > CHROMA_MAX:
            fails.append(f"CHROMA {name}: {cd:.2f} over {CHROMA_MAX}")

    if which in ("all", "arrow", "type", "limb", "bystander"):
        al = alpha_of(img)
        person = al > 24

    if which in ("all", "arrow"):
        am = arrow_mask(a)
        n = int(am.sum())
        notes.append(f"{name} arrow {n}px")
        if not (ARROW_MIN <= n <= ARROW_MAX):
            fails.append(f"ARROW {name}: {n}px outside {ARROW_MIN}-{ARROW_MAX}")
        else:
            on = float((am & person).sum()) / max(n, 1)
            if on > 0.02:
                fails.append(f"ARROW {name}: {on*100:.1f}% of it sits on a person")
            # and it must actually reach somebody - zero overlap while pointing
            # at empty ceiling scored perfectly once
            ys, xs = np.where(am)
            if len(xs):
                cx, cy = xs.mean(), ys.mean()
                hit = False
                for ang in range(0, 360, 5):
                    dx, dy = np.cos(np.radians(ang)), np.sin(np.radians(ang))
                    for d in range(10, 500, 4):
                        px, py = int(cx + dx * d), int(cy + dy * d)
                        if not (0 <= px < W and 0 <= py < H):
                            break
                        if person[py, px]:
                            hit = True
                            break
                    if hit:
                        break
                if not hit:
                    fails.append(f"ARROW {name}: no ray from it reaches a person")

    if which in ("all", "type"):
        tm = type_mask(a)
        bad = 0
        for (fx, fy, fw, fh) in faces(img):
            # the brow-down part of the face, which is what must stay clear
            y0 = fy + int(fh * 0.30)
            bad += int(tm[y0:fy + fh, fx:fx + fw].sum())
        notes.append(f"{name} type-on-face {bad}px")
        if bad > 60:
            fails.append(f"TYPE-ON-FACE {name}: {bad}px of type on a face")

    if which in ("all", "limb"):
        lbl, k = nd.label(person)
        if k:
            sizes = nd.sum(person, lbl, range(1, k + 1))
            big = int(np.argmax(sizes)) + 1
            m = lbl == big
            ys, xs = np.where(m)
            # a limb cut by a rectangle leaves a long straight vertical edge:
            # a column where the silhouette stops dead across many rows
            col_counts = m.sum(axis=0)
            occupied = np.where(col_counts > 0)[0]
            if len(occupied) > 4:
                edge = col_counts[occupied]
                jump = np.abs(np.diff(edge.astype(int)))
                worst = int(jump.max()) if len(jump) else 0
                span = int(ys.max() - ys.min()) + 1
                notes.append(f"{name} silhouette edge jump {worst}/{span}")
                if span and worst > 0.55 * span:
                    fails.append(f"LIMB {name}: silhouette drops {worst}px in one "
                                 f"column of a {span}px body - a straight cut")

    if which in ("all", "bystander"):
        lbl, k = nd.label(person)
        if k >= 2:
            sizes = nd.sum(person, lbl, range(1, k + 1))
            order = np.argsort(sizes)[::-1]
            hero = int(order[0]) + 1
            hero_m = lbl == hero
            worst = None
            for idx in order[1:]:
                comp = int(idx) + 1
                if sizes[idx] < 4000:
                    continue
                cm = lbl == comp
                ys, xs = np.where(cm)
                hh = ys.max() - ys.min()
                head = cm.copy()
                head[ys.min() + int(0.34 * hh):, :] = False
                if head.sum() < 200:
                    continue
                # how much of that head is behind the hero's silhouette
                grown = nd.binary_dilation(hero_m, iterations=3)
                cov = float((head & grown).sum()) / float(head.sum())
                if BYST_CLEAR < cov < BYST_HIDDEN:
                    worst = cov if worst is None else max(worst, cov)
            if worst is not None:
                fails.append(f"BYSTANDER {name}: a head is {worst*100:.0f}% "
                             f"behind the cut-out - half-peeking")
    return fails, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--check", default="all",
                    choices=("all", "size", "luma", "chroma", "arrow", "type",
                             "limb", "bystander", "pale"))
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    d = a.dir if a.dir.is_absolute() else (Path.cwd() / a.dir)
    files = sorted(p for p in d.glob("*.jpg") if not p.name.startswith("_"))
    if not files:
        print(f"no thumbnails in {d}")
        return 1

    all_fails, all_notes = [], []
    for p in files:
        f, n = check(p, a.check)
        all_fails += f
        all_notes += n

    if a.verbose or a.check == "all":
        for n in all_notes:
            print("  " + n)

    labels = {"type": "TYPE-ON-FACE", "arrow": "ARROW", "limb": "LIMB",
              "luma": "LUMA", "chroma": "CHROMA", "bystander": "BYSTANDER",
              "size": "SIZE", "pale": "PALE"}
    for f in all_fails:
        print("  FAIL " + f)
    if a.check == "all":
        print(f"\n{len(files)} thumbnails, {len(all_fails)} failures")
    else:
        print(f"{labels[a.check]}: {len(all_fails)} failures")
    return 0 if not all_fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
