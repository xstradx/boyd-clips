"""eye.py - the rubric grader. A local VLM looking at a thumbnail.

This is the piece that makes the system work on ANY thumbnail with no context,
which is what Nathan asked for and what Pikzels actually does.

The reverse-engineering, 2026-08-29: Pikzels' score endpoint returns subscores
named clarity / curiosity / emotion / idea / virality plus one free-text
suggestion (schema fetched from docs.pikzels.com/openapi.json). Those are RUBRIC
DIMENSIONS, not the output of a pixels-to-CTR regressor - a regressor emits one
number, and "idea" is not a pixel property. So the product is a vision-language
model grading against a rubric. That is why it needs no channel context: the
general knowledge of what a good thumbnail looks like is already inside the
model. It also explains the measured absence of any public pixels-to-CTR model.

Ours runs locally, so it is free, unlimited and offline.

The rubric lives in spec/THUMBNAIL_RUBRIC.md and is read at runtime - one source
of truth, editable without touching this file.

  python scripts/eye.py grade <img> [--model NAME] [--json]
  python scripts/eye.py anchors          # re-grade the two calibration anchors
  python scripts/eye.py selftest         # is a vision model actually reachable?
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "spec" / "THUMBNAIL_RUBRIC.md"
OWN = ROOT / "research" / "reference" / "ttt_own"

_h = os.environ.get("OLLAMA_HOST", "").strip()
if not _h:
    _h = "http://localhost:11434"
elif not _h.startswith("http"):
    # OLLAMA_HOST is commonly a bare host or host:port (e.g. "0.0.0.0"),
    # which is a bind address, not a URL. Normalise it.
    _h = "http://" + (_h if ":" in _h else _h + ":11434")
if _h.startswith("http://0.0.0.0"):
    _h = _h.replace("0.0.0.0", "127.0.0.1")
OLLAMA = _h.rstrip("/")
DEFAULT_MODEL = os.environ.get("BOYD_VLM", "qwen3.6-35b-abliterated-vision")

DIMENSIONS = [
    "focal_clarity", "subject_isolation", "emotional_read", "headline_force",
    "colour_separation", "feed_survival", "curiosity_gap", "authenticity",
]

# The two real outcomes the rubric is anchored on, same channel, same format,
# same judge - so the model is calibrated against measured results rather than
# against adjectives.
ANCHORS = {
    "cSz-vkSwVlk": dict(views=9800, role="best Boyd long-form on the channel"),
    "OGj_eLUXjrk": dict(views=55, role="worst - a screenshot with words on it"),
}

PROMPT = """You are grading a YouTube thumbnail for a real courtroom-clip
channel. Judge only what you can SEE in the image.

{rubric}

Grade the image on each of the eight dimensions, 0-100.

Rules you must follow:
- Every score must cite the specific thing you observed that drove it. A score
  with a vague reason ("good composition") is invalid; say WHAT you saw.
- Count the competing elements for focal_clarity and say the number.
- For headline_force, state the word count and whether it is ALL CAPS or
  sentence case.
- Do not guess at click-through rate. Do not output a "viral percentage".
- If you cannot see something, say so rather than inventing it.

Reply with STRICT JSON only, no prose around it, in exactly this shape:
{{"scores": {{"focal_clarity": 0, "subject_isolation": 0, "emotional_read": 0,
"headline_force": 0, "colour_separation": 0, "feed_survival": 0,
"curiosity_gap": 0, "authenticity": 0}},
"reasons": {{"focal_clarity": "", "subject_isolation": "", "emotional_read": "",
"headline_force": "", "colour_separation": "", "feed_survival": "",
"curiosity_gap": "", "authenticity": ""}},
"biggest_problem": "", "single_highest_value_fix": ""}}"""


def _post(path, payload, timeout=600):
    req = urllib.request.Request(
        OLLAMA + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # ollama puts the real reason in the body; a bare traceback hides it.
        # Measured 2026-08-29: a 500 here is usually resource contention -
        # this model is ~21 GB against 16 GB of VRAM, so it cannot load while
        # a Q3 render is using the machine. That is an operational fact worth
        # printing rather than a bug to chase.
        try:
            body = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            body = "(no body)"
        raise SystemExit(
            "ollama returned HTTP %s\n  %s\n"
            "  If a render is running, the model cannot fit alongside it - "
            "wait for the render, then retry." % (exc.code, body))


def models():
    try:
        return [m["name"] for m in _post.__globals__["_get"]("/api/tags")["models"]]
    except Exception:
        pass
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10) as r:
            return [m["name"] for m in json.loads(r.read().decode())["models"]]
    except Exception as exc:
        raise SystemExit("ollama not reachable at %s (%s). Start it with:\n"
                         "  ollama serve" % (OLLAMA, exc))


def grade(img: Path, model: str):
    if not img.exists():
        raise SystemExit("no such image: %s" % img)
    have = models()
    if model not in have:
        # ollama reports tags as "name:latest"; accept the bare name too.
        match = [m for m in have if m.split(":")[0] == model.split(":")[0]]
        if not match:
            raise SystemExit(
                "model %r is not installed.\ninstalled: %s\n"
                "Pick one with --model, or set BOYD_VLM." % (model, ", ".join(have)))
        model = match[0]

    b64 = base64.b64encode(img.read_bytes()).decode("ascii")
    prompt = PROMPT.format(rubric=RUBRIC.read_text(encoding="utf-8"))

    out = _post("/api/generate", dict(
        model=model, prompt=prompt, images=[b64], stream=False,
        format="json", options=dict(temperature=0.2, num_predict=1600)))

    raw = (out.get("response") or "").strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        return dict(ok=False, raw=raw, thinking=out.get("thinking"),
                    error="model did not return valid JSON")

    scores = parsed.get("scores") or {}
    missing = [d for d in DIMENSIONS if d not in scores]
    vals = [scores[d] for d in DIMENSIONS if isinstance(scores.get(d), (int, float))]
    parsed["ok"] = not missing
    parsed["missing_dimensions"] = missing
    parsed["overall"] = round(sum(vals) / len(vals), 1) if vals else None
    parsed["model"] = model
    parsed["eval_tps"] = (
        round((out.get("eval_count") or 0) / ((out.get("eval_duration") or 1) / 1e9), 1))
    return parsed


def show(img, r):
    print("%s" % img.name)
    if not r.get("ok"):
        print("  GRADE FAILED: %s" % r.get("error", "missing dimensions"))
        if r.get("missing_dimensions"):
            print("  missing: %s" % ", ".join(r["missing_dimensions"]))
        if r.get("raw"):
            print("  raw response (first 300 chars):\n  %s" % r["raw"][:300])
        return 1
    print("  overall %s/100   (%s, %s tok/s)"
          % (r["overall"], r["model"], r["eval_tps"]))
    for d in DIMENSIONS:
        why = (r.get("reasons") or {}).get(d, "")
        print("   %-19s %3s   %s" % (d, r["scores"].get(d), why[:88]))
    if r.get("biggest_problem"):
        print("\n  biggest problem : %s" % r["biggest_problem"])
    if r.get("single_highest_value_fix"):
        print("  highest-value fix: %s" % r["single_highest_value_fix"])
    return 0


SEPARATION_MIN = 20.0


def separates(model):
    """The eye must rank the two MEASURED extremes far apart.

    Claim being tested, exactly: it separates the channel's best-performing
    Boyd thumbnail (9,800 views) from its worst (55 views) by a wide margin.
    Nothing more - see honesty() for what this does NOT license.
    """
    got = {}
    for vid in ANCHORS:
        img = OWN / (vid + ".jpg")
        if not img.exists():
            print("missing anchor image: %s" % img)
            return 1
        r = grade(img, model)
        if not r.get("ok"):
            print("anchor %s failed to grade: %s" % (vid, r.get("error")))
            return 1
        got[vid] = r["overall"]

    win = [v for v in ANCHORS if ANCHORS[v]["views"] == max(
        a["views"] for a in ANCHORS.values())][0]
    lose = [v for v in ANCHORS if v != win][0]
    margin = got[win] - got[lose]

    print("winner %s (%d views): %.1f" % (win, ANCHORS[win]["views"], got[win]))
    print("loser  %s (%d views): %.1f" % (lose, ANCHORS[lose]["views"], got[lose]))
    print("margin %.1f (required >= %.1f, and the winner must be higher)"
          % (margin, SEPARATION_MIN))
    if margin < SEPARATION_MIN:
        print("FAILED: the eye does not separate the measured extremes")
        return 1
    print("for contrast, the OLD gate score ranked these BACKWARDS: "
          "95.1 SHIP for the 55-view loser, 71.4 WEAK for the 9,800 winner")
    print("SEPARATES")
    return 0


def honesty():
    """The eye must NOT claim to predict views, and its measured limit must be
    on the record rather than buried.

    This gate exists because the flattering number here is rho=+0.50 across all
    eight of the channel's Boyd long-forms - which is driven by the two anchors
    that are NAMED IN THE RUBRIC. On the six it has never seen, rho was -0.20.
    Reporting the +0.50 without the -0.20 would be the exact overclaim this
    whole rebuild was meant to stop.
    """
    problems = []

    rub = RUBRIC.read_text(encoding="utf-8")
    if "cannot predict CTR" not in rub:
        problems.append("spec/THUMBNAIL_RUBRIC.md no longer states it cannot "
                        "predict CTR")

    banned = ("viral_percentage", "predicted_ctr", "ctr_estimate", "virality_pct")
    src = Path(__file__).read_text(encoding="utf-8")
    for b in banned:
        if b in src and "banned" not in src.split(b)[0][-80:]:
            problems.append("eye.py emits a field implying CTR prediction: %s" % b)

    rec = OWN / "eye_vs_views.txt"
    if not rec.exists():
        problems.append("the measured correlation against real views is not on "
                        "record at %s" % rec)
    else:
        t = rec.read_text(encoding="utf-8")
        if "UNSEEN" not in t:
            problems.append("the record does not separate anchors from unseen "
                            "thumbnails, so it cannot show the honest number")

    if problems:
        print("OVERCLAIM RISK:")
        for p in problems:
            print("  -", p)
        return 1

    print("rubric states plainly that it cannot predict CTR")
    print("no output field implies a click-through or virality percentage")
    print("measured correlation is on record, split anchors vs unseen:")
    for line in (OWN / "eye_vs_views.txt").read_text(encoding="utf-8").splitlines():
        if "Spearman" in line or "comparison" in line:
            print("   ", line.strip())
    print("NO_OVERCLAIM")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade"); g.add_argument("image")
    g.add_argument("--model", default=DEFAULT_MODEL); g.add_argument("--json", action="store_true")
    a_ = sub.add_parser("anchors"); a_.add_argument("--model", default=DEFAULT_MODEL)
    sub.add_parser("selftest")
    sp = sub.add_parser("separates"); sp.add_argument("--model", default=DEFAULT_MODEL)
    sub.add_parser("honesty")
    a = ap.parse_args()

    if a.cmd == "honesty":
        return honesty()
    if a.cmd == "separates":
        return separates(a.model)
    if a.cmd == "selftest":
        have = models()
        print("ollama reachable at %s" % OLLAMA)
        print("installed models: %s" % ", ".join(have))
        vis = [m for m in have if "vision" in m or "vl" in m.lower()]
        if not vis:
            print("NO VISION MODEL INSTALLED - eye.py cannot grade anything yet.")
            return 1
        print("vision-capable: %s" % ", ".join(vis))
        print("VISION_READY")
        return 0

    if a.cmd == "anchors":
        rc = 0
        for vid, meta in ANCHORS.items():
            img = OWN / (vid + ".jpg")
            print("\n=== %s  (%d views - %s)" % (vid, meta["views"], meta["role"]))
            rc |= show(img, grade(img, a.model))
        return rc

    img = Path(a.image)
    r = grade(img, a.model)
    if a.json:
        print(json.dumps(r, indent=1))
        return 0 if r.get("ok") else 1
    return show(img, r)


if __name__ == "__main__":
    raise SystemExit(main())
