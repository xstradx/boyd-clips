# -*- coding: utf-8 -*-
"""
grammar.py — turns measurements + outlier scores into the NICHE GRAMMAR:
the "what works right now" object.

For every measurable property it reports the range the winners occupy against
the range the losers occupy, and it is REQUIRED to say plainly when a
difference is not distinguishable from noise.

------------------------------------------------------------------------------
WHY THIS MODULE IS MOSTLY DEFENCES RATHER THAN STATISTICS
------------------------------------------------------------------------------
measure.FEATURE_KEYS has 133 entries. Testing 133 features at alpha=0.05 against
a null of pure noise produces roughly 7 "significant" findings BY CONSTRUCTION.
A grammar that prints all 133 rows as findings is worse than no grammar at all,
because the reader cannot check any of them and a confident number becomes what
he believes. Three defences, all mandatory, none optional:

  1. MINIMUM GROUP SIZE (MIN_GROUP). Below MIN_GROUP winners or MIN_GROUP
     losers, `meaningful` is False for every key, full stop, and the grammar
     carries a top-level warning. MIN_GROUP=8 is a JUDGEMENT CALL, not a number
     derived from any data on this machine — see the constant's docstring.

  2. A NONPARAMETRIC EFFECT SIZE (Cliff's delta), not just a p-value. These
     feature distributions are skewed and small-n; a t-test's normality and
     equal-variance assumptions do not hold, and a p-value answers "is it
     detectable" when the question is "how much".

  3. BENJAMINI-HOCHBERG FDR correction across every tested key, applied AFTER
     all rules are built because it depends on the whole set of p-values.

A rule is `meaningful` ONLY when:
    n_win >= MIN_GROUP  and  n_lose >= MIN_GROUP
    and |cliffs_delta| >= EFFECT_MIN
    and q_value < ALPHA
Everything else is reported with meaningful=False and a `reason` string, and
critique.py must not raise a defect from a non-meaningful rule.

------------------------------------------------------------------------------
WHAT THIS MODULE CANNOT DO — carried through to grammar['notes']
------------------------------------------------------------------------------
outlier_score (built in harvest.py) measures a video's views-per-day against its
OWN channel's median views-per-day. That removes the subscriber-count confound
and nothing else. It CANNOT separate thumbnail effect from title, topic, upload
timing, or the recommendation algorithm. Every rule here is therefore a
CORRELATION IN A SMALL OBSERVATIONAL SAMPLE, never an attribution, and
grammar['confidence'] is capped at 'moderate' — 'strong' is not reachable and
that is deliberate.

------------------------------------------------------------------------------
WRITES grammar.json AND NOTHING ELSE. Reads only through measure.load_measurements
and harvest.load_harvest / harvest.join_measurements — never opens those files
directly.
------------------------------------------------------------------------------
CLI
    python -m tools.thumbeng.grammar --niche court [--win 1.5 --lose 0.8]
    python -m tools.thumbeng.grammar --selftest
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np

# --------------------------------------------------------------------------
# Package bootstrap.
#
# `python -m tools.thumbeng.grammar` arrives here with __package__ set and the
# relative imports below just work. `python tools/thumbeng/grammar.py` arrives
# with __package__ == "" — so put the REPO ROOT (not tools/) on sys.path and
# adopt the package name. Deliberately NOT putting tools/ itself on sys.path
# first: tools/harvest.py already exists and is an unrelated courtroom-frame
# harvester, so a bare `import harvest` from inside this package would silently
# bind the wrong module.
# --------------------------------------------------------------------------
if __package__ in (None, ""):  # pragma: no cover - only on direct script run
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    __package__ = "tools.thumbeng"

from . import SCHEMA_VERSION, niche_dir, read_json, utc_now, write_json  # noqa: E402
from . import measure as _measure  # noqa: E402

# scipy is verified present (1.18.0) on this interpreter, but the module must
# still run if it is not — a permutation test in numpy answers the same
# question, just slower and with a granular p-value floor of 1/n_perm.
try:
    from scipy.stats import mannwhitneyu as _scipy_mwu

    HAVE_SCIPY = True
except Exception:  # pragma: no cover - scipy is present here
    _scipy_mwu = None
    HAVE_SCIPY = False


__all__ = [
    "DEFAULT_WIN", "DEFAULT_LOSE", "MIN_GROUP", "EFFECT_MIN", "ALPHA",
    "MIN_CONFIDENCE", "PROVENANCE_KEYS",
    "WEAK_N", "MIN_CHANNELS", "MIN_QUARTILE_N", "MIN_DECILE_N", "MIN_STD_N",
    "split_groups", "cliffs_delta", "rule_for_key", "fdr_adjust",
    "build_grammar", "grammar_summary", "render_grammar",
    "save_grammar", "load_grammar", "main", "selftest",
]


# ==========================================================================
# Constants
# ==========================================================================

DEFAULT_WIN = 1.5
"""A winner ran at >= 1.5x its own channel's normal views-per-day."""

DEFAULT_LOSE = 0.8
"""A loser ran at <= 0.8x its own channel's normal views-per-day.

The band between DEFAULT_LOSE and DEFAULT_WIN is DISCARDED, not assigned to
either side. The middle is exactly where a thumbnail's effect is least
separable from topic, title and upload timing; forcing a binary split there
manufactures contrast out of the noisiest part of the sample. Both numbers are
CHOSEN CONVENTIONS, not thresholds measured on this machine.
"""

MIN_GROUP = 8
"""Below 8 winners or 8 losers, nothing is meaningful.

THIS IS A JUDGEMENT CALL AND MUST BE READ AS ONE. It is not derived from any
data on this machine. It is set where it is because Cliff's delta on n=5 per
group can only take 26 distinct values and a Mann-Whitney U on 5 vs 5 cannot
reach p<0.05 two-sided at any effect size short of perfect separation — so
below roughly this size the test is not capable of the answer it appears to
give. Raise it, never silently lower it.
"""

EFFECT_MIN = 0.33
"""Minimum |Cliff's delta| for a rule to count as meaningful.

0.33 is the conventional "medium" boundary in Romano et al.'s mapping of
Cliff's delta onto Cohen's d benchmarks (|d|~0.5). It is a CONVENTION ADOPTED
FROM THE LITERATURE, not something measured here. Interpreted: at delta=0.33,
a randomly drawn winner beats a randomly drawn loser on this feature about 2:1.
"""

ALPHA = 0.05
"""FDR level for the Benjamini-Hochberg q-values. Conventional."""

MIN_CONFIDENCE = 0.5
"""Drop rows whose harvest outlier_confidence is below this.

outlier_confidence degrades with the size of the channel baseline the score was
computed against; below 0.5 the channel had fewer than ~10 settled videos and
its median views-per-day is not a stable denominator.
"""

PROVENANCE_KEYS = frozenset((
    "src_width_px", "src_height_px", "src_aspect", "src_bytes",
    "jpeg_qsum_luma", "letterbox_frac", "source_kind_code",
))
"""Never tested.

These describe how the file ARRIVED, not how it was designed. Reporting that
winners have larger src_bytes would be a finding about which thumbnail variant
YouTube happened to serve (maxresdefault vs mqdefault), presented in the same
voice as a finding about face size. That is the single easiest way for this
module to launder an artefact into advice.
"""

WEAK_N = 20
"""Below 20 winners or 20 losers the grammar's confidence is 'weak'.

ANOTHER JUDGEMENT CALL, not a measured number. It sits above MIN_GROUP because
MIN_GROUP is the floor at which a test can return an answer at all, which is a
different question from the size at which the answer is worth acting on. It was
previously an unnamed literal buried in build_grammar; naming it is the point,
so that a reader can see it is chosen rather than derived.
"""

MIN_CHANNELS = 4
"""Below 4 contributing channels the result describes those channels, not a niche.

Also a judgement call. With one or two channels every "finding" is confounded
with that channel's own house style, audience and upload cadence, and the
grammar would be reporting one creator's habits in the voice of a niche law.
"""

MIN_QUARTILE_N = 4
"""Fewer than 4 finite values -> p25/p75 (and therefore target_lo/target_hi,
the IQR and `separation`) are reported as NaN rather than as numbers.

With n<4 no observation lies strictly inside either half of the sample, so the
"quartiles" are pure linear interpolation between the minimum and the maximum:
the IQR is just a rescaled range wearing the name of a robust statistic. At n=1
the old code returned target_lo == target_hi == the single value, which reads on
the page as an extraordinarily tight, extraordinarily confident target band.
"""

MIN_DECILE_N = 10
"""Fewer than 10 finite values -> p10/p90 are NaN.

A 10th percentile estimated from fewer than 10 points is interpolated between
the smallest and second-smallest observation; it describes a tail the sample
does not actually contain.
"""

MIN_STD_N = 3
"""Fewer than 3 finite values -> the sample standard deviation is NaN.

np.std(ddof=1) on two points is |a-b|/sqrt(2) — a rescaling of a single gap, not
a spread estimate, and printing it invites it to be read as one.
"""

_DEV_EPS = 1e-12


# ==========================================================================
# Small numeric helpers
# ==========================================================================

def _finite(values):
    """Return a float64 array of only the finite entries of `values`.

    Never raises. A bulk float64 cast is tried first because that is the fast
    path and covers every well-formed caller; if ANY element is non-numeric
    (a stray string in one cell of one measurement row) numpy raises for the
    whole array, and the old code let that ValueError escape and destroy the
    entire grammar over one bad cell. The fallback coerces element by element
    and drops what will not convert, which is the same treatment a missing
    value already gets.
    """
    if isinstance(values, np.ndarray):
        a = values
    else:
        a = np.asarray(list(values), dtype=object)
    try:
        a = a.astype(np.float64, copy=False)
    except (TypeError, ValueError):
        a = np.asarray([_f(v) for v in np.asarray(a).ravel()], dtype=np.float64)
    if a.size == 0:
        return np.empty(0, dtype=np.float64)
    return a[np.isfinite(a)]


def _pct(a, q, min_n=1):
    """Percentile, NaN on an empty array and NaN below `min_n` finite values.

    min_n is how the sample-size honesty of MIN_QUARTILE_N / MIN_DECILE_N is
    actually enforced: a percentile that the sample cannot support is returned
    as unavailable rather than as a number, because a printed number is
    indistinguishable from a measured one once it reaches the page.
    """
    if a.size < max(1, int(min_n)):
        return float("nan")
    return float(np.percentile(a, q))


def _f(x, default=float("nan")):
    """Coerce anything to a plain float; None / '' / unparseable -> default."""
    if x is None:
        return default
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v


def _jsonable(x):
    """Recursively convert numpy scalars and non-finite floats for json.dump.

    json.dump emits bare NaN / Infinity, which is invalid JSON and breaks every
    other reader. Non-finite becomes null.
    """
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        x = float(x)
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def _key_doc(key, warnings=None):
    """KEY_DOC entry for `key`, degrading to a labelled placeholder.

    measure.describe_key raises KeyError by design so a typo fails loudly. Here
    the keys come from measure.FEATURE_KEYS itself, so a KeyError means
    measure.py's KEY_DOC is incomplete — a real bug, but not one that should
    destroy an otherwise valid grammar. It is recorded in warnings instead.
    """
    try:
        d = _measure.describe_key(key)
        if isinstance(d, dict):
            return d
    except Exception as exc:  # KeyError, or KEY_DOC absent mid-build
        if warnings is not None:
            msg = "KEY_DOC missing entry for %r (%s)" % (key, type(exc).__name__)
            if msg not in warnings:
                warnings.append(msg)
    return {"unit": "unitless", "lo": None, "hi": None,
            "meaning": key.replace("_", " "), "higher_is": "neither",
            "family": key.split("_")[0]}


def _plain_name(key, doc):
    """Human phrase for a key: KEY_DOC label if there is one, else the meaning.

    All English about a metric comes from measure.KEY_DOC. Nothing in this file
    hand-writes prose per key, so renaming a metric changes one dictionary.
    """
    for field in ("label", "name", "short", "title"):
        v = doc.get(field)
        if isinstance(v, str) and v.strip():
            return v.strip()
    v = doc.get("meaning")
    if isinstance(v, str) and v.strip():
        s = v.strip()
        # KEY_DOC 'meaning' may be a full sentence; the summary line wants a
        # phrase, so take up to the first sentence break.
        for stop in (". ", "; ", " — ", " - "):
            if stop in s:
                s = s.split(stop, 1)[0]
                break
        return s if len(s) <= 60 else s[:57].rstrip() + "..."
    return key.replace("_", " ")


def _fmt_delta(v):
    """Cliff's delta for a human line, 'n/a' when it is undefined.

    '%+.2f' on a NaN prints '+nan', which reads as a value rather than as an
    absence — and delta is genuinely undefined whenever one group had no finite
    measurement for the key.
    """
    d = _f(v)
    return ("%+.2f" % d) if math.isfinite(d) else "n/a"


def _fmt(v, unit):
    """Format a measured value for a human line, with unit-appropriate digits."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "n/a"
    if unit in ("count",):
        return "%g" % round(float(v), 2)
    if unit in ("px", "K", "0-255", "L*"):
        return "%.1f" % float(v)
    if unit in ("deg",):
        return "%.1f" % float(v)
    av = abs(float(v))
    if av and (av < 0.001 or av >= 10000):
        return "%.3g" % float(v)
    return "%.3f" % float(v)


# ==========================================================================
# Group split
# ==========================================================================

def split_groups(merged_rows, win_at=DEFAULT_WIN, lose_at=DEFAULT_LOSE,
                 require_settled=True, min_confidence=MIN_CONFIDENCE):
    """Split merged (harvest + measurement) rows into winners, losers, middle.

    Returns (winners, losers, middle, dropped) where `dropped` is a dict of
    reason -> count. The counts are returned rather than swallowed because a
    grammar built on 14 of 60 harvested videos is a completely different claim
    from one built on 55 of 60, and that distinction has to be visible on the
    object rather than buried in a log line.

    Drop order is fixed so the counts partition the ROWS THIS FUNCTION SEES
    exactly once: a row is attributed to the FIRST reason that applies. Rows
    dropped earlier, by the harvest/measurement join, are counted there and
    folded in by build_grammar — see _join.

    Raises ValueError when win_at <= lose_at. That combination is not a strange
    preference, it is a swap: every row then satisfies `score >= win_at` before
    the loser branch is ever reached, so the winners group silently fills with
    losers and the grammar comes back inverted, confidently, with no warning.
    """
    win_at, lose_at = float(win_at), float(lose_at)
    if not (math.isfinite(win_at) and math.isfinite(lose_at)):
        raise ValueError("win_at and lose_at must be finite (got %r / %r)"
                         % (win_at, lose_at))
    if win_at <= lose_at:
        raise ValueError(
            "win_at (%.3f) must be greater than lose_at (%.3f); these look "
            "swapped, and swapping them silently inverts every rule in the "
            "grammar rather than failing" % (win_at, lose_at))

    winners, losers, middle = [], [], []
    dropped = {
        "measure_error": 0,
        "no_outlier_score": 0,
        "unsettled": 0,
        "low_confidence": 0,
    }
    for row in merged_rows:
        if row.get("measure_error"):
            dropped["measure_error"] += 1
            continue
        score = _f(row.get("outlier_score"))
        if not math.isfinite(score):
            dropped["no_outlier_score"] += 1
            continue
        if require_settled and not bool(row.get("settled", True)):
            dropped["unsettled"] += 1
            continue
        # An ABSENT confidence means the harvest never scored confidence at all,
        # and the row is taken at face value. A PRESENT but unparseable/NaN one
        # means the harvest tried and failed, which is exactly the case
        # min_confidence exists to exclude — the old code coerced both to 1.0
        # and let the second kind through as fully trusted.
        if "outlier_confidence" in row:
            conf = _f(row.get("outlier_confidence"))
            if (not math.isfinite(conf)) or conf < min_confidence:
                dropped["low_confidence"] += 1
                continue
        if score >= win_at:
            winners.append(row)
        elif score <= lose_at:
            losers.append(row)
        else:
            middle.append(row)
    return winners, losers, middle, dropped


# ==========================================================================
# Effect size and significance
# ==========================================================================

def cliffs_delta(a, b):
    """Cliff's delta: (#(a>b) - #(a<b)) / (len(a)*len(b)), NaN entries dropped.

    Positive means group `a` (the winners) runs higher on this feature.

    Chosen over Cohen's d because it assumes nothing about the shape of the
    distribution and is not moved by a single extreme thumbnail — and these
    populations reliably contain one blown-out white frame and one near-black
    one. It is also directly interpretable: delta = 0.6 means a randomly chosen
    winner exceeds a randomly chosen loser 80% of the time.

    Implemented with two sorted searches (O((n+m) log m)) rather than the naive
    O(n*m) double loop, so 133 keys stay fast on a few hundred rows.
    """
    x = _finite(a)
    y = _finite(b)
    if x.size == 0 or y.size == 0:
        return float("nan")
    ys = np.sort(y)
    # count of y strictly less than each x  -> x wins
    less = np.searchsorted(ys, x, side="left").sum(dtype=np.int64)
    # count of y <= each x -> everything above that is y strictly greater
    lte = np.searchsorted(ys, x, side="right").sum(dtype=np.int64)
    greater = x.size * ys.size - lte
    total = float(x.size) * float(ys.size)
    return float((less - greater) / total)


def _permutation_p(a, b, n_perm=4000, seed=0):
    """Two-sided permutation p-value on |Cliff's delta|. scipy-free fallback.

    Granularity floor is 1/(n_perm+1); with n_perm=4000 that is 2.5e-4, well
    below any alpha this module uses.
    """
    x = _finite(a)
    y = _finite(b)
    if x.size < 1 or y.size < 1:
        return float("nan")
    obs = abs(cliffs_delta(x, y))
    pool = np.concatenate([x, y])
    n = x.size
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if abs(cliffs_delta(pool[:n], pool[n:])) >= obs - 1e-12:
            hits += 1
    return float((hits + 1) / (n_perm + 1))


def _mwu_p(a, b):
    """Two-sided Mann-Whitney U p-value, or a permutation test without scipy.

    Returns 1.0 (not NaN) when every value in both groups is identical: there is
    genuinely nothing to detect, and a NaN here would propagate into the FDR
    pass and silently drop the key from the correction's denominator, which
    would make the OTHER keys look more significant than they are.
    """
    x = _finite(a)
    y = _finite(b)
    if x.size < 1 or y.size < 1:
        return float("nan")
    both = np.concatenate([x, y])
    if np.all(both == both[0]):
        return 1.0
    if HAVE_SCIPY:
        try:
            return float(_scipy_mwu(x, y, alternative="two-sided").pvalue)
        except Exception:
            pass
    return _permutation_p(x, y)


def fdr_adjust(rules, alpha=ALPHA, effect_min=EFFECT_MIN, min_group=MIN_GROUP):
    """Benjamini-Hochberg across every tested key; fills q_value, re-evaluates.

    Applied only AFTER every rule is built, because a BH q-value is a function
    of the whole set of p-values, not of one test. Without it, 133 simultaneous
    tests at alpha=0.05 yield roughly 7 findings on pure noise and the grammar's
    entire output becomes untrustworthy.

    effect_min and min_group are parameters and NOT read from the module
    constants, because this function re-runs _apply_meaningful and therefore has
    the last word on every rule's `meaningful` flag. When they defaulted to the
    module constants, a caller who passed a stricter min_group to build_grammar
    (or to `--min-group`) had it applied by rule_for_key and then silently
    overwritten back to 8 here: `python -m tools.thumbeng.grammar --min-group 40`
    on 30 winners still returned meaningful=True. The threshold has to travel
    with the call.

    `rules` is a dict of key -> rule dict (or any iterable of rule dicts).
    Mutates the rules in place. Returns the dict when given one, and otherwise
    the MATERIALISED LIST — returning the caller's iterable back would hand a
    generator caller an already-exhausted generator and lose every rule.
    """
    if isinstance(rules, dict):
        items = list(rules.values())
    else:
        items = list(rules)
        rules = items
    tested = [r for r in items if math.isfinite(_f(r.get("p_value")))]
    m = len(tested)
    if m:
        tested.sort(key=lambda r: _f(r["p_value"]))
        running = 1.0
        # Walk from the largest p downwards taking the running minimum, which is
        # the standard step-up form of BH.
        for i in range(m - 1, -1, -1):
            p = _f(tested[i]["p_value"])
            q = min(1.0, p * m / float(i + 1))
            running = min(running, q)
            tested[i]["q_value"] = float(running)
    for r in items:
        if not math.isfinite(_f(r.get("q_value"))):
            r["q_value"] = float("nan")
        _apply_meaningful(r, alpha=alpha, effect_min=effect_min,
                          min_group=min_group)
    return rules


def _apply_meaningful(rule, alpha=ALPHA, effect_min=EFFECT_MIN, min_group=MIN_GROUP):
    """Set rule['meaningful'], rule['reason'] and rule['weight'] from the stats.

    Reasons are checked in order of how badly they undermine the claim: sample
    size first (no statistic can rescue n=3), then effect size (a real but tiny
    difference is not advice), then the multiple-comparison-corrected p-value.
    """
    n_win = int(rule.get("n_win_finite") or 0)
    n_lose = int(rule.get("n_lose_finite") or 0)
    delta = _f(rule.get("delta"))
    q = _f(rule.get("q_value"))

    reason = ""
    if n_win < min_group or n_lose < min_group:
        reason = ("group too small: n_win=%d, n_lose=%d, need >= %d in each"
                  % (n_win, n_lose, min_group))
    elif not math.isfinite(delta):
        reason = "effect size undefined (a group had no finite values for this key)"
    elif abs(delta) < effect_min:
        reason = ("effect too small: |cliffs delta|=%.3f < %.2f"
                  % (abs(delta), effect_min))
    elif not math.isfinite(q):
        reason = "no p-value could be computed for this key"
    elif q >= alpha:
        reason = ("not significant after FDR correction: q=%.3f >= %.2f"
                  % (q, alpha))

    rule["meaningful"] = (reason == "")
    rule["reason"] = reason
    rule["weight"] = abs(delta) if (reason == "" and math.isfinite(delta)) else 0.0
    return rule


# ==========================================================================
# One rule
# ==========================================================================

def rule_for_key(key, win_vals, lose_vals, alpha=ALPHA, effect_min=EFFECT_MIN,
                 min_group=MIN_GROUP, doc=None, warnings=None):
    """Build the full grammar rule for one feature key.

    target_lo / target_hi are the winners' INTERQUARTILE RANGE, deliberately not
    their min/max. The middle half of what worked is a target a creator can aim
    at; the full range always includes the one weird thumbnail that won anyway,
    and quoting that as a target means quoting a band so wide it forbids
    nothing.

    Every dispersion statistic here is gated on the number of FINITE values in
    its own group (MIN_QUARTILE_N / MIN_DECILE_N / MIN_STD_N) and returned as
    NaN when the group is too small to support it. A rule can be built from one
    winner — rule_for_key is called for all 133 keys before anything is known
    about which will clear — and at n=1 the ungated code reported
    target_lo == target_hi == that single value, i.e. an infinitely tight target
    band, which is the most confident-looking output the module can produce and
    the least supported.

    q_value is left NaN here and filled by build_grammar's fdr_adjust pass, so
    `meaningful` as returned by this function is provisional.
    """
    doc = doc if doc is not None else _key_doc(key, warnings)
    # Materialise once: an iterator would be exhausted by the first pass and
    # every statistic after it would silently be computed on an empty group.
    win_vals = list(win_vals)
    lose_vals = list(lose_vals)
    w = _finite(win_vals)
    l = _finite(lose_vals)

    delta = cliffs_delta(w, l)
    p = _mwu_p(w, l)

    win_p25 = _pct(w, 25, min_n=MIN_QUARTILE_N)
    win_p75 = _pct(w, 75, min_n=MIN_QUARTILE_N)
    win_med, lose_med = _pct(w, 50), _pct(l, 50)
    iqr = win_p75 - win_p25 if (math.isfinite(win_p25) and math.isfinite(win_p75)) else float("nan")
    if math.isfinite(iqr) and iqr > _DEV_EPS and math.isfinite(win_med) and math.isfinite(lose_med):
        separation = abs(win_med - lose_med) / iqr
    else:
        # A zero-width winner IQR means every winner sat on the same value; a
        # ratio there is either 0/0 or infinite, neither of which is a number to
        # print, so it is reported as unavailable rather than as a huge effect.
        separation = float("nan")

    if math.isfinite(delta) and delta >= effect_min:
        direction = "higher"
    elif math.isfinite(delta) and delta <= -effect_min:
        direction = "lower"
    else:
        direction = "none"

    rule = {
        "key": key,
        "unit": doc.get("unit", "unitless"),
        "family": doc.get("family", ""),
        "label": _plain_name(key, doc),
        "higher_is": doc.get("higher_is", "neither"),

        "n_win": int(len(win_vals)),
        "n_lose": int(len(lose_vals)),
        "n_win_finite": int(w.size),
        "n_lose_finite": int(l.size),

        "win_median": win_med,
        "win_mean": float(np.mean(w)) if w.size else float("nan"),
        "win_std": float(np.std(w, ddof=1)) if w.size >= MIN_STD_N else float("nan"),
        "win_p10": _pct(w, 10, min_n=MIN_DECILE_N),
        "win_p25": win_p25,
        "win_p75": win_p75,
        "win_p90": _pct(w, 90, min_n=MIN_DECILE_N),

        "lose_median": lose_med,
        "lose_mean": float(np.mean(l)) if l.size else float("nan"),
        "lose_p25": _pct(l, 25, min_n=MIN_QUARTILE_N),
        "lose_p75": _pct(l, 75, min_n=MIN_QUARTILE_N),

        "delta": delta,
        "p_value": p,
        "q_value": float("nan"),
        "direction": direction,
        "target_lo": win_p25,
        "target_hi": win_p75,
        "target_center": win_med,
        "separation": separation,
        "meaningful": False,
        "reason": "",
        "weight": 0.0,
    }
    _apply_meaningful(rule, alpha=alpha, effect_min=effect_min, min_group=min_group)
    return rule


# ==========================================================================
# The grammar
# ==========================================================================

def _default_keys():
    """measure.FEATURE_KEYS minus the provenance keys. See PROVENANCE_KEYS."""
    return tuple(k for k in _measure.FEATURE_KEYS if k not in PROVENANCE_KEYS)


def _load_inputs(niche, measure_rows, harvest_rows):
    """Resolve rows from a niche name when they were not passed in.

    Imported lazily so a caller who already has rows in hand (selftest,
    critique.py) never pays for harvest.py's import or its yt-dlp path checks.
    """
    src = {"harvest_jsonl": None, "measurements_jsonl": None, "styles_json": None}
    if measure_rows is None:
        if niche is None:
            raise ValueError("build_grammar needs either niche= or measure_rows=")
        measure_rows = _measure.load_measurements(niche)
        src["measurements_jsonl"] = os.path.join(
            niche_dir(niche, create=False), "measurements.jsonl").replace("\\", "/")
    if harvest_rows is None and niche is not None:
        from . import harvest as _harvest
        harvest_rows = _harvest.load_harvest(niche)
        src["harvest_jsonl"] = os.path.join(
            niche_dir(niche, create=False), "harvest.jsonl").replace("\\", "/")
    return measure_rows, (harvest_rows or []), src


def _join(harvest_rows, measure_rows, warnings=None):
    """Inner-join harvest rows onto measurement rows on video_id == image_id.

    Returns (merged_rows, join_counts). The COUNTS are returned rather than
    discarded because harvest.join_measurements drops rows itself — rows whose
    measurement failed, and rows with no partner on either side — and the old
    code kept only `joined[0]`. Those rows then never reached split_groups, so
    grammar['groups']['dropped']['measure_error'] read 0 no matter how many
    measurements had failed and render_grammar printed "dropped: none" over a
    harvest that had lost half its rows in the join.

    Delegates to harvest.join_measurements when it is importable so the join
    lives in exactly one place. The local fallback exists only so a caller
    holding rows in memory (the selftest) does not have to import harvest at
    all; it is NOT identical — it cannot drop measure_error rows, which
    split_groups then counts instead — so taking it is recorded as a warning.
    Only import/shape failures fall back: the old bare `except Exception`
    also caught a genuine bug inside join_measurements and silently answered
    with a different join.
    """
    try:
        from . import harvest as _harvest
        joined = _harvest.join_measurements(harvest_rows, measure_rows)
    except (ImportError, AttributeError) as exc:
        if warnings is not None:
            warnings.append(
                "harvest.join_measurements unavailable (%s: %s); used the "
                "in-module fallback join, which does not drop measure_error "
                "rows before the split" % (type(exc).__name__, exc))
        joined = None

    if joined is not None:
        counts = {}
        if isinstance(joined, tuple):  # (rows, counts) form
            if len(joined) > 1 and isinstance(joined[1], dict):
                counts = dict(joined[1])
            joined = joined[0]
        return list(joined), counts

    by_id = {}
    for m in measure_rows:
        iid = m.get("image_id")
        if iid is not None:
            by_id[str(iid)] = m
    out = []
    n_unmatched_h = 0
    for h in harvest_rows:
        vid = h.get("video_id")
        if vid is None:
            n_unmatched_h += 1
            continue
        m = by_id.get(str(vid))
        if m is None:
            n_unmatched_h += 1
            continue
        merged = dict(m)
        merged.update(h)
        out.append(merged)
    matched = {str(r.get("image_id")) for r in out}
    counts = {
        "n_harvest": len(harvest_rows),
        "n_measure": len(measure_rows),
        "n_joined": len(out),
        "n_dropped_measure_error": 0,  # fallback cannot drop these; see above
        "n_harvest_unmatched": n_unmatched_h,
        "n_measure_unmatched": sum(1 for m in measure_rows
                                   if str(m.get("image_id")) not in matched),
        "join": "grammar_fallback",
    }
    return out, counts


def build_grammar(niche=None, measure_rows=None, harvest_rows=None, keys=None,
                  win_at=DEFAULT_WIN, lose_at=DEFAULT_LOSE, styles=None,
                  out_json=None, min_group=MIN_GROUP, effect_min=EFFECT_MIN,
                  alpha=ALPHA, min_confidence=MIN_CONFIDENCE,
                  require_settled=True, outlier_basis=None):
    """Build the "what works right now" object for a niche.

    Pass either a niche name (rows are loaded through the sanctioned readers) or
    the rows directly. `harvest_rows` may be a list of already-merged rows that
    carry both the FEATURE_KEYS and outlier_score, in which case the join is a
    no-op — that is the path the selftest and any in-memory caller take.

    `keys` defaults to measure.FEATURE_KEYS minus PROVENANCE_KEYS.
    """
    warnings = []
    notes = []

    # Validate before computing anything. Every one of these silently produces a
    # confident, wrong grammar rather than an error: alpha>=1 makes the FDR gate
    # unconditional, a negative effect_min makes the effect gate unconditional,
    # and min_group<1 removes the sample-size floor that is this module's whole
    # reason for existing. (win_at vs lose_at is checked in split_groups.)
    alpha = float(alpha)
    effect_min = float(effect_min)
    min_group = int(min_group)
    min_confidence = float(min_confidence)
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0, 1); got %r" % (alpha,))
    if not (0.0 <= effect_min <= 1.0):
        raise ValueError("effect_min is |Cliff's delta| and must be in [0, 1]; "
                         "got %r" % (effect_min,))
    if min_group < 1:
        raise ValueError("min_group must be >= 1; got %r" % (min_group,))
    if effect_min < EFFECT_MIN:
        warnings.append(
            "effect_min lowered to %.3f (module default %.2f); rules will "
            "clear on smaller effects than the documented convention"
            % (effect_min, EFFECT_MIN))
    if min_group < MIN_GROUP:
        warnings.append(
            "min_group lowered to %d (module default %d); below roughly %d per "
            "group the test is not capable of the answer it appears to give"
            % (min_group, MIN_GROUP, MIN_GROUP))

    measure_rows, harvest_rows, src = _load_inputs(niche, measure_rows, harvest_rows)
    n_measured = len(measure_rows)
    n_harvested = len(harvest_rows)

    join_counts = {}
    if harvest_rows:
        merged, join_counts = _join(harvest_rows, measure_rows, warnings)
    else:
        # No harvest side at all. The rows must already carry outlier_score or
        # split_groups will drop every one of them into no_outlier_score — which
        # is the correct, visible outcome rather than a silent empty grammar.
        merged = list(measure_rows)
        warnings.append("no harvest rows supplied; outlier scores must already "
                        "be on the measurement rows or nothing can be split")
    n_joined = len(merged)

    if keys is None:
        keys = _default_keys()
    keys = tuple(keys)

    winners, losers, middle, dropped = split_groups(
        merged, win_at=win_at, lose_at=lose_at,
        require_settled=require_settled, min_confidence=min_confidence)

    # Fold in what the JOIN dropped before split_groups ever saw the rows, so
    # `dropped` accounts for every harvested row exactly once instead of only
    # for the survivors of the join.
    dropped["measure_error"] += int(join_counts.get("n_dropped_measure_error") or 0)
    dropped["unmatched_harvest"] = int(join_counts.get("n_harvest_unmatched") or 0)
    dropped["unmatched_measurement"] = int(join_counts.get("n_measure_unmatched") or 0)

    def _channels(rows):
        return sorted({str(r.get("channel_id") or r.get("channel") or "?")
                       for r in rows} - {"?"})

    win_channels = _channels(winners)
    lose_channels = _channels(losers)
    all_channels = sorted(set(win_channels) | set(lose_channels))

    # --- the rules -------------------------------------------------------
    rules = {}
    for key in keys:
        doc = _key_doc(key, warnings)
        wv = [_f(r.get(key)) for r in winners]
        lv = [_f(r.get(key)) for r in losers]
        rules[key] = rule_for_key(key, wv, lv, alpha=alpha, effect_min=effect_min,
                                  min_group=min_group, doc=doc, warnings=warnings)
    # effect_min and min_group MUST be forwarded: fdr_adjust re-runs
    # _apply_meaningful and has the last word on every `meaningful` flag.
    fdr_adjust(rules, alpha=alpha, effect_min=effect_min, min_group=min_group)

    meaningful_keys = sorted(
        [k for k, r in rules.items() if r["meaningful"]],
        key=lambda k: -abs(_f(rules[k]["delta"], 0.0)))

    # --- honesty ---------------------------------------------------------
    n_win, n_lose = len(winners), len(losers)
    if n_win < min_group or n_lose < min_group:
        confidence = "none"
        warnings.insert(0,
            "SAMPLE TOO SMALL: %d winners / %d losers, need >= %d in each. "
            "Every rule is reported with meaningful=False. Nothing in this "
            "grammar is a finding." % (n_win, n_lose, min_group))
    elif n_win < WEAK_N or n_lose < WEAK_N or len(all_channels) < MIN_CHANNELS:
        confidence = "weak"
        warnings.append(
            "WEAK EVIDENCE: %d winners / %d losers across %d distinct channels "
            "(want >= %d per group and >= %d channels). Treat every rule as a "
            "hypothesis to re-check after a larger harvest."
            % (n_win, n_lose, len(all_channels), WEAK_N, MIN_CHANNELS))
    else:
        confidence = "moderate"

    if len(all_channels) and len(all_channels) < MIN_CHANNELS:
        warnings.append(
            "only %d distinct channel(s) contributed; this measures those "
            "channels, not the niche" % len(all_channels))
    if not HAVE_SCIPY:
        notes.append("scipy unavailable; p-values came from a 4000-shuffle "
                     "permutation test on |Cliff's delta|")

    notes.append(
        "outlier_score is views-per-day against the video's OWN channel median. "
        "It removes the subscriber-count confound and NOTHING ELSE: it cannot "
        "separate thumbnail effect from title, topic, upload timing or the "
        "algorithm. Every rule here is a correlation in a small observational "
        "sample, never an attribution.")
    notes.append(
        "confidence is capped at 'moderate' by design. No sample this pipeline "
        "can gather from public data supports the word 'strong'.")
    notes.append(
        "MIN_GROUP=%d and the %.2f/%.2f win/lose split are chosen conventions, "
        "not thresholds measured on this machine." % (min_group, win_at, lose_at))
    notes.append(
        "%d keys tested; Benjamini-Hochberg FDR applied at alpha=%.2f. Without "
        "it roughly %.0f of these would look significant on pure noise."
        % (len(keys), alpha, alpha * len(keys)))
    notes.append(
        "dispersion statistics are suppressed to null below the sample size "
        "that supports them: quartiles (and target_lo/target_hi/separation) "
        "need >= %d finite values, deciles >= %d, the standard deviation >= %d."
        % (MIN_QUARTILE_N, MIN_DECILE_N, MIN_STD_N))
    if middle:
        notes.append("%d row(s) fell in the discarded middle band (%.2f-%.2f x) "
                     "and contributed to neither group." % (len(middle), lose_at, win_at))

    style_summary = []
    if styles:
        for c in (styles.get("clusters") or []):
            style_summary.append({
                "cluster_id": c.get("cluster_id"),
                "label": c.get("label"),
                "size": c.get("size"),
                "median_outlier": _f(c.get("median_outlier")),
                "outlier_lift": _f(c.get("outlier_lift")),
                "rank": c.get("rank"),
            })
        src["styles_json"] = styles.get("_path") or src.get("styles_json")

    grammar = {
        "schema_version": SCHEMA_VERSION,
        "niche": niche,
        "generated_utc": utc_now(),
        "source": {
            "harvest_jsonl": src.get("harvest_jsonl"),
            "measurements_jsonl": src.get("measurements_jsonl"),
            "styles_json": src.get("styles_json"),
            "n_harvested": n_harvested,
            "n_measured": n_measured,
            "n_joined": n_joined,
            "join_counts": join_counts,
        },
        "thresholds": {
            "win_at": float(win_at),
            "lose_at": float(lose_at),
            "min_group": int(min_group),
            "effect_min": float(effect_min),
            "alpha": float(alpha),
            "min_confidence": float(min_confidence),
            "weak_n": int(WEAK_N),
            "min_channels": int(MIN_CHANNELS),
            "min_quartile_n": int(MIN_QUARTILE_N),
            "min_decile_n": int(MIN_DECILE_N),
            "settle_days": _settle_days(),
        },
        "groups": {
            "n_win": n_win,
            "n_lose": n_lose,
            "n_middle": len(middle),
            "dropped": dropped,
            "win_channels": win_channels,
            "lose_channels": lose_channels,
            "n_distinct_channels": len(all_channels),
        },
        "outlier_basis": outlier_basis or _outlier_basis(merged, warnings),
        # feature_keys is the FULL measure vocabulary at build time. load_grammar
        # compares it against the live measure.FEATURE_KEYS, because scoring a
        # candidate against a grammar built on a different vocabulary silently
        # compares the wrong columns.
        "feature_keys": list(_measure.FEATURE_KEYS),
        "tested_keys": list(keys),
        "rules": rules,
        "meaningful_keys": meaningful_keys,
        "style_summary": style_summary,
        "warnings": warnings,
        "notes": notes,
        "confidence": confidence,
    }

    if out_json is None and niche is not None:
        out_json = os.path.join(niche_dir(niche), "grammar.json").replace("\\", "/")
    if out_json:
        save_grammar(grammar, out_json)
        _record_stage(niche, grammar, out_json)
    return grammar


def _settle_days():
    """SETTLE_DAYS from harvest.py, or None when harvest is not importable."""
    try:
        from . import harvest as _harvest
        return int(_harvest.SETTLE_DAYS)
    except Exception:
        return None


def _outlier_basis(rows, warnings=None):
    """The basis string carried by the harvested rows, so a later reader knows
    exactly what outlier_score meant. Never invented here.

    Returning the FIRST row's basis was wrong when the rows carry more than one:
    outlier_score would then mean different things in different rows and the
    grammar would print a single basis line asserting they all meant the same
    thing. All distinct bases are reported, and the mix is warned about.
    """
    seen = []
    for r in rows:
        b = r.get("outlier_basis")
        if isinstance(b, str) and b and b not in seen:
            seen.append(b)
    if not seen:
        return "unknown"
    if len(seen) > 1:
        if warnings is not None:
            warnings.append(
                "rows carry %d DIFFERENT outlier_basis values (%s); "
                "outlier_score does not mean the same thing in every row and "
                "the two sides are not comparable"
                % (len(seen), ", ".join(sorted(seen))))
        return "MIXED: " + " | ".join(sorted(seen))
    return seen[0]


def _record_stage(niche, grammar, out_json):
    """Append this stage to run.json. Never fatal — a manifest write failing
    must not lose a grammar that was computed correctly."""
    if niche is None:
        return
    try:
        from . import run_manifest
        run_manifest(niche, "grammar",
                     {"win_at": grammar["thresholds"]["win_at"],
                      "lose_at": grammar["thresholds"]["lose_at"],
                      "out_json": out_json},
                     {"n_win": grammar["groups"]["n_win"],
                      "n_lose": grammar["groups"]["n_lose"],
                      "n_meaningful": len(grammar["meaningful_keys"]),
                      "confidence": grammar["confidence"]})
    except Exception as exc:
        grammar.setdefault("warnings", []).append(
            "run.json not updated: %s: %s" % (type(exc).__name__, exc))


# ==========================================================================
# Human output
# ==========================================================================

def grammar_summary(grammar, top_n=12):
    """One line per meaningful rule, formatted from measure.KEY_DOC.

    Shape, fixed here so critique.py's headlines are built from one phrasing:
        'largest face: winners 0.180-0.270 (median 0.220), losers median 0.090
         [delta +0.61, n=14/11]'

    When grammar['confidence'] == 'none' the FIRST line returned is the warning,
    not a finding — a reader skimming the top of the output must not be able to
    mistake a 9-video grammar for an answer.
    """
    lines = []
    if grammar.get("confidence") == "none":
        for w in grammar.get("warnings", []):
            lines.append("!! " + w)
        if not lines:
            lines.append("!! no meaningful evidence: sample too small")

    rules = grammar.get("rules") or {}
    # Only keys that actually have a rule: a hand-built or older grammar can
    # name a meaningful key it does not carry, and the old grammar["rules"][key]
    # turned that into a KeyError in the middle of printing a report.
    mk = [k for k in (grammar.get("meaningful_keys") or []) if k in rules]
    if not mk:
        lines.append("no rule cleared sample size + effect size + FDR. "
                     "That is a finding about the sample, not about design.")
        return lines

    for key in mk[:top_n]:
        r = rules[key]
        unit = r.get("unit", "unitless")
        lines.append(
            "%s: winners %s-%s (median %s), losers median %s  [delta %+.2f, n=%d/%d, q=%s]"
            % (r.get("label") or key,
               _fmt(r.get("target_lo"), unit), _fmt(r.get("target_hi"), unit),
               _fmt(r.get("target_center"), unit), _fmt(r.get("lose_median"), unit),
               _f(r.get("delta"), 0.0),
               int(r.get("n_win_finite") or 0), int(r.get("n_lose_finite") or 0),
               ("%.4f" % _f(r.get("q_value"))) if math.isfinite(_f(r.get("q_value"))) else "n/a"))
    if len(mk) > top_n:
        lines.append("... and %d more meaningful rules" % (len(mk) - top_n))
    return lines


def render_grammar(grammar, top_n=12, show_near_misses=6):
    """Full human-printable block: header, groups, findings, near misses.

    The near-miss section exists so the reader can see WHAT WAS TESTED AND
    REJECTED. A report that only prints its hits looks far more certain than it
    is; printing the strongest rejected rules with their reasons is the cheapest
    honest counterweight.
    """
    g = grammar
    out = []
    out.append("=" * 78)
    out.append("NICHE GRAMMAR  niche=%s  generated=%s" % (g.get("niche"), g.get("generated_utc")))
    out.append("=" * 78)
    # .get throughout: this renders whatever load_grammar handed back, including
    # an older or hand-built object, and a report must not die half-printed on a
    # missing bookkeeping key.
    gr = g.get("groups") or {}
    th = g.get("thresholds") or {}
    out.append("confidence: %s" % str(g.get("confidence", "?")).upper())
    out.append("groups: %d winners (>=%.2fx own-channel pace), %d losers (<=%.2fx), "
               "%d discarded middle"
               % (_f(gr.get("n_win"), 0), _f(th.get("win_at"), float("nan")),
                  _f(gr.get("n_lose"), 0), _f(th.get("lose_at"), float("nan")),
                  _f(gr.get("n_middle"), 0)))
    out.append("channels: %d distinct contributing" % _f(gr.get("n_distinct_channels"), 0))
    src = g.get("source") or {}
    out.append("source: %d harvested / %d measured / %d joined"
               % (_f(src.get("n_harvested"), 0), _f(src.get("n_measured"), 0),
                  _f(src.get("n_joined"), 0)))
    drops = ", ".join("%s=%d" % (k, v)
                      for k, v in sorted((gr.get("dropped") or {}).items()) if v)
    out.append("dropped: %s" % (drops if drops else "none"))
    out.append("outlier basis: %s" % g.get("outlier_basis"))
    out.append("tested %d keys | thresholds: min_group=%d effect_min=%.2f alpha=%.2f"
               % (len(g.get("tested_keys") or []), _f(th.get("min_group"), 0),
                  _f(th.get("effect_min"), float("nan")),
                  _f(th.get("alpha"), float("nan"))))
    out.append("")

    if g.get("warnings"):
        out.append("-- WARNINGS " + "-" * 66)
        for w in g["warnings"]:
            out.append("  !! " + w)
        out.append("")

    out.append("-- WHAT WORKS RIGHT NOW " + "-" * 54)
    for line in grammar_summary(g, top_n=top_n):
        if line.startswith("!! "):
            continue  # already printed in the warnings block
        out.append("  " + line)
    out.append("")

    if show_near_misses:
        # Ranked by (|delta|, then GROUP SIZE) rather than |delta| alone. Cliff's
        # delta saturates at +/-1.00 the moment two small groups happen not to
        # overlap, so on a 6-vs-6 sample dozens of keys tie at 1.00 and a
        # |delta|-only sort filled this block with the least-supported rows in an
        # arbitrary order, reading exactly like a ranked findings list. n is now
        # printed on every line for the same reason.
        scored = []
        for k, r in (g.get("rules") or {}).items():
            if r.get("meaningful"):
                continue
            nmin = min(int(r.get("n_win_finite") or 0), int(r.get("n_lose_finite") or 0))
            d = abs(_f(r.get("delta")))
            # A key with an UNDEFINED delta (one group had no finite value for
            # it) sorted to the TOP of a block headed "largest raw gaps",
            # because every NaN comparison is False and the sort left them where
            # they started. Rank them last: an absent measurement is the
            # smallest possible amount of evidence, not the largest.
            scored.append((d if math.isfinite(d) else -1.0, nmin, k, r))
        scored.sort(reverse=True, key=lambda t: (t[0], t[1]))
        if scored:
            out.append("-- TESTED AND REJECTED (NOT findings; each line says why) " + "-" * 20)
            for _, _, k, r in scored[:show_near_misses]:
                unit = r.get("unit", "unitless")
                out.append("  %s: win median %s vs lose median %s  "
                           "[delta %s, n=%d/%d] -- %s"
                           % (r.get("label") or k,
                              _fmt(r.get("win_median"), unit),
                              _fmt(r.get("lose_median"), unit),
                              _fmt_delta(r.get("delta")),
                              int(r.get("n_win_finite") or 0),
                              int(r.get("n_lose_finite") or 0),
                              r.get("reason") or "rejected"))
            out.append("")

    if g.get("style_summary"):
        out.append("-- STYLES " + "-" * 68)
        for s in g["style_summary"]:
            out.append("  #%s %-28s n=%-3s median_outlier=%s lift=%s"
                       % (s["cluster_id"], s["label"], s["size"],
                          _fmt(s["median_outlier"], "ratio"), _fmt(s["outlier_lift"], "ratio")))
        out.append("")

    out.append("-- NOTES " + "-" * 69)
    for n in g.get("notes", []):
        out.append("  * " + n)
    out.append("=" * 78)
    return "\n".join(out)


# ==========================================================================
# Persistence
# ==========================================================================

def save_grammar(grammar, path):
    """The only sanctioned writer of grammar.json (atomic, via write_json)."""
    return write_json(path, _jsonable(grammar))


def load_grammar(path_or_niche):
    """The only sanctioned reader of grammar.json.

    Raises on a schema_version mismatch, and on a feature_keys set that does not
    match the current measure.FEATURE_KEYS — scoring a candidate against a
    grammar built on a different vocabulary silently compares the wrong columns,
    which produces confident numbers about the wrong thing.
    """
    path = str(path_or_niche)
    if not path.lower().endswith(".json"):
        path = niche_dir(path_or_niche, create=False) + "/grammar.json"
    # niche_dir returns forward slashes; os.path.join was appending a backslash
    # on Windows, so the error message below quoted a mixed-separator path that
    # does not match anything the rest of the engine prints. Normalise both the
    # constructed and the caller-supplied form.
    path = path.replace("\\", "/")
    g = read_json(path, default=None)
    if g is None:
        raise FileNotFoundError("no grammar at %s" % path)
    sv = g.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise ValueError("grammar.json schema_version %r != current %r (%s) — "
                         "rebuild it, do not read it" % (sv, SCHEMA_VERSION, path))
    fk = g.get("feature_keys")
    if fk is not None and list(fk) != list(_measure.FEATURE_KEYS):
        raise ValueError(
            "grammar.json was built on a different FEATURE_KEYS vocabulary "
            "(%d keys stored vs %d live) — rebuild it (%s)"
            % (len(fk), len(_measure.FEATURE_KEYS), path))
    return g


# ==========================================================================
# Selftest
# ==========================================================================

def _synthetic_checks():
    """The four assertions the contract names, plus their evidence lines."""
    checks = []
    rng = np.random.default_rng(7)

    # 1. Cliff's delta must recover known answers.
    a = np.array([10., 11., 12., 13., 14.])
    b = np.array([1., 2., 3., 4., 5.])
    d_sep = cliffs_delta(a, b)
    d_id = cliffs_delta(a, a)
    same_a = rng.normal(0, 1, 400)
    same_b = rng.normal(0, 1, 400)
    d_same = cliffs_delta(same_a, same_b)
    checks.append(("cliffs_delta separated == +1",
                   abs(d_sep - 1.0) < 1e-12, "delta=%+.6f" % d_sep))
    checks.append(("cliffs_delta identical == 0",
                   abs(d_id) < 1e-12, "delta=%+.6f" % d_id))
    checks.append(("cliffs_delta same-distribution ~ 0",
                   abs(d_same) < 0.15, "delta=%+.4f" % d_same))

    # 2/3. A real 2-sigma shift: meaningful at n=20, not meaningful at n=5.
    def _shift_rule(n):
        w = rng.normal(2.0, 1.0, n)
        l = rng.normal(0.0, 1.0, n)
        r = rule_for_key("lum_mean", w, l,
                         doc={"unit": "L*", "family": "luminance",
                              "meaning": "mean luminance", "higher_is": "neither"})
        fdr_adjust({"lum_mean": r})
        return r

    r20 = _shift_rule(20)
    checks.append(("2-sigma shift at n=20 is meaningful",
                   r20["meaningful"] is True,
                   "delta=%+.3f q=%.5f" % (r20["delta"], r20["q_value"])))
    r5 = _shift_rule(5)
    checks.append(("same shift at n=5 is NOT meaningful",
                   (r5["meaningful"] is False) and ("group too small" in r5["reason"]),
                   "reason=%r" % r5["reason"]))

    # 4. FDR must bury 130 pure-noise keys.
    noise = {}
    for i in range(130):
        w = rng.normal(0, 1, 24)
        l = rng.normal(0, 1, 24)
        noise["noise_%03d" % i] = rule_for_key(
            "noise_%03d" % i, w, l,
            doc={"unit": "unitless", "family": "noise", "meaning": "pure noise",
                 "higher_is": "neither"})
    raw_hits = sum(1 for r in noise.values() if _f(r["p_value"]) < ALPHA)
    fdr_adjust(noise)
    fdr_hits = sum(1 for r in noise.values() if r["meaningful"])
    checks.append(("FDR buries 130 pure-noise keys",
                   fdr_hits == 0,
                   "raw p<0.05: %d/130  ->  meaningful after BH: %d/130"
                   % (raw_hits, fdr_hits)))
    return checks


def _planted_signal_check(n_per_group=30, seed=11):
    """Full end-to-end run on the REAL 133-key vocabulary with ONE planted signal.

    This is the check that matters most. Every key is pure noise except:
      * face_area_frac_largest, given a genuine winners-vs-losers separation;
      * src_bytes, given an enormous separation — and src_bytes is a
        PROVENANCE key, so a correct build_grammar must never test it at all.

    A grammar that comes back reporting a dozen findings here is manufacturing
    them, and a grammar that reports src_bytes is laundering a YouTube encoder
    artefact into design advice. Both failures are invisible on real data; this
    is the only place they can be caught.

    Returns (checks, grammar) so the caller can print the grammar too.
    """
    rng = np.random.default_rng(seed)
    keys = list(_measure.FEATURE_KEYS)
    signal_key = "face_area_frac_largest" if "face_area_frac_largest" in keys else keys[0]

    rows = []
    for i in range(2 * n_per_group):
        win = i < n_per_group
        r = {
            "image_id": "syn%03d" % i, "video_id": "syn%03d" % i,
            "channel_id": "UC_synthetic_%d" % (i % 6),
            "channel": "synthetic %d" % (i % 6),
            "settled": True, "outlier_confidence": 1.0,
            "outlier_score": 2.0 if win else 0.4,
            "outlier_basis": "SELFTEST_SYNTHETIC_planted_signal",
        }
        for k in keys:
            r[k] = float(rng.normal(0.0, 1.0))
        r[signal_key] = float(rng.normal(0.22 if win else 0.09, 0.04))
        r["src_bytes"] = float(rng.normal(900000.0 if win else 100000.0, 1000.0))
        rows.append(r)

    g = build_grammar(niche=None, measure_rows=rows, harvest_rows=rows, out_json=None)
    mk = g["meaningful_keys"]
    checks = [
        ("planted signal is recovered", signal_key in mk,
         "meaningful=%r" % (mk[:4],)),
        ("provenance key is never tested", "src_bytes" not in g["tested_keys"],
         "src_bytes had a 9x planted gap and was excluded by PROVENANCE_KEYS"),
        ("noise does not become findings", len(mk) <= 3,
         "%d meaningful out of %d tested keys" % (len(mk), len(g["tested_keys"]))),
    ]
    return checks, g


def _hardening_checks():
    """One check per defect found in the 2026-08-30 hardening pass.

    Each of these FAILED before that pass. They live here, not in a comment,
    because every one of them was silent: the module returned a number and the
    number was wrong. A fix without a check is just this session's repair.
    """
    checks = []
    rng = np.random.default_rng(23)

    # A real 30-vs-30 signal, used by the threshold-forwarding checks below.
    def _rows(n=30, key="lum_mean"):
        rows = []
        for i in range(2 * n):
            win = i < n
            rows.append({
                "image_id": "h%03d" % i, "video_id": "h%03d" % i,
                "channel_id": "UC_h%d" % (i % 6), "settled": True,
                "outlier_confidence": 1.0,
                "outlier_score": 2.0 if win else 0.4,
                "outlier_basis": "SELFTEST_SYNTHETIC_hardening",
                key: float(rng.normal(2.0 if win else 0.0, 1.0)),
            })
        return rows

    rows = _rows()
    base = build_grammar(niche=None, measure_rows=rows, harvest_rows=rows,
                         keys=("lum_mean",), out_json=None)
    strict = build_grammar(niche=None, measure_rows=rows, harvest_rows=rows,
                           keys=("lum_mean",), out_json=None, min_group=40)
    checks.append((
        "min_group is honoured end to end",
        base["rules"]["lum_mean"]["meaningful"] is True
        and strict["rules"]["lum_mean"]["meaningful"] is False
        and "group too small" in strict["rules"]["lum_mean"]["reason"],
        "n=30/30: min_group=8 -> meaningful, min_group=40 -> %r"
        % (strict["rules"]["lum_mean"]["reason"][:44],)))

    loose = build_grammar(niche=None, measure_rows=rows, harvest_rows=rows,
                          keys=("lum_mean",), out_json=None, effect_min=0.99)
    checks.append((
        "effect_min is honoured end to end",
        loose["rules"]["lum_mean"]["meaningful"] is False
        and "effect too small" in loose["rules"]["lum_mean"]["reason"]
        and "0.99" in loose["rules"]["lum_mean"]["reason"],
        "effect_min=0.99 -> %r" % (loose["rules"]["lum_mean"]["reason"][:44],)))

    # Swapped thresholds must raise, not invert the grammar silently.
    try:
        split_groups([{"outlier_score": 1.0}], win_at=0.8, lose_at=1.5)
        swapped_ok, ev = False, "no exception raised"
    except ValueError as exc:
        swapped_ok, ev = True, "ValueError: %s" % str(exc)[:46]
    checks.append(("swapped win/lose thresholds raise", swapped_ok, ev))

    # alpha outside (0,1) makes the FDR gate unconditional.
    try:
        build_grammar(niche=None, measure_rows=rows, harvest_rows=rows,
                      keys=("lum_mean",), out_json=None, alpha=5.0)
        alpha_ok, ev = False, "alpha=5.0 accepted"
    except ValueError as exc:
        alpha_ok, ev = True, "ValueError: %s" % str(exc)[:46]
    checks.append(("alpha outside (0,1) raises", alpha_ok, ev))

    # Statistics no sample size supports.
    r1 = rule_for_key("lum_mean", [5.0], [1.0],
                      doc={"unit": "L*", "family": "f", "meaning": "m",
                           "higher_is": "neither"})
    r2 = rule_for_key("lum_mean", [5.0, 7.0], [1.0, 2.0],
                      doc={"unit": "L*", "family": "f", "meaning": "m",
                           "higher_is": "neither"})
    checks.append((
        "n=1 emits no target band",
        (not math.isfinite(_f(r1["target_lo"])))
        and (not math.isfinite(_f(r1["target_hi"])))
        and (not math.isfinite(_f(r1["win_p10"]))),
        "target_lo=%r win_p10=%r (was 5.0 / 5.0)"
        % (r1["target_lo"], r1["win_p10"])))
    checks.append((
        "n=2 emits no standard deviation",
        not math.isfinite(_f(r2["win_std"])),
        "win_std=%r (was 1.414 from two points)" % (r2["win_std"],)))

    # fdr_adjust must not hand back an exhausted iterator.
    gen = (rule_for_key("k%d" % i, [1., 2., 3.], [4., 5., 6.],
                        doc={"unit": "unitless", "family": "f", "meaning": "m",
                             "higher_is": "neither"}) for i in range(3))
    got = fdr_adjust(gen)
    checks.append(("fdr_adjust survives a generator", len(list(got)) == 3,
                   "returned %d rules (was 0)" % len(list(got))))

    # One non-numeric cell must not destroy the grammar.
    try:
        bad = _finite([1.0, "not a number", 3.0, None])
        finite_ok = list(bad) == [1.0, 3.0]
        ev = "-> %r" % (list(bad),)
    except Exception as exc:
        finite_ok, ev = False, "RAISED %s" % type(exc).__name__
    checks.append(("a non-numeric cell does not raise", finite_ok, ev))

    # Rows the JOIN dropped must appear in `dropped`, not vanish.
    m_rows = [{"image_id": "ok1", "lum_mean": 1.0},
              {"image_id": "ok2", "lum_mean": 2.0},
              {"image_id": "bad", "measure_error": "unreadable jpeg"}]
    h_rows = [{"video_id": "ok1", "outlier_score": 2.0, "settled": True},
              {"video_id": "ok2", "outlier_score": 0.4, "settled": True},
              {"video_id": "bad", "outlier_score": 2.0, "settled": True},
              {"video_id": "never_measured", "outlier_score": 2.0, "settled": True}]
    gj = build_grammar(niche=None, measure_rows=m_rows, harvest_rows=h_rows,
                       keys=("lum_mean",), out_json=None)
    dj = gj["groups"]["dropped"]
    checks.append((
        "join drops are counted, not hidden",
        int(dj.get("measure_error") or 0) >= 1
        and int(dj.get("unmatched_harvest") or 0) >= 1,
        "measure_error=%s unmatched_harvest=%s (both were always 0)"
        % (dj.get("measure_error"), dj.get("unmatched_harvest"))))

    # A present-but-unparseable confidence is not a trusted 1.0.
    _, _, _, d_conf = split_groups(
        [{"outlier_score": 2.0, "outlier_confidence": "high"}])
    checks.append((
        "unparseable outlier_confidence drops the row",
        int(d_conf.get("low_confidence") or 0) == 1,
        "low_confidence=%s (was silently coerced to 1.0)"
        % d_conf.get("low_confidence")))

    # A mixed outlier_basis must be reported as mixed.
    mixed = [dict(r) for r in rows]
    for r in mixed[:5]:
        r["outlier_basis"] = "A_DIFFERENT_BASIS"
    gm = build_grammar(niche=None, measure_rows=mixed, harvest_rows=mixed,
                       keys=("lum_mean",), out_json=None)
    checks.append((
        "mixed outlier_basis is flagged",
        str(gm["outlier_basis"]).startswith("MIXED:")
        and any("DIFFERENT outlier_basis" in w for w in gm["warnings"]),
        "outlier_basis=%r" % (str(gm["outlier_basis"])[:46],)))

    # render_grammar must survive a partial object rather than KeyError.
    try:
        txt = render_grammar({"rules": {}, "confidence": "none",
                              "meaningful_keys": ["absent_key"]})
        render_ok, ev = ("NICHE GRAMMAR" in txt), "%d lines" % len(txt.splitlines())
    except Exception as exc:
        render_ok, ev = False, "RAISED %s: %s" % (type(exc).__name__, exc)
    checks.append(("render survives a partial grammar", render_ok, ev))

    return checks


_READY = "D:/Boyd Clips/READY-TO-POST"

# Filenames Nathan kept / approved as the final version of that thumbnail.
# This is a REAL label that exists on disk (his own revision naming), not an
# invented view count. It is used ONLY to exercise the machinery end-to-end;
# see the loud warning attached to the grammar it produces.
_KEPT_SUFFIXES = ("_V2", "_FINAL", "_APPROVED")


def _ready_to_post_grammar():
    """Derive a grammar from D:/Boyd Clips/READY-TO-POST and return it.

    HONESTY, stated here and stamped onto the object: these are Nathan's own
    local files. They have NO public view data, so there is no real
    outlier_score for any of them. To exercise the whole pipeline on real
    measurements, the split is taken from his own revision naming — a file
    ending _V2 / _FINAL / _APPROVED is the version he kept, the bare name is the
    version it superseded. That is a real signal about his preference and a
    completely fake proxy for audience performance. The grammar's own machinery
    then correctly reports that n=6/6 is below MIN_GROUP and that NOTHING in it
    is a finding, which is precisely the behaviour this selftest exists to show.
    """
    if not os.path.isdir(_READY):
        return None, "READY-TO-POST folder not on this machine: %s" % _READY

    # Guarded because this reads a real folder on a real drive: D: can be
    # disconnected mid-walk, a file can be locked by another process, and
    # measure_folder itself raises on a directory it cannot enumerate (only
    # per-file failures are caught inside it, as measure_error rows). None of
    # that is a fault in grammar.py, so it must not fail grammar.py's selftest.
    try:
        rows = _measure.measure_folder(_READY, pattern="*.jpg", source_kind="local",
                                       skip_existing=False, progress=False)
    except Exception as exc:
        return None, ("could not measure %s: %s: %s"
                      % (_READY, type(exc).__name__, exc))
    if not rows:
        return None, "no .jpg measured in %s" % _READY

    # measure_folder returns a measure_error row for an unreadable/corrupt file
    # rather than raising. Those carry no features, so they are dropped here and
    # reported, instead of being counted as videos that contributed evidence.
    n_err = sum(1 for r in rows if r.get("measure_error"))
    rows = [r for r in rows if not r.get("measure_error")]
    if not rows:
        return None, ("every .jpg in %s failed to measure (%d file(s))"
                      % (_READY, n_err))

    merged = []
    for r in rows:
        stem = str(r.get("image_id", ""))
        kept = stem.upper().endswith(_KEPT_SUFFIXES)
        m = dict(r)
        m.update({
            "video_id": stem,
            "channel_id": "LOCAL_TEXAS_TRIAL_TRACKER",
            "channel": "Texas Trial Tracker (local files)",
            "settled": True,
            "outlier_confidence": 1.0,
            # 2.0 / 0.5 are LABEL ENCODINGS, not measured pace. They exist only
            # to place the row on one side of the win/lose split.
            "outlier_score": 2.0 if kept else 0.5,
            "outlier_basis": "SELFTEST_LABEL_SPLIT_kept_filename_vs_superseded__NOT_VIEW_DATA",
        })
        merged.append(m)

    g = build_grammar(niche=None, measure_rows=rows, harvest_rows=merged,
                      out_json=None)
    g["niche"] = "READY-TO-POST (selftest, local files)"
    g["warnings"].insert(0,
        "THIS GRAMMAR HAS NO AUDIENCE DATA. The winner/loser split came from "
        "Nathan's own filename revisions (_V2/_FINAL/_APPROVED = kept), NOT "
        "from views. It demonstrates the machinery; it is not evidence about "
        "what works.")
    return g, None


def selftest():
    """Prove the module can fail before believing it when it passes."""
    checks = _synthetic_checks()

    print("--- synthetic checks " + "-" * 55)
    for name, ok, evidence in checks:
        print("  [%s] %-42s  %s" % ("ok" if ok else "BLIND", name, evidence))
    print()

    hardening = _hardening_checks()
    print("--- hardening checks (each of these failed before 2026-08-30) " + "-" * 14)
    for name, ok, evidence in hardening:
        print("  [%s] %-42s  %s" % ("ok" if ok else "BLIND", name, evidence))
    checks.extend(hardening)
    print()

    print("--- planted-signal run on the real 133-key vocabulary " + "-" * 22)
    planted, g_planted = _planted_signal_check()
    for name, ok, evidence in planted:
        print("  [%s] %-42s  %s" % ("ok" if ok else "BLIND", name, evidence))
    checks.extend(planted)
    print()
    for line in grammar_summary(g_planted, top_n=4):
        print("    " + line)
    print()

    g, err = _ready_to_post_grammar()
    if err:
        print("READY-TO-POST grammar SKIPPED: %s" % err)
        ready_ok = True  # not a failure of this module
    else:
        print(render_grammar(g, top_n=12, show_near_misses=6))
        print()
        # The honesty behaviour is itself asserted: with 6 vs 6 the module MUST
        # refuse to call anything meaningful. If it ever does, this selftest is
        # the thing that catches it.
        ready_ok = (g["confidence"] == "none"
                    and len(g["meaningful_keys"]) == 0
                    and any("SAMPLE TOO SMALL" in w for w in g["warnings"]))
        print("  [%s] %-42s  n_win=%d n_lose=%d meaningful=%d confidence=%s"
              % ("ok" if ready_ok else "BLIND",
                 "READY-TO-POST refuses to claim a finding",
                 g["groups"]["n_win"], g["groups"]["n_lose"],
                 len(g["meaningful_keys"]), g["confidence"]))
        checks.append(("READY-TO-POST refuses to claim a finding", ready_ok, ""))
        print()

    ok = all(c for _, c, *_ in checks)

    def _tag(name):
        """Compact, DISTINCT label per check. Three of the checks start with the
        same word, and a summary line reading 'cliffs_delta=ok cliffs_delta=ok'
        tells a reader nothing about which one went blind. Operator tokens
        ('==', '+1', '~') are dropped so the tag stays readable."""
        words = [w.strip("|,.").lower() for w in name.split()]
        words = [w for w in words if any(ch.isalpha() for ch in w)]
        return "-".join(words[:3]) or "check"

    print(("SELFTEST_PASS  " if ok else "SELFTEST_FAIL  ")
          + " ".join(("%s=%s" % (_tag(n), "ok" if c else "BLIND"))
                     for n, c, *_ in checks))
    return 0 if ok else 1


# ==========================================================================
# CLI
# ==========================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m tools.thumbeng.grammar",
        description="Build the niche grammar from measurements + outlier scores.")
    ap.add_argument("--niche", help="niche name (resolves through niche_dir)")
    ap.add_argument("--win", type=float, default=DEFAULT_WIN,
                    help="winner threshold on outlier_score (default %.2f)" % DEFAULT_WIN)
    ap.add_argument("--lose", type=float, default=DEFAULT_LOSE,
                    help="loser threshold on outlier_score (default %.2f)" % DEFAULT_LOSE)
    ap.add_argument("--min-group", type=int, default=MIN_GROUP)
    ap.add_argument("--top", type=int, default=12, help="rules to print")
    ap.add_argument("--json", dest="out_json", default=None,
                    help="override the output path for grammar.json")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.niche:
        ap.error("--niche is required (or use --selftest)")

    g = build_grammar(niche=args.niche, win_at=args.win, lose_at=args.lose,
                      min_group=args.min_group, out_json=args.out_json)
    if not args.quiet:
        print(render_grammar(g, top_n=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
