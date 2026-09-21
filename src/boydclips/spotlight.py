# -*- coding: utf-8 -*-
"""The spotlight treatment: a red ring drawn around one subject and a red
arrow swinging in to point at another, with level-matched cue sounds.

Nathan, 2026-09-13, pointing at a reference Short ("this is exactly how i want
the shorts ... the circle around the defendant moving and the arrow comes in
for the judge as the voice is explaining"):

    * the ring is DRAWN (it closes as the sentence lands), never a still circle;
    * the arrow is a solid red shaft plus a pressed-in head, arriving after the
      ring, holding, then leaving;
    * both are canvas-pixel geometry measured from the Short's own layout, so a
      cue can point at a real face instead of a guessed position;
    * the cues are one extra overlay pass on an already-rendered Short (one
      encode), with their own whoosh/ding mixed under the dialogue.

Nothing here decides editorial timing: a spec supplies it and is validated.
"""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

CANVAS_W = 1080
CANVAS_H = 1920
RING_RGBA = (236, 44, 44, 236)
ARROW_RGBA = (226, 38, 38, 245)


def _ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_back(t: float) -> float:
    t = min(1.0, max(0.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


@dataclass
class RingCue:
    """The drawn ring. `box` is (x1, y1, x2, y2) in canvas pixels."""
    box: tuple[int, int, int, int]
    start_s: float
    draw_s: float = 0.55
    hold_until_s: float = 3.0
    width_px: int = 13
    tail_overlap: float = 0.06      # the arc overlaps its own start, like a pen closing a loop
    fade_s: float = 0.25

    def visible_span(self) -> tuple[float, float]:
        return self.start_s, self.hold_until_s + self.fade_s

    def validate(self) -> None:
        x1, y1, x2, y2 = self.box
        if not (0 <= x1 < x2 <= CANVAS_W and 0 <= y1 < y2 <= CANVAS_H):
            raise ValueError(f"ring box must lie inside the canvas: {self.box}")
        if self.draw_s <= 0 or self.hold_until_s <= self.start_s + self.draw_s:
            raise ValueError("ring must finish drawing before it starts to hold")


@dataclass
class ArrowCue:
    """The incoming arrow, tip last. Tail and tip are canvas pixels."""
    tail: tuple[float, float]
    tip: tuple[float, float]
    start_s: float
    rise_s: float = 0.30
    hold_until_s: float = 5.0
    shaft_px: int = 24
    head_len_px: int = 74
    head_half_px: int = 46
    fade_s: float = 0.25

    def visible_span(self) -> tuple[float, float]:
        return self.start_s, self.hold_until_s + self.fade_s

    def validate(self) -> None:
        for name, (x, y) in (("tail", self.tail), ("tip", self.tip)):
            if not (0 <= x <= CANVAS_W and 0 <= y <= CANVAS_H):
                raise ValueError(f"arrow {name} outside the canvas: {(x, y)}")
        if math.hypot(self.tip[0] - self.tail[0], self.tip[1] - self.tail[1]) < self.head_len_px:
            raise ValueError("arrow is shorter than its own head")
        if self.rise_s <= 0 or self.hold_until_s <= self.start_s + self.rise_s:
            raise ValueError("arrow must finish arriving before it starts to hold")


@dataclass
class CueSound:
    """A cue sound, levelled by PEAK (dBFS). Integrated LUFS cannot gate a
    transient cue: a 0.37 s whoosh measures -70 LUFS and a 1.2 s ding's
    loudness is dominated by its tail, which made both cues far quieter than
    intended on 2026-09-13. Peak is what a whoosh or a ding actually is."""
    path: Path
    at_s: float
    peak_dbfs: float = -12.0


@dataclass
class SpotlightSpec:
    ring: RingCue | None = None
    arrow: ArrowCue | None = None
    sounds: list[CueSound] = field(default_factory=list)

    def validate(self) -> None:
        if self.ring is None and self.arrow is None:
            raise ValueError("a spotlight spec needs at least one cue")
        if self.ring is not None:
            self.ring.validate()
        if self.arrow is not None:
            self.arrow.validate()
        for snd in self.sounds:
            if not Path(snd.path).is_file():
                raise ValueError(f"cue sound is missing: {snd.path}")
            if snd.at_s < 0:
                raise ValueError("cue sound cannot start before the video")

    def span(self) -> tuple[float, float]:
        spans = [c.visible_span() for c in (self.ring, self.arrow) if c is not None]
        return min(a for a, _ in spans), max(b for _, b in spans)

    def to_json(self) -> dict[str, Any]:
        return {
            "ring": None if self.ring is None else {
                "box": list(self.ring.box), "start_s": self.ring.start_s, "draw_s": self.ring.draw_s,
                "hold_until_s": self.ring.hold_until_s, "width_px": self.ring.width_px},
            "arrow": None if self.arrow is None else {
                "tail": list(self.arrow.tail), "tip": list(self.arrow.tip), "start_s": self.arrow.start_s,
                "rise_s": self.arrow.rise_s, "hold_until_s": self.arrow.hold_until_s,
                "shaft_px": self.arrow.shaft_px, "head_len_px": self.arrow.head_len_px,
                "head_half_px": self.arrow.head_half_px},
            "sounds": [{"path": str(s.path), "at_s": s.at_s, "peak_dbfs": s.peak_dbfs} for s in self.sounds],
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "SpotlightSpec":
        ring = raw.get("ring")
        arrow = raw.get("arrow")
        return cls(
            ring=None if not ring else RingCue(tuple(ring["box"]), float(ring["start_s"]),
                                                float(ring.get("draw_s", 0.55)),
                                                float(ring["hold_until_s"]),
                                                int(ring.get("width_px", 13))),
            arrow=None if not arrow else ArrowCue(tuple(arrow["tail"]), tuple(arrow["tip"]),
                                                   float(arrow["start_s"]), float(arrow.get("rise_s", 0.30)),
                                                   float(arrow["hold_until_s"]),
                                                   int(arrow.get("shaft_px", 24)),
                                                   int(arrow.get("head_len_px", 74)),
                                                   int(arrow.get("head_half_px", 46))),
            sounds=[CueSound(Path(s["path"]), float(s["at_s"]), float(s.get("peak_dbfs", -12.0)))
                    for s in (raw.get("sounds") or [])],
        )


# ---------------------------------------------------------------- frames


def _region(spec: SpotlightSpec, pad: int = 24) -> tuple[int, int, int, int]:
    xs: list[float] = []
    ys: list[float] = []
    if spec.ring is not None:
        x1, y1, x2, y2 = spec.ring.box
        w = spec.ring.width_px
        xs += [x1 - w, x2 + w]
        ys += [y1 - w, y2 + w]
    if spec.arrow is not None:
        a = spec.arrow
        r = max(a.shaft_px, a.head_half_px) + 4
        xs += [a.tail[0] - r, a.tip[0] + r]
        ys += [a.tail[1] - r, a.tip[1] + r]
    x0 = int(max(0, math.floor(min(xs) - pad)))
    y0 = int(max(0, math.floor(min(ys) - pad)))
    x1 = int(min(CANVAS_W, math.ceil(max(xs) + pad)))
    y1 = int(min(CANVAS_H, math.ceil(max(ys) + pad)))
    return x0, y0, x1 - x0, y1 - y0


def render_overlay_frames(spec: SpotlightSpec, out_dir: Path, fps: int = 30, ss: int = 3) -> dict[str, Any]:
    """One RGBA PNG per frame of the spec's whole span, cropped to its region."""
    from PIL import Image, ImageDraw, ImageFilter

    spec.validate()
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("spot_*.png"):
        old.unlink()
    rx, ry, rw, rh = _region(spec)
    start, end = spec.span()
    n = int(math.ceil((end - start) * fps)) + 1
    for k in range(n):
        t = start + k / float(fps)
        layer = Image.new("RGBA", (rw * ss, rh * ss), (0, 0, 0, 0))
        if spec.ring is not None:
            cue = spec.ring
            if cue.start_s <= t <= cue.hold_until_s + cue.fade_s:
                alpha = 1.0
                if t > cue.hold_until_s:
                    alpha = max(0.0, 1.0 - (t - cue.hold_until_s) / max(1e-6, cue.fade_s))
                prog = _ease_out((t - cue.start_s) / cue.draw_s) if t >= cue.start_s else 0.0
                width = cue.width_px * (0.35 + 0.65 * min(1.0, prog / 0.25)) if prog > 0 else 0.0
                if prog > 0.0 and width >= 1.0:
                    ring = Image.new("L", layer.size, 0)
                    d = ImageDraw.Draw(ring)
                    sweep = 360.0 * min(1.0, prog) * (1.0 + cue.tail_overlap)
                    box = [(cue.box[0] - rx) * ss, (cue.box[1] - ry) * ss,
                           (cue.box[2] - rx) * ss, (cue.box[3] - ry) * ss]
                    d.arc(box, start=-92, end=-92 + sweep, fill=int(255 * alpha),
                          width=max(1, int(round(width * ss))))
                    ring = ring.filter(ImageFilter.GaussianBlur(0.6 * ss))
                    ink = Image.new("RGBA", layer.size, RING_RGBA[:3] + (0,))
                    ink.putalpha(ring.point(lambda v: int(v * RING_RGBA[3] / 255)))
                    layer = Image.alpha_composite(layer, ink)
        if spec.arrow is not None:
            cue = spec.arrow
            if cue.start_s <= t <= cue.hold_until_s + cue.fade_s:
                alpha = 1.0
                if t > cue.hold_until_s:
                    alpha = max(0.0, 1.0 - (t - cue.hold_until_s) / max(1e-6, cue.fade_s))
                prog = _ease_back((t - cue.start_s) / cue.rise_s) if t >= cue.start_s else 0.0
                if prog > 0.0:
                    tx, ty = cue.tip
                    bx, by = cue.tail
                    ux, uy = tx - bx, ty - by
                    length = math.hypot(ux, uy) or 1.0
                    ux, uy = ux / length, uy / length
                    px, py = -uy, ux
                    grow = min(1.0, prog)
                    head_at = (bx + ux * (length - cue.head_len_px) * grow,
                               by + uy * (length - cue.head_len_px) * grow)
                    layer_arrow = Image.new("L", layer.size, 0)
                    d = ImageDraw.Draw(layer_arrow)
                    shaft_end = head_at if prog > 0.65 else (bx + ux * length * grow, by + uy * length * grow)
                    d.line([((bx - rx) * ss, (by - ry) * ss), ((shaft_end[0] - rx) * ss, (shaft_end[1] - ry) * ss)],
                           fill=int(255 * alpha), width=int(round(cue.shaft_px * ss)),
                           joint="curve")
                    if prog > 0.65:
                        pop = _ease_back(min(1.0, (prog - 0.65) / 0.35))
                        hl = cue.head_len_px * (0.55 + 0.45 * pop)
                        hh = cue.head_half_px * (0.55 + 0.45 * pop)
                        base = (tx - ux * hl, ty - uy * hl)
                        tri = [((tx - rx) * ss, (ty - ry) * ss),
                               ((base[0] + px * hh - rx) * ss, (base[1] + py * hh - ry) * ss),
                               ((base[0] - px * hh - rx) * ss, (base[1] - py * hh - ry) * ss)]
                        d.polygon(tri, fill=int(255 * alpha))
                    layer_arrow = layer_arrow.filter(ImageFilter.GaussianBlur(0.5 * ss))
                    ink = Image.new("RGBA", layer.size, ARROW_RGBA[:3] + (0,))
                    ink.putalpha(layer_arrow.point(lambda v: int(v * ARROW_RGBA[3] / 255)))
                    layer = Image.alpha_composite(layer, ink)
        layer.resize((rw, rh), Image.LANCZOS).save(out_dir / f"spot_{k:04d}.png", compress_level=3)
    return {"pattern": str((out_dir / "spot_%04d.png").resolve()).replace("\\", "/"),
            "frames": n, "region": [rx, ry, rw, rh], "fps": fps, "supersample": ss,
            "start_s": round(start, 4), "end_s": round(end, 4)}


# ---------------------------------------------------------------- compose


def measure_levels_dbfs(path: Path) -> tuple[float | None, float | None]:
    """(mean, peak) of a cue file in dBFS, from ffmpeg's volumedetect."""
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
                           "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    mean = peak = None
    for line in (proc.stderr or "").splitlines():
        for key, setter in (("mean_volume:", "mean"), ("max_volume:", "peak")):
            if key in line:
                try:
                    value = float(line.split(key)[1].split("dB")[0].strip())
                except (IndexError, ValueError):
                    continue
                if setter == "mean":
                    mean = value
                else:
                    peak = value
    return mean, peak


def measure_mean_dbfs(path: Path) -> float | None:
    """Plain mean level of a cue file (dBFS)."""
    return measure_levels_dbfs(path)[0]


def audio_mix_filter(n_sounds: int) -> str:
    """The cue mix graph. The Short's own audio is FIRST: `amix`'s
    `duration=first` keys the output length to its first input, and putting a
    cue first truncated a 38.9 s Short to 0.37 s (2026-09-13)."""
    labels = "".join(f"[s{i}]" for i in range(n_sounds))
    return f"[0:a]{labels}amix=inputs={n_sounds + 1}:duration=first:normalize=0[aout]"


def compose(short: Path, output: Path, spec: SpotlightSpec, work_dir: Path, *, fps: int = 30,
            video_bitrate: str = "12M", preset: str = "slow") -> dict[str, Any]:
    """One extra overlay+audio pass over an already-mastered Short."""
    from . import cta  # level matching, already measured for the CTA

    spec.validate()
    frames = render_overlay_frames(spec, work_dir / "spotlight", fps=fps)
    start, end = spec.span()
    dlg_lufs = cta.measure_file_lufs(short)
    inputs = ["-i", str(short), "-framerate", str(fps), "-start_number", "0", "-i", frames["pattern"]]
    vf = (f"[1:v]format=rgba,setpts=PTS+{frames['start_s']:.4f}/TB[spot];"
          f"[0:v][spot]overlay=0:0:format=yuv444:eof_action=pass:"
          f"enable='between(t,{frames['start_s'] - 0.001:.3f},{frames['end_s'] + 0.05:.3f})'[vs]")
    af = None
    gains: list[dict[str, Any]] = []
    if spec.sounds:
        labels = []
        for i, snd in enumerate(spec.sounds):
            inputs += ["-i", str(snd.path)]
            mean_dbfs, peak_dbfs = measure_levels_dbfs(Path(snd.path))
            if peak_dbfs is None:
                raise ValueError(f"cue sound has no measurable peak: {snd.path}")
            gain = snd.peak_dbfs - peak_dbfs
            gain = max(-60.0, min(12.0, gain))
            gains.append({"path": str(snd.path), "at_s": snd.at_s,
                          "mean_dbfs": mean_dbfs, "peak_dbfs": peak_dbfs,
                          "gain_db": round(gain, 2), "target_peak_dbfs": snd.peak_dbfs,
                          "dialogue_lufs": dlg_lufs})
            label = f"s{i}"
            vf += (f";[{2 + i}:a]adelay={int(round(snd.at_s * 1000))}:all=1,"
                   f"volume={gain:.2f}dB[{label}]")
            labels.append(label)
        af = audio_mix_filter(len(labels))
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
           vf + (";" + af if af else ""),
           "-map", "[vs]", "-map", "[aout]" if af else "0:a",
           "-c:v", "libx264", "-preset", preset, "-b:v", video_bitrate, "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"spotlight compose failed: {proc.stderr[-600:]}")
    receipt = {"short": str(short), "output": str(output), "spec": spec.to_json(),
               "frames": frames, "dialogue_lufs": dlg_lufs, "sounds": gains,
               "span": [round(start, 4), round(end, 4)]}
    (work_dir / "spotlight.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt
