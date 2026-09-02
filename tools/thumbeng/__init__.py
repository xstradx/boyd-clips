# -*- coding: utf-8 -*-
"""thumbeng - shared foundation for the thumbnail engine.

Nothing here does image work. This module exists so that the five modules of
the engine cannot invent five different path schemes, five JSONL writers and
five timestamp formats.

MEASURED ENVIRONMENT FACTS (verified on this machine 2026-08-30):
  * python 3.14.2, numpy 2.5.2, cv2 5.0.0, sklearn 1.9.0, scipy 1.18.0, PIL,
    requests 2.33.1.
  * pandas is NOT installed. Every table here is stdlib json + csv.
  * numpy 2.5 removed ndarray.ptp(); use np.ptp(a). Nothing in this file uses
    numpy at all, deliberately - the foundation must import even if numpy is
    broken, so a path bug never masquerades as an import error.
  * torch is not on this interpreter.

IMPORT DISCIPLINE - a real collision, not a hypothetical.
tools/harvest.py already exists and is an unrelated courtroom-frame harvester.
Any thumbeng module that puts the tools dir on sys.path and then does
`import harvest` gets the WRONG file. So legacy modules are reached only via:

    import os, sys
    _TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _TOOLS not in sys.path: sys.path.append(_TOOLS)   # append, NOT insert(0)
    import thumb_metrics, verify_thumb, comp_pro

`append` rather than `insert(0)` so that thumbeng's own `harvest` always wins
resolution inside the package.

ON-DISK LAYOUT - the single source of truth for where anything lives:
    work/thumbeng/                          WORK_ROOT
    work/thumbeng/<niche_slug>/             niche_dir(niche)
        thumbs/<video_id>.jpg               harvest.py writes
        harvest.jsonl                       harvest.py writes
        channels.json                       harvest.py writes
        measurements.jsonl                  measure.py writes
        measurements.csv                    measure.py writes
        styles.json                         styles.py writes
        grammar.json                        grammar.py writes
        critique/<candidate_stem>.json      critique.py writes
        run.json                            every stage appends its manifest

Exactly one module writes each file. Pipeline order is
harvest -> measure -> styles -> grammar -> critique.
"""

import os
import sys
import csv
import json
import math
import datetime

# ------------------------------------------------------------------ constants
# Resolved from __file__, never hardcoded, so a moved checkout still works.
ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
).replace("\\", "/")
TOOLS_DIR = ROOT + "/tools"
MODELS_DIR = ROOT + "/models"

# models/ also holds yunet.onnx and face_detection_yunet_2026may.onnx.
# Use yunet2023.onnx and nothing else: thumb_metrics and verify_thumb were
# derived against it, and a different model changes every face number.
YUNET = MODELS_DIR + "/yunet2023.onnx"

WORK_ROOT = ROOT + "/work/thumbeng"

# Stamped into every row this engine writes. A module that loads a row whose
# schema_version differs must raise rather than proceed: a stale
# measurements.jsonl silently mixed with a new FEATURE_KEYS list is the single
# most likely way a parallel build produces quietly wrong numbers.
SCHEMA_VERSION = 1

# Counted rather than raised, so one bad line in a long harvest is visible
# without killing the run. Read it after a load if you care.
WARNINGS = []

__all__ = [
    "ROOT", "TOOLS_DIR", "MODELS_DIR", "YUNET", "WORK_ROOT", "SCHEMA_VERSION",
    "WARNINGS", "slug", "niche_dir", "utc_now", "write_json", "read_json",
    "write_jsonl", "read_jsonl", "write_csv", "run_manifest",
    "bootstrap_legacy",
]


def bootstrap_legacy():
    """Put tools/ on sys.path by APPEND and return it.

    Append, not insert(0): tools/harvest.py is an unrelated pre-existing script
    and prepending would shadow tools/thumbeng/harvest.py for anything inside
    this package.
    """
    if TOOLS_DIR not in sys.path:
        sys.path.append(TOOLS_DIR)
    return TOOLS_DIR


# ------------------------------------------------------------------ text/paths
def slug(text):
    """Turn a niche query into a stable directory name.

    Deterministic so that re-running the same query re-enters the same
    directory instead of littering work/thumbeng with near-duplicates.
    Truncated to 60 chars because Windows still has a path length that bites
    once thumbs/<video_id>.jpg is appended.
    """
    s = "" if text is None else str(text)
    out = []
    prev_dash = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
            prev_dash = True
    return "".join(out).strip("-")[:60].strip("-")


def niche_dir(niche, create=True):
    """Return WORK_ROOT/slug(niche), creating thumbs/ and critique/ under it.

    Every module takes a niche NAME, never a raw path, so no module can invent
    its own folder layout.
    """
    d = WORK_ROOT + "/" + slug(niche)
    if create:
        os.makedirs(d + "/thumbs", exist_ok=True)
        os.makedirs(d + "/critique", exist_ok=True)
    return d


def utc_now():
    """ISO-8601 UTC to seconds with a trailing Z.

    One format everywhere so timestamps sort correctly as plain strings and no
    module has to parse another module's dates.
    """
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ json bits
def _clean(obj):
    """Recursively replace non-finite floats with None.

    json.dump emits bare NaN/Infinity, which is invalid JSON and breaks every
    reader that is not Python's own. Serialising as null and restoring NaN on
    read keeps the round trip lossless without producing an unreadable file.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return dict((k, _clean(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def write_json(path, obj):
    """Atomic write: temp file then os.replace onto the target.

    A crash mid-write must not leave a half-parsed grammar.json that a later
    stage reads as truth.
    """
    path = str(path).replace("\\", "/")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_clean(obj), fh, indent=2, ensure_ascii=False,
                  sort_keys=False)
    os.replace(tmp, path)
    return path


def read_json(path, default=None):
    """Return default when the file is absent or unparseable.

    Lets a caller proceed without optional metadata rather than crashing on a
    file that was never required in the first place.
    """
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_jsonl(path, rows, append=False):
    """One compact JSON object per line, UTF-8, ensure_ascii off.

    JSONL rather than one big JSON array: appendable during a long harvest, one
    corrupt line does not destroy the run, and it streams without pandas.
    ensure_ascii is off because competitor titles carry em-dashes and emoji and
    escaping them makes the file unreadable by eye.
    """
    path = str(path).replace("\\", "/")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    mode = "a" if append else "w"
    n = 0
    with open(path, mode, encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(_clean(row), ensure_ascii=False,
                                separators=(",", ":")))
            fh.write("\n")
            n += 1
    return n


def read_jsonl(path, strict=False, nan_keys=None):
    """Read a JSONL file into a list of dicts.

    Skips blank and unparseable lines when strict is False, counting them into
    WARNINGS; raises on the first bad line when strict is True.

    nan_keys names the keys whose JSON null should be restored to NaN. Only the
    caller knows which of its keys are NaN-bearing numerics versus genuinely
    nullable strings (harvest's thumb_path is legitimately None), so this is
    never guessed here.
    """
    nan_keys = frozenset(nan_keys or ())
    rows = []
    if not os.path.exists(str(path)):
        return rows
    with open(str(path), "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError as exc:
                if strict:
                    raise ValueError("%s line %d: %s" % (path, i, exc))
                WARNINGS.append("%s line %d unparseable: %s" % (path, i, exc))
                continue
            if nan_keys and isinstance(obj, dict):
                for k in nan_keys:
                    if k in obj and obj[k] is None:
                        obj[k] = float("nan")
            rows.append(obj)
    return rows


def write_csv(path, rows, columns):
    """Stdlib csv.DictWriter. newline='' is mandatory on Windows.

    Without newline='' every row gets a blank line between it and the next.
    NaN becomes an empty cell rather than the string 'nan' so a spreadsheet
    reads it as blank. Nothing in this engine reads the CSV back; it exists
    purely so the table can be eyeballed.
    """
    path = str(path).replace("\\", "/")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            out = {}
            for c in columns:
                v = row.get(c, "")
                if isinstance(v, float) and not math.isfinite(v):
                    v = ""
                out[c] = v
            w.writerow(out)
            n += 1
    return n


# ------------------------------------------------------------------ manifest
def run_manifest(niche, stage, args_dict, counts_dict,
                 started_utc=None, ok=True, error=None):
    """Record one pipeline stage under <niche_dir>/run.json.

    This is how the engine shows its own state: one file to cat and the whole
    pipeline's status is there, rather than anyone having to ask whether a
    stage ran.
    """
    d = niche_dir(niche, create=True)
    path = d + "/run.json"
    doc = read_json(path, default=None)
    if not isinstance(doc, dict):
        doc = {"niche": niche, "dir": d, "schema_version": SCHEMA_VERSION,
               "stages": {}}
    doc.setdefault("stages", {})
    doc["niche"] = niche
    doc["dir"] = d
    doc["schema_version"] = SCHEMA_VERSION
    entry = {
        "stage": stage,
        "started_utc": started_utc or utc_now(),
        "finished_utc": utc_now(),
        "args": args_dict or {},
        "counts": counts_dict or {},
        "schema_version": SCHEMA_VERSION,
        "ok": bool(ok),
        "error": error,
    }
    doc["stages"][stage] = entry
    write_json(path, doc)
    return entry
