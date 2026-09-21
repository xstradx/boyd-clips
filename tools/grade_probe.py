"""Per-camera grade probe: what a candidate highlight curve does to each
tile's highlights versus its face, measured on the Short's own frames.

Nathan, 2026-09-06: the defendant camera's fluorescent ceiling dominates the
top frame; compress its highlights without darkening the subject. This tool
measures, it does not decide: for each tile it reports the luma
distribution of the base window (p50 / p90 / p99, % of pixels at or above
235), the ceiling band (the top quarter of the window), the face box median
(from the measured anchor) and the midtone separation (p75 - p25), raw,
after the candidate per-camera curve, and after the common floor grade —
so the choice is made on numbers, not by eye.

    python tools/grade_probe.py out/review/<dir> --top "curves=all='0/0 0.5/0.5 ... 1/0.85'" --bottom ""
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import render  # noqa: E402


def gray(path: Path, t: float, vf: str, w: int, h: int) -> np.ndarray | None:
    proc = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) < w * h:
        return None
    return np.frombuffer(proc.stdout[: w * h], dtype=np.uint8).reshape(h, w).astype(float)


def stats(img: np.ndarray, face: tuple[int, int, int, int] | None) -> dict:
    flat = img.ravel()
    top = img[: max(1, img.shape[0] // 4)].ravel()
    out = {
        "p50": float(np.percentile(flat, 50)), "p90": float(np.percentile(flat, 90)),
        "p99": float(np.percentile(flat, 99)), "blown_pct": float((flat >= 235).mean() * 100),
        "ceiling_p99": float(np.percentile(top, 99)), "ceiling_blown_pct": float((top >= 235).mean() * 100),
        "midtone_sep": float(np.percentile(flat, 75) - np.percentile(flat, 25)),
    }
    if face:
        x, y, w, h = face
        box = img[max(0, y): y + h, max(0, x): x + w]
        if box.size:
            out["face_p50"] = float(np.percentile(box, 50))
            out["face_p90"] = float(np.percentile(box, 90))
    return out


def parse_crop(s: str) -> tuple[int, int, int, int]:
    m = re.fullmatch(r"crop=(\d+):(\d+):(\d+):(\d+)", s.strip())
    w, h, x, y = (int(v) for v in m.groups())
    return w, h, x, y


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("review_dir")
    ap.add_argument("--top", default="", help="candidate filter for the TOP tile (before assembly)")
    ap.add_argument("--bottom", default="", help="candidate filter for the BOTTOM tile (before assembly)")
    ap.add_argument("--final", default=None, help="common stage after assembly (default: the short floor grade)")
    ap.add_argument("--tiles", default=None, help="raw tile crops 'top|bottom' (default: from manifest)")
    ap.add_argument("--json", help="write the measurements here")
    a = ap.parse_args()

    d = Path(a.review_dir)
    man = json.loads((d / "manifest_v2short.json").read_text(encoding="utf-8"))
    plan = json.loads((d / "short_plan.json").read_text(encoding="utf-8"))
    comp = man["short_editor"]["composition"]
    source = Path(man["source_file"])
    offset = float(man["source_offset_s"])
    final = a.final if a.final is not None else render.short_grade_filter(man["output_short_config"])
    tiles = {}
    if a.tiles:
        tiles["top"], tiles["bottom"] = a.tiles.split("|")
    else:
        # the raw tiles are not stored; rebuild from the log convention (628-wide halves at y 186)
        tiles["top"], tiles["bottom"] = "crop=628:348:6:186", "crop=628:348:646:186"
    times = []
    for s in plan["segments"]:
        times.append(s[0] + 0.5)
        if s[1] - s[0] > 3.0:
            times.append((s[0] + s[1]) / 2.0)
    times = sorted(set(round(t, 2) for t in times))[:8]

    report = {"source": str(source), "final": final, "candidates": {"top": a.top, "bottom": a.bottom}, "tiles": {}}
    for name, cand in (("top", a.top), ("bottom", a.bottom)):
        win = comp["base"][name]["crop"]
        ww, wh, wx, wy = parse_crop(win)
        tw, th, tx, ty = parse_crop(tiles[name])
        an = comp["anchors"][name]
        face = None
        if an.get("face_w"):
            fw, fh = an["face_w"] * tw, an["face_h"] * th
            cx, cy = an["fx"] * tw - (wx - tx), an["fy"] * th - (wy - ty)
            face = (int(cx - fw / 2), int(cy - fh / 2), int(fw), int(fh))
        stages = {"raw": win, "camera": f"{win},{cand}" if cand else win,
                  "camera+final": ",".join(x for x in (win, cand, final) if x)}
        acc: dict[str, list[dict]] = {k: [] for k in stages}
        for t in times:
            for stage, vf in stages.items():
                img = gray(source, t - offset, vf, ww, wh)
                if img is not None:
                    acc[stage].append(stats(img, face))
        summary = {}
        for stage, rows in acc.items():
            if not rows:
                continue
            summary[stage] = {k: round(float(np.median([r[k] for r in rows if k in r])), 1)
                              for k in rows[0].keys()}
        report["tiles"][name] = {"window": win, "face_box_in_window": face, "frames": len(times), "stages": summary}
        role = "defendant" if comp["tile_map"].get("defendant") == name else "boyd"
        print(f"\n{name.upper()} tile = {role}   window {win}   candidate: {cand or '(none)'}")
        print(f"  {'stage':<14}{'p50':>6}{'p90':>6}{'p99':>6}{'blown%':>8}{'ceil p99':>10}{'ceil blown%':>13}{'face p50':>10}{'face p90':>10}{'mid sep':>9}")
        for stage, s in summary.items():
            print(f"  {stage:<14}{s['p50']:>6.0f}{s['p90']:>6.0f}{s['p99']:>6.0f}{s['blown_pct']:>8.1f}{s['ceiling_p99']:>10.0f}"
                  f"{s['ceiling_blown_pct']:>13.1f}{s.get('face_p50', float('nan')):>10.0f}{s.get('face_p90', float('nan')):>10.0f}{s['midtone_sep']:>9.0f}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
