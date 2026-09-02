# -*- coding: utf-8 -*-
"""critique.py — score ONE candidate thumbnail against a niche grammar and
against general design principles, and return ranked, SPECIFIC defects.

This is the module Nathan actually looks at, so it is the module where a
confident guess does the most damage. Three rules hold everywhere below:

PROVENANCE ON EVERY DEFECT. `source` is one of
    'grammar'   measured on this niche's own harvest; quotes n and effect size
    'gate'      inherited from verify_thumb.py's derived thresholds, which
                carry that file's own caveat that the approved set is n=2
    'principle' a general design heuristic with NO measured threshold on this
                machine
and `confidence` is 'measured' / 'gate' / 'heuristic' to match. A report that
prints an unvalidated 10px text-height rule in the same voice as a measured
0.22 face-area finding teaches the reader to trust the wrong half.

THE PRE-DELIVERY SCOPE RULE. verify_thumb.py measured that 10 of 12 competitor
thumbnails trip the posterisation gate purely because YouTube re-encodes them
(quant table sum 736 versus 369 for a local file). tm_flat_g_p90 and
tm_poster_fa may therefore raise a defect ONLY when source_kind == 'local'. On
a downloaded image they are reported in `diagnostics` at zero severity and can
never contribute to the score. Applying them to a harvested thumbnail condemns
work that is fine.

MEASURED BEATS ASSUMED. Where a grammar rule is meaningful for the same key a
principle covers, the grammar wins and the principle is suppressed — otherwise
one defect is counted twice and arrives louder than it earned.

---------------------------------------------------------------------------
ONE DELIBERATE DEPARTURE FROM "NO IMAGE CODE IN THIS MODULE".

The frozen FEATURE_KEYS vocabulary cannot express three checks a human spots
instantly:
    * two text blocks colliding — no vertical gap between their ink boxes
    * text running off / touching the frame edge
    * the dominant focal mass being clipped by the frame edge
There is no key for any of them, and inventing keys would fork the schema that
five parallel modules code against. So they live in `structure_probe()`, a
clearly separated function that opens the image itself, returns a plain dict of
extras, and adds NOTHING to the feature row. Everything it produces is labelled
source='principle', confidence='structural' or 'heuristic'. When no image is
available (a pre-measured row was passed in) the extras are absent and those
checks are skipped and said to be skipped — never defaulted to "fine".
---------------------------------------------------------------------------

CLI
    python -m tools.thumbeng.critique IMG [IMG ...] --niche court
    python -m tools.thumbeng.critique --compare A.jpg B.jpg
    python -m tools.thumbeng.critique --selftest
"""

import os
import sys
import math
import glob
import argparse
import importlib

import numpy as np
import cv2

# --------------------------------------------------------------------- import
# Resolve the package however this file was launched: `python -m
# tools.thumbeng.critique` sets __package__, a bare `python tools/thumbeng/
# critique.py` does not. Both must reach the same modules.
_HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
_TOOLS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_TOOLS)

if __package__:
    _PKG = __package__
else:                                            # direct-script run
    _PKG = "tools.thumbeng"
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)                   # append, never insert(0)

_base = importlib.import_module(_PKG)
SCHEMA_VERSION = _base.SCHEMA_VERSION
YUNET = _base.YUNET
niche_dir = _base.niche_dir
utc_now = _base.utc_now
write_json = _base.write_json
read_json = _base.read_json

# tools/ on sys.path by APPEND so tools/harvest.py can never shadow
# tools/thumbeng/harvest.py for anything inside this package.
_base.bootstrap_legacy()
import thumb_metrics                              # noqa: E402
import verify_thumb                               # noqa: E402
import comp_pro                                   # noqa: E402  (named in fixes)

# The three gate thresholds below are READ from verify_thumb, never restated.
# PRINCIPLES claims provenance "verify_thumb.py Gate A / C / D" for them; when
# they were literals here, a change to verify_thumb's derived limits would have
# left critique quoting a stale number under verify_thumb's name. getattr with a
# fallback so an older verify_thumb that lacks one of them still imports, and
# the fallback is the value verify_thumb carried when this was written.
GATE_FLAT = float(getattr(verify_thumb, "LIM_FLAT", 0.30))
GATE_SUBJECT_L = float(getattr(verify_thumb, "LIM_L", 180.0))
GATE_DUP = float(getattr(verify_thumb, "LIM_DUP", 1))

measure = importlib.import_module(_PKG + ".measure")


def _optional(name):
    """Import a sibling module, or None when it is not on disk yet.

    styles.py and grammar.py are genuinely optional: critique must run with
    principles only, before any harvest has happened, and say so.
    """
    try:
        return importlib.import_module(_PKG + "." + name)
    except Exception:
        return None


# ------------------------------------------------------------------ constants
SEVERITY_MAX = 100

# How far outside the winners' interquartile range counts as "as bad as it
# gets". Three IQRs is a convention adopted here, not a measurement: past that
# point the defect is already maximal and scaling further only inflates numbers.
DEV_CAP = 3.0

# Presentational bands. CHOSEN CONVENTION, not a measured cutoff — nothing on
# this machine establishes that 80 is where a thumbnail becomes shippable.
VERDICT_SHIP, VERDICT_FIX = 80.0, 50.0

# 0-100 severity mapped to the 1-5 band the brief asks for, so a report can be
# skimmed. The boundaries are a display choice, nothing more.
_SEV5_EDGES = (20.0, 40.0, 60.0, 80.0)

_FAMILY_CATEGORY = {
    "face": "face",
    "luminance": "contrast",
    "contrast": "contrast",
    "colour": "colour",
    "color": "colour",
    "palette": "colour",
    "edge": "detail",
    "detail": "detail",
    "focal": "composition",
    "saliency": "composition",
    "balance": "composition",
    "composition": "composition",
    "text": "text",
    "survival": "detail",
    "downscale": "detail",
    "provenance": "technical",
    "technical": "technical",
    "thumb_metrics": "technical",
}


# Units for the keys structure_probe produces. They are NOT in measure.KEY_DOC
# and must never be added to it - KEY_DOC describes the frozen feature vector,
# and these are extras that live only in a report. Without this table they
# would print as bare numbers and "0.001" would be read as pixels.
PROBE_KEY_DOC = {
    "text_line_count": {"unit": "count", "family": "text",
                        "meaning": "text lines found"},
    "text_min_line_gap_px": {"unit": "px", "family": "text",
                             "meaning": "gap between the closest two text lines"},
    "text_mean_line_h_px": {"unit": "px", "family": "text",
                            "meaning": "mean text line height"},
    "text_edge_margin_min": {"unit": "fraction", "family": "text",
                             "meaning": "nearest text edge to the frame border"},
    "focal_edge_touch_frac": {"unit": "fraction", "family": "focal",
                              "meaning": "share of the dominant focal mass on "
                                         "the frame border"},
    "dup_inliers": {"unit": "count", "family": "face",
                    "meaning": "matched features between two face detections"},
    "face_count_probe": {"unit": "count", "family": "face",
                         "meaning": "faces found by the probe"},
}


def _category_for(key, family=""):
    """Bucket a feature key for the report's grouping.

    Keyed off KEY_DOC's family first because that is the one place families are
    defined; the prefix fallback exists only so a key added later still lands
    somewhere sensible instead of crashing the report.
    """
    fam = (family or "").strip().lower()
    if fam in _FAMILY_CATEGORY:
        return _FAMILY_CATEGORY[fam]
    k = key or ""
    if k.startswith("face"):
        return "face"
    if k.startswith("text"):
        return "text"
    if k.startswith("lum") or k.startswith("subject_bg_lum"):
        return "contrast"
    if k.startswith(("sat", "hue", "chroma", "colour", "warm", "cool", "cct",
                     "lab", "skin", "palette")):
        return "colour"
    if k.startswith(("edge", "grad", "laplacian", "hf_", "busy", "clutter",
                     "negative", "bg_blur", "survive")):
        return "detail"
    if k.startswith(("focal", "saliency", "balance", "mass", "thirds",
                     "center", "symmetry", "quadrant")):
        return "composition"
    if k.startswith(("src_", "jpeg_", "letterbox", "source_kind", "tm_")):
        return "technical"
    return "composition"


# ------------------------------------------------------------------ formatting
def _isnum(v):
    """True for a real, finite number. Guards every threshold comparison."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _doc(key):
    """KEY_DOC entry for a key, or a minimal stand-in.

    measure.describe_key raises on an unknown key by design. Here a missing key
    must not take the whole report down, so the stand-in is used and the fact
    is recorded by the caller in notes.
    """
    try:
        return dict(measure.describe_key(key))
    except Exception:
        pass
    if key in PROBE_KEY_DOC:
        d = dict(PROBE_KEY_DOC[key])
        d.setdefault("lo", 0.0)
        d.setdefault("hi", 1.0)
        d.setdefault("higher_is", "neither")
        return d
    return {"unit": "unitless", "lo": 0.0, "hi": 1.0,
            "meaning": key.replace("_", " "), "higher_is": "neither",
            "family": ""}


def _label(key):
    """Short plain-words name for a property, from KEY_DOC and nowhere else.

    Truncated at the first clause break because KEY_DOC 'meaning' is allowed to
    be a sentence and a headline needs a noun phrase.
    """
    d = _doc(key)
    lab = d.get("label") or d.get("meaning") or key.replace("_", " ")
    lab = str(lab).strip()
    for sep in (";", " — ", " - ", ". ", ","):
        i = lab.find(sep)
        if i > 3:
            lab = lab[:i]
            break
    lab = lab.rstrip(". ")
    if len(lab) > 64:
        lab = lab[:61].rstrip() + "..."
    return lab or key.replace("_", " ")


def fmt_value(value, unit):
    """Render one measurement the way it should be read.

    Fractions become percentages because "6.1%" is a sentence a human parses and
    "0.061" is one they have to convert.
    """
    if not _isnum(value):
        return "n/a"
    v = float(value)
    u = (unit or "unitless").lower()
    if u == "fraction":
        return "%.1f%%" % (v * 100.0)
    if u == "px":
        return "%.0fpx" % v
    if u == "deg":
        return "%.0f deg" % v
    if u == "k":
        return "%.0fK" % v
    if u in ("l*", "l"):
        return "%.0f L*" % v
    if u == "bits":
        return "%.2f bits" % v
    if u == "count":
        return "%.0f" % v
    if u == "deltae":
        return "%.1f dE" % v
    if u == "0-255":
        return "%.0f" % v
    if abs(v) >= 100:
        return "%.0f" % v
    if abs(v) >= 1:
        return "%.2f" % v
    return "%.3f" % v


def severity_5(severity):
    """Map the 0-100 severity onto the 1-5 band the brief asks for.

    A non-numeric severity returns band 1 rather than raising: this runs inside
    the renderer, and a report that cannot print is worse than one that prints a
    conservative band.
    """
    if not _isnum(severity):
        return 1
    s = float(severity)
    for i, edge in enumerate(_SEV5_EDGES):
        if s <= edge:
            return i + 1
    return 5


# ------------------------------------------------------------------- fix lines
# One concrete imperative sentence per key, naming the comp_pro function where
# comp_pro already has the tool. A defect the reader cannot act on is a number,
# not a critique. Keys absent here fall back to _generic_fix.
FIX_BY_KEY = {
    "face_area_frac_largest":
        "crop tighter so the largest face fills about {target} of the frame",
    "face_area_frac_total":
        "crop in, or drop a face, until faces cover about {target} of the frame",
    "face_largest_cx":
        "slide the crop sideways so the face sits at about {target} across",
    "face_largest_cy":
        "slide the crop vertically so the face sits at about {target} down",
    "face_thirds_dist":
        "re-crop so the face lands nearer a thirds intersection",
    "face_edge_margin_min":
        "pull the crop back so no face is jammed against the frame edge",
    "face_largest_L_median":
        "re-expose the face with comp_pro.dodge_burn / comp_pro.key_light",
    "lum_michelson":
        "push the tonal range with comp_pro.grade(contrast=...) and "
        "comp_pro.dodge_burn on the subject",
    "lum_rms_contrast":
        "raise local contrast with comp_pro.dodge_burn before global grade",
    "lum_mean":
        "shift overall exposure toward {target} with comp_pro.grade",
    "lum_dark_frac":
        "lift or deepen the shadows toward {target} with comp_pro.grade(lift=...)",
    "lum_bright_frac":
        "rebalance the highlights toward {target} with comp_pro.grade",
    "lum_entropy":
        "spread the histogram: more separated tones, fewer flat regions",
    "subject_bg_lum_contrast":
        "lift subject separation with comp_pro.rim_light / comp_pro.light_wrap",
    "subject_bg_sat_contrast":
        "desaturate the plate or saturate the subject with comp_pro.grade(sat=...)",
    "subject_bg_hue_dist":
        "push the background hue away from the subject with comp_pro.harmonise",
    "sat_mean":
        "move saturation toward {target} with comp_pro.grade(sat=...)",
    "sat_p90":
        "let the accent colours reach about {target} with comp_pro.grade(sat=...)",
    "colourfulness":
        "raise colourfulness toward {target} with comp_pro.grade(sat=..., teal=...)",
    "warm_frac":
        "warm or cool the plate toward {target} with comp_pro.grade(teal=...)",
    "cct_kelvin":
        "shift white balance toward {target} with comp_pro.grade(teal=...)",
    "hue_circvar":
        "tighten the palette: fewer competing hues",
    "edge_density":
        "simplify the plate with comp_pro.depth_push(blur=...) so edges land "
        "near {target}",
    "clutter_index":
        "blur or darken the background with comp_pro.depth_push",
    "busyness_tile_std":
        "even out the detail: the frame is busy in patches",
    "negative_space_frac":
        "crop in — too much of the frame is doing nothing",
    "bg_blur_ratio":
        "separate planes with comp_pro.depth_push so the plate reads softer "
        "than the subject",
    "focal_count":
        "cut competing bright areas with comp_pro.depth_push so one thing wins",
    "focal_concentration":
        "concentrate attention with comp_pro.key_light on the subject and "
        "comp_pro.depth_push behind it",
    "text_area_frac":
        "resize the title so its ink covers about {target} of the frame",
    "text_max_height_frac":
        "set the title cap height to about {target} of frame height",
    "text_mean_height_frac":
        "raise the title size toward {target} of frame height",
    "text_contrast":
        "add a stroke or shadow behind the title, or move it onto a darker plate",
    "text_overlaps_face_frac":
        "move the title off the face",
    "balance_lr":
        "re-crop: the visual weight is stacked to one side",
    "thirds_alignment":
        "re-crop so the mass centroid lands on a thirds intersection",
    "tm_flat_g_p90":
        "re-render from the source at higher quality; flat, posterised regions "
        "are present before delivery",
    "tm_subject_max_L":
        "pull the subject exposure down with comp_pro.dodge_burn(amount=-...)",
}


def _rule_n(rule):
    """The sample sizes a grammar rule was ACTUALLY computed on.

    grammar._apply_meaningful decides `meaningful` from n_win_finite /
    n_lose_finite - the counts after non-finite values are dropped - and
    grammar_summary prints those. critique used to quote n_win / n_lose, the
    group sizes BEFORE dropping. On a key that is NaN for half the winners that
    reported "measured on 14 winners" a rule that saw six. The finite counts are
    preferred and the raw ones are only a fallback for an older grammar that
    does not carry them.
    """
    def pick(fin, raw):
        v = rule.get(fin)
        if v is None:
            v = rule.get(raw)
        return v
    return pick("n_win_finite", "n_win"), pick("n_lose_finite", "n_lose")


def _generic_fix(key, direction, target_txt):
    """Last-resort fix line, still imperative and still carrying a number."""
    verb = "raise" if direction == "up" else "lower"
    return "%s %s toward %s" % (verb, _label(key), target_txt)


# -------------------------------------------------------------------- principles
def _p(pid, keys, primary, test, weight, confidence, provenance, headline,
       fix, limits=None, scope="any"):
    """Build one principle record.

    `test` receives the merged row (features + structure extras) and returns
    True when the principle FIRES. It is only called once every key it names is
    finite, so a test never has to guard for NaN itself.
    """
    return {"id": pid, "keys": tuple(keys), "primary": primary, "test": test,
            "severity_weight": float(weight), "confidence": confidence,
            "provenance": provenance, "headline_template": headline,
            "fix": fix, "limits": dict(limits or {}), "scope": scope}


PRINCIPLES = (
    _p("text_illegible_at_grid", ("survive_text_px_210", "text_box_count"),
       "survive_text_px_210",
       lambda r: r["text_box_count"] > 0 and r["survive_text_px_210"] < 10.0,
       0.80, "heuristic", "HEURISTIC — no threshold measured on this machine; "
       "10px is a stated assumption about minimum readable cap height",
       "title text is about {obs} tall once the thumbnail is shown at grid "
       "size; below about {lim} it stops being readable",
       "make the title bigger, or cut words until the remaining ones are large",
       {"lim": ("survive_text_px_210", 10.0)}),

    _p("face_unrecognisable_at_grid", ("survive_face_px_210", "face_count"),
       "survive_face_px_210",
       lambda r: r["face_count"] > 0 and r["survive_face_px_210"] < 20.0,
       0.80, "heuristic", "HEURISTIC — 20px is a stated assumption about the "
       "smallest recognisable face, not something measured here",
       "the face is about {obs} across at grid size; below about {lim} it is "
       "a smudge rather than a person",
       "crop tighter on the face so it survives the grid",
       {"lim": ("survive_face_px_210", 20.0)}),

    _p("no_single_read", ("focal_count", "focal_concentration"),
       "focal_concentration",
       lambda r: r["focal_count"] > 3 and r["focal_concentration"] < 0.35,
       0.60, "heuristic", "HEURISTIC — the 3-region / 0.35 pair is a stated "
       "assumption, unvalidated on this machine",
       "attention is split across {n_focal} competing regions and the strongest "
       "holds only {obs} of it; the eye has nowhere to land",
       "cut competing bright areas with comp_pro.depth_push and put "
       "comp_pro.key_light on the one thing that matters",
       {}),

    _p("flat_tonal_range", ("lum_michelson",), "lum_michelson",
       lambda r: r["lum_michelson"] < 0.25,
       0.55, "heuristic", "HEURISTIC — 0.25 is a stated assumption",
       "brightest-to-darkest contrast is {obs} (Michelson); below about {lim} "
       "the image reads flat",
       "push the tonal range with comp_pro.grade(contrast=...) and "
       "comp_pro.dodge_burn",
       {"lim": ("lum_michelson", 0.25)}),

    _p("text_covers_face", ("text_overlaps_face_frac",),
       "text_overlaps_face_frac",
       lambda r: r["text_overlaps_face_frac"] > 0.10,
       0.70, "heuristic", "STRUCTURAL — the direction needs no measurement; "
       "only the 0.10 tolerance is assumed",
       "the title covers {obs} of the face area; text on a face costs both",
       "move the title off the face",
       {"lim": ("text_overlaps_face_frac", 0.10)}),

    _p("detail_dies_downscaled", ("survive_edge_ret_210",),
       "survive_edge_ret_210",
       lambda r: r["survive_edge_ret_210"] < 0.10,
       0.50, "heuristic", "HEURISTIC — for scale, MONKEY_thumbnail.jpg "
       "measured 0.125; that is one file, not a threshold",
       "only {obs} of the edge detail survives the downscale to grid size",
       "carry the idea in large shapes: fine detail is invisible in the grid",
       {"lim": ("survive_edge_ret_210", 0.10)}),

    _p("subject_blown", ("tm_subject_max_L",), "tm_subject_max_L",
       lambda r: r["tm_subject_max_L"] > GATE_SUBJECT_L,
       0.40, "gate", "GATE — verify_thumb.py Gate C, which that file "
       "explicitly calls a FLAG not a fail because 3 of 12 successful "
       "competitors trip it",
       "the subject's median face lightness is {obs}; above {lim} it is "
       "heading for blown",
       "pull the subject exposure down with comp_pro.dodge_burn",
       {"lim": ("tm_subject_max_L", GATE_SUBJECT_L)}),

    _p("posterised", ("tm_flat_g_p90",), "tm_flat_g_p90",
       lambda r: r["tm_flat_g_p90"] > GATE_FLAT,
       0.70, "gate", "GATE — verify_thumb.py Gate A. PRE-DELIVERY ONLY: 10 of "
       "12 competitor thumbnails trip it purely because YouTube re-encoded them",
       "large flat, posterised regions: flat_g_p90 is {obs} against a {lim} "
       "limit",
       "re-render from the source at higher quality before delivery",
       {"lim": ("tm_flat_g_p90", GATE_FLAT)}, scope="local"),

    _p("duplicate_face", ("dup_inliers",), "dup_inliers",
       lambda r: r["dup_inliers"] >= GATE_DUP,
       1.00, "gate", "GATE — verify_thumb.py Gate D, the only gate that file "
       "declares valid on an arbitrary image from any source",
       "the same face appears twice ({obs} matched inliers between two "
       "detections)",
       "remove or replace one of the duplicated faces",
       {}),

    _p("subject_lost_in_background",
       ("subject_bg_lum_contrast", "bg_blur_ratio"), "subject_bg_lum_contrast",
       lambda r: r["subject_bg_lum_contrast"] < 0.12 and r["bg_blur_ratio"] > 0.8,
       0.70, "heuristic", "HEURISTIC — the 0.12 / 0.8 pair is a stated "
       "assumption",
       "the subject separates from the plate by only {obs} of lightness and "
       "the background is as sharp as the subject",
       "lift separation with comp_pro.rim_light / comp_pro.light_wrap and "
       "push the plate back with comp_pro.depth_push",
       {}),

    _p("crop_unsafe", ("face_edge_margin_min",), "face_edge_margin_min",
       lambda r: r["face_edge_margin_min"] < 0.02,
       0.60, "heuristic", "HEURISTIC — 0.02 of the frame is a stated safe "
       "margin, not a measured one",
       "a face sits {obs} from the frame edge; anything important that close "
       "is read as clipped",
       "pull the crop back so no face touches the frame edge",
       {"lim": ("face_edge_margin_min", 0.02)}),

    _p("dead_frame", ("negative_space_frac", "face_area_frac_total"),
       "negative_space_frac",
       lambda r: r["negative_space_frac"] > 0.55 and r["face_area_frac_total"] < 0.05,
       0.50, "heuristic", "HEURISTIC — the 0.55 / 0.05 pair is a stated "
       "assumption",
       "{obs} of the frame is empty and faces cover under 5% of it",
       "crop in until the subject owns the frame",
       {}),
)

# ------------------------------------------------------------------------------
# EXTRA_PRINCIPLES — the checks the brief names that the frozen FEATURE_KEYS
# vocabulary has no key for. They are evaluated exactly like PRINCIPLES and
# carry the same provenance discipline; they are kept in a separate tuple so
# PRINCIPLES stays the contract's frozen twelve.
EXTRA_PRINCIPLES = (
    _p("contrast_dies_at_grid", ("survive_lum_michelson_210",),
       "survive_lum_michelson_210",
       lambda r: r["survive_lum_michelson_210"] < 0.20,
       0.50, "heuristic", "HEURISTIC — 0.20 is a stated assumption; what is "
       "measured is only that the round trip to 210px changes the number",
       "brightest-against-darkest falls to {obs} once the image is shown at "
       "grid size",
       "build the contrast out of large shapes so it survives the downscale",
       {"lim": ("survive_lum_michelson_210", 0.20)}),

    _p("text_lines_collide", ("text_min_line_gap_px", "text_line_count"),
       "text_min_line_gap_px",
       lambda r: r["text_line_count"] >= 2 and r["text_min_line_gap_px"] <= 0.0,
       0.80, "structural", "STRUCTURAL — measured directly on this image by "
       "structure_probe: two text lines' ink boxes have no vertical gap. The "
       "direction needs no threshold; zero gap is zero gap",
       "two text lines collide - their ink boxes overlap by {obs_abs} with no "
       "gap between them",
       "add leading between the title lines, or shorten one so they stop "
       "touching",
       {}),

    _p("text_lines_cramped", ("text_min_line_gap_px", "text_line_count",
                              "text_mean_line_h_px"), "text_min_line_gap_px",
       lambda r: (r["text_line_count"] >= 2 and r["text_min_line_gap_px"] > 0.0
                  and r["text_min_line_gap_px"]
                  < 0.12 * r["text_mean_line_h_px"]),
       0.40, "heuristic", "HEURISTIC — 12% of line height as a minimum gap is "
       "a stated typographic assumption, not measured here",
       "the tightest gap between two text lines is {obs}, under 12% of the "
       "line height — they merge at grid size",
       "add leading between the title lines",
       {}),

    _p("text_touches_edge", ("text_edge_margin_min",), "text_edge_margin_min",
       lambda r: r["text_edge_margin_min"] < 0.012,
       0.50, "heuristic", "HEURISTIC — 1.2% of the frame as a text safe "
       "margin is a stated assumption",
       "text comes within {obs} of the frame edge and reads as cut off",
       "inset the title to a safe margin on every side",
       {"lim": ("text_edge_margin_min", 0.012)}),

    _p("focal_mass_crosses_edge", ("focal_edge_touch_frac",),
       "focal_edge_touch_frac",
       lambda r: r["focal_edge_touch_frac"] > 0.25,
       0.45, "heuristic", "HEURISTIC — 25% of the dominant salient blob "
       "touching the border is a stated assumption",
       "{obs} of the dominant focal mass runs off the frame edge",
       "re-crop so the thing the eye goes to is whole",
       {"lim": ("focal_edge_touch_frac", 0.25)}),
)


# ------------------------------------------------------------- structure probe
# The saliency blob that focal_edge_touch_frac describes has to be THE SAME blob
# measure.py counted in focal_count / focal_concentration, or a report can say
# "the dominant focal mass runs off the edge" about a region that is not the one
# it just called dominant two lines above. These mirror the literals inside
# measure._focal_stats and are named once so the mirroring is visible; the
# selftest asserts the two agree on a real image.
_FOCAL_PCTL = 88.0
_FOCAL_MIN_CELLS = 3


def _as_rgb_u8(arr):
    """Force any incoming array to contiguous uint8 RGB, or say why it cannot.

    structure_probe is documented as taking "a path or an RGB uint8 array" and
    every caller inside this file honours that, but the failure mode when a
    caller did not was a raw cv2.error out of cvtColor / threshold with the
    channel count in it and nothing about this module - measured on a 2-D
    grayscale frame and on a float32 frame. A grayscale still is a perfectly
    ordinary thing to hand a critic, so it is converted rather than refused, and
    anything genuinely unusable raises a ValueError that names the shape.
    """
    a = np.asarray(arr)
    if a.ndim == 2:
        a = np.dstack([a, a, a])
    elif a.ndim == 3 and a.shape[2] == 1:
        a = np.dstack([a[:, :, 0]] * 3)
    elif a.ndim == 3 and a.shape[2] == 4:
        a = a[:, :, :3]
    if a.ndim != 3 or a.shape[2] != 3 or a.shape[0] < 1 or a.shape[1] < 1:
        raise ValueError("structure_probe needs an HxWx3 RGB image, got shape %r"
                         % (tuple(np.shape(arr)),))
    if a.dtype != np.uint8:
        # A float frame is assumed 0-255 when it exceeds 1.0 and 0-1 otherwise;
        # both conventions are in circulation and guessing wrong would silently
        # black the frame out, so the branch is on the observed range.
        f = a.astype(np.float32)
        top = float(np.nanmax(f)) if f.size else 0.0
        if top <= 1.0:
            f = f * 255.0
        a = np.clip(np.nan_to_num(f), 0, 255).astype(np.uint8)
    return np.ascontiguousarray(a)


def _canon(rgb):
    """Canonical 1280x720, matching thumb_metrics.CANON_W/CANON_H exactly."""
    return cv2.resize(_as_rgb_u8(rgb), (measure.CANON_W, measure.CANON_H),
                      interpolation=cv2.INTER_AREA)


def _face_box_mask(shape, faces):
    """Padded face rectangles, as a 0/1 mask on the canonical frame.

    Text detection is masked against this because EVERY false positive in the
    first version of this probe was a facial feature - eyebrows, an eye, a lip
    line. They are dark, uniform in colour and horizontally elongated, which is
    exactly what a line of type looks like to any ink detector. Excluding faces
    removed all of them across the twelve READY-TO-POST thumbnails, verified by
    drawing the surviving boxes back onto the images and looking at them.

    The cost is stated rather than hidden: text laid ON a face is invisible to
    this probe. That case is already covered by the text_covers_face principle,
    which uses measure.py's text_overlaps_face_frac.
    """
    H, W = shape[:2]
    m = np.zeros((H, W), np.uint8)
    for f in faces or []:
        bw, bh = f["bw"], f["bh"]
        cx, cy = f["cx"] * W, f["cy"] * H
        x0 = int(max(0, cx - bw * 0.62)); x1 = int(min(W, cx + bw * 0.62))
        y0 = int(max(0, cy - bh * 0.62)); y1 = int(min(H, cy + bh * 0.62))
        if x1 > x0 and y1 > y0:
            m[y0:y1, x0:x1] = 1
    return m


def _ink_components(gray, face_mask=None):
    """High-contrast ink blobs - words and glyphs - on the canonical grey frame.

    NOT cv2.MSER, which the contract suggested. MSER returns 218 regions on
    MONKEY_thumbnail.jpg but ZERO regions on every synthetic test image built
    here (flat ground, gradient ground, with and without noise, before and
    after a JPEG round trip; cv2 5.0.0). A detector that cannot be run against
    a known answer cannot be trusted to raise a defect, so it was replaced by a
    morphological top-hat / black-hat response, which does reproduce a known
    answer: on synthetic two-line titles it recovers the true line gap EXACTLY
    at true gaps of 137, 107, 77, 47, 27 and 17 canonical px. (It used to be
    quoted as "within 2px". The 2px was the selftest's hardcoded 61px cap
    height being wrong by 2, not the probe being wrong by 2; deriving the cap
    height from the glyphs took the error to zero.)

    Top-hat catches bright ink on a darker ground and black-hat the reverse, so
    a white title and a black one are both found. The 15px kernel is smaller
    than any thumbnail title stroke, which is what keeps the response on the
    type instead of on the scenery behind it.
    """
    H, W = gray.shape[:2]
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    resp = np.maximum(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k),
                      cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k))
    t, _ = cv2.threshold(resp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu, floored and capped: on a title-heavy frame the raw Otsu level runs
    # up to 254 and the mask empties out; on a flat frame it drops near zero and
    # the mask fills with noise. Both were observed while deriving this.
    t = max(30, min(140, int(t)))
    m = ((resp >= t).astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = [int(st[i, c]) for c in (
            cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH,
            cv2.CC_STAT_HEIGHT, cv2.CC_STAT_AREA)]
        if a < 40 or h < 6 or w < 3:
            continue
        if not (0.08 <= w / float(h) <= 12.0):
            continue                       # a word or a glyph, never a bar
        if not (0.03 <= h / float(H) <= 0.28):
            continue
        if w / float(W) > 0.45:
            continue
        fill = a / float(w * h)
        if not (0.12 <= fill <= 0.95):
            continue
        if face_mask is not None:
            sub = face_mask[y:y + h, x:x + w]
            if sub.size and float(sub.mean()) > 0.35:
                continue
        comps.append({"x": x, "y": y, "w": w, "h": h, "i": i})
    return comps, lab


def _text_lines(comps, lab, rgb):
    """Group ink blobs into text LINES, keeping only groups that look like type.

    Four conditions, and each one was added because dropping it let scenery
    through on a real thumbnail:
      * at least 2 blobs, uniform in height (std/mean <= 0.35) - type is one size
      * the line is at least 3x wider than it is tall - a line of words is long
      * the blobs span at least 55% of the line's height - one tall blob is a
        person or a doorframe, not a line of text
      * the ink is a flat fill (mean Lab std <= 14 over the polarity-consistent
        ink pixels) - a title is one colour, scenery is not

    The ink pixels are chosen by polarity because the raw component carries the
    halo the black-hat response leaves around bright type; sampling the whole
    component measured a colour spread of 25-30 on pure white text and made the
    flat-fill test useless.
    """
    if not comps:
        return []
    cs = sorted(comps, key=lambda c: (c["y"], c["x"]))
    groups = []
    for c in cs:
        placed = False
        for gp in groups:
            oy = min(c["y"] + c["h"], gp["y1"]) - max(c["y"], gp["y0"])
            if oy <= 0 or oy < 0.6 * min(c["h"], gp["y1"] - gp["y0"]):
                continue
            lh = max(c["h"], gp["y1"] - gp["y0"])
            if abs(c["h"] - gp["mh"]) > 0.45 * gp["mh"]:
                continue
            gx = max(gp["x0"] - (c["x"] + c["w"]), c["x"] - gp["x1"])
            if gx > 1.6 * lh:
                continue
            gp["x0"] = min(gp["x0"], c["x"])
            gp["x1"] = max(gp["x1"], c["x"] + c["w"])
            gp["y0"] = min(gp["y0"], c["y"])
            gp["y1"] = max(gp["y1"], c["y"] + c["h"])
            gp["cs"].append(c)
            gp["mh"] = float(np.median([q["h"] for q in gp["cs"]]))
            placed = True
            break
        if not placed:
            groups.append({"x0": c["x"], "x1": c["x"] + c["w"], "y0": c["y"],
                           "y1": c["y"] + c["h"], "cs": [c],
                           "mh": float(c["h"])})

    # THE GREEDY PASS ABOVE IS ORDER-DEPENDENT, so it is run to a fixed point.
    # Measured on the selftest's own title: components sort by (y, x), and a
    # one-pixel difference in ink-box top between two words of the SAME line
    # interleaves them - GUILTY(y=238) ON(y=239) ALL(y=238) - so "ON" was tested
    # against a group that had not yet absorbed the word sitting between them,
    # measured a 139px gap against a 101px limit, and started a second group.
    # "GUILTY ON ALL" was reported as two lines and text_line_count came back 3
    # for a two-line title. Merging pairs until nothing more merges removes the
    # dependence on arrival order; the predicates are the ones above, unchanged.
    def _mergeable(a, b):
        oy = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
        ha, hb = a["y1"] - a["y0"], b["y1"] - b["y0"]
        if oy <= 0 or oy < 0.6 * min(ha, hb):
            return False
        if abs(a["mh"] - b["mh"]) > 0.45 * max(a["mh"], b["mh"]):
            return False
        gx = max(a["x0"] - b["x1"], b["x0"] - a["x1"])
        return gx <= 1.6 * max(ha, hb)

    changed = True
    while changed and len(groups) > 1:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                if not _mergeable(a, b):
                    continue
                a["x0"] = min(a["x0"], b["x0"]); a["x1"] = max(a["x1"], b["x1"])
                a["y0"] = min(a["y0"], b["y0"]); a["y1"] = max(a["y1"], b["y1"])
                a["cs"].extend(b["cs"])
                a["mh"] = float(np.median([q["h"] for q in a["cs"]]))
                groups.pop(j)
                changed = True
                break
            if changed:
                break

    lab_img = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    L0 = lab_img[:, :, 0]
    keep = []
    for gp in groups:
        n = len(gp["cs"])
        lw = gp["x1"] - gp["x0"]
        lh = gp["y1"] - gp["y0"]
        if n < 2 or lh <= 0 or lw < 3.0 * lh:
            continue
        hs = [c["h"] for c in gp["cs"]]
        mh = float(np.mean(hs))
        if mh <= 0 or float(np.std(hs)) / mh > 0.35 or mh < 0.55 * lh:
            continue
        mask = np.zeros(lab.shape, np.uint8)
        for c in gp["cs"]:
            mask[lab == c["i"]] = 1
        mb = mask.astype(bool)
        if int(mb.sum()) < 80:
            continue
        ring = cv2.dilate(mask, np.ones((9, 9), np.uint8)).astype(bool) & (~mb)
        if int(ring.sum()) < 50:
            continue
        Lc = L0[mb].astype(np.float32)
        ringL = float(np.median(L0[ring].astype(np.float32)))
        if float(np.median(Lc)) >= ringL:
            sel = Lc >= np.percentile(Lc, 60)
        else:
            sel = Lc <= np.percentile(Lc, 40)
        px = lab_img[mb][sel]
        if px.shape[0] < 50:
            continue
        if float(np.mean(np.std(px.astype(np.float32), axis=0))) > 14.0:
            continue
        gp["n"] = n
        keep.append(gp)
    keep.sort(key=lambda g: g["y0"])
    return keep


def _saliency(rgb_or_gray):
    """Spectral-residual saliency on a 64x36 frame.

    DELEGATES to measure._saliency_map when it is importable, because "the same
    construction measure.py uses" has to be literally the same code. The two
    copies had already drifted - this one used an epsilon of 1e-8 against
    measure's 1e-9 and guarded `rng <= 0` against measure's `rng < _EPS` - so a
    frame near either boundary could put a different blob in this report's
    focal_edge_touch_frac than in the same report's focal_count. The local body
    below is kept only as a fallback for the case measure's helper is renamed.
    """
    arr = np.asarray(rgb_or_gray)
    fn = getattr(measure, "_saliency_map", None)
    if fn is not None:
        try:
            return fn(_as_rgb_u8(arr))
        except Exception:
            pass                      # fall through to the local copy
    gray = arr if arr.ndim == 2 else cv2.cvtColor(_as_rgb_u8(arr),
                                                  cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
    f = np.fft.fft2(small)
    amp = np.abs(f)
    logamp = np.log(amp + 1e-8)
    phase = np.angle(f)
    smooth = cv2.blur(logamp, (3, 3))
    residual = logamp - smooth
    recon = np.fft.ifft2(np.exp(residual + 1j * phase))
    sal = np.abs(recon) ** 2
    sal = cv2.GaussianBlur(sal, (0, 0), 2.0)
    rng = float(np.ptp(sal))          # numpy 2.5 removed ndarray.ptp()
    if rng <= 0:
        return np.zeros_like(sal)
    return (sal - float(sal.min())) / rng


def structure_probe(image, faces=None):
    """Geometry the frozen FEATURE_KEYS cannot express, measured on the image.

    Returns a plain dict of extras - never keys, never anything that touches a
    feature row:
        text_line_count          text lines found, face regions excluded
        text_min_line_gap_px     smallest vertical gap between two stacked,
                                 horizontally overlapping lines, in canonical
                                 px; <= 0 means their ink boxes collide
        text_mean_line_h_px      mean line height, the scale that gap is judged against
        text_edge_margin_min     nearest text edge to the frame border, as a
                                 fraction of the shorter frame side
        focal_edge_touch_frac    share of the dominant saliency blob sitting on
                                 the border, i.e. how much of it runs off frame
        dup_inliers              verify_thumb Gate D, the same-person-twice check
        face_count_probe         faces found on the canonical frame

    VALIDATED, WITH ITS BLIND SPOT STATED. On synthetic two-line titles the gap
    is recovered EXACTLY at true gaps of 137, 107, 77, 47, 27 and 17px, and
    text_line_count reports 2 at every one of them and 1 for a one-line title.
    At a true gap of 12px the two lines' ink merges into one connected band and
    the probe reports ONE line instead of a collision - so a total overlap is a
    false NEGATIVE, never a false positive. This probe under-reports rather than
    inventing defects, which is the safe direction for something whose whole
    job is to generate criticism.

    `image` is a path or an RGB uint8 array; everything is measured on the
    canonical 1280x720 frame so the pixel numbers mean the same thing here as
    everywhere else in the engine.
    """
    if isinstance(image, str):
        rgb, _meta = measure.load_rgb(image)
        rgb, _lb = measure.deletterbox(rgb)
    else:
        # An array arrives already de-letterboxed by convention; only the path
        # branch can know it came off disk with bars on it.
        rgb = _as_rgb_u8(image)
    canon = _canon(rgb)
    H, W = canon.shape[:2]
    gray = cv2.cvtColor(canon, cv2.COLOR_RGB2GRAY)

    if faces is None:
        faces = thumb_metrics.detect_faces(canon, YUNET)
    fm = _face_box_mask(canon.shape, faces)
    comps, lab = _ink_components(gray, fm)
    lines = _text_lines(comps, lab, canon)

    extras = {
        "text_line_count": float(len(lines)),
        "text_min_line_gap_px": float("nan"),
        "text_mean_line_h_px": float("nan"),
        "text_edge_margin_min": float("nan"),
        "focal_edge_touch_frac": float("nan"),
        "dup_inliers": float("nan"),
        "face_count_probe": float(len(faces)),
    }

    if lines:
        extras["text_mean_line_h_px"] = float(
            np.mean([ln["y1"] - ln["y0"] for ln in lines]))
        m = min(min(ln["x0"], ln["y0"], W - ln["x1"], H - ln["y1"])
                for ln in lines)
        extras["text_edge_margin_min"] = float(m) / float(min(W, H))
    if len(lines) >= 2:
        gaps = []
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                a, b = lines[i], lines[j]
                ox = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                # Only stacked lines can collide. Two lines side by side in the
                # same row are not a defect, they are a row.
                if ox <= 0.10 * min(a["x1"] - a["x0"], b["x1"] - b["x0"]):
                    continue
                gaps.append(float(b["y0"] - a["y1"]))
        if gaps:
            extras["text_min_line_gap_px"] = float(min(gaps))

    sal = _saliency(canon)
    if sal.size:
        thr = float(np.percentile(sal, _FOCAL_PCTL))
        mask = (sal > thr).astype(np.uint8)
        n, slab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        best, best_area = 0, 0
        for i in range(1, n):
            a = int(stats[i, cv2.CC_STAT_AREA])
            if a >= _FOCAL_MIN_CELLS and a > best_area:
                best, best_area = i, a
        if best:
            blob = (slab == best)
            border = np.zeros_like(blob)
            border[0, :] = True
            border[-1, :] = True
            border[:, 0] = True
            border[:, -1] = True
            extras["focal_edge_touch_frac"] = float(
                (blob & border).sum()) / float(best_area)
        else:
            extras["focal_edge_touch_frac"] = 0.0

    try:
        extras["dup_inliers"] = float(verify_thumb._dup_inliers(canon, faces))
    except Exception:
        extras["dup_inliers"] = float("nan")
    return extras


# --------------------------------------------------------------- grammar path
def defects_from_grammar(feature_row, grammar, min_weight=0.0):
    """Defects raised by rules the grammar itself calls meaningful.

    A rule with meaningful=False produces NOTHING here no matter how far the
    candidate sits from the winners — the grammar has already said that
    difference is not distinguishable from noise, and shouting about it would
    turn a multiple-comparisons artefact into advice.
    """
    out, skipped = [], []
    if not grammar:
        return out, skipped
    rules = grammar.get("rules") or {}
    for key, rule in rules.items():
        if not rule.get("meaningful"):
            continue
        w = float(rule.get("weight") or 0.0)
        if w <= min_weight:
            continue
        obs = feature_row.get(key, None)
        if not _isnum(obs):
            skipped.append("%s: candidate value is not finite, rule skipped" % key)
            continue
        lo = rule.get("target_lo")
        hi = rule.get("target_hi")
        if not (_isnum(lo) and _isnum(hi)):
            skipped.append("%s: rule has no usable target band" % key)
            continue
        lo, hi, obs = float(lo), float(hi), float(obs)
        if lo > hi:
            lo, hi = hi, lo
        outside = max(0.0, lo - obs, obs - hi)
        if outside <= 0.0:
            continue
        denom = hi - lo
        if denom <= 0:
            denom = float(rule.get("win_std") or 0.0)
        if denom <= 0:
            skipped.append("%s: winners' spread is zero, deviation cannot be "
                           "scaled, rule skipped" % key)
            continue
        dev = min(DEV_CAP, outside / denom)
        # Clamped because severity is promised as 0-100 everywhere downstream
        # (severity_5's fixed edges, the render bar, the score's /200 penalty).
        # grammar.py sets weight = |Cliff's delta| <= 1 today, so this changes
        # nothing now; it stops a future weight scheme from quietly emitting
        # "sev 130/100".
        sev = int(round(SEVERITY_MAX * w * dev / DEV_CAP))
        sev = max(0, min(SEVERITY_MAX, sev))
        if sev < 1:
            continue
        d = _doc(key)
        unit = d.get("unit", "unitless")
        centre = rule.get("target_center", (lo + hi) / 2.0)
        head = ("%s is %s; winners in this niche sit at %s-%s (median %s)"
                % (_label(key), fmt_value(obs, unit), fmt_value(lo, unit),
                   fmt_value(hi, unit), fmt_value(centre, unit)))
        direction = "up" if obs < lo else "down"
        target_txt = fmt_value(centre, unit)
        fix = FIX_BY_KEY.get(key)
        fix = (fix.format(target=target_txt) if fix
               else _generic_fix(key, direction, target_txt))
        n_win, n_lose = _rule_n(rule)
        detail = ("%s outside the winners' interquartile band, %.2f band-widths "
                  "out. Measured on %s winners vs %s losers (values that were "
                  "finite for this key), Cliff's delta %+.2f."
                  % (fmt_value(outside, unit), outside / denom,
                     n_win, n_lose, float(rule.get("delta") or 0.0)))
        out.append({
            "id": "grammar:" + key, "key": key,
            "family": d.get("family", ""),
            "category": _category_for(key, d.get("family", "")),
            "severity": sev, "severity_5": severity_5(sev),
            "source": "grammar", "confidence": "measured",
            "headline": head, "detail": detail,
            "observed": obs, "unit": unit,
            "target_lo": lo, "target_hi": hi, "target_center": centre,
            "n_win": n_win, "n_lose": n_lose,
            "effect": rule.get("delta"), "fix": fix,
        })
    return out, skipped


# ------------------------------------------------------------- principle path
def defects_from_principles(feature_row, source_kind="local", grammar=None,
                            extras=None):
    """Evaluate PRINCIPLES + EXTRA_PRINCIPLES against the candidate.

    Three suppressions, each load-bearing:
      * a principle whose keys are missing or NaN is SKIPPED and said to be
        skipped, never defaulted to passing;
      * a scope='local' principle on a non-local source becomes a zero-severity
        diagnostic, because verify_thumb measured that YouTube's own re-encode
        trips it;
      * a principle whose key already has a MEANINGFUL grammar rule is
        suppressed — measured beats assumed, and reporting both double-counts
        one defect into a louder severity than it earned.
    """
    row = dict(feature_row)
    if extras:
        row.update(extras)
    grules = (grammar or {}).get("rules") or {}
    defects, diagnostics, skipped = [], [], []

    for pr in PRINCIPLES + EXTRA_PRINCIPLES:
        missing = [k for k in pr["keys"] if not _isnum(row.get(k, None))]
        if missing:
            skipped.append("%s: skipped, no finite value for %s"
                           % (pr["id"], ", ".join(missing)))
            continue
        covered = [k for k in pr["keys"]
                   if (grules.get(k) or {}).get("meaningful")]
        if covered:
            skipped.append("%s: suppressed, the niche grammar has a measured "
                           "rule for %s" % (pr["id"], ", ".join(covered)))
            continue
        try:
            fired = bool(pr["test"](row))
        except Exception as exc:                  # a bad test must not kill the report
            skipped.append("%s: test raised %s" % (pr["id"], exc))
            continue
        if not fired:
            continue

        pk = pr["primary"]
        obs = float(row[pk])
        d = _doc(pk)
        unit = d.get("unit", "unitless")
        lim_key, lim_val = pr["limits"].get("lim", (None, None))
        subs = {
            "obs": fmt_value(obs, unit),
            "obs_abs": fmt_value(abs(obs), unit),
            "lim": fmt_value(lim_val, unit) if lim_val is not None else "the limit",
            # focal_count can be NaN on a row that came from a failed measure;
            # "%.0f" would print the word nan into a headline as if it were a
            # count of regions.
            "n_focal": ("%.0f" % float(row["focal_count"])
                        if _isnum(row.get("focal_count")) else "an unknown "
                        "number of"),
        }
        head = pr["headline_template"].format(**subs)

        pre_delivery_muted = (pr["scope"] == "local" and source_kind != "local")
        sev = 0 if pre_delivery_muted else int(round(
            SEVERITY_MAX * pr["severity_weight"]))
        rec = {
            "id": pr["id"], "key": pk, "family": d.get("family", ""),
            "category": _category_for(pk, d.get("family", "")),
            "severity": sev, "severity_5": severity_5(sev),
            "source": "gate" if pr["confidence"] == "gate" else "principle",
            "confidence": pr["confidence"],
            "headline": head,
            "detail": pr["provenance"] + (
                ". Source is '%s', so this pre-delivery gate is reported as a "
                "diagnostic only and contributes no severity." % source_kind
                if pre_delivery_muted else ""),
            "observed": obs, "unit": unit,
            "target_lo": None, "target_hi": lim_val,
            "target_center": lim_val,
            "n_win": None, "n_lose": None, "effect": None,
            "fix": pr["fix"],
        }
        (diagnostics if pre_delivery_muted else defects).append(rec)

    return defects, diagnostics, skipped


# --------------------------------------------------------------------- coverage
def coverage(feature_row, grammar=None, extras=None):
    """How many of this module's checks the candidate could actually be judged by.

    THE BUG THIS EXISTS TO KILL. Every check in here skips itself when its key
    is missing or NaN, and says so - which is right. But the SCORE was then
    computed as 100 * prod(1 - sev/200) over an empty defect list, so a feature
    row where nothing at all was measurable came back 100.0 / "ship". Measured:
    critique({}) and critique(a row of NaNs, which is exactly what
    measure.measure_file returns for a corrupt JPEG) both returned score 100.0,
    verdict "ship", zero defects. A perfect score for an image nobody looked at
    is the single most damaging number this module could print.

    So coverage is counted and travels with the score. checks_run == 0 means the
    score is not a score, and score_candidate refuses to invent one.

    A principle suppressed by a meaningful grammar rule counts as RUN, not
    skipped - the property was judged, just by the measured rule instead.
    """
    row = dict(feature_row)
    if extras:
        row.update(extras)
    grules = (grammar or {}).get("rules") or {}

    g_possible = g_run = 0
    for key, rule in grules.items():
        if not rule.get("meaningful"):
            continue
        g_possible += 1
        if (_isnum(row.get(key)) and _isnum(rule.get("target_lo"))
                and _isnum(rule.get("target_hi"))):
            g_run += 1

    p_possible = p_run = 0
    for pr in PRINCIPLES + EXTRA_PRINCIPLES:
        p_possible += 1
        if any((grules.get(k) or {}).get("meaningful") for k in pr["keys"]):
            p_run += 1                       # judged by the measured rule instead
        elif all(_isnum(row.get(k)) for k in pr["keys"]):
            p_run += 1
    return {
        "checks_run": g_run + p_run,
        "checks_possible": g_possible + p_possible,
        "grammar_rules_run": g_run, "grammar_rules_possible": g_possible,
        "principles_run": p_run, "principles_possible": p_possible,
    }


# ---------------------------------------------------------------------- scoring
def score_candidate(feature_row, grammar=None, styles=None, source_kind="local",
                    extras=None):
    """Combine grammar defects, principle defects and style placement.

    overall_score = 100 * prod(1 - severity/200): many mild defects accumulate,
    but no single defect can zero the score. That shape is a CHOSEN convention —
    nothing on this machine measures how a viewer trades one bad property
    against another.
    """
    notes = []
    g_defects, g_skipped = defects_from_grammar(feature_row, grammar)
    p_defects, p_diag, p_skipped = defects_from_principles(
        feature_row, source_kind=source_kind, grammar=grammar, extras=extras)
    notes.extend(g_skipped)
    notes.extend(p_skipped)

    defects = g_defects + p_defects
    _order = {"grammar": 0, "gate": 1, "principle": 2}
    defects.sort(key=lambda d: (-d["severity"], _order.get(d["source"], 3),
                                d["id"]))
    for i, d in enumerate(defects, 1):
        d["rank"] = i

    cov = coverage(feature_row, grammar=grammar, extras=extras)
    penalty = 1.0
    for d in defects:
        penalty *= (1.0 - min(SEVERITY_MAX, d["severity"]) / 200.0)
    if cov["checks_run"] <= 0:
        # No check could be evaluated at all. 100.0 would be a lie; None is the
        # true answer and every consumer of this dict now has to notice.
        overall, verdict = None, "insufficient-data"
        notes.append("NOT SCORED: none of the %d checks could be evaluated - "
                     "every key they need is missing or not finite. This is not "
                     "a clean thumbnail, it is an unmeasured one."
                     % cov["checks_possible"])
    else:
        overall = round(100.0 * penalty, 1)
        verdict = ("ship" if overall >= VERDICT_SHIP
                   else "fix" if overall >= VERDICT_FIX else "rebuild")
        if cov["checks_run"] * 2 < cov["checks_possible"]:
            notes.append("LOW COVERAGE: only %d of %d checks could be evaluated, "
                         "so the score is built on under half the evidence it "
                         "normally uses"
                         % (cov["checks_run"], cov["checks_possible"]))

    # strengths: the meaningful rules the candidate already satisfies, so the
    # reader knows what not to break while fixing the rest.
    strengths, n_meaningful, n_inside = [], 0, 0
    for key, rule in ((grammar or {}).get("rules") or {}).items():
        if not rule.get("meaningful"):
            continue
        obs = feature_row.get(key)
        lo, hi = rule.get("target_lo"), rule.get("target_hi")
        if not (_isnum(obs) and _isnum(lo) and _isnum(hi)):
            continue
        n_meaningful += 1
        lo, hi = float(min(lo, hi)), float(max(lo, hi))
        if lo <= float(obs) <= hi:
            n_inside += 1
            unit = _doc(key).get("unit", "unitless")
            strengths.append({
                "key": key, "observed": float(obs), "unit": unit,
                "target_lo": lo, "target_hi": hi,
                "text": "%s is %s, inside the winners' %s-%s"
                        % (_label(key), fmt_value(obs, unit),
                           fmt_value(lo, unit), fmt_value(hi, unit)),
                "n_win": _rule_n(rule)[0], "n_lose": _rule_n(rule)[1],
                "effect": rule.get("delta"),
            })
    strengths.sort(key=lambda s: -abs(float(s.get("effect") or 0.0)))
    # Reported WITH its denominator. On its own, "grammar_fit=1.0" reads like a
    # strong result whether it came from 1 meaningful rule or 40, and three
    # decimal places on a ratio of small integers claims a precision the count
    # does not have - so the rounding follows the denominator.
    grammar_fit = (round(n_inside / float(n_meaningful),
                         1 if n_meaningful < 10 else 2)
                   if n_meaningful else None)
    if not grammar:
        notes.append("no niche grammar; general principles only")
    elif n_meaningful == 0:
        notes.append("the niche grammar found no meaningful rule, so nothing "
                     "here is measured against this niche - principles only")

    nearest = None
    if styles is not None:
        st = _optional("styles")
        if st is None:
            notes.append("styles.py is not importable; style placement skipped")
        else:
            try:
                a = st.assign(styles, feature_row)
                cid = a.get("cluster_id")
                cl = next((c for c in styles.get("clusters", [])
                           if c.get("cluster_id") == cid), {})
                nearest = {
                    "cluster_id": cid, "label": cl.get("label"),
                    "distance": a.get("distance"),
                    "is_outlier_far": bool(a.get("is_outlier_far")),
                    "outlier_lift": cl.get("outlier_lift"),
                }
                if nearest["is_outlier_far"]:
                    notes.append("the candidate matches no discovered style in "
                                 "this niche; the nearest cluster is reported "
                                 "for reference only")
            except Exception as exc:
                notes.append("style placement failed: %s" % exc)

    diagnostics = list(p_diag)
    return {
        "overall_score": overall, "verdict": verdict,
        "grammar_fit": grammar_fit,
        "grammar_fit_n": n_meaningful or None,
        "grammar_fit_inside": n_inside if n_meaningful else None,
        "coverage": cov,
        "nearest_style": nearest,
        "style_lift": (nearest or {}).get("outlier_lift"),
        "defects": defects, "strengths": strengths,
        "diagnostics": diagnostics, "notes": notes,
    }


# ------------------------------------------------------------------- entry point
def critique(candidate, niche=None, grammar=None, styles=None,
             source_kind="local", top_n=None, out_json=None, probe=True):
    """Critique one candidate: a file path, or an already-measured row.

    Runs happily with grammar=None — principles only, labelled as such in
    notes — so the module is useful before any harvest has been done.
    """
    notes = []
    extras = None
    if isinstance(candidate, str):
        row = measure.measure_file(candidate, source_kind=source_kind)
        if row.get("measure_error"):
            raise RuntimeError("could not measure %s: %s"
                               % (candidate, row["measure_error"]))
        if probe:
            try:
                extras = structure_probe(candidate)
            except Exception as exc:
                notes.append("structure_probe failed (%s); the edge, text "
                             "collision and focal-clipping checks were not run"
                             % exc)
    else:
        row = dict(candidate)
        notes.append("measured row supplied directly; structure_probe needs the "
                     "image, so the text-collision, text-edge and focal-edge "
                     "checks were not run")

    if grammar is None and niche:
        gm = _optional("grammar")
        if gm is None:
            notes.append("grammar.py is not importable; running principles only")
        else:
            try:
                grammar = gm.load_grammar(niche)
            except Exception as exc:
                notes.append("no grammar for niche %r (%s); principles only"
                             % (niche, exc))
    if styles is None and niche:
        st = _optional("styles")
        if st is not None:
            try:
                styles = st.load_styles(niche)
            except Exception:
                styles = None

    res = score_candidate(row, grammar=grammar, styles=styles,
                          source_kind=source_kind, extras=extras)
    defects = res["defects"]
    if top_n:
        defects = defects[:int(top_n)]

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": utc_now(),
        "candidate": {
            "image_id": row.get("image_id"),
            "image_path": row.get("image_path"),
            "image_sha1": row.get("image_sha1"),
            "source_kind": row.get("source_kind", source_kind),
            "width": row.get("src_width_px"),
            "height": row.get("src_height_px"),
        },
        "niche": niche,
        "grammar_confidence": (grammar or {}).get("confidence"),
        "grammar_n_win": ((grammar or {}).get("groups") or {}).get("n_win"),
        "grammar_n_lose": ((grammar or {}).get("groups") or {}).get("n_lose"),
        "overall_score": res["overall_score"],
        "verdict": res["verdict"],
        "grammar_fit": res["grammar_fit"],
        "grammar_fit_n": res.get("grammar_fit_n"),
        "grammar_fit_inside": res.get("grammar_fit_inside"),
        "coverage": res.get("coverage"),
        "nearest_style": res["nearest_style"],
        "defects": defects,
        "strengths": res["strengths"],
        "diagnostics": res["diagnostics"],
        "structure": extras or {},
        "notes": notes + res["notes"],
        "measurements": {k: row.get(k) for k in measure.FEATURE_KEYS},
    }
    if out_json:
        save_report(report, out_json)
    elif niche:
        try:
            d = niche_dir(niche, create=True)
            stem = _safe_stem(row.get("image_id"))
            save_report(report, d + "/critique/" + stem + ".json")
        except Exception as exc:
            report["notes"].append("could not save report: %s" % exc)
    return report


def _safe_stem(image_id):
    """A filename Windows will actually accept, from an arbitrary image_id.

    image_id is a filename stem for a measured file, but critique also takes a
    pre-measured row whose image_id came from somewhere else entirely - a
    YouTube video id, a hand-written dict. A path separator in it silently
    creates a directory under critique/, and a colon or a wildcard throws
    OSError deep inside write_json from a path the caller never typed.
    """
    stem = str(image_id or "candidate")
    for ch in tuple(chr(92) + '/:*?"<>|') + (chr(13), chr(10), chr(9)):
        stem = stem.replace(ch, "_")
    stem = stem.strip(" .")                  # Windows drops both from the tail
    return stem[:120] or "candidate"


# ---------------------------------------------------------------------- render
_BAR = "#"


def render_report(report, width=100, top_n=None):
    """Plain-text block for the terminal, so the module shows its own state."""
    L = []
    c = report.get("candidate", {})
    L.append("=" * width)
    sc = report.get("overall_score")
    L.append("%s   %s   score %s"
             % (str(c.get("image_id") or "?"),
                str(report.get("verdict", "?")).upper(),
                ("%.1f/100" % float(sc)) if _isnum(sc) else "NOT SCORED"))
    cov = report.get("coverage") or {}
    if cov:
        L.append("coverage: %s of %s checks evaluated (%s grammar rules, "
                 "%s principles)"
                 % (cov.get("checks_run"), cov.get("checks_possible"),
                    cov.get("grammar_rules_run"), cov.get("principles_run")))
    conf = report.get("grammar_confidence")
    if conf:
        fit_n = report.get("grammar_fit_n")
        fit_txt = ("grammar_fit=%s (%s of %s meaningful rules satisfied)"
                   % (report.get("grammar_fit"),
                      report.get("grammar_fit_inside"), fit_n)
                   if fit_n else "no meaningful rule, so nothing to fit")
        L.append("grammar: niche=%s  confidence=%s  winners=%s losers=%s   %s"
                 % (report.get("niche"), conf, report.get("grammar_n_win"),
                    report.get("grammar_n_lose"), fit_txt))
    else:
        L.append("grammar: NONE - general design principles only, nothing below "
                 "is measured against a niche")
    if not any(d.get("source") == "grammar" for d in report.get("defects", [])):
        L.append("!! no MEASURED rule contributed: every defect below is a "
                 "heuristic or an inherited gate, so the score and the verdict "
                 "are opinions with numbers attached, not findings")
    ns = report.get("nearest_style")
    if ns:
        L.append("nearest style: #%s %s  distance %.2f%s"
                 % (ns.get("cluster_id"), ns.get("label"),
                    float(ns.get("distance") or 0.0),
                    "  (candidate matches NO discovered style)"
                    if ns.get("is_outlier_far") else ""))
    L.append("-" * width)

    defects = report.get("defects", [])
    if top_n:
        defects = defects[:int(top_n)]
    if not defects:
        L.append("no defects raised.")
    for d in defects:
        sev = int(d.get("severity") or 0)
        bar = _BAR * max(1, int(round(sev / 10.0)))
        if d.get("source") == "grammar":
            tag = "[measured n=%s/%s, delta %+.2f]" % (
                d.get("n_win"), d.get("n_lose"), float(d.get("effect") or 0.0))
        elif d.get("confidence") == "gate":
            tag = "[gate, verify_thumb thresholds]"
        elif d.get("confidence") == "structural":
            tag = "[structural, measured on this image]"
        else:
            tag = "[heuristic, unvalidated]"
        L.append("%2d. sev %3d/100 (%d/5) %-12s %s"
                 % (d.get("rank", 0), sev, d.get("severity_5", 1), bar,
                    d.get("category", "")))
        L.append("    %s" % d.get("headline", ""))
        if d.get("target_lo") is not None and d.get("target_hi") is not None:
            L.append("    observed %s   winners %s-%s   %s"
                     % (fmt_value(d.get("observed"), d.get("unit")),
                        fmt_value(d.get("target_lo"), d.get("unit")),
                        fmt_value(d.get("target_hi"), d.get("unit")), tag))
        else:
            L.append("    observed %s   limit %s   %s"
                     % (fmt_value(d.get("observed"), d.get("unit")),
                        fmt_value(d.get("target_hi"), d.get("unit")), tag))
        L.append("    FIX: %s" % d.get("fix", ""))
        L.append("")

    st = report.get("strengths", [])
    if st:
        L.append("STRENGTHS (do not break these while fixing the above)")
        for s in st[:8]:
            L.append("  + %s" % s.get("text"))
        L.append("")

    dg = report.get("diagnostics", [])
    if dg:
        L.append("DIAGNOSTICS (reported, no severity)")
        for d in dg:
            L.append("  . %s" % d.get("headline"))
        L.append("")

    stru = report.get("structure") or {}
    if stru:
        L.append("STRUCTURE PROBE  lines=%s  min line gap=%s px  "
                 "text edge margin=%s  focal on border=%s  dup inliers=%s"
                 % (_n(stru.get("text_line_count")),
                    _n(stru.get("text_min_line_gap_px")),
                    _n(stru.get("text_edge_margin_min"), 3),
                    _n(stru.get("focal_edge_touch_frac"), 3),
                    _n(stru.get("dup_inliers"))))

    notes = report.get("notes", [])
    interesting = [n for n in notes if "suppressed" not in n]
    if interesting:
        L.append("NOTES")
        for n in interesting[:12]:
            L.append("  - %s" % n)
    L.append("=" * width)
    return "\n".join(L)


def _n(v, nd=1):
    """Format a possibly-NaN number for the one-line probe summary."""
    if not _isnum(v):
        return "n/a"
    return ("%." + str(nd) + "f") % float(v)


# --------------------------------------------------------------------- compare
def compare(candidates, grammar=None, styles=None, source_kind="local",
            niche=None):
    """Score several candidates against one grammar and rank them.

    The A/B path: READY-TO-POST already holds _V2 and _FINAL variants of the
    same thumbnail, and "which of these two do I post" is the commonest real
    question this engine gets asked.
    """
    reports, failed = [], []
    for c in candidates:
        try:
            reports.append(critique(c, niche=niche, grammar=grammar,
                                    styles=styles, source_kind=source_kind))
        except Exception as exc:
            # A candidate that could not be measured used to disappear from the
            # table and survive only as a stderr line, so a two-way A/B where B
            # failed printed a one-row table that read like A had won.
            failed.append((str(c), "%s: %s" % (type(exc).__name__, exc)))
            print("  ! %s: %s" % (c, exc), file=sys.stderr)
    # An unscored candidate sorts LAST, not as zero: "could not be judged" is a
    # different thing from "judged and bad", and ranking it as the worst entry
    # would be an answer this module does not have.
    reports.sort(key=lambda r: (0 if _isnum(r.get("overall_score")) else 1,
                                -float(r.get("overall_score") or 0.0)))
    rows = ["%-34s %6s  %-17s  %s" % ("candidate", "score", "verdict",
                                      "top defect")]
    rows.append("-" * 110)
    for r in reports:
        top = (r.get("defects") or [{}])[0]
        sc = r.get("overall_score")
        rows.append("%-34s %6s  %-17s  %s"
                    % (str(r["candidate"].get("image_id"))[:34],
                       ("%.1f" % float(sc)) if _isnum(sc) else "n/a",
                       r.get("verdict"), (top.get("headline") or "-")[:52]))
    for path, err in failed:
        rows.append("%-34s %6s  %-17s  %s"
                    % (os.path.basename(path)[:34], "n/a", "NOT MEASURED",
                       err[:52]))
    return reports, "\n".join(rows)


# ------------------------------------------------------------------- persistence
def save_report(report, path):
    """Write through write_json's atomic tmp+replace."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    return write_json(path, report)


def load_report(path):
    r = read_json(path, default=None)
    if r is None:
        raise IOError("no report at %s" % path)
    if r.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("report schema_version %r != %r"
                         % (r.get("schema_version"), SCHEMA_VERSION))
    return r


# ---------------------------------------------------------------------- selftest
def _synthetic_grammar():
    """A two-rule grammar: one meaningful, one not.

    Built by hand rather than harvested so the assertions below test THIS
    module's logic and not the harvest's.
    """
    def rule(key, meaningful, lo, hi, centre, delta, weight):
        return {"key": key, "unit": "fraction", "family": "face",
                "n_win": 14, "n_lose": 11, "n_win_finite": 14,
                "n_lose_finite": 11, "win_median": centre, "win_mean": centre,
                "win_std": (hi - lo) / 1.35, "win_p10": lo, "win_p25": lo,
                "win_p75": hi, "win_p90": hi, "lose_median": 0.09,
                "lose_mean": 0.09, "lose_p25": 0.06, "lose_p75": 0.12,
                "delta": delta, "p_value": 0.001, "q_value": 0.01,
                "direction": "higher", "target_lo": lo, "target_hi": hi,
                "target_center": centre, "separation": 1.4,
                "meaningful": meaningful,
                "reason": "" if meaningful else "effect below EFFECT_MIN",
                "weight": weight if meaningful else 0.0}
    return {
        "schema_version": SCHEMA_VERSION, "niche": "synthetic",
        "confidence": "weak",
        "groups": {"n_win": 14, "n_lose": 11},
        "rules": {
            "face_area_frac_largest": rule("face_area_frac_largest", True,
                                           0.18, 0.27, 0.22, 0.61, 0.61),
            "sat_mean": rule("sat_mean", False, 0.30, 0.55, 0.42, 0.05, 0.05),
        },
        "meaningful_keys": ["face_area_frac_largest"],
        "warnings": [], "notes": [],
    }


def _blank_row(**over):
    """A feature row that trips nothing, so each assertion tests one thing."""
    row = {}
    for k in measure.FEATURE_KEYS:
        row[k] = 0.0
    row.update({
        "face_count": 1.0, "face_area_frac_largest": 0.22,
        "face_area_frac_total": 0.22, "face_edge_margin_min": 0.20,
        "text_box_count": 4.0, "survive_text_px_210": 40.0,
        "survive_face_px_210": 60.0, "survive_edge_ret_210": 0.40,
        "survive_lum_michelson_210": 0.60,
        "focal_count": 2.0, "focal_concentration": 0.70,
        "lum_michelson": 0.60, "text_overlaps_face_frac": 0.0,
        "tm_subject_max_L": 120.0, "tm_flat_g_p90": 0.10,
        "subject_bg_lum_contrast": 0.40, "bg_blur_ratio": 0.4,
        "negative_space_frac": 0.20, "sat_mean": 0.42,
    })
    row.update(over)
    return row


def _folder_selftest(candidate, folders):
    """End-to-end: measure a real folder, build a grammar, critique one file.

    THE LABELS ARE A PROXY, and the printed output says so. Nathan's own
    iteration is the only outcome signal this folder carries: a file whose name
    ends _V2 / _FINAL / _APPROVED is the version he kept after looking at the
    earlier one, and the plain-named file is the version he replaced. That is a
    real preference and a defensible split, but it is HIS preference, not view
    data, and it says nothing about what the audience did. Whatever the grammar
    reports about this population, its own `confidence` field governs — with
    ~10 per group and one channel it will not exceed 'weak'.
    """
    gm = _optional("grammar")
    if gm is None:
        print("SELFTEST_SKIP folder pass: grammar.py not importable yet")
        return None, None
    # JPEG ONLY, deliberately, and the count that is dropped is printed rather
    # than swallowed. measure.IMAGE_PATTERNS covers jpg/jpeg/png/webp, but the
    # 27 PNGs sitting in READY-TO-POST are contact sheets, verify sheets and AB
    # grids - FONT_CHECK.png, MONKEY_verify_sheet.png, SHORTS_ALL.png - not
    # thumbnails. Measuring them into the population would build the "winners'
    # band" partly out of screenshots of this pipeline's own diagnostics.
    paths, skipped_kinds = [], []
    for f in folders:
        paths.extend(sorted(glob.glob(f + "/*.jpg")))
        for pat in measure.IMAGE_PATTERNS:
            if pat != "*.jpg":
                skipped_kinds.extend(glob.glob(f + "/" + pat))
    paths = [p.replace(chr(92), "/") for p in paths]
    if skipped_kinds:
        print("  (%d non-JPEG images in these folders are excluded on purpose: "
              "they are contact sheets, not thumbnails)" % len(skipped_kinds))
    cand = candidate.replace("\\", "/")
    pop = [p for p in paths if os.path.basename(p).lower()
           != os.path.basename(cand).lower()]
    if len(pop) < 4:
        print("SELFTEST_SKIP folder pass: only %d population images" % len(pop))
        return None, None

    print("  measuring %d population images ..." % len(pop))
    rows = []
    for p in pop:
        r = measure.measure_file(p, source_kind="local")
        if not r.get("measure_error"):
            rows.append(r)

    winners = ("_v2", "_final", "_approved", "_b", "_c")
    hrows = []
    for r in rows:
        stem = str(r.get("image_id") or "").lower()
        is_win = stem.endswith(winners)
        hrows.append({
            "video_id": r["image_id"], "channel_id": "LOCAL",
            "channel": "Texas Trial Tracker (local files)",
            "outlier_score": 2.0 if is_win else 0.5,
            "outlier_log2": 1.0 if is_win else -1.0,
            "outlier_confidence": 1.0, "settled": True,
            "views_per_day": 0.0, "view_count": 0, "age_days": 999.0,
            "schema_version": SCHEMA_VERSION,
        })
    n_win = sum(1 for h in hrows if h["outlier_score"] > 1.0)
    print("  proxy labels: %d kept-version 'winners', %d replaced 'losers' "
          "(Nathan's own iteration, NOT view data)"
          % (n_win, len(hrows) - n_win))

    g = gm.build_grammar(measure_rows=rows, harvest_rows=hrows)
    rep = critique(cand, grammar=g, source_kind="local")
    return g, rep


def selftest():
    """A checker that cannot fail is worse than no checker.

    Every assertion below is one this module could genuinely get wrong: the
    headline numbers, the non-meaningful-rule suppression, and the pre-delivery
    scope rule that stops the engine condemning every competitor thumbnail it
    downloads.
    """
    checks = []
    g = _synthetic_grammar()

    # 1. a candidate well below the winners' band raises a defect whose headline
    #    carries BOTH the observed number and the winners' median.
    low = _blank_row(face_area_frac_largest=0.06)
    d1, _ = defects_from_grammar(low, g)
    hit = [d for d in d1 if d["key"] == "face_area_frac_largest"]
    checks.append(("headline-carries-numbers",
                   bool(hit) and "6" in hit[0]["headline"]
                   and "22" in hit[0]["headline"]))

    # 2. a candidate inside the band raises nothing for that key and shows up
    #    as a strength.
    ok = _blank_row(face_area_frac_largest=0.22)
    res = score_candidate(ok, grammar=g)
    checks.append(("inside-band-is-a-strength",
                   not any(d["key"] == "face_area_frac_largest"
                           for d in res["defects"])
                   and any(s["key"] == "face_area_frac_largest"
                           for s in res["strengths"])))

    # 3. a NON-meaningful rule raises nothing at any deviation.
    far = _blank_row(sat_mean=0.99)
    d3, _ = defects_from_grammar(far, g)
    checks.append(("non-meaningful-rule-is-silent",
                   not any(d["key"] == "sat_mean" for d in d3)))

    # 4. THE ONE THAT MATTERS: the pre-delivery gate fires on a local file and
    #    is muted to a diagnostic on a downloaded one.
    post = _blank_row(tm_flat_g_p90=0.45)
    dl, _, _ = defects_from_principles(post, source_kind="local")
    dy, diagy, _ = defects_from_principles(post, source_kind="youtube")
    checks.append(("posterised-local-fails",
                   any(d["id"] == "posterised" and d["severity"] > 0
                       for d in dl)))
    checks.append(("posterised-youtube-is-diagnostic-only",
                   not any(d["id"] == "posterised" for d in dy)
                   and any(d["id"] == "posterised" and d["severity"] == 0
                           for d in diagy)))

    # 5. the structural checks the brief asks for actually fire on the numbers
    #    that should trip them, and stay silent when the extras are absent.
    coll = _blank_row()
    dc, _, _ = defects_from_principles(
        coll, extras={"text_line_count": 3.0, "text_min_line_gap_px": -4.0,
                      "text_mean_line_h_px": 60.0,
                      "text_edge_margin_min": 0.004,
                      "focal_edge_touch_frac": 0.44, "dup_inliers": 0.0})
    ids = {d["id"] for d in dc}
    checks.append(("text-collision-fires", "text_lines_collide" in ids))
    checks.append(("text-edge-fires", "text_touches_edge" in ids))
    checks.append(("focal-edge-fires", "focal_mass_crosses_edge" in ids))
    dn, _, skipped = defects_from_principles(coll)
    checks.append(("no-extras-means-skipped-not-passed",
                   not any(i in {d["id"] for d in dn}
                           for i in ("text_lines_collide", "text_touches_edge"))
                   and any("text_lines_collide" in s for s in skipped)))

    # 6. a meaningful grammar rule suppresses the principle on the same key.
    g2 = _synthetic_grammar()
    g2["rules"]["lum_michelson"] = dict(
        g2["rules"]["face_area_frac_largest"], key="lum_michelson",
        target_lo=0.4, target_hi=0.7, target_center=0.55, meaningful=True,
        unit="unitless", family="luminance")
    flat = _blank_row(lum_michelson=0.10)
    _, _, sk = defects_from_principles(flat, grammar=g2)
    checks.append(("grammar-suppresses-principle",
                   any("flat_tonal_range" in s and "suppressed" in s
                       for s in sk)))

    # 7. THE DETECTOR ITSELF, against a known answer. A defect generator whose
    #    measurement has never been shown to recover a number someone already
    #    knows is just an opinion with a decimal point on it. Two synthetic
    #    title lines are drawn a known distance apart and the probe must report
    #    that distance, and must report the lines shrinking together.
    def _two_line_title(offset, second=True):
        rng = np.random.default_rng(0)
        yy, xx = np.mgrid[0:720, 0:1280]
        base = 40 + 50 * (xx / 1280.0) + 30 * (yy / 720.0)
        img = np.ascontiguousarray(
            np.dstack([base, base * 0.95, base * 0.9]).astype(np.uint8))
        f = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, "GUILTY ON ALL", (120, 300), f, 3.0, (240, 240, 240),
                    8, cv2.LINE_AA)
        if second:
            cv2.putText(img, "FIVE COUNTS", (120, 300 + offset), f, 3.0,
                        (240, 240, 240), 8, cv2.LINE_AA)
        return np.ascontiguousarray(np.clip(
            img.astype(np.float32) + rng.normal(0, 4, img.shape),
            0, 255).astype(np.uint8))

    def _ink_cap_height(text):
        """Ink height of one drawn line, measured on the glyphs themselves.

        This used to be the literal 61, with a comment saying it "measures
        61px". A constant that describes what another library draws is a
        constant that goes stale silently: a Hershey metric change, a different
        cv2 build or an edited font scale would move the true answer while the
        assertion kept comparing against 61 and still passing. Both title lines
        are all-caps with no descenders, so the ink box IS the cap height, and
        it is taken from the same putText call the test image uses.
        """
        pad = np.zeros((300, 1280), np.uint8)
        cv2.putText(pad, text, (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 3.0,
                    255, 8, cv2.LINE_AA)
        ys = np.where(pad.max(axis=1) > 0)[0]
        return float(ys.max() - ys.min() + 1) if ys.size else float("nan")

    cap_h = _ink_cap_height("GUILTY ON ALL")
    cap_h2 = _ink_cap_height("FIVE COUNTS")
    checks.append(("both-title-lines-same-cap-height",
                   _isnum(cap_h) and abs(cap_h - cap_h2) <= 1.0))
    print("  derived cap height at scale 3.0, thickness 8: %.0f px" % cap_h)

    recovered, counts = [], []
    for offset in (200, 140, 90):
        ex = structure_probe(_two_line_title(offset), faces=[])
        recovered.append((offset - cap_h, ex["text_min_line_gap_px"]))
        counts.append(ex["text_line_count"])
    # text_line_count is printed in every report, so a two-line title that
    # counts as three is a wrong number on the page, not just an internal one.
    # It counted 3 until the grouper was made order-independent.
    checks.append(("line-count-matches-the-lines-drawn",
                   all(c == 2.0 for c in counts)
                   and structure_probe(_two_line_title(200, second=False),
                                       faces=[])["text_line_count"] == 1.0))
    checks.append(("gap-probe-recovers-known-answer",
                   all(_isnum(got) and abs(got - true) <= 3.0
                       for true, got in recovered)))
    checks.append(("gap-probe-is-monotonic",
                   recovered[0][1] > recovered[1][1] > recovered[2][1]))
    print("  gap probe, true vs measured: " +
          "  ".join("%.0f->%s" % (t, _n(g, 0)) for t, g in recovered))

    # 8. THE CHECKS ADDED WHEN THIS MODULE WAS HARDENED. Each one is a bug that
    #    was measured here, not a hypothetical.
    #    (a) an unmeasurable candidate must NOT come back as a perfect score.
    nothing = score_candidate({})
    checks.append(("unmeasurable-row-is-not-scored",
                   nothing["overall_score"] is None
                   and nothing["verdict"] == "insufficient-data"))
    nan_row = dict((k, float("nan")) for k in measure.FEATURE_KEYS)
    checks.append(("all-nan-row-is-not-scored",
                   score_candidate(nan_row)["overall_score"] is None))
    #    and a normal row must still score, so the guard above is not just
    #    switching the module off.
    checks.append(("normal-row-still-scores",
                   _isnum(score_candidate(_blank_row())["overall_score"])))

    #    (b) the probe must survive the image shapes a caller really passes.
    def _probe_ok(arr):
        try:
            ex = structure_probe(arr, faces=[])
            return isinstance(ex, dict) and "text_line_count" in ex
        except Exception:
            return False
    grey2d = np.full((360, 640), 90, np.uint8)
    checks.append(("probe-survives-2d-grayscale", _probe_ok(grey2d)))
    checks.append(("probe-survives-float32",
                   _probe_ok(np.full((360, 640, 3), 90.0, np.float32))))
    checks.append(("probe-survives-1x1", _probe_ok(np.zeros((1, 1, 3), np.uint8))))
    checks.append(("probe-refuses-a-non-image",
                   not _probe_ok(np.zeros((4, 4, 7), np.uint8))))

    #    (c) the gate thresholds must BE verify_thumb's, not a copy of them.
    checks.append(("gate-limits-come-from-verify-thumb",
                   GATE_FLAT == float(verify_thumb.LIM_FLAT)
                   and GATE_SUBJECT_L == float(verify_thumb.LIM_L)
                   and GATE_DUP == float(verify_thumb.LIM_DUP)))

    #    (d) the saliency this module thresholds must be measure's own, or the
    #        focal blob it reports on is not the blob measure counted.
    _sal_probe = _saliency(_two_line_title(200))
    _sal_measure = measure._saliency_map(_two_line_title(200))
    checks.append(("saliency-identical-to-measure",
                   _sal_probe.shape == _sal_measure.shape
                   and float(np.max(np.abs(_sal_probe - _sal_measure))) < 1e-9))

    #    (e) a grammar rule must quote the sample it was actually computed on.
    g_fin = _synthetic_grammar()
    g_fin["rules"]["face_area_frac_largest"]["n_win_finite"] = 6
    g_fin["rules"]["face_area_frac_largest"]["n_lose_finite"] = 5
    d_fin, _ = defects_from_grammar(_blank_row(face_area_frac_largest=0.06),
                                    g_fin)
    checks.append(("defect-quotes-finite-sample",
                   bool(d_fin) and d_fin[0]["n_win"] == 6
                   and "6 winners vs 5 losers" in d_fin[0]["detail"]))

    #    (f) an image_id that is not a legal filename must not become a path.
    checks.append(("report-stem-is-a-legal-filename",
                   _safe_stem("a/b:c*?" + chr(92) + "d") == "a_b_c___d"
                   and _safe_stem(None) == "candidate"
                   and _safe_stem("  .. ") == "candidate"))

    ok_all = all(c for _, c in checks)
    print("\n" + " ".join("%s=%s" % (n, "ok" if c else "BLIND")
                          for n, c in checks))
    print("SELFTEST_PASS" if ok_all else "SELFTEST_FAIL")

    # ---- the real pass the brief asks for -----------------------------------
    cand = "D:/Boyd Clips/READY-TO-POST/MONKEY_thumbnail_V2.jpg"
    folders = ["D:/Boyd Clips/READY-TO-POST",
               "D:/Boyd Clips/READY-TO-POST/AB-THUMBNAILS"]
    if not os.path.exists(cand):
        print("SELFTEST_SKIP folder pass: %s not on disk" % cand)
        return 0 if ok_all else 1
    print("\n" + "=" * 100)
    print("FOLDER PASS - %s against a grammar built from the rest of the folder"
          % os.path.basename(cand))
    print("=" * 100)
    g3, rep = _folder_selftest(cand, folders)
    if rep is not None:
        gm = _optional("grammar")
        if gm is not None and hasattr(gm, "grammar_summary"):
            print("\nGRAMMAR (confidence=%s)" % g3.get("confidence"))
            for line in gm.grammar_summary(g3)[:12]:
                print("  " + line)
        print()
        print(render_report(rep))
    return 0 if ok_all else 1


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m tools.thumbeng.critique",
        description="Score a candidate thumbnail against a niche grammar and "
                    "general design principles.")
    ap.add_argument("images", nargs="*", help="candidate image path(s)")
    ap.add_argument("--niche", default=None,
                    help="niche name; loads its grammar.json and styles.json")
    ap.add_argument("--source-kind", default="local",
                    choices=("local", "youtube"),
                    help="'youtube' mutes the pre-delivery posterisation gate")
    ap.add_argument("--compare", nargs="+", default=None,
                    help="rank several candidates against one grammar")
    ap.add_argument("--top", type=int, default=None, help="show only N defects")
    ap.add_argument("--json", default=None, help="write the report here")
    ap.add_argument("--no-probe", action="store_true",
                    help="skip structure_probe (faster, loses the edge/text "
                         "collision checks)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    if a.compare:
        reports, table = compare(a.compare, source_kind=a.source_kind,
                                 niche=a.niche)
        print(table)
        # Exit non-zero when nothing could be scored, so a script that ranks two
        # candidates and reads the exit code is not told "fine" after both
        # failed to measure.
        return 0 if reports else 1

    if not a.images:
        ap.print_help()
        return 2

    # --json names ONE file. With several images the loop used to write every
    # report to it in turn and the last one silently won, so the caller got a
    # report for an image they did not ask about under a filename that said
    # otherwise. Several images get a per-image suffix and are told so.
    multi = a.json and len(a.images) > 1
    if multi:
        print("--json with %d images: writing one file per image, suffixed with "
              "the image id" % len(a.images), file=sys.stderr)
    worst = 0
    for img in a.images:
        out = a.json
        if multi:
            stem, ext = os.path.splitext(a.json)
            out = "%s.%s%s" % (stem, _safe_stem(
                os.path.splitext(os.path.basename(img))[0]), ext or ".json")
        try:
            rep = critique(img, niche=a.niche, source_kind=a.source_kind,
                           out_json=out, probe=not a.no_probe)
        except Exception as exc:
            print("  ! %s: %s" % (img, exc), file=sys.stderr)
            worst = 1
            continue
        print(render_report(rep, top_n=a.top))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
