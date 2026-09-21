# -*- coding: utf-8 -*-
"""DIRECT thumbnail generation (thumbnail.mode: direct_gen), 2026-09-06.

Nathan: skip the compositor. Give the image model the real assets and the
story, and let it generate the finished thumbnails - the way he did by hand
with ChatGPT for Flores. Claude orchestrates:

    gather assets (defendant cutouts, Boyd reactions, courtroom plates)
    -> story brief (angle, money moment, verbatim lines, facts, prop idea)
    -> ONE codex exec session with the images attached
       (built-in image_gen, gpt-image-2, ChatGPT login - proven 2026-09-06:
        referenced_image_paths carries the real faces through)
    -> the model generates three concept FAMILIES, reviews its own output,
       retries weak ones inside a budget (2 per concept, 9 images per case)
    -> deterministic QC here (size, text inside the frame and readable at
       feed size, faces intact, identity against the source crops, text
       grounded in the case, no profanity, no defendant name, concepts
       materially different)
    -> a failed concept is regenerated with the remaining budget
    -> three 1280x720 JPEGs + manifest + contact sheet

Concept families (families, not templates):
    A  defendant-only courtroom CONTROL - clean, minimal, high readability
    B  defendant + Judge Boyd reaction - interpersonal tension
    C  the strongest story-prop / art-directed concept - highest upside

What is reused from the old path, as services only: the prepared cutouts in
thumbwork/<CASE>/ and the libraries under assets/harvest/, tools/identity.py
(SFace), tools/matting.py (alpha for fallback extraction), the censor, the
feed-size diff from tools/check_variants.py. Not used: tools/thumb.py's
fixed layout, the SIFT duplicate-face gate (false-fails generated faces),
the old quality-floor envelopes.

    python tools/thumb_direct.py FLORES
    python tools/thumb_direct.py FLORES --dry-run        # brief + prompt only, no model call
    python tools/thumb_direct.py FLORES --out "D:/Boyd Clips/READY-TO-POST/FLORES/direct"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boydclips.censor import censor, has_profanity  # noqa: E402

CASES = ROOT / "config" / "cases.json"
SCHEMA = ROOT / "tools" / "thumb_direct_schema.json"
THUMBWORK = Path(r"D:/Boyd Clips/thumbwork")
READY = Path(r"D:/Boyd Clips/READY-TO-POST")
REACTIONS = ROOT / "assets" / "harvest" / "reactions" / "boyd"
BACKGROUNDS = ROOT / "assets" / "harvest" / "backgrounds"

W, H = 1280, 720
FAMILIES = ("A", "B", "C")
DEFAULTS: dict[str, Any] = {
    "budget": 9,                # hard cap on generated images per case
    "model_call_budget": 7,     # initial session + at most two retries/family
    "retries": 2,               # per concept, inside the session
    "identity_min": 0.55,       # SFace cosine, generated face vs source crop (measured: 0.73-0.91 on real outputs, 0.03-0.06 cross-identity)
    "min_variant_diff": 12.0,   # mean-abs at 168x94 between finals (tools/check_variants: he could not see 10.5, saw 12.5)
    "text_margin_frac": 0.02,   # ink may not touch the outer 2 % of the frame (Image 2 / the probe sit at 2.5 %)
    "text_min_height_frac": 0.09,   # tallest text block >= 9 % of frame height (readable at 168 px)
    "ocr_min_recall": 0.6,      # words of the reported text recovered by OCR at 336 px
    "hero_face_min_frac": 0.28, # largest face >= 28 % of frame height
    "effort": "medium",
    "model": None,              # None = codex default
    "timeout_s": 1800,
    "max_text_words": 12,  # complete reviewed thought/dialogue; mobile readability still gates every image
}


# ---------------------------------------------------------------- case + assets


def load_case(case: str) -> dict[str, Any]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if case not in cases:
        raise SystemExit(f"{case}: not in config/cases.json")
    c = dict(cases[case])
    c["_key"] = case
    return c


def transcript_words(c: dict[str, Any]) -> list[str]:
    p = c.get("transcript")
    if not p:
        return []
    path = ROOT / p if not os.path.isabs(p) else Path(p)
    if not path.exists():
        return []
    t = json.loads(path.read_text(encoding="utf-8"))
    words = t.get("words") if isinstance(t, dict) else t
    lo, hi = float(c.get("case_from", 0)), float(c.get("case_to", 1e12))
    return [w["w"] for w in words if lo - 1 <= float(w.get("t", 0)) <= hi + 1]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9$.%, ]+", " ", s.lower().replace("’", "'")).strip()


def _norm_tokens(s: str) -> list[str]:
    return [t.strip(".,!?\"'“”:;") for t in _norm(s).split() if t.strip(".,!?\"'“”:;")]


@dataclass
class Assets:
    defendant: list[Path] = field(default_factory=list)
    boyd: list[Path] = field(default_factory=list)
    rooms: list[Path] = field(default_factory=list)
    refs: dict[str, Path] = field(default_factory=dict)   # identity references: defendant / boyd

    def attachments(self) -> list[tuple[str, Path]]:
        out = []
        for i, p in enumerate(self.defendant[:2], 1):
            out.append((f"defendant_{i}", p))
        for i, p in enumerate(self.boyd[:3], 1):
            out.append((f"boyd_{i}", p))
        for i, p in enumerate(self.rooms[:2], 1):
            out.append((f"room_{i}", p))
        return out


def gather_assets(c: dict[str, Any], work: Path | None = None) -> Assets:
    """Best available cutouts and plates for the case. Order of preference:
    the case's own prepared work dir (thumbwork/<CASE>), then the libraries
    (approved Boyd cutouts, harvested plates), then extraction from the
    video (frames around the hook, alpha from BiRefNet)."""
    key = c["_key"]
    a = Assets()
    wd = work or (THUMBWORK / key)
    for name in ("defendant_surgical.png", "defendant_colour.png", "defendant_hypir.png", "defendant_raw.png"):
        p = wd / name
        if p.exists() and p not in a.defendant:
            a.defendant.append(p)
    for name in ("judge_surgical_colour.png", "judge_surgical.png"):
        p = wd / name
        if p.exists():
            a.boyd.append(p)
            break                                    # one from the case; the library adds other expressions
    if REACTIONS.exists():
        idx = REACTIONS / "index.json"
        usable: list[Path] = []
        try:
            items = json.loads(idx.read_text(encoding="utf-8"))
            items = items if isinstance(items, list) else list(items.values())
            for it in items:
                if isinstance(it, dict) and it.get("usable", True) and not it.get("defects"):
                    f = Path(it.get("file") or it.get("name") or "")
                    if f.exists():
                        usable.append(f)
        except Exception:  # noqa: BLE001
            usable = sorted(REACTIONS.glob("boyd_*_approved.png"))
        for p in usable:
            if p not in a.boyd and p.resolve() not in [q.resolve() for q in a.boyd]:
                a.boyd.append(p)
    for name in ("bg_hypir.png", "bg_raw.png"):
        p = wd / name
        if p.exists():
            a.rooms.append(p)
            break
    if BACKGROUNDS.exists():
        for sub in sorted(BACKGROUNDS.iterdir()):
            if sub.is_dir() and sub.name != key:
                pngs = sorted(x for x in sub.glob("*.png") if not x.name.startswith("_"))
                if pngs:
                    a.rooms.append(pngs[0])
            if len(a.rooms) >= 3:
                break
    if not a.defendant:
        extracted = extract_from_video(c, wd)
        a.defendant.extend(extracted.get("defendant", []))
        a.rooms = extracted.get("rooms", []) + a.rooms
        if not a.boyd:
            a.boyd.extend(extracted.get("boyd", []))
    if a.defendant:
        a.refs["defendant"] = a.defendant[0]
    if a.boyd:
        a.refs["boyd"] = a.boyd[0]
    return a


def parse_crop(spec: str) -> tuple[int, int, int, int] | None:
    """'crop=W:H:X:Y' -> (W, H, X, Y)."""
    m = re.match(r"crop=(\d+):(\d+):(\d+):(\d+)", str(spec))
    return tuple(int(v) for v in m.groups()) if m else None  # type: ignore[return-value]


def boyd_tile_index(scores: list[float], margin: float = 0.05) -> int | None:
    """Which tile holds the judge, given each tile's best SFace cosine against
    the Boyd reference. None when no tile shows a face that looks like her
    (nothing to separate) or two tiles tie within `margin`."""
    if not scores:
        return None
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    top = order[0]
    if scores[top] < 0.2:
        return None
    if len(order) > 1 and scores[top] - scores[order[1]] < margin:
        return None
    return top


def person_box(face: tuple[float, float, float, float], width: int, height: int,
               side: float = 1.7, above: float = 0.7, below: float = 4.0) -> tuple[int, int, int, int]:
    """A generous crop around one face (x, y, w, h in pixels): shoulders on
    both sides, hair above, torso below, clipped to the tile. The matting
    model then separates this ONE person from the room instead of every
    person standing at the lectern."""
    x, y, w, h = face
    cx = x + w / 2.0
    x0 = int(max(0, cx - side * w))
    x1 = int(min(width, cx + side * w))
    y0 = int(max(0, y - above * h))
    y1 = int(min(height, y + h + below * h))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def _tile_faces(bgr) -> list[tuple[float, float, float, float, float]]:
    """(width_px, fx, fy, fw, fh) rows for pipeline.choose_subject_face."""
    import identity as I  # noqa: E402
    h, w = bgr.shape[:2]
    rows = []
    for r in I.faces_in(bgr, 0.6):
        x, y, fw, fh = (float(v) for v in r[:4])
        rows.append((fw, (x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h))
    return rows


def _person_crop(tile, face, choose):
    """The lectern person's pixels inside one tile, or None."""
    th, tw = tile.shape[:2]
    rows = _tile_faces(tile)
    f = choose(rows, face)
    if f is None:
        return None, rows, None
    _w, fx, fy, fw, fh = f
    box = person_box((fx * tw - fw * tw / 2, fy * th - fh * th / 2, fw * tw, fh * th), tw, th)
    x, y, w, h = box
    return tile[y:y + h, x:x + w], rows, {"face": [round(fx, 3), round(fy, 3)], "box": list(box)}


def _matte(person, out_path: Path, M, cv2, np) -> Path | None:
    try:
        alpha = M.alpha(person, refine=True)
        rgba = np.dstack([person, (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
        cv2.imwrite(str(out_path), rgba)
        return out_path
    except Exception:  # noqa: BLE001
        return None


def extract_from_video(c: dict[str, Any], out_dir: Path, samples: int = 5) -> dict[str, list[Path]]:
    """Fallback asset extraction (no prepared work dir): grab frames around
    the hook, find the judge's tile of the 2-up by face identity, take the
    person at the lectern from the OTHER tile, matte that person with
    BiRefNet (alpha only), keep the sharpest. The generator re-renders the
    person, so no restore pass is needed here.

    Before 2026-09-06 this cropped the LEFT tile and handed it over as the
    defendant. On this docket the left tile is Judge Boyd, so Garcia's three
    concepts rendered the judge in an orange jumpsuit. The defendant is now
    chosen by the same lectern rule the short uses (pipeline.choose_subject_face)
    and Boyd's tile is only ever used for the judge's own reference."""
    from boydclips import render as R  # noqa: E402
    from boydclips.pipeline import choose_subject_face  # noqa: E402
    video = c.get("video")
    if not video:
        return {}
    src = ROOT / video if not os.path.isabs(video) else Path(video)
    if not src.exists():
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    offset = float(c.get("offset", 0.0))
    hook = float(c.get("plate_t") or c.get("hook_t") or c.get("call_t") or 0.0) - offset
    try:
        tiles = R.detect_tile_crops(src)
    except Exception:  # noqa: BLE001
        tiles = None
    try:
        import cv2
        import numpy as np
        sys.path.insert(0, str(ROOT / "tools"))
        import matting as M  # noqa: E402
        import identity as I  # noqa: E402
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[Path]] = {"defendant": [], "boyd": [], "rooms": []}
    ts = [max(0.0, hook + d) for d in (-2.0, -1.0, 0.0, 1.0, 2.0)][:samples]
    frames = []
    for k, t in enumerate(ts):
        frame = out_dir / f"_frame_{k}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", str(frame)],
                       capture_output=True)
        if frame.exists():
            bgr = cv2.imread(str(frame))
            if bgr is not None:
                frames.append((frame, bgr))
    if not frames:
        return out
    H, W = frames[0][1].shape[:2]
    geoms = [g for g in (parse_crop(t) for t in (tiles or ())) if g] or [(W, H, 0, 0)]

    def crop(im, g):
        return im[g[3]:g[3] + g[1], g[2]:g[2] + g[0]]

    # the judge's tile: best Boyd cosine over all sampled frames
    ref = I.load_reference()
    scores = [-1.0] * len(geoms)
    for _f, bgr in frames:
        for i, g in enumerate(geoms):
            tile = crop(bgr, g)
            for r in I.faces_in(tile, 0.6):
                try:
                    scores[i] = max(scores[i], I.score_against(I.embed(tile, r), ref))
                except Exception:  # noqa: BLE001
                    continue
    bi = boyd_tile_index(scores)
    if bi is None and len(geoms) > 1:
        bi = 0                                       # docket layout: judge left, courtroom right
    court = [i for i in range(len(geoms)) if i != bi] or [0]
    di = court[0]
    # the lectern person in the courtroom tile, sharpest frame wins
    best = None
    for frame, bgr in frames:
        tile = crop(bgr, geoms[di])
        person, rows, finfo = _person_crop(tile, "defendant", choose_subject_face)
        if person is None:
            continue
        sharp = cv2.Laplacian(cv2.cvtColor(person, cv2.COLOR_BGR2GRAY), cv2.CV_32F).var()
        if best is None or sharp > best[0]:
            best = (sharp, frame, bgr, tile, person, dict(finfo, tile=di, boyd_tile=bi, faces=len(rows),
                                                          boyd_scores=[round(s, 3) for s in scores]))
    if best is None:
        # no face at the lectern in any sample: hand over the whole courtroom tile
        frame, bgr = frames[0]
        tile = crop(bgr, geoms[di])
        best = (0.0, frame, bgr, tile, tile, {"tile": di, "face": None, "boyd_tile": bi, "faces": 0,
                                              "boyd_scores": [round(s, 3) for s in scores]})
    _s, frame, bgr, tile, person, info = best
    plate = out_dir / "courtroom_tile.png"
    cv2.imwrite(str(plate), tile)
    cut = _matte(person, out_dir / "defendant_extracted.png", M, cv2, np)
    if cut is None:
        cut = out_dir / "defendant_raw_crop.png"
        cv2.imwrite(str(cut), person)
    out["defendant"].append(cut)
    if bi is not None:
        judge, _rows, jinfo = _person_crop(crop(bgr, geoms[bi]), "boyd", choose_subject_face)
        if judge is not None:
            bcut = _matte(judge, out_dir / "boyd_extracted.png", M, cv2, np)
            if bcut is not None:
                out["boyd"].append(bcut)
            info["boyd"] = jinfo
    info["frame"] = frame.name
    (out_dir / "extraction.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    out["rooms"].append(plate)
    return out


# ---------------------------------------------------------------- the brief


def read_copy(key: str) -> str:
    for p in (READY / key / f"COPY-PASTE-{key}.txt", READY / f"COPY-PASTE-{key}.txt"):
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return ""


def defendant_name_tokens(c: dict[str, Any]) -> set[str]:
    toks: set[str] = set()
    for k in ("defendant", "defendant_full"):
        for t in _norm_tokens(str(c.get(k, ""))):
            if len(t) >= 3 and t not in ("the", "and", "jr", "sr", "j."):
                toks.add(t)
    for extra in re.findall(r"'([A-Z][a-z]+)'", str(c.get("name_note", ""))):
        toks.add(extra.lower())
    return toks


def build_brief(c: dict[str, Any], args: argparse.Namespace | None = None) -> dict[str, Any]:
    """Everything the model needs to art-direct, and nothing it may invent:
    the story, the money moment, verbatim lines it may print, facts with
    numbers, an optional prop idea. Never the defendant's name."""
    copy = read_copy(c["_key"])
    titles: list[str] = [str(title) for title in c.get("title_candidates", []) if str(title).strip()]
    for line in copy.splitlines():
        m = re.match(r"\s+[ABC]\s+\[\d+\]\s+(.+)$", line)
        if m:
            titles.append(m.group(1).strip())
    if args and getattr(args, "titles", None):
        titles = list(args.titles) + titles
    quote = " ".join(x for x in (c.get("white", ""), c.get("yellow", "")) if x).strip()
    lines = [q for q in (quote, c.get("kicker", "")) if q]
    concept_directions = dict(c.get("concept_directions") or {})
    lines.extend(
        str(row.get("thumbnail_text") or "")
        for row in concept_directions.values()
        if str(row.get("thumbnail_text") or "").strip()
    )
    for t in titles:
        lines += re.findall(r"\"([^\"]{6,80})\"", t)
    desc = ""
    if "DESCRIPTION" in copy:
        body = copy.split("DESCRIPTION", 1)[1]
        paras = [p.strip() for p in body.split("\n\n") if p.strip() and not p.startswith("---")]
        desc = " ".join(paras[1:4])[:1200] if len(paras) > 1 else ""
    story = (args.story if args and getattr(args, "story", None) else None) or c.get("story_angle") or desc or str(c.get("note", ""))[:600]
    money = (args.money_moment if args and getattr(args, "money_moment", None) else None) or quote
    prop = (args.prop if args and getattr(args, "prop", None) else None) or c.get("prop_idea") or ""
    name_tokens = defendant_name_tokens(c)
    facts = []
    for m in re.finditer(r"(\$[\d,]+(?:\.\d+)?|\b\d+ (?:years?|months?|days?)\b)[^.;,\n]{0,50}", desc or str(c.get("note", ""))):
        facts.append(m.group(0).strip())
    return {
        "case": c["_key"],
        "story": censor(str(story)),
        "money_moment": censor(str(money)),
        "allowed_lines": [censor(l) for l in dict.fromkeys(lines) if l],
        "titles": [censor(t) for t in titles[:3]],
        "concept_directions": concept_directions,
        "facts": [censor(f) for f in facts[:6]],
        "prop_idea": censor(str(prop)),
        "forbidden_tokens": sorted(name_tokens),
        "hearing": f"Judge Stephanie Boyd, 187th District Court, Bexar County, Texas; {c.get('hearing_date', '')}",
    }


def build_prompt(brief: dict[str, Any], attachments: list[tuple[str, Path]], cfg: dict[str, Any]) -> str:
    budget, retries = int(cfg["budget"]), int(cfg["retries"])
    files = "\n".join(f"  - {label}: {p.name}" for label, p in attachments)
    who = {"defendant": "the defendant (orange jail uniform)", "boyd": "Judge Stephanie Boyd (black robe, glasses)", "room": "the courtroom"}
    legend = "\n".join(f"  - files named {k}_N are {v}" for k, v in who.items())
    lines = "\n".join(f'  - "{l}"' for l in brief["allowed_lines"]) or "  (none)"
    facts = "\n".join(f"  - {f}" for f in brief["facts"]) or "  (none)"
    titles = "\n".join(f"  - {t}" for t in brief["titles"]) or "  (none)"
    prop = brief["prop_idea"] or "none suggested - propose one only if it explains the story instantly"
    directions = json.dumps(brief.get("concept_directions") or {}, ensure_ascii=False, indent=2)
    return f"""You are the thumbnail art director for the YouTube channel Texas Trial Tracker (courtroom video of Judge Stephanie Boyd, 187th District Court, Bexar County). Produce THREE finished, high-CTR YouTube thumbnails for one hearing, each a different concept, using the built-in image_gen tool with the attached reference images passed as reference/input images (referenced_image_paths) so the REAL people appear.

ATTACHED FILES
{files}
{legend}

THE STORY (never print the defendant's name; he is "the defendant" or "he")
{brief['story']}

MONEY MOMENT (the line the video is built around): "{brief['money_moment']}"
Title candidates for the video (context only, do not copy them onto the image):
{titles}
Supporting lines and approved thumbnail copy (the matching A/B/C thumbnail_text below controls the rendered wording):
{lines}
Facts you may state in a short caps phrase instead of a quote (numbers must stay exact):
{facts}
Prop idea: {prop}

CASE-SPECIFIC TITLE + THUMBNAIL PAIRS
Use the matching A/B/C direction below. The family rules still apply; this
direction supplies the real story, text, expression and credibility risks.
{directions}

THREE CONCEPT FAMILIES - produce exactly one thumbnail per family, saved as concept_A.png, concept_B.png, concept_C.png in the current working directory (copy the selected generated PNG there with one shell command each):
  A. COURT OF JUSTICE CONTROL. Defendant-only, big and sharp, inside the authentic courtroom. Clean hierarchy, high credibility, minimal clutter. No Judge Boyd and no prop unless the case direction requires one.
  B. DEFENDANT + JUDGE BOYD CONFRONTATION. Both people visible; their real tension is the picture. Judge Boyd's expression must match a supplied same-hearing reference. Use clearly attributed speaker labels only when the case direction calls for dialogue.
  C. STRONGEST CASE STORY / REACTION CONCEPT. Use the strongest human story, truthful reaction, or case-specific prop only when it makes the real story immediate. Highest creative upside, still serious and credible.
These are families, not layouts: choose the composition that serves each concept. Do not reuse one layout three times.

HARD RULES for every image
  - 16:9 landscape (target 1280x720). Faces must match the references: same person, same features. Do not invent other recognisable people; background figures must be small or soft.
  - Use one compact text block, {cfg['max_text_words']} words or fewer, unless B's approved case direction requires two-speaker dialogue. In that one exception, use two short quote blocks with explicit BOYD / DEFENDANT attribution and keep the same total word cap.
  - Typography must fit the case direction. Keep it bold and mobile-readable. Use restrained white/yellow emphasis when useful, but vary type treatment and layout across A/B/C. Outline or shadow only as much as readability needs.
  - Render the matching A/B/C thumbnail_text exactly, preserving its words and speaker attribution. Typography and line breaks may vary; do not shorten, paraphrase or substitute words during generation or retries. If no concept-specific copy was supplied, use a complete source-grounded idea from the supporting lines/facts.
  - Nathan permits faithful paraphrases and stylistic quotation marks in planned copy. The meaning must remain truthful. Reject unfinished thoughts such as YOU BEING THE ADULT and incoherent exchanges such as PROBABLY HAUNTED / YOU SHOULDN'T. Each line must express a clear idea, and a reply must address the preceding statement. Never invent guilt, admissions, outcomes, profanity or a defendant name.
  - No face cut by the frame edge through the eyes or mouth; shoulders may bleed off. The hero face is at least a third of the frame height.
  - Keep the real courtroom recognizable. Preserve natural skin and realistic texture. Do not make Boyd blue, pale, plastic, or over-smoothed. Do not crush the background into black.
  - Reference images provide likeness and style guidance only. Never import a person, uniform, object, quote, or allegation that is absent from this case's supplied assets and facts.
  - Text never covers a face. An arrow, underline or circle is allowed only when it points at something the eye would otherwise miss.

PROCESS AND BUDGET
  1. Generate concept A, then B, then C (one image_gen call each).
  2. LOOK at each result at full size AND imagine it at 168 px wide. Score it 1-10 on: story read at a glance, face likeness and quality, text readability and placement, composition and hierarchy, no artefacts (extra fingers, garbled letters, cut faces). Reject anything with garbled text, wrong faces, a cut face, or a score under 7.
  3. Regenerate a rejected concept with a corrected prompt: at most {retries} retries per concept, and NEVER more than {budget} generated images in total for this whole task. Stop retrying when the budget is spent and keep the best version you have.
  4. Copy each final PNG to concept_A.png / concept_B.png / concept_C.png in the current working directory. Do not resize; do not add anything after generation.
  5. Your final reply must be ONLY the JSON object described by the output schema: concepts (family, file, text exactly as rendered, prop or null, one-line description of the composition, attempts, self_score, rejected_files), images_generated_total, notes.
"""


# ---------------------------------------------------------------- the session


class UsageLimit(RuntimeError):
    """The subscription's rolling limit refused the session. Not a bug: wait
    for the time in the message (or buy credits - his call), then rerun."""


def _stage_image(src: Path, dst: Path, max_side: int = 1600) -> None:
    """Copy an attachment into the session dir as PNG, downscaled so the
    reference payload stays small (a 5 MB library cutout is not a better
    reference than a 1 MB one)."""
    from PIL import Image
    im = Image.open(src)
    if max(im.size) > max_side:
        r = max_side / max(im.size)
        im = im.resize((max(1, int(im.size[0] * r)), max(1, int(im.size[1] * r))), Image.LANCZOS)
    im.save(dst, "PNG", optimize=True)


def run_codex(prompt: str, attachments: list[tuple[str, Path]], workdir: Path, cfg: dict[str, Any],
              extra_args: list[str] | None = None) -> dict[str, Any]:
    """One codex exec session: images attached, workspace-write sandbox in
    `workdir`, structured final message. Returns the parsed JSON."""
    workdir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for label, p in attachments:
        dst = workdir / f"{label}.png"
        if not dst.exists() or dst.stat().st_mtime < p.stat().st_mtime:
            _stage_image(p, dst)
        staged.append(dst)
    codex = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        raise RuntimeError("codex CLI not on PATH")
    last = workdir / "last_message.json"
    if last.exists():
        last.unlink()
    cmd = [codex, "exec"]
    for s in staged:
        cmd += ["-i", str(s)]
    if cfg.get("model"):
        cmd += ["-m", str(cfg["model"])]
    cmd += ["-c", f'model_reasoning_effort="{cfg.get("effort", "medium")}"',
            "--sandbox", "workspace-write", "--skip-git-repo-check",
            "-C", str(workdir), "-o", str(last), "--output-schema", str(SCHEMA)]
    if extra_args:
        cmd += extra_args
    cmd += ["-"]
    log = workdir / f"codex_{int(time.time())}.log"
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.run(cmd, input=prompt, text=True, encoding="utf-8", errors="replace",
                              stdout=fh, stderr=subprocess.STDOUT, timeout=float(cfg.get("timeout_s", 1800)))
    if not last.exists():
        tail = log.read_text(encoding="utf-8", errors="replace")
        errs = [l.strip() for l in tail.splitlines() if l.startswith("ERROR")]
        if any("usage limit" in e.lower() for e in errs):
            m = re.search(r"try again at ([^.]+)", " ".join(errs))
            raise UsageLimit(f"ChatGPT/Codex usage limit reached; try again at {m.group(1) if m else 'the time in the log'} (see {log})")
        raise RuntimeError(f"codex exec produced no final message (exit {proc.returncode}); "
                           f"{'; '.join(errs[-2:]) or 'no ERROR line'}; see {log}")
    raw = last.read_text(encoding="utf-8", errors="replace").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise RuntimeError(f"final message is not JSON; see {log}")
        data = json.loads(m.group(0))
    data["_log"] = str(log)
    data["_exit"] = proc.returncode
    return data


# ---------------------------------------------------------------- deterministic QC


def normalize_to_1280(src: Path, dst: Path) -> dict[str, Any]:
    """Any 16:9-ish PNG (image_gen returns 1672x941) -> exactly 1280x720
    JPEG q95. Off-aspect input is centre-cropped to 16:9 first."""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w, h = im.size
    ar = w / h
    note = f"{w}x{h}"
    if abs(ar - 16 / 9) > 0.02:
        if ar > 16 / 9:
            nw = int(round(h * 16 / 9)); x0 = (w - nw) // 2; im = im.crop((x0, 0, x0 + nw, h))
        else:
            nh = int(round(w * 9 / 16)); y0 = (h - nh) // 2; im = im.crop((0, y0, w, y0 + nh))
        note += " centre-cropped to 16:9"
    im = im.resize((W, H), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    q = 95
    while True:
        im.save(dst, "JPEG", quality=q, subsampling=0, optimize=True)
        if dst.stat().st_size <= 2_000_000 or q <= 80:
            break
        q -= 3
    return {"source_size": note, "jpeg_quality": q, "bytes": dst.stat().st_size}


def text_mask(bgr):
    import numpy as np
    b, g, r = bgr[:, :, 0].astype(int), bgr[:, :, 1].astype(int), bgr[:, :, 2].astype(int)
    white = (r > 225) & (g > 225) & (b > 225)
    yellow = (r > 195) & (g > 165) & (b < 110)
    return (white | yellow)


def ink_mask(bgr):
    """Type ink only: bright pixels whose immediate surround is dark (the
    outline every thumbnail letter carries). Ceiling lights, white walls and
    the judge's collar are bright too, but their ring is not dark."""
    import cv2
    import numpy as np
    h, w = bgr.shape[:2]
    bright = text_mask(bgr).astype(np.uint8)
    dark = (cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) < 70).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    keep = np.zeros(n, dtype=bool)
    k = np.ones((5, 5), np.uint8)
    for i in range(1, n):
        a, ch = stats[i, cv2.CC_STAT_AREA], stats[i, cv2.CC_STAT_HEIGHT]
        if a < 12 or ch > 0.40 * h or stats[i, cv2.CC_STAT_WIDTH] > 0.60 * w:
            continue
        x, y, cw = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP], stats[i, cv2.CC_STAT_WIDTH]
        y0, y1, x0, x1 = max(0, y - 6), min(h, y + ch + 6), max(0, x - 6), min(w, x + cw + 6)
        comp = (lab[y0:y1, x0:x1] == i).astype(np.uint8)
        ring = cv2.dilate(comp, k) - comp
        if ring.sum() == 0:
            continue
        if (dark[y0:y1, x0:x1] & ring).sum() / ring.sum() >= 0.45:
            keep[i] = True
    return keep[lab].astype(np.uint8)


def text_geometry(bgr, cfg: dict[str, Any]) -> dict[str, Any]:
    """Where the type sits: bounding box of the letter clusters, whether it
    touches the margin, the tallest line as a frame fraction."""
    import cv2
    import numpy as np
    h, w = bgr.shape[:2]
    m = ink_mask(bgr)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 21), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return {"found": False}
    comps = [(stats[i, cv2.CC_STAT_AREA], i) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 0.0005 * w * h]
    if not comps:
        return {"found": False}
    comps.sort(reverse=True)
    keep = [i for _a, i in comps[:8]]
    ys, xs = np.where(np.isin(lab, keep))
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    margin = float(cfg["text_margin_frac"])
    touches = x0 < margin * w or y0 < margin * h or x1 > (1 - margin) * w or y1 > (1 - margin) * h
    tallest = max(stats[i, cv2.CC_STAT_HEIGHT] for i in keep)
    return {"found": True, "bbox": [int(x0), int(y0), int(x1), int(y1)], "touches_margin": bool(touches),
            "boxes": [[int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                       int(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH]),
                       int(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT])] for i in keep],
            "height_frac": round(float(tallest) / h, 3), "cover": round(float(m.mean()), 4)}


def text_face_overlap(geometry: dict[str, Any], faces: list[dict[str, Any]]) -> float:
    """Measure actual type clusters, excluding empty space between separate blocks."""
    import numpy as np
    boxes = geometry.get("boxes") or [geometry["bbox"]]
    overlap = 0.0
    for face in faces:
        fx, fy, fw, fh = map(int, face["box"])
        covered = np.zeros((max(1, fh), max(1, fw)), dtype=bool)
        for x0, y0, x1, y1 in boxes:
            left, right = max(0, x0 - fx), min(fw, x1 - fx)
            top, bottom = max(0, y0 - fy), min(fh, y1 - fy)
            if left < right and top < bottom:
                covered[top:bottom, left:right] = True
        overlap = max(overlap, float(covered.mean()))
    return overlap


def ocr_words(bgr, width: int = 336) -> list[tuple[str, float]]:
    try:
        import cv2
        from rapidocr_onnxruntime import RapidOCR
    except Exception:  # noqa: BLE001
        return []
    h, w = bgr.shape[:2]
    small = cv2.resize(bgr, (width, int(round(h * width / w))), interpolation=cv2.INTER_AREA)
    res, _ = RapidOCR()(small)
    out = []
    for r in (res or []):
        try:
            out.append((str(r[1]), float(r[2])))
        except Exception:  # noqa: BLE001
            continue
    return out


def faces_and_identity(bgr, refs: dict[str, Path], cfg: dict[str, Any], family: str | None = None) -> dict[str, Any]:
    """YuNet faces on the final frame; SFace cosine against the source crops.
    Reports which reference each large face matches best."""
    import cv2
    import numpy as np
    try:
        import identity as I  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        return {"error": f"identity unavailable: {exc}", "faces": []}
    h, w = bgr.shape[:2]
    rows = sorted(I.faces_in(bgr, 0.5), key=lambda r: -(r[2] * r[3]))
    big = [r for r in rows if r[3] >= 0.15 * h][:3]
    ref_vec: dict[str, Any] = {}
    for who, p in refs.items():
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if im is None:
            continue
        if im.ndim == 3 and im.shape[2] == 4:
            im = cv2.cvtColor(im, cv2.COLOR_BGRA2BGR)
        rr = sorted(I.faces_in(im, 0.5), key=lambda r: -(r[2] * r[3]))
        if rr:
            ref_vec[who] = I.embed(im, rr[0])
    faces = []
    for r in big:
        x, y, fw, fh = (int(v) for v in r[:4])
        cut = x < 2 or y < 2 or x + fw > w - 2 or y + fh > h - 2
        best, best_s = None, -1.0
        if ref_vec:
            v = I.embed(bgr, r)
            for who, rv in ref_vec.items():
                s = float(I.cosine(v, rv))
                if s > best_s:
                    best, best_s = who, s
        faces.append({"box": [x, y, fw, fh], "height_frac": round(fh / h, 3), "cut_by_frame": bool(cut),
                      "match": best, "cosine": round(best_s, 3)})
    return {"faces": faces, "refs": sorted(ref_vec)}


def text_grounded(text: str, brief: dict[str, Any], transcript: list[str], cfg: dict[str, Any]) -> tuple[bool, str]:
    t = text.strip()
    if not t:
        return False, "no text reported"
    if has_profanity(t):
        return False, "profanity"
    toks = _norm_tokens(t)
    from boydclips.thumbnail_copy import copy_words
    word_count = len(copy_words(t))
    if word_count > int(cfg["max_text_words"]):
        return False, f"{word_count} words > {cfg['max_text_words']}"
    for f in brief.get("forbidden_tokens", []):
        if f in toks:
            return False, f"defendant name token {f!r}"
    tnorm = " ".join(toks)
    allowed = [" ".join(_norm_tokens(l)) for l in brief.get("allowed_lines", [])]
    if any(tnorm and tnorm in a for a in allowed):
        return True, "verbatim allowed line"
    trans = " ".join(_norm_tokens(" ".join(transcript)))
    if tnorm and tnorm in trans:
        return True, "verbatim in transcript"
    facts = " ".join(_norm_tokens(" ".join(brief.get("facts", []))))
    numbers = [x for x in toks if re.match(r"^\$?\d", x)]
    for n in numbers:
        if n not in facts and n not in trans:
            return False, f"number {n!r} not in the case"
    content = [x for x in toks if len(x) > 3 and x not in ("this", "that", "with", "your", "from", "have", "what", "when", "they", "them", "just", "said", "says")]
    missing = [x for x in content if x not in trans and x not in facts]
    if content and len(missing) > max(1, len(content) // 3):
        return False, f"words not in the case: {missing}"
    return True, "phrase built from case words"


def recovered_copy_words(expected: list[str], ocr: list[str], currency_numbers: tuple[str, ...] = ()) -> set[int]:
    """OCR may merge adjacent words. Require the whole chunk to match a sequence."""
    compact = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    want = [compact(word) for word in expected]
    recovered: set[int] = set()
    for chunk in ocr:
        # Dollar glyphs are often read as S. Only normalize an explicitly
        # planned dollar amount, with every digit intact (S200 cannot match $20).
        chunk = re.sub(r"(?<![A-Za-z0-9])[Ss]([0-9]+)(?![A-Za-z0-9])",
                       lambda m: '$' + m[1] if m[1] in currency_numbers else m[0], chunk)
        # Real OCR also returns complete spaced lines in one box.
        for part in chunk.split():
            key = compact(part)
            recovered.update(i for i, word in enumerate(want) if key and word == key)
        token = compact(chunk)
        if not token:
            continue
        for start in range(len(want)):
            joined = ""
            for end in range(start, len(want)):
                joined += want[end]
                if joined == token:
                    recovered.update(range(start, end + 1))
                    break
                if len(joined) >= len(token):
                    break
    return recovered


def qc_concept(png: Path, family: str, reported: dict[str, Any], brief: dict[str, Any], refs: dict[str, Path],
               transcript: list[str], cfg: dict[str, Any], out_jpg: Path) -> dict[str, Any]:
    import cv2
    report: dict[str, Any] = {"family": family, "source": str(png), "gates": []}

    def gate(name: str, ok: bool, detail: str) -> None:
        report["gates"].append({"gate": name, "ok": bool(ok), "detail": detail})

    if not png.exists():
        gate("file_exists", False, str(png))
        report["ok"] = False
        return report
    norm = normalize_to_1280(png, out_jpg)
    report["normalized"] = norm
    bgr = cv2.imread(str(out_jpg))
    h, w = bgr.shape[:2]
    gate("dimensions", (w, h) == (W, H), f"{w}x{h} (from {norm['source_size']})")
    tg = text_geometry(bgr, cfg)
    report["text_geometry"] = tg
    direction = (brief.get("concept_directions") or {}).get(family, {})
    text_free = ("thumbnail_text" in direction and direction["thumbnail_text"] == ""
                 and str(direction.get("direction", {}).get("typography", "")).lower().startswith("no text"))
    words = ocr_words(bgr, 336)
    report["ocr_336"] = words
    want = _norm_tokens(str(reported.get("text", "")))
    got = _norm_tokens(" ".join(t for t, _s in words))
    recovered = recovered_copy_words(want, [t for t, _s in words])
    recall = len(recovered) / len(want) if want else 0.0
    report["ocr_recall"] = round(recall, 2)
    if "thumbnail_text" in direction:
        from boydclips.thumbnail_copy import copy_words, fragment_errors
        expected = copy_words(direction["thumbnail_text"])
        actual = copy_words(str(reported.get("text", "")))
        gate("reviewed_copy_unchanged", actual == expected,
             f"rendered words {actual!r}; approved words {expected!r}")
        errors = fragment_errors(str(reported.get("text", "")))
        gate("complete_copy", not errors, "; ".join(errors) or "no incomplete construction")
        critical = [word for word in expected if word in {"not", "no", "never", "without"}
                    or word.endswith("n't") or any(c.isdigit() for c in word)]
        currency_numbers = tuple(re.findall(r"\$\s*([0-9]+)\b", direction["thumbnail_text"]))
        visible_indices = recovered_copy_words(expected, [t for t, _s in words], currency_numbers)
        visible = [expected[i] for i in visible_indices]
        missing = [word for word in critical if word not in visible]
        gate("critical_copy_words_visible", not missing,
             f"missing meaning-changing words/numbers in feed OCR: {missing}" if missing else "negations and numbers recovered")
        report["copy_binding"] = {"words": actual, "sha256": hashlib.sha256(out_jpg.read_bytes()).hexdigest()}
    if text_free:
        gate("intentional_text_free", not want and not words,
             "Producer explicitly requested no text; reported text and feed OCR must both be empty")
    else:
        gate("text_present", tg.get("found", False), "bright type found" if tg.get("found") else "no bright type found")
        gate("text_inside_frame", tg.get("found", False) and not tg.get("touches_margin", True),
             f"bbox {tg.get('bbox')} margin {cfg['text_margin_frac']:.0%}")
        gate("text_size", tg.get("found", False) and tg.get("height_frac", 0) >= float(cfg["text_min_height_frac"]),
             f"tallest text block {tg.get('height_frac', 0):.1%} of height (floor {cfg['text_min_height_frac']:.0%})")
        gate("text_readable_336", recall >= float(cfg["ocr_min_recall"]) if want else bool(words),
             f"OCR at 336 px recovered {recall:.0%} of {want!r}: {[t for t, _ in words]}")
        ok_text, why = text_grounded(str(reported.get("text", "")), brief, transcript, cfg)
        gate("text_grounded", ok_text, why)
    fi = faces_and_identity(bgr, refs, cfg, family=family)
    report["faces"] = fi
    faces = fi.get("faces", [])
    gate("faces_found", len(faces) >= 1, f"{len(faces)} large face(s)")
    gate("faces_not_cut", all(not f["cut_by_frame"] for f in faces), "no large face cut by the frame" if faces else "no faces")
    hero = max((f["height_frac"] for f in faces), default=0.0)
    gate("hero_face_size", hero >= float(cfg["hero_face_min_frac"]), f"largest face {hero:.0%} of height (floor {cfg['hero_face_min_frac']:.0%})")
    imin = float(cfg["identity_min"])
    by = {}
    for f in faces:
        if f["match"] and f["cosine"] > by.get(f["match"], -1):
            by[f["match"]] = f["cosine"]
    need = ["defendant"] if family in ("A", "B") else []
    if family == "B":
        need.append("boyd")
    if family == "C" and not need:
        need = ["defendant"] if "defendant" in fi.get("refs", []) else []
    for who in need:
        gate(f"identity_{who}", by.get(who, 0.0) >= imin, f"SFace cosine {by.get(who, 0.0):.2f} (floor {imin})")
    if family == "A":
        gate("control_defendant_only", by.get("boyd", 0.0) < imin, "Judge Boyd absent from the control" if by.get("boyd", 0.0) < imin else f"Boyd present (cosine {by.get('boyd'):.2f})")
    # text over a face
    if tg.get("found") and faces:
        overlap = text_face_overlap(tg, faces)
        gate("text_clear_of_faces", overlap < 0.10, f"text clusters overlap a face by {overlap:.0%}")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sd = float(gray.std())
    gate("not_flat", sd >= 40.0, f"luma sd {sd:.0f}")
    report["self_score"] = reported.get("self_score")
    report["ok"] = all(g["ok"] for g in report["gates"])
    return report


def variant_diffs(jpgs: dict[str, Path], min_diff: float) -> dict[str, Any]:
    try:
        import check_variants as CV  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "ok": True}
    keys = sorted(jpgs)
    import numpy as np
    grays = {k: CV.sidebar_gray(str(jpgs[k])) for k in keys}
    pairs = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            pairs[f"{a}-{b}"] = round(float(np.mean(np.abs(grays[a] - grays[b]))), 1)
    return {"pairs": pairs, "min_diff": min_diff, "ok": all(v >= min_diff for v in pairs.values())}


# ---------------------------------------------------------------- orchestration


def contact_sheet(jpgs: dict[str, Path], out: Path, labels: dict[str, str]) -> Path:
    from PIL import Image, ImageDraw
    tiles = [(k, Image.open(jpgs[k]).convert("RGB")) for k in sorted(jpgs)]
    tw, th = 640, 360
    sheet = Image.new("RGB", (tw * len(tiles) + 10 * (len(tiles) - 1), th + 40), "black")
    d = ImageDraw.Draw(sheet)
    x = 0
    for k, im in tiles:
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, 40))
        d.text((x + 8, 12), f"{k}: {labels.get(k, '')}"[:90], fill="white")
        x += tw + 10
    sheet.save(out, "JPEG", quality=90)
    return out


def run_case(case: str, out_dir: Path | None = None, work: Path | None = None, args: argparse.Namespace | None = None,
             runner: Callable[..., dict[str, Any]] | None = None, cfg: dict[str, Any] | None = None,
             case_dict: dict[str, Any] | None = None, resume: bool = False) -> dict[str, Any]:
    cfg = dict(DEFAULTS, **(cfg or {}))
    if int(cfg["budget"]) < len(FAMILIES):
        raise UsageLimit(
            f"thumbnail image budget has {int(cfg['budget'])} remaining; "
            f"a complete A/B/C set needs at least {len(FAMILIES)}"
        )
    if int(cfg["model_call_budget"]) < 1:
        raise UsageLimit("thumbnail Sol-call budget is exhausted before the initial A/B/C session")
    runner = runner or run_codex
    c = dict(case_dict) if case_dict else load_case(case)
    c.setdefault("_key", case)
    work = work or (THUMBWORK / case / "direct")
    out_dir = out_dir or (READY / case / "direct")
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = gather_assets(c, args.assets if args and getattr(args, "assets", None) else None)
    if not assets.defendant:
        raise SystemExit(f"{case}: no defendant asset found (thumbwork/{case} or video extraction)")
    brief = build_brief(c, args)
    transcript = transcript_words(c)
    attachments = assets.attachments()
    prompt = build_prompt(brief, attachments, cfg)
    (work / "brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    (work / "prompt.txt").write_text(prompt, encoding="utf-8")
    manifest: dict[str, Any] = {"case": case, "mode": "direct_gen", "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "brief": brief, "assets": {k: [str(p) for p in v] for k, v in
                                                            (("defendant", assets.defendant), ("boyd", assets.boyd), ("rooms", assets.rooms))},
                                "attachments": [f"{l}={p.name}" for l, p in attachments], "config": {k: v for k, v in cfg.items()},
                                "sessions": [], "concepts": {}}
    if args and getattr(args, "dry_run", False):
        manifest["dry_run"] = True
        (work / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return manifest

    generated_total = 0
    model_calls_used = 0
    finals: dict[str, Path] = {}
    reports: dict[str, dict[str, Any]] = {}
    reported: dict[str, dict[str, Any]] = {}
    retries_used: dict[str, int] = {f: 0 for f in FAMILIES}

    # A resume keeps previous spend and passing concepts. It never starts a
    # fresh A/B/C session simply because one candidate failed visual QC.
    if resume:
        saved_path = out_dir / "manifest.json"
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        if saved.get("in_flight"):
            raise UsageLimit("previous thumbnail call has uncertain spend; reconcile its log before resuming")
        if saved.get("case") != case or saved.get("brief") != brief:
            raise ValueError("thumbnail resume source/brief changed; review before regenerating")
        manifest = saved
        generated_total = int(saved.get("images_generated_total") or 0)
        model_calls_used = int(saved.get("model_calls_used") or 0)
        retries_used.update(saved.get("retries_used") or {})
        for fam, rep in (saved.get("concepts") or {}).items():
            reported[fam] = {**(rep.get("reported") or {}), "family": fam,
                             "file": str(rep.get("source") or f"concept_{fam}.png")}
        if generated_total > int(cfg["budget"]) or model_calls_used > int(cfg["model_call_budget"]):
            raise UsageLimit("saved thumbnail spend already exceeds the supplied resume allowance")

    # session 1: all three concepts
    def checkpoint():
        manifest.update(images_generated_total=generated_total, model_calls_used=model_calls_used,
                        retries_used=retries_used, concepts=reports, config=dict(cfg))
        body = json.dumps(manifest, indent=2, ensure_ascii=False)
        for directory in (out_dir, work):
            temporary = directory / "manifest.pending.json"
            temporary.write_text(body, encoding="utf-8")
            temporary.replace(directory / "manifest.json")

    def call_runner(call_prompt, call_attachments, image_reservation):
        nonlocal model_calls_used, generated_total
        if model_calls_used >= int(cfg["model_call_budget"]):
            raise UsageLimit("thumbnail Sol-call budget is exhausted")
        model_calls_used += 1
        manifest["in_flight"] = {"model_call": model_calls_used, "images_reserved": image_reservation}
        checkpoint()
        data = runner(call_prompt, call_attachments, work, cfg)
        generated_total += int(data.get("images_generated_total") or 0)
        manifest.pop("in_flight", None)
        checkpoint()
        return data

    if not resume:
        data = call_runner(prompt, attachments, int(cfg["budget"]))
        manifest["sessions"].append({"kind": "initial", "log": data.get("_log"), "exit": data.get("_exit"),
                                     "images_generated_total": data.get("images_generated_total"), "notes": data.get("notes")})
        for cpt in data.get("concepts", []):
            fam = str(cpt.get("family", "")).upper()
            if fam in FAMILIES:
                reported[fam] = cpt

    def evaluate(fam: str) -> None:
        cpt = reported.get(fam)
        if not cpt:
            reports[fam] = {"family": fam, "ok": False, "gates": [{"gate": "reported", "ok": False, "detail": "model returned no concept"}]}
            return
        png = work / (cpt.get("file") or f"concept_{fam}.png")
        if not png.exists():
            alt = work / f"concept_{fam}.png"
            png = alt if alt.exists() else png
        out_jpg = out_dir / f"{case}_{fam}.jpg"
        rep = qc_concept(png, fam, cpt, brief, assets.refs, transcript, cfg, out_jpg)
        rep["reported"] = {k: cpt.get(k) for k in ("text", "prop", "description", "attempts", "self_score", "rejected_files")}
        reports[fam] = rep
        if rep["ok"]:
            finals[fam] = out_jpg
        elif out_jpg.exists():
            rejected = out_dir / "rejected" / f"{case}_{fam}_r{retries_used[fam]}.jpg"
            rejected.parent.mkdir(exist_ok=True)
            out_jpg.replace(rejected)
            rep["rejected_copy"] = str(rejected)

    for fam in FAMILIES:
        evaluate(fam)

    # follow-up sessions for concepts our QC rejected, inside the budget
    for fam in FAMILIES:
        while (
            not reports.get(fam, {}).get("ok")
            and retries_used[fam] < int(cfg["retries"])
            and generated_total < int(cfg["budget"])
            and model_calls_used < int(cfg["model_call_budget"])
        ):
            retries_used[fam] += 1
            remaining = int(cfg["budget"]) - generated_total
            reasons = "; ".join(f"{g['gate']}: {g['detail']}" for g in reports[fam]["gates"] if not g["ok"])
            face_hint = ("Target a face height of at least 33 percent to clear the 28 percent floor. "
                         if any(g["gate"] == "hero_face_size" and not g["ok"]
                                for g in reports[fam]["gates"]) else "")
            prev = reported.get(fam, {})
            follow = (f"REGENERATE ONLY concept {fam} for the same case. The previous attempt failed our checks: {reasons}. "
                      f"Fix exactly those problems, keep the concept family definition, keep the same real people (references attached), "
                      f"and generate exactly ONE image for this correction. {face_hint}Save the final as concept_{fam}.png in the current working directory. "
                      f"Previous text was: \"{prev.get('text', '')}\". Reply with the JSON schema (one concept).\n\n" + prompt)
            attach = list(attachments)
            previous_copy = reports[fam].get("rejected_copy")
            if previous_copy:
                prev_png = Path(previous_copy)
                if prev_png.is_file():
                    attach.append((f"previous_{fam}", prev_png))
            data = call_runner(follow, attach, 1)
            manifest["sessions"].append({"kind": f"retry_{fam}_{retries_used[fam]}", "log": data.get("_log"), "exit": data.get("_exit"),
                                         "images_generated_total": data.get("images_generated_total"), "notes": data.get("notes")})
            for cpt in data.get("concepts", []):
                if str(cpt.get("family", "")).upper() == fam:
                    reported[fam] = cpt
            evaluate(fam)
            checkpoint()

    variants = variant_diffs(finals, float(cfg["min_variant_diff"])) if len(finals) >= 2 else {"pairs": {}, "ok": True}
    manifest["variants"] = variants
    manifest["images_generated_total"] = generated_total
    manifest["model_calls_used"] = model_calls_used
    manifest["retries_used"] = retries_used
    manifest["concepts"] = reports
    manifest["finals"] = {k: str(v) for k, v in finals.items()}
    manifest["control_present"] = "A" in finals
    manifest["budget_exceeded"] = generated_total > int(cfg["budget"])
    manifest["complete"] = (
        all(f in finals for f in FAMILIES)
        and bool(variants.get("ok", True))
        and not manifest["budget_exceeded"]
    )
    if finals:
        sheet = contact_sheet(finals, out_dir / f"{case}_contact_sheet.jpg",
                              {k: f"{reported.get(k, {}).get('text', '')} | {reported.get(k, {}).get('description', '')}" for k in finals})
        manifest["contact_sheet"] = str(sheet)
    for fam, rep in reports.items():
        side = out_dir / f"{case}_{fam}.json"
        side.write_text(json.dumps({"case": case, "family": fam, "story_angle": brief["story"][:300],
                                    "text": reported.get(fam, {}).get("text"), "prop": reported.get(fam, {}).get("prop"),
                                    "source_assets": manifest["attachments"], "retry_count": retries_used[fam],
                                    "model_attempts": reported.get(fam, {}).get("attempts"),
                                    "qc": rep, "session": {"model": cfg.get("model") or "codex default", "effort": cfg.get("effort"),
                                                           "logs": [s.get("log") for s in manifest["sessions"]]}},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case")
    ap.add_argument("--out", help="final JPEGs + manifest + sheet (default D:/Boyd Clips/READY-TO-POST/<CASE>/direct)")
    ap.add_argument("--work", help="session workdir (default D:/Boyd Clips/thumbwork/<CASE>/direct)")
    ap.add_argument("--assets", help="prepared asset dir to read instead of thumbwork/<CASE>")
    ap.add_argument("--model", help="codex model (default: codex config)")
    ap.add_argument("--effort", default=None, help="model_reasoning_effort (default medium)")
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument("--retries", type=int, default=None)
    ap.add_argument("--story", help="story angle override")
    ap.add_argument("--money-moment", dest="money_moment")
    ap.add_argument("--title", dest="titles", action="append")
    ap.add_argument("--prop")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true", help="write brief + prompt, call no model")
    a = ap.parse_args()
    cfg: dict[str, Any] = {}
    for k in ("model", "effort", "budget", "retries"):
        if getattr(a, k) is not None:
            cfg[k] = getattr(a, k)
    m = run_case(a.case, Path(a.out) if a.out else None, Path(a.work) if a.work else None, a, cfg=cfg)
    if m.get("dry_run"):
        print(f"DRY RUN: brief + prompt in {Path(a.work) if a.work else THUMBWORK / a.case / 'direct'}")
        return 0
    print(f"{a.case}: {len(m['finals'])}/3 finals, {m['images_generated_total']} images generated, retries {m['retries_used']}, "
          f"variants {'ok' if m['variants'].get('ok') else 'TOO SIMILAR'}, control {'present' if m['control_present'] else 'MISSING'}")
    for fam, rep in m["concepts"].items():
        bad = [g["gate"] for g in rep.get("gates", []) if not g["ok"]]
        print(f"  {fam}: {'PASS' if rep.get('ok') else 'FAIL ' + ','.join(bad)}  text={rep.get('reported', {}).get('text')!r}")
    print(f"  sheet: {m.get('contact_sheet')}")
    return 0 if m["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
