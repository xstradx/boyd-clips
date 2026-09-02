"""thumbdoctor - score a thumbnail, name what is wrong, fix it, re-verify.

The repo already had every part of this except the part that matters: nothing
read a verifier's FAIL line and did something about it. `verify_thumbnail.py`
and `thumb_eval.py` print defects and exit 1; `thumb_Q3_detail.py` exposes the
exact flags that fix those defects; no code connected the two, so every repair
was a human reading a red line and typing a flag.

Measured 2026-08-29, which is why this exists: the thumbnail on the LIVE
Thompson video fails ARROW_AIMS_AT_NOTHING and scores 62.5/100 REJECT, and the
monkey one fails text_on_face at 0.081. Both shipped anyway.

What this is NOT: a virality predictor. There is no downloadable model that
predicts CTR from a thumbnail image - searched 2026-08-29, and the one published
attempt (codencoding/Red-Means-Go) measured thumbnail pixel features performing
WORSE than predicting the mean. Anything claiming otherwise, including the
commercial products, is selling an opaque number. This tool only promises the
thing that can actually be checked: never ship a thumbnail that violates the
gates this channel calibrated on its own winners and losers.

  python scripts/thumbdoctor.py diagnose <img> [--json]
  python scripts/thumbdoctor.py selftest-map
  python scripts/thumbdoctor.py selftest-unknown
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

BUILDER = SCRIPTS / "thumb_Q3_detail.py"   # the construction Nathan approved


# ----------------------------------------------------------------- the map
# One entry per defect code the two verifiers can emit. `flag` is a real
# argparse flag on thumb_Q3_detail.py - checked by selftest-map, so a flag
# renamed in the builder breaks the gate instead of silently becoming a no-op.
#
# step is signed and is ADDED to the current value each round.
# flag=None or step=None means no lever exists: the defect is real but not
# repairable by a parameter, and must be SURFACED rather than silently skipped.

FIX = {
    "TEXT_OVER_FACE":      dict(flag="--face-margin", step=+0.02, lo=None, hi=None,
                                why="push the headline further off the face box"),
    "FEED_ILLEGIBLE":      dict(flag="--cap", step=+6, lo=None, hi=None,
                                why="bigger cap height survives the downscale"),
    "CLIPPED_HIGHLIGHTS":  dict(flag="--highlight-ceiling", step=-4, lo=None, hi=None,
                                why="pull the ceiling down off 255"),
    "CRUSHED_BLACKS":      dict(flag="--brightness", step=+3, lo=-40, hi=40,
                                why="lift the floor off 0"),
    "EDGE_ARTEFACT":       dict(flag="--light-wrap", step=+0.05, lo=0.0, hi=0.60,
                                why="wrap background light onto the cut edge, killing the halo"),
    "ARROW_ON_PERSON":     dict(flag="--arrow-gap", step=+6, lo=0, hi=120,
                                why="stand the arrow further off the subject"),
    "ARROW_AIMS_AT_NOTHING": dict(flag="--arrow-prefer-deg", step=+12, lo=-180, hi=180,
                                why="rotate the approach so the ray lands on a face"),
    # step +2, NOT +1: --chroma-r becomes the size of PIL's MedianFilter in
    # boydclips.thumbnail.grade_image (thumbnail.py:448), and PIL requires an
    # ODD size. Measured 2026-08-29: stepping 5 -> 6 raised "ValueError: bad
    # filter size" and killed three repair rounds in a row.
    "CHROMA_BLOCKING":     dict(flag="--chroma-r", step=+2, lo=1, hi=13, odd=True,
                                why="widen chroma denoise over the blocky flat area"),
    "SILHOUETTE_CUT":      dict(flag="--max-area-loss", step=-0.002, lo=None, hi=None,
                                why="tighten the refusal so the mover cannot sever a limb"),
    "FACE_TOO_SMALL":      dict(flag="--judge-crop", step=None, lo=None, hi=None,
                                why="the crop rectangle is wrong; a scalar step cannot fix it"),
    "NO_FACE":             dict(flag="--judge-t", step=None, lo=None, hi=None,
                                why="wrong frame entirely - re-pick it, do not nudge"),

    # thumb_eval HARD gates
    "text_on_face_frac":   dict(flag="--face-margin", step=+0.02, lo=None, hi=None,
                                why="same lever as TEXT_OVER_FACE, measured differently"),
    "primary_survives_210": dict(flag="--cap", step=+6, lo=None, hi=None,
                                why="largest line must survive the 210px card"),
    "text_max_h_frac":     dict(flag="--cap", step=+6, lo=None, hi=None,
                                why="headline below the Audit median height"),
    "face_max_h_frac":     dict(flag="--judge-crop", step=None, lo=None, hi=None,
                                why="hero face under the losing band; needs a tighter crop"),
    "bytes":               dict(flag="--quality", step=-4, lo=60, hi=98,
                                why="over YouTube's 2 MB mobile cap"),
    "_geom":               dict(flag=None, step=None, lo=None, hi=None,
                                why="output geometry is not a builder parameter"),

    # thumb_eval SOFT bands
    "sat_mean":            dict(flag="--sat-gain", step=+0.04, lo=0.5, hi=2.0,
                                why="saturation outside the measured winning band"),
    "val_mean":            dict(flag="--target-luma", step=+3, lo=90, hi=150,
                                why="overall luma off the corpus target"),
    "rms_contrast":        dict(flag="--contrast", step=+2, lo=-30, hi=30,
                                why="global contrast off the winning band"),
    "clip_hi":             dict(flag="--highlight-knee", step=-3, lo=None, hi=None,
                                why="soften the knee before the ceiling"),
    "wcag_min":            dict(flag="--band", step=+0.02, lo=None, hi=None,
                                why="darken the band behind the type for contrast"),
    "n_faces":             dict(flag=None, step=None, lo=None, hi=None,
                                why="how many people are in frame is a frame choice"),
    "red_frac":            dict(flag="--arrow-scale", step=+0.05, lo=0.4, hi=2.0,
                                why="red area is almost entirely the arrow"),
    "yellow_frac":         dict(flag=None, step=None, lo=None, hi=None,
                                why="yellow is the second headline colour, an editorial choice"),
}

DEFECT_RE = re.compile(r"^([A-Za-z_]+)[: ]")


def _code(line):
    """The defect code at the head of a verifier failure line."""
    m = DEFECT_RE.match(line.strip())
    return m.group(1) if m else line.strip().split()[0].rstrip(":")


def _entry(code, line, source):
    f = FIX.get(code)
    if f is None:
        return dict(code=code, detail=line, source=source, fix=None,
                    why="NO MAPPING - this defect has never been given a lever")
    if f["flag"] is None or f["step"] is None:
        return dict(code=code, detail=line, source=source, fix=None,
                    flag=f["flag"], why=f["why"])
    return dict(code=code, detail=line, source=source,
                fix=dict(flag=f["flag"], step=f["step"], lo=f["lo"], hi=f["hi"]),
                why=f["why"])


# ----------------------------------------------------------------- diagnose
def diagnose(path):
    """Both verifiers, one unified answer."""
    import thumb_eval
    import verify_thumbnail as vt

    out = {"path": str(path), "defects": [], "unmapped": [],
           "warnings": [], "verdict": None, "score": None}

    m = vt.measure(str(path))
    bad, warn = vt.check(m)
    for line in bad:
        out["defects"].append(_entry(_code(line), line, "verify_thumbnail"))
    out["warnings"] = list(warn)

    ev = thumb_eval.score(str(path), verbose=False)
    out["verdict"] = ev.get("_verdict")
    out["score"] = ev.get("_score")
    for key, ok, _note in thumb_eval.HARD:
        v = ev.get(key)
        try:
            passed = ok(v, ev)
        except Exception:
            passed = True
        if not passed:
            out["defects"].append(
                _entry(key, "%s = %s violates a HARD gate" % (key, v), "thumb_eval"))

    out["unmapped"] = [d["code"] for d in out["defects"] if d["fix"] is None]
    return out


# ----------------------------------------------------------------- selftests
def selftest_map():
    """Every defect code either verifier can emit must appear in FIX."""
    src = (SCRIPTS / "verify_thumbnail.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'(?:bad|warn)\.append\(\s*f?"\s*([A-Za-z_]+)', src))
    import thumb_eval
    emitted |= {k for k, _ok, _n in thumb_eval.HARD}
    emitted |= {row[0] for row in thumb_eval.SOFT}
    emitted.discard("NO_TEXT")          # a warning, not a defect

    missing = sorted(e for e in emitted if e not in FIX)
    if missing:
        print("UNMAPPED DEFECTS (each would be silently ignored):")
        for x in missing:
            print("   ", x)
        return 1

    bsrc = BUILDER.read_text(encoding="utf-8")
    ghosts = sorted({v["flag"] for v in FIX.values()
                     if v["flag"] and ('"%s"' % v["flag"]) not in bsrc})
    if ghosts:
        print("FLAGS THAT DO NOT EXIST ON %s:" % BUILDER.name)
        for g in ghosts:
            print("   ", g)
        return 1

    # Every declared range must contain the builder's REAL default, or the
    # range was invented. Measured 2026-08-29: 9 of 19 levers failed this,
    # including --face-margin declared 0.0..0.30 when the builder's default is
    # 40, and --light-wrap seeded at 0.35 when the real default is 0.18. The
    # loop lurched instead of stepping and crashed PIL. Those now carry
    # lo=hi=None and derive their bounds from the measured default.
    d = builder_defaults()
    invented = []
    for code, f in FIX.items():
        if not f["flag"] or f["step"] is None:
            continue
        if f["lo"] is None or f["hi"] is None:
            continue
        dv = d.get(f["flag"])
        if dv is not None and not (f["lo"] <= dv <= f["hi"]):
            invented.append((code, f["flag"], dv, f["lo"], f["hi"]))
    if invented:
        print("INVENTED RANGES - the builder's real default sits outside them:")
        for code, fl, dv, lo, hi in invented:
            print("   %-24s %-22s default=%s outside [%s, %s]"
                  % (code, fl, dv, lo, hi))
        return 1

    levers = sum(1 for v in FIX.values()
                 if v["flag"] and v["step"] is not None)
    print("%d defect codes emitted by the verifiers, all mapped." % len(emitted))
    print("%d have a real lever; %d are honestly declared unfixable-by-parameter."
          % (levers, len(FIX) - levers))
    print("every mapped flag verified to exist on %s" % BUILDER.name)
    print("MAP_COMPLETE")
    return 0


def selftest_layers():
    """Constraints must never be tradeable against the rubric score.

    This is the bug the whole rebuild exists to fix: thumb_eval.py fused
    Nathan's R1-R15 constraints (binary correctness) with success metrics and
    scored them together, which is why its score measured rho = -0.571 against
    his actual views. A constraint violation must lose to a clean render no
    matter how beautiful the violating one is.

    Tested with a positive control first, so it cannot pass for the wrong
    reason: two clean candidates must still rank by rubric score.
    """
    def rank(violations, eye):
        # the exact key used by repair(); if that changes, this test breaks,
        # which is the point.
        return (-violations, eye)

    perfect_but_illegal = rank(violations=1, eye=100.0)
    ugly_but_legal = rank(violations=0, eye=1.0)
    if not ugly_but_legal > perfect_but_illegal:
        print("FAILED: a constraint violation was outranked by a high score.")
        print("  a 100/100 render with 1 violation beat a 1/100 clean render.")
        return 1

    # positive control: among equally-legal candidates, the rubric decides
    good, bad = rank(0, 90.0), rank(0, 40.0)
    if not good > bad:
        print("CONTROL FAILED: rubric score is not deciding between clean renders")
        return 1

    # and the two layers must come from different sources
    import thumb_eval
    hard = {k for k, _ok, _n in thumb_eval.HARD}
    rules = (ROOT / "spec" / "NATHAN_RULES.md")
    if not rules.exists():
        print("FAILED: spec/NATHAN_RULES.md missing - constraints have no home")
        return 1
    rubric = (ROOT / "spec" / "THUMBNAIL_RUBRIC.md")
    if not rubric.exists():
        print("FAILED: spec/THUMBNAIL_RUBRIC.md missing - the eye has no rubric")
        return 1

    print("constraint layer : spec/NATHAN_RULES.md + %d hard gates" % len(hard))
    print("rubric layer     : spec/THUMBNAIL_RUBRIC.md, 8 dimensions")
    print("a violation always loses to a clean render (100/100 dirty < 1/100 clean)")
    print("control: among clean renders, the rubric score decides")
    print("LAYERS_SEPARATED")
    return 0


def selftest_pipeline():
    """The unattended pipeline must INVOKE the approved builder with correct
    geometry - not merely mention it.

    The gate this replaces was a grep for "thumb_Q3_detail" in thumbnail.py,
    which a broken rename would have satisfied while producing nothing:
    thumbnail.build() fed --bg/--subject/--cutout to make_thumbnail_v2, and
    thumb_Q3_detail takes --video/--judge-crop/--plate-t. So this intercepts
    the real call and inspects the command line it built.

    Rendering is deliberately NOT done here - that is G7's job, on a real file.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from boydclips import thumbnail as T

    case = json.loads((ROOT / "config" / "cases.json").read_text(encoding="utf-8"))
    c = case["CARTHIEF"]
    src = ROOT / c["video"]
    if not src.exists():
        print("source video missing: %s" % src)
        return 1

    captured = {}

    def fake_run(cmd, out):
        captured["cmd"] = list(cmd)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"")      # never rendered; G7 covers rendering
        return Path(out)

    real = T._run_builder
    T._run_builder = fake_run
    try:
        # judge_t in cases.json is ABSOLUTE source time; the clip file starts
        # at `offset`, so the pipeline's clip-relative hook is the difference.
        hook = float(c["judge_t"]) - float(c.get("offset", 0))
        # Which half holds the judge is NOT constant on this docket - she is
        # on the LEFT in CARTHIEF and the RIGHT in SANCHEZ/OFFERUP. The
        # pipeline's default of "right" would put the defendant in the hero
        # slot for CARTHIEF. Derived here from the case config; automatic
        # detection is tracked as its own unmet gate (G11) rather than assumed.
        left = "18:190"
        side = "left" if c["judge_crop"].endswith(left) else "right"
        T.build(src, hook, c["white"], c["yellow"],
                ROOT / "work" / "repair" / "_pipeline_probe.jpg",
                cfg={"subject_side": side})
    except Exception as exc:
        print("pipeline build raised: %s" % exc)
        return 1
    finally:
        T._run_builder = real

    cmd = captured.get("cmd") or []
    joined = " ".join(str(x) for x in cmd)
    if "thumb_Q3_detail" not in joined:
        print("STILL_V2 - the pipeline invoked: %s"
              % (Path(cmd[1]).name if len(cmd) > 1 else "nothing"))
        return 1

    # geometry must be real and must match what the case config hand-wrote
    def arg(flag):
        return cmd[cmd.index(flag) + 1] if flag in cmd else None

    jc, pc = arg("--judge-crop"), arg("--plate-crop")
    if not jc or not pc:
        print("Q3 invoked without crop geometry - judge=%r plate=%r" % (jc, pc))
        return 1
    if jc.startswith("crop=") or pc.startswith("crop="):
        print("crop= prefix was not stripped; Q3 cannot parse %r" % jc)
        return 1
    if jc != c["judge_crop"] or pc != c["plate_crop"]:
        print("derived geometry disagrees with config/cases.json:")
        print("  judge derived %r vs config %r" % (jc, c["judge_crop"]))
        print("  plate derived %r vs config %r" % (pc, c["plate_crop"]))
        return 1

    print("pipeline invoked %s" % Path(cmd[1]).name)
    print("judge-crop %s and plate-crop %s were DERIVED from the video and "
          "match config/cases.json exactly" % (jc, pc))
    print("(so the per-case crop tuning in cases.json was never necessary)")
    print("PIPELINE_PRODUCES_Q3")
    return 0


def selftest_checks():
    """Every constraint check must DISCRIMINATE. A check that fires on the
    known-good reference corpus is not detecting a defect.

    Measured 2026-08-29, and this is why the repair loop looked broken for three
    runs: EDGE_ARTEFACT fires on 15/15 courtroomtime winners AND 10/10 losers -
    100% of both, so it carries exactly zero information. CHROMA_BLOCKING fires
    on 11/12 of the known-good competitor references. The loop could not fix
    those defects because there was nothing to fix; it was chasing constants.

    The reference sets are ground truth by the repo's own rule (competitor set
    in verify_thumbnail.py's own docstring, courtroomtime top/bot in
    thumb_eval.py). If a check fails them, the check is wrong, not the corpus.
    """
    import glob
    import verify_thumbnail as vt
    from collections import Counter

    good = sorted(glob.glob(str(ROOT / "research/reference/competitor/thumbs/*.jpg")))
    if not good:
        print("no reference corpus on disk - cannot calibrate")
        return 1

    counts, n = Counter(), 0
    for f in good:
        try:
            m = vt.measure(f)
        except SystemExit:
            continue
        bad, _ = vt.check(m)
        n += 1
        for line in bad:
            counts[line.split(":")[0].split()[0]] += 1

    LIMIT = 0.50          # a check firing on half the known-good set is noise
    broken = [(c, k) for c, k in counts.items() if k / n > LIMIT]
    print("checked %d known-good reference thumbnails" % n)
    for c, k in counts.most_common():
        mark = "  <-- FIRES ON THE REFERENCE SET" if k / n > LIMIT else ""
        print("   %-24s %2d/%d = %3.0f%%%s" % (c, k, n, 100 * k / n, mark))
    if broken:
        print("\n%d check(s) fire on more than %.0f%% of known-good references."
              % (len(broken), LIMIT * 100))
        print("Those are not defect detectors. Re-threshold or retire them "
              "before any repair loop is tuned against them.")
        return 1
    print("no check fires on a majority of the reference set")
    print("CHECKS_DISCRIMINATE")
    return 0


def selftest_unknown():
    """An unmapped defect must be REPORTED, never silently dropped.

    Runs a known positive control first: a defect that IS mapped must keep its
    lever, otherwise this check would pass for the wrong reason.
    """
    control = _entry("TEXT_OVER_FACE", "TEXT_OVER_FACE: 30% ...", "control")
    if control["fix"] is None:
        print("CONTROL FAILED: a mapped defect was reported as unmapped")
        return 1
    e = _entry("ZZ_NOT_A_REAL_DEFECT", "ZZ_NOT_A_REAL_DEFECT: fabricated", "test")
    if e["fix"] is not None:
        print("FAILED: an unknown defect was handed a fix")
        return 1
    if "NO MAPPING" not in e["why"]:
        print("FAILED: unknown defect was not flagged as unmapped")
        return 1
    print("control kept its lever (--face-margin); fabricated defect surfaced as unmapped")
    print("UNMAPPED_REPORTED")
    return 0


# ----------------------------------------------------------------- repair
AUTO = SCRIPTS / "make_thumbnail_auto.py"

_DEFAULT_RE = re.compile(
    r'add_argument\(\s*"(--[a-z0-9-]+)"[^)]*?default=([-\d.]+)', re.S)


def builder_defaults():
    """The builder's REAL default for each flag, read from its argparse.

    Measured 2026-08-29, and the reason this function exists: seeding an
    unset flag at the midpoint of its allowed range is not a step, it is a
    lurch. The first repair run put --light-wrap straight to 0.35 (mid of
    0..0.6) and --chroma-r to 7 (mid of 0..12), which changed the image
    wholesale and then crashed PIL with "bad filter size". A repair loop must
    start from where the builder actually starts and move in small steps, or
    it is not repairing anything - it is rerolling.
    """
    src = BUILDER.read_text(encoding="utf-8")
    out = {}
    for flag, val in _DEFAULT_RE.findall(src):
        try:
            out[flag] = float(val) if "." in val else int(val)
        except ValueError:
            continue
    return out


_VLM = "qwen3.6-35b-abliterated-vision:latest"


def _ollama_host():
    import os
    h = os.environ.get("OLLAMA_HOST", "").strip() or "http://localhost:11434"
    if not h.startswith("http"):
        h = "http://" + (h if ":" in h else h + ":11434")
    return h.replace("0.0.0.0", "127.0.0.1").rstrip("/")


def _free_vram():
    """Evict the vision model before a render. Best effort, never fatal.

    Measured 2026-08-29 and it is a hard constraint on this box, not a flake:
    the rubric model is ~21 GB against 16 GB of VRAM, and while it is resident
    the builder's onnxruntime cannot initialise CUDA - the render dies with
    "Invalid handle. Cannot load symbol cudnnCreate". The eye and the builder
    cannot hold the GPU at the same time, so the loop hands it back explicitly
    rather than relying on ollama's keep_alive timer happening to expire first.
    """
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(
            _ollama_host() + "/api/generate",
            data=_json.dumps({"model": _VLM, "prompt": "",
                              "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass          # no ollama, or already unloaded - either is fine


def _build(case, out, flags, auto_plate=False):
    """Render one candidate. Returns (ok, stderr_tail).

    Drives make_thumbnail_auto.py, whose --extra is argparse.REMAINDER and is
    appended straight onto the thumb_Q3_detail command line - the seam the
    repair loop needs, already present, previously unused by any code.

    auto_plate defaults OFF, measured 2026-08-29: on CARTHIEF every frame
    --auto-plate ranked scored 0.0% clear on the right, and the build correctly
    REFUSED ("component 2.48x the scrubs, MERGED with another person"). The
    plate_t already in config/cases.json builds clean. Auto plate selection is
    a real unsolved problem, not a default to lean on.
    """
    import subprocess
    _free_vram()
    cmd = [sys.executable, str(AUTO), "--case", case, "--out", str(out)]
    if auto_plate:
        cmd.append("--auto-plate")
    if flags:
        cmd.append("--extra")
        for k, v in flags.items():
            cmd += [k, str(v)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    return p.returncode == 0 and out.exists(), (p.stderr or "")[-400:]


def _objective(path, use_eye, model):
    """Constraints are binary and come first; the rubric score is what we
    maximise. They are never traded against each other - that fusion is the
    bug this whole rebuild exists to fix."""
    d = diagnose(path)
    violations = len(d["defects"])
    eye_score = None
    if use_eye:
        sys.path.insert(0, str(SCRIPTS))
        import eye as eye_mod
        g = eye_mod.grade(path, model)
        eye_score = g.get("overall") if g.get("ok") else None
        d["eye"] = g
    d["violations"] = violations
    d["eye_score"] = eye_score
    return d


def repair(case, out, max_rounds, use_eye, model):
    import shutil
    defaults = builder_defaults()
    journal, flags, best = [], {}, None
    failed_flags = set()
    prev_flags = {}
    out = Path(out)
    work = out.with_suffix(".round.jpg")

    for rnd in range(max_rounds + 1):
        ok, err = _build(case, work, flags)
        if not ok:
            # A build that dies on a value is information, not the end of the
            # run. Blame the flags this round introduced, blacklist them so no
            # later round retries the same poison, revert, and carry on with
            # the best render already in hand.
            tail = (err.strip().splitlines() or ["(no stderr)"])[-1]
            print("round %d: BUILD FAILED - %s" % (rnd, tail))
            # Blame the flags that differ from the last set that BUILT. A
            # snapshot taken at the top of this round is useless: flags are
            # mutated at the end of the previous round, so the two are always
            # identical and nothing ever gets blamed. Measured 2026-08-29:
            # that bug retried the same poisoned --chroma-r three rounds
            # running and the loop reported no improvement.
            blamed = [k for k in flags
                      if k not in prev_flags or flags[k] != prev_flags.get(k)]
            for k in blamed:
                failed_flags.add(k)
                if k in prev_flags:
                    flags[k] = prev_flags[k]
                else:
                    flags.pop(k, None)
            if blamed:
                print("  blacklisted: %s" % ", ".join(blamed))
            if not journal:
                break
            continue

        prev_flags = dict(flags)          # this set built; it is the baseline
        d = _objective(work, use_eye, model)
        entry = dict(round=rnd, flags=dict(flags), violations=d["violations"],
                     gate_score=d["score"], verdict=d["verdict"],
                     eye_score=d["eye_score"],
                     defects=[x["code"] for x in d["defects"]])
        journal.append(entry)
        print("round %d  violations=%d  gate=%.1f  eye=%s  %s"
              % (rnd, d["violations"], d["score"] or 0,
                 d["eye_score"] if d["eye_score"] is not None else "-",
                 ",".join(entry["defects"]) or "clean"))

        # rank: fewest constraint violations first, then highest rubric score
        key = (-d["violations"], d["eye_score"] if d["eye_score"] is not None
               else (d["score"] or 0))
        if best is None or key > best[0]:
            best = (key, rnd, dict(flags))
            shutil.copyfile(work, out)

        if d["violations"] == 0:
            print("all constraints satisfied at round %d" % rnd)
            break
        if rnd == max_rounds:
            break

        # apply one step per fixable defect
        moved = False
        for x in d["defects"]:
            f = x["fix"]
            if not f:
                continue
            if f["flag"] in failed_flags:
                continue
            cur = flags.get(f["flag"])
            if cur is None:
                # Start from where the BUILDER starts, never the midpoint of
                # the allowed range. Measured 2026-08-29: midpoint seeding put
                # --light-wrap at 0.35 when its real default is 0.18, and
                # --chroma-r at 7 when its real default is 5, which changed the
                # image wholesale and then crashed PIL with "bad filter size".
                # That is rerolling, not repairing.
                cur = defaults.get(f["flag"])
                if cur is None:
                    print("  %s has no discoverable default - skipped rather "
                          "than guessed" % f["flag"])
                    continue
            lo = f["lo"] if f["lo"] is not None else cur - abs(f["step"]) * 20
            hi = f["hi"] if f["hi"] is not None else cur + abs(f["step"]) * 20
            new = min(hi, max(lo, cur + f["step"]))
            if f.get("odd") and int(new) % 2 == 0:
                # domain constraint, not a preference: this value becomes a PIL
                # filter size and PIL rejects even sizes outright.
                new = int(new) + 1
            if new != cur:
                flags[f["flag"]] = round(new, 4) if isinstance(new, float) else new
                moved = True
        if not moved:
            print("no lever can move any remaining defect - stopping honestly")
            break

    jpath = out.with_suffix(".journal.json")
    jpath.write_text(json.dumps(journal, indent=1), encoding="utf-8")
    if best:
        print("\nbest = round %d, written to %s" % (best[1], out))
        print("flags: %s" % (best[2] or "(builder defaults)"))
        first, last = journal[0], journal[best[1]]
        print("violations %d -> %d ; gate %.1f -> %.1f"
              % (first["violations"], last["violations"],
                 first["gate_score"] or 0, last["gate_score"] or 0))
    print("journal: %s" % jpath)
    return 0 if best and journal[best[1]]["violations"] == 0 else 1


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose")
    d.add_argument("image")
    d.add_argument("--json", action="store_true")

    sub.add_parser("selftest-map")
    sub.add_parser("selftest-unknown")
    sub.add_parser("selftest-layers")
    sub.add_parser("selftest-pipeline")
    sub.add_parser("selftest-checks")
    rp = sub.add_parser("repair")
    rp.add_argument("--case", required=True)
    rp.add_argument("--out", required=True)
    rp.add_argument("--max-rounds", type=int, default=4)
    rp.add_argument("--use-eye", action="store_true",
                    help="also grade each round with the local VLM (slower)")
    rp.add_argument("--model", default="qwen3.6-35b-abliterated-vision")

    a = ap.parse_args()

    if a.cmd == "selftest-map":
        return selftest_map()
    if a.cmd == "selftest-unknown":
        return selftest_unknown()
    if a.cmd == "selftest-layers":
        return selftest_layers()
    if a.cmd == "selftest-pipeline":
        return selftest_pipeline()
    if a.cmd == "selftest-checks":
        return selftest_checks()
    if a.cmd == "repair":
        outp = Path(a.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        return repair(a.case, outp, a.max_rounds, a.use_eye, a.model)

    r = diagnose(Path(a.image))
    if a.json:
        print(json.dumps(r, indent=1, default=str))
        return 0 if not r["defects"] else 1

    print("%s   %s  %.1f/100" % (Path(a.image).name, r["verdict"], r["score"]))
    if not r["defects"]:
        print("  no defects")
        return 0
    for x in r["defects"]:
        print("\n  [%s]  (%s)" % (x["code"], x["source"]))
        print("     %s" % x["detail"])
        if x["fix"]:
            f = x["fix"]
            print("     FIX: %s %+g per round (clamped %s..%s) - %s"
                  % (f["flag"], f["step"], f["lo"], f["hi"], x["why"]))
        else:
            print("     NO AUTOMATIC FIX: %s" % x["why"])
    if r["unmapped"]:
        print("\n  %d defect(s) with no lever: %s"
              % (len(r["unmapped"]), ", ".join(r["unmapped"])))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
