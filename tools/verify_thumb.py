# -*- coding: utf-8 -*-
"""Score ANY thumbnail file against the measured gates.

Metrics live in thumb_metrics.py, which reproduces the derivation exactly
(max drift 0.0008 across the 7 same-encoder files, 0 FP / 0 FN).

    A  posterisation      flat_g_p90 > 0.30  or  poster_fa > 0.020     FAIL
    C  blown subject      subject_max_L > 180                          FLAG
    D  duplicate faces    SIFT+RANSAC inliers >= 1                     FAIL
                         (a pair with a side under MIN_DESC=20 SIFT
                          descriptors is UNMEASURABLE and printed as such;
                          inliers on a fit no duplicate could give - see
                          _fit_geometry - are REJECTED and printed as such)

Gate B (background mush) is NOT a pass/fail gate: measured on this evidence it is
a strict SUBSET of A - every file it catches, A already catches. It is printed as
a diagnostic because it localises WHERE a smear is, which is what "smooth areas
where it's not supposed to be smooth" points at.

SCOPE, measured not assumed:
  * A is PRE-DELIVERY ONLY. 10 of 12 competitor thumbnails trip it AFTER YouTube
    re-encodes them (quant table sum 736 vs our 369). Running A on a downloaded
    thumbnail condemns work that is fine.
  * C is a FLAG, not a fail - 3 of 12 successful competitors trip it.
  * D is the only gate valid on an arbitrary image from any source. 0 of 15 clean
    files score above zero.

Caveat carried from the derivation: the approved set is n=2. The gates separate
perfectly, but two is two.

    python tools/verify_thumb.py IMG [IMG ...]
    python tools/verify_thumb.py --selftest
"""
import sys, os
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_metrics as M

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
YUNET = os.path.join(ROOT, "models", "yunet2023.onnx")

LIM_FLAT, LIM_POST, LIM_L, LIM_DUP = 0.30, 0.020, 180.0, 1

# Gate D's measurement has a validity floor of its own. Each face crop is
# resized to 160x160 and SIFT-described; a homography fitted by RANSAC always
# marks its 4-point minimal sample as inliers, so a crop that yields only a
# handful of descriptors can "match" anything at 4-5 inliers. Measured
# 2026-09-01 on MONKEY_S: the monkey's face (367 descriptors) vs a 20x22 px
# blurred GALLERY face behind its arm (11 descriptors) -> 11 ratio-test
# matches, 5 inliers, gate D FAIL on a plate the monkey is not in. Every
# duplicate that YuNet can detect measures far above that: same-size copies
# of each accepted subject 90-141 descriptors / 20-55 inliers; the same
# subject shrunk to 40 px and pasted into the plate 67-77 descriptors /
# 8-19 inliers. The five tiny gallery faces across the accepted set give
# 3-11. Pasting each accepted subject back into its own plate at 30-100 px
# (12 placements x 4 files): the smallest duplicate YuNet still detects (30 px
# on HS_REMAKE and CARTHIEF, 40 px on OFFERUP and MONKEY) yields 32-60
# descriptors and 8-20 inliers. MIN_DESC = 20 sits between the two
# populations (x1.8 above the worst blob, x1.6 under the smallest duplicate).
# A pair with a side under it is UNMEASURABLE, not a pass: it is counted and
# printed, never silently dropped. Below ~30 px the gate is blind for a
# different reason - the DETECTOR no longer fires - and that limit is not
# closed by anything here.
MIN_DESC = 20


def _dup_inliers(rgb, faces, detail=None):
    """The same person twice. Absolute - never waived.

    `detail`, when a dict is passed, receives every measured pair as
    (i, j, n_desc_i, n_desc_j, good, inliers) under "pairs" and the pairs
    skipped for too few descriptors under "unmeasurable"."""
    if detail is not None:
        detail.setdefault("pairs", [])
        detail.setdefault("unmeasurable", [])
        detail.setdefault("rejected_fit", [])
    if len(faces) < 2:
        return 0
    sift = cv2.SIFT_create()
    feats = []
    H_, W_ = rgb.shape[:2]
    for f in faces:
        fw, fh = int(f["bw"]), int(f["bh"])
        x = int(f["cx"] * W_ - fw / 2)
        y = int(f["cy"] * H_ - fh / 2)
        pad = int(fw * 0.15)
        c = rgb[max(0, y - pad):y + fh + pad, max(0, x - pad):x + fw + pad]
        if c.size == 0:
            feats.append((None, None))
            continue
        c = cv2.resize(cv2.cvtColor(c, cv2.COLOR_RGB2GRAY), (160, 160))
        feats.append(sift.detectAndCompute(c, None))
    # Box geometry, so nested detections can be skipped below.
    boxes = []
    for f in faces:
        fw, fh = int(f["bw"]), int(f["bh"])
        x = int(f["cx"] * W_ - fw / 2)
        y = int(f["cy"] * H_ - fh / 2)
        boxes.append((x, y, fw, fh))

    def _nested(a, b, thresh=0.5):
        """True when one box sits largely inside the other.

        YuNet sometimes fires a small extra detection INSIDE a real face - on
        MONKEY it returned a 32x42 box at (1000,471), inside Judge Boyd's own
        183x254 face box. SIFT then matched it to her with 9 inliers, which is
        correct: they are the same pixels. That is not the same person twice,
        it is one person detected twice, and Gate D must not fail on it.
        """
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0, min(ay + ah, by + bh) - max(ay, by))
        inter = ix * iy
        if inter == 0:
            return False
        return inter / float(min(aw * ah, bw * bh)) > thresh

    bf = cv2.BFMatcher()
    worst = 0
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            if _nested(boxes[i], boxes[j]):
                continue
            (k1, d1), (k2, d2) = feats[i], feats[j]
            n1 = 0 if d1 is None else len(d1)
            n2 = 0 if d2 is None else len(d2)
            if min(n1, n2) < MIN_DESC:
                if detail is not None:
                    detail["unmeasurable"].append((i, j, n1, n2))
                continue
            g = {}
            inl, good = _pair_inliers(k1, d1, k2, d2, bf, geom=g)
            if detail is not None:
                detail["pairs"].append((i, j, n1, n2, good, inl))
                if g and not g["valid"] and g["raw_inliers"] >= LIM_DUP:
                    detail["rejected_fit"].append((i, j, n1, n2, good, g))
            worst = max(worst, inl)
    return worst


# A duplicate is the SAME face box on the SAME pixels, and both crops are
# resized to 160x160 by the same rule - so the homography between two real
# duplicates is close to the identity. Measured 2026-09-01 (paste sweep, the
# biggest face of CARTHIEF / SANCHEZ / THOMPSON shrunk to 30-100 px and pasted
# into its own plate): scale 0.89-1.15, anisotropy 1.00-1.15, perspective
# <= 0.14, translation <= 22 px on every detected duplicate of 40 px and up.
# The false positive that got past MIN_DESC on MONKEY_audit_now_ul (the
# monkey, 340 descriptors, vs a 24x30 px blurred gallery face, 24
# descriptors: 12 ratio-test matches, 9 "inliers") fits scale 0.45,
# anisotropy 9.0, perspective 2.4, translation 108 px - a degenerate
# transform that maps nothing to anything. The ratio test is the mechanism:
# with 24 train descriptors every one of the monkey's 340 queries has a
# "clearly best" neighbour, and RANSAC then finds 9 of those 12 on one
# arbitrary homography. Reversed (blob -> monkey) the same pair gives 0
# matches. So an inlier count only counts when the fitted transform is one a
# duplicate could physically produce. Anisotropy and perspective are the
# discriminators (>= 1.7x outside every real duplicate, >= 4.5x inside the
# false positive); scale and translation are loose sanity bounds only -
# YuNet boxes the same face differently at different sizes (MONKEY's face
# pasted at 100 px came back as a 54x69 box: scale 1.44, shift 70 px, on a
# clean fit with anisotropy 1.02). A rejected fit is printed, never dropped.
# Cost, said out loud: two degenerate fits that were right by luck are no
# longer counted - SANCHEZ at 30 px (7 inliers, anisotropy 10.6) and MONKEY_S
# at 40 px (7 inliers, perspective 5.4, shift 317 px). The smallest duplicate
# caught on a clean fit is 40 px on MONKEY / OFFERUP / CARTHIEF / SANCHEZ and
# 50 px on THOMPSON / MONKEY_S; D-50px-dup in --selftest holds that floor.
FIT_SCALE = (0.5, 2.0)     # sqrt|det| of the affine part
FIT_ANISO = 2.0            # ratio of the affine part's singular values
FIT_PERSP = 0.5            # |(h31, h32)| * 160  (perspective terms)
FIT_TRANS = 120.0          # px on the 160x160 crop (3/4 of it: sanity only)


def _fit_geometry(Hm):
    """(scale, anisotropy, perspective, translation) of a 3x3 homography on
    the 160x160 crop, and whether it is a transform a duplicate could give."""
    A = Hm[:2, :2]
    det = float(np.linalg.det(A))
    sv = np.linalg.svd(A, compute_uv=False)
    g = dict(scale=float(np.sqrt(abs(det))),
             aniso=float(sv[0] / max(sv[1], 1e-9)),
             persp=float(np.hypot(Hm[2, 0], Hm[2, 1]) * 160),
             trans=float(np.hypot(Hm[0, 2], Hm[1, 2])))
    g["valid"] = (det > 0 and FIT_SCALE[0] <= g["scale"] <= FIT_SCALE[1]
                  and g["aniso"] <= FIT_ANISO and g["persp"] <= FIT_PERSP
                  and g["trans"] <= FIT_TRANS)
    return g


def _pair_inliers(k1, d1, k2, d2, bf=None, geom=None):
    """RANSAC-homography inliers between two described crops -> (inliers, good).
    Inliers on a fit that no duplicate could produce (see _fit_geometry) are
    returned as 0; `geom`, when a dict is passed, receives the fit and the raw
    inlier count so the rejection is printed. Split out so the selftest can
    drive the validity floor directly."""
    bf = bf or cv2.BFMatcher()
    good = [m for m, n in bf.knnMatch(d1, d2, k=2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return 0, len(good)
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    Hm, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if Hm is None or mask is None:
        return 0, len(good)
    raw = int(mask.sum())
    g = _fit_geometry(Hm)
    g["raw_inliers"] = raw
    if geom is not None:
        geom.update(g)
    return (raw if g["valid"] else 0), len(good)


def score(path, quiet=False):
    rgb = cv2.imread(path)[:, :, ::-1].copy()
    # Measured on the FINAL frame, which is the domain LIM_FLAT was derived from.
    # A photo-layer variant is written next to the output for diagnosis, but it is
    # NOT gated: its threshold would have to be re-derived on that domain, and with
    # an approved set of n=2 there is nothing honest to derive it from yet.
    photo_path = os.path.splitext(path)[0] + ".photo.jpg"
    faces = M.detect_faces(rgb, YUNET)
    flat = M.flat_g_p90(rgb)
    post = M.poster_fa(rgb)
    mush = M.bg_mush(rgb, faces)
    subL = M.subject_max_L(rgb, faces)
    dup_detail = {}
    dup = _dup_inliers(rgb, faces, dup_detail)

    # poster_fa is a DIAGNOSTIC, not a vote. Measured on the full approved/rejected
    # set it changes nothing: 0 FP / 0 FN with it, 0 FP / 0 FN without it. What it
    # does do is fail legitimate uniform content - a plain ceiling, a flat set of
    # scrubs - because the approved set is n=2. Same demotion gate B got.
    a_bad = flat > LIM_FLAT
    c_flag = subL > LIM_L
    d_bad = dup >= LIM_DUP

    if not quiet:
        print(f"\n{os.path.basename(path)}   ({len(faces)} faces)")
        print(f"   {'FAIL' if a_bad else 'PASS'}  A posterisation   "
              f"flat_g_p90={flat:.4f} (<= {LIM_FLAT})")
        print(f"   ....  poster_fa={post:.4f}  (diagnostic only - redundant with A)")
        print(f"   {'FLAG' if c_flag else 'PASS'}  C blown subject   "
              f"subject_max_L={subL:.1f} (<= {LIM_L})")
        print(f"   {'FAIL' if d_bad else 'PASS'}  D duplicate face  "
              f"inliers={dup} (< {LIM_DUP})")
        for (i, j, n1, n2, good, inl) in dup_detail.get("pairs", []):
            if inl >= LIM_DUP:
                print(f"         face{i} ~ face{j}: {n1}/{n2} descriptors, "
                      f"{good} matches, {inl} inliers")
        if dup_detail.get("unmeasurable"):
            um = dup_detail["unmeasurable"]
            print(f"   ....  D unmeasurable pairs: {len(um)} "
                  f"(a side under {MIN_DESC} SIFT descriptors: "
                  + ", ".join(f"face{i}~face{j} {n1}/{n2}" for i, j, n1, n2 in um) + ")")
        for (i, j, n1, n2, good, g) in dup_detail.get("rejected_fit", []):
            print(f"   ....  D rejected fit: face{i}~face{j} {n1}/{n2} descriptors, "
                  f"{good} matches, {g['raw_inliers']} raw inliers on a transform no "
                  f"duplicate gives (scale {g['scale']:.2f} aniso {g['aniso']:.1f} "
                  f"persp {g['persp']:.2f} trans {g['trans']:.0f}px)")
        print(f"   ....  bg_mush={mush:.4f}  (diagnostic only, subset of A)")
        bad = [n for n, b in (("A", a_bad), ("D", d_bad)) if b]
        tail = "SHIP" if not bad else "BLOCKED on " + ",".join(bad)
        if c_flag and not bad:
            tail += "  (C flagged - check the subject is not blown)"
        print(f"   -> {tail}")
    return not (a_bad or d_bad), dict(flat=flat, post=post, mush=mush, subL=subL, dup=dup)


def selftest():
    """A gate that cannot fail is worse than no gate."""
    ref = os.path.join(ROOT, "work", "repair", "HS_REMAKE.jpg")
    if not os.path.exists(ref):
        print("SELFTEST_SKIP no reference on disk")
        return 0
    rgb = cv2.imread(ref)[:, :, ::-1].copy()
    faces = M.detect_faces(rgb, YUNET)
    checks = []

    post = (rgb.astype(np.float32) // 40 * 40).astype(np.uint8)
    checks.append(("A", M.flat_g_p90(post) > LIM_FLAT))

    blown = np.clip(rgb.astype(np.float32) * 1.9, 0, 255).astype(np.uint8)
    bf = M.detect_faces(blown, YUNET)
    checks.append(("C", M.subject_max_L(blown, bf) > LIM_L))

    dup = rgb.copy()
    if faces:
        f0 = faces[0]
        fw, fh = int(f0["bw"]), int(f0["bh"])
        x = int(f0["cx"] * rgb.shape[1] - fw / 2)
        y = int(f0["cy"] * rgb.shape[0] - fh / 2)
        tx = min(rgb.shape[1] - fw - 1, x + int(fw * 1.6))
        dup[y:y + fh, tx:tx + fw] = rgb[y:y + fh, x:x + fw]
    checks.append(("D", _dup_inliers(dup, M.detect_faces(dup, YUNET)) >= LIM_DUP))

    # D's validity floor (MIN_DESC) must not blind it to a SMALL duplicate: the
    # biggest face shrunk to 50 px and pasted into the plate still fails (50 px
    # at (40,300) is detected and matched on all four references measured) ...
    if faces:
        f0 = max(faces, key=lambda f: f["bh"])
        fw, fh = int(f0["bw"]), int(f0["bh"])
        x = int(f0["cx"] * rgb.shape[1] - fw / 2)
        y = int(f0["cy"] * rgb.shape[0] - fh / 2)
        small = cv2.resize(rgb[y:y + fh, x:x + fw], (max(8, int(fw * 50 / fh)), 50),
                           interpolation=cv2.INTER_AREA)
        dup2 = rgb.copy()
        dup2[300:350, 40:40 + small.shape[1]] = small
        d2 = {}
        fs2 = M.detect_faces(dup2, YUNET)
        w2 = _dup_inliers(dup2, fs2, d2)
        checks.append(("D-50px-dup", len(fs2) > len(faces) and w2 >= LIM_DUP))
        # ... while the MONKEY_S false positive - a 20 px blurred blob - is
        # reported UNMEASURABLE (too few descriptors), not as a duplicate
        sift = cv2.SIFT_create()
        g = cv2.cvtColor(rgb[y:y + fh, x:x + fw], cv2.COLOR_RGB2GRAY)
        big = sift.detectAndCompute(cv2.resize(g, (160, 160)), None)
        blob = cv2.resize(cv2.resize(g, (20, 22), interpolation=cv2.INTER_AREA), (160, 160))
        k_b, d_b = sift.detectAndCompute(blob, None)
        n_blob = 0 if d_b is None else len(d_b)
        checks.append(("D-floor-blob-unmeasurable", n_blob < MIN_DESC <= len(big[1])))
        # (D-50px-dup above already proves the fit check does not blind D to a
        # real small duplicate: an inlier count survives only on a valid fit.)

    # The false positive that got PAST the descriptor floor (MONKEY_audit_now_ul,
    # 2026-09-01): the monkey vs a 24 px gallery face, saved as a fixture. It
    # must still reproduce the mechanism (>= LIM_DUP raw RANSAC inliers on
    # >= MIN_DESC descriptors both sides - otherwise the control proves
    # nothing) and must score 0 after the fit check.
    fx = os.path.join(ROOT, "tools", "fixtures", "gateD_falsepos_monkey_vs_24px_gallery.png")
    if os.path.exists(fx):
        pair = cv2.imread(fx, cv2.IMREAD_GRAYSCALE)
        sift = cv2.SIFT_create()
        ka, da = sift.detectAndCompute(pair[:, :160], None)
        kb, db = sift.detectAndCompute(pair[:, 160:], None)
        gg = {}
        inl, good = _pair_inliers(ka, da, kb, db, geom=gg)
        reproduced = (da is not None and db is not None and min(len(da), len(db)) >= MIN_DESC
                      and gg.get("raw_inliers", 0) >= LIM_DUP)
        checks.append(("D-falsepos-fixture-reproduces", reproduced))
        checks.append(("D-falsepos-rejected-by-fit", reproduced and inl == 0 and not gg.get("valid", True)))
    else:
        checks.append(("D-falsepos-fixture-present", False))

    clean_ok = not (M.flat_g_p90(rgb) > LIM_FLAT)
    checks.append(("clean-ref-passes-A", clean_ok))

    ok = all(c for _, c in checks)
    print(("SELFTEST_PASS  " if ok else "SELFTEST_FAIL  ") +
          " ".join(f"{n}={'ok' if c else 'BLIND'}" for n, c in checks))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    bad = 0
    for f in [a for a in sys.argv[1:] if not a.startswith("-")]:
        ok, _ = score(f)
        bad += 0 if ok else 1
    raise SystemExit(1 if bad else 0)
