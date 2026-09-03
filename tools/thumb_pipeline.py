# -*- coding: utf-8 -*-
"""The WHOLE thumbnail build for one case, end to end, every time.

Nathan, 2026-08-29:

  "You have to make them correctly every single time the entire thing with
   regenerating and the lighting and the background and cutting and all of that
   every single time to make a professional looking thumbnail. Go back and
   basically follow all the steps"

Before this file existed the SANCHEZ build lived as loose scratchpad scripts, so
"follow all the steps" meant remembering nine of them in order. That is exactly
how steps got skipped. This runs them in one command, and every stage is
resumable - re-running skips work whose output already exists.

    python tools/thumb_pipeline.py CARTHIEF --work D:/Boyd Clips/thumbwork/CARTHIEF

Stages (spec/THUMBNAIL_SPEC.md §5):
    1 frames   grab the judge frame and the defendant frame from the case video
    2 plate    the CLEAN harvested background (nobody standing)
    3 hypir    4x restore EACH crop on its own, caption-conditioned
    4 matte    BiRefNet + guided filter, ALPHA ONLY (never touches RGB)
    5 faces    detect - never estimate a face box from a matte
    6 build    tools/thumb.py, one linear pass
    7 gate     tools/verify_thumb.py, refuse to ship on failure

The judge's share of 1/3/4/5 is SKIPPED when the reactions library already
holds her (R44, judge_from_library): the approved cutout is copied in as
judge_surgical.png and its face box comes from the index. Plates have worked
this way since pick_clean_plate; the judge caught up 2026-09-01.

    python tools/thumb_pipeline.py NEWCASE --work ... --judge-from-library best
    python tools/thumb_pipeline.py NEWCASE --work ... --judge-from-library SANCHEZ
    python tools/thumb_pipeline.py --selftest      # library reuse, no GPU
"""
import os, sys, json, argparse, subprocess, shutil
import hashlib
import io

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

HYPIR_DIR = r"D:/AI-Models/HYPIR"
HYPIR_PY = r"C:/Users/natha/miniconda3/envs/wan2gp/python.exe"
# NOT the Fooocus venv - it has torch but NO diffusers, and HYPIR imports
# diffusers on line 2 of its sd2 enhancer. Verified 2026-08-29:
#   wan2gp   torch 2.7.1+cu128  cuda=True  diffusers 0.36.0   <- works
#   Fooocus / ComfyUI / ornith-finetune: no diffusers
HYPIR_WEIGHTS = r"D:/AI-Models/HYPIR/weights/HYPIR_sd2.pth"
# Manojb/ is a mirror of stabilityai/stable-diffusion-2-1-base and is what is
# already in the HF cache on this machine - using the stabilityai id would
# trigger a fresh multi-GB download for no benefit.
HYPIR_BASE = "Manojb/stable-diffusion-2-1-base"
LORA_MODULES = ("to_k,to_q,to_v,to_out.0,conv,conv1,conv2,conv_shortcut,"
                "conv_out,proj_in,proj_out,ff.net.2,ff.net.0.proj")
YUNET = os.path.join(ROOT, "models", "yunet2023.onnx")
QUIET = r"D:/Boyd Clips/READY-TO-POST/QUIET"
PLATE_TRIM = 0.04   # fraction cropped off each edge of a harvested plate


def cases():
    return json.load(open(os.path.join(ROOT, "config", "cases.json"), encoding="utf-8"))


def sh(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd[:6]), "...")
    subprocess.run(cmd, check=True, **kw)


# ------------------------------------------------------------- 0 auto-crop --
FACE_FRAC_TARGET = 0.42   # face height as a share of the crop height

def autocrop(video, t, region, target=FACE_FRAC_TARGET):
    """Recompute a subject crop so the FACE is `target` of its height.

    thumb.cut() scales each layer so the detected face becomes FACE_H, so if a
    crop frames a lot of body the whole silhouette renders far too large and the
    heads leave the frame. Measured 2026-08-29/30:
        MONKEY  defendant face = 30% of its crop -> giant cropped heads
        OFFERUP defendant face = 23% of its crop -> same defect
        CARTHIEF (which composed correctly)      = 36%
    Hand-fixing this per case is how it keeps coming back, so it is computed.

    `region` is (x, y, w, h) of the FULL frame in which this subject lives - it
    must exclude the other people in the tile. On MONKEY the first attempt
    framed the attorney instead of the defendant because the attorney had the
    larger face in the region.
    """
    import cv2, subprocess as sp, tempfile
    rx, ry, rw, rh = region
    tmp = os.path.join(tempfile.gettempdir(), "_autocrop_probe.png")
    sp.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video,
            "-frames:v", "1", tmp], check=True)
    fr = cv2.imread(tmp)
    sub = fr[ry:ry + rh, rx:rx + rw]
    h, w = sub.shape[:2]
    det = cv2.FaceDetectorYN.create(YUNET, "", (w, h), 0.6, 0.3, 5000)
    det.setInputSize((w, h))
    _, r = det.detect(sub)
    if r is None or not len(r):
        raise SystemExit(f"autocrop: no face at t={t} in region {region}")
    f = max(r, key=lambda f: f[3])
    fx, fy, fw, fh = [int(v) for v in f[:4]]
    ch = int(fh / target); cw = int(ch * 0.95)
    cx = rx + fx + fw // 2
    cy = ry + fy + int(fh * 0.62)          # bias down: keep chest, lose ceiling
    H_, W_ = fr.shape[:2]
    x0 = max(0, min(W_ - cw, cx - cw // 2))
    y0 = max(0, min(H_ - ch, cy - ch // 2))
    spec = f"{cw}:{ch}:{x0}:{y0}"
    print(f"  autocrop t={t}: face {fw}x{fh} ({fh/rh*100:.0f}% of region) -> {spec} "
          f"(face becomes {fh/ch*100:.0f}% of crop)")
    return spec


def _face_in(I, fr, region, exclude=None, near_x=None):
    """The largest face inside `region`, excluding one already-claimed row."""
    rows = I.faces_in(fr)
    if exclude is not None:
        ex = tuple(int(round(v)) for v in exclude[:4])
        rows = [r for r in rows if tuple(int(round(v)) for v in r[:4]) != ex]
    if region:
        rx, ry, rw, rh = region
        rows = [r for r in rows
                if rx <= r[0] + r[2] / 2 <= rx + rw and ry <= r[1] + r[3] / 2 <= ry + rh]
    if not rows:
        return None
    if near_x is not None:
        return min(rows, key=lambda r: abs(r[0] + r[2] / 2 - near_x))
    return max(rows, key=lambda r: r[3])


def crop_from_face(face_row, frame_shape, target=FACE_FRAC_TARGET):
    """A crop spec framing one ALREADY-IDENTIFIED face at `target` of its height.

    This is autocrop()'s geometry with the guesswork removed. autocrop took a
    region and re-detected inside it, picking the largest face - which its own
    docstring records framing the attorney instead of the defendant on MONKEY.
    Once the right face is known, there is nothing left to pick.
    """
    fx, fy, fw, fh = [int(v) for v in face_row[:4]]
    ch = int(fh / target)
    cw = int(ch * 0.95)
    cx = fx + fw // 2
    cy = fy + int(fh * 0.62)           # bias down: keep chest, lose ceiling
    H_, W_ = frame_shape[:2]
    x0 = max(0, min(W_ - cw, cx - cw // 2))
    y0 = max(0, min(H_ - ch, cy - ch // 2))
    return f"{cw}:{ch}:{x0}:{y0}"


def solve_crops(case, c, video, off, skip=()):
    """Fill in judge_crop / plate_crop for a case that omits them.

    `skip` names crops not to derive - prep() passes ("judge_crop",) when the
    judge comes from the reactions library, because deriving her crop means
    reading a frame she is not going to be cut from.

    The chain that finally closes autonomy:

        frame -> detect every face -> RECOGNISE Boyd -> crop each face

    An earlier version routed through tile detection and an `expression_side`
    constant. Measured against the five approved cases it put CARTHIEF's judge
    crop 646px off, because Boyd sits on the LEFT there - see tools/identity.py.
    Recognition is 5/5 leave-one-out on those same cases.

    Returns a copy; never overwrites a value the case already carries, because
    re-deriving under work Nathan has signed off is how a "fix" silently moves a
    shipped file.
    """
    need = [k for k in ("judge_crop", "plate_crop") if not c.get(k) and k not in skip]
    if not need:
        return c
    import identity as I
    import tiles as T
    out = dict(c)
    for key, tkey in (("judge_crop", "judge_t"), ("plate_crop", "plate_t")):
        if key not in need:
            continue
        t = c[tkey] - off
        fr = T.frame_at(video, t)
        if fr is None:
            raise SystemExit(f"solve_crops: no frame at t={t}")
        jrow, sc = I.find_judge(fr)
        if jrow is None:
            raise SystemExit(f"solve_crops: no face at t={t}; author {key} by hand")
        if key == "judge_crop":
            row, who = jrow, f"Boyd (cos={sc:.3f})"
        else:
            # Constrain to the tile Zoom is outlining as the active speaker.
            # Without this the defendant is "the largest non-Boyd face", which
            # is exactly how MONKEY framed the attorney - autocrop's own
            # docstring records that failure. The border is 5/5 on the approved
            # cases; see tiles.active_tile.
            at = T.active_tile(fr)
            # WHICH person in that tile is the defendant is NOT in the image.
            # Measured: on MONKEY the tile holds the defendant AND their
            # attorney, and the attorney's face is the larger (97px vs 73px), so
            # "largest face" picks the wrong one - the exact failure autocrop's
            # docstring records. Mouth-motion did not separate them either.
            # It is a fact about the CASE, so it stays one hand-authored number:
            # `defendant_at`, the x position of the defendant as a fraction of
            # frame width. One number a human can eyeball, replacing four typed
            # coordinates. Absent, the largest face in the speaking tile is used
            # and the choice is printed so it can be checked.
            hint = c.get("defendant_at")
            row = _face_in(I, fr, at, exclude=jrow,
                           near_x=None if hint is None else hint * fr.shape[1])
            who = (f"defendant_at={hint}" if hint is not None
                   else "largest face in the speaking tile (UNHINTED - check it)")
            if row is None:
                raise SystemExit(
                    f"solve_crops: no defendant face at plate_t={t}; "
                    f"pick a plate_t with the defendant speaking, or author "
                    f"plate_crop by hand")
        out[key] = crop_from_face(row, fr.shape)
        print(f"  solve_crops: {key} <- {who} at "
              f"({row[0] + row[2] / 2:.0f},{row[1] + row[3] / 2:.0f}) -> {out[key]}")
    return out


# ---------------------------------------------------------------- 1 frames --
def grab(video, t, crop, out):
    """One frame at t, cropped to w:h:x:y, at source resolution."""
    if os.path.exists(out):
        print(f"  [skip] {os.path.basename(out)}")
        return out
    w, h, x, y = [int(v) for v in crop.split(":")]
    sh(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video,
        "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}", out])
    return out


# ----------------------------------------------------------------- 3 hypir --
def hypir(src_png, out_png, caption, upscale=4):
    """4x restore ONE crop, with a caption describing THAT crop.

    Per-crop, never on the composite: HYPIR is caption-conditioned, so a crop
    captioned for a face spends its capacity on that face instead of on the
    whole courtroom. (spec R28 / §8.6)
    """
    if os.path.exists(out_png):
        print(f"  [skip] {os.path.basename(out_png)}")
        return out_png
    # THE STAGING DIRS MUST BE UNIQUE PER RUN, NOT PER TAG.
    # `tag` is the output BASENAME ("defendant_hypir"), which is identical for
    # every case, so two builds running at once shared `_in_defendant_hypir` /
    # `_out_defendant_hypir` - and this function rmtree's both on entry. The
    # second build deleted the first build's result between HYPIR writing it
    # and the copy below, and the first build died on "HYPIR produced nothing"
    # with the model's own "Done. Enjoy your results in ..." still in its log.
    # Measured 2026-09-02 building LOPEZGONZALEZ while four sibling agents
    # built PERKINS / GARCIA_J / CLAYTON / PACE. The work dir is what actually
    # distinguishes one build from another, so it goes into the name.
    tag = os.path.splitext(os.path.basename(out_png))[0]
    uniq = hashlib.sha1(
        os.path.abspath(out_png).encode("utf-8", "replace")).hexdigest()[:10]
    lq = os.path.join(HYPIR_DIR, f"_in_{tag}_{uniq}")
    hq = os.path.join(HYPIR_DIR, f"_out_{tag}_{uniq}")
    shutil.rmtree(lq, ignore_errors=True)
    shutil.rmtree(hq, ignore_errors=True)
    os.makedirs(lq, exist_ok=True)
    shutil.copy(src_png, os.path.join(lq, "img.png"))
    sh([HYPIR_PY, "test.py",
        "--base_model_type", "sd2",
        "--base_model_path", HYPIR_BASE,
        "--model_t", "200", "--coeff_t", "200",
        "--lora_rank", "256", "--lora_modules", LORA_MODULES,
        "--weight_path", HYPIR_WEIGHTS,
        "--lq_dir", lq, "--output_dir", hq,
        "--upscale", str(upscale),
        "--captioner", "fixed", "--fixed_caption", caption],
       cwd=HYPIR_DIR)
    produced = os.path.join(hq, "result", "img.png")
    if not os.path.exists(produced):
        raise SystemExit(f"HYPIR produced nothing at {produced}")
    shutil.copy(produced, out_png)
    shutil.rmtree(lq, ignore_errors=True)
    shutil.rmtree(hq, ignore_errors=True)
    return out_png


# ----------------------------------------------------------------- 4 matte --
MATTE_MODEL = "birefnet-portrait"
MATTE_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]
# Alpha contrast, floor and ceiling. Until 2026-08-31 this was (26, 232): every
# alpha below 26 crushed to zero - the faint hair the matting model exists to
# produce. verify_build gate E(source) asserts these stay gentle; a build
# cannot pass the gates with the crush back in.
ALPHA_FLOOR = 6.0
ALPHA_CEIL = 246.0


def _stray_island_px():
    """The stray-alpha-island threshold, read from the gate that refuses it.

    ONE source of truth with `verify_build.MIN_STRAY_COMPONENT` - a second
    constant here would drift the moment the gate is retuned. The import is
    lazy because verify_build imports THIS module (inside its own functions),
    so a module-level import would be a cycle.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import verify_build
        return int(verify_build.MIN_STRAY_COMPONENT)
    except Exception:
        return 4000


def matte(src, dst):
    """TRUE ALPHA MATTING, not segmentation. See tools/matting.py for why.

    Nathan, 2026-08-31: "every single thumbnail had very low effort cut outs" -
    which also means every threshold calibrated off those mattes was calibrated
    off the low bar. The model class was wrong, not the settings: birefnet
    -general/-portrait answer "is this pixel the subject" (segmentation);
    hair needs "how much of this pixel is the subject" (matting).

    Falls back to the segmentation path only if the matting model is absent, and
    says so out loud rather than silently producing worse cut-outs.

    ALPHA ONLY - a matte that changes RGB is a bug, verified byte-identical on
    SANCHEZ. bria-rmbg stays banned: CC BY-NC, and this channel is monetised.
    """
    # R56, 2026-09-03: the skip must be STALENESS-AWARE, not existence-only.
    # The colour correction writes a NEW input (`<who>_colour.png`) beside the
    # HYPIR crop, so on any work dir that already had a matte from an earlier
    # build the matte was skipped and the corrected pixels were never consumed:
    # measured on PERKINS, `defendant_colour.png` sat at skin chroma 19.2 while
    # `_placed_rgb_defendant.png` came out at 13.9 - the uncorrected 14.2. The
    # build looked like it applied R56 (the log printed the correction) and did
    # not. An existence check answers "has this ever been made", never "is it
    # still made from THIS input".
    if os.path.exists(dst):
        if os.path.getmtime(dst) >= os.path.getmtime(src):
            print(f"  [skip] {os.path.basename(dst)}")
            return dst
        print(f"  [stale] {os.path.basename(dst)} is older than "
              f"{os.path.basename(src)} - re-matting")
    import numpy as np, cv2
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import matting

    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    if matting.available():
        a = matting.alpha(bgr)
        engine = "birefnet-matting"
    else:
        print("  WARNING matting model absent - falling back to segmentation")
        from rembg import remove, new_session
        sess = new_session(MATTE_MODEL, providers=MATTE_PROVIDERS)
        w, h = im.size
        cap = 2048
        small = im if w <= cap else im.resize((cap, int(h * cap / w)), Image.LANCZOS)
        raw = np.asarray(remove(small, session=sess, post_process_mask=False).split()[-1])
        raw = cv2.resize(raw, (w, h), interpolation=cv2.INTER_LINEAR)
        a = cv2.ximgproc.guidedFilter(bgr, raw, radius=8, eps=1e-4 * 255 * 255)
        engine = MATTE_MODEL

    # Gentle contrast only. The line here used to be (a-26)*255/(232-26), which
    # crushed every alpha below 26 to zero - i.e. exactly the faint hair the
    # matting model exists to produce. ALPHA_FLOOR / ALPHA_CEIL, gated.
    a = np.clip((a.astype(np.float32) - ALPHA_FLOOR) * (255.0 / (ALPHA_CEIL - ALPHA_FLOOR)), 0, 255)
    a = a.astype(np.uint8)
    # ONE SUBJECT PER MATTE (R8 / verify_build gate L: "it looks weird how his
    # lawyer is right behind judge boyd"). Gate L has always REFUSED a stray
    # alpha island >= MIN_STRAY_COMPONENT px, and nothing on the build path ever
    # removed one - so the rule was a rejection with no fix, and the only way
    # past it was to hunt for a frame the matting model happened to miss the
    # bystander in. Measured 2026-09-02 on LOPEZGONZALEZ: the defendant's matte
    # carried a second island of 19,708 px - a woman in the gallery holding a
    # folder, 750 px clear of him - so the build failed L. A component that
    # does not touch the subject is by definition not the subject, and dropping
    # it is alpha-only, so it cannot be a hard cut of him (gate K still judges
    # that). Keep the largest component; drop any other >= the gate's own
    # threshold, out loud. Smaller islands are left alone - they are the faint
    # hair and edge specks the matting model exists to produce, and the accepted
    # five carry a largest secondary island of 12 px.
    _stray_px = _stray_island_px()
    _n, _lab, _st, _ = cv2.connectedComponentsWithStats((a > 8).astype(np.uint8), 8)
    if _n > 2:
        _areas = [(_st[i, cv2.CC_STAT_AREA], i) for i in range(1, _n)]
        _areas.sort(reverse=True)
        _dropped = [(ar, i) for ar, i in _areas[1:] if ar >= _stray_px]
        for _ar, _i in _dropped:
            a[_lab == _i] = 0
        if _dropped:
            print(f"  matte {os.path.basename(dst):28} dropped "
                  f"{len(_dropped)} stray island(s) "
                  f"({', '.join(str(int(ar)) + 'px' for ar, _ in _dropped)}) - "
                  f"not connected to the subject (R8 / gate L)")
    # A tile-seam cliff in this matte (R29) is NOT patched here: thumb.cut()
    # grows the layer until the cut leaves the canvas - see thumb.find_cliff.
    Image.fromarray(np.dstack([rgb, a])).save(dst)
    soft = int(((a > 8) & (a < 248)).sum())
    print(f"  matte {os.path.basename(dst):28} [{engine}] coverage {(a>8).mean()*100:5.1f}%"
          f"  soft-edge {soft}")
    return dst


# ----------------------------------------------------------------- 5 faces --
def face_of(png, at=None):
    """Detect the SUBJECT's face. NEVER estimate a box from a matte.

    `at` is where the subject sits across the crop, 0.0 = left edge, 1.0 = right.
    Without it this picks the largest face, and that has now chosen the WRONG
    PERSON three times:
      MONKEY   the attorney had the larger face in the tile
      OFFERUP  ditto, plus plate_t pointed past the end of the hearing entirely
      CARTHIEF the attorney measured 80px against the defendant's 77px - a
               three-pixel margin decided who appeared in the thumbnail
    A courtroom crop nearly always contains counsel standing beside the
    defendant, so "largest face" is not a safe default. State the position.
    """
    import cv2
    bgr = cv2.imread(png)
    if bgr is None:
        raise SystemExit(f"cannot read {png}")
    if bgr.shape[2] == 4:
        bgr = bgr[:, :, :3]
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(YUNET, "", (w, h), 0.6, 0.3, 5000)
    det.setInputSize((w, h))
    _, raw = det.detect(bgr)
    if raw is None or not len(raw):
        raise SystemExit(f"no face detected in {png} - pick another frame, do not estimate")
    cands = [r for r in raw if r[2] * r[3] >= 0.15 * max(x[2] * x[3] for x in raw)]
    if at is None:
        r = max(cands, key=lambda r: r[3])
        how = "largest"
    else:
        r = min(cands, key=lambda r: abs((r[0] + r[2] / 2) / w - at))
        how = f"nearest to x={at:.2f}"
    box = tuple(int(v) for v in r[:4])
    print(f"  face {os.path.basename(png):26} {box}  score {r[14]:.2f}  "
          f"centre_frac {(r[0]+r[2]/2)/w:.2f}  ({how}, {len(cands)} candidates)")
    return box


# ----------------------------------------------------------- 2 clean plate --
def faces_in_file(png, thresh=0.55):
    import cv2
    bgr = cv2.imread(png)
    if bgr is None:
        return 99
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(YUNET, "", (w, h), thresh, 0.3, 5000)
    det.setInputSize((w, h))
    _, r = det.detect(bgr)
    return 0 if r is None else len(r)


def pick_clean_plate(case, dst):
    """Choose a background plate from the SHARED library.

    History, because it was mis-diagnosed twice:
      1. QUIET/CARTHIEF.jpg was never a plate - it was a frame from an EDITED
         video still holding the defendant, his attorney, burned-in subtitles
         and a 187th DC bug. Gate D blocked it at 9 SIFT inliers.
      2. "A plate must have ZERO faces" is WRONG - his approved SANCHEZ
         thumbnail sits on a plate with 9-12 detected faces. Gallery strangers
         are normal courtroom; the defect is OUR SUBJECT appearing twice, which
         is what Gate D measures.
      3. The plate is a SHARED asset, not per-case. MONKEY has no empty moment
         at all - counsel stands in that tile for the entire hearing.

    Ranked by flatness AFTER the 1.6 blur, which is what Gate A actually
    measures - not by Laplacian detail, which disagrees (spec 12.8).
    """
    import cv2, glob
    from PIL import Image
    root = os.path.join(ROOT, "assets", "harvest", "backgrounds")
    cands = []
    for fp in glob.glob(os.path.join(root, "*", "*.png")):
        if os.path.basename(fp).startswith("_"):
            continue
        im = cv2.imread(fp)
        if im is None:
            continue
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        sd = float(g.std())
        if sd < 5.0:
            print(f"  plate {os.path.basename(fp):26} REJECTED blank/sting (sd {sd:.1f})")
            continue
        w0, h0 = im.shape[1], im.shape[0]
        m = PLATE_TRIM
        tr = im[int(h0 * m):int(h0 * (1 - m)), int(w0 * m):int(w0 * (1 - m))]
        r = cv2.resize(tr, (1280, 720), interpolation=cv2.INTER_LANCZOS4)
        b = cv2.GaussianBlur(r.astype("float32"), (0, 0), 1.6)
        import numpy as _np
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import thumb_metrics as _M
        flat = _M.flat_g_p90(cv2.cvtColor(_np.clip(b, 0, 255).astype("uint8"), cv2.COLOR_BGR2RGB))
        cands.append((flat, fp, tr))
    if not cands:
        raise SystemExit(f"no usable plate - run: python tools/harvest.py backgrounds {case} --n 8")
    cands.sort(key=lambda t: t[0])
    for flat, fp, _ in cands[:4]:
        print(f"  plate {os.path.basename(fp):26} flat_after_blur {flat:.4f}")
    flat, best, tr = cands[0]
    print(f"  using {os.path.basename(best)}  flat_after_blur {flat:.4f}, "
          f"trimmed {PLATE_TRIM*100:.0f}% (removes the burned-in court label)")
    Image.fromarray(cv2.cvtColor(tr, cv2.COLOR_BGR2RGB)).save(dst)
    return dst


# -------------------------------------------------- 1b judge from library --
JUDGE_SIDECAR = "judge_source.json"   # written beside judge_surgical.png when
                                      # the judge came from the library


def _read_sidecar(work):
    """The record of a judge taken from the library on an earlier run, or
    None. Anything that is not that record (missing, unreadable, or not a
    library take) reads as None, so a caller never branches on a stray file."""
    p = os.path.join(work, JUDGE_SIDECAR)
    try:
        side = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return side if isinstance(side, dict) and side.get("source") == "library" else None


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _take_library_judge(entry, work, why):
    """Put the library cutout where the matte stage would have written it,
    give verify_build gate F the crop it was restored from, and record where
    it came from.

    judge_raw.png ends up as THIS entry's `source_raw` (or absent when the
    index has none). Gate F measures each face's skin chroma against its OWN
    source crop and reads <work>/judge_raw.png for hers - so a raw crop left
    behind by another cutout, or by a video path that never finished, would
    make F measure Boyd against a frame she was not cut from and report a
    drift that is not there. Whatever is replaced here is a one-frame ffmpeg
    grab or an earlier library copy - both re-creatable from the video or the
    index - and the replacement is printed, never silent. Verified 2026-09-01
    on the approved SANCHEZ thumbwork: its judge_raw.png IS the index's
    source_raw (same file), so nothing under a signed-off build moves."""
    import library as L
    jsurg = os.path.join(work, "judge_surgical.png")
    name = os.path.basename(entry["file"])
    if os.path.exists(jsurg) and L._sha(jsurg) == entry["sha256"]:
        print(f"  [skip] judge_surgical.png (already {name})")
    else:
        shutil.copy2(entry["file"], jsurg)
        print(f"  copied {name} -> judge_surgical.png")
    raw = entry.get("source_raw")
    raw = raw if raw and os.path.exists(raw) else None
    jraw = os.path.join(work, "judge_raw.png")
    have = os.path.exists(jraw)
    if raw and have and (_same_file(raw, jraw) or L._sha(jraw) == L._sha(raw)):
        pass                                        # already her source crop
    elif raw:
        shutil.copy2(raw, jraw)
        print(f"  {'replaced' if have else 'copied'} judge_raw.png with the source crop of "
              f"{name} (verify_build gate F reads it)")
    elif have:
        os.remove(jraw)
        print(f"  removed judge_raw.png - it was not the source crop of {name} and the index "
              f"has none for it; verify_build gate F will skip the judge")
    else:
        print(f"  no source crop on disk for {name} - verify_build gate F will skip the judge")
    rec = dict(source="library", file=entry["file"], case=entry.get("case"),
               sha256=entry["sha256"], face_box=entry.get("face_box"),
               approved=entry.get("approved"), source_raw=raw, why=why)
    json.dump(rec, open(os.path.join(work, JUDGE_SIDECAR), "w"), indent=1)
    return rec


def judge_from_library(case, c, work, judge_source=None, headline=None, search=None):
    """Does Boyd come from assets/harvest/reactions/boyd/ or get re-cut from
    the video? Returns the entry to use (file, sha256, face_box, ...) or None
    for the video path. Never silent: every branch prints what it did and why.

    Nathan, 2026-08-31 (said twice): "we should have a library of screenshots
    of boyd reactions and a library of the plates so we don't have to keep
    regenerating things every time". Plates were wired first
    (pick_clean_plate reads the shared library on every build); this is the
    same shape for the judge. Until 2026-09-01 the library was seeded and
    never read.

    `judge_source` - cases.json `judge_source`, or --judge-from-library:
      'video'          re-cut from the video; the library is ignored, out loud
      'library:<CASE>' THAT case's approved cutout, whatever case is being
                       built and whatever is already in the work dir from an
                       earlier library take; refuse if it is not usable.
                       Honoured before the case's own cutout - the first
                       build of this ordered the branches the other way round
                       and `SANCHEZ --judge-from-library THOMPSON` handed back
                       SANCHEZ's Boyd without a word (refuted 2026-09-01).
      'library'        the best usable cutout for the brief's profile, the
                       case's own included (it wins ties); refuse if there is
                       none. No video search. Re-ranked on every run: a
                       cutout already in place is kept only if it is still
                       the best, and superseded out loud otherwise.
      'auto' (default) SAME CASE: the case's own approved cutout, when it is
                       usable (no floor-declared defects, file present, bytes
                       unchanged since the seed). A case with hand-typed work
                       he has signed off keeps exactly the pixels he signed
                       off - re-deriving under approved work is how a shipped
                       file silently moves (see DERIVE THE CROPS in prep). An
                       own entry that is NOT usable (MONKEY: K, a severed
                       matte, R29) sends the judge back to the video - never
                       another case's face under his signed-off case.
                       NEW CASE (no entry of its own): the usable cutouts are
                       ranked by tools/expression.py score on the profile the
                       brief implies (the same profile_for the picker uses)
                       and compared with the best frame the video search
                       finds. A library cutout is already restored, matted and
                       approved, so it wins on ties and whenever its score is
                       >= the searched frame's expression score.

    What is already in the work dir:
      - a judge taken from the library earlier leaves a judge_source.json
        sidecar. Under 'auto' that decision is not re-made while
        judge_surgical.png still matches it (resumability, as for every
        other stage). An explicit request that names a different cutout
        supersedes it, printed - it is a copy, nothing is lost.
      - a judge_surgical.png the VIDEO path produced (no sidecar) is minutes
        of HYPIR and matting, possibly signed off: it is never overwritten.
        'auto' keeps it; an explicit request that would replace it refuses
        and names what to delete.

    `search` is a zero-argument callable running the case's own expression
    search (prep's, anchored on judge_t) and returning pick_expression_t's
    (t_src, best, profile) or None; it is only called when the decision needs
    the searched score.
    """
    import library as L
    jsrc = str(judge_source or c.get("judge_source") or "auto").strip()
    if jsrc not in ("auto", "video", "library") and not jsrc.startswith("library:"):
        raise SystemExit(f"judge_source {jsrc!r}: want video | library | library:<CASE> | auto")
    jsurg = os.path.join(work, "judge_surgical.png")
    jraw = os.path.join(work, "judge_raw.png")

    def _name(e):
        return os.path.basename(e.get("file", "?"))

    def _approved(e):
        return e.get("approved", "?")

    side = _read_sidecar(work)
    in_place = bool(side) and os.path.exists(jsurg) and L._sha(jsurg) == side.get("sha256")
    own = L.entry_for_case(case)

    def _clear_to_take(e, how):
        """Before an explicit request replaces judge_surgical.png: an earlier
        LIBRARY take is a copy and is superseded out loud; a matte the VIDEO
        path produced is never overwritten - refuse and name what to delete."""
        if not os.path.exists(jsurg) or L._sha(jsurg) == e["sha256"]:
            return
        if side:
            print(f"  library: superseding {_name(side)} (in place from an earlier run: "
                  f"{side.get('why', '?')}) with {_name(e)} {how}")
            return
        raise SystemExit(
            f"library: judge_surgical.png in {work} is a matte the video path produced, not a "
            f"library copy - delete it (with judge_raw.png and judge_hypir.png) to take "
            f"{_name(e)} {how}, or drop the request to keep it")

    # A. VIDEO on request: the library is ignored, out loud
    if jsrc == "video":
        if side:
            raise SystemExit(
                f"{case}: judge_source=video, but judge_surgical.png in {work} came from the "
                f"library ({_name(side)}). Delete judge_raw.png, judge_hypir.png, "
                f"judge_surgical.png and {JUDGE_SIDECAR} there to re-cut her from the video, "
                f"or drop judge_source=video to keep the library cutout.")
        if own:
            print(f"  library: judge_source=video - own cutout {_name(own)} ignored on request")
        return None

    # B. BY NAME on request (library:<CASE>) - before the case's own cutout and
    #    before whatever an earlier run left in place
    if jsrc.startswith("library:"):
        want = jsrc.split(":", 1)[1].strip()
        e = L.entry_for_case(want)
        if e is None:
            raise SystemExit(f"library: no approved cutout for {want!r} in {L.REACTIONS} "
                             f"(python tools/library.py list)")
        ok, why = L.reusable(e)
        if not ok:
            raise SystemExit(f"library: {_name(e)} is not reusable - {why}")
        if in_place and side.get("sha256") == e["sha256"]:
            print(f"library: judge cutout {_name(e)} already in place (approved {_approved(e)}, "
                  f"{jsrc}) - nothing to redo")
            return side
        _clear_to_take(e, f"on request ({jsrc})")
        if want == case:
            print(f"library: judge cutout reused from {_name(e)} (approved {_approved(e)})")
            return _take_library_judge(e, work, "same case")
        print(f"library: judge cutout {_name(e)} (approved {_approved(e)}) taken "
              f"for {case} on request ({jsrc}); video not searched")
        return _take_library_judge(e, work, jsrc)

    # C. RESUME under 'auto': a judge already taken from the library on an
    #    earlier run is not re-decided
    if side and jsrc == "auto":
        if in_place:
            print(f"library: judge cutout already in place from {_name(side)} "
                  f"(approved {side.get('approved', '?')}, {side.get('why', '')}) - not re-decided")
            return side
        e = L.entry_for_case(side.get("case"))
        ok, why = L.reusable(e) if e else (False, "entry no longer in the index")
        if ok:
            print(f"library: judge_surgical.png missing - taking {_name(e)} again")
            return _take_library_judge(e, work, side.get("why", "resumed"))
        print(f"  library: {JUDGE_SIDECAR} names {_name(side)} but it is not reusable now "
              f"({why}) - re-cutting from the video")
        return None

    # D. SAME CASE under 'auto': the case's own approved cutout
    if own is not None and jsrc == "auto":
        ok, why = L.reusable(own)
        if ok and os.path.exists(jsurg) and L._sha(jsurg) != own["sha256"]:
            ok, why = False, ("judge_surgical.png in this work dir is a different matte "
                              "(delete it to take the library cutout)")
        if ok:
            print(f"library: judge cutout reused from {_name(own)} (approved {_approved(own)})")
            return _take_library_judge(own, work, "same case")
        print(f"  library: own cutout {_name(own)} NOT reused - {why}")
        print("  library: re-cutting from the video (on 'auto' a case with its own entry "
              "never takes another case's face)")
        return None

    # E. BEST for the brief's profile: 'library' on request (the case's own
    #    cutout competes and wins ties), or 'auto' on a NEW case, competing
    #    with the video search
    import expression as X
    hl = headline or f"{c.get('white', '')} {c.get('yellow', '')}"
    prof = X.profile_for(hl)
    ranked, rejected = L.rank(prof, exclude_case=None if jsrc == "library" else case)
    for e, why in rejected:
        print(f"  library: {_name(e)} passed over - {why}")
    if jsrc == "library":
        if not ranked:
            raise SystemExit(f"library: judge_source=library but no usable cutout for "
                             f"profile {prof!r} ({len(rejected)} passed over)")
        s, e = ranked[0]
        own_s = next((so for so, eo in ranked if own and eo.get("file") == own.get("file")), None)
        if own_s is not None and own_s >= s:          # own wins ties
            s, e = own_s, own
        if in_place and side.get("sha256") == e["sha256"]:
            print(f"library: judge cutout {_name(e)} already in place and still the best usable "
                  f"for profile {prof!r} at {s:.4f} (judge_source=library) - nothing to redo")
            return side
        _clear_to_take(e, f"(best usable for profile {prof!r} at {s:.4f}, judge_source=library)")
        if own and e.get("file") == own.get("file"):
            print(f"library: judge cutout reused from {_name(own)} (approved {_approved(own)})")
            print(f"  library: own cutout is also the best usable for profile {prof!r} at {s:.4f} "
                  f"(judge_source=library, {len(ranked) - 1} other(s) ranked)")
            return _take_library_judge(own, work, "same case")
        if own_s is not None:
            print(f"  library: own cutout {_name(own)} at {own_s:.4f} passed over for "
                  f"{_name(e)} at {s:.4f} on request (judge_source=library)")
        print(f"library: judge cutout {_name(e)} (approved {_approved(e)}) taken "
              f"for {case}: best usable for profile {prof!r} at {s:.4f} "
              f"(judge_source=library, video not searched)")
        return _take_library_judge(e, work, f"library: best for {prof!r} at {s:.4f}")
    # 'auto', a NEW case
    if os.path.exists(jsurg):
        print("  library: judge_surgical.png already in this work dir - keeping it (video path)")
        return None
    if os.path.exists(jraw):
        print("  library: judge_raw.png already in this work dir - the video path has "
              "started, keeping it")
        return None
    if not ranked:
        print(f"  library: no usable cutout for profile {prof!r} - cutting from the video")
        return None
    s, e = ranked[0]
    picked = search() if (search is not None and c.get("judge_t") is not None) else None
    if not picked:
        why = ("no judge_t to search from" if c.get("judge_t") is None
               else "the video search found no usable face")
        print(f"library: judge cutout {_name(e)} (approved {_approved(e)}) taken "
              f"for {case}: profile {prof!r} library {s:.4f}, {why}")
        return _take_library_judge(e, work, f"auto: {prof!r} {s:.4f}, {why}")
    t_src, best, _ = picked
    vs = float(best["expr"])
    if s >= vs:
        print(f"library: judge cutout {_name(e)} (approved {_approved(e)}) wins "
              f"for {case}: profile {prof!r} library {s:.4f} >= searched {vs:.4f} at "
              f"t={t_src:.0f} (already restored, matted and approved)")
        return _take_library_judge(e, work, f"auto: {prof!r} library {s:.4f} >= searched {vs:.4f}")
    print(f"  library: best cutout {_name(e)} {s:.4f} < searched {vs:.4f} at t={t_src:.0f} "
          f"for profile {prof!r} - cutting from the video")
    return None


# ------------------------------------------------------------------- main --
def prep(case, work, kicker=None, judge_source=None, regen=False):
    os.makedirs(work, exist_ok=True)
    c = cases()[case]
    video = os.path.join(ROOT, c["video"])
    off = c.get("offset", 0)

    # AUTO-PICK the judge frame by expression, when the case declares a window.
    # Runs BEFORE grab() so the chosen frame is the one actually extracted, and
    # only when judge_raw.png is absent - re-running must not silently swap the
    # face under a build that has already been approved.
    jraw = os.path.join(work, "judge_raw.png")
    jside = c.get("expression_side", "right")
    # HER WINDOW IS ANCHORED TOO. Nathan, 2026-08-31, on the SANCHEZ rebuild:
    # "the Sanchez one isn't even her". A wide search of the bench tile found an
    # ASSOCIATE JUDGE sitting in Boyd's courtroom - same bench, same robe, same
    # flowers, similar bob - and picked her.
    #
    # Face recognition does NOT save us here, and the measurement says so
    # plainly: SFace scored that other woman 0.728 against Boyd's reference,
    # while Boyd's own leave-one-out score on OFFERUP is 0.548. The impostor
    # outscores the real person, so no threshold separates them at this
    # resolution. (The earlier "5/5 leave-one-out" proved only that she was the
    # best match among faces PRESENT - not that a stranger would be rejected.)
    #
    # What is actually trustworthy is the case's own hand-verified judge_t. So
    # the search is anchored around it, exactly as the defendant's is around his
    # plate_t. Same fix, both siblings, this time.
    _picked = {}

    def _search_judge():
        """The judge's expression search, at most once per prep(). Only while
        judge_raw.png is absent (see above) and only when the case has a
        judge_t to anchor on - a case whose judge comes from the library
        needs neither judge_t nor judge_crop."""
        if "r" in _picked:
            return _picked["r"]
        _picked["r"] = None
        if os.path.exists(jraw) or c.get("judge_t") is None:
            return None
        _jt = float(c["judge_t"]) - float(c.get("offset", 0))
        jwin = c.get("judge_expression_window") or [max(1.0, _jt - 25.0), _jt + 25.0]
        jc = dict(c, expression_window=jwin)
        _picked["r"] = pick_expression_t(case, jc, None, None, side=jside,
                                         ident_ref=__import__("identity").load_reference())
        return _picked["r"]

    # THE LIBRARY FIRST (R44). Nathan, 2026-08-31, said twice: "we should have
    # a library of screenshots of boyd reactions and a library of the plates so
    # we don't have to keep regenerating things every time". The plate has
    # come from the shared library since pick_clean_plate; until 2026-09-01
    # the judge was still grabbed, HYPIRed, regenerated and matted from the
    # reaction frame on every build while five approved cutouts sat seeded in
    # assets/harvest/reactions/boyd/. `lib` is the entry she comes from, or
    # None for the video path; every judge stage below keys off it.
    lib = judge_from_library(case, c, work, judge_source, search=_search_judge)
    if lib is None:
        if c.get("judge_t") is None:
            raise SystemExit(f"{case}: no judge_t in cases.json and no library cutout "
                             f"taken - author judge_t, or set judge_source: library")
        picked = _search_judge()
        if picked:
            c = dict(c, judge_t=int(round(picked[0])))
            print(f"  expression: judge_t auto-set to {c['judge_t']}")

    # THE DEFENDANT'S FACE TOO. Nathan, 2026-08-31: "I think you should kinda
    # exaggerate in all the thumbnails slightly with their facial reactions too
    # would be good". His reaction was never expression-picked at all - the
    # picker was wired for the judge only, so plate_t stayed hand-typed. Same
    # one-of-two asymmetry as the title/kicker shadow, the arrow config and the
    # no-type-on-face assert.
    #
    # The defendant is on the other side of the 2-up, and his brief is the
    # KICKER (the payoff line about him), not the judge's headline.
    draw = os.path.join(work, "defendant_raw.png")
    # HIS window, not hers. Defaulting the defendant to the judge's search
    # window was wrong: she is on screen for the whole hearing, he is on screen
    # for HIS hearing. On OFFERUP the judge window is 200-560s while he appears
    # around 20s, so the identity filter correctly rejected every candidate and
    # the search found nothing. A span around his own plate_t is the right
    # default - he is, by definition, on screen there.
    _pt = float(c["plate_t"]) - float(c.get("offset", 0))
    dwin = (c.get("defendant_expression_window")
            or [max(1.0, _pt - 25.0), _pt + 25.0])
    if dwin and not os.path.exists(draw):
        dside = "left" if jside == "right" else "right"
        # THE KICKER IS HIS BRIEF, and it arrives on the command line, not in
        # the case file - so `c.get("kicker")` was always None and every
        # defendant search silently fell back to the judge's headline. That is
        # why asking for a scared frame produced a composed one: the profile
        # resolved from "You're why your son is struggling" -> serious.
        brief = kicker or c.get("kicker") or f"{c['white']} {c['yellow']}"
        dc = dict(c, white=brief, yellow="", expression_window=dwin)
        # WHO the defendant is, taken from the case's own hand-approved
        # plate_t/plate_crop - the one place his identity is established.
        # NO identity filter here. Measured 2026-08-31: SFace scored a
        # different judge 0.728 against Boyd's reference while Boyd's own
        # leave-one-out score was 0.548 - the impostor outscores the real
        # person, so no threshold is trustworthy at this resolution. What DOES
        # pin the right person is the pair of constraints below: a +/-25s window
        # around the case's verified plate_t, and a tight region around where
        # the subject stands. Using the recognizer on top of those only produced
        # false rejections ("NO usable face in the window") on a frame where the
        # defendant was plainly present.
        ref = None
        if True:
            # Anchor the search on where the subject stands, padded for
            # movement. A case that DERIVES its plate_crop has no typed
            # rectangle to anchor on, so derive one for this purpose too rather
            # than crashing on the missing key.
            # The region has to be TIGHT - the landmarker needs the face to
            # fill a decent share of it, and an active tile is far too wide
            # (measured: 0 faces found in a 628x323 tile, 1 in a 300x320 crop).
            # When the case derives its crop rather than typing one, derive it
            # HERE first, at the original plate_t, purely to get that rectangle.
            # The crop is solved again afterwards against whatever frame the
            # expression search settles on.
            # ONLY the plate crop is wanted here. Without skip= this call also
            # derived judge_crop, which reads c["judge_t"] - and a new case
            # whose judge just came from the library has no judge_t: KeyError
            # one line after "taken for NEWX" (refuted 2026-09-01; the judge's
            # crop is solved below, skipped when she is from the library).
            if c.get("plate_crop"):
                _spec = c["plate_crop"]
            else:
                _spec = solve_crops(case, c, video, off, skip=("judge_crop",)).get("plate_crop")
            if _spec:
                _cw, _ch, _cx, _cy = [int(v) for v in _spec.split(":")]
            else:
                _cw = _ch = 0
            if _cw and _ch:
                _px, _py = int(_cw * 0.35), int(_ch * 0.30)
                _reg = (max(0, _cx - _px), max(0, _cy - _py),
                        _cw + 2 * _px, _ch + 2 * _py)
            else:
                _reg = None
            picked = pick_expression_t(case, dc, brief, "", side=dside,
                                       ident_ref=None, region=_reg)
        if picked:
            c = dict(c, plate_t=int(round(picked[0])))
            print(f"  expression: plate_t auto-set to {c['plate_t']} ({dside} tile)")

    # DERIVE THE CROPS. Nathan, 2026-08-31, asking what actually blocks me from
    # building a thumbnail on my own: the honest answer was that `cases.json`
    # holds 31 hand-authored fields and `autocrop()` - which computes three of
    # them and whose docstring cites the measurements proving it works - was
    # called by NOTHING. Same orphan shape as `assemble_final` and `expression`.
    # So making thumbnail #6 meant a human authoring case #6 first.
    #
    # A crop is now derived whenever the case OMITS it. The five approved cases
    # keep their hand-typed values untouched - re-deriving under work he has
    # already signed off is how a "fix" silently moves a shipped file - and a
    # new case needs no crop fields at all.
    c = solve_crops(case, c, video, off, skip=("judge_crop",) if lib else ())

    _lname = os.path.basename(lib["file"]) if lib else None
    print(f"[1/5] frames  judge={'library ' + _lname if lib else 't=' + str(c['judge_t'])}"
          f"  plate_t={c['plate_t']}")
    jr = None if lib else grab(video, c["judge_t"] - off, c["judge_crop"], jraw)
    dr = grab(video, c["plate_t"] - off, c["plate_crop"], os.path.join(work, "defendant_raw.png"))

    print("[2/5] clean plate")
    bg_raw = os.path.join(work, "bg_raw.png")
    if not os.path.exists(bg_raw):
        bg_raw = pick_clean_plate(case, bg_raw)

    print("[3/5] HYPIR 4x, per crop, caption-conditioned"
          + (f"  (judge skipped - {_lname} is already restored)" if lib else ""))
    if not lib:
        hypir(jr, os.path.join(work, "judge_hypir.png"),
              "a close-up photograph of a judge speaking from the bench in a courtroom, "
              "sharp facial detail, natural skin texture, high quality")
    hypir(dr, os.path.join(work, "defendant_hypir.png"),
          "a close-up photograph of a person standing in a courtroom facing the bench, "
          "sharp facial detail, natural skin texture, high quality")
    hypir(bg_raw, os.path.join(work, "bg_hypir.png"),
          "an empty courtroom interior, wooden benches, ceiling lights, "
          "sharp architectural detail, high quality", upscale=2)

    # R28 STAGE TWO: regenerate after restoring. The rules file has carried
    # "Qwen NOT AUTOMATED YET" since 2026-08-29 - this is that gap. Falls back
    # to the HYPIR frame, out loud, when the weights are absent or the identity
    # check rejects the result.
    # 2026-09-02: MEASURED AND TURNED OFF BY DEFAULT. The loader bug is fixed
    # (bitsandbytes 4-bit + device_map="balanced" raised "Cannot copy out of
    # meta tensor"; device_map="cuda" loads), so the step finally RAN - and its
    # output is worse than the HYPIR frame it replaces: speckled noise over the
    # whole crop and a different face
    # (D:/Boyd Clips/thumbwork/PACE/_regen_compare.jpg, his verdict: "left is
    # good it's something else you're doing after"). 15 minutes of model load
    # per build for a rejected result. Opt in with --regen when the weights or
    # the settings change; never silently.
    if regen:
        import regenerate as _R
        for _w in (("defendant",) if lib else ("judge", "defendant")):
            _h = os.path.join(work, f"{_w}_hypir.png")
            if os.path.exists(_h):
                _R.regenerate(_h, _h)
    else:
        print("  regenerate: OFF (measured worse than HYPIR 2026-09-02; --regen to force)")

    # R56 SKIN COLOUR. Nathan, 2026-09-03, sending a designer's before/after
    # sheet: *"when i said fix the colors this is what i meant like how
    # thumbnail makers do it"* - and, on the raw HYPIR crop, *"No I like left"*.
    # So the people are NOT to be regenerated; they are to be COLOUR CORRECTED.
    # Measured that day (tools/_colour_target.py): the PACE judge sat at skin
    # chroma 9.9 against 16.5-25.6 across all five thumbnails he has accepted -
    # less than half. That is the "grey / waxy / colourless" complaint, stated
    # as a number for the first time.
    # The HYPIR frame is NEVER overwritten - it is the thing he said he likes,
    # and every comparison since is measured against it.
    import cv2 as _cv2
    import numpy as np
    import skin_colour_fix as _S
    _subj = {}
    for _w in (("defendant",) if lib else ("judge", "defendant")):
        _h = os.path.join(work, f"{_w}_hypir.png")
        _c = os.path.join(work, f"{_w}_colour.png")
        if os.path.exists(_h):
            print(f"  {_w}:")
            _cv2.imwrite(_c, _S.fix(_cv2.imread(_h)))
            _subj[_w] = _c

    def _src_for(_w):
        return _subj.get(_w, os.path.join(work, f"{_w}_hypir.png"))

    print("[4/5] mattes (alpha only)"
          + (f"  (judge skipped - {_lname} is already matted)" if lib else ""))
    if not lib:
        matte(_src_for("judge"), os.path.join(work, "judge_surgical.png"))
    matte(_src_for("defendant"), os.path.join(work, "defendant_surgical.png"))

    print("[5/5] faces  (detected on the RAW crop, scaled by the HYPIR factor)")
    # Detect on the SOURCE crop, not the restored one. Measured 2026-08-29 on
    # MONKEY: YuNet on judge_hypir.png returned a 648px box at score 0.66 where
    # her real face is ~979px. thumb.cut() scales so the detected box becomes
    # FACE_H, so a box 34% too small rendered her face at 453px instead of 300 -
    # parity silently broken, and both people came out as giant cropped heads
    # while every gate passed. The raw crop detects at 0.91.
    def scaled(raw_png, k=4, at=None):
        b = face_of(raw_png, at=at)
        return tuple(int(v * k) for v in b)
    if lib:
        # the box the library recorded when the cutout was approved - already
        # in the cutout's own (x4) pixels, exactly what faces.json carried the
        # day it was seeded
        faces = dict(judge=tuple(int(v) for v in lib["face_box"]))
        print(f"  judge     library {faces['judge']}  (index face_box of {_lname})")
    else:
        faces = dict(judge=scaled(os.path.join(work, "judge_raw.png"), at=c.get("judge_face_at")))
        print(f"  judge     raw->x4 {faces['judge']}")
    faces["defendant"] = scaled(os.path.join(work, "defendant_raw.png"), at=c.get("plate_face_at"))
    print(f"  defendant raw->x4 {faces['defendant']}")
    json.dump(faces, open(os.path.join(work, "faces.json"), "w"), indent=1)
    print(f"\nPREP_OK  {work}")
    return faces


def _defendant_ref(c, video):
    """An embedding of THIS case's defendant, from its approved plate frame.

    Without it the defendant search picks whoever happens to be at the podium -
    measured on OFFERUP, it chose a defence attorney in a suit and rendered him
    as the defendant.
    """
    import identity as I
    import tiles as T
    import numpy as np
    fr = T.frame_at(video, c["plate_t"] - c.get("offset", 0))
    if fr is None:
        return None
    if c.get("plate_crop"):
        cw, ch, cx, cy = [int(v) for v in c["plate_crop"].split(":")]
        sub = fr[cy:cy + ch, cx:cx + cw]
        rows = I.faces_in(sub, score=0.5)
        if not rows:
            return None
        return np.stack([I.embed(sub, max(rows, key=lambda r: r[3]))])
    # No hand-typed crop - derive him the same way solve_crops does, from the
    # active-speaker tile plus the one hand fact, `defendant_at`. Without this
    # branch a case that DERIVES its plate_crop got no reference at all and the
    # expression search was skipped entirely ("no defendant reference").
    hint = c.get("defendant_at")
    at = T.active_tile(fr)
    rows = I.faces_in(fr, score=0.6)
    if at:
        rx, ry, rw, rh = at
        rows = [r for r in rows
                if rx <= r[0] + r[2] / 2 <= rx + rw and ry <= r[1] + r[3] / 2 <= ry + rh]
    if not rows:
        return None
    if hint is not None:
        want = hint * fr.shape[1]
        pick = min(rows, key=lambda r: abs(r[0] + r[2] / 2 - want))
    else:
        pick = max(rows, key=lambda r: r[3])
    return np.stack([I.embed(fr, pick)])


def pick_expression_t(case, c, white, yellow, side="right", span=None,
                      ident_ref=None, region=None):
    """Choose judge_t by MEASURING the face, not by hand.

    THE ROOT FIX. tools/expression.py existed for one build before this and was
    invoked by hand - I ran it, read the number, and pasted it into
    cases.json. That is precisely the orphan pattern this repo already has eight
    of: a tool that works, that nothing calls, so the defect returns on the next
    build. Nathan caught it in one line: "Re picking her frame? Did you fix root
    problems tho".

    The headline is the brief: expression.profile_for() maps the words on the
    card to the expression the face should be showing.

    Returns None when the case does not declare a search window, so existing
    cases keep their hand-picked judge_t rather than silently changing.
    """
    win = span or c.get("expression_window")
    if not win:
        return None
    import expression as X
    video = os.path.join(ROOT, c["video"])
    if not os.path.exists(video):
        print("  expression: source video missing, keeping judge_t")
        return None
    headline = f"{white or c['white']} {yellow or c['yellow']}"
    prof = X.profile_for(headline)
    t0, t1 = float(win[0]), float(win[1])
    print(f"  expression: headline {headline!r} -> profile {prof!r}, "
          f"scanning {t0:.0f}-{t1:.0f}s of the {side} tile")
    best, rows = X.search(video, t0, t1, prof, side=side, progress=False,
                          ident_ref=ident_ref, region=region)
    if not best:
        print("  expression: NO usable face in the window - keeping judge_t")
        return None
    # R54 (2026-09-02): EXPRESSION IS NOT ENOUGH. This picker scored the face
    # only on what it was DOING, so it returned a defendant frame with 11.7%
    # of the scalp blown past L235 (the bald-dome head he pointed at) and a
    # judge frame with 16.7% of the face under harsh specular patches. A frame
    # the light has already destroyed cannot be rescued downstream. So the
    # top expression candidates are re-ranked on the LIGHT they arrive in, and
    # what was traded is printed.
    scored = _rerank_on_light(video, rows or [best], prof, side, off=float(c.get("offset", 0)))
    if scored and scored[0] is not best:
        print(f"  expression: re-ranked on light - was t={best['t']:.1f}s "
              f"expr={best['expr']:.4f}, now t={scored[0]['t']:.1f}s "
              f"expr={scored[0]['expr']:.4f} (blown/patchy light rejected)")
        best = scored[0]
    off = float(c.get("offset", 0))
    t_src = off + best["t"]
    flag = "" if best["expr"] >= X.FLOOR else "  BELOW FLOOR - near-neutral face"
    print(f"  expression: t={best['t']:.1f}s (src {t_src:.0f}) "
          f"expr={best['expr']:.4f} floor={X.FLOOR}{flag}")
    return t_src, best, prof


def _rerank_on_light(video, rows, prof, side, off=0.0, keep=12):
    """Re-rank the top expression candidates on the light they arrive in.

    Measured 2026-09-02 on his accepted five vs the batch he rejected: a face
    is unusable when the frame already carries blown or patchy light, and no
    grade downstream puts it back. Two terms, both measured on the SOURCE
    frame: fraction of the face over L235 (blow-out) and fraction more than
    45 L above the face median (harsh specular patches). Expression still
    leads; light breaks the tie and vetoes a ruined frame.
    """
    import cv2
    import numpy as np
    cand = sorted([r for r in rows if r.get("expr") is not None],
                  key=lambda r: -r["expr"])[:keep]
    if len(cand) < 2:
        return cand
    cap = cv2.VideoCapture(video)
    det = None
    out = []
    for r in cand:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(r["t"]) * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        half = fr[:, w // 2:] if side == "right" else fr[:, :w // 2]
        if det is None:
            det = cv2.FaceDetectorYN.create(
                os.path.join(ROOT, "models", "yunet2023.onnx"), "",
                (half.shape[1], half.shape[0]), 0.7, 0.3, 5000)
        det.setInputSize((half.shape[1], half.shape[0]))
        _, f = det.detect(half)
        if f is None:
            continue
        b = max(f, key=lambda q: q[2])
        x, y, bw, bh = (max(0, int(v)) for v in b[:4])
        face = half[y:y + bh, x:x + bw]
        if face.size < 900:
            continue
        L = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)[..., 0].astype(float)
        blown = float((L > 235).mean())
        patchy = float((L > np.median(L) + 45).mean())
        r = dict(r)
        r["blown"] = round(blown, 4)
        r["patchy"] = round(patchy, 4)
        # expression leads; a blown or patchy frame is pushed down hard
        r["light_score"] = r["expr"] * (1.0 - min(blown * 6.0, 0.9)) * (1.0 - min(patchy * 2.5, 0.8))
        out.append(r)
    cap.release()
    out.sort(key=lambda r: -r["light_score"])
    return out

def build(case, work, out_jpg, white=None, yellow=None, kicker=None, arrow=True,
          type_style=None):
    import numpy as np
    from PIL import Image
    import thumb as T
    import thumb_type as TT
    import verify_thumb as V
    c = cases()[case]
    faces = json.load(open(os.path.join(work, "faces.json")))
    # R56 ON THE LIBRARY PATH. prep() skips HYPIR for a library judge, so she is
    # the one subject the colour correction never reaches - measured 2026-09-03,
    # gate I FAIL at chroma 13.7 against a band of 16.5-25.6 while the defendant
    # beside her sat at 19.0. It runs HERE, in build(), and writes a NEW file:
    # judge_surgical.png must stay byte-identical to the library cutout, which
    # R44's reuse contract asserts in eleven places (writing the correction in
    # place broke 14 of its selftest checks).
    _jpng = os.path.join(work, "judge_surgical.png")
    _jcol = os.path.join(work, "judge_surgical_colour.png")
    if not os.path.exists(os.path.join(work, "judge_hypir.png")) \
            and os.path.exists(_jpng):
        import cv2 as _cv2
        import numpy as _np
        import skin_colour_fix as _S
        _rgba = _cv2.imread(_jpng, _cv2.IMREAD_UNCHANGED)
        if _rgba is not None and _rgba.ndim == 3 and _rgba.shape[2] == 4:
            print("  judge (library):")
            _fx = _S.fix(_rgba[..., :3], alpha=_rgba[..., 3])
            _cv2.imwrite(_jcol, _np.dstack([_fx, _rgba[..., 3]]))
            _cv2.imwrite(os.path.join(work, "judge_colour.png"), _fx)
    if os.path.exists(_jcol):
        _jpng = _jcol
    t = T.Thumb(plate_png=os.path.join(work, "defendant_surgical.png"),
                judge_png=_jpng,
                plate_face=tuple(faces["defendant"]),
                judge_face=tuple(faces["judge"]),
                texts=(white or c["white"], yellow or c["yellow"]),
                arrow_png=os.path.join(ROOT, "assets", "arrow_hires.png"))
    # SUBSTITUTION, not a solo flag. The compositor is built for exactly two
    # subjects - every stage downstream (face boxes, skin balance, heads level,
    # rim, grade) assumes both exist. Zeroing one alpha broke two stages in a
    # row, which is the signal that a flag is the wrong shape of fix.
    # Putting the PROP in the second subject slot gives a genuinely different
    # layout with zero downstream changes.
    t.defendant_png = os.path.join(work, c.get("defendant_src",
                                               "defendant_surgical.png"))
    t.defendant_face = tuple(faces["defendant"])
    t.cover_masks = {}                      # clean plate: nothing to hide
    t.bg_plate = np.asarray(Image.open(os.path.join(work, "bg_hypir.png")).convert("RGB"))
    # §8.3 calls 1.6 a hard CEILING, not a target. OFFERUP needs less: its
    # composite trips the posterisation gate at 0.3325 with 1.6, because blur is
    # itself flatness and this case's plate is already softer than CARTHIEF's.
    t.bg_blur = float(c.get("bg_blur", 1.6))
    assert t.bg_blur <= 1.6, "bg_blur ceiling is 1.6 (spec 8.3)"
    # The kicker lives in the case file like the title does. MONKEY_K
    # (2026-09-01) rebuilt without 'YOUR OWNER HATES YOU' because the text
    # had only ever been passed on the command line - the monkey grew into
    # the space the kicker reserves and the build silently changed shape.
    t.kicker_text = kicker or c.get("kicker")
    t.arrow_on = arrow

    # THIRD ELEMENT. thumb.py has supported this since 2026-08-29, written for
    # MONKEY on his instruction - "Cut out the monkey put him in the thumbnail"
    # and "make the spider monkey more seen ... more noticeable and attention
    # grabbing" - and the pipeline never passed it through, so every rebuild
    # since produced a thumbnail whose headline asks "Where's the spider
    # monkey?" over a picture containing no monkey.
    #
    # Composited WITH the photo layers so it takes the same look pass, grain and
    # rim. A prop pasted after finishing reads as a sticker.
    # Subject centres, so margins can be SOLVED rather than nudged. Measured on
    # MONKEY_v7: left margin 13px, right margin 2px - asymmetric, and Boyd's
    # hair ran off the right edge entirely. Nathan, 2026-08-31: "pay attention
    # to how sloppy it looks when everything isn't evenly proportionally spaced
    # and stuff over lapping".
    if c.get("def_c"):
        t.def_c = tuple(c["def_c"])
    if c.get("jud_c"):
        t.jud_c = tuple(c["jud_c"])
    if c.get("face_l_bias"):
        t.face_l_bias = dict(c["face_l_bias"])

    if c.get("judge_head_dy"):
        t.judge_head_dy = int(c["judge_head_dy"])

    if c.get("solve_face_h") is not None:
        t.solve_face_h = bool(c["solve_face_h"])

    if c.get("face_l_target"):
        t.face_l_target = float(c["face_l_target"])

    if c.get("face_h"):
        t.face_h = int(c["face_h"])
    if c.get("solo"):
        t.solo = True

    if c.get("defendant_nudge"):
        t.defendant_nudge = tuple(c["defendant_nudge"])

    if c.get("extra"):
        ex = dict(c["extra"])
        ex["png"] = os.path.join(work, ex["png"])
        if os.path.exists(ex["png"]):
            t.extra = ex
        else:
            print("extra element declared but missing: " + ex["png"])

    # Arrow placement/size/angle apply to EVERY case. These used to sit INSIDE
    # the `extra` branch above, so a case without a third element - OFFERUP, for
    # one - silently could not position its arrow at all no matter what the
    # config said. Same asymmetric-enforcement shape as the title/kicker bug.
    if c.get("arrow_xy"):
        t.arrow_xy = tuple(c["arrow_xy"])
    if c.get("arrow_want"):
        t.arrow_want = int(c["arrow_want"])
    if c.get("arrow_rot"):
        t.arrow_rot = float(c["arrow_rot"])
    if c.get("defendant_scale"):
        t.defendant_scale = float(c["defendant_scale"])
    if c.get("kicker_split"):
        t.kicker_split = c["kicker_split"]
        # thumb.kicker() falls back to the plain golden kicker when the split
        # is not a prefix of the text. MONKEY_K (2026-09-01) rendered
        # 'YOUR OWNER HATES YOU' all yellow because the case file carried
        # kicker_split '"YOUR OWNER ' (a stray quote) - a silent downgrade of
        # a rule he stated ("your owner is white and hates you is red").
        if t.kicker_text and not t.kicker_text.startswith(t.kicker_split):
            raise SystemExit(f"KICKER_SPLIT_MISMATCH {case}: kicker_split "
                             f"{t.kicker_split!r} is not a prefix of the kicker "
                             f"{t.kicker_text!r} - fix config/cases.json")
    if c.get("kicker_colors"):
        t.kicker_colors = [tuple(v) for v in c["kicker_colors"]]
    if c.get("rim_mode"):
        t.rim_mode = c["rim_mode"]
    if c.get("rim_glow") is not None:
        t.rim_glow = float(c["rim_glow"])
    # TYPE TREATMENT. "house" is the accepted 2026-08-31 look byte for byte
    # (proved by scratchpad/identity_type.py against the pre-2026-09-01
    # renderers on every case). Anything else is one of the options he asked
    # for - P36 2026-08-29 "a little bit more click baity type font so tweak
    # it and give me multiple options to pick from and we could lock one in",
    # 2026-09-01 "Maybe throw in a underline under hates you" / "make the
    # words [not] look so generic and cheap". The case file locks the pick
    # (`type_style`); the CLI flag is for building the option sheet. An
    # unknown name refuses the build (TYPE_STYLE_UNKNOWN) instead of quietly
    # falling back to house.
    t.type_style = type_style or c.get("type_style", "house")
    TT.resolve(t.type_style, "title")

    t.debug_dir = work
    t.build(out_jpg)
    t.log["type_style"] = t.type_style
    t.log["type_tells"] = TT.tells(t.type_style)   # R45, on disk with the build
    print(json.dumps(t.log, indent=1))
    json.dump(t.log, open(os.path.join(work, "_build_log.json"), "w"),
              indent=1, default=str)
    # R40: the build carries the floor it was built under, so a later floor
    # change makes this artifact refuse instead of quietly shipping stale.
    import floor_stamp
    _fl = floor_stamp.stamp(work)
    print(f"  floor stamp  {_fl['hash'][:12]}  ({', '.join(_fl['files'])})")
    # BUILD GATES. Not optional, and not a separate command someone has to
    # remember - that is precisely how nine checkers in this repo ended up
    # orphaned while the defects they would have caught shipped.
    # HOUSE-STYLE CHECKLIST, printed every build. Nathan, 2026-08-31: "Make
    # sure u don't forget anything next time you generate a thumbnail too".
    # Every one of these was something he had to ask for, and the recurring
    # failure was applying it to ONE case and calling it done. Printing what
    # actually ran means an omission cannot hide in the noise.
    _L = t.log
    _cl = [
        # checked against the MODULE, not this run's log - the matte is cached
        # between builds, so a re-render legitimately prints no matte line
        ("true alpha matting (not segmentation)",
         __import__("matting").available()),
        ("expression-picked frames, both subjects", True),
        ("face size solved from the vertical budget", t.solve_face_h),
        ("heads level", _L.get("head_top_delta", 99) <= 2 + abs(t.judge_head_dy)),
        ("separation glow (no hard outline)", isinstance(_L.get("rim"), dict)),
        ("background blurred + separation solved", "separation_solve" in _L),
        ("dodge & burn on faces", isinstance(_L.get("dodge_burn"), dict)),
        ("highlight shoulder + skin on corpus target", "skin_final" in _L),
        ("grain layer over the whole frame", float(_L.get("final_grain", 0)) >= 2.0),
        # the house kicker separates from the plate with an offset shadow;
        # another treatment may do it with a glow, an extrude or a heavy
        # stroke. Read off the resolved spec, not assumed.
        (f"kicker separated from the plate ({t.type_style}: "
         f"{TT.describe(t.type_style)})",
         bool(TT.resolve(t.type_style, 'kicker').get('shadow')
              or TT.resolve(t.type_style, 'kicker').get('extrude')
              or TT.resolve(t.type_style, 'kicker')['stroke'] >= 9)),
        ("type clear of every face", _L.get("type_on_subject_px", 1) == 0),
        ("arrow placed last, clear of subjects and type",
         _L.get("arrow") == "off" or isinstance(_L.get("arrow_placed"), dict)),
    ]
    print(chr(10) + "  house style:")
    for _name, _done in _cl:
        print(f"    {'[x]' if _done else '[ ] MISSING'}  {_name}")
    # R45: the cheap tells he named are reported on every build, never
    # refused - 'house' carries all three until he locks a preset in.
    _tells = _L["type_tells"]
    print(f"  type_style={t.type_style}  cheap tells (R45, reported not refused): "
          + (", ".join(f"{k} = {TT.TELLS[k]}" for k in _tells) if _tells else "none")
          + "  |  'looks generic' itself is NOT AUTOMATED - his call")
    _missing = [n for n, d in _cl if not d]
    if _missing:
        print(f"  {len(_missing)} house-style item(s) missing")

    # CLAUDE.md: "Before packaging, search YouTube for the defendant / case and
    # record who has posted it in config/cases.json" - his 2026-08-30 rule that
    # selection outranks packaging. Until 2026-09-01 this was a manual step
    # nothing checked. Now it is a build gate: no posted_by, or a search older
    # than case_search.STALE_DAYS, fails the build like any other gate.
    import case_search
    _cs_code, _cs_line = case_search.check(case)
    print(f"  {'[x]' if _cs_code == 0 else '[ ] MISSING'}  {_cs_line}")

    import verify_build
    _ok, _ = verify_build.run(work, out_jpg)
    _ok = _ok and not _missing and _cs_code == 0
    print("BUILD_GATES PASS" if _ok else "BUILD_GATES FAIL")
    ok, _ = V.score(out_jpg)
    print(("GATES PASS  " if ok else "GATES FAIL  ") + out_jpg)
    # the verdict is BOTH: until 2026-09-01 only verify_thumb's score came
    # back, so a build with a failing build gate still returned True to the
    # caller and read as "GATES PASS" one line after "BUILD_GATES FAIL"
    return ok and _ok


def selftest_cut_edge(check):
    """R29 in the compositor. (1) thumb.find_cliff finds a tile-seam cliff
    (a run of rows ending on one column) and ignores a natural silhouette and
    a short ledge; (2) thumb.Thumb.cut() GROWS a layer whose cliff would land
    inside the canvas until the cut is at the canvas edge, logs the growth,
    and leaves a layer alone when its cliff already lands outside; (3) a cliff
    on the near side of the face is reported as unresolvable, not hidden."""
    import tempfile
    import numpy as np
    from PIL import Image
    import thumb as T
    d = tempfile.mkdtemp(prefix="cutedge_")
    try:
        H, W = 600, 400
        rgba = np.zeros((H, W, 4), np.uint8)
        yy, xx = np.mgrid[:H, :W]
        head = ((xx - 200) ** 2 / 60.0 ** 2 + (yy - 90) ** 2 / 70.0 ** 2) <= 1
        body = (yy >= 150) & (xx >= 100 + (yy % 23)) & (xx <= 299)   # ragged left, cliff right
        arm = (yy >= 130) & (yy < 150) & (xx >= 250) & (xx <= 380)    # content past the cliff
        m = head | body | arm
        rgba[m] = (90, 120, 80, 255)
        hit = T.find_cliff(rgba[:, :, 3], "right")
        check("find_cliff: right cliff at x=299, 450 of span 580 rows",
              hit is not None and hit[0] == 299 and hit[2] == 450 and hit[3] == 580)
        check("find_cliff: no left cliff on the ragged edge", T.find_cliff(rgba[:, :, 3], "left") is None)
        ell = np.zeros((H, W, 4), np.uint8)
        e = ((xx - 200) ** 2 / 120.0 ** 2 + (yy - 300) ** 2 / 280.0 ** 2) <= 1
        ell[e] = (90, 120, 80, 255)
        check("find_cliff: an ellipse has no cliff on either side",
              T.find_cliff(ell[:, :, 3], "right") is None and T.find_cliff(ell[:, :, 3], "left") is None)
        ledge = ell.copy()
        ledge[300:340, 200:380] = (90, 120, 80, 255)   # 40 rows on a 580 span = 0.07
        check("find_cliff: a ledge under CUT_EDGE_RUN_FRAC is not a cliff",
              T.find_cliff(ledge[:, :, 3], "right") is None)
        # 2. cut(): a cliff that would land inside the canvas grows the layer
        png = os.path.join(d, "torso.png")
        Image.fromarray(rgba).save(png)
        face = (150, 40, 100, 100)          # face centre x=200; the cliff is 99 px right of it
        t = T.Thumb.__new__(T.Thumb)
        t.log = {}
        want = 200                          # s0 = 2.0 -> cliff at cx + 99*2
        cx = T.W - 300                      # cliff would land at W-102: inside
        _, al = T.Thumb.cut(t, png, face, want, cx, 300, "boyd", top_y=100)
        g = t.log.get("cut_edge", {}).get("boyd")
        a1 = al > 0.5
        last = np.where(a1.any(axis=0))[0]
        cliff_rows = a1[:, T.W - 1]
        check("cut: layer grew (logged) and the cliff now sits ON the canvas edge",
              g is not None and g["grew"] > 1.0 and last.size and int(last.max()) == T.W - 1
              and int(cliff_rows.sum()) > 100)
        check("cut: grew by the smallest 3% step that clears the edge (x1.03^n, n>=1)",
              g is not None and 1.0 < g["grew"] <= 1.03 ** 40
              and abs(g["grew"] - 1.03 ** round(np.log(g["grew"]) / np.log(1.03))) < 1e-3)   # log rounds to 3 dp
        check("cut: the placed layer has no interior straight run (gate K's signature is gone)",
              T.find_cliff((al * 255).astype(np.uint8), "right") is None
              or T.find_cliff((al * 255).astype(np.uint8), "right")[0] == T.W - 1)
        # control: the same layer placed so the cliff already lands past the edge
        t2 = T.Thumb.__new__(T.Thumb)
        t2.log = {}
        _, al2 = T.Thumb.cut(t2, png, face, want, T.W - 150, 300, "boyd", top_y=100)
        check("cut control: cliff already outside -> no growth, no log entry",
              "cut_edge" not in t2.log and t2.log["boyd"]["face_h"] == want)
        # 3. a cliff on the NEAR side of the face: reported, not grown
        left = rgba[:, ::-1].copy()          # cliff now on the LEFT at x=100
        png3 = os.path.join(d, "left.png")
        Image.fromarray(left).save(png3)
        t3 = T.Thumb.__new__(T.Thumb)
        t3.log = {}
        _, al3 = T.Thumb.cut(t3, png3, face, want, 300, 300, "boyd", top_y=100)
        g3 = t3.log.get("cut_edge", {}).get("boyd")
        check("cut: a left cliff placed left of centre grows until it leaves the left edge",
              g3 is not None and g3["grew"] > 1.0 and not g3["unresolvable"]
              and bool((al3 > 0.5)[:, 0].sum() > 100))
        # near side: the LEFT cliff with the face centre to its LEFT (face at x=50 in the crop)
        t4 = T.Thumb.__new__(T.Thumb)
        t4.log = {}
        _, _ = T.Thumb.cut(t4, png3, (20, 40, 60, 100), 200, 600, 300, "boyd", top_y=100)
        g4 = t4.log.get("cut_edge", {}).get("boyd")
        check("cut: a cliff on the near side of the face is logged unresolvable and NOT grown",
              g4 is not None and g4["unresolvable"] and g4["grew"] == 1.0)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def selftest_ink_vs_subjects(check):
    """R1, measured honestly (2026-09-01). thumb.ink_vs_subjects must (1) count
    title ink over a subject, (2) count kicker ink inside a face box, (3) count
    but NOT fold kicker-over-body into the asserted number - the kicker band
    sits on both bodies on all five accepted builds - and (4) read 0/0/0 on a
    clean layout. The old single number counted the title only while the
    skill said it covered the kicker too."""
    import numpy as np
    import thumb as T
    H, W = 720, 1280
    jal = np.zeros((H, W), np.float32)
    dal = np.zeros((H, W), np.float32)
    jal[200:720, 800:1280] = 1.0          # judge: right half, from y=200 down
    dal[300:720, 100:500] = 1.0           # defendant: left, from y=300 down
    boxes = [[900, 220, 200, 240], [200, 320, 100, 120]]   # faces inside each
    t = np.zeros((H, W), bool)
    k = np.zeros((H, W), bool)
    t[40:140, 100:1100] = True            # title across the top: clear of both
    k[600:680, 250:700] = True            # kicker low, over the defendant's body only
    m = T.ink_vs_subjects(t, k, jal, dal, boxes)
    check("ink: clean layout -> title 0, kicker-on-face 0, asserted number 0",
          m["title_on_subject_px"] == 0 and m["kicker_on_face_px"] == 0
          and m["type_on_subject_px"] == 0)
    check("ink: kicker over a BODY is counted (80x250) but not asserted",
          m["kicker_on_subject_px"] == 80 * 250 and m["type_on_subject_px"] == 0)
    t3 = t.copy(); t3[150:260, 700:1100] = True       # title runs down into the judge
    m3 = T.ink_vs_subjects(t3, k, jal, dal, boxes)
    check("ink: title into the judge -> title_on_subject_px 60x300, asserted number > 0",
          m3["title_on_subject_px"] == 60 * 300 and m3["type_on_subject_px"] == 60 * 300)
    k4 = k.copy(); k4[400:440, 900:1020] = True       # kicker ink fully inside the judge face box (x 900..1100, y 220..460)
    m4 = T.ink_vs_subjects(t, k4, jal, dal, boxes)
    check("ink: kicker inside a face box -> kicker_on_face_px 40x120, asserted",
          m4["kicker_on_face_px"] == 40 * 120 and m4["type_on_subject_px"] == 40 * 120)
    m5 = T.ink_vs_subjects(t, k4, jal, dal, [None, None])
    check("ink: no face boxes -> kicker-on-face unmeasurable reads 0, body count unchanged",
          m5["kicker_on_face_px"] == 0 and m5["kicker_on_subject_px"] == m4["kicker_on_subject_px"])


def selftest():
    """PROVE the library path on the real prep(): same-case reuse copies the
    approved cutout, writes the index face box into faces.json and SKIPS the
    judge's grab / HYPIR / regenerate / matte / detect, while the defendant and
    plate go through every stage; the negative controls (bytes changed since
    the seed, a declared K defect, judge_source=video, a searched frame that
    out-scores the library) send her back through all of them; an explicit
    request by name is honoured over the case's own cutout and over an earlier
    library take (both refuted 2026-09-01); a matte the video path produced is
    never overwritten; and a new case with no judge_t builds from the library
    through the REAL crop-solving contract (the stub raises exactly where
    solve_crops does - the KeyError the first build shipped).

    Temp work dirs, a temp library, every heavy stage stubbed with a recorder
    that keeps the real skip-if-exists contract - no ffmpeg, no HYPIR, no GPU,
    no network, no mediapipe (the library score is computed from stored
    blendshapes by tools/expression.py, the search is a stub)."""
    import contextlib
    import io
    import tempfile
    import traceback
    import types
    import cv2
    import numpy as np
    import library as L
    import expression as X
    g = globals()
    saved = {k: g[k] for k in ("cases", "grab", "hypir", "matte", "face_of",
                               "pick_clean_plate", "pick_expression_t", "solve_crops")}
    saved_mods = {k: sys.modules.get(k) for k in ("regenerate", "identity")}
    real_reactions = L.REACTIONS
    tmp = tempfile.mkdtemp(prefix="thumb_pipeline_")
    ok = True
    calls = []

    def check(label, good):
        nonlocal ok
        ok = ok and bool(good)
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        return good

    # R29 in the compositor (2026-09-01): cliff detection + the growth in cut()
    selftest_cut_edge(check)
    selftest_ink_vs_subjects(check)
    # the case file itself: a kicker_split that is not a prefix of the kicker
    # renders the plain golden kicker with no error (MONKEY_K, 2026-09-01)
    for _k, _c in cases().items():
        if _c.get("kicker_split") and _c.get("kicker"):
            check(f"cases.json {_k}: kicker_split is a prefix of the kicker",
                  _c["kicker"].startswith(_c["kicker_split"]))
        elif _c.get("kicker_split"):
            check(f"cases.json {_k}: has kicker_split but no kicker text in the case file "
                  f"(the split can only be applied to a --kicker typed by hand)", False)

    def _png(path, v=90, alpha=False):
        im = np.full((16, 16, 4 if alpha else 3), v, np.uint8)
        cv2.imwrite(path, im)
        return path

    # ---- stubs, each keeping the real "existing output is skipped" contract
    def s_grab(video, t, crop, out):
        if os.path.exists(out):
            calls.append(("grab-skip", os.path.basename(out)))
            return out
        calls.append(("grab", os.path.basename(out)))
        return _png(out)

    def s_hypir(src, out, caption, upscale=4):
        if os.path.exists(out):
            calls.append(("hypir-skip", os.path.basename(out)))
            return out
        calls.append(("hypir", os.path.basename(out)))
        shutil.copy(src, out)
        return out

    def s_matte(src, dst):
        if os.path.exists(dst):
            calls.append(("matte-skip", os.path.basename(dst)))
            return dst
        calls.append(("matte", os.path.basename(dst)))
        return _png(dst, 120, alpha=True)

    def s_face_of(png, at=None):
        calls.append(("face_of", os.path.basename(png)))
        return (1, 2, 3, 4)

    def s_plate(case, dst):
        calls.append(("plate", os.path.basename(dst)))
        return _png(dst, 60)

    search_expr = {"v": None}          # None -> the search finds nothing

    def s_pick(case, c, white, yellow, side="right", span=None, ident_ref=None, region=None):
        calls.append(("search", side))
        if search_expr["v"] is None:
            return None
        return (123.0, dict(t=100.0, expr=search_expr["v"], total=search_expr["v"],
                            box=[0, 0, 8, 8]), "serious")

    def s_solve(case, c, video, off, skip=()):
        """The real solve_crops' contract, minus the frame reads: a crop that is
        neither typed nor skipped is derived from ITS time key - c[tkey] -
        which raises KeyError exactly as the real one does when the key is
        absent. The first build's stub set both crops unconditionally, so the
        real KeyError('judge_t') on a library judge with no judge_t was
        invisible to this selftest."""
        calls.append(("solve_crops", tuple(skip)))
        need = [k for k in ("judge_crop", "plate_crop") if not c.get(k) and k not in skip]
        out = dict(c)
        for key, tkey in (("judge_crop", "judge_t"), ("plate_crop", "plate_t")):
            if key in need:
                _ = c[tkey] - off                    # KeyError when absent, as real
                out[key] = "16:16:0:0"
        return out

    CASES = {
        "FAKE": dict(video="work/fake.mp4", offset=0, judge_t=100, plate_t=90,
                     judge_crop="16:16:0:0", plate_crop="16:16:0:0",
                     white="Do you want", yellow="a jury trial?"),
        "NEWCASE": dict(video="work/new.mp4", offset=0, judge_t=300, plate_t=290,
                        white="Do you want", yellow="a jury trial?"),
        # the brief's own new-case shape: nothing typed but plate_t
        "NOJUDGET": dict(video="work/new.mp4", offset=0, plate_t=290,
                         white="Do you want", yellow="a jury trial?"),
    }
    prof = X.profile_for("Do you want a jury trial?")
    # blendshapes that read as the brief's profile, scored by the live scorer;
    # OTHER is a second approved cutout that scores lower on it
    shapes = {k: 0.6 for k, _ in X.PROFILES[prof]}
    shapes_lo = {k: 0.3 for k, _ in X.PROFILES[prof]}
    lib_score = float(X.score(shapes, prof))
    lo_score = float(X.score(shapes_lo, prof))

    # The `regenerate` stage is NOT listed. It has been off by default since
    # 2026-09-02 (measured worse than the HYPIR frame) and `run()` below calls
    # prep() without --regen, so expecting it made five checks read "every
    # stage ran (4/5)" / "(6/7)" and fail on a pipeline that was behaving
    # correctly. Verified 2026-09-03 against `git show HEAD`: these five were
    # already failing before R56/R57 touched anything.
    JUDGE_STAGES = {("grab", "judge_raw.png"), ("hypir", "judge_hypir.png"),
                    ("matte", "judge_surgical.png"),
                    ("face_of", "judge_raw.png")}
    DEF_STAGES = {("grab", "defendant_raw.png"), ("hypir", "defendant_hypir.png"),
                  ("matte", "defendant_surgical.png"),
                  ("face_of", "defendant_raw.png"), ("plate", "bg_raw.png"),
                  ("hypir", "bg_hypir.png")}

    def run(case, judge_source=None, work=None):
        calls.clear()
        work = work or os.path.join(tmp, "work_" + case + "_" + str(len(os.listdir(tmp))))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                prep(case, work, judge_source=judge_source)
                err = None
            except SystemExit as e:
                err = str(e)
            except Exception:                        # a crash is a failed check, not a
                err = "CRASH " + traceback.format_exc()  # traceback out of the selftest
        text = buf.getvalue()
        faces = (json.load(open(os.path.join(work, "faces.json")))
                 if os.path.exists(os.path.join(work, "faces.json")) else None)
        return work, text, faces, err

    def judge_ran():
        return sorted(set(calls) & JUDGE_STAGES)

    def defendant_ran():
        return sorted(set(calls) & DEF_STAGES)

    def sha_of(work, name):
        p = os.path.join(work, name)
        return L._sha(p) if os.path.exists(p) else None

    try:
        g.update(cases=lambda: CASES, grab=s_grab, hypir=s_hypir, matte=s_matte,
                 face_of=s_face_of, pick_clean_plate=s_plate, pick_expression_t=s_pick,
                 solve_crops=s_solve)
        sys.modules["regenerate"] = types.SimpleNamespace(
            regenerate=lambda src, dst: calls.append(("regenerate", os.path.basename(src))))
        sys.modules["identity"] = types.SimpleNamespace(load_reference=lambda: None)
        # ---- the temp library: two approved cutouts, FAKE and OTHER, usable, tagged
        L.REACTIONS = os.path.join(tmp, "reactions", "boyd")
        os.makedirs(L.REACTIONS)
        cut = _png(os.path.join(L.REACTIONS, "boyd_FAKE_approved.png"), 200, alpha=True)
        raw = _png(os.path.join(tmp, "FAKE_judge_raw.png"), 30)
        cut2 = _png(os.path.join(L.REACTIONS, "boyd_OTHER_approved.png"), 150, alpha=True)
        raw2 = _png(os.path.join(tmp, "OTHER_judge_raw.png"), 40)

        def mk(case, f, r, box, shp):
            return dict(file=f, case=case, source=f, source_raw=r,
                        approved="2026-08-31", kind=L.CUTOUT, w=16, h=16,
                        face_box=box, sha256=L._sha(f), judge_t=100,
                        video="work/fake.mp4", usable=True, defects=[],
                        expression=dict(profile=prof, scores={}, eyes_shut=False,
                                        top_shapes=[], shapes=shp),
                        expression_note=None)
        entry = mk("FAKE", cut, raw, [5, 6, 7, 8], shapes)
        other = mk("OTHER", cut2, raw2, [9, 10, 11, 12], shapes_lo)

        def write_index(*rows):
            json.dump(list(rows), open(os.path.join(L.REACTIONS, "index.json"), "w"), indent=1)

        write_index(entry, other)
        check(f"library scores for profile {prof!r}: FAKE {lib_score:.4f} > OTHER {lo_score:.4f} > 0",
              lib_score > lo_score > 0)

        # 1. SAME CASE, fresh work dir
        work, text, faces, err = run("FAKE")
        jsurg = os.path.join(work, "judge_surgical.png")
        check("same case: prep() ran to PREP_OK", err is None and "PREP_OK" in text)
        check("same case: prints 'library: judge cutout reused from boyd_FAKE_approved.png (approved 2026-08-31)'",
              "library: judge cutout reused from boyd_FAKE_approved.png (approved 2026-08-31)" in text)
        check("same case: judge_surgical.png IS the library cutout (sha equal)",
              os.path.exists(jsurg) and L._sha(jsurg) == entry["sha256"])
        check("same case: faces.json judge == index face_box [5, 6, 7, 8]",
              faces and faces["judge"] == [5, 6, 7, 8])
        check("same case: defendant box still detected (x4 of the stub)",
              faces and faces["defendant"] == [4, 8, 12, 16])
        check(f"same case: NO judge stage ran {judge_ran()}", judge_ran() == [])
        check(f"same case: every defendant/plate stage ran ({len(defendant_ran())}/{len(DEF_STAGES)})",
              set(defendant_ran()) == DEF_STAGES)
        check("same case: judge_crop derivation skipped in solve_crops",
              ("solve_crops", ("judge_crop",)) in calls)
        check("same case: source crop carried in as judge_raw.png for gate F",
              sha_of(work, "judge_raw.png") == L._sha(raw))
        check("same case: judge_source.json sidecar written",
              (_read_sidecar(work) or {}).get("source") == "library")
        # 2. RESUME the same work dir: nothing re-done, judge still from the library
        _, text2, faces2, err2 = run("FAKE", work=work)
        check("resume: judge cutout 'already in place', not re-decided",
              err2 is None and "already in place from boyd_FAKE_approved.png" in text2)
        check(f"resume: no judge stage ran, defendant stages skipped as existing outputs "
              f"{[c for c in calls if c[0].endswith('-skip')][:3]}...",
              judge_ran() == [] and ("grab-skip", "defendant_raw.png") in calls
              and ("matte-skip", "defendant_surgical.png") in calls)
        check("resume: faces.json unchanged", faces2 == faces)
        # 3. NEGATIVE: bytes changed since the seed -> video path, every judge stage
        keep = open(cut, "rb").read()
        _png(cut, 7, alpha=True)
        work3, text3, faces3, err3 = run("FAKE")
        check("sha mismatch: NOT reused, says why",
              err3 is None and "NOT reused" in text3 and "sha256 mismatch" in text3)
        check(f"sha mismatch: every judge stage ran ({len(judge_ran())}/{len(JUDGE_STAGES)})",
              set(judge_ran()) == JUDGE_STAGES)
        check("sha mismatch: faces.json judge is the detected box, not the index box",
              faces3 and faces3["judge"] == [4, 8, 12, 16])
        check("sha mismatch: no sidecar written", _read_sidecar(work3) is None)
        open(cut, "wb").write(keep)
        # 4. NEGATIVE: a declared K defect (MONKEY's shape) is never reused
        write_index(dict(entry, usable=False, defects=["K"]), other)
        work4, text4, faces4, err4 = run("FAKE")
        check("K defect: NOT reused, names the defect",
              err4 is None and "NOT reused" in text4 and "['K']" in text4)
        check(f"K defect: every judge stage ran ({len(judge_ran())}/{len(JUDGE_STAGES)})",
              set(judge_ran()) == JUDGE_STAGES)
        check("K defect on auto: OTHER's face is NOT borrowed under a case with its own entry",
              "never takes another case's face" in text4
              and sha_of(work4, "judge_surgical.png") != other["sha256"])
        write_index(entry, other)
        # 5. judge_source=video ignores a usable own cutout, out loud
        work5, text5, faces5, err5 = run("FAKE", judge_source="video")
        check("judge_source=video: own cutout ignored on request, judge stages ran",
              err5 is None and "ignored on request" in text5 and set(judge_ran()) == JUDGE_STAGES)
        # 6. CROSS CASE on auto: library beats a weaker searched frame
        search_expr["v"] = round(lib_score - 0.05, 4)
        work6, text6, faces6, err6 = run("NEWCASE")
        check(f"cross-case auto: library {lib_score:.4f} >= searched {search_expr['v']:.4f} -> "
              f"boyd_FAKE_approved.png wins, printed with both scores",
              err6 is None and "wins for NEWCASE" in text6
              and f"library {lib_score:.4f} >= searched {search_expr['v']:.4f}" in text6)
        check("cross-case auto: the search DID run (the library competed, it was not assumed)",
              ("search", "right") in calls)
        check("cross-case auto: judge_surgical.png is the FAKE cutout (the higher-scoring of two), "
              "face box from the index",
              sha_of(work6, "judge_surgical.png") == entry["sha256"]
              and faces6 and faces6["judge"] == [5, 6, 7, 8] and judge_ran() == [])
        # 7. NEGATIVE: a stronger searched frame wins -> video path
        search_expr["v"] = round(lib_score + 0.05, 4)
        work7, text7, faces7, err7 = run("NEWCASE")
        check(f"cross-case auto: searched {search_expr['v']:.4f} > library -> cutting from the video",
              err7 is None and "cutting from the video" in text7 and set(judge_ran()) == JUDGE_STAGES
              and faces7 and faces7["judge"] == [4, 8, 12, 16])
        # 8. tie -> library
        search_expr["v"] = lib_score
        work8, text8, faces8, err8 = run("NEWCASE")
        check("cross-case auto: a tie goes to the library",
              err8 is None and "wins for NEWCASE" in text8 and judge_ran() == [])
        # 9. --judge-from-library FAKE: by name, no search
        search_expr["v"] = 0.99
        work9, text9, faces9, err9 = run("NEWCASE", judge_source="library:FAKE")
        check("library:FAKE: taken on request, video not searched",
              err9 is None and "taken for NEWCASE on request (library:FAKE)" in text9
              and ("search", "right") not in calls and judge_ran() == []
              and faces9 and faces9["judge"] == [5, 6, 7, 8])
        # 10. --judge-from-library best: no search even when the video would win
        work10, text10, faces10, err10 = run("NEWCASE", judge_source="library")
        check("library (best): best usable for the profile, video not searched",
              err10 is None and "best usable for profile" in text10
              and ("search", "right") not in calls and judge_ran() == []
              and sha_of(work10, "judge_surgical.png") == entry["sha256"])
        # 11. a case with no judge_t at all builds from the library on auto -
        #     through the real crop-solving contract (the stub raises on a
        #     missing judge_t exactly as solve_crops does)
        work11, text11, faces11, err11 = run("NOJUDGET")
        check("no judge_t: auto takes the library (nothing to search from), no judge stage ran",
              err11 is None and "no judge_t to search from" in text11 and judge_ran() == [])
        check("no judge_t: prep() reached PREP_OK - the plate crop was solved with judge_crop "
              "skipped, no KeyError('judge_t')",
              err11 is None and "PREP_OK" in text11 and faces11 is not None
              and ("solve_crops", ("judge_crop",)) in calls
              and ("solve_crops", ()) not in calls)
        # 12. NEGATIVE: no judge_t AND nothing usable -> refuses, does not guess
        write_index(dict(entry, usable=False, defects=["K"]), dict(other, usable=False, defects=["K"]))
        work12, text12, faces12, err12 = run("NOJUDGET")
        check("no judge_t and no usable cutout: refuses with the fix named",
              err12 is not None and "judge_t" in err12)
        write_index(entry, other)
        # 13. BY NAME on a case with its OWN usable cutout: the named one is
        #     taken, not the case's own (the first build returned FAKE here)
        work13, text13, faces13, err13 = run("FAKE", judge_source="library:OTHER")
        check("library:OTHER on FAKE: OTHER taken on request, own cutout NOT substituted",
              err13 is None and "boyd_OTHER_approved.png (approved 2026-08-31) taken for FAKE on request "
              "(library:OTHER)" in text13
              and sha_of(work13, "judge_surgical.png") == other["sha256"]
              and faces13 and faces13["judge"] == [9, 10, 11, 12] and judge_ran() == [])
        check("library:OTHER on FAKE: judge_raw.png is OTHER's source crop (gate F input)",
              sha_of(work13, "judge_raw.png") == L._sha(raw2))
        # 14. same work dir, now asked for FAKE by name: the earlier library take
        #     is superseded OUT LOUD (the first build said 'not re-decided')
        _, text14, faces14, err14 = run("FAKE", judge_source="library:FAKE", work=work13)
        check("library:FAKE over an in-place OTHER: superseded, printed, FAKE in place",
              err14 is None and "superseding boyd_OTHER_approved.png" in text14
              and "on request (library:FAKE)" in text14
              and sha_of(work13, "judge_surgical.png") == entry["sha256"]
              and faces14 and faces14["judge"] == [5, 6, 7, 8] and judge_ran() == [])
        check("superseded: judge_raw.png replaced with FAKE's source crop, sidecar names FAKE",
              sha_of(work13, "judge_raw.png") == L._sha(raw)
              and (_read_sidecar(work13) or {}).get("case") == "FAKE")
        # 15. same request again: nothing to redo, still FAKE
        _, text15, _, err15 = run("FAKE", judge_source="library:FAKE", work=work13)
        check("library:FAKE again: 'already in place ... nothing to redo'",
              err15 is None and "already in place" in text15 and "nothing to redo" in text15
              and sha_of(work13, "judge_surgical.png") == entry["sha256"])
        # 16. 'library' (best) on a work dir holding a by-name pick that is NOT
        #     the best: re-ranked and superseded, printed
        work16, text16, _, err16 = run("NEWCASE", judge_source="library:OTHER")
        _, text16b, faces16, err16b = run("NEWCASE", judge_source="library", work=work16)
        check("library (best) over an in-place OTHER: re-ranked, FAKE supersedes it, printed",
              err16 is None and err16b is None and "superseding boyd_OTHER_approved.png" in text16b
              and "best usable for profile" in text16b
              and sha_of(work16, "judge_surgical.png") == entry["sha256"]
              and faces16 and faces16["judge"] == [5, 6, 7, 8])
        _, text16c, _, err16c = run("NEWCASE", judge_source="library", work=work16)
        check("library (best) again: 'already in place and still the best', nothing redone",
              err16c is None and "still the best" in text16c and judge_ran() == [])
        # 17. 'auto' on a work dir holding an explicit by-name pick keeps it
        #     (resumability), and says so
        work17, _, _, _ = run("NEWCASE", judge_source="library:OTHER")
        _, text17, faces17, err17 = run("NEWCASE", work=work17)
        check("auto over an in-place by-name OTHER: kept, 'not re-decided'",
              err17 is None and "already in place from boyd_OTHER_approved.png" in text17
              and "not re-decided" in text17
              and sha_of(work17, "judge_surgical.png") == other["sha256"]
              and faces17 and faces17["judge"] == [9, 10, 11, 12])
        # 18. 'library' (best) on a case whose own cutout is usable: own wins a
        #     tie; when another out-scores it, own is passed over ON REQUEST.
        #     OTHER is listed FIRST so a stable sort alone cannot hand the tie
        #     to FAKE - the tie rule has to do it (a mutant with `>` for `>=`
        #     passed while the index order did the work).
        write_index(dict(other, expression=dict(other["expression"], shapes=shapes)), entry)
        work18, text18, faces18, err18 = run("FAKE", judge_source="library")
        check("library (best) on FAKE, tie with OTHER: own cutout wins the tie",
              err18 is None and "reused from boyd_FAKE_approved.png" in text18
              and "also the best usable" in text18
              and sha_of(work18, "judge_surgical.png") == entry["sha256"])
        hi = {k: 0.9 for k, _ in X.PROFILES[prof]}
        write_index(entry, dict(other, expression=dict(other["expression"], shapes=hi)))
        work18b, text18b, faces18b, err18b = run("FAKE", judge_source="library")
        check("library (best) on FAKE, OTHER out-scores own: OTHER taken, own passed over on request",
              err18b is None and "own cutout boyd_FAKE_approved.png at" in text18b
              and "passed over for boyd_OTHER_approved.png" in text18b
              and sha_of(work18b, "judge_surgical.png") == other["sha256"]
              and faces18b and faces18b["judge"] == [9, 10, 11, 12])
        write_index(entry, other)
        # 19. NEGATIVE: a matte the VIDEO path produced (no sidecar) is never
        #     overwritten by a request - refuse and name what to delete
        work19 = os.path.join(tmp, "work_video_matte")
        os.makedirs(work19)
        _png(os.path.join(work19, "judge_surgical.png"), 33, alpha=True)
        _, text19, _, err19 = run("NEWCASE", judge_source="library:FAKE", work=work19)
        check("library:FAKE over a video-path matte: refused, names judge_surgical.png to delete",
              err19 is not None and "matte the video path produced" in err19
              and "delete it" in err19
              and L._sha(os.path.join(work19, "judge_surgical.png")) != entry["sha256"])
        _, text19b, _, err19b = run("NEWCASE", work=work19)
        check("auto over a video-path matte: kept (video path), no library take",
              err19b is None and "keeping it (video path)" in text19b
              and _read_sidecar(work19) is None)
        # 20. NEGATIVE: an unknown case name is refused, not guessed
        _, _, _, err20 = run("NEWCASE", judge_source="library:NOSUCH")
        check("library:NOSUCH: refused, names the list command",
              err20 is not None and "no approved cutout for 'NOSUCH'" in err20)
    finally:
        g.update(saved)
        for k, m in saved_mods.items():
            if m is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = m
        L.REACTIONS = real_reactions
        shutil.rmtree(tmp, ignore_errors=True)
    print("SELFTEST_PASS thumb_pipeline" if ok else "SELFTEST_FAIL thumb_pipeline")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out")
    ap.add_argument("--white"); ap.add_argument("--yellow"); ap.add_argument("--kicker")
    ap.add_argument("--no-arrow", action="store_true",
                    help="drop the arrow. On MONKEY the arrow and the monkey "
                         "compete for the same ~300px gap between two large "
                         "faces; the monkey is the story, so it gets the space.")
    ap.add_argument("--judge-from-library", metavar="CASE|best",
                    help="take Boyd from assets/harvest/reactions/boyd/ instead of "
                         "re-cutting her: 'best' ranks the usable cutouts on the "
                         "brief's expression profile, a CASE name takes that "
                         "case's approved cutout. Overrides cases.json judge_source.")
    ap.add_argument("--regen", action="store_true",
                    help="run the Qwen regenerate pass after HYPIR. OFF by default "
                         "since 2026-09-02: measured worse than the HYPIR frame "
                         "(speckled noise, face drift) and costs ~15 min of model "
                         "load per build.")
    ap.add_argument("--prep-only", action="store_true")
    ap.add_argument("--type-style", metavar="STYLE",
                    help="type treatment for title + kicker (tools/thumb_type.py "
                         "STYLES). Default: the case file's type_style, else "
                         "'house' - the accepted 2026-08-31 look byte for byte.")
    a = ap.parse_args()
    jsrc = None
    if a.judge_from_library:
        jsrc = "library" if a.judge_from_library.lower() == "best" else f"library:{a.judge_from_library}"
    prep(a.case, a.work, kicker=a.kicker, judge_source=jsrc, regen=a.regen)
    if a.prep_only:
        sys.exit(0)
    # THE GATES MUST ACTUALLY BLOCK. build() has always returned the verdict and
    # this line has always thrown it away, so every failing build exited 0 and
    # left a shippable-looking JPEG on disk. That is why "five built, four
    # clean" was reported when zero of five passed both suites - the word FAIL
    # scrolled past and nothing acted on it. The identical bug was already found
    # and fixed in scripts/make_short.py ("main() returned into the void; gates
    # need an exit code") and never carried across.
    ok = build(a.case, a.work, a.out or os.path.join(a.work, f"{a.case}_thumb.jpg"),
               a.white, a.yellow, a.kicker, arrow=not a.no_arrow,
               type_style=a.type_style)
    sys.exit(0 if ok else 1)
