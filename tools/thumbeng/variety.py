# -*- coding: utf-8 -*-
"""Is this the same picture you shipped last time?

The rest of the engine asks "how does this compare to the NICHE". This asks the
question nothing else does: how does it compare to YOUR OWN BACK CATALOGUE.

WHY IT EXISTS. Measured 2026-08-31 by rendering the four live Texas Trial
Tracker thumbnails at the size YouTube actually serves them (168x94) beside
Audit the Court's twelve:

    layout self-similarity   ours mean 0.32 (max 0.46)   theirs mean 0.09 (max 0.26)

Ours were one template four times - identical headline band, identical red arrow
angle, identical yellow kicker, identical two-up head crop. Attention in a feed
goes to what BREAKS the pattern of its neighbours, and a channel's own recent
uploads are part of that neighbourhood. A channel whose thumbnails are a
template competes against itself.

This is the ONLY check in the engine that is not niche-relative, and that is
deliberate: matching the niche and differing from yourself are different jobs.

MEASURED AT SIDEBAR SIZE, because that is where sameness bites. At 1280px on a
large monitor four variations of one layout look like four different images.

A CAVEAT THAT LIMITS EVERY NUMBER HERE: 2026-08-31 measurement found that NO
image feature - across 126 of them, 231 winners vs 259 losers, FDR corrected -
predicts whether a video beats its own channel. So this check does NOT claim
that self-similarity costs views. It claims only what it measures: that the
image repeats your own recent work. Whether that matters is not established.
"""
import os, glob
import numpy as np
import cv2

SIDEBAR = (168, 94)

# Derived, not chosen: sits above the competitor set's worst pair (0.26) and
# below our own mean (0.32). The FIRST version of this threshold was 0.62 and
# was invented - the selftest caught it, which is why every number here names
# its evidence.
SIM_LIMIT = 0.30


def _sidebar_gray(path_or_bgr):
    im = cv2.imread(path_or_bgr) if isinstance(path_or_bgr, str) else path_or_bgr
    if im is None:
        return None
    im = cv2.resize(im, (1280, 720), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(cv2.resize(im, SIDEBAR, interpolation=cv2.INTER_AREA),
                     cv2.COLOR_BGR2GRAY).astype(np.float32)
    return (g - g.mean()) / (g.std() + 1e-6)


def layout_sim(a, b):
    ga, gb = _sidebar_gray(a), _sidebar_gray(b)
    if ga is None or gb is None:
        return None
    return float(np.corrcoef(ga.ravel(), gb.ravel())[0, 1])


def check(candidate, history_glob, limit=SIM_LIMIT):
    """Compare one candidate against every thumbnail already shipped."""
    globs = [history_glob] if isinstance(history_glob, str) else list(history_glob)
    hist = sorted({os.path.abspath(p) for g in globs for p in glob.glob(g)})
    hist = [p for p in hist if p != os.path.abspath(str(candidate))]
    sims = []
    for h in hist:
        s = layout_sim(candidate, h)
        if s is not None:
            sims.append((round(s, 3), os.path.basename(h)))
    sims.sort(reverse=True)
    worst = sims[0] if sims else (0.0, None)
    return {
        "n_compared": len(sims),
        "max_similarity": worst[0],
        "most_similar_to": worst[1],
        "limit": limit,
        "repeats_own_work": bool(sims and worst[0] >= limit),
        "all": sims[:5],
    }


def selftest():
    """A gate that cannot fail is worse than no gate. Both directions are
    checked against controls whose answer is known before the number is read."""
    ok = True
    a = np.zeros((720, 1280, 3), np.uint8)
    cv2.rectangle(a, (80, 80), (600, 640), (255, 255, 255), -1)
    b = a.copy()
    c = np.zeros((720, 1280, 3), np.uint8)
    cv2.circle(c, (1000, 200), 150, (255, 255, 255), -1)

    same = layout_sim(a, b)
    diff = layout_sim(a, c)
    print(f"  identical images   sim={same:.3f}  (want ~1.0)")
    print(f"  different images   sim={diff:.3f}  (want well below {SIM_LIMIT})")
    if not (same is not None and same > 0.99):
        print("  FAIL an image is not similar to itself"); ok = False
    if not (diff is not None and diff < SIM_LIMIT):
        print("  FAIL two unrelated layouts score as similar"); ok = False

    # and the real controls, if they are on disk
    ours = sorted(glob.glob(r"D:/Boyd Clips/thumbwork/*/[A-Z]*_thumb.jpg"))
    comp = sorted(glob.glob(r"C:/Users/natha/Projects/boyd-clips/"
                            r"research/reference/competitor/thumbs/*.jpg"))
    if len(ours) >= 2 and len(comp) >= 2:
        def pw(s):
            v = [layout_sim(x, y) for i, x in enumerate(s) for y in s[i + 1:]]
            v = [q for q in v if q is not None]
            return float(np.mean(v)), float(np.max(v))
        om, ox = pw(ours); cm, cx = pw(comp)
        print(f"  ours       mean {om:.2f} max {ox:.2f}  (n={len(ours)})")
        print(f"  competitor mean {cm:.2f} max {cx:.2f}  (n={len(comp)})")
        if om <= cm:
            print("  FAIL does not detect that our own set is more templated")
            ok = False
    else:
        print("  (real controls not on disk - synthetic checks only)")

    print("SELFTEST_PASS variety" if ok else "SELFTEST_FAIL variety")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # every build that shipped or was accepted: the 08-29 *_thumb.jpg set, the
    # *_FINAL.jpg builds and the 2026-08-31 *_NEW.jpg floor. The old glob only
    # saw 4 files and missed all five accepted builds.
    hist = [r"D:/Boyd Clips/thumbwork/*/[A-Z]*_thumb.jpg",
            r"D:/Boyd Clips/thumbwork/*/[A-Z]*_FINAL.jpg",
            r"D:/Boyd Clips/thumbwork/*/[A-Z]*_NEW.jpg"]
    bad = 0
    for p in args:
        r = check(p, hist)
        print(f"\n{os.path.basename(p)}")
        print(f"  compared against {r['n_compared']} shipped thumbnails")
        print(f"  max similarity {r['max_similarity']} vs {r['most_similar_to']}"
              f"   limit {r['limit']}")
        if r["repeats_own_work"]:
            print("  REPEATS_OWN_WORK - this is the same layout you already shipped")
            bad += 1
    print(f"\n{'VARIETY_OK' if not bad else f'VARIETY_FAIL n={bad}'}")
    sys.exit(1 if bad else 0)
