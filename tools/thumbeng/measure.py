# -*- coding: utf-8 -*-
"""measure.py - the design properties of any thumbnail, as 133 numbers.

This module defines the shared vocabulary of the whole engine. styles.py,
grammar.py and critique.py contain ZERO image-analysis code; they derive
everything from the flat dict returned here.

WHY EVERYTHING IS MEASURED AT A CANONICAL 1280x720
thumb_metrics.py states explicitly that its metrics are NOT scale-invariant.
Measuring at native resolution therefore gives different numbers for the same
design, and Nathan's own 1280x720 exports would be incomparable with a
competitor's 320x180 mqdefault. Every geometric key is additionally normalised
to a fraction of the frame, so the vocabulary stays resolution-free.

DE-LETTERBOXING IS LOAD-BEARING
Measured, not assumed: i.ytimg.com/vi/<id>/hqdefault.jpg is 480x360 with pure
black bars top and bottom, sddefault.jpg is 640x480 with bars, and
maxresdefault / hq720 / mqdefault are native 16:9 with none. Measuring a
letterboxed fallback without cropping poisons lum_mean, lum_dark_frac,
edge_density, balance_tb and every palette and saliency key. The crop is done by
ASPECT ARITHMETIC, never by detecting dark rows: a legitimately dark court
thumbnail must not be eaten by a darkness detector.

WHY TEXT IS NOT DETECTED WITH thumb_metrics.text_mask
That mask is keyed to Nathan's own graphics palette - white above 225,
saturated yellow, and the red arrow. It is correct for his files and near-blind
on a competitor's blue, green or black title. Text here is found generically
with cv2.MSER plus geometry filters. thumb_metrics' own outputs are still
carried through under the tm_ prefix so critique.py can speak verify_thumb.py's
exact language.

NaN POLICY
Exactly one set of keys may be NaN - NAN_WHEN_NO_FACE - and, with ONE named
exception, only when face_count == 0. Every other key in FEATURE_KEYS is always
finite. Downstream modules need NaN-aware code for that set and nothing else.
Never None, never a string, never a missing key.

The exception is tm_subject_max_L. thumb_metrics.subject_max_L samples the
NATIVE array and returns NaN when no face region carries at least 400 usable
pixels after its graphics / hair / blowout filters, so a real face can be too
small to sample. MEASURED 2026-08-30 by re-measuring all twelve READY-TO-POST
files at each YouTube variant size: no occurrences at 480x270 or 320x180, and
2 of 12 at 120x90 (SANCHEZ_thumbnail, SANCHEZ_thumbnail_FINAL). So it is rare
and confined to default.jpg, but it is real and must not be asserted away.
It is deliberately NOT back-filled from a canonical-resolution median: the whole
reason the tm_ keys exist is that they equal verify_thumb.py's own numbers on
the same file, and quietly swapping in a different measurement would end that.
face_largest_h_frac * src_height_px tells a reader whether the face was ever
sampleable.

Faces whose box does not intersect the frame are dropped before face_count is
computed. Without that a detector box centred off-frame gave face_count > 0 with
an empty subject mask, and every subject-vs-background key went NaN while the
row still claimed a face - the exact combination that makes "NaN means no face"
false downstream.

PERSISTENCE
This module is the only writer of measurements.jsonl / measurements.csv and the
only definition of load/save. styles.py, grammar.py and critique.py import
load_measurements from here rather than reading the file themselves.
"""

import glob
import hashlib
import math
import os
import sys

import numpy as np
import cv2

# ---------------------------------------------------------------- bootstrap
# Package-relative when imported normally; path-based when run as a script.
if __package__ in (None, ""):
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _REPO = os.path.dirname(os.path.dirname(_HERE))
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    from tools.thumbeng import (SCHEMA_VERSION, TOOLS_DIR, YUNET, niche_dir,
                                read_jsonl, run_manifest, utc_now, write_csv,
                                write_jsonl)
else:
    from . import (SCHEMA_VERSION, TOOLS_DIR, YUNET, niche_dir, read_jsonl,
                   run_manifest, utc_now, write_csv, write_jsonl)

# APPEND, not insert(0): tools/harvest.py is an unrelated pre-existing module
# and prepending tools/ would shadow tools/thumbeng/harvest.py inside this
# package.
if TOOLS_DIR not in sys.path:
    sys.path.append(TOOLS_DIR)
import thumb_metrics  # noqa: E402

try:
    from PIL import Image as _PILImage
except ImportError:  # PIL is present on this machine; guarded so a missing
    _PILImage = None  # PIL costs only the jpeg quant table, not the run.

# YuNet on cv2 5.0 prints "Targets are not supported by the new graph engine"
# from native code when the detector is built. Verified on this machine:
# cv2.setLogLevel(0) does NOT stop it, cv2.utils.logging.setLogLevel(SILENT)
# does. Silenced once at import rather than left to print per image, because a
# 60-video harvest would otherwise bury its own progress output.
try:
    import cv2.utils.logging as _cv2log
    _cv2log.setLogLevel(_cv2log.LOG_LEVEL_SILENT)
except Exception:
    try:
        cv2.setLogLevel(0)
    except Exception:
        pass  # cosmetic only; never worth failing a measurement over

CANON_W, CANON_H = 1280, 720

# 210 is the "does it survive the grid" width named in the brief - roughly what
# a thumbnail occupies in a desktop feed row. The height is DERIVED from the
# canonical frame instead of written as 118, so the preview cannot silently
# stop being 16:9 if CANON_W/CANON_H are ever changed.
PREVIEW_W = 210
PREVIEW_H = int(round(PREVIEW_W * CANON_H / float(CANON_W)))

# edge_density and survive_edge_ret_210 mean nothing next to each other unless
# both use IDENTICAL Canny thresholds. They were two separate literal pairs and
# nothing stopped one being edited alone, so they are named once here.
_CANNY_LO, _CANNY_HI = 80, 160

# The most of a frame de-letterboxing may ever remove. The real cases are fixed
# geometry: hqdefault 480x360 and sddefault 640x480 are both 4:3, and cropping
# 4:3 to 16:9 removes 1 - (9/16)/(3/4) = 0.25 of the rows, so 0.30 clears them
# with margin. MEASURED consequence of having had no cap: a 1000x10 banner was
# "de-letterboxed" to 18x10, discarding 98.2% of the picture and reporting
# letterbox_frac 0.982 as though the discarded part had been black bars. Past
# the cap the frame is measured as it stands and letterbox_frac stays 0.0.
MAX_LETTERBOX_FRAC = 0.30

# Hue is binned into 36 arcs of 10 degrees. Named so the bin count, the clip
# limit and the bin-centre offset cannot drift apart.
_HUE_BINS = 36
_HUE_BIN_DEG = 360.0 / _HUE_BINS

_EPS = 1e-9

# --------------------------------------------------------------- vocabulary
FEATURE_KEYS = (
    # provenance / technical (7)
    "src_width_px", "src_height_px", "src_aspect", "src_bytes",
    "jpeg_qsum_luma", "letterbox_frac", "source_kind_code",
    # face (17)
    "face_count", "face_area_frac_total", "face_area_frac_largest",
    "face_largest_cx", "face_largest_cy", "face_largest_w_frac",
    "face_largest_h_frac", "face_largest_score", "face_largest_diag_frac",
    "face_area_frac_mean", "face_centroid_x", "face_centroid_y", "face_spread",
    "face_largest_L_median", "face_thirds_dist", "face_edge_margin_min",
    "face_subject_offset_x",
    # luminance (15)
    "lum_mean", "lum_median", "lum_std", "lum_p05", "lum_p95", "lum_range",
    "lum_rms_contrast", "lum_michelson", "lum_dark_frac", "lum_mid_frac",
    "lum_bright_frac", "lum_entropy", "lum_clip_low_frac", "lum_clip_high_frac",
    "subject_bg_lum_contrast",
    # colour (23)
    "sat_mean", "sat_median", "sat_std", "sat_p90", "sat_high_frac",
    "chroma_mean", "chroma_p90", "colourfulness", "hue_entropy",
    "hue_dominant_deg", "hue_dominant_frac", "hue_second_deg",
    "hue_second_frac", "hue_circvar", "warm_frac", "cool_frac",
    "warm_cool_ratio", "cct_kelvin", "lab_a_mean", "lab_b_mean", "skin_frac",
    "subject_bg_sat_contrast", "subject_bg_hue_dist",
    # palette (24)
    "palette_1_r", "palette_1_g", "palette_1_b", "palette_1_frac",
    "palette_2_r", "palette_2_g", "palette_2_b", "palette_2_frac",
    "palette_3_r", "palette_3_g", "palette_3_b", "palette_3_frac",
    "palette_4_r", "palette_4_g", "palette_4_b", "palette_4_frac",
    "palette_5_r", "palette_5_g", "palette_5_b", "palette_5_frac",
    "palette_top1_frac", "palette_top3_frac", "palette_mean_deltaE",
    "palette_max_deltaE",
    # edge / detail (9)
    "edge_density", "grad_mean", "grad_p90", "laplacian_var", "hf_energy",
    "busyness_tile_std", "clutter_index", "negative_space_frac",
    "bg_blur_ratio",
    # focal / saliency (8)
    "focal_count", "focal_largest_frac", "focal_top1_x", "focal_top1_y",
    "focal_top2_frac", "focal_concentration", "saliency_entropy",
    "saliency_p95",
    # text-like (10)
    "text_area_frac", "text_box_count", "text_largest_box_frac",
    "text_mean_height_frac", "text_max_height_frac", "text_centroid_x",
    "text_centroid_y", "text_contrast", "text_overlaps_face_frac",
    "text_line_count_est",
    # downscale survival (7)
    "survive_ssim_210", "survive_edge_ret_210", "survive_face_px_210",
    "survive_text_px_210", "survive_lum_michelson_210",
    "survive_colourfulness_ratio_210", "survive_focal_count_210",
    # balance / composition (8)
    "balance_lr", "balance_tb", "mass_centroid_x", "mass_centroid_y",
    "thirds_alignment", "center_mass_frac", "symmetry_lr", "quadrant_max_frac",
    # thumb_metrics carry-through (5)
    "tm_flat_g_p90", "tm_poster_fa", "tm_bg_mush", "tm_bg_tiles",
    "tm_subject_max_L",
)

# The ONLY keys allowed to be NaN, and only when face_count == 0.
# face_count and face_area_frac_total are 0.0, never NaN: a faceless thumbnail
# genuinely has zero face area, and turning that into NaN would silently drop
# faceless thumbnails from grammar.py's comparison - which is exactly the
# finding a court-content creator most needs to see.
NAN_WHEN_NO_FACE = frozenset((
    "face_area_frac_largest", "face_largest_cx", "face_largest_cy",
    "face_largest_w_frac", "face_largest_h_frac", "face_largest_score",
    "face_largest_diag_frac", "face_area_frac_mean", "face_centroid_x",
    "face_centroid_y", "face_spread", "face_largest_L_median",
    "face_thirds_dist", "face_edge_margin_min", "face_subject_offset_x",
    "subject_bg_lum_contrast", "subject_bg_sat_contrast",
    "subject_bg_hue_dist", "bg_blur_ratio", "text_overlaps_face_frac",
    "survive_face_px_210", "tm_subject_max_L",
))

# Non-numeric companions, kept strictly separate so feature_vector never has to
# guess. source_kind_code mirrors source_kind numerically (1 local, 2 youtube,
# 0 unknown) so the distinction can sit in the vector. That distinction is NOT
# cosmetic: verify_thumb.py measured that 10 of 12 competitor thumbnails trip
# the posterisation gate purely because YouTube re-encodes them (quant table sum
# 736 vs 369 for a local export), so critique.py must never fail a 'youtube'
# row on tm_flat_g_p90.
IDENTITY_KEYS = (
    "image_id", "image_path", "image_sha1", "source_kind", "thumb_quality",
    "schema_version", "measured_utc", "measure_error",
)

SOURCE_KIND_CODE = {"unknown": 0, "local": 1, "youtube": 2}


def _kd(unit, lo, hi, meaning, higher_is, family):
    return {"unit": unit, "lo": lo, "hi": hi, "meaning": meaning,
            "higher_is": higher_is, "family": family}


# Human labels for all 133 keys. THIS is why styles.py and critique.py contain
# no hand-written English about metrics - they format sentences from KEY_DOC and
# nothing else, so a name or a range changes in exactly one place.
#
# higher_is is 'neither' for every key where nobody has measured a direction on
# this machine, which is most of them. Guessing a direction here would launder a
# hunch into Nathan's report.
KEY_DOC = {
    "src_width_px": _kd("px", 0, 4000, "source image width before any crop", "neither", "technical"),
    "src_height_px": _kd("px", 0, 2400, "source image height before any crop", "neither", "technical"),
    "src_aspect": _kd("ratio", 0.5, 3.0, "source width over height", "neither", "technical"),
    "src_bytes": _kd("count", 0, 800000, "file size on disk", "neither", "technical"),
    "jpeg_qsum_luma": _kd("count", 0, 2000, "sum of the JPEG luma quantisation table; higher means harsher compression", "worse", "technical"),
    "letterbox_frac": _kd("fraction", 0.0, 0.4, "share of source rows cropped off as letterbox bars", "neither", "technical"),
    "source_kind_code": _kd("count", 0, 2, "0 unknown, 1 local export, 2 downloaded from YouTube", "neither", "technical"),

    "face_count": _kd("count", 0, 6, "faces YuNet found", "neither", "face"),
    "face_area_frac_total": _kd("fraction", 0.0, 0.5, "share of the frame covered by all face boxes", "neither", "face"),
    "face_area_frac_largest": _kd("fraction", 0.0, 0.5, "share of the frame covered by the largest face", "neither", "face"),
    "face_largest_cx": _kd("fraction", 0.0, 1.0, "largest face centre, across the frame", "neither", "face"),
    "face_largest_cy": _kd("fraction", 0.0, 1.0, "largest face centre, down the frame", "neither", "face"),
    "face_largest_w_frac": _kd("fraction", 0.0, 0.8, "largest face box width as a share of frame width", "neither", "face"),
    "face_largest_h_frac": _kd("fraction", 0.0, 1.0, "largest face box height as a share of frame height", "neither", "face"),
    "face_largest_score": _kd("unitless", 0.5, 1.0, "YuNet detection confidence for the largest face", "neither", "face"),
    "face_largest_diag_frac": _kd("fraction", 0.0, 1.0, "largest face box diagonal over the frame diagonal", "neither", "face"),
    "face_area_frac_mean": _kd("fraction", 0.0, 0.5, "mean face area share across all faces", "neither", "face"),
    "face_centroid_x": _kd("fraction", 0.0, 1.0, "centroid of all faces, across the frame", "neither", "face"),
    "face_centroid_y": _kd("fraction", 0.0, 1.0, "centroid of all faces, down the frame", "neither", "face"),
    "face_spread": _kd("fraction", 0.0, 0.6, "how far apart the faces sit, in frame widths", "neither", "face"),
    "face_largest_L_median": _kd("L*", 0.0, 100.0, "median lightness of the largest face", "neither", "face"),
    "face_thirds_dist": _kd("fraction", 0.0, 0.5, "distance from the largest face to the nearest rule-of-thirds intersection", "neither", "face"),
    "face_edge_margin_min": _kd("fraction", 0.0, 0.5, "smallest gap between any face box and the frame edge", "neither", "face"),
    "face_subject_offset_x": _kd("fraction", -0.5, 0.5, "how far the largest face sits off centre, negative left", "neither", "face"),

    "lum_mean": _kd("L*", 0.0, 100.0, "average lightness", "neither", "contrast"),
    "lum_median": _kd("L*", 0.0, 100.0, "median lightness", "neither", "contrast"),
    "lum_std": _kd("L*", 0.0, 50.0, "spread of lightness", "neither", "contrast"),
    "lum_p05": _kd("L*", 0.0, 100.0, "5th percentile lightness, the shadows", "neither", "contrast"),
    "lum_p95": _kd("L*", 0.0, 100.0, "95th percentile lightness, the highlights", "neither", "contrast"),
    "lum_range": _kd("L*", 0.0, 100.0, "highlight minus shadow lightness", "neither", "contrast"),
    "lum_rms_contrast": _kd("unitless", 0.0, 0.5, "RMS contrast, the standard deviation of normalised lightness", "neither", "contrast"),
    "lum_michelson": _kd("unitless", 0.0, 1.0, "Michelson contrast between highlights and shadows", "neither", "contrast"),
    "lum_dark_frac": _kd("fraction", 0.0, 1.0, "share of the frame darker than L*25", "neither", "contrast"),
    "lum_mid_frac": _kd("fraction", 0.0, 1.0, "share of the frame in the midtones", "neither", "contrast"),
    "lum_bright_frac": _kd("fraction", 0.0, 1.0, "share of the frame lighter than L*75", "neither", "contrast"),
    "lum_entropy": _kd("bits", 0.0, 8.0, "how evenly the tones are spread across the histogram", "neither", "contrast"),
    "lum_clip_low_frac": _kd("fraction", 0.0, 0.3, "share of pixels crushed to black", "worse", "contrast"),
    "lum_clip_high_frac": _kd("fraction", 0.0, 0.3, "share of pixels blown to white", "worse", "contrast"),
    "subject_bg_lum_contrast": _kd("unitless", 0.0, 1.0, "lightness separation between the faces and everything else", "neither", "contrast"),

    "sat_mean": _kd("fraction", 0.0, 1.0, "average saturation", "neither", "colour"),
    "sat_median": _kd("fraction", 0.0, 1.0, "median saturation", "neither", "colour"),
    "sat_std": _kd("fraction", 0.0, 0.6, "spread of saturation", "neither", "colour"),
    "sat_p90": _kd("fraction", 0.0, 1.0, "saturation of the most colourful tenth", "neither", "colour"),
    "sat_high_frac": _kd("fraction", 0.0, 1.0, "share of the frame with saturation above 0.5", "neither", "colour"),
    "chroma_mean": _kd("unitless", 0.0, 80.0, "average Lab chroma, colour intensity independent of lightness", "neither", "colour"),
    "chroma_p90": _kd("unitless", 0.0, 120.0, "Lab chroma of the most colourful tenth", "neither", "colour"),
    "colourfulness": _kd("unitless", 0.0, 120.0, "Hasler-Suesstrunk colourfulness", "neither", "colour"),
    "hue_entropy": _kd("bits", 0.0, 5.2, "how many different hues the frame uses", "neither", "colour"),
    "hue_dominant_deg": _kd("deg", 0.0, 360.0, "the dominant hue", "neither", "colour"),
    "hue_dominant_frac": _kd("fraction", 0.0, 1.0, "share of colour carried by the dominant hue", "neither", "colour"),
    "hue_second_deg": _kd("deg", 0.0, 360.0, "the second hue", "neither", "colour"),
    "hue_second_frac": _kd("fraction", 0.0, 1.0, "share of colour carried by the second hue", "neither", "colour"),
    "hue_circvar": _kd("unitless", 0.0, 1.0, "circular variance of hue; 0 is one hue, 1 is hues cancelling out", "neither", "colour"),
    "warm_frac": _kd("fraction", 0.0, 1.0, "share of the frame that is a saturated warm colour", "neither", "colour"),
    "cool_frac": _kd("fraction", 0.0, 1.0, "share of the frame that is a saturated cool colour", "neither", "colour"),
    "warm_cool_ratio": _kd("ratio", 0.0, 10.0, "warm area over cool area", "neither", "colour"),
    "cct_kelvin": _kd("K", 1500.0, 25000.0, "correlated colour temperature of the average colour", "neither", "colour"),
    "lab_a_mean": _kd("unitless", -40.0, 40.0, "average green-red axis; positive is red", "neither", "colour"),
    "lab_b_mean": _kd("unitless", -40.0, 40.0, "average blue-yellow axis; positive is yellow", "neither", "colour"),
    "skin_frac": _kd("fraction", 0.0, 1.0, "share of the frame in the skin-tone range", "neither", "colour"),
    "subject_bg_sat_contrast": _kd("unitless", 0.0, 1.0, "saturation separation between the faces and everything else", "neither", "colour"),
    "subject_bg_hue_dist": _kd("deg", 0.0, 180.0, "hue distance between the faces and everything else", "neither", "colour"),

    "palette_top1_frac": _kd("fraction", 0.0, 1.0, "share of the frame taken by the biggest palette colour", "neither", "palette"),
    "palette_top3_frac": _kd("fraction", 0.0, 1.0, "share of the frame taken by the three biggest palette colours", "neither", "palette"),
    "palette_mean_deltaE": _kd("deltaE", 0.0, 100.0, "average perceptual distance between palette colours", "neither", "palette"),
    "palette_max_deltaE": _kd("deltaE", 0.0, 150.0, "largest perceptual distance between palette colours", "neither", "palette"),

    "edge_density": _kd("fraction", 0.0, 0.2, "share of pixels on a Canny edge", "neither", "detail"),
    "grad_mean": _kd("0-255", 0.0, 80.0, "average Sobel gradient magnitude", "neither", "detail"),
    "grad_p90": _kd("0-255", 0.0, 200.0, "gradient magnitude of the sharpest tenth", "neither", "detail"),
    "laplacian_var": _kd("unitless", 0.0, 3000.0, "Laplacian variance, the standard focus measure", "neither", "detail"),
    "hf_energy": _kd("0-255", 0.0, 30.0, "average high-pass energy, fine texture", "neither", "detail"),
    "busyness_tile_std": _kd("fraction", 0.0, 0.15, "how unevenly detail is spread across 40px tiles", "neither", "detail"),
    "clutter_index": _kd("fraction", 0.0, 1.0, "share of tiles that are busy", "neither", "detail"),
    "negative_space_frac": _kd("fraction", 0.0, 1.0, "share of the frame that is quiet, empty area", "neither", "detail"),
    "bg_blur_ratio": _kd("ratio", 0.0, 3.0, "background sharpness over face sharpness; below 1 means the background is softer", "neither", "detail"),

    "focal_count": _kd("count", 0, 10, "how many distinct high-attention blobs the frame has", "neither", "focal"),
    "focal_largest_frac": _kd("fraction", 0.0, 1.0, "size of the biggest attention blob", "neither", "focal"),
    "focal_top1_x": _kd("fraction", 0.0, 1.0, "biggest attention blob, across the frame", "neither", "focal"),
    "focal_top1_y": _kd("fraction", 0.0, 1.0, "biggest attention blob, down the frame", "neither", "focal"),
    "focal_top2_frac": _kd("fraction", 0.0, 1.0, "size of the second attention blob", "neither", "focal"),
    "focal_concentration": _kd("fraction", 0.0, 1.0, "share of all attention landing in the single biggest blob", "neither", "focal"),
    "saliency_entropy": _kd("bits", 0.0, 11.2, "how spread out attention is; low means one clear read", "neither", "focal"),
    "saliency_p95": _kd("fraction", 0.0, 1.0, "strength of the top attention peak", "neither", "focal"),

    "text_area_frac": _kd("fraction", 0.0, 0.5, "share of the frame covered by text-like regions", "neither", "text"),
    "text_box_count": _kd("count", 0, 200, "how many text-like regions were found", "neither", "text"),
    "text_largest_box_frac": _kd("fraction", 0.0, 0.3, "size of the biggest text-like region", "neither", "text"),
    "text_mean_height_frac": _kd("fraction", 0.0, 0.4, "average text height as a share of frame height", "neither", "text"),
    "text_max_height_frac": _kd("fraction", 0.0, 0.4, "tallest text as a share of frame height", "neither", "text"),
    "text_centroid_x": _kd("fraction", 0.0, 1.0, "where the text sits, across the frame", "neither", "text"),
    "text_centroid_y": _kd("fraction", 0.0, 1.0, "where the text sits, down the frame", "neither", "text"),
    "text_contrast": _kd("unitless", 0.0, 1.0, "lightness separation between the text and what is behind it", "neither", "text"),
    "text_overlaps_face_frac": _kd("fraction", 0.0, 1.0, "share of the text that lands on a face", "worse", "text"),
    "text_line_count_est": _kd("count", 0, 12, "estimated number of text lines", "neither", "text"),

    "survive_ssim_210": _kd("unitless", 0.0, 1.0, "how much of the image survives a trip through feed size", "neither", "survival"),
    "survive_edge_ret_210": _kd("fraction", 0.0, 0.1, "edge structure still present after a trip through feed size", "neither", "survival"),
    "survive_face_px_210": _kd("px", 0.0, 118.0, "height of the largest face in a 210px-wide feed thumbnail", "neither", "survival"),
    "survive_text_px_210": _kd("px", 0.0, 118.0, "height of the tallest text in a 210px-wide feed thumbnail", "neither", "survival"),
    "survive_lum_michelson_210": _kd("unitless", 0.0, 1.0, "contrast measured at feed size", "neither", "survival"),
    "survive_colourfulness_ratio_210": _kd("ratio", 0.0, 1.5, "colourfulness at feed size over colourfulness at full size", "neither", "survival"),
    "survive_focal_count_210": _kd("count", 0, 10, "attention blobs still distinct at feed size", "neither", "survival"),

    "balance_lr": _kd("unitless", -1.0, 1.0, "visual weight left minus right; positive is left-heavy", "neither", "composition"),
    "balance_tb": _kd("unitless", -1.0, 1.0, "visual weight top minus bottom; positive is top-heavy", "neither", "composition"),
    "mass_centroid_x": _kd("fraction", 0.0, 1.0, "centre of visual weight, across the frame", "neither", "composition"),
    "mass_centroid_y": _kd("fraction", 0.0, 1.0, "centre of visual weight, down the frame", "neither", "composition"),
    "thirds_alignment": _kd("unitless", 0.0, 1.0, "how close the visual weight sits to a rule-of-thirds intersection", "neither", "composition"),
    "center_mass_frac": _kd("fraction", 0.0, 1.0, "share of visual weight in the middle of the frame", "neither", "composition"),
    "symmetry_lr": _kd("unitless", -1.0, 1.0, "left-right mirror symmetry", "neither", "composition"),
    "quadrant_max_frac": _kd("fraction", 0.25, 1.0, "share of visual weight in the heaviest quarter", "neither", "composition"),

    "tm_flat_g_p90": _kd("fraction", 0.0, 1.0, "posterisation: how flat the flattest tiles are in grey", "worse", "technical"),
    "tm_poster_fa": _kd("fraction", 0.0, 1.0, "chroma banding: share of tiles flat in Lab a*", "worse", "technical"),
    "tm_bg_mush": _kd("fraction", 0.0, 1.0, "share of background tiles with no fine detail left", "worse", "technical"),
    "tm_bg_tiles": _kd("count", 0, 600, "how many background tiles the mush figure was measured over", "neither", "technical"),
    "tm_subject_max_L": _kd("L*", 0.0, 255.0, "lightness of the brightest subject face, from verify_thumb's Gate C", "neither", "technical"),
}

# palette_N_r/g/b/frac are generated rather than typed out 20 times.
for _i in range(1, 6):
    KEY_DOC["palette_%d_r" % _i] = _kd("0-255", 0, 255, "palette colour %d, red" % _i, "neither", "palette")
    KEY_DOC["palette_%d_g" % _i] = _kd("0-255", 0, 255, "palette colour %d, green" % _i, "neither", "palette")
    KEY_DOC["palette_%d_b" % _i] = _kd("0-255", 0, 255, "palette colour %d, blue" % _i, "neither", "palette")
    KEY_DOC["palette_%d_frac" % _i] = _kd("fraction", 0.0, 1.0, "share of the frame taken by palette colour %d" % _i, "neither", "palette")


def describe_key(key):
    """Return the KEY_DOC entry for a key.

    Raises KeyError on an unknown key rather than returning a placeholder, so a
    typo in styles.py or critique.py fails loudly at the point of the typo
    instead of printing a blank label into Nathan's report.
    """
    return KEY_DOC[key]


# ------------------------------------------------------------------ helpers
def _f(x):
    """Coerce to a plain float; no numpy scalars leak into a row."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v


def _safe_div(a, b, default=0.0):
    return a / b if abs(b) > _EPS else default


def _entropy_bits(counts):
    """Shannon entropy in bits of a non-negative count vector."""
    c = np.asarray(counts, dtype=np.float64)
    s = c.sum()
    if s <= 0:
        return 0.0
    p = c[c > 0] / s
    return float(-(p * np.log2(p)).sum())


def _colourfulness(rgb):
    """Hasler & Suesstrunk (2003) colourfulness metric.

    Chosen because it is the standard published measure, needs no model, and
    correlates with the "does this pop in the feed" question better than mean
    saturation, which a single large flat colour can dominate.
    """
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    rg = r - g
    yb = 0.5 * (r + g) - b
    std_root = math.sqrt(float(rg.std()) ** 2 + float(yb.std()) ** 2)
    mean_root = math.sqrt(float(rg.mean()) ** 2 + float(yb.mean()) ** 2)
    return std_root + 0.3 * mean_root


def _michelson(gray_or_L):
    a = np.asarray(gray_or_L, dtype=np.float64)
    p05, p95 = np.percentile(a, [5, 95])
    return float((p95 - p05) / (p95 + p05 + 1e-6))


def _ssim(a, b):
    """Mean SSIM between two float32 single-channel images, 0-255 scale.

    Standard 11x11 gaussian window, sigma 1.5, C1 = (0.01*255)^2,
    C2 = (0.03*255)^2. Implemented here rather than imported because
    scikit-image is not on this interpreter and the formula is six lines.
    """
    C1 = (0.01 * 255.0) ** 2
    C2 = (0.03 * 255.0) ** 2
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
    mu_a2, mu_b2, mu_ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    s_a2 = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a2
    s_b2 = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b2
    s_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_ab
    num = (2 * mu_ab + C1) * (2 * s_ab + C2)
    den = (mu_a2 + mu_b2 + C1) * (s_a2 + s_b2 + C2)
    return float(np.mean(num / (den + 1e-12)))


def _saliency_map(rgb, w=64, h=36):
    """Spectral-residual saliency, pure numpy.

    Chosen over cv2.saliency because it is deterministic, needs no model file,
    and runs on a 64x36 grid in microseconds. Hou & Zhang 2007: take the log
    amplitude spectrum, subtract its local average, invert the transform, and
    the residual is what the frame does that a generic natural image would not.

    np.ptp(a), never a.ptp() - numpy 2.5 removed the ndarray method.
    """
    g = cv2.cvtColor(cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA),
                     cv2.COLOR_RGB2GRAY).astype(np.float32)
    F = np.fft.fft2(g)
    log_amp = np.log(np.abs(F) + 1e-9)
    phase = np.angle(F)
    avg = cv2.blur(log_amp.astype(np.float32), (3, 3))
    residual = log_amp - avg
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (0, 0), 2.0)
    rng = np.ptp(sal)
    if rng < _EPS:
        return np.zeros_like(sal)
    return (sal - sal.min()) / rng


def _focal_stats(rgb):
    """Distinct high-attention blobs and how concentrated attention is.

    A thumbnail with one clear focal point behaves differently in a feed from
    one with four, and that is the property this returns. Blobs are connected
    components of the saliency map above its own 88th percentile, keeping any
    blob of 3 or more cells - a self-relative threshold, so a uniformly
    low-contrast frame still reports where its attention goes rather than
    reporting nothing.
    """
    sal = _saliency_map(rgb)
    cells = float(sal.size)
    total = float(sal.sum())
    thr = float(np.percentile(sal, 88))
    mask = (sal > thr).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    blobs = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area >= 3:
            blobs.append((area, float(cent[i][0]), float(cent[i][1]), i))
    blobs.sort(key=lambda t: -t[0])
    if blobs:
        top = blobs[0]
        top1_frac = top[0] / cells
        top1_x = top[1] / (sal.shape[1] - 1.0)
        top1_y = top[2] / (sal.shape[0] - 1.0)
        conc = _safe_div(float(sal[lab == top[3]].sum()), total, 0.0)
    else:
        top1_frac, top1_x, top1_y, conc = 0.0, 0.5, 0.5, 0.0
    top2_frac = (blobs[1][0] / cells) if len(blobs) > 1 else 0.0
    return {
        "focal_count": len(blobs),
        "focal_largest_frac": top1_frac,
        "focal_top1_x": top1_x,
        "focal_top1_y": top1_y,
        "focal_top2_frac": top2_frac,
        "focal_concentration": conc,
        "saliency_entropy": _entropy_bits(sal.ravel()),
        "saliency_p95": float(np.percentile(sal, 95)),
        "_sal": sal,
    }


def _text_boxes(gray):
    """Text-like regions via MSER plus geometry filters. No OCR is installed.

    MSER finds maximally stable extremal regions, which is what a glyph is: a
    blob whose area barely changes as the threshold moves. Unlike
    thumb_metrics.text_mask this is colour-agnostic, so a competitor's blue or
    black title is found as readily as Nathan's white-on-yellow.

    Filters, all chosen conventions rather than measured thresholds:
      aspect 0.1 to 10   - drops hairline scratches and long horizontal bars
      height 1.5% to 35% - a glyph smaller than 1.5% of frame height is noise
                           at any size, and one taller than 35% is a graphic
      IoU 0.5 dedupe     - MSER emits heavily nested near-duplicates of the same
                           glyph; without this the box count is meaningless
    """
    # Both are absolute pixel counts, so they are derived from the canonical
    # frame area rather than left as bare literals; at 1280x720 they reproduce
    # exactly the 30 / 20000 this was calibrated with. Stated because it is not
    # obvious from the filter list below: MaxArea, not the 35% height filter, is
    # what actually caps a very large glyph - a 252px-tall region (the height
    # filter's own ceiling) only survives while it stays under about 80px wide.
    mser = cv2.MSER_create()
    mser.setMinArea(max(1, int(round(CANON_W * CANON_H * 3.2552e-5))))
    mser.setMaxArea(int(round(CANON_W * CANON_H * 2.1701e-2)))
    try:
        _, raw = mser.detectRegions(gray)
    except cv2.error:
        return []
    h_img, w_img = gray.shape[:2]
    cand = []
    for (x, y, w, h) in raw:
        if h <= 0 or w <= 0:
            continue
        ar = w / float(h)
        hf = h / float(h_img)
        if 0.1 <= ar <= 10.0 and 0.015 <= hf <= 0.35:
            cand.append((int(x), int(y), int(w), int(h)))
    cand.sort(key=lambda b: -(b[2] * b[3]))
    kept = []
    for b in cand:
        bx, by, bw, bh = b
        dup = False
        for (kx, ky, kw, kh) in kept:
            ix = max(0, min(bx + bw, kx + kw) - max(bx, kx))
            iy = max(0, min(by + bh, ky + kh) - max(by, ky))
            inter = ix * iy
            if inter and inter / float(bw * bh + kw * kh - inter) > 0.5:
                dup = True
                break
        if not dup:
            kept.append(b)
    return kept


def _line_count(boxes):
    """Group boxes into lines by vertical overlap.

    Two glyphs belong to the same line when their vertical extents overlap by
    at least half the shorter one - the standard cheap substitute for a layout
    analyser, and enough to tell a one-line title from a three-line one.
    """
    if not boxes:
        return 0
    lines = []
    for (x, y, w, h) in sorted(boxes, key=lambda b: b[1]):
        placed = False
        for ln in lines:
            ov = max(0, min(y + h, ln[1]) - max(y, ln[0]))
            if ov >= 0.5 * min(h, ln[1] - ln[0]):
                ln[0] = min(ln[0], y)
                ln[1] = max(ln[1], y + h)
                placed = True
                break
        if not placed:
            lines.append([y, y + h])
    return len(lines)


def _palette(rgb, n_colours=5, stride=37):
    """K-means palette in Lab, returned as sRGB plus each colour's share.

    Lab rather than sRGB because k-means minimises Euclidean distance and only
    in Lab does that distance approximate what the eye calls "a different
    colour". Every 37th pixel (a prime, so it cannot align with any row or tile
    period) keeps the fit fast and deterministic.
    """
    import warnings
    from sklearn.cluster import KMeans
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float64)
    sample = lab[::stride]
    if sample.shape[0] < n_colours:
        sample = lab
    real = np.column_stack([sample[:, 0] * (100.0 / 255.0),
                            sample[:, 1] - 128.0,
                            sample[:, 2] - 128.0])
    # A frame with fewer than five distinct colours (a flat card, a solid
    # background) makes KMeans emit ConvergenceWarning. That case is real and
    # handled correctly - the empty clusters simply get a 0.0 share - so the
    # warning is noise that would print per image across a whole harvest.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        km = KMeans(n_clusters=n_colours, n_init=4, random_state=0).fit(real)
    labels = km.labels_
    centres = km.cluster_centers_
    counts = np.bincount(labels, minlength=n_colours).astype(np.float64)
    order = np.argsort(-counts)
    centres = centres[order]
    fracs = counts[order] / max(1.0, counts.sum())
    enc = np.zeros((1, n_colours, 3), np.uint8)
    enc[0, :, 0] = np.clip(centres[:, 0] * 255.0 / 100.0, 0, 255)
    enc[0, :, 1] = np.clip(centres[:, 1] + 128.0, 0, 255)
    enc[0, :, 2] = np.clip(centres[:, 2] + 128.0, 0, 255)
    srgb = cv2.cvtColor(enc, cv2.COLOR_LAB2RGB)[0]
    # deltaE over OCCUPIED clusters only. MEASURED 2026-08-30 on a synthetic
    # half-red / half-blue frame: KMeans parks the three unused centres on top
    # of the red one, and averaging all ten pairwise distances returned
    # palette_mean_deltaE 70.5 when the only real distance in that image is
    # 176.3. The old figure averaged seven pairs of colours no pixel belongs to.
    # Fewer than two occupied clusters means there are no pairs at all, which is
    # 0.0 - a real count of zero, not a missing value.
    occupied = [i for i in range(n_colours) if fracs[i] > 0.0]
    d = []
    for ai in range(len(occupied)):
        for bi in range(ai + 1, len(occupied)):
            d.append(float(np.linalg.norm(centres[occupied[ai]] -
                                          centres[occupied[bi]])))
    return srgb, fracs, (float(np.mean(d)) if d else 0.0), (float(np.max(d)) if d else 0.0)


def _cct_kelvin(rgb):
    """Correlated colour temperature of the frame's average colour.

    Mean linear sRGB -> CIE XYZ (D65 matrix) -> xy -> McCamy's cubic. Clamped
    to 1500-25000 K because McCamy's approximation diverges badly outside the
    Planckian locus and an unclamped 200000 K would read as a measurement.
    """
    m = rgb.reshape(-1, 3).astype(np.float64).mean(axis=0) / 255.0
    lin = np.where(m <= 0.04045, m / 12.92, ((m + 0.055) / 1.055) ** 2.4)
    X = 0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]
    Y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    Z = 0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]
    s = X + Y + Z
    if s < _EPS:
        return 6500.0
    x, y = X / s, Y / s
    if abs(0.1858 - y) < 1e-6:
        return 6500.0
    n = (x - 0.3320) / (0.1858 - y)
    cct = 449.0 * n ** 3 + 3525.0 * n ** 2 + 6823.3 * n + 5520.33
    return float(min(25000.0, max(1500.0, cct)))


def _face_boxes_px(faces, w, h):
    """thumb_metrics face dicts -> integer pixel boxes in the passed frame."""
    out = []
    for f in faces:
        bw, bh = float(f["bw"]), float(f["bh"])
        x0 = int(round(f["cx"] * w - bw / 2.0))
        y0 = int(round(f["cy"] * h - bh / 2.0))
        out.append((x0, y0, int(round(bw)), int(round(bh))))
    return out


def _usable_faces(faces, w, h):
    """Drop face dicts whose box does not intersect the w x h frame.

    A detector box can be centred outside the frame, or be given by a caller
    building face dicts by hand. Such a box paints nothing into the subject
    mask, and the old code then reported face_count > 0 with an all-NaN set of
    subject-vs-background keys - which makes the module's own "NaN means no
    face" contract false exactly where a downstream module trusts it. Dropping
    the box instead keeps face_count and the NaN set describing the same thing.

    Also drops non-positive boxes, which cannot be measured at all.
    """
    out = []
    for f in faces:
        try:
            bw, bh = float(f["bw"]), float(f["bh"])
            cx, cy = float(f["cx"]), float(f["cy"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (bw > 0.0 and bh > 0.0):
            continue
        if not (math.isfinite(cx) and math.isfinite(cy)):
            continue
        x0 = cx * w - bw / 2.0
        y0 = cy * h - bh / 2.0
        # Half-open overlap with [0, w) x [0, h), computed in float before the
        # int rounding _face_boxes_px does, so a box that rounds to zero width
        # at the frame edge is dropped here rather than surviving as an empty
        # rectangle.
        if min(w, x0 + bw) - max(0.0, x0) < 1.0:
            continue
        if min(h, y0 + bh) - max(0.0, y0) < 1.0:
            continue
        out.append(f)
    return out


def _mask_from_boxes(boxes, w, h, pad=0.0):
    m = np.zeros((h, w), np.uint8)
    for (x, y, bw, bh) in boxes:
        px, py = int(bw * pad), int(bh * pad)
        cv2.rectangle(m, (max(0, x - px), max(0, y - py)),
                      (min(w - 1, x + bw + px), min(h - 1, y + bh + py)),
                      255, -1)
    return m


_THIRDS = [(1 / 3.0, 1 / 3.0), (2 / 3.0, 1 / 3.0), (1 / 3.0, 2 / 3.0), (2 / 3.0, 2 / 3.0)]
# The farthest any point in the unit square can be from the nearest thirds
# intersection is the corner, sqrt(2)/3.
_THIRDS_MAX = math.sqrt(2.0) / 3.0


def _thirds_dist(x, y):
    return min(math.hypot(x - tx, y - ty) for tx, ty in _THIRDS)


# ------------------------------------------------------------------- I/O
def load_rgb(path):
    """Read an image as contiguous RGB uint8, plus its source metadata.

    cv2.imdecode over np.fromfile, NOT cv2.imread: imread silently returns None
    for any path containing non-ASCII characters on Windows, and candidate paths
    are whatever Nathan drags in. The .copy() makes the array contiguous because
    thumb_metrics indexes it directly.
    """
    path = str(path).replace("\\", "/")
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        raise IOError("empty or unreadable file: %s" % path)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise IOError("not a decodable image: %s" % path)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).copy()
    h, w = rgb.shape[:2]

    qsum = 0.0
    if _PILImage is not None:
        try:
            with _PILImage.open(path) as im:
                q = getattr(im, "quantization", None)
                if q and 0 in q:
                    qsum = float(sum(q[0]))
        except Exception:
            qsum = 0.0  # non-JPEG or unreadable table; 0.0 means "not a JPEG"

    meta = {
        "src_width_px": int(w),
        "src_height_px": int(h),
        "src_bytes": int(data.size),
        "image_sha1": hashlib.sha1(data.tobytes()).hexdigest(),
        "jpeg_qsum_luma": qsum,
    }
    return rgb, meta


def deletterbox(rgb, target_aspect=16.0 / 9.0, tol=0.02):
    """Crop symmetric letterbox bars using aspect arithmetic only.

    Deliberately NOT content-based. A legitimately dark court thumbnail must
    never be eaten by a darkness detector, and the YouTube variants' bar heights
    are fixed geometry anyway: hqdefault.jpg is 480x360 with black bars,
    sddefault.jpg is 640x480 with black bars, while maxresdefault, hq720 and
    mqdefault are native 16:9 with none.

    Refuses to remove more than MAX_LETTERBOX_FRAC of the frame. Past that the
    input is not a letterboxed 16:9 thumbnail, it is a different shape, and
    cropping it would throw the picture away under a name that claims black bars
    were removed.

    Returns (cropped, fraction of original rows or columns removed). That
    fraction is what the slice actually drops, h - keep_h, NOT 2 * bar: when
    h - keep_h is odd the odd row comes off the bottom, and 2 * bar under-stated
    the crop by one row (measured: a 361-row frame reported 0.2493 for a crop
    that removed 0.2521).
    """
    h, w = rgb.shape[:2]
    if h == 0 or w == 0:
        return rgb, 0.0
    aspect = w / float(h)
    if abs(aspect - target_aspect) <= tol:
        return rgb, 0.0
    if aspect < target_aspect:
        # Too tall: bars top and bottom.
        keep_h = int(round(w / target_aspect))
        bar = (h - keep_h) // 2
        if bar <= 0 or keep_h <= 0:
            return rgb, 0.0
        frac = float(h - keep_h) / float(h)
        if frac > MAX_LETTERBOX_FRAC:
            return rgb, 0.0
        return rgb[bar:bar + keep_h, :].copy(), frac
    # Too wide: pillars left and right.
    keep_w = int(round(h * target_aspect))
    bar = (w - keep_w) // 2
    if bar <= 0 or keep_w <= 0:
        return rgb, 0.0
    frac = float(w - keep_w) / float(w)
    if frac > MAX_LETTERBOX_FRAC:
        return rgb, 0.0
    return rgb[:, bar:bar + keep_w].copy(), frac


# --------------------------------------------------------------- the core
def measure_image(rgb, faces=None, source_kind="local", src_meta=None):
    """Measure one de-letterboxed RGB frame into exactly the 133 FEATURE_KEYS.

    `rgb` is the native-resolution, already de-letterboxed array. It is resized
    to 1280x720 with INTER_AREA once and that canonical array is reused for
    everything except the tm_ carry-through keys, which thumb_metrics documents
    as native-resolution measurements.

    Pass `faces` (canonical-frame face dicts) to avoid re-detecting.
    """
    src_meta = dict(src_meta or {})
    h_native, w_native = rgb.shape[:2]
    canon = cv2.resize(rgb, (CANON_W, CANON_H), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(canon, cv2.COLOR_RGB2GRAY)
    grayf = gray.astype(np.float32)
    lab = cv2.cvtColor(canon, cv2.COLOR_RGB2LAB)
    hsv = cv2.cvtColor(canon, cv2.COLOR_RGB2HSV)
    L = lab[:, :, 0].astype(np.float32) * (100.0 / 255.0)
    A = lab[:, :, 1].astype(np.float32) - 128.0
    B = lab[:, :, 2].astype(np.float32) - 128.0
    S = hsv[:, :, 1].astype(np.float32) / 255.0
    HUE = hsv[:, :, 0].astype(np.float32) * 2.0  # cv2 packs 0-179 into uint8

    if faces is None:
        faces = thumb_metrics.detect_faces(canon, YUNET)
    faces = _usable_faces(faces, CANON_W, CANON_H)

    row = {}

    # ------------------------------------------------------- provenance
    row["src_width_px"] = float(src_meta.get("src_width_px", w_native))
    row["src_height_px"] = float(src_meta.get("src_height_px", h_native))
    row["src_aspect"] = _safe_div(row["src_width_px"], row["src_height_px"], 0.0)
    row["src_bytes"] = float(src_meta.get("src_bytes", 0.0))
    row["jpeg_qsum_luma"] = float(src_meta.get("jpeg_qsum_luma", 0.0))
    row["letterbox_frac"] = float(src_meta.get("letterbox_frac", 0.0))
    row["source_kind_code"] = float(SOURCE_KIND_CODE.get(source_kind, 0))

    # ------------------------------------------------------------ faces
    frame_area = float(CANON_W * CANON_H)
    frame_diag = math.hypot(CANON_W, CANON_H)
    boxes = _face_boxes_px(faces, CANON_W, CANON_H)
    n_faces = len(faces)
    row["face_count"] = float(n_faces)
    areas = [float(f["bw"]) * float(f["bh"]) / frame_area for f in faces]
    row["face_area_frac_total"] = float(sum(areas)) if areas else 0.0

    if n_faces == 0:
        for k in ("face_area_frac_largest", "face_largest_cx", "face_largest_cy",
                  "face_largest_w_frac", "face_largest_h_frac",
                  "face_largest_score", "face_largest_diag_frac",
                  "face_area_frac_mean", "face_centroid_x", "face_centroid_y",
                  "face_spread", "face_largest_L_median", "face_thirds_dist",
                  "face_edge_margin_min", "face_subject_offset_x"):
            row[k] = float("nan")
        face_mask = np.zeros((CANON_H, CANON_W), np.uint8)
    else:
        big = faces[0]  # thumb_metrics.detect_faces sorts largest first
        bw, bh = float(big["bw"]), float(big["bh"])
        row["face_area_frac_largest"] = bw * bh / frame_area
        row["face_largest_cx"] = float(big["cx"])
        row["face_largest_cy"] = float(big["cy"])
        row["face_largest_w_frac"] = bw / CANON_W
        row["face_largest_h_frac"] = bh / CANON_H
        row["face_largest_score"] = float(big.get("score", float("nan")))
        row["face_largest_diag_frac"] = math.hypot(bw, bh) / frame_diag
        row["face_area_frac_mean"] = float(np.mean(areas))
        cxs = np.array([f["cx"] for f in faces], dtype=np.float64)
        cys = np.array([f["cy"] for f in faces], dtype=np.float64)
        row["face_centroid_x"] = float(cxs.mean())
        row["face_centroid_y"] = float(cys.mean())
        # RMS distance from the group centroid, in frame widths. 0 for one face.
        row["face_spread"] = float(np.sqrt(np.mean(
            (cxs - cxs.mean()) ** 2 + (cys - cys.mean()) ** 2)))
        x0, y0, w0, h0 = boxes[0]
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(CANON_W, x0 + w0), min(CANON_H, y0 + h0)
        # _usable_faces guarantees a non-empty clipped box, so the else is
        # unreachable defence rather than a real NaN source. It stays because a
        # future caller passing hand-built face dicts straight to measure_image
        # would otherwise get an IndexError instead of a row.
        if sx1 > sx0 and sy1 > sy0:
            row["face_largest_L_median"] = float(np.median(L[sy0:sy1, sx0:sx1]))
        else:
            row["face_largest_L_median"] = float(np.median(L))
        row["face_thirds_dist"] = _thirds_dist(float(big["cx"]), float(big["cy"]))
        margins = []
        for (bx, by, bbw, bbh) in boxes:
            margins.append(min(bx / float(CANON_W),
                               by / float(CANON_H),
                               (CANON_W - (bx + bbw)) / float(CANON_W),
                               (CANON_H - (by + bbh)) / float(CANON_H)))
        row["face_edge_margin_min"] = float(min(margins))
        row["face_subject_offset_x"] = float(big["cx"]) - 0.5
        face_mask = _mask_from_boxes(boxes, CANON_W, CANON_H, pad=0.0)

    fm_bool = face_mask > 0
    bg_bool = ~fm_bool
    # n_faces > 0 now implies fm_bool.any() (see _usable_faces). bg_bool can
    # still be empty when a face box covers the whole frame; that is a real
    # measurement of "no background to contrast against", handled as 0.0 at each
    # use below, NOT as NaN - NaN there would mean "no face", which is false.
    has_face = n_faces > 0
    has_bg = bool(bg_bool.any())

    # -------------------------------------------------------- luminance
    Lf = L.ravel()
    p05, p50, p95 = np.percentile(Lf, [5, 50, 95])
    row["lum_mean"] = float(Lf.mean())
    row["lum_median"] = float(p50)
    row["lum_std"] = float(Lf.std())
    row["lum_p05"] = float(p05)
    row["lum_p95"] = float(p95)
    row["lum_range"] = float(p95 - p05)
    # RMS contrast in its usual form: the standard deviation of intensity
    # normalised to 0-1.
    row["lum_rms_contrast"] = float((Lf / 100.0).std())
    row["lum_michelson"] = _michelson(Lf)
    # 25 and 75 L* are chosen band edges, not measured cutoffs: they are the
    # conventional shadow/midtone/highlight split on a 0-100 lightness scale.
    row["lum_dark_frac"] = float((Lf < 25.0).mean())
    row["lum_mid_frac"] = float(((Lf >= 25.0) & (Lf < 75.0)).mean())
    row["lum_bright_frac"] = float((Lf >= 75.0).mean())
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    row["lum_entropy"] = _entropy_bits(hist)
    row["lum_clip_low_frac"] = float((gray <= 2).mean())
    row["lum_clip_high_frac"] = float((gray >= 253).mean())
    row["subject_bg_lum_contrast"] = (
        abs(float(L[fm_bool].mean()) - float(L[bg_bool].mean())) / 100.0
        if (has_face and has_bg) else (0.0 if has_face else float("nan")))

    # ----------------------------------------------------------- colour
    Sf = S.ravel()
    row["sat_mean"] = float(Sf.mean())
    row["sat_median"] = float(np.median(Sf))
    row["sat_std"] = float(Sf.std())
    row["sat_p90"] = float(np.percentile(Sf, 90))
    row["sat_high_frac"] = float((Sf > 0.5).mean())
    chroma = np.sqrt(A * A + B * B)
    row["chroma_mean"] = float(chroma.mean())
    row["chroma_p90"] = float(np.percentile(chroma, 90))
    row["colourfulness"] = _colourfulness(canon)

    wsum = float(Sf.sum())
    hue_flat = HUE.ravel()
    if wsum > _EPS:
        bins = np.clip((hue_flat / _HUE_BIN_DEG).astype(np.int32), 0, _HUE_BINS - 1)
        hh = np.bincount(bins, weights=Sf, minlength=_HUE_BINS)
        hh_norm = hh / hh.sum()
        order = np.argsort(-hh_norm)
        row["hue_entropy"] = _entropy_bits(hh)
        row["hue_dominant_deg"] = float(order[0] * _HUE_BIN_DEG + _HUE_BIN_DEG / 2.0)
        row["hue_dominant_frac"] = float(hh_norm[order[0]])
        # A single-hue frame has no second hue. argsort then hands back the
        # lowest-indexed EMPTY bin, and reporting its centre angle as
        # hue_second_deg states a hue that no pixel in the frame has (measured:
        # a flat red frame reported hue_second_deg 15 at frac 0.000). When the
        # second bin carries no weight the angle is 0.0, matching the same
        # "nothing to measure" convention the no-chroma branch below uses.
        row["hue_second_frac"] = float(hh_norm[order[1]])
        row["hue_second_deg"] = (
            float(order[1] * _HUE_BIN_DEG + _HUE_BIN_DEG / 2.0)
            if row["hue_second_frac"] > 0.0 else 0.0)
        th = np.deg2rad(hue_flat)
        R = math.hypot(float((Sf * np.cos(th)).sum()), float((Sf * np.sin(th)).sum()))
        row["hue_circvar"] = float(1.0 - R / wsum)
    else:
        # A frame with no chroma at all has no hue to describe. These are
        # "nothing to measure" defaults, not measurements.
        row["hue_entropy"] = 0.0
        row["hue_dominant_deg"] = 0.0
        row["hue_dominant_frac"] = 0.0
        row["hue_second_deg"] = 0.0
        row["hue_second_frac"] = 0.0
        row["hue_circvar"] = 0.0

    # Only pixels with real chroma get a hue verdict; below S 0.15 the hue angle
    # of a near-grey pixel is numerically unstable and means nothing.
    colourful = S >= 0.15
    warm = colourful & ((HUE < 90.0) | (HUE >= 330.0))
    cool = colourful & (HUE >= 90.0) & (HUE < 330.0)
    row["warm_frac"] = float(warm.mean())
    row["cool_frac"] = float(cool.mean())
    row["warm_cool_ratio"] = float(min(1000.0, _safe_div(
        row["warm_frac"], row["cool_frac"], 1000.0 if row["warm_frac"] > 0 else 0.0)))
    row["cct_kelvin"] = _cct_kelvin(canon)
    row["lab_a_mean"] = float(A.mean())
    row["lab_b_mean"] = float(B.mean())

    # Skin range in YCrCb. This is the widely-published Chai & Ngan rule, cited
    # as a convention adopted here - it was NOT derived on this machine, and it
    # over-reports on warm wood and orange graphics, which a courtroom has.
    ycrcb = cv2.cvtColor(canon, cv2.COLOR_RGB2YCrCb)
    cr = ycrcb[:, :, 1].astype(np.int32)
    cb = ycrcb[:, :, 2].astype(np.int32)
    row["skin_frac"] = float(((cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127)).mean())

    if has_face and not has_bg:
        # Face box covers the entire frame: there is no background, so both
        # subject-vs-background colour keys are a measured 0.0.
        row["subject_bg_sat_contrast"] = 0.0
        row["subject_bg_hue_dist"] = 0.0
    elif has_face:
        row["subject_bg_sat_contrast"] = abs(float(S[fm_bool].mean()) -
                                             float(S[bg_bool].mean()))
        hf_face = HUE[fm_bool]
        hf_bg = HUE[bg_bool]
        wf = S[fm_bool]
        wb = S[bg_bool]
        if float(wf.sum()) > _EPS and float(wb.sum()) > _EPS:
            af = math.atan2(float((wf * np.sin(np.deg2rad(hf_face))).sum()),
                            float((wf * np.cos(np.deg2rad(hf_face))).sum()))
            ab = math.atan2(float((wb * np.sin(np.deg2rad(hf_bg))).sum()),
                            float((wb * np.cos(np.deg2rad(hf_bg))).sum()))
            d = abs(math.degrees(af - ab)) % 360.0
            row["subject_bg_hue_dist"] = float(min(d, 360.0 - d))
        else:
            row["subject_bg_hue_dist"] = 0.0
    else:
        row["subject_bg_sat_contrast"] = float("nan")
        row["subject_bg_hue_dist"] = float("nan")

    # ---------------------------------------------------------- palette
    pal_rgb, pal_frac, pal_mean_de, pal_max_de = _palette(canon)
    for i in range(5):
        row["palette_%d_r" % (i + 1)] = float(pal_rgb[i][0])
        row["palette_%d_g" % (i + 1)] = float(pal_rgb[i][1])
        row["palette_%d_b" % (i + 1)] = float(pal_rgb[i][2])
        row["palette_%d_frac" % (i + 1)] = float(pal_frac[i])
    row["palette_top1_frac"] = float(pal_frac[0])
    row["palette_top3_frac"] = float(pal_frac[:3].sum())
    row["palette_mean_deltaE"] = pal_mean_de
    row["palette_max_deltaE"] = pal_max_de

    # ------------------------------------------------------ edge/detail
    edges = cv2.Canny(gray, _CANNY_LO, _CANNY_HI)
    row["edge_density"] = float((edges > 0).mean())
    gx = cv2.Sobel(grayf, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(grayf, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    row["grad_mean"] = float(mag.mean())
    row["grad_p90"] = float(np.percentile(mag, 90))
    row["laplacian_var"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    hp = grayf - cv2.GaussianBlur(grayf, (0, 0), 1.2)
    row["hf_energy"] = float(np.abs(hp).mean())

    tile = 40  # same tile size thumb_metrics uses, so tile talk means one thing
    e01 = (edges > 0).astype(np.float32)
    tiles = e01.reshape(CANON_H // tile, tile, CANON_W // tile, tile).mean(axis=(1, 3))
    row["busyness_tile_std"] = float(tiles.std())
    # A tile more than 10% edge pixels is "busy". A chosen convention, not a
    # measured cutoff - it is only ever used as a relative comparison.
    row["clutter_index"] = float((tiles > 0.10).mean())
    activity = cv2.GaussianBlur(mag, (0, 0), 12.0)
    # 6.0 on a 0-255 gradient scale is a chosen "visually quiet" level.
    row["negative_space_frac"] = float((activity < 6.0).mean())

    if has_face:
        # padded.any() is guaranteed by _usable_faces; (~padded).any() is not -
        # a 35%-padded box can swallow the frame, and that is "no background
        # left to be blurrier than the face", a measured 0.0.
        padded = _mask_from_boxes(boxes, CANON_W, CANON_H, pad=0.35) > 0
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        v_in = float(lap[padded].var()) if padded.any() else 0.0
        v_out = float(lap[~padded].var()) if (~padded).any() else 0.0
        row["bg_blur_ratio"] = float(min(50.0, _safe_div(v_out, v_in, 0.0)))
    else:
        row["bg_blur_ratio"] = float("nan")

    # ------------------------------------------------------------ focal
    foc = _focal_stats(canon)
    sal = foc.pop("_sal")
    for k, v in foc.items():
        row[k] = float(v)
    row["focal_count"] = float(foc["focal_count"])

    # ------------------------------------------------------------- text
    tboxes = _text_boxes(gray)
    row["text_box_count"] = float(len(tboxes))
    if tboxes:
        tmask = _mask_from_boxes(tboxes, CANON_W, CANON_H, pad=0.0)
        tb = tmask > 0
        row["text_area_frac"] = float(tb.mean())
        row["text_largest_box_frac"] = float(max(w * h for _, _, w, h in tboxes) / frame_area)
        heights = np.array([h for _, _, _, h in tboxes], dtype=np.float64) / CANON_H
        row["text_mean_height_frac"] = float(heights.mean())
        row["text_max_height_frac"] = float(heights.max())
        wts = np.array([w * h for _, _, w, h in tboxes], dtype=np.float64)
        cxs = np.array([x + w / 2.0 for x, _, w, _ in tboxes]) / CANON_W
        cys = np.array([y + h / 2.0 for _, y, _, h in tboxes]) / CANON_H
        row["text_centroid_x"] = float((cxs * wts).sum() / wts.sum())
        row["text_centroid_y"] = float((cys * wts).sum() / wts.sum())
        ring = (cv2.dilate(tmask, np.ones((25, 25), np.uint8)) > 0) & (~tb)
        if ring.any():
            row["text_contrast"] = abs(float(np.median(L[tb])) -
                                       float(np.median(L[ring]))) / 100.0
        else:
            row["text_contrast"] = 0.0
        row["text_line_count_est"] = float(_line_count(tboxes))
        row["text_overlaps_face_frac"] = (float((tb & fm_bool).sum()) /
                                          max(1.0, float(tb.sum()))) if n_faces else float("nan")
        row["survive_text_px_210"] = float(row["text_max_height_frac"] * PREVIEW_H)
    else:
        row["text_area_frac"] = 0.0
        row["text_largest_box_frac"] = 0.0
        row["text_mean_height_frac"] = 0.0
        row["text_max_height_frac"] = 0.0
        row["text_centroid_x"] = 0.5
        row["text_centroid_y"] = 0.5
        row["text_contrast"] = 0.0
        row["text_line_count_est"] = 0.0
        row["text_overlaps_face_frac"] = 0.0 if n_faces else float("nan")
        row["survive_text_px_210"] = 0.0

    # -------------------------------------------------- downscale survival
    # The round trip models what a viewer's eye actually loses in a feed row:
    # down to 210x118 with INTER_AREA, back up to 1280x720 with INTER_LINEAR.
    small = cv2.resize(canon, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_AREA)
    back = cv2.resize(small, (CANON_W, CANON_H), interpolation=cv2.INTER_LINEAR)
    back_gray = cv2.cvtColor(back, cv2.COLOR_RGB2GRAY)
    row["survive_ssim_210"] = _ssim(grayf, back_gray.astype(np.float32))

    # survive_edge_ret_210 is the ABSOLUTE Canny edge density remaining after
    # the round trip, in canonical units - not the retained fraction.
    # MEASURED 2026-08-30 on three of Nathan's own files, which is why:
    #     file                    canonical   round-trip   ratio
    #     MONKEY_thumbnail        0.0468      0.0167       0.357
    #     MONKEY, softened 5x     0.0219      0.0124       0.566
    #     CARTHIEF_thumbnail      0.0362      0.0137       0.378
    #     CARTHIEF, softened 5x   0.0174      0.0112       0.643
    # The RATIO form goes UP when an image is made mushier, because a soft image
    # has little high frequency left to lose. It therefore rewards exactly the
    # defect it is supposed to catch, and is rejected. The absolute form falls
    # on every softened file, which is the behaviour "does detail survive at
    # feed size" requires.
    # NOTE for critique.py: its PRINCIPLES comment cites 0.125 for MONKEY. That
    # number matches none of the definitions above; against this implementation
    # MONKEY measures 0.0167, so that principle's threshold needs recalibrating
    # against real values rather than being taken across.
    row["survive_edge_ret_210"] = float(
        (cv2.Canny(back_gray, _CANNY_LO, _CANNY_HI) > 0).mean())

    row["survive_face_px_210"] = (float(row["face_largest_h_frac"] * PREVIEW_H)
                                  if n_faces else float("nan"))
    small_lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)
    row["survive_lum_michelson_210"] = _michelson(
        small_lab[:, :, 0].astype(np.float32) * (100.0 / 255.0))
    # A frame with no colourfulness to begin with (greyscale, a flat neutral
    # card) has none to lose, and the old 0.0 default read as "colour collapses
    # at feed size" - the opposite of the truth. 1.0 is "unchanged". The 0.5
    # floor is a chosen guard well below any real thumbnail: the twelve files in
    # READY-TO-POST measure colourfulness 47 to 113.
    row["survive_colourfulness_ratio_210"] = float(min(5.0, _safe_div(
        _colourfulness(small), row["colourfulness"], 0.0)
        if row["colourfulness"] > 0.5 else 1.0))
    row["survive_focal_count_210"] = float(_focal_stats(back)["focal_count"])

    # ------------------------------------------------------- composition
    # Visual weight = saliency times lightness: bright AND attention-grabbing.
    sal_full = cv2.resize(sal, (CANON_W, CANON_H), interpolation=cv2.INTER_LINEAR)
    weight = sal_full * (L / 100.0)
    total = float(weight.sum())
    if total < _EPS:
        weight = np.full_like(weight, 1.0 / weight.size)
        total = float(weight.sum())
    half_w, half_h = CANON_W // 2, CANON_H // 2
    left = float(weight[:, :half_w].sum())
    right = float(weight[:, half_w:].sum())
    top = float(weight[:half_h, :].sum())
    bottom = float(weight[half_h:, :].sum())
    # Sign convention, stated because the contract's prose and its formula
    # disagreed: this is (left - right) / total, so POSITIVE means left-heavy.
    row["balance_lr"] = float((left - right) / total)
    row["balance_tb"] = float((top - bottom) / total)
    xs = np.arange(CANON_W, dtype=np.float32) / (CANON_W - 1.0)
    ys = np.arange(CANON_H, dtype=np.float32) / (CANON_H - 1.0)
    cx = float((weight.sum(axis=0) * xs).sum() / total)
    cy = float((weight.sum(axis=1) * ys).sum() / total)
    row["mass_centroid_x"] = cx
    row["mass_centroid_y"] = cy
    row["thirds_alignment"] = float(1.0 - _thirds_dist(cx, cy) / _THIRDS_MAX)
    row["center_mass_frac"] = float(
        weight[CANON_H // 3:2 * CANON_H // 3, CANON_W // 3:2 * CANON_W // 3].sum() / total)
    a = grayf.ravel()
    b = np.fliplr(grayf).ravel()
    sa, sb = float(a.std()), float(b.std())
    row["symmetry_lr"] = float(np.corrcoef(a, b)[0, 1]) if sa > _EPS and sb > _EPS else 1.0
    quads = [weight[:half_h, :half_w].sum(), weight[:half_h, half_w:].sum(),
             weight[half_h:, :half_w].sum(), weight[half_h:, half_w:].sum()]
    row["quadrant_max_frac"] = float(max(quads) / total)

    # ------------------------------------------- thumb_metrics carry-through
    # Computed on the NATIVE array with NATIVE faces: thumb_metrics documents
    # subject_max_L as a native-resolution measurement, and re-deriving these at
    # canonical size would make them disagree with verify_thumb.py's own output
    # on the same file, which is the whole point of carrying them.
    # Native faces are RESCALED FROM THE CANONICAL SET, not detected a second
    # time. MEASURED 2026-08-30: on a 480x270 copy of 1_LONGFORM_thumbnail the
    # canonical pass found 4 faces and a second native pass found 3, and on
    # MONKEY_thumbnail 3 vs 2 - so tm_bg_mush, tm_bg_tiles and tm_subject_max_L
    # were computed against a face set the row never disclosed and that
    # contradicted its own face_count. Rescaling is exact: detect_faces returns
    # cx/cy already normalised to the array, and only bw/bh are in its pixels.
    # It also halves the YuNet cost per image and finally makes the documented
    # `faces=` argument mean what it says - the old code re-detected regardless.
    sx_native = w_native / float(CANON_W)
    sy_native = h_native / float(CANON_H)
    native_faces = [{"cx": f["cx"], "cy": f["cy"],
                     "bw": float(f["bw"]) * sx_native,
                     "bh": float(f["bh"]) * sy_native,
                     "score": float(f.get("score", 0.0))} for f in faces]
    tm_flat = thumb_metrics.flat_g_p90(rgb)
    tm_post = thumb_metrics.poster_fa(rgb)
    tm_mush = thumb_metrics.bg_mush(rgb, native_faces)
    tm_tiles = thumb_metrics.bg_tile_count(rgb, native_faces)
    tm_subL = thumb_metrics.subject_max_L(rgb, native_faces)
    # flat/poster/mush return NaN only when their tile denominator is empty
    # (every tile was masked as text or subject). That is "nothing measurable",
    # not a missing face, and these keys are not in NAN_WHEN_NO_FACE - so they
    # go to 0.0 and tm_bg_tiles carries the denominator so a reader can see it.
    row["tm_flat_g_p90"] = tm_flat if math.isfinite(tm_flat) else 0.0
    row["tm_poster_fa"] = tm_post if math.isfinite(tm_post) else 0.0
    row["tm_bg_mush"] = tm_mush if math.isfinite(tm_mush) else 0.0
    row["tm_bg_tiles"] = float(tm_tiles)
    row["tm_subject_max_L"] = float(tm_subL) if native_faces else float("nan")

    # ---------------------------------------------------------- coercion
    out = {}
    for k in FEATURE_KEYS:
        if k not in row:
            raise KeyError("measure_image did not produce %r" % k)
        out[k] = _f(row[k])
    return out


def measure_file(path, source_kind="local", thumb_quality="", faces=None):
    """Measure one file into FEATURE_KEYS + IDENTITY_KEYS.

    image_id is the filename stem, which makes it equal to the YouTube video_id
    for harvested thumbs. That equality IS the join key between harvest.jsonl
    and measurements.jsonl, and every downstream module depends on it.

    On any exception this returns a row with measure_error set and every
    FEATURE_KEY NaN rather than raising: one corrupt JPEG in a 60-video harvest
    must not kill the run. grammar.py and styles.py drop such rows.
    """
    path = str(path).replace("\\", "/")
    ident = {
        "image_id": os.path.splitext(os.path.basename(path))[0],
        "image_path": path,
        "image_sha1": "",
        "source_kind": source_kind,
        "thumb_quality": thumb_quality,
        "schema_version": SCHEMA_VERSION,
        "measured_utc": utc_now(),
        "measure_error": "",
    }
    try:
        rgb, meta = load_rgb(path)
        ident["image_sha1"] = meta["image_sha1"]
        cropped, lb = deletterbox(rgb)
        meta["letterbox_frac"] = lb
        feats = measure_image(cropped, faces=faces, source_kind=source_kind,
                              src_meta=meta)
    except Exception as exc:                     # noqa: BLE001 - deliberate
        feats = dict((k, float("nan")) for k in FEATURE_KEYS)
        ident["measure_error"] = "%s: %s" % (type(exc).__name__, exc)
    out = dict(feats)
    out.update(ident)
    return out


IMAGE_PATTERNS = ("*.jpg", "*.jpeg", "*.png", "*.webp")


def _file_sha1(path):
    """sha1 of a file's bytes, or "" if it cannot be read.

    Streamed in 1 MiB blocks so a stray large file cannot be loaded whole just
    to answer a cache question.
    """
    h = hashlib.sha1()
    try:
        with open(str(path), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def measure_folder(folder, out_jsonl=None, out_csv=None, pattern=IMAGE_PATTERNS,
                   source_kind="youtube", skip_existing=True, progress=True):
    """Measure every matching image in a folder.

    `pattern` may be one glob or a sequence of them; the default covers the
    extensions a thumbnail actually arrives as. It used to be "*.jpg" alone,
    which measured a folder of PNGs as zero files and called that success.

    A missing folder RAISES rather than returning an empty list. Measuring
    nothing is not a result, and the old silent [] let a typo'd path travel all
    the way to an empty grammar.

    skip_existing re-reads any existing out_jsonl and measures only new files.
    A cached row is reused only when its image_sha1 AND its schema_version still
    match - matching on the filename stem alone meant that re-exporting
    SANCHEZ_thumbnail.jpg over itself, which is Nathan's normal loop, silently
    returned the measurements of the file he had just replaced.

    progress prints to stderr - the engine showing its own state rather than
    sitting silent for two minutes.
    """
    folder = str(folder).replace("\\", "/")
    if not os.path.isdir(folder):
        raise FileNotFoundError("not a folder: %s" % folder)
    pats = (pattern,) if isinstance(pattern, str) else tuple(pattern)
    # glob.escape the DIRECTORY only. "D:/thumbs/dir[1]/x.jpg" matched nothing
    # at all before this, because [1] is a glob character class - a silent zero
    # on any path holding [ ] ? or *, which is a plausible Windows folder name.
    stem_dir = glob.escape(folder)
    hits = []
    for p in pats:
        hits.extend(glob.glob(stem_dir + "/" + p))
    files = sorted(set(f.replace("\\", "/") for f in hits))
    if not files:
        present = sorted(set(os.path.splitext(f)[1].lower()
                             for f in os.listdir(folder))) or ["(folder is empty)"]
        sys.stderr.write("WARNING %s: 0 files matched %s; folder holds %s\n"
                         % (folder, list(pats), ", ".join(present)))
        sys.stderr.flush()
        # Deliberately does NOT write out_jsonl. Overwriting a good
        # measurements.jsonl with nothing because a pattern was wrong is the
        # one outcome here that destroys work.
        return []
    existing = {}
    if skip_existing and out_jsonl and os.path.exists(str(out_jsonl)):
        for r in read_jsonl(out_jsonl, nan_keys=NAN_WHEN_NO_FACE):
            if (isinstance(r, dict) and r.get("image_id")
                    and r.get("schema_version") == SCHEMA_VERSION
                    and r.get("image_sha1")):
                existing[r["image_id"]] = r
    rows = []
    total = len(files)
    for i, f in enumerate(files, 1):
        stem = os.path.splitext(os.path.basename(f))[0]
        cached = existing.get(stem)
        if cached is not None and _file_sha1(f) == cached.get("image_sha1"):
            rows.append(cached)
            if progress:
                sys.stderr.write("%d/%d %s (cached)\n" % (i, total, stem))
            continue
        if progress:
            sys.stderr.write("%d/%d %s\n" % (i, total, stem))
            sys.stderr.flush()
        rows.append(measure_file(f, source_kind=source_kind))
    if out_jsonl:
        save_measurements(rows, out_jsonl, out_csv)
    return rows


def measure_niche(niche, source_kind="youtube"):
    """Measure <niche_dir>/thumbs into measurements.jsonl + measurements.csv.

    The pipeline entry point. measure_folder stays available for ad-hoc folders
    such as D:/Boyd Clips/READY-TO-POST.
    """
    started = utc_now()
    d = niche_dir(niche, create=True)
    jsonl = d + "/measurements.jsonl"
    csvp = d + "/measurements.csv"
    err = None
    rows = []
    try:
        rows = measure_folder(d + "/thumbs", out_jsonl=jsonl, out_csv=csvp,
                              source_kind=source_kind)
    except Exception as exc:                     # noqa: BLE001
        err = "%s: %s" % (type(exc).__name__, exc)
    run_manifest(niche, "measure",
                 {"source_kind": source_kind, "thumbs_dir": d + "/thumbs"},
                 {"n_measured": len(rows),
                  "n_errors": sum(1 for r in rows if r.get("measure_error"))},
                 started_utc=started, ok=(err is None), error=err)
    if err:
        raise RuntimeError(err)
    return rows


# ---------------------------------------------------------------- vectors
def feature_vector(row, keys=FEATURE_KEYS):
    """Pull keys in frozen order.

    Raises KeyError on a missing key - never substitutes 0.0, because a
    silently-zeroed feature would move a cluster centroid and nobody would ever
    see it.
    """
    return [float(row[k]) for k in keys]


def feature_matrix(rows, keys=FEATURE_KEYS):
    """Build the (n, k) matrix and the parallel list of image_ids.

    The only place a matrix is built, so styles.py and critique.py cannot
    disagree about column order. Does NOT impute: NaNs pass through for the
    caller to handle explicitly.
    """
    ids = [r.get("image_id", "") for r in rows]
    X = np.array([feature_vector(r, keys) for r in rows], dtype=np.float64) \
        if rows else np.zeros((0, len(keys)), dtype=np.float64)
    return X, ids


# ------------------------------------------------------------ persistence
def save_measurements(rows, jsonl_path, csv_path=None):
    """Validate every row against FEATURE_KEYS, then write JSONL (+ CSV).

    The validation is the guard that stops a mid-build FEATURE_KEYS edit by one
    module from corrupting a file three other modules read.
    """
    need = set(FEATURE_KEYS)
    for i, r in enumerate(rows):
        missing = need - set(r)
        if missing:
            raise KeyError("row %d (%s) is missing %d feature keys, first: %s"
                           % (i, r.get("image_id", "?"), len(missing),
                              sorted(missing)[0]))
    write_jsonl(jsonl_path, rows)
    if csv_path:
        cols = ["image_id"] + [k for k in IDENTITY_KEYS if k != "image_id"] + list(FEATURE_KEYS)
        write_csv(csv_path, rows, cols)
    return str(jsonl_path)


def load_measurements(path_or_niche):
    """Read measurements.jsonl. THE ONLY sanctioned reader.

    Accepts a direct .jsonl path or a niche name. Raises on a schema_version
    mismatch: scoring a candidate against rows built on a different vocabulary
    silently compares the wrong columns.

    Raises FileNotFoundError when the file is not there. read_jsonl returns []
    for a missing path, and passing that on meant "you have not run measure yet"
    and "this niche has no thumbnails" arrived at grammar.py as the same empty
    list - one is a mistake to fix, the other is a finding.
    """
    p = str(path_or_niche).replace("\\", "/")
    if not p.lower().endswith(".jsonl"):
        p = niche_dir(path_or_niche, create=False) + "/measurements.jsonl"
    if not os.path.exists(p):
        raise FileNotFoundError("no measurements at %s - run measure first" % p)
    rows = read_jsonl(p, nan_keys=NAN_WHEN_NO_FACE)
    for r in rows:
        sv = r.get("schema_version")
        if sv != SCHEMA_VERSION:
            raise ValueError(
                "%s: schema_version %r but this build is %d - re-run measure"
                % (p, sv, SCHEMA_VERSION))
    return rows


# ------------------------------------------------------------------- CLI
_TABLE_COLS = (
    ("faces", "face_count", "%5.0f"),
    ("face%", "face_area_frac_largest", "%6.3f"),
    ("lumM", "lum_mean", "%6.1f"),
    ("mich", "lum_michelson", "%6.3f"),
    ("colr", "colourfulness", "%6.1f"),
    ("edge", "edge_density", "%6.4f"),
    ("edge210", "survive_edge_ret_210", "%8.4f"),
    ("ssim", "survive_ssim_210", "%6.3f"),
    ("facepx", "survive_face_px_210", "%7.1f"),
    ("txtpx", "survive_text_px_210", "%6.1f"),
    ("txtN", "text_box_count", "%5.0f"),
    ("focal", "focal_count", "%6.0f"),
    ("conc", "focal_concentration", "%6.3f"),
    ("neg%", "negative_space_frac", "%6.3f"),
    ("flatG", "tm_flat_g_p90", "%6.3f"),
    ("subjL", "tm_subject_max_L", "%6.1f"),
)


def render_table(rows):
    """Fixed-width table of the columns worth eyeballing."""
    name_w = max([12] + [len(r.get("image_id", "")) for r in rows])
    head = "%-*s" % (name_w, "image") + "".join(
        "%*s" % (int(fmt[1:].split(".")[0]) + 1, lbl) for lbl, _, fmt in _TABLE_COLS)
    lines = [head, "-" * len(head)]
    for r in rows:
        cells = []
        for _lbl, key, fmt in _TABLE_COLS:
            v = r.get(key, float("nan"))
            # int, not just float: a row round-tripped through JSON by another
            # writer can carry 4 where this module wrote 4.0, and the old
            # float-only test printed a dash over a number that was really there.
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) \
                and math.isfinite(v)
            cells.append(" " + (fmt % v if ok
                                else "%*s" % (int(fmt[1:].split(".")[0]), "-")))
        lines.append("%-*s" % (name_w, r.get("image_id", "?")) + "".join(cells))
    return "\n".join(lines)


SAMPLE_DIR = os.environ.get("THUMBENG_SAMPLE_DIR", "D:/Boyd Clips/READY-TO-POST")


def _synthetic_sample(tmpdir):
    """Write three deterministic frames so the selftest can never test nothing.

    Not a substitute for real thumbnails - they carry no faces and no real
    typography - but every structural invariant (key set, NaN policy, writers,
    matrix shape) is exercised by them, and that is what must not go unchecked
    just because the D: drive is not mounted.
    """
    os.makedirs(tmpdir, exist_ok=True)
    rs = np.random.RandomState(20260830)
    out = []
    frames = {
        # Structured, so edges and text-like boxes actually exist.
        "synthetic_blocks": None,
        "synthetic_noise": (rs.rand(720, 1280, 3) * 255).astype(np.uint8),
        "synthetic_flat": np.full((720, 1280, 3), 40, np.uint8),
    }
    blocks = np.zeros((720, 1280, 3), np.uint8)
    blocks[:, :426] = (200, 40, 30)
    blocks[:, 426:853] = (30, 30, 30)
    blocks[:, 853:] = (240, 220, 20)
    for y in range(120, 600, 96):
        cv2.rectangle(blocks, (500, y), (760, y + 48), (255, 255, 255), -1)
    frames["synthetic_blocks"] = blocks
    for name, arr in frames.items():
        p = tmpdir + "/" + name + ".jpg"
        cv2.imwrite(p, cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        out.append(p)
    return sorted(out)


def selftest(folder=None):
    """Measure the sample thumbnails and check the invariants.

    A checker that cannot fail is worse than no checker, so the substantive
    checks are constructed to fail if the code is wrong:
      * the letterbox check builds a bar-padded copy and requires the crop to
        recover the original lum_mean to within 1%
      * the downscale check builds a 5x-softened copy and requires less edge
        structure to survive to feed size
      * the NaN check requires every key outside NAN_WHEN_NO_FACE to be finite
      * the regression block at the end re-runs each defect fixed on 2026-08-30
        against a synthetic input that reproduced it

    It NEVER returns 0 without having run. The old version printed
    SELFTEST_SKIP and exited 0 when D: was not mounted, so a green selftest
    could mean "measured 12 files, all invariants hold" or "measured nothing" -
    and the caller could not tell which. With no real sample it now falls back
    to synthetic frames and says so in the output.
    """
    folder = str(folder or SAMPLE_DIR).replace("\\", "/")
    files = sorted(glob.glob(glob.escape(folder) + "/*.jpg")) if os.path.isdir(folder) else []
    synthetic = not files
    scratch = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "_selftest_tmp").replace("\\", "/")
    if synthetic:
        sys.stderr.write("no jpgs in %s - falling back to synthetic frames\n" % folder)
        files = _synthetic_sample(scratch)

    rows = []
    for i, f in enumerate(files, 1):
        sys.stderr.write("measuring %d/%d %s\n" % (i, len(files), os.path.basename(f)))
        sys.stderr.flush()
        rows.append(measure_file(f, source_kind="local"))
    print(render_table(rows))
    print("")

    checks = []
    checks.append(("no-measure-errors",
                   all(not r["measure_error"] for r in rows)))
    checks.append(("133-keys",
                   all(len(set(FEATURE_KEYS) - set(r)) == 0 for r in rows)
                   and len(FEATURE_KEYS) == 133))
    checks.append(("identity-keys",
                   all(len(set(IDENTITY_KEYS) - set(r)) == 0 for r in rows)))
    checks.append(("key-doc-complete",
                   all(k in KEY_DOC for k in FEATURE_KEYS)))

    # tm_subject_max_L is the single documented exception to "NaN only when
    # face_count == 0" - see the NaN POLICY block in the module docstring. It is
    # named here rather than folded into NAN_WHEN_NO_FACE so the exemption is
    # visible at the point the invariant is enforced.
    NAN_WITH_FACE_OK = frozenset(("tm_subject_max_L",))
    bad = []
    for r in rows:
        for k in FEATURE_KEYS:
            v = r[k]
            if not math.isfinite(v) and k not in NAN_WHEN_NO_FACE:
                bad.append((r["image_id"], k))
            if (not math.isfinite(v) and k in NAN_WHEN_NO_FACE
                    and r["face_count"] > 0 and k not in NAN_WITH_FACE_OK):
                bad.append((r["image_id"], k + "(has-face)"))
    checks.append(("finite-outside-nan-set", not bad))
    if bad:
        print("  non-finite where it must not be: %s" % bad[:8])

    checks.append(("plain-scalars",
                   all(type(r[k]) is float for r in rows for k in FEATURE_KEYS)))

    ref = files[0]
    rgb, meta = load_rgb(ref)
    base = measure_image(*deletterbox(rgb)[:1], src_meta=meta)
    # Synthetic letterbox: pad to 4:3 with black bars, exactly as hqdefault does.
    h, w = rgb.shape[:2]
    new_h = int(round(w * 3.0 / 4.0))
    bar = max(1, (new_h - h) // 2)
    boxed = np.zeros((h + 2 * bar, w, 3), np.uint8)
    boxed[bar:bar + h] = rgb
    crop, lb = deletterbox(boxed)
    fixed = measure_image(crop, src_meta=meta)
    drift = abs(fixed["lum_mean"] - base["lum_mean"]) / max(1e-6, base["lum_mean"])
    checks.append(("deletterbox-recovers-lum(%.4f, bars=%.3f)" % (drift, lb),
                   drift < 0.01 and lb > 0.05))

    # A 5x-downscaled-then-upscaled copy must carry less edge structure to
    # feed size than the original does.
    tiny = cv2.resize(rgb, (max(1, w // 5), max(1, h // 5)), interpolation=cv2.INTER_AREA)
    soft = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_LINEAR)
    soft_row = measure_image(soft, src_meta=meta)
    checks.append(("soft-copy-survives-less(%.4f<%.4f)"
                   % (soft_row["survive_edge_ret_210"], base["survive_edge_ret_210"]),
                   soft_row["survive_edge_ret_210"] < base["survive_edge_ret_210"]))

    # Round-trip through the writers and back, including the NaN restoration.
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest.jsonl")
    save_measurements(rows, tmp, tmp.replace(".jsonl", ".csv"))
    back = read_jsonl(tmp, nan_keys=NAN_WHEN_NO_FACE)
    same = (len(back) == len(rows) and
            all(abs(b["lum_mean"] - r["lum_mean"]) < 1e-9
                for b, r in zip(back, rows)))
    nan_ok = all((not math.isfinite(b[k])) == (not math.isfinite(r[k]))
                 for b, r in zip(back, rows) for k in NAN_WHEN_NO_FACE)
    checks.append(("jsonl-roundtrip", same and nan_ok))
    for p in (tmp, tmp.replace(".jsonl", ".csv")):
        try:
            os.remove(p)
        except OSError:
            pass

    # feature_matrix must not quietly reshape or reorder.
    X, ids = feature_matrix(rows)
    checks.append(("matrix-shape", X.shape == (len(rows), len(FEATURE_KEYS))
                   and ids == [r["image_id"] for r in rows]))

    # describe_key must fail loudly on a typo.
    try:
        describe_key("face_area_frac_larget")
        raised = False
    except KeyError:
        raised = True
    checks.append(("describe_key-raises-on-typo", raised))

    # ------------------------------------------------ regressions, 2026-08-30
    # Each of these reproduced a real defect before it was fixed. They are
    # cheap and synthetic on purpose: none of them needs the D: sample set.
    os.makedirs(scratch, exist_ok=True)

    # A frame that does not intersect the frame must not survive as a face, or
    # face_count > 0 coexists with an all-NaN subject-vs-background set.
    off = measure_image(np.full((CANON_H, CANON_W, 3), 90, np.uint8),
                        faces=[{"cx": -0.4, "cy": 0.5, "bw": 100.0,
                                "bh": 100.0, "score": 0.9}])
    checks.append(("offframe-face-dropped", off["face_count"] == 0.0))

    # A face box covering the whole frame is still a face; the keys that need a
    # background become 0.0, never NaN, because NaN there would say "no face".
    fullf = measure_image(np.full((CANON_H, CANON_W, 3), 90, np.uint8),
                          faces=[{"cx": 0.5, "cy": 0.5, "bw": 4000.0,
                                  "bh": 3000.0, "score": 0.9}])
    checks.append(("fullframe-face-not-nan",
                   fullf["face_count"] == 1.0
                   and all(math.isfinite(fullf[k]) for k in
                           ("subject_bg_lum_contrast", "subject_bg_sat_contrast",
                            "subject_bg_hue_dist", "bg_blur_ratio"))))

    # palette deltaE must describe only colours the image actually contains.
    two = np.zeros((CANON_H, CANON_W, 3), np.uint8)
    two[:, :CANON_W // 2] = (255, 0, 0)
    two[:, CANON_W // 2:] = (0, 0, 255)
    _srgb, pfr, pmean, pmax = _palette(two)
    n_occ = int((pfr > 0).sum())
    checks.append(("palette-deltaE-occupied-only(n=%d,mean=%.1f,max=%.1f)"
                   % (n_occ, pmean, pmax),
                   n_occ == 2 and abs(pmean - pmax) < 1e-6 and pmax > 100.0))

    # A greyscale frame has no colourfulness to lose. Reporting 0.0 said the
    # opposite; the honest ratio is 1.0.
    grey = np.dstack([np.tile(np.linspace(0, 255, CANON_W, dtype=np.uint8),
                              (CANON_H, 1))] * 3)
    checks.append(("greyscale-colour-ratio-1",
                   abs(measure_image(grey)["survive_colourfulness_ratio_210"] - 1.0) < 1e-9))

    # De-letterboxing must refuse to eat a frame that is simply a different
    # shape, and must report the rows it really removed.
    banner = np.full((10, 1000, 3), 120, np.uint8)
    _c, lb_banner = deletterbox(banner)
    odd = np.zeros((361, 480, 3), np.uint8)
    odd[45:315] = 200
    c_odd, lb_odd = deletterbox(odd)
    checks.append(("deletterbox-capped(banner=%.3f,odd=%.4f)" % (lb_banner, lb_odd),
                   lb_banner == 0.0
                   and abs(lb_odd - (361 - c_odd.shape[0]) / 361.0) < 1e-9))

    # A folder whose name holds a glob character must still be measured, and a
    # replaced file with the same name must NOT be served from cache.
    braced = scratch + "/dir[1]"
    os.makedirs(braced, exist_ok=True)
    cv2.imwrite(braced + "/a.jpg", np.full((720, 1280, 3), 60, np.uint8))
    n_braced = len(measure_folder(braced, progress=False, skip_existing=False))
    cache_jsonl = scratch + "/cache.jsonl"
    cachedir = scratch + "/cache"
    os.makedirs(cachedir, exist_ok=True)
    cv2.imwrite(cachedir + "/same.jpg", np.full((720, 1280, 3), 30, np.uint8))
    first = measure_folder(cachedir, out_jsonl=cache_jsonl, progress=False)
    cv2.imwrite(cachedir + "/same.jpg", np.full((720, 1280, 3), 200, np.uint8))
    second = measure_folder(cachedir, out_jsonl=cache_jsonl, progress=False)
    checks.append(("glob-and-sha1-cache(n=%d)" % n_braced,
                   n_braced == 1 and len(first) == 1 and len(second) == 1
                   and abs(second[0]["lum_mean"] - first[0]["lum_mean"]) > 1.0))

    # A missing folder and a missing measurements file are mistakes, not empty
    # results, and must raise.
    try:
        measure_folder(scratch + "/does-not-exist", progress=False)
        folder_raised = False
    except FileNotFoundError:
        folder_raised = True
    try:
        load_measurements(scratch + "/does-not-exist.jsonl")
        load_raised = False
    except FileNotFoundError:
        load_raised = True
    checks.append(("missing-inputs-raise", folder_raised and load_raised))

    # Corrupt, empty and absent files must come back as rows carrying
    # measure_error, never as an exception that kills a 60-video harvest.
    with open(scratch + "/corrupt.jpg", "wb") as fh:
        fh.write(b"this is not a jpeg")
    with open(scratch + "/empty.jpg", "wb"):
        pass
    bad_rows = [measure_file(scratch + "/corrupt.jpg"),
                measure_file(scratch + "/empty.jpg"),
                measure_file(scratch + "/absent.jpg")]
    checks.append(("bad-files-become-error-rows",
                   all(r["measure_error"] and
                       all(k in r for k in FEATURE_KEYS) for r in bad_rows)))

    # A 1x1 image is a legal input and must produce a full finite row.
    cv2.imwrite(scratch + "/onepx.png", np.full((1, 1, 3), 128, np.uint8))
    one = measure_file(scratch + "/onepx.png")
    checks.append(("1x1-image-measures",
                   not one["measure_error"]
                   and all(math.isfinite(one[k]) for k in FEATURE_KEYS
                           if k not in NAN_WHEN_NO_FACE)))

    # A wrong pattern must warn and return [], and must NOT overwrite a good
    # measurements file with nothing.
    before = os.path.getsize(cache_jsonl)
    empty_hit = measure_folder(cachedir, out_jsonl=cache_jsonl,
                               pattern="*.nosuchext", progress=False)
    checks.append(("no-match-does-not-truncate",
                   empty_hit == [] and os.path.getsize(cache_jsonl) == before))

    import shutil
    shutil.rmtree(scratch, ignore_errors=True)

    ok = all(c for _, c in checks)
    print(("SELFTEST_PASS  " if ok else "SELFTEST_FAIL  ") +
          "  ".join("%s=%s" % (n, "ok" if c else "BLIND") for n, c in checks))
    print("  measured %d %s files, %d features each"
          % (len(rows), "SYNTHETIC" if synthetic else "real", len(FEATURE_KEYS)))
    if synthetic:
        print("  WARNING: no real sample at %s - structural checks only, no"
              " faces or typography were exercised" % folder)
    return 0 if ok else 1


def main(argv=None):
    """CLI: IMG..., --folder DIR --out F.jsonl, --niche NAME, --selftest."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        i = argv.index("--selftest")
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        return selftest(nxt if (nxt and not nxt.startswith("-")) else None)

    def _opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    niche = _opt("--niche")
    folder = _opt("--folder")
    out = _opt("--out")
    source_kind = _opt("--source-kind", "local")

    if niche:
        rows = measure_niche(niche, source_kind=_opt("--source-kind", "youtube"))
        print(render_table(rows))
        return 0
    if folder:
        rows = measure_folder(folder, out_jsonl=out,
                              out_csv=(out.replace(".jsonl", ".csv") if out else None),
                              source_kind=source_kind)
        print(render_table(rows))
        return 0

    skip = {"--niche", "--folder", "--out", "--source-kind"}
    imgs = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in skip:
            i += 2
            continue
        if not a.startswith("-"):
            imgs.append(a)
        i += 1
    if not imgs:
        print(__doc__.strip().splitlines()[0])
        print("usage: measure.py IMG [IMG ...] | --folder DIR [--out F.jsonl]"
              " | --niche NAME | --selftest")
        return 2
    rows = [measure_file(p, source_kind=source_kind) for p in imgs]
    print(render_table(rows))
    for r in rows:
        if r["measure_error"]:
            print("  ERROR %s: %s" % (r["image_id"], r["measure_error"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
