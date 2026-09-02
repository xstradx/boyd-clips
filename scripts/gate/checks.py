#!/usr/bin/env python
"""The render gate's individual checks.

Every check measures the FINISHED file, never the code that produced it, and
every result carries the parameters it was taken at - because two agents once
reported 0 and 23 silent spans on the same file and both were right, at
different thresholds neither of them stated.

A check returns a Result. `validated` records whether the check has been proven
against a known-good AND known-bad control. A check that has not been proven is
reported NOT-VALIDATED and never counted as a pass, because a checker that has
never been run against a known answer is not evidence.
"""
from __future__ import annotations
import subprocess, re, math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Result:
    name: str
    ok: bool | None                 # None = could not be determined
    detail: str
    params: dict = field(default_factory=dict)
    validated: bool = True          # proven against controls?

    @property
    def status(self) -> str:
        if not self.validated:
            return "NOT-VALIDATED"
        if self.ok is None:
            return "UNKNOWN"
        return "PASS" if self.ok else "FAIL"

    def line(self) -> str:
        p = " ".join(f"{k}={v}" for k, v in self.params.items())
        return f"  {self.status:<13} {self.name:<10} {self.detail}" + (f"   [{p}]" if p else "")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in args], capture_output=True, text=True)


def probe(path: Path, entries: str, stream: str | None = None) -> str:
    a = ["ffprobe", "-v", "error"]
    if stream:
        a += ["-select_streams", stream]
    a += ["-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)]
    p = _run(a)
    if p.returncode != 0:
        return ""
    return p.stdout.strip()


def _gray_frames(path: Path, w: int, h: int, fps: float, extra_vf: str = "") -> np.ndarray:
    """Decode to a small grayscale array [n, h, w]. No temp files."""
    vf = f"fps={fps},scale={w}:{h},format=gray"
    if extra_vf:
        vf = extra_vf + "," + vf
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo",
         "-pix_fmt", "gray", "-"], capture_output=True)
    n = len(p.stdout) // (w * h)
    if n == 0:
        return np.zeros((0, h, w), dtype=np.uint8)
    return np.frombuffer(p.stdout[: n * w * h], dtype=np.uint8).reshape(n, h, w)


# --------------------------------------------------------------- integrity
def integrity(path: Path, *, want_pix_fmt: str = "yuv420p", max_av_drift: float = 0.10) -> list[Result]:
    """pix_fmt, A/V alignment, and a clean decode of every packet."""
    out: list[Result] = []
    pf = probe(path, "stream=pix_fmt", "v:0")
    out.append(Result("pix_fmt", pf == want_pix_fmt, f"{pf or 'unreadable'}",
                      {"want": want_pix_fmt}))

    try:
        vd = float(probe(path, "stream=duration", "v:0") or 0)
        ad = float(probe(path, "stream=duration", "a:0") or 0)
    except ValueError:
        vd = ad = 0.0
    drift = abs(vd - ad)
    out.append(Result("av_sync", (vd > 0 and ad > 0 and drift <= max_av_drift),
                      f"video {vd:.3f}s audio {ad:.3f}s drift {drift:.3f}s",
                      {"max_drift": max_av_drift}))

    p = _run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])
    errs = [l for l in p.stderr.splitlines() if l.strip()]
    out.append(Result("decode", len(errs) == 0,
                      "clean" if not errs else f"{len(errs)} error(s): {errs[0][:70]}"))
    return out


# ---------------------------------------------------------------- dead air
def deadair(path: Path, *, noise_db: float = -30.0, min_span: float = 0.30,
            window_s: float = 60.0, max_density: float = 0.22) -> Result:
    """Silence DENSITY in a sliding window, not the longest single span.

    The max-span rule this replaces cannot catch the real defect: every shipped
    long-form passed "no gap over 4s" while roughly a third of its runtime was
    silence arriving in two- and three-second pieces.
    """
    dur = float(probe(path, "format=duration") or 0)
    if dur <= 0:
        return Result("deadair", None, "unreadable duration",
                      {"noise_db": noise_db, "min_span": min_span})

    p = _run(["ffmpeg", "-v", "info", "-i", str(path), "-af",
              f"silencedetect=noise={noise_db}dB:d={min_span}", "-f", "null", "-"])
    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?[\d.]+)", p.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", p.stderr)]
    if len(ends) < len(starts):
        ends.append(dur)
    spans = [(s, e) for s, e in zip(starts, ends) if e > s]

    win = min(window_s, dur)
    step = max(0.5, win / 20.0)
    worst, worst_at = 0.0, 0.0
    t = 0.0
    while t + win <= dur + 1e-6:
        silent = sum(max(0.0, min(e, t + win) - max(s, t)) for s, e in spans)
        d = silent / win
        if d > worst:
            worst, worst_at = d, t
        t += step
    total = sum(e - s for s, e in spans) / dur if dur else 0.0

    return Result("deadair", worst <= max_density,
                  f"worst {worst*100:.1f}% in a {win:.0f}s window at t={worst_at:.1f}s; "
                  f"overall {total*100:.1f}%, {len(spans)} spans",
                  {"noise_db": noise_db, "min_span": min_span,
                   "window_s": round(win, 1), "max_density": max_density})


# ------------------------------------------------------------------- intro
def intro(path: Path, ref: Path, *, tol: float = 0.15) -> Result:
    """Is the branded sting actually on the front?

    Keys on the luma-over-time signature of the reference sting rather than a
    single frame: the old 1.4s sting opens flat, v2 ramps, and a single frame
    cannot tell those apart.
    """
    params = {"ref": ref.name, "tol": tol}
    if not ref.exists():
        return Result("intro", None, f"reference sting missing: {ref}", params, validated=False)
    rdur = float(probe(ref, "format=duration") or 0)
    if rdur <= 0:
        return Result("intro", None, "reference sting unreadable", params, validated=False)

    fps = 10.0
    r = _gray_frames(ref, 32, 18, fps).astype(np.float64)
    a = _gray_frames(path, 32, 18, fps).astype(np.float64)
    n = min(len(r), len(a))
    if n < 3:
        return Result("intro", None, f"too few frames to compare (n={n})", params)
    rs = r[:n].mean(axis=(1, 2))
    as_ = a[:n].mean(axis=(1, 2))
    denom = (np.linalg.norm(rs - rs.mean()) * np.linalg.norm(as_ - as_.mean()))
    ncc = float(((rs - rs.mean()) @ (as_ - as_.mean())) / denom) if denom > 1e-9 else 0.0
    mad = float(np.abs(rs - as_).mean())
    params["ref_dur"] = round(rdur, 2)
    ok = mad <= (255 * tol) and ncc > 0.5
    return Result("intro", ok,
                  f"first {n/fps:.1f}s vs sting: mean abs luma diff {mad:.2f}, shape corr {ncc:+.3f}",
                  params)


# ---------------------------------------------------------------- captions
def captions(path: Path, *, core: int = 238, stroke: int = 45, radius: int = 17,
             min_px: int = 400, samples: int = 12) -> Result:
    """Captions present, and on WHICH half.

    Keys on the glyph signature - a very bright pixel with a very dark pixel
    within `radius` - not on brightness. A previous checker thresholded on white
    alone and scored a correct render 0/5 wrong: it was measuring the ceiling
    and Judge Boyd's white collar. Nothing else in a courtroom frame is a bright
    core inside a dark stroke.
    """
    dur = float(probe(path, "format=duration") or 0)
    if dur <= 0:
        return Result("captions", None, "unreadable duration", {})
    fps = max(0.5, samples / dur)
    W, H = 320, 180
    fr = _gray_frames(path, W, H, fps)
    if len(fr) == 0:
        return Result("captions", None, "no frames decoded", {})

    r = max(1, int(radius * W / 1920))
    top_hits, bot_hits = [], []
    for f in fr:
        bright = f >= core
        if not bright.any():
            top_hits.append(0); bot_hits.append(0); continue
        dark = (f <= stroke).astype(np.uint8)
        # max-filter the dark mask by a (2r+1) box: is any dark pixel within r?
        k = 2 * r + 1
        cs = np.cumsum(np.cumsum(np.pad(dark, ((1, 0), (1, 0))), axis=0), axis=1)
        ys, xs = np.mgrid[0:H, 0:W]
        y0 = np.clip(ys - r, 0, H); y1 = np.clip(ys + r + 1, 0, H)
        x0 = np.clip(xs - r, 0, W); x1 = np.clip(xs + r + 1, 0, W)
        box = cs[y1, x1] - cs[y0, x1] - cs[y1, x0] + cs[y0, x0]
        glyph = bright & (box > 0)
        top_hits.append(int(glyph[: H // 2].sum()))
        bot_hits.append(int(glyph[H // 2:].sum()))

    scale = (1920 * 1080) / (W * H)
    top = int(np.median(top_hits) * scale)
    bot = int(np.median(bot_hits) * scale)
    present = max(top, bot) >= min_px
    half = "bottom" if bot > top else ("top" if top > bot else "none")
    return Result("captions", present,
                  f"glyph px median top {top} / bottom {bot} -> {half if present else 'NONE DETECTED'}",
                  {"core": core, "stroke": stroke, "radius": radius,
                   "min_px": min_px, "frames": len(fr)})


# ------------------------------------------------- not yet validated checks
def watermark(path: Path) -> Result:
    """Deliberately unimplemented rather than faked.

    The watermark sits on a static region of courtroom wall, so a static overlay
    is not separable from static background by variance alone, and the brand
    PNGs were removed on 2026-08-29 so there is no reference to match against.
    Reported NOT-VALIDATED so it can never be mistaken for a pass.
    """
    return Result("watermark", None,
                  "no reference asset on disk (boyd-brand/ removed 2026-08-29); "
                  "regenerate with scripts/make_watermarks_v2.py, then match the mark's alpha "
                  "against the rendered ROI",
                  {}, validated=False)
