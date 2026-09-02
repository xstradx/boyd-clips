# -*- coding: utf-8 -*-
"""styles.py - discover the recurring styles in a harvested niche by clustering
the measured feature vectors from measure.py.

sklearn only. torch is not on this interpreter and no neural embedding is
permitted anywhere in this engine.

WHY KMeans ON SCALED FEATURES rather than anything cleverer: with 40-120
thumbnails per niche and ~107 clustering dimensions, any method with more knobs
than KMeans is fitting noise. The scaling choice matters far more than the
algorithm - several features (laplacian_var, cct_kelvin, lum_entropy) have
ranges thousands of times larger than the fractions, and unscaled they would be
the only thing the distance metric ever sees.

RobustScaler, not StandardScaler: thumbnail feature distributions are heavily
skewed and contain genuine extremes (one blown-out white thumbnail, one nearly
black one). A mean/std scaler lets a single extreme squash everything else
toward zero; median/IQR does not. The fitted center and scale are SERIALISED
INTO styles.json so critique.py can place a candidate into the existing cluster
space without refitting on a population of one.

WHAT THIS MODULE MAY AND MAY NOT SAY. describe_cluster produces a DESCRIPTION -
what a cluster looks like. It never says whether a style works. Whether it works
is correlate_with_outliers' job, it is bounded by min_members, and below that
bound the answer is NaN rather than a number. With 16 thumbnails you cannot
conclude anything about a niche, and render_styles is required to print that
sentence rather than let a lift of 2.4x on three videos read as a finding.

WRITES styles.json ONLY. Reads via measure.load_measurements and
harvest.load_harvest - never opens those files directly.

    python -m tools.thumbeng.styles --niche court [--k 4]
    python -m tools.thumbeng.styles --folder "D:/Boyd Clips/READY-TO-POST"
    python -m tools.thumbeng.styles --selftest
"""

import os
import sys
import math
import glob
import argparse
import warnings

import numpy as np

# --- package import, working both as `-m tools.thumbeng.styles` and as a script
try:
    from . import (SCHEMA_VERSION, WORK_ROOT, niche_dir, utc_now, write_json,
                   read_json, run_manifest)
    from . import measure
except ImportError:                                     # direct script run
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _ROOT = os.path.dirname(os.path.dirname(_HERE))
    if _ROOT not in sys.path:
        sys.path.append(_ROOT)
    from tools.thumbeng import (SCHEMA_VERSION, WORK_ROOT, niche_dir, utc_now,
                                write_json, read_json, run_manifest)
    from tools.thumbeng import measure

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import RobustScaler


# --------------------------------------------------------------- feature space
#
# Each exclusion below carries its reason. A key excluded without a reason is a
# key someone will silently re-add.
#
NON_STYLE_KEYS = frozenset([
    # Thumbnail-quality artefacts, not design choices. A mqdefault fallback is
    # 320x180 and a maxresdefault is 1280x720; clustering on that would sort
    # the niche by which CDN variant answered, which is not a style.
    "src_width_px", "src_height_px", "src_aspect", "src_bytes",
    "jpeg_qsum_luma", "letterbox_frac", "source_kind_code",
    # A denominator count, not a property of the image.
    "tm_bg_tiles",
    # Detector confidence, not design.
    "face_largest_score",
    # Circular quantities where Euclidean distance is meaningless: 359 deg and
    # 1 deg are adjacent but 358 apart. Their information survives via
    # warm_frac, cool_frac, lab_a_mean, lab_b_mean and hue_circvar.
    "hue_dominant_deg", "hue_second_deg",
    # Euclidean distance in sRGB is not perceptual, and these 15 channels would
    # dominate 15 of the dimensions with a distance that means nothing. The
    # palette FRACTIONS and the deltaE summaries are kept.
    "palette_1_r", "palette_1_g", "palette_1_b",
    "palette_2_r", "palette_2_g", "palette_2_b",
    "palette_3_r", "palette_3_g", "palette_3_b",
    "palette_4_r", "palette_4_g", "palette_4_b",
    "palette_5_r", "palette_5_g", "palette_5_b",
])

# Frozen and stamped into styles.json, so a candidate scored months later is
# projected into exactly the space the clusters were built in.
STYLE_FEATURES = tuple(k for k in measure.FEATURE_KEYS
                       if k not in NON_STYLE_KEYS)

# Mirrors grammar.DEFAULT_WIN. Kept as a local constant rather than an import
# because grammar.py runs AFTER styles.py in the pipeline and styles must not
# depend on a module that has not run yet. selftest() asserts the two are equal
# rather than trusting the "change both together" comment that used to be the
# only thing holding them in sync.
WIN_AT = 1.5

# Below this many thumbnails, cluster-level performance differences are not
# reportable at all and render_styles says so in its first line. This is a
# judgement call, not a number measured on this machine.
SMALL_N = 30

# Ranking a cluster on fewer than this many SCORED members is refused outright.
# correlate_with_outliers takes min_members from its caller, but it floors it
# here: a caller passing min_members=1 was previously able to publish a median
# outlier of 9.0x and rank 1 from a single video, which is precisely the
# invented finding the rest of this module is built to prevent.
MIN_RANK_MEMBERS = 4

# Silhouette below this is read as "no substantial structure found". That
# reading is Kaufman and Rousseeuw's conventional band, adopted here as a
# convention; it is not a threshold measured on this machine.
WEAK_SILHOUETTE = 0.25

# Keys measure.KEY_DOC had no entry for. Collected rather than raised so that a
# gap in another module's dictionary degrades one label instead of killing a
# whole clustering run - but surfaced in notes, because a silently blank label
# in Nathan's report is exactly the failure this engine is built to avoid.
MISSING_KEY_DOC = set()

__all__ = [
    "NON_STYLE_KEYS", "STYLE_FEATURES", "WIN_AT", "SMALL_N",
    "WEAK_SILHOUETTE", "MIN_RANK_MEMBERS", "MIN_AUTO_K_N",
    "prepare_matrix", "choose_k", "cluster", "describe_cluster",
    "correlate_with_outliers", "assign", "discover_styles", "load_styles",
    "render_styles", "main", "selftest",
]


# ----------------------------------------------------------------- size rules
#
# Both rules live here because choose_k enforced them and cluster() re-derived
# them by hand in its note text. Two copies of `max(3, n // 20)` is one edit
# away from a report whose warning describes a threshold the code no longer
# uses.
#
def _k_ceiling(n, k_max=8):
    """Largest k that n rows can honestly support.

    The n // 5 term is the binding one: asking for 8 styles from 16 thumbnails
    cannot produce anything but noise, so k is capped so that the AVERAGE
    cluster holds at least 5 members.
    """
    return int(min(int(k_max), max(0, int(n) // 5), int(n) - 1))


def _min_cluster_size(n):
    """Smallest cluster a winning k is allowed to contain.

    A k that wins on silhouette by isolating a single thumbnail is not a style,
    it is an outlier.
    """
    return max(3, int(n) // 20)


# Derived from _k_ceiling rather than asserted, because the previous hardcoded
# claim was wrong in a way that reached the CLI: every gate in this module said
# "at least 4 thumbnails", but _k_ceiling(9) is 1, so cluster() raised on any
# n from 4 to 9 with a message that contradicted itself. This is the real floor
# for choosing k automatically; a caller who forces k needs only k + 1 rows.
MIN_AUTO_K_N = next(n for n in range(2, 1000) if _k_ceiling(n) >= 2)


# ------------------------------------------------------------------- internals
def _f(x, default=float("nan")):
    """Coerce to a plain float, mapping anything unusable to default."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v


def _finite(x):
    return isinstance(x, float) and math.isfinite(x)


def _json_safe(obj):
    """Non-finite floats -> None, so --json emits valid JSON.

    Reuses the package's own _clean when it is importable so that piped output
    and the written styles.json cannot drift apart; the inline fallback exists
    only for a direct script run where the relative import is unavailable.
    """
    try:
        from . import _clean
    except ImportError:
        try:
            from tools.thumbeng import _clean
        except ImportError:
            _clean = None
    if _clean is not None:
        return _clean(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return dict((k, _json_safe(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _nan_stats(col):
    """median/p25/p75/mean/std over the FINITE values of one column.

    Computed on the raw pre-imputation values on purpose: the median reported
    here is the same number used to impute, so critique.py can impute a
    candidate identically from styles.json without a second stored table.
    """
    finite = col[np.isfinite(col)]
    if finite.size == 0:
        return {"median": float("nan"), "p25": float("nan"),
                "p75": float("nan"), "mean": float("nan"),
                "std": float("nan"), "n_finite": 0}
    return {
        "median": float(np.median(finite)),
        "p25": float(np.percentile(finite, 25)),
        "p75": float(np.percentile(finite, 75)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "n_finite": int(finite.size),
    }


def _short_name(key):
    """A short human label for a key, taken from measure.KEY_DOC.

    Formatted from KEY_DOC rather than hand-written per key, so that renaming a
    metric changes its prose in exactly one place and no module invents its own
    English for a number.
    """
    try:
        doc = measure.describe_key(key)
    except Exception:
        MISSING_KEY_DOC.add(key)
        doc = {}
    meaning = str(doc.get("meaning") or "").strip()
    for cut in (" - ", ",", ";", "(", ":"):
        if cut in meaning:
            meaning = meaning.split(cut)[0].strip()
    if meaning and len(meaning) <= 30:
        return meaning.lower()
    return key.replace("_", " ")


def _unit(key):
    try:
        return str(measure.describe_key(key).get("unit") or "")
    except Exception:
        return ""


def _family(key):
    try:
        return str(measure.describe_key(key).get("family") or "")
    except Exception:
        return ""


def _fmt_val(v, unit):
    """Format one measured value with its unit for display."""
    if not _finite(v):
        return "n/a"
    if unit == "fraction":
        return "%.3f" % v
    if unit in ("px", "count"):
        return "%.0f" % v
    if unit == "K":
        return "%.0fK" % v
    if unit == "deg":
        return "%.0f deg" % v
    if abs(v) >= 1000:
        return "%.0f" % v
    if abs(v) >= 10:
        return "%.1f" % v
    return "%.3f" % v


# ---------------------------------------------------------------- matrix build
def prepare_matrix(rows, keys=STYLE_FEATURES, scaler=None):
    """Build the scaled clustering matrix.

    Returns (X, ids, keys, scaler, imputed_counts).

    NaN is imputed with the COLUMN MEDIAN over the finite values, never with
    zero: zero is a meaningful value for face_area_frac_total, and imputing
    zero would stack every faceless thumbnail on top of the genuinely-zero ones
    by accident and manufacture a cluster out of a missing measurement.

    When `scaler` is a previously-saved dict it is APPLIED, not refitted - that
    is the path critique.py takes to place a single candidate into an existing
    cluster space, where refitting on a population of one is meaningless.

    imputed_counts is returned (and written into styles.json) so that a column
    which was 60% imputed is visible rather than trusted.
    """
    keys = tuple(keys)
    raw, ids = measure.feature_matrix(rows, keys=keys)
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 2 or raw.shape[0] == 0:
        raise ValueError("prepare_matrix: no rows to cluster")

    imputed_counts = {}
    all_nan_cols = []
    X = raw.copy()
    for j, key in enumerate(keys):
        col = X[:, j]
        bad = ~np.isfinite(col)
        n_bad = int(bad.sum())
        if n_bad:
            imputed_counts[key] = n_bad
        if n_bad == col.size:
            # Nothing finite anywhere. Imputing a median is impossible; 0.0 is
            # recorded as a stated fallback, not as a measurement.
            col[bad] = 0.0
            all_nan_cols.append(key)
        elif n_bad:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                med = float(np.nanmedian(col))
            col[bad] = med if math.isfinite(med) else 0.0
        X[:, j] = col

    if scaler is None:
        rs = RobustScaler()
        rs.fit(X)
        center = np.asarray(rs.center_, dtype=np.float64)
        scale = np.asarray(rs.scale_, dtype=np.float64)
        # A constant column has IQR 0; sklearn already substitutes 1.0, but the
        # substitution is made explicit here because it is what gets serialised.
        scale = np.where(np.isfinite(scale) & (scale > 0), scale, 1.0)
        scaler_out = {
            "kind": "robust",
            "center": dict((k, float(center[i])) for i, k in enumerate(keys)),
            "scale": dict((k, float(scale[i])) for i, k in enumerate(keys)),
            "all_nan_columns": all_nan_cols,
        }
    else:
        # A saved scaler round-trips through JSON, where write_json turns any
        # non-finite float into null. float(None) is a TypeError three frames
        # from anything the caller can read, and a key the saved scaler never
        # had is a vocabulary mismatch worth naming, so both are caught here.
        missing = [k for k in keys
                   if k not in scaler.get("center", {})
                   or k not in scaler.get("scale", {})]
        if missing:
            raise KeyError(
                "prepare_matrix: the supplied scaler has no entry for %d of "
                "the %d requested keys (first: %s). It was fitted on a "
                "different feature list."
                % (len(missing), len(keys), missing[0]))
        center = np.array([_f(scaler["center"][k], 0.0) for k in keys])
        center = np.where(np.isfinite(center), center, 0.0)
        sc = np.array([_f(scaler["scale"][k], 1.0) for k in keys])
        scale = np.where(np.isfinite(sc) & (sc > 0), sc, 1.0)
        scaler_out = scaler

    Xs = (X - center) / scale
    Xs = np.nan_to_num(Xs, nan=0.0, posinf=0.0, neginf=0.0)
    return Xs, list(ids), keys, scaler_out, imputed_counts


# ------------------------------------------------------------------- choosing k
def choose_k(X, k_min=2, k_max=8, random_state=0):
    """Scan k, score with silhouette, and return (best_k, scan_table).

    The eligibility rule is the honest part. A k that wins on silhouette by
    isolating a single thumbnail is not a style, it is an outlier, and
    reporting it as a style would be exactly the confident-guess failure this
    engine exists to avoid. So the winner must also have a smallest cluster of
    at least max(3, n//20) members.

    k_max is additionally capped by _k_ceiling regardless of the argument, so
    below MIN_AUTO_K_N rows there is no eligible k at all and this returns
    1 - the caller's signal that automatic k is not available, not a claim that
    the population is one style.

    The full scan is returned so the choice is inspectable rather than
    asserted.
    """
    X = np.asarray(X, dtype=np.float64)
    n = X.shape[0]
    scan = []
    k_hi = _k_ceiling(n, k_max)
    k_lo = int(max(2, k_min))
    if k_hi < k_lo:
        return 1, scan

    min_size_req = _min_cluster_size(n)
    for k in range(k_lo, k_hi + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
        labels = km.fit_predict(X)
        sizes = np.bincount(labels, minlength=k)
        try:
            sil = float(silhouette_score(X, labels))
        except ValueError:
            # Degenerate labelling (a k that collapsed); record, do not crash.
            sil = float("nan")
        scan.append({
            "k": int(k),
            "silhouette": sil,
            "inertia": float(km.inertia_),
            "min_cluster_size": int(sizes.min()),
            "sizes": [int(s) for s in sizes],
            "eligible": bool(sizes.min() >= min_size_req and
                             math.isfinite(sil)),
        })

    eligible = [s for s in scan if s["eligible"]]
    pool = eligible if eligible else [s for s in scan
                                      if math.isfinite(s["silhouette"])]
    if not pool:
        return k_lo, scan
    best = max(pool, key=lambda s: s["silhouette"])
    return int(best["k"]), scan


# ----------------------------------------------------------------- description
def describe_cluster(centroid_original, centroid_z, keys, top_n=6):
    """Name a cluster from the features on which it is most extreme.

    Ranks by |z| against the population and renders through measure.KEY_DOC, so
    the English comes from one dictionary and no agent hand-writes metric prose.

    The label is a DESCRIPTION, never a diagnosis. It says what the cluster
    looks like ("high largest-face area, low text area, warm"); it never says
    whether that works. Whether it works is correlate_with_outliers' job.
    """
    ranked = sorted(
        (k for k in keys if _finite(_f(centroid_z.get(k)))),
        key=lambda k: abs(_f(centroid_z.get(k), 0.0)),
        reverse=True,
    )[:max(1, int(top_n))]

    drivers = []
    phrases = []
    for k in ranked:
        z = _f(centroid_z.get(k), 0.0)
        v = _f(centroid_original.get(k))
        unit = _unit(k)
        direction = "high" if z > 0 else "low"
        drivers.append({
            "key": k,
            "z": round(z, 3),
            "value": None if not _finite(v) else round(v, 6),
            "unit": unit,
            "direction": direction,
            "family": _family(k),
            "short": _short_name(k),
        })
        phrases.append("%s %s (%s, z%+.2f)" %
                       (direction, _short_name(k), _fmt_val(v, unit), z))

    label = ", ".join("%s %s" % (d["direction"], d["short"])
                      for d in drivers[:3]) or "undifferentiated"
    return {"label": label, "phrases": phrases, "drivers": drivers}


# --------------------------------------------------------------------- cluster
def cluster(rows, k=None, keys=STYLE_FEATURES, random_state=0,
            k_min=2, k_max=8):
    """Cluster measured rows into styles.

    Runs choose_k when k is None, fits the final KMeans, and inverse-transforms
    each centroid back into ORIGINAL UNITS, so a stored centroid reads as a real
    number ("face_area_frac_largest: 0.22") rather than a z-score nobody can
    interpret. Both are kept: z-scores are what describe_cluster ranks on,
    original units are what critique.py quotes.
    """
    rows = [r for r in rows if not str(r.get("measure_error") or "")]
    if not rows:
        raise ValueError("cluster: no usable rows (all carried measure_error)")

    keys = tuple(keys)
    raw, _ids = measure.feature_matrix(rows, keys=keys)
    raw = np.asarray(raw, dtype=np.float64)
    population_stats = dict((key, _nan_stats(raw[:, j]))
                            for j, key in enumerate(keys))

    X, ids, keys, scaler, imputed_counts = prepare_matrix(rows, keys=keys)
    n = X.shape[0]
    notes = []
    # MISSING_KEY_DOC is a module global that survives between calls. Diffing
    # against a snapshot means a gap found in an earlier run cannot reappear as
    # a warning on this run's report - which it previously did, and a stale
    # warning is indistinguishable from a fresh one to the reader.
    _kd_before = set(MISSING_KEY_DOC)

    if k is None:
        k, k_scan = choose_k(X, k_min=k_min, k_max=k_max,
                             random_state=random_state)
    else:
        k = int(k)
        _bk, k_scan = choose_k(X, k_min=k_min, k_max=k_max,
                               random_state=random_state)
        notes.append("k was supplied as %d; the silhouette scan is reported "
                     "but was not used to choose it." % k)

    if k < 2 or k > n - 1:
        raise ValueError(
            "cluster: cannot cluster %d rows into k=%s. Choosing k "
            "automatically needs at least %d measured thumbnails (k is capped "
            "so the average cluster holds 5); with %d you must either supply k "
            "yourself, where k+1 rows suffice, or measure more thumbnails."
            % (n, k, MIN_AUTO_K_N, n))

    if not any(s["k"] == k and s["eligible"] for s in k_scan):
        notes.append(
            "no k in the scan produced clusters all at least %d members; the "
            "reported k is the best silhouette regardless, and at least one "
            "cluster is small enough to be a single odd thumbnail rather than "
            "a style." % _min_cluster_size(n))

    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    labels = km.fit_predict(X)
    try:
        sil = float(silhouette_score(X, labels))
    except ValueError:
        sil = float("nan")

    center = np.array([scaler["center"][key] for key in keys])
    scale = np.array([scaler["scale"][key] for key in keys])

    clusters = []
    for cid in range(k):
        sel = np.where(labels == cid)[0]
        cz = km.cluster_centers_[cid]
        co = cz * scale + center
        centroid_z = dict((key, float(cz[i])) for i, key in enumerate(keys))
        centroid_original = dict((key, float(co[i]))
                                 for i, key in enumerate(keys))
        if sel.size:
            d = np.linalg.norm(X[sel] - cz, axis=1)
            max_d = float(d.max())
            p95_d = float(np.percentile(d, 95))
            mean_d = float(d.mean())
        else:
            max_d = p95_d = mean_d = float("nan")
        desc = describe_cluster(centroid_original, centroid_z, keys)
        clusters.append({
            "cluster_id": int(cid),
            "size": int(sel.size),
            "member_ids": [ids[i] for i in sel],
            "centroid": centroid_original,
            "centroid_z": centroid_z,
            "max_member_distance": max_d,
            "p95_member_distance": p95_d,
            "mean_member_distance": mean_d,
            "label": desc["label"],
            "phrases": desc["phrases"],
            "drivers": desc["drivers"],
            # Filled by correlate_with_outliers; NaN until then, never 0.
            "n_with_outlier": 0,
            "median_outlier": float("nan"),
            "mean_outlier": float("nan"),
            "p25_outlier": float("nan"),
            "p75_outlier": float("nan"),
            "outlier_lift": float("nan"),
            "win_rate": float("nan"),
            "rank": None,
            "caveat": "no outlier data supplied; this cluster is described, "
                      "not evaluated",
        })

    if n < SMALL_N:
        notes.append(
            "n=%d. This is a description of these %d thumbnails, not evidence "
            "about the niche. Cluster-level performance differences at this "
            "sample size are not reportable." % (n, n))

    # n <= dimensionality was previously unreported, and it is the single
    # biggest reason to distrust the silhouette printed at the top of the
    # report. With 12 points in 107 dimensions every pair of points is close to
    # equidistant, so the number is arithmetically real and evidentially empty.
    if n <= len(keys):
        notes.append(
            "n=%d is not greater than the %d clustering dimensions. Distances "
            "in a space with at least as many dimensions as points are close "
            "to uniform, so the silhouette and the whole k scan above are "
            "arithmetic, not evidence. Roughly %d thumbnails (5 per dimension) "
            "would be needed before this geometry means anything; treat the "
            "clusters as a way to eyeball the set, nothing more."
            % (n, len(keys), 5 * len(keys)))

    # p95 over a handful of members is the maximum in all but name, and
    # assign()'s is_outlier_far tests against exactly this number.
    small_clusters = [c["size"] for c in clusters if c["size"] < 20]
    if small_clusters:
        notes.append(
            "%d cluster(s) hold fewer than 20 members, so their "
            "p95_member_distance is effectively the single farthest member. "
            "assign()'s is_outlier_far therefore means 'farther than the "
            "farthest training thumbnail', not a calibrated 95th percentile."
            % len(small_clusters))

    if math.isfinite(sil) and sil < WEAK_SILHOUETTE:
        notes.append(
            "silhouette %.3f is below %.2f. Kaufman and Rousseeuw's "
            "conventional reading of that band is 'no substantial structure "
            "found' - a convention adopted here, not a threshold measured on "
            "this machine. The split may still track something real, but the "
            "geometry alone does not establish that these are two styles "
            "rather than one spread-out group." % (sil, WEAK_SILHOUETTE))

    _kd_new = MISSING_KEY_DOC - _kd_before
    if _kd_new:
        notes.append(
            "measure.KEY_DOC has no entry for %d key(s) (%s); their labels "
            "fall back to the raw key name."
            % (len(_kd_new), ", ".join(sorted(_kd_new)[:5])))

    heavy = sorted(((v, key) for key, v in imputed_counts.items()
                    if v >= 0.5 * n), reverse=True)
    if heavy:
        notes.append(
            "%d feature(s) were imputed in at least half the rows (worst: %s "
            "at %d/%d); they contribute little real separation."
            % (len(heavy), heavy[0][1], heavy[0][0], n))

    return {
        "schema_version": SCHEMA_VERSION,
        "niche": None,
        "generated_utc": utc_now(),
        "n": int(n),
        "k": int(k),
        "feature_keys": list(keys),
        "k_scan": k_scan,
        "silhouette": sil,
        "scaler": scaler,
        "imputed_counts": imputed_counts,
        "population_stats": population_stats,
        "assignments": dict((ids[i], int(labels[i])) for i in range(n)),
        "clusters": clusters,
        "notes": notes,
    }


# ---------------------------------------------------------------- performance
def correlate_with_outliers(style_result, harvest_rows, min_members=4,
                            win_at=WIN_AT):
    """Attach per-cluster outlier statistics. Augments style_result in place.

    Clusters with fewer than min_members SCORED rows get median_outlier NaN,
    outlier_lift NaN, no rank, and a caveat string. With three members a lift of
    2.4x is one lucky video; presenting it as "the style that works" is exactly
    the invented number this contract exists to prevent.

    min_members is FLOORED at MIN_RANK_MEMBERS and the floor is recorded in the
    result. The argument used to be honoured as given, so min_members=1 - which
    the CLI exposes directly as --min-members - published a median and a rank
    computed from one video. A guard a caller can switch off is not a guard.

    Carried honestly from harvest.py: outlier_score measures a video's pace
    against its own channel's norm. It cannot separate thumbnail effect from
    title, topic, upload timing or the algorithm. It is a ranking signal, not an
    attribution.
    """
    requested_members = int(min_members)
    min_members = max(MIN_RANK_MEMBERS, requested_members)
    win_at = _f(win_at)
    win_at_usable = _finite(win_at)

    by_id = {}
    for r in harvest_rows or []:
        vid = r.get("video_id") or r.get("image_id")
        if not vid:
            continue
        s = _f(r.get("outlier_score"))
        if _finite(s):
            by_id[str(vid)] = s

    all_scores = [by_id[i] for i in style_result["assignments"] if i in by_id]
    pop_median = float(np.median(all_scores)) if all_scores else float("nan")
    style_result["population_median_outlier"] = pop_median
    style_result["n_with_outlier_total"] = len(all_scores)
    style_result["outlier_basis"] = "vpd_ratio_vs_channel_median_settled7d"
    style_result["win_at"] = win_at
    style_result["min_members"] = int(min_members)
    style_result["min_members_requested"] = requested_members

    ranked = []
    for c in style_result["clusters"]:
        vals = [by_id[m] for m in c["member_ids"] if m in by_id]
        c["n_with_outlier"] = len(vals)
        if len(vals) < int(min_members):
            c["median_outlier"] = float("nan")
            c["mean_outlier"] = float("nan")
            c["p25_outlier"] = float("nan")
            c["p75_outlier"] = float("nan")
            c["outlier_lift"] = float("nan")
            c["win_rate"] = float("nan")
            c["rank"] = None
            c["caveat"] = ("only %d of %d members have a usable outlier score "
                           "(need %d); not ranked."
                           % (len(vals), c["size"], int(min_members)))
            continue
        a = np.asarray(vals, dtype=np.float64)
        c["median_outlier"] = float(np.median(a))
        c["mean_outlier"] = float(a.mean())
        c["p25_outlier"] = float(np.percentile(a, 25))
        c["p75_outlier"] = float(np.percentile(a, 75))
        c["outlier_lift"] = (float(np.median(a) / pop_median)
                             if _finite(pop_median) and pop_median > 0
                             else float("nan"))
        # A non-finite win_at used to produce win_rate 0.0, because every
        # comparison against NaN is False. 0% reads as "this style never wins";
        # the truth is that no threshold was supplied.
        c["win_rate"] = (float((a >= win_at).mean()) if win_at_usable
                         else float("nan"))
        c["caveat"] = ""
        ranked.append(c)

    ranked.sort(key=lambda c: c["median_outlier"], reverse=True)
    for i, c in enumerate(ranked, 1):
        c["rank"] = i

    if requested_members < min_members:
        style_result.setdefault("notes", []).append(
            "min_members was requested as %d and raised to %d. A median and a "
            "rank computed from fewer than %d videos is one lucky upload, not "
            "a style effect." % (requested_members, min_members,
                                 MIN_RANK_MEMBERS))
    if not win_at_usable and ranked:
        style_result.setdefault("notes", []).append(
            "win_at was not a finite number, so win_rate is NaN rather than "
            "0%; no cluster is being reported as never winning.")
    if ranked:
        # The denominator of outlier_lift includes the numerator's own members.
        # With k=2 that is roughly half the population, so lift is structurally
        # pulled toward 1.0 and is a within-set comparison, not an effect size.
        style_result.setdefault("notes", []).append(
            "outlier_lift divides a cluster's median by the median of all %d "
            "scored thumbnails, that cluster's own members included. With %d "
            "clusters the denominator overlaps the numerator heavily, so lift "
            "compresses toward 1.0 and is a within-set ordering, not an effect "
            "size." % (len(all_scores), len(style_result["clusters"])))
    if style_result["n"] < SMALL_N and ranked:
        style_result.setdefault("notes", []).append(
            "cluster ranking is shown on n=%d thumbnails across %d ranked "
            "clusters. Treat the order as a hypothesis to test, not a finding."
            % (style_result["n"], len(ranked)))
    if not all_scores:
        style_result.setdefault("notes", []).append(
            "no outlier scores were available, so no cluster is evaluated for "
            "performance - only described.")
    elif not ranked:
        # Scores existed but every cluster fell under min_members. Saying
        # nothing here would let a reader assume performance was checked and
        # came back level, when in fact it was never computable.
        style_result.setdefault("notes", []).append(
            "%d outlier scores were available but no cluster had %d scored "
            "members, so NO cluster is ranked. Nothing here says which style "
            "performs better." % (len(all_scores), int(min_members)))
    return style_result


# ----------------------------------------------------------------- projection
def assign(style_result, feature_row):
    """Place one measured row into the existing cluster space.

    Projects through the SAVED scaler, never a refitted one. NaN features are
    imputed from population_stats medians - the same numbers used when the
    clusters were fitted - so a faceless candidate is not silently pushed toward
    the origin.

    is_outlier_far is True when the distance exceeds the 95th percentile of the
    training members' own distances to that centroid. That is a genuine finding:
    the candidate belongs to no discovered style, and critique.py must report it
    that way rather than naming a cluster the image does not sit in.

    THREE GUARDS, all added after a probe showed the function answering
    confidently when it had nothing to answer with:

      * A row sharing NO finite feature with feature_keys raises. assign({}) and
        assign({"nonsense": 1.0}) both used to return cluster_id 0 with a
        distance, which critique.py would then print as the candidate's style.
      * A row carrying a schema_version different from this build raises,
        because a vocabulary mismatch imputes almost every column instead of
        comparing it.
      * When population_stats has no median for a key, the z-score is set to 0
        (the population centre) rather than the raw value 0.0. The old fallback
        put the RAW number zero through the scaler, which for a key centred far
        from zero is an extreme z, not a neutral one: on a probe the identical
        empty row moved from distance 5.06 to 8.36 purely on whether
        population_stats happened to be present.

    imputed_frac and is_reliable are returned so a caller can tell a real
    placement from an arithmetic one.
    """
    clusters = style_result.get("clusters") or []
    if not clusters:
        raise ValueError("assign: style_result carries no clusters")

    keys = tuple(style_result["feature_keys"])
    if not keys:
        raise ValueError("assign: style_result carries no feature_keys")

    sv = (feature_row or {}).get("schema_version")
    if sv is not None and sv != SCHEMA_VERSION:
        raise ValueError(
            "assign: feature row schema_version %r != %r; re-run measure "
            "rather than projecting one vocabulary into another's clusters."
            % (sv, SCHEMA_VERSION))

    center = style_result["scaler"]["center"]
    scale = style_result["scaler"]["scale"]
    pop = style_result.get("population_stats", {})

    z_row = {}
    vec = np.empty(len(keys), dtype=np.float64)
    imputed = []
    neutralised = []
    for i, key in enumerate(keys):
        v = _f((feature_row or {}).get(key))
        neutral = False
        if not _finite(v):
            imputed.append(key)
            v = _f((pop.get(key) or {}).get("median"))
            if not _finite(v):
                # No median to impute from. Sit at the population centre.
                neutral = True
                neutralised.append(key)
        if neutral:
            z = 0.0
        else:
            sc = _f(scale.get(key), 1.0)
            if not _finite(sc) or sc <= 0:
                sc = 1.0
            z = (v - _f(center.get(key), 0.0)) / sc
            if not math.isfinite(z):
                z = 0.0
        vec[i] = z
        z_row[key] = float(z)

    n_present = len(keys) - len(imputed)
    if n_present == 0:
        raise ValueError(
            "assign: the row carries no finite value for any of the %d "
            "clustering features, so any cluster returned would be arithmetic "
            "on imputed medians. Measure the image first." % len(keys))

    dists = []
    for c in clusters:
        cz = np.array([_f((c.get("centroid_z") or {}).get(key), 0.0)
                       for key in keys])
        dists.append((float(np.linalg.norm(vec - cz)), int(c["cluster_id"])))
    dists.sort()

    best_d, best_id = dists[0]
    near = next(c for c in clusters if c["cluster_id"] == best_id)
    p95 = _f(near.get("p95_member_distance"))
    imputed_frac = len(imputed) / float(len(keys))
    return {
        "cluster_id": best_id,
        "distance": best_d,
        "nearest_two": [{"cluster_id": cid, "distance": d}
                        for d, cid in dists[:2]],
        "z_row": z_row,
        "is_outlier_far": bool(_finite(p95) and best_d > p95),
        "imputed_keys": imputed,
        "neutralised_keys": neutralised,
        "imputed_frac": round(imputed_frac, 4),
        # Half the vector borrowed from the population median means the
        # placement is largely a statement about the population, not the image.
        "is_reliable": bool(imputed_frac <= 0.5),
        "caveat": ("" if imputed_frac <= 0.5 else
                   "%d of %d features (%.0f%%) were imputed; this placement "
                   "describes the population median more than the candidate"
                   % (len(imputed), len(keys), 100.0 * imputed_frac)),
    }


# ------------------------------------------------------------------- pipeline
def discover_styles(niche=None, measure_rows=None, harvest_rows=None, k=None,
                    out_json=None, min_members=4):
    """Pipeline entry point. Loads, clusters, correlates, writes styles.json.

    Loads through measure.load_measurements and harvest.load_harvest when given
    a niche; never opens those files directly, so a schema bump is caught by
    their loaders rather than silently mis-parsed here.
    """
    started = utc_now()
    if measure_rows is None:
        if niche is None:
            raise ValueError("discover_styles needs a niche or measure_rows")
        measure_rows = measure.load_measurements(niche)
    if harvest_rows is None and niche is not None:
        try:
            from . import harvest as _harvest
        except ImportError:
            try:
                from tools.thumbeng import harvest as _harvest
            except ImportError:
                _harvest = None
        if _harvest is not None:
            try:
                harvest_rows = _harvest.load_harvest(niche)
            except Exception as exc:
                harvest_rows = []
                print("styles: harvest.jsonl unreadable (%s); clustering "
                      "without performance data." % exc, file=sys.stderr)
        else:
            harvest_rows = []

    res = cluster(measure_rows, k=k)
    res["niche"] = niche
    correlate_with_outliers(res, harvest_rows or [], min_members=min_members)

    if out_json is None and niche is not None:
        out_json = niche_dir(niche) + "/styles.json"
    if out_json:
        write_json(out_json, res)
        # Both spellings: grammar.py reads styles["_path"] to record its
        # source, critique.py and the CLI read "path". Cheaper to write two
        # keys than to make two modules agree after the fact.
        res["path"] = out_json
        res["_path"] = out_json
    if niche is not None:
        run_manifest(niche, "styles",
                     {"k": k, "min_members": min_members},
                     {"n": res["n"], "k": res["k"],
                      "n_with_outlier_total": res.get("n_with_outlier_total", 0)},
                     started_utc=started, ok=True)
    return res


def load_styles(path_or_niche):
    """The only sanctioned reader of styles.json. Raises on schema mismatch.

    read_json returns None both for a file that is absent and for one that is
    present but unparseable, so the two are separated here before raising. The
    single message this used to print - "no styles.json at X" - sent a reader
    looking for a missing file while a truncated one sat at that exact path.
    """
    p = str(path_or_niche).replace("\\", "/")
    if not p.lower().endswith(".json"):
        p = niche_dir(path_or_niche, create=False) + "/styles.json"
    doc = read_json(p, default=None)
    if doc is None:
        if os.path.exists(p):
            raise ValueError(
                "styles.json at %s exists but is not parseable JSON (%d "
                "bytes). Re-run styles rather than reading around it."
                % (p, os.path.getsize(p)))
        raise FileNotFoundError("no styles.json at %s" % p)
    if not isinstance(doc, dict):
        raise ValueError("styles.json at %s is a %s, not an object"
                         % (p, type(doc).__name__))
    sv = doc.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise ValueError(
            "styles.json schema_version %r != %r. Re-run measure and styles "
            "rather than mixing vocabularies." % (sv, SCHEMA_VERSION))
    return doc


# --------------------------------------------------------------------- render
def render_styles(style_result, width=100):
    """Plain-text block, printed by the CLI so the module shows its own state.

    The sample-size sentence comes FIRST when n is small. A reader who sees
    "cluster 2 runs 2.4x" before they see "n=16" has already been misled.

    Every number here is read through _f/_finite rather than used directly,
    because this is the one function that runs on a styles.json LOADED FROM
    DISK, where write_json has already turned every NaN into null. The k-scan
    line called math.isfinite on a raw value and raised TypeError on exactly
    the file this module writes.
    """
    R = style_result
    L = []
    width = max(40, int(width))
    bar = "=" * width
    sil_top = _f(R.get("silhouette"))
    n = int(_f(R.get("n"), 0))
    n_keys = len(R.get("feature_keys") or ())
    L.append(bar)
    L.append("STYLES  niche=%s  n=%d  k=%s  silhouette=%s"
             % (R.get("niche"), n, R.get("k"),
                ("%.3f" % sil_top) if _finite(sil_top) else "n/a"))
    L.append("features=%d of %d measured keys  generated=%s"
             % (n_keys, len(measure.FEATURE_KEYS), R.get("generated_utc")))
    if n < SMALL_N:
        L.append("!! SAMPLE SIZE %d. These are descriptions of this set, not "
                 "findings about a niche." % n)
    if n_keys and n <= n_keys:
        L.append("!! %d thumbnails in %d dimensions. The silhouette and k scan "
                 "below are arithmetic, not evidence - with no more points "
                 "than dimensions every distance is nearly the same."
                 % (n, n_keys))
    L.append(bar)

    scan = R.get("k_scan") or []
    if scan:
        L.append("k scan (silhouette / smallest cluster / eligible):")
        for s in scan:
            ssil = _f(s.get("silhouette"))
            L.append("   k=%s  sil=%s  min_size=%s  sizes=%s  %s"
                     % (s.get("k"),
                        ("%.3f" % ssil) if _finite(ssil) else "n/a",
                        s.get("min_cluster_size"), s.get("sizes"),
                        "eligible" if s.get("eligible") else "REJECTED"))
        L.append("")

    ordered = sorted(R.get("clusters") or [],
                     key=lambda c: (c.get("rank") is None,
                                    c.get("rank") or 0,
                                    -int(_f(c.get("size"), 0))))
    for c in ordered:
        L.append("-" * width)
        head = "CLUSTER %s  n=%s  %s" % (c.get("cluster_id"), c.get("size"),
                                         c.get("label"))
        if c.get("rank"):
            head += "   [rank %d]" % c["rank"]
        L.append(head)
        med = _f(c.get("median_outlier"))
        lift = _f(c.get("outlier_lift"))
        wr = _f(c.get("win_rate"))
        if _finite(med):
            L.append("   performance: median outlier %.2fx  lift %s  "
                     "win_rate %s  (n scored=%s)"
                     % (med,
                        ("%.2fx" % lift) if _finite(lift) else "n/a",
                        ("%.0f%%" % (100.0 * wr)) if _finite(wr) else "n/a",
                        c.get("n_with_outlier")))
        else:
            L.append("   performance: NOT EVALUATED - %s"
                     % (c.get("caveat") or "no outlier data"))
        L.append("   what makes it distinct:")
        for d in (c.get("drivers") or []):
            popmed = _f(((R.get("population_stats") or {}).get(d.get("key"))
                         or {}).get("median"))
            L.append("      %-26s %-10s  z%+.2f   (all thumbs median %s)"
                     % (str(d.get("short") or d.get("key"))[:26],
                        _fmt_val(_f(d.get("value")), d.get("unit") or ""),
                        _f(d.get("z"), 0.0),
                        _fmt_val(popmed, d.get("unit") or "")))
        mids = list(c.get("member_ids") or [])
        members = ", ".join(mids[:8])
        if len(mids) > 8:
            members += ", ... (+%d)" % (len(mids) - 8)
        L.append("   members: %s" % members)

    L.append("-" * width)
    for note in R.get("notes", []):
        L.append("NOTE: %s" % note)
    L.append(bar)
    return "\n".join(L)


# ------------------------------------------------------------------- selftest
def _synthetic_rows(n_per=12, n_groups=3, seed=0):
    """Build well-separated synthetic populations spanning every FEATURE_KEY.

    Every clustering dimension carries the group signal. That is deliberate: a
    synthetic set where only a handful of dimensions separate the groups would
    be swamped by the remaining ~100 scaled noise dimensions, and the test would
    then be measuring dimensionality rather than whether choose_k works.
    """
    rng = np.random.default_rng(seed)
    keys = measure.FEATURE_KEYS
    group_centers = rng.normal(0.0, 3.0, size=(n_groups, len(keys)))
    rows, truth = [], []
    for g in range(n_groups):
        for i in range(n_per):
            row = {}
            noise = rng.normal(0.0, 0.30, size=len(keys))
            vals = group_centers[g] + noise
            for j, key in enumerate(keys):
                row[key] = float(vals[j])
            row["image_id"] = "g%d_%02d" % (g, i)
            row["image_path"] = ""
            row["source_kind"] = "local"
            row["measure_error"] = ""
            row["schema_version"] = SCHEMA_VERSION
            rows.append(row)
            truth.append(g)
    return rows, truth


def selftest():
    """Prove the clustering recovers a known answer, then cluster real files.

    A clustering that cannot be shown to recover a known answer is not evidence
    of anything, so the synthetic half runs first and its failure is fatal.
    """
    ok = True
    print("=" * 100)
    print("styles.py SELFTEST")
    print("=" * 100)
    print("STYLE_FEATURES: %d of %d measured keys (%d excluded)"
          % (len(STYLE_FEATURES), len(measure.FEATURE_KEYS),
             len(measure.FEATURE_KEYS) - len(STYLE_FEATURES)))

    # ---- 1. synthetic: does choose_k recover a known k=3? -------------------
    rows, truth = _synthetic_rows(n_per=12, n_groups=3, seed=0)
    X, ids, keys, scaler, imp = prepare_matrix(rows)
    best_k, scan = choose_k(X, k_min=2, k_max=8)
    sil = [s["silhouette"] for s in scan if s["k"] == best_k][0]
    print("\n[1] synthetic 3 populations x 12 -> choose_k=%d silhouette=%.3f"
          % (best_k, sil))
    for s in scan:
        print("      k=%d sil=%.3f min_size=%d %s"
              % (s["k"], s["silhouette"], s["min_cluster_size"],
                 "eligible" if s["eligible"] else "REJECTED"))
    if best_k != 3:
        print("    FAIL: expected k=3, got %d" % best_k)
        ok = False
    if not (sil > 0.5):
        print("    FAIL: expected silhouette > 0.5, got %.3f" % sil)
        ok = False

    res = cluster(rows)
    # KMeans cluster ids are arbitrary, so compare against the modal id of the
    # known group rather than assuming label 2 means group 2.
    g2_ids = [r["image_id"] for r in rows if r["image_id"].startswith("g2_")]
    g2_labels = [res["assignments"][i] for i in g2_ids]
    modal = max(set(g2_labels), key=g2_labels.count)
    pure = g2_labels.count(modal) == len(g2_labels)
    print("\n[2] group 2 lands wholly in cluster %d: %s" % (modal, pure))
    if not pure:
        print("    FAIL: group 2 was split across clusters %s" % set(g2_labels))
        ok = False

    # ---- 3. assign() places a fresh point from population 2 correctly ------
    rng = np.random.default_rng(99)
    probe = dict(rows[24])          # a group-2 row
    for key in measure.FEATURE_KEYS:
        probe[key] = float(probe[key] + rng.normal(0.0, 0.30))
    a = assign(res, probe)
    print("[3] fresh group-2 point assigned to cluster %d (expected %d), "
          "distance %.2f, outlier_far=%s"
          % (a["cluster_id"], modal, a["distance"], a["is_outlier_far"]))
    if a["cluster_id"] != modal:
        print("    FAIL: assign() put a group-2 point in cluster %d"
              % a["cluster_id"])
        ok = False

    # ---- 4. a thinly-scored cluster must not be ranked ----------------------
    fake_harvest = []
    for cid, c in enumerate(res["clusters"]):
        keep = 3 if cid == modal else len(c["member_ids"])
        for j, m in enumerate(c["member_ids"][:keep]):
            fake_harvest.append({"video_id": m,
                                 "outlier_score": 2.4 if cid == modal
                                 else 1.0 + 0.05 * j})
    correlate_with_outliers(res, fake_harvest, min_members=4)
    thin = res["clusters"][modal]
    print("[4] cluster %d scored on only %d members -> median_outlier=%s "
          "rank=%s" % (modal, thin["n_with_outlier"],
                       thin["median_outlier"], thin["rank"]))
    print("      caveat: %s" % thin["caveat"])
    if _finite(_f(thin["median_outlier"])) or thin["rank"] is not None:
        print("    FAIL: a 3-member cluster was ranked with a real median. "
              "That is the noise-as-insight failure this guard exists for.")
        ok = False
    other = [c for c in res["clusters"] if c["cluster_id"] != modal]
    if not all(c["rank"] is not None for c in other):
        print("    FAIL: fully-scored clusters were not ranked")
        ok = False

    # ---- 5. real thumbnails ------------------------------------------------
    folder = "D:/Boyd Clips/READY-TO-POST"
    print("\n[5] clustering the real thumbnails in %s" % folder)
    # glob.escape on this module's OWN glob only. measure_folder escapes the
    # directory itself, so it must be handed the raw path.
    files = sorted(glob.glob(glob.escape(folder) + "/*.jpg"))
    if not files:
        print("    SELFTEST_SKIP: no jpgs found at %s" % folder)
    else:
        real = measure.measure_folder(folder, pattern="*.jpg",
                                      source_kind="local", progress=True)
        real = [r for r in real if not str(r.get("measure_error") or "")]
        print("    measured %d/%d files cleanly" % (len(real), len(files)))
        if len(real) < MIN_AUTO_K_N:
            print("    SELFTEST_SKIP: %d usable thumbnails is below the %d "
                  "needed to choose k automatically."
                  % (len(real), MIN_AUTO_K_N))
        else:
            rres = cluster(real)
            rres["niche"] = "ready-to-post"
            correlate_with_outliers(rres, [], min_members=4)
            print()
            print(render_styles(rres))
            if len(rres["clusters"]) != rres["k"]:
                print("    FAIL: k and cluster count disagree")
                ok = False
            if sum(c["size"] for c in rres["clusters"]) != rres["n"]:
                print("    FAIL: cluster sizes do not sum to n")
                ok = False
            if any(c["rank"] is not None for c in rres["clusters"]):
                print("    FAIL: clusters were ranked with no outlier data")
                ok = False
            if not any("dimensions" in nt for nt in rres["notes"]):
                print("    FAIL: n=%d in %d dimensions and no note said so"
                      % (rres["n"], len(rres["feature_keys"])))
                ok = False

    # ---- 6. edge cases that used to crash or answer wrongly -----------------
    print("\n[6] edge cases")
    ok = _selftest_edges(rows) and ok

    print()
    print("SELFTEST_PASS" if ok else "SELFTEST_FAIL")
    return 0 if ok else 1


def _selftest_edges(rows):
    """Each check here corresponds to a defect that was reachable from the CLI.

    Kept in its own function because these are regression tests, not a
    demonstration of the clustering: they assert what the module REFUSES to do.
    """
    import json as _json
    import shutil
    import tempfile

    ok = True

    def _check(name, cond, detail=""):
        nonlocal ok
        print("    %-46s %s%s" % (name, "ok" if cond else "FAIL",
                                  (" - " + detail) if detail else ""))
        if not cond:
            ok = False

    res = cluster(rows)

    # A small population must refuse with a message that names the real floor,
    # not the old self-contradicting "at least 4" that fired at n=4.
    try:
        cluster(rows[:MIN_AUTO_K_N - 1])
        _check("cluster(n=%d) refuses" % (MIN_AUTO_K_N - 1), False,
               "it returned a clustering")
    except ValueError as exc:
        _check("cluster(n=%d) refuses" % (MIN_AUTO_K_N - 1),
               str(MIN_AUTO_K_N) in str(exc), str(exc)[:70])
    # ...but a forced k needs only k+1 rows.
    try:
        r_small = cluster(rows[:4], k=2)
        _check("cluster(n=4, k=2) forced works", r_small["k"] == 2)
    except Exception as exc:
        _check("cluster(n=4, k=2) forced works", False,
               "%s: %s" % (type(exc).__name__, exc))

    # render_styles must survive the JSON round trip this module itself writes:
    # write_json turns NaN into null and math.isfinite(None) is a TypeError.
    nan_doc = cluster(rows)
    nan_doc["silhouette"] = float("nan")
    nan_doc["k_scan"][0]["silhouette"] = float("nan")
    tmp = tempfile.mkdtemp(prefix="thumbeng_styles_")
    try:
        write_json(tmp + "/styles.json", nan_doc)
        loaded = read_json(tmp + "/styles.json")
        try:
            txt = render_styles(loaded)
            _check("render_styles(loaded json, NaN silhouette)",
                   "sil=n/a" in txt or "silhouette=n/a" in txt)
        except Exception as exc:
            _check("render_styles(loaded json, NaN silhouette)", False,
                   "%s: %s" % (type(exc).__name__, exc))

        # load_styles must tell a corrupt file from an absent one.
        with open(tmp + "/bad.json", "w", encoding="utf-8") as fh:
            fh.write("{not json")
        try:
            load_styles(tmp + "/bad.json")
            _check("load_styles(corrupt) raises", False)
        except ValueError as exc:
            _check("load_styles(corrupt) raises",
                   "not parseable" in str(exc), str(exc)[:60])
        except FileNotFoundError:
            _check("load_styles(corrupt) raises", False,
                   "called a corrupt file missing")
        try:
            load_styles(tmp + "/absent.json")
            _check("load_styles(absent) raises FileNotFoundError", False)
        except FileNotFoundError:
            _check("load_styles(absent) raises FileNotFoundError", True)

        # A folder whose name contains a glob metachar is legal on Windows.
        gd = tmp + "/set [v2]"
        os.makedirs(gd)
        shutil.copy(tmp + "/styles.json", gd + "/a.json")
        _check("glob.escape finds files under 'set [v2]'",
               len(glob.glob(glob.escape(gd) + "/*.json")) == 1
               and len(glob.glob(gd + "/*.json")) == 0)
        # measure_folder escapes the directory itself, so it must receive the
        # RAW path. Passing an already-escaped one turned "set [v2]" into
        # "set [[]v2]" and raised "not a folder" - a bug this module caused by
        # double-escaping, not one it inherited.
        try:
            import cv2 as _cv2
            _cv2.imwrite(gd + "/probe.jpg",
                         np.full((180, 320, 3), 200, dtype=np.uint8))
            got = measure.measure_folder(gd, pattern="*.jpg",
                                         source_kind="local", progress=False)
            _check("measure_folder takes the RAW 'set [v2]' path",
                   len(got) == 1, "%d rows" % len(got))
        except Exception as exc:
            _check("measure_folder takes the RAW 'set [v2]' path", False,
                   "%s: %s" % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # assign() must refuse rather than answer from imputed medians alone.
    for label, row in (("empty row", {}),
                       ("foreign vocabulary", {"nonsense": 1.0})):
        try:
            assign(res, row)
            _check("assign(%s) refuses" % label, False,
                   "it named a cluster")
        except ValueError:
            _check("assign(%s) refuses" % label, True)
    try:
        assign(res, {"schema_version": SCHEMA_VERSION + 99,
                     STYLE_FEATURES[0]: 0.0})
        _check("assign(wrong schema_version) refuses", False)
    except ValueError:
        _check("assign(wrong schema_version) refuses", True)

    # A real row still places, and reports how much of it was imputed.
    a = assign(res, rows[0])
    _check("assign(real row) places and is_reliable",
           a["is_reliable"] and a["imputed_frac"] == 0.0,
           "imputed_frac=%.2f" % a["imputed_frac"])

    # Dropping population_stats must not move the placement, because the
    # fallback is a neutral z rather than the raw value 0.0.
    partial = dict(rows[0])
    for key in STYLE_FEATURES[:40]:
        partial[key] = float("nan")
    no_pop = dict(res)
    no_pop.pop("population_stats", None)
    d_pop = assign(res, partial)["distance"]
    d_nopop = assign(no_pop, partial)["distance"]
    _check("missing population_stats does not distort distance",
           abs(d_pop - d_nopop) < 0.5 * max(1.0, d_pop),
           "with=%.2f without=%.2f" % (d_pop, d_nopop))
    _check("40/107 imputed still counts as reliable",
           assign(res, partial)["is_reliable"],
           "imputed_frac=%.2f" % assign(res, partial)["imputed_frac"])
    mostly_missing = dict(rows[0])
    for key in STYLE_FEATURES[:len(STYLE_FEATURES) - 5]:
        mostly_missing[key] = float("nan")
    a_bad = assign(res, mostly_missing)
    _check("heavy imputation marks the placement unreliable",
           (not a_bad["is_reliable"]) and a_bad["caveat"],
           "imputed_frac=%.2f" % a_bad["imputed_frac"])

    # min_members must not be talked below the floor.
    r1 = cluster(rows)
    one = [{"video_id": r1["clusters"][0]["member_ids"][0],
            "outlier_score": 9.0}]
    correlate_with_outliers(r1, one, min_members=1)
    _check("min_members=1 cannot rank a 1-video cluster",
           r1["clusters"][0]["rank"] is None
           and not _finite(_f(r1["clusters"][0]["median_outlier"])),
           "rank=%s median=%s" % (r1["clusters"][0]["rank"],
                                  r1["clusters"][0]["median_outlier"]))

    # A non-finite win_at must give NaN, not a 0% that reads as "never wins".
    r2 = cluster(rows)
    full = [{"video_id": m, "outlier_score": 3.0}
            for c in r2["clusters"] for m in c["member_ids"]]
    correlate_with_outliers(r2, full, min_members=MIN_RANK_MEMBERS,
                            win_at=float("nan"))
    _check("win_at=NaN gives win_rate NaN, not 0%",
           not _finite(_f(r2["clusters"][0]["win_rate"])),
           str(r2["clusters"][0]["win_rate"]))
    r3 = cluster(rows)
    correlate_with_outliers(r3, full, min_members=MIN_RANK_MEMBERS)
    _check("win_at=1.5 with every score 3.0 gives win_rate 1.0",
           r3["clusters"][0]["win_rate"] == 1.0)

    # A stale KEY_DOC gap from an earlier call must not appear in this report.
    MISSING_KEY_DOC.add("stale_key_from_a_previous_run")
    try:
        r4 = cluster(rows)
        _check("stale MISSING_KEY_DOC does not leak into notes",
               not any("stale_key_from_a_previous_run" in nt
                       for nt in r4["notes"]))
    finally:
        MISSING_KEY_DOC.discard("stale_key_from_a_previous_run")

    # --json must be parseable by something other than Python.
    payload = _json.dumps(_json_safe(cluster(rows)), allow_nan=False,
                          default=str)
    _check("--json payload has no bare NaN token",
           "NaN" not in payload and _json.loads(payload)["k"] >= 2)

    # WIN_AT is a hand-copy of grammar.DEFAULT_WIN; assert it, do not trust the
    # comment that says to change both together.
    try:
        try:
            from . import grammar as _grammar
        except ImportError:
            from tools.thumbeng import grammar as _grammar
        _check("WIN_AT == grammar.DEFAULT_WIN",
               WIN_AT == _grammar.DEFAULT_WIN,
               "styles=%s grammar=%s" % (WIN_AT, _grammar.DEFAULT_WIN))
    except ImportError as exc:
        print("    %-46s SKIP - grammar not importable (%s)"
              % ("WIN_AT == grammar.DEFAULT_WIN", exc))

    # MIN_AUTO_K_N must stay derived from the ceiling rule, not drift from it.
    _check("MIN_AUTO_K_N agrees with _k_ceiling",
           _k_ceiling(MIN_AUTO_K_N) >= 2
           and _k_ceiling(MIN_AUTO_K_N - 1) < 2,
           "MIN_AUTO_K_N=%d" % MIN_AUTO_K_N)

    return ok


# ------------------------------------------------------------------------ cli
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="tools.thumbeng.styles",
        description="Discover recurring thumbnail styles by clustering "
                    "measured feature vectors.")
    ap.add_argument("--niche", help="niche name under work/thumbeng")
    ap.add_argument("--folder", help="ad-hoc folder of images to cluster "
                                     "instead of a niche")
    ap.add_argument("--source-kind", default="local",
                    choices=["local", "youtube"])
    # Was hardcoded to "*.jpg", which reported "0 usable images" for a folder
    # of PNGs rather than saying it had not looked at them. The default now
    # comes from measure.IMAGE_PATTERNS so styles cannot know a narrower set of
    # extensions than the module that does the reading.
    ap.add_argument("--pattern", action="append", default=None,
                    help="glob pattern within --folder; repeatable "
                         "(default %s)" % " ".join(measure.IMAGE_PATTERNS))
    ap.add_argument("--k", type=int, default=None,
                    help="force k instead of choosing by silhouette")
    ap.add_argument("--min-members", type=int, default=MIN_RANK_MEMBERS,
                    help="scored members a cluster needs before it is ranked "
                         "(floored at %d)" % MIN_RANK_MEMBERS)
    ap.add_argument("--out", default=None, help="write styles.json here")
    ap.add_argument("--json", action="store_true",
                    help="print the styles object instead of the report")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        if args.folder:
            folder = str(args.folder).replace("\\", "/").rstrip("/")
            if not os.path.isdir(folder):
                print("styles: --folder %s is not a directory" % folder,
                      file=sys.stderr)
                return 2
            # The RAW folder goes to measure_folder, which glob.escapes the
            # directory itself - "D:/Boyd Clips/set [v2]" is a legal Windows
            # name whose [v2] glob reads as a character class. Escaping here as
            # well produced "set [[]v2]" and a spurious "not a folder".
            patterns = tuple(args.pattern or measure.IMAGE_PATTERNS)
            rows = measure.measure_folder(folder, pattern=patterns,
                                          source_kind=args.source_kind,
                                          progress=True)
            n_seen = len(rows)
            rows = [r for r in rows if not str(r.get("measure_error") or "")]
            need = MIN_AUTO_K_N if args.k is None else int(args.k) + 1
            if len(rows) < need:
                print("styles: %d of %d images measured cleanly; need at "
                      "least %d %s. (Pattern was %s.)"
                      % (len(rows), n_seen, need,
                         "to choose k automatically" if args.k is None
                         else "to cluster into k=%d" % args.k,
                         " ".join(patterns)),
                      file=sys.stderr)
                return 2
            res = cluster(rows, k=args.k)
            res["niche"] = args.niche or os.path.basename(folder) or "folder"
            correlate_with_outliers(res, [], min_members=args.min_members)
            if args.out:
                write_json(args.out, res)
        elif args.niche:
            res = discover_styles(niche=args.niche, k=args.k,
                                  out_json=args.out,
                                  min_members=args.min_members)
        else:
            ap.error("give --niche, --folder or --selftest")
            return 2
    except (ValueError, KeyError, FileNotFoundError) as exc:
        # These are the module's own refusals ("not enough rows", "schema
        # mismatch"). A refusal the author wrote deliberately should reach the
        # user as one line on stderr, not as a traceback they have to read.
        print("styles: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        import json as _json
        # json.dumps emits a bare NaN token by default, which is invalid JSON
        # and rejected by every parser that is not Python's own. write_json
        # already nulls non-finite floats; the same cleaner is used here so the
        # piped output and the written file agree.
        print(_json.dumps(_json_safe(res), indent=2, ensure_ascii=False,
                          default=str, allow_nan=False))
    else:
        print(render_styles(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
