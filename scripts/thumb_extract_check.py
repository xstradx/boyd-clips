"""Run the direct_gen asset extraction alone for finished review directories
and lay the cutouts out on one sheet, so the defendant reference can be
checked BEFORE any image-generation quota is spent.

    python scripts/thumb_extract_check.py out/review/<dir> [more dirs...]

Writes D:/Boyd Clips/thumbwork/<section stem>/ (the same work dir
thumbnail.build_direct uses) and out/batch_2026-09-06/extract_sheet.jpg.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import thumb_direct as TD                      # noqa: E402
from boydclips.pipeline import Pipeline        # noqa: E402


def main() -> int:
    from PIL import Image, ImageDraw
    pipe = Pipeline()
    panels = []
    for arg in sys.argv[1:]:
        review = Path(arg).resolve()
        man = json.loads((review / "manifest.json").read_text(encoding="utf-8"))
        m = re.search(r"_([A-Za-z0-9_-]{11})_(\d+)$", review.name)
        vid, start = m.group(1), m.group(2)
        case = pipe.store.get_case(f"{vid}:{start}") or {}
        source = sorted((pipe.work / vid).glob(f"{vid}_{start}_*.mp4"))[-1]
        offset = float(re.search(r"_(\d+)-\d+\.mp4$", source.name).group(1))
        key = source.stem
        c = {"_key": key, "video": str(source), "offset": offset,
             "plate_t": float(case.get("hook_start_s") or 0.0), "call_t": float(case.get("start_s") or 0.0)}
        wd = TD.THUMBWORK / key
        got = TD.extract_from_video(c, wd)
        info = json.loads((wd / "extraction.json").read_text(encoding="utf-8"))
        print(review.name, json.dumps(info))
        row = [wd / "courtroom_tile.png"] + got.get("defendant", []) + got.get("boyd", [])
        panels.append((review.name, row))
    sheet = Image.new("RGB", (1500, 360 * len(panels)), "black")
    d = ImageDraw.Draw(sheet)
    for i, (name, row) in enumerate(panels):
        x = 0
        d.text((4, i * 360 + 2), name, fill="yellow")
        for p in row:
            im = Image.open(p).convert("RGBA")
            im.thumbnail((620, 330))
            bg = Image.new("RGB", im.size, (40, 120, 40))
            bg.paste(im, mask=im.split()[3])
            sheet.paste(bg, (x, i * 360 + 20))
            x += im.width + 10
    out = ROOT / "out" / "batch_2026-09-06" / "extract_sheet.jpg"
    sheet.save(out, quality=88)
    print("sheet", out)
    pipe.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
