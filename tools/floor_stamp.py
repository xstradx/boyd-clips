# -*- coding: utf-8 -*-
"""R40 - an artifact carries the floor it was built under, and a floor that
moved after the render makes the file stale even though it plays.

Nathan, 2026-08-31 17:17: "Okay but that short was made off the old rules or
whatever and should be made with our new ones". The OFFERUP short had been
rendered before config/short_floor.json existed and nothing on disk could say
so, so nothing could refuse it.

    python tools/floor_stamp.py current                 # the hashes right now
    python tools/floor_stamp.py stamp <work_dir|short.mp4>
    python tools/floor_stamp.py check <work_dir|_build_log.json|short.mp4>
    python tools/floor_stamp.py --selftest

Thumbnail floor  = config/quality_floor.json + spec/THUMBNAIL_SPEC.md
                   stamped into <work>/_build_log.json["floor"]
Short floor      = config/short_floor.json
                   stamped into <short>.floor.json beside the file

check prints FLOOR_OK or FLOOR_STALE and exits 0/1. A missing stamp is STALE:
"unknown rules" is exactly the state that let the old short through.
"""
import hashlib
import json
import os
import sys
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FLOORS = {
    "thumb": ("config/quality_floor.json", "spec/THUMBNAIL_SPEC.md"),
    "short": ("config/short_floor.json",),
}
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm")


def floor_hash(kind, root=ROOT):
    """SHA-256 over the floor files, name-prefixed so a swap between two files
    with the same bytes still changes the hash."""
    h = hashlib.sha256()
    for rel in FLOORS[kind]:
        p = os.path.join(root, rel)
        h.update(rel.encode("utf-8") + b"\0")
        with open(p, "rb") as f:
            h.update(f.read())
        h.update(b"\0")
    return h.hexdigest()


def current(root=ROOT):
    return {k: floor_hash(k, root) for k in FLOORS}


def _kind_and_stamp_path(target):
    """work dir / _build_log.json -> thumb ; video file -> short."""
    t = os.path.abspath(target)
    if os.path.isdir(t):
        return "thumb", os.path.join(t, "_build_log.json")
    if t.lower().endswith("_build_log.json"):
        return "thumb", t
    if t.lower().endswith(VIDEO_EXT):
        return "short", t + ".floor.json"
    raise ValueError(f"not a work dir, build log or video: {target}")


def stamp(target, root=ROOT):
    kind, sp = _kind_and_stamp_path(target)
    rec = {"kind": kind, "hash": floor_hash(kind, root),
           "files": list(FLOORS[kind]),
           "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if kind == "thumb":
        log = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
        log["floor"] = rec
        json.dump(log, open(sp, "w", encoding="utf-8"), indent=1, default=str)
    else:
        json.dump(rec, open(sp, "w", encoding="utf-8"), indent=1)
    return rec


def check(target, root=ROOT, verbose=True):
    kind, sp = _kind_and_stamp_path(target)
    now = floor_hash(kind, root)
    rec = None
    if os.path.exists(sp):
        d = json.load(open(sp, encoding="utf-8"))
        rec = d.get("floor") if kind == "thumb" else d
    if not rec or not rec.get("hash"):
        why = f"no floor stamp on {os.path.basename(sp)} - built under unknown rules"
        ok = False
    elif rec["hash"] != now:
        why = (f"floor moved since the build at {rec.get('at', '?')}: "
               f"{rec['hash'][:12]} -> {now[:12]} ({', '.join(FLOORS[kind])})")
        ok = False
    else:
        why = f"built on the current {kind} floor {now[:12]} at {rec.get('at', '?')}"
        ok = True
    if verbose:
        print(("FLOOR_OK     " if ok else "FLOOR_STALE  ") + why)
    return ok, why


def selftest():
    """Known answers before any number is read: a fresh stamp passes, a moved
    floor fails, no stamp fails. Runs against a copy of the real floor files so
    nothing in config/ or spec/ is touched."""
    import shutil
    import tempfile
    ok = True
    tmp = tempfile.mkdtemp(prefix="floor_stamp_")
    try:
        for kind, rels in FLOORS.items():
            for rel in rels:
                dst = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), dst)
        work = os.path.join(tmp, "WORK")
        os.makedirs(work)
        json.dump({"type": {"size": 1}}, open(os.path.join(work, "_build_log.json"), "w"))
        short = os.path.join(tmp, "SHORT.mp4")
        open(short, "wb").write(b"\0" * 16)

        def case(label, target, want):
            nonlocal ok
            got, why = check(target, tmp, verbose=False)
            good = got == want
            ok = ok and good
            print(f"  {'ok  ' if good else 'FAIL'} {label}: {why}")

        case("thumb without stamp is stale", work, False)
        case("short without stamp is stale", short, False)
        stamp(work, tmp)
        stamp(short, tmp)
        case("fresh thumb stamp passes", work, True)
        case("fresh short stamp passes", short, True)
        # the build log keeps its other keys
        log = json.load(open(os.path.join(work, "_build_log.json")))
        keep = log.get("type", {}).get("size") == 1 and "floor" in log
        ok = ok and keep
        print(f"  {'ok  ' if keep else 'FAIL'} stamp is added to the build log, not written over it")
        # move each floor by one byte
        with open(os.path.join(tmp, "config/quality_floor.json"), "ab") as f:
            f.write(b"\n")
        case("thumb floor moved -> stale", work, False)
        with open(os.path.join(tmp, "config/short_floor.json"), "ab") as f:
            f.write(b"\n")
        case("short floor moved -> stale", short, False)
        # the thumb stamp is the whole pair: THUMBNAIL_SPEC alone must count
        stamp(work, tmp)
        with open(os.path.join(tmp, "spec/THUMBNAIL_SPEC.md"), "ab") as f:
            f.write(b"\n")
        case("THUMBNAIL_SPEC moved -> stale", work, False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("SELFTEST_PASS floor_stamp" if ok else "SELFTEST_FAIL floor_stamp")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        sys.exit(0 if selftest() else 1)
    if a[0] == "current":
        for k, v in current().items():
            print(f"  {k:6} {v}  ({', '.join(FLOORS[k])})")
        sys.exit(0)
    if a[0] == "stamp" and len(a) == 2:
        r = stamp(a[1])
        print(f"  stamped {r['kind']} floor {r['hash'][:12]} on {a[1]}")
        sys.exit(0)
    if a[0] == "check" and len(a) == 2:
        sys.exit(0 if check(a[1])[0] else 1)
    print(__doc__)
    sys.exit(2)
