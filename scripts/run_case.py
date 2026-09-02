"""The routine: one case in, thumbnail and short out.

Nathan, 2026-08-29: "from start to finish can handle everything from a routine".

Everything a case needs lives in `config/cases.json` — the source video, its
offset, the tile crops, the copy. Nothing is hardcoded per case in any script, so
adding a fourth hearing is a JSON entry, not a code change. That is the whole
test of whether this generalises.

    python scripts/run_case.py --list
    python scripts/run_case.py --case OFFERUP
    python scripts/run_case.py --all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
def _desk() -> Path:
    """Where the finished files actually live.

    The Desktop entry "Boyd Clips" is a JUNCTION to D:/Boyd Clips, and on
    2026-08-29 at 05:44 it stopped being one: something replaced it with a
    plain .lnk shortcut and left an empty real folder in its place. Renders
    then went into the empty stub instead of the project, silently, because a
    hardcoded path cannot tell the difference. So the location is resolved,
    the shortcut is followed, and the first path that actually holds
    READY-TO-POST wins.
    """
    cands = [Path(r"D:/Boyd Clips"),
             Path(r"C:/Users/natha/OneDrive/Desktop/Boyd Clips"),
             Path(r"C:/Users/natha/Desktop/Boyd Clips")]
    for c in cands:
        if (c / "READY-TO-POST").is_dir() and any((c / "READY-TO-POST").iterdir()):
            return c
    for c in cands:
        if c.is_dir():
            return c
    return cands[1]


DESK = _desk()


def resolve(p: str) -> Path:
    q = Path(p)
    if q.is_absolute():
        return q
    a = ROOT / p
    return a if a.exists() else (DESK / p)


def run(cmd, label, dry=False):
    if dry:
        print(f"    would run: {label}")
        return True
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    ok = p.returncode == 0
    print(f"    {label}: {'ok' if ok else 'FAILED'} ({time.time() - t:.0f}s)")
    if not ok:
        tail = (p.stderr or p.stdout).strip().splitlines()[-6:]
        print("      " + "\n      ".join(tail))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=ROOT / "config" / "cases.json")
    ap.add_argument("--case", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-short", action="store_true")
    ap.add_argument("--skip-thumb", action="store_true")
    ap.add_argument("--auto-plate", action="store_true",
                    help="re-measure every candidate plate frame in the hearing "
                         "before building (~25 min per case on CPU: BiRefNet "
                         "runs on each). OFF by default because the winning "
                         "frame is already recorded in config/cases.json as "
                         "plate_t, with the sweep that chose it. It is not "
                         "needed to be safe either way: the builder REFUSES a "
                         "frame with no room for a full-size judge, and the "
                         "wrapper then runs the sweep itself and retries.")
    ap.add_argument("--outdir", type=Path, default=DESK / "READY-TO-POST" / "Q3SET")
    a = ap.parse_args()

    cfg = json.load(open(a.cases, encoding="utf-8"))

    if a.list:
        print(f"{len(cfg)} cases configured")
        for k, c in cfg.items():
            side = "judge LEFT" if int(c["judge_crop"].split(":")[2]) < 300 \
                else "judge RIGHT"
            print(f"  {k:10} {side:12} {c['white']} / {c['yellow']}")
        return 0

    names = list(cfg) if a.all else ([a.case] if a.case else [])
    if not names:
        print("give --case NAME, --all, or --list")
        return 2
    for n in names:
        if n not in cfg:
            print(f"unknown case '{n}'. known: {', '.join(cfg)}")
            return 2

    if a.dry_run:
        for n in names:
            c = cfg[n]
            print(f"\n{n}")
            for key in ("video", "transcript", "short"):
                p = resolve(c[key])
                print(f"    {key:11} {'found' if p.exists() else 'MISSING'}  {p}")
        print("\nDRY RUN OK")
        return 0

    a.outdir.mkdir(parents=True, exist_ok=True)
    bad = []
    for n in names:
        c = cfg[n]
        print(f"\n=== {n} ===")
        if not a.skip_thumb:
            ok = run([PY, str(ROOT / "scripts" / "make_thumbnail_auto.py"),
                      "--case", n, "--cases", str(a.cases),
                      "--out", str(a.outdir / f"{n}.jpg")]
                     + (["--auto-plate"] if a.auto_plate else []),
                     "thumbnail (frame chosen, built, graded)")
            if not ok:
                bad.append(f"{n} thumbnail")
        if not a.skip_short:
            short = resolve(c["short"])
            if not short.exists():
                print(f"    short: source missing at {short}")
                bad.append(f"{n} short (missing source)")
            else:
                ok = run([PY, str(ROOT / "scripts" / "make_short_auto.py"),
                          "--short", str(short),
                          "--transcript", str(resolve(c["transcript"])),
                          "--src-start", str(c["short_src_start"]),
                          "--out", str(DESK / "READY-TO-POST" / f"{n}_SHORT_FINAL.mp4")],
                         "short (cut, deblocked, captioned)")
                if not ok:
                    bad.append(f"{n} short")

    print("\n" + ("all cases completed" if not bad
                  else f"{len(bad)} step(s) failed: {', '.join(bad)}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
