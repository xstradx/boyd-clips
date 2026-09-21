"""Post-render QC for one review directory produced by the daily route.

    python tools/batch_qc.py out/review/<date>_<vid>_<start>

Measures the FILES (not the plan): ffprobe geometry and duration, the R49
cold-open checker on the long-form, integrated loudness, black frames at the
head and tail, and writes two contact sheets (long-form 12 frames, short 8
frames) for a real visual inspection. Results go to <review_dir>/qc.json and
to stdout. This is evidence gathering; the eyes-on pass is still on the sheets.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    return {
        "duration_s": round(float(j["format"].get("duration", 0.0)), 3),
        "width": v.get("width"), "height": v.get("height"), "fps": v.get("avg_frame_rate"),
        "vcodec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
        "acodec": a.get("codec_name"), "channels": a.get("channels"), "sample_rate": a.get("sample_rate"),
        "size_mb": round(int(j["format"].get("size", 0)) / 1e6, 1),
    }


def loudness(path: Path) -> float | None:
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?\d+\.\d) LUFS", r.stderr)
    return float(m[-1]) if m else None


def black_spans(path: Path, t0: float | None = None, dur: float | None = None) -> list[tuple[float, float]]:
    cmd = ["ffmpeg", "-nostats"]
    if t0 is not None:
        cmd += ["-ss", f"{t0:.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vf", "blackdetect=d=0.2:pix_th=0.10", "-an", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    spans = []
    for m in re.finditer(r"black_start:(\d+\.?\d*) black_end:(\d+\.?\d*)", r.stderr):
        a, b = float(m.group(1)), float(m.group(2))
        if t0:
            a, b = a + t0, b + t0
        spans.append((round(a, 2), round(b, 2)))
    return spans


def contact_sheet(path: Path, out: Path, n: int, cols: int, tile_w: int) -> Path:
    d = ffprobe(path)["duration_s"]
    step = d / n
    # one frame at the middle of each of n equal slices
    sel = "+".join(f"eq(n\\,0)" for _ in ())  # placeholder, replaced below
    expr = "select='" + "+".join(f"between(t\\,{step * i + step / 2 - 0.02:.3f}\\,{step * i + step / 2 + 0.02:.3f})"
                                 for i in range(n)) + "'"
    rows = (n + cols - 1) // cols
    vf = f"{expr},scale={tile_w}:-2,tile={cols}x{rows}:padding=4:margin=4"
    subprocess.run(["ffmpeg", "-y", "-nostats", "-loglevel", "error", "-i", str(path), "-vf", vf,
                    "-frames:v", "1", "-q:v", "3", str(out)], check=True)
    return out


def main() -> int:
    review = Path(sys.argv[1]).resolve()
    man = json.loads((review / "manifest.json").read_text(encoding="utf-8"))
    outs = man.get("outputs") or {}
    res: dict = {"review_dir": str(review), "case_key": man.get("case_key") or man.get("case", {}).get("case_key")}

    lf = outs.get("longform") or {}
    lfp = Path(lf.get("file_path") or review / "longform.mp4")
    if lfp.is_file():
        p = ffprobe(lfp)
        res["longform"] = p
        p["loudness_lufs"] = loudness(lfp)
        p["black_head"] = black_spans(lfp, 0.0, 20.0)
        p["black_tail"] = black_spans(lfp, max(0.0, p["duration_s"] - 6.0), None)
        co = subprocess.run([sys.executable, str(ROOT / "tools" / "check_coldopen.py"), str(lfp)],
                            capture_output=True, text=True)
        p["coldopen_check"] = (co.stdout.strip().splitlines() or ["(no output)"])[-1]
        p["coldopen_ok"] = "COLDOPEN_OK" in co.stdout
        p["sheet"] = str(contact_sheet(lfp, review / "qc_longform_sheet.jpg", 12, 4, 480))
        p["cap_fit"] = lf.get("cap_fit")
        p["coldopen_plan"] = lf.get("coldopen")
    else:
        res["longform"] = {"missing": str(lfp)}

    sh = outs.get("short") or {}
    shp = Path(sh.get("file_path") or review / "short.mp4")
    if shp.is_file():
        p = ffprobe(shp)
        res["short"] = p
        p["loudness_lufs"] = loudness(shp)
        p["black_head"] = black_spans(shp, 0.0, 3.0)
        p["black_tail"] = black_spans(shp, max(0.0, p["duration_s"] - 3.0), None)
        p["sheet"] = str(contact_sheet(shp, review / "qc_short_sheet.jpg", 8, 4, 270))
        p["vertical"] = bool(p["width"] and p["height"] and p["height"] > p["width"])
        for k in ("caption_visual_center_error_px", "qc", "captions", "plan_reason", "duration_s"):
            if k in sh:
                p[f"plan_{k}"] = sh[k]
    else:
        res["short"] = {"missing": str(shp), "reason": sh.get("reason") or sh.get("refusal")}

    th = outs.get("thumbnail") or {}
    res["thumbnail"] = {"file_path": th.get("file_path"), "mode": th.get("mode"), "candidates": th.get("candidates"),
                        "exists": bool(th.get("file_path") and Path(th["file_path"]).is_file())}

    (review / "qc.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
