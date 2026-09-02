# -*- coding: utf-8 -*-
"""R44 - a cutout that shipped is saved back, so the next build starts from
the best of everything harvested so far instead of from zero.

Nathan, 2026-08-31 (#178, said twice): "we should have a library of screenshots
of boyd reactions and a library of the plates so we don't have to keep
regenerating things every time"

Two libraries, both WIRED - say which function reads each:

    plates     assets/harvest/backgrounds/<CASE>/bg_<CASE>_<t>.png + index.json
               WIRED. tools/thumb_pipeline.py pick_clean_plate() ranks every
               plate across every case on every build (tools/harvest.py
               backgrounds fills it).
    reactions  assets/harvest/reactions/boyd/boyd_<CASE>_<tag>.png + index.json
               WIRED 2026-09-01. tools/thumb_pipeline.py judge_from_library()
               reads it inside prep(): a case whose own approved cutout is in
               the library reuses it and the judge's grab / HYPIR / regenerate /
               matte stages are skipped; a case with no entry of its own ranks
               the usable cutouts against the video search by
               tools/expression.py score and the library wins on ties. Until
               2026-09-01 this half was SEEDED, NOT READ - every build still
               re-cut Boyd from the reaction frame. wired_state() proves the
               reading function is still present in thumb_pipeline.py rather
               than asserting it.

    python tools/library.py seed-boyd          # approved judge cutouts -> reactions library
    python tools/library.py list               # both libraries, counts and the wired state
    python tools/library.py --selftest

seed-boyd copies <thumbwork>/<CASE>/judge_surgical.png for every case in
config/quality_floor.json["approved"] (the accepted five - the floor, never
AUTOTEST) into the reactions library as boyd_<CASE>_approved.png with its face
box from faces.json and, when mediapipe loads, its 52 blendshapes and the
expression profile it best fits (tools/expression.py). The COPY is idempotent
on bytes (an entry whose source has not changed is not re-copied); the
expression block, the usability and the case facts are REFRESHED on every run,
because a recalibrated tools/expression.py never reached the index while the
whole row was skipped with the copy.

Usability. Every entry carries `usable` and `defects`, read from
config/quality_floor.json["gate_disagreements"][CASE] - the gates the floor
file declares against that case's accepted build. MONKEY declares F, J, K; K is
a severed matte (R29, measured 2026-09-01: judge matte severed at x=1239, a
203px pixel-straight edge), and a cutout with K is never reused. Entries with
defects stay in the index (they are the floor's record) but are never picked.

Only `kind: approved_cutout` rows are ever picked. tools/harvest.py reactions
writes raw frames into the same index without a `kind` - those are frames, not
cutouts, and are not candidates.
"""
import hashlib
import json
import os
import shutil
import sys

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
THUMBWORK = "D:/Boyd Clips/thumbwork"
PLATES = os.path.join(ROOT, "assets", "harvest", "backgrounds")
REACTIONS = os.path.join(ROOT, "assets", "harvest", "reactions", "boyd")
FLOOR = os.path.join(ROOT, "config", "quality_floor.json")
CASES = os.path.join(ROOT, "config", "cases.json")
PIPELINE = os.path.join(ROOT, "tools", "thumb_pipeline.py")
CUTOUT = "approved_cutout"
# The five were accepted on 2026-08-31 (P46, "the floor and minimum quality");
# a row keeps the date it was first seeded with, this is only the default.
APPROVED_ON = "2026-08-31"
# The function in tools/thumb_pipeline.py that reads this library. list/seed
# print WIRED only after wired_state() finds it in the file - a claim that is
# checked, not remembered.
WIRED_BY = "judge_from_library"
NOT_WIRED = (f"reactions library is NOT read by tools/thumb_pipeline.py - "
             f"{WIRED_BY}() is missing from it, so every build re-cuts Boyd "
             f"from the reaction frame")
# what the last seed_boyd() did, for the selftest and for callers that need
# more than the rows
LAST = {}


def _floor():
    return json.load(open(FLOOR, encoding="utf-8"))


def approved_cases():
    return list(_floor().get("approved", []))


def cases():
    if not os.path.exists(CASES):
        return {}
    return json.load(open(CASES, encoding="utf-8"))


def floor_defects(case):
    """Gate letters config/quality_floor.json declares against this case's
    accepted build - MONKEY: ['F', 'J', 'K'] as of 2026-09-01."""
    gd = _floor().get("gate_disagreements") or {}
    d = gd.get(case) or {}
    return sorted(k for k in d if k != "note")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tag_expression(png_path):
    """52 blendshapes + best-fitting profile for an RGBA cutout, or None with
    the reason when mediapipe is not available. The cutout is laid on mid grey
    so the landmarker sees a face, not a transparent hole."""
    try:
        import expression as ex
    except Exception as e:                                   # pragma: no cover
        return None, f"tools/expression.py did not import: {e}"
    im = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
    if im is None:
        return None, "unreadable"
    if im.ndim == 3 and im.shape[2] == 4:
        a = im[..., 3:4].astype(np.float32) / 255.0
        bgr = (im[..., :3].astype(np.float32) * a + 128.0 * (1 - a)).astype(np.uint8)
    else:
        bgr = im[..., :3]
    # the landmarker is happiest well under 2000 px on the long side
    s = 1600.0 / max(bgr.shape[:2])
    if s < 1.0:
        bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    try:
        faces = ex.blendshapes(bgr)
    except Exception as e:
        return None, f"mediapipe did not run: {str(e).splitlines()[0][:120]}"
    if not faces:
        return None, "no face found on the cutout"
    f = max(faces, key=lambda r: r["box"][2] * r["box"][3])
    shapes = f["shapes"]
    scored = {p: round(ex.score(shapes, p), 3) for p in ex.PROFILES}
    best = max(scored, key=scored.get)
    top = sorted(((round(v, 3), k) for k, v in shapes.items()), reverse=True)[:6]
    return dict(profile=best, scores=scored, eyes_shut=bool(ex.eyes_shut(shapes)),
                top_shapes=[k for _, k in top], shapes=shapes), None


def seed_boyd(thumbwork=THUMBWORK, verbose=True):
    """Approved judge cutouts -> reactions library. Returns the index rows.

    Copy: idempotent on bytes. Tag / usability / case facts: refreshed every
    run. A run whose tagger fails (mediapipe absent, no face) keeps the
    previous shapes - they are measurements, not calibration, and losing five
    good rows to one bad import would leave the picker nothing to pick - and
    says so in expression_note."""
    os.makedirs(REACTIONS, exist_ok=True)
    idx_path = os.path.join(REACTIONS, "index.json")
    prev = json.load(open(idx_path, encoding="utf-8")) if os.path.exists(idx_path) else []
    rows = {r["file"]: r for r in prev}
    allc = cases()
    added, kept, missing, retag_failed = [], [], [], []
    for case in approved_cases():
        src = os.path.join(thumbwork, case, "judge_surgical.png")
        if not os.path.exists(src):
            missing.append(case)
            continue
        dst = os.path.join(REACTIONS, f"boyd_{case}_approved.png")
        sha = _sha(src)
        old = rows.get(dst) or {}
        if old.get("sha256") == sha and os.path.exists(dst):
            kept.append(case)
        else:
            shutil.copy2(src, dst)
            added.append(case)
        fj = os.path.join(thumbwork, case, "faces.json")
        box = json.load(open(fj, encoding="utf-8")).get("judge") if os.path.exists(fj) else None
        im = cv2.imread(dst, cv2.IMREAD_UNCHANGED)
        h, w = im.shape[:2]
        tag, why = _tag_expression(dst)
        if tag is None and old.get("expression"):
            tag = old["expression"]
            why = f"re-tag failed this run ({why}); shapes kept from the previous seed"
            retag_failed.append(case)
        defects = floor_defects(case)
        cc = allc.get(case) or {}
        raw = os.path.join(thumbwork, case, "judge_raw.png")
        row = dict(file=dst, case=case, source=src,
                   # the raw crop the cutout was restored from, so a build that
                   # takes the cutout can give verify_build gate F its "own
                   # source crop" (it reads <work>/judge_raw.png)
                   source_raw=raw if os.path.exists(raw) else None,
                   approved=old.get("approved") or APPROVED_ON,
                   kind=CUTOUT, w=w, h=h, face_box=box, sha256=sha,
                   judge_t=cc.get("judge_t"), video=cc.get("video"),
                   usable=not defects, defects=defects,
                   expression=tag, expression_note=why)
        rows[dst] = row
    out = sorted(rows.values(), key=lambda r: (r.get("case", ""), r["file"]))
    json.dump(out, open(idx_path, "w", encoding="utf-8"), indent=1, default=str)
    LAST.clear()
    LAST.update(added=added, kept=kept, missing=missing, retag_failed=retag_failed)
    if verbose:
        for r in out:
            e = r.get("expression")
            ex = f"{e['profile']} {e['scores'][e['profile']]}" if e else f"untagged ({r.get('expression_note')})"
            use = "usable" if r.get("usable") else f"UNUSABLE {r.get('defects')}"
            print(f"  {r['case']:9} {os.path.basename(r['file']):28} {r['w']}x{r['h']}  "
                  f"face {r.get('face_box')}  {ex}  {use}")
        print(f"LIBRARY_OK  reactions: {len(added)} added, {len(kept)} unchanged bytes "
              f"(all {len(out)} re-tagged"
              + (f", re-tag FAILED for {retag_failed}" if retag_failed else "")
              + ")"
              + (f", MISSING source for {missing}" if missing else "")
              + f" -> {REACTIONS}")
        print("NOTE  " + wired_state()[1])
    return out


# ---------------------------------------------------------------- picking --
def load_index(path=None):
    p = path or os.path.join(REACTIONS, "index.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def cutouts(entries=None):
    """Only the approved cutouts. Raw harvest frames carry no `kind`."""
    return [e for e in (load_index() if entries is None else entries)
            if e.get("kind") == CUTOUT]


def entry_for_case(case, entries=None):
    for e in cutouts(entries):
        if e.get("case") == case:
            return e
    return None


def reusable(entry):
    """(True, why) when a build may take this cutout as-is, else (False, why).

    Refuses, in this order: not an approved cutout; declared defects (K is a
    severed matte and is never reused); file gone; bytes changed since the
    seed (the index describes a file that no longer exists)."""
    if not entry or entry.get("kind") != CUTOUT:
        return False, "not an approved cutout"
    if not entry.get("usable", False):
        return False, f"defects {entry.get('defects') or []} declared in quality_floor.json"
    f = entry.get("file") or ""
    if not os.path.exists(f):
        return False, f"file missing: {f}"
    if entry.get("sha256") != _sha(f):
        return False, "sha256 mismatch - the file changed since it was seeded; re-run seed-boyd"
    if not entry.get("face_box"):
        return False, "no face box"
    return True, f"approved {entry.get('approved', '?')}"


def score_entry(entry, profile):
    """tools/expression.py score of this cutout for `profile`, computed LIVE
    from the stored blendshapes so a recalibrated scorer applies without a
    re-seed. None when the entry was never tagged."""
    shapes = ((entry.get("expression") or {}).get("shapes"))
    if not shapes:
        return None
    import expression as ex
    return float(ex.score(shapes, profile))


def rank(profile, entries=None, exclude_case=None):
    """Usable, reusable, scored cutouts for `profile`, best first.

    Returns (ranked, rejected): ranked is [(score, entry)], rejected is
    [(entry, why)] so the caller can print why a cutout was passed over
    rather than passing it over silently."""
    ranked, rejected = [], []
    for e in cutouts(entries):
        if exclude_case and e.get("case") == exclude_case:
            continue
        ok, why = reusable(e)
        if not ok:
            rejected.append((e, why))
            continue
        s = score_entry(e, profile)
        if s is None:
            rejected.append((e, "untagged - no blendshapes in the index"))
            continue
        ranked.append((s, e))
    ranked.sort(key=lambda t: -t[0])
    return ranked, rejected


def wired_state(pipeline=None):
    """Is the reading function actually in tools/thumb_pipeline.py, and does
    it read this module? Measured off the file, never asserted."""
    p = pipeline or PIPELINE
    try:
        src = open(p, encoding="utf-8").read()
    except OSError:
        return False, NOT_WIRED + " (thumb_pipeline.py unreadable)"
    defined = f"def {WIRED_BY}(" in src
    imports = "import library" in src
    # a CALL, not the def, a comment or a docstring line
    called = any(f"{WIRED_BY}(" in ln and not ln.strip().startswith(("def ", "#", '"', "'"))
                 for ln in src.splitlines())
    if defined and imports and called:
        return True, (f"reactions library is WIRED via tools/thumb_pipeline.py "
                      f"{WIRED_BY}() (called from prep())")
    return False, NOT_WIRED


def list_libraries(verbose=True):
    plates = {}
    if os.path.isdir(PLATES):
        for case in sorted(os.listdir(PLATES)):
            d = os.path.join(PLATES, case)
            if os.path.isdir(d):
                plates[case] = sorted(f for f in os.listdir(d)
                                      if f.lower().endswith(".png") and not f.startswith("_"))
    reactions = load_index()
    if verbose:
        n = sum(len(v) for v in plates.values())
        wired, note = wired_state()
        print(f"plates     {n} over {len(plates)} cases  {PLATES}  WIRED via tools/thumb_pipeline.py pick_clean_plate()")
        for c, fs in plates.items():
            print(f"           {c:9} {len(fs)}")
        state = f"WIRED via tools/thumb_pipeline.py {WIRED_BY}()" if wired else "NOT WIRED"
        print(f"reactions  {len(reactions)} entries  {REACTIONS}  {state}")
        for r in reactions:
            e = r.get("expression")
            ok, why = reusable(r) if r.get("kind") == CUTOUT else (False, "raw frame, not a cutout")
            print(f"           {r.get('case', '?'):9} {os.path.basename(r['file']):28} "
                  f"{(e or {}).get('profile', 'untagged'):9} "
                  f"{'pickable' if ok else 'NOT pickable: ' + why}")
        print("NOTE  " + note)
    return plates, reactions


def selftest():
    """Seeding is idempotent on bytes, re-tags every run, and a moved source is
    re-copied; a defect makes an entry unusable and the picker never returns
    it; the picker returns the best usable entry for a profile; a sha mismatch
    is not reusable. Runs on a temp thumbwork, temp library and temp floor so
    nothing real is touched. No mediapipe needed: the tagger is stubbed."""
    import tempfile
    global REACTIONS, FLOOR, _tag_expression
    ok = True
    tmp = tempfile.mkdtemp(prefix="library_")
    real = (REACTIONS, FLOOR, _tag_expression)

    def check(label, good):
        nonlocal ok
        ok = ok and bool(good)
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        return good

    try:
        REACTIONS = os.path.join(tmp, "reactions", "boyd")
        FLOOR = os.path.join(tmp, "quality_floor.json")
        # a temp floor: three approved cases, one with a declared K (the
        # MONKEY shape - severed matte, R29)
        json.dump({"approved": ["ALPHA", "BRAVO", "CHARLIE"],
                   "gate_disagreements": {"note": "selftest",
                                          "BRAVO": {"K": "severed matte (selftest)"}}},
                  open(FLOOR, "w"))
        tw = os.path.join(tmp, "thumbwork")
        for case in approved_cases():
            os.makedirs(os.path.join(tw, case))
            img = np.zeros((64, 48, 4), np.uint8)
            img[..., 3] = 255
            cv2.imwrite(os.path.join(tw, case, "judge_surgical.png"), img)
            json.dump({"judge": [1, 2, 3, 4]}, open(os.path.join(tw, case, "faces.json"), "w"))
        # stubbed tagger: shapes chosen so ALPHA reads 'speaking', CHARLIE
        # 'stern', and BRAVO (defective) out-scores both on every profile
        SHAPES = {"ALPHA": {"jawOpen": 0.9, "mouthOpen": 0.8},
                  "BRAVO": {"jawOpen": 1.0, "mouthOpen": 1.0, "browDownLeft": 1.0,
                            "browDownRight": 1.0, "mouthPressLeft": 1.0, "mouthPressRight": 1.0},
                  "CHARLIE": {"browDownLeft": 0.9, "browDownRight": 0.9,
                              "mouthPressLeft": 0.7, "mouthPressRight": 0.7}}
        tag_runs = {"n": 0}

        def fake_tag(png):
            tag_runs["n"] += 1
            case = os.path.basename(png).split("_")[1]
            return dict(profile=f"run{tag_runs['n']}", scores={}, eyes_shut=False,
                        top_shapes=[], shapes=SHAPES[case]), None
        _tag_expression = fake_tag

        rows = seed_boyd(tw, verbose=False)
        n = len(approved_cases())
        check(f"seeded {len(rows)}/{n} approved cutouts with face boxes",
              len(rows) == n and all(r["face_box"] == [1, 2, 3, 4] for r in rows))
        by = {r["case"]: r for r in rows}
        # (a) usability from the floor's gate_disagreements
        check("BRAVO (declares K) is usable=false, defects=['K']",
              by["BRAVO"]["usable"] is False and by["BRAVO"]["defects"] == ["K"])
        check("ALPHA and CHARLIE are usable=true with no defects",
              by["ALPHA"]["usable"] is True and by["CHARLIE"]["usable"] is True
              and by["ALPHA"]["defects"] == [])
        r_ok, r_why = reusable(by["BRAVO"])
        check(f"reusable(BRAVO) refuses: {r_why}", r_ok is False and "K" in r_why)
        ranked, rejected = rank("speaking", rows)
        check("picker never returns BRAVO although it out-scores every usable entry",
              all(e["case"] != "BRAVO" for _, e in ranked)
              and any(e["case"] == "BRAVO" for e, _ in rejected)
              and score_entry(by["BRAVO"], "speaking") > score_entry(by["ALPHA"], "speaking"))
        # (b) best usable entry per profile
        check("picker ranks ALPHA first for 'speaking'",
              ranked and ranked[0][1]["case"] == "ALPHA")
        ranked_s, _ = rank("stern", rows)
        check("picker ranks CHARLIE first for 'stern'",
              ranked_s and ranked_s[0][1]["case"] == "CHARLIE")
        # NEGATIVE CONTROL for (a): with BRAVO's defect cleared it is picked
        # first - proving the exclusion above came from the defect, not the score
        clean = [dict(r, usable=True, defects=[]) for r in rows]
        ranked_c, _ = rank("speaking", clean)
        check("negative control: same rows with BRAVO's defect cleared rank BRAVO first",
              ranked_c and ranked_c[0][1]["case"] == "BRAVO")
        # idempotent copy, refreshed tag
        idx = os.path.join(REACTIONS, "index.json")
        first_profile = by["ALPHA"]["expression"]["profile"]
        rows2 = seed_boyd(tw, verbose=False)
        by2 = {r["case"]: r for r in rows2}
        check(f"second seed re-copies nothing (kept {LAST['kept']}, added {LAST['added']})",
              sorted(LAST["kept"]) == ["ALPHA", "BRAVO", "CHARLIE"] and LAST["added"] == [])
        check(f"second seed re-tags every row ({first_profile} -> {by2['ALPHA']['expression']['profile']})",
              by2["ALPHA"]["expression"]["profile"] != first_profile and tag_runs["n"] == 2 * n)
        # a tagger failure keeps the previous shapes and says so
        _tag_expression = lambda png: (None, "mediapipe absent (selftest)")
        rows3 = seed_boyd(tw, verbose=False)
        by3 = {r["case"]: r for r in rows3}
        check("a failed re-tag keeps the previous shapes and notes it",
              by3["ALPHA"]["expression"]["shapes"] == SHAPES["ALPHA"]
              and "re-tag failed" in by3["ALPHA"]["expression_note"]
              and sorted(LAST["retag_failed"]) == ["ALPHA", "BRAVO", "CHARLIE"])
        _tag_expression = fake_tag
        # (c) sha mismatch -> not reusable; negative control: restore -> reusable
        a_ok, a_why = reusable(by3["ALPHA"])
        check(f"ALPHA is reusable before tampering ({a_why})", a_ok)
        lib_png = by3["ALPHA"]["file"]
        keep = open(lib_png, "rb").read()
        cv2.imwrite(lib_png, np.full((64, 48, 4), 77, np.uint8))
        a_ok, a_why = reusable(by3["ALPHA"])
        check(f"ALPHA with changed bytes is NOT reusable ({a_why})",
              a_ok is False and "sha256" in a_why)
        ranked_t, rejected_t = rank("speaking", rows3)
        check("picker skips the tampered ALPHA and reports why",
              all(e["case"] != "ALPHA" for _, e in ranked_t)
              and any(e["case"] == "ALPHA" and "sha256" in w for e, w in rejected_t))
        open(lib_png, "wb").write(keep)
        check("restored bytes are reusable again", reusable(by3["ALPHA"])[0])
        # a changed SOURCE is re-copied and the index stays the same size
        case = "ALPHA"
        img = np.full((64, 48, 4), 200, np.uint8)
        cv2.imwrite(os.path.join(tw, case, "judge_surgical.png"), img)
        rows4 = seed_boyd(tw, verbose=False)
        dst = os.path.join(REACTIONS, f"boyd_{case}_approved.png")
        check(f"changed source is re-copied (added {LAST['added']}), index stays {n}",
              cv2.imread(dst, cv2.IMREAD_UNCHANGED)[0, 0, 0] == 200 and len(rows4) == n
              and LAST["added"] == ["ALPHA"])
        # the wiring claim is measured off thumb_pipeline.py, not remembered
        w_ok, w_note = wired_state()
        check(f"thumb_pipeline.py defines and calls {WIRED_BY}(): {w_note}", w_ok)
        fake = os.path.join(tmp, "not_wired.py")
        open(fake, "w").write("def prep():\n    pass\n")
        check("negative control: a pipeline without the reader reports NOT WIRED",
              wired_state(fake)[0] is False)
    finally:
        REACTIONS, FLOOR, _tag_expression = real
        shutil.rmtree(tmp, ignore_errors=True)
    print("SELFTEST_PASS library" if ok else "SELFTEST_FAIL library")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        sys.exit(0 if selftest() else 1)
    if a[0] == "seed-boyd":
        seed_boyd()
        sys.exit(0)
    if a[0] == "list":
        list_libraries()
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
