"""Build one case's long-form from explicit in/out points.

`rebuild_longform.py` looks its boundaries up in the store, and the store is
built by `find_called_hearings.py`, which splits on the phrase "the court is
calling". The court does not always say it. On 2XkPnvstmRQ that miss merges two
defendants into one 19.5-minute span — the spider monkey case runs 0:00-13:49
and a second defendant's case starts there — which breaks the one-defendant-
per-video rule silently, because the render still succeeds.

So this takes the two boundaries as arguments instead of trusting the segmenter,
and runs the identical code path from there: refine.refine to snap both ends
onto real speech, detect_silences + plan_silence_trim for CONTENT_SPEC §2 dead
air, then render_longform with the branded sting in front and the mark anchored
inside the picture.

    python scripts/build_case_longform.py \
        --source work/2XkPnvstmRQ/2XkPnvstmRQ_h_5915_5895-7108.mp4 \
        --offset 5895.0 --in 5915.92 --out-s 6739.30 \
        --dest "C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/..."

Boundaries are given in SOURCE time (the full stream's clock), the same units
the transcript and the .map.json sidecars use. `--offset` is where the cut file
starts in that clock; getting it wrong shifts every cut, so it is required and
never defaulted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import refine as refine_mod                      # noqa: E402
from boydclips import render                                    # noqa: E402
from boydclips.config import load_config                        # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The channel sting. sting.mp4 is the 1.4s fade-up to the mark and is what the
# SHIPPED Thompson long-form carries (verified by extracting its frame at 0.7s),
# so it is the house default rather than the flashier 2.6s sting_v2.
INTRO = Path(r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\sting.mp4")

DEAD_AIR_S = 4.0     # CONTENT_SPEC §2
KEEP_S = 0.35
MIN_PIECE_S = 0.5

_BRAND = Path(r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand")
WATERMARK_LIGHT = _BRAND / "watermarks_v2" / "wm_brand_halo_40.png"
WATERMARK_DARK = _BRAND / "watermarks" / "wm_02_mark_dark_55.png"


def _background_luminance(source: Path, right_x: int, y: int,
                          lf_cfg: dict, samples: int = 9,
                          origin: tuple[int, int] = (0, 0),
                          scale: float | None = None,
                          pad_y: float = 0.0) -> float | None:
    """Mean luminance of the rectangle the mark will occupy, over `samples`
    frames spread across the source.

    Sampling rather than one frame because a Zoom tile changes: a participant
    stands up, a document is held to camera. One frame can say "dark" about a
    spot that is bright for the other twelve minutes.
    """
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return None
    cw, ch = lf_cfg.get("resolution", [1920, 1080])
    src_w, src_h = render.probe_dimensions(source)
    # canvas pixels -> source pixels. `scale` is the canvas/source factor the
    # render will use; without a crop that is just ch/src_h, but under --two-up
    # the frame is cropped first and then letterboxed, so the inverse has to
    # undo the letterbox and re-add the crop origin or the sample lands on the
    # wrong part of the picture and picks the wrong mark.
    inv = (float(src_h) / float(ch)) if scale is None else (1.0 / scale)
    wm_w = int(round(cw * 0.06 * inv))
    wm_h = max(1, int(round(wm_w * 0.42)))
    margin = int(round(cw * 0.035))
    x0 = int(round((right_x - int(cw * 0.06) - margin // 2) * inv)) + origin[0]
    y0 = int(round((y - pad_y) * inv)) + origin[1]

    dur = float(render.probe_duration(source)) if hasattr(render, "probe_duration") else 0.0
    if dur <= 0:
        import subprocess
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(source)],
            capture_output=True, text=True).stdout.strip() or 0)
    if dur <= 0:
        return None

    import subprocess
    import tempfile
    means = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(samples):
            t = dur * (i + 0.5) / samples
            f = Path(td) / f"{i}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}",
                            "-i", str(source), "-frames:v", "1", str(f), "-y"],
                           capture_output=True)
            if not f.is_file():
                continue
            im = Image.open(f).convert("L")
            means.append(ImageStat.Stat(
                im.crop((x0, y0, x0 + wm_w, y0 + wm_h))).mean[0])
    return sum(means) / len(means) if means else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--offset", type=float, required=True,
                    help="source-time position of the cut file's first frame")
    ap.add_argument("--in", dest="t_in", type=float, required=True)
    ap.add_argument("--out-s", dest="t_out", type=float, required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--no-snap", action="store_true")
    ap.add_argument("--crop", default=None,
                    help="explicit ffmpeg crop=W:H:X:Y, overriding --two-up's "
                         "auto-detection. Needed where detect_tile_crops merges "
                         "the top row with the box below it: on -4WiCeWxBu0 it "
                         "returned 628x708 tiles, i.e. full frame height, "
                         "because the witness box sits under both columns.")
    ap.add_argument("--two-up", action="store_true",
                    help="crop to the two participant tiles, dropping the "
                         "unmanned witness box, and centre the pair")
    a = ap.parse_args()

    source = Path(a.source)
    if not source.is_file():
        print(f"source not found: {source}")
        return 1
    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    lf_cfg = dict(cfg.require("output.longform"))

    print(f"source {source.name} @ offset {a.offset:.1f}")
    print(f"asked  {a.t_in:.2f} -> {a.t_out:.2f}  ({a.t_out - a.t_in:.1f}s)")

    # One decode pass serves both jobs: snapping the two outer boundaries onto
    # real speech, and finding the dead air inside. Detected at 0.30s here
    # because refine needs the fine-grained bursts; the 4.0s spec threshold is
    # applied later by plan_silence_trim, not by the detector.
    fine = render.detect_silences(source, noise_db=-30.0, min_silence_s=0.30)
    print(f"  {len(fine)} silent spans >=0.30s")

    t_in, t_out = a.t_in, a.t_out
    if not a.no_snap:
        f_in, f_out = t_in - a.offset, t_out - a.offset
        s_in, s_out, note = refine_mod.refine(f_in, f_out, fine)
        print(f"  snapped in  {f_in:+.2f} -> {s_in:.2f}  ({s_in - f_in:+.2f}s)")
        print(f"  snapped out {f_out:+.2f} -> {s_out:.2f}  ({s_out - f_out:+.2f}s)")
        print(f"  refine: {note}")
        t_in, t_out = s_in + a.offset, s_out + a.offset

    segs = [render.Segment(start_s=t_in, end_s=t_out)]
    raw = t_out - t_in

    coarse = [s for s in fine if s[1] - s[0] >= DEAD_AIR_S]
    pieces = render.plan_silence_trim(
        segs, coarse, a.offset, min_silence_s=DEAD_AIR_S, keep_s=KEEP_S,
        min_piece_s=MIN_PIECE_S, edge_keep_s=0.05,
    )
    kept = sum(p.duration for p in pieces)
    print(f"  dead air >{DEAD_AIR_S:.0f}s: {raw:.0f}s -> {kept:.0f}s "
          f"(-{raw - kept:.0f}s, {100 * (raw - kept) / raw:.1f}%) "
          f"across {len(pieces)} pieces")

    floor = float(lf_cfg.get("min_duration_s", 120))
    cap = float(lf_cfg.get("max_duration_s", 1200))
    if kept < floor:
        print(f"  REFUSING: {kept:.0f}s under the {floor:.0f}s floor")
        return 1
    if kept > cap:
        print(f"  REFUSING: {kept:.0f}s over the {cap:.0f}s cap")
        return 1
    if [p.start_s for p in pieces] != sorted(p.start_s for p in pieces):
        print("  REFUSING: pieces out of chronological order")
        return 1

    # The mark is anchored inside the RIGHT TILE, not inside the canvas. This
    # docket composites a 2-up with black between and beside the tiles, so both
    # the canvas top and the canvas right edge are black here: the default put
    # the mark half on Judge Boyd's tile and half on the black beside it, which
    # reads as a broken overlay rather than a channel bug. Both anchors are
    # derived from the measured tile rather than hardcoded, so a docket framed
    # differently still lands correctly.
    wm_y = wm_x = None
    crop = None
    tiles = render.detect_tile_crops(source)
    if a.crop:
        rect = [int(v) for v in a.crop.replace("crop=", "").split(":")]
        cwid, chgt, cx0, cy0 = rect
        crop = f"crop={cwid}:{chgt}:{cx0}:{cy0}"
        cw, ch = lf_cfg.get("resolution", [1920, 1080])
        s = min(cw / cwid, ch / chgt)
        pad_y = (ch - chgt * s) / 2.0
        if tiles:
            r2 = [int(v) for v in tiles[-1].replace("crop=", "").split(":")]
            tw, th, tx, ty = r2
            wm_y = int(round(pad_y + max(0, ty - cy0) * s)) + 28
            wm_x = int(round(min(cwid, (tx + tw) - cx0) * s))
        print(f"  explicit crop {crop}  ({cwid}x{chgt}, {cwid/chgt:.2f}:1)")
        print(f"  scaled x{s:.3f}, letterbox {pad_y:.0f}px top and bottom")
        print(f"  watermark y={wm_y} right_x={wm_x}")
        lum = _background_luminance(source, wm_x, wm_y, lf_cfg,
                                    origin=(cx0, cy0), scale=s, pad_y=pad_y)
        if lum is not None:
            pick = WATERMARK_DARK if lum > 140 else WATERMARK_LIGHT
            if pick.is_file():
                lf_cfg["watermark"] = str(pick)
                print(f"  background luminance {lum:.0f}/255 -> {pick.name}")
        tiles = None
    if tiles:
        src_w, src_h = render.probe_dimensions(source)
        cw, ch = lf_cfg.get("resolution", [1920, 1080])
        rect = [int(v) for v in tiles[-1].replace("crop=", "").split(":")]
        tw, th, tx, ty = rect
        l_rect = [int(v) for v in tiles[0].replace("crop=", "").split(":")]
        lw, lh, lx, ly = l_rect

        if a.two_up:
            # Nathan, 2026-08-23: "crop the video to where its just him and
            # judge boyd and not the 3rd box so cut and then scoot down their
            # boxes to center as if the other one wasnt there".
            #
            # This docket is a 3-box Zoom grid: the two participant tiles across
            # the top and an unmanned "Witness" camera pointed at the empty
            # courtroom below them. The witness box is a third of the frame and
            # never has anyone in it, so the two people who matter were being
            # rendered at two thirds scale for nothing.
            #
            # Crop to the union of the two top tiles, then let render_longform's
            # existing scale+pad do the rest: it scales the strip to the canvas
            # width and pads equally top and bottom, which centres the pair
            # vertically — the "scoot down" — rather than leaving them stuck to
            # the top edge with the dead box's black underneath.
            cx0, cy0 = min(lx, tx), min(ly, ty)
            cx1, cy1 = max(lx + lw, tx + tw), max(ly + lh, ty + th)
            cwid, chgt = cx1 - cx0, cy1 - cy0
            crop = f"crop={cwid}:{chgt}:{cx0}:{cy0}"
            # Canvas geometry after that crop, so the mark still lands inside
            # Judge Boyd's tile rather than in the new letterbox.
            s = min(cw / cwid, ch / chgt)
            pad_y = (ch - chgt * s) / 2.0
            wm_y = int(round(pad_y + (ty - cy0) * s)) + 28
            wm_x = int(round(((tx + tw) - cx0) * s))
            print(f"  two-up crop {crop}  ({cwid}x{chgt}, {cwid/chgt:.2f}:1)")
            print(f"  scaled x{s:.3f}, letterbox {pad_y:.0f}px top and bottom")
        else:
            s = float(ch) / float(src_h)
            wm_y = int(round(ty * s)) + 28
            wm_x = int(round((tx + tw) * s))
        print(f"  watermark anchored to right tile: y={wm_y} right_x={wm_x}")

        # Light or dark mark, decided by MEASURING what is behind it rather than
        # by picking one and hoping. The white mark is the house default and is
        # correct over courtroom footage, but this docket's right tile is a
        # cream wall with the Bexar County seal on it: sampled across nine
        # frames the mark's own rectangle sits at mean luminance 182/255, and
        # every white variant tested — 40%, 55%, halo, mono — vanished into it
        # with only the red star showing. The dark mark on the same spot reads
        # cleanly. The threshold is the midpoint of the range measured across
        # the eight tile corners on this source (46.6 to 246.7).
        lum = _background_luminance(
            source, wm_x, wm_y, lf_cfg,
            origin=(cx0, cy0) if a.two_up else (0, 0),
            scale=s if a.two_up else None,
            pad_y=pad_y if a.two_up else 0.0)
        if lum is not None:
            pick = WATERMARK_DARK if lum > 140 else WATERMARK_LIGHT
            if pick.is_file():
                lf_cfg["watermark"] = str(pick)
                print(f"  background luminance {lum:.0f}/255 -> {pick.name}")
            else:
                print(f"  WARNING: {pick.name} missing, keeping configured mark")
    else:
        print("  WARNING: no tile crop detected, watermark uses canvas margin")

    intro = INTRO if INTRO.is_file() else None
    if intro is None:
        print(f"  REFUSING: intro missing: {INTRO}")
        return 1

    out = Path(a.dest)
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = render.render_longform(source, a.offset, pieces, lf_cfg, out,
                                 crop=crop, intro=intro, watermark_y=wm_y,
                                 watermark_right_x=wm_x)
    print(f"  rendered {dur:.1f}s ({dur / 60:.1f} min) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
