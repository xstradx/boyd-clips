"""Solve each variant's vertical placement by MEASURING it, not assuming it.

A MarginV positions the text BOX. Every font carries its own internal leading,
and a solid-box or marker style adds padding on top of that, so the ink lands
somewhere else. Rather than hardcode a per-font constant, render the subtitles
over black, take the ink bounding box, and solve for the offset.

Targets, same as the approved cut:
    defendant  ink BOTTOM at SPLIT - GAP   (grows up, away from the divide)
    Boyd       ink TOP    at SPLIT + GAP   (grows down, away from it)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from caption_variants import PLAY_H, SPLIT, GAP, VARIANTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VD = ROOT / "work/_variants"
ASS = VD / "ass"
FR = VD / "frames"
PROBE = {"D": 12.75, "B": 35.30}      # a moment where each speaker is on


def render(ass: Path, at: float, dest: Path):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", f"color=black:s=1080x1920:d=60:r=25",
         "-vf", f"subtitles=ass/{ass.name}:fontsdir=fonts",
         "-ss", f"{at}", "-frames:v", "1", "-y", str(dest)],
        cwd=VD, check=True)


def ink(png: Path):
    a = np.array(Image.open(png).convert("L"))
    rows = np.where(a.max(axis=1) > 12)[0]
    if not len(rows):
        return None
    return int(rows[0]), int(rows[-1])


def main():
    leads = {}
    FR.mkdir(exist_ok=True)
    for v in VARIANTS:
        ass = ASS / f"{v.key}.ass"
        cur = v.lead.copy()
        row = {}
        for who, at in PROBE.items():
            out = FR / f"cal_{v.key}_{who}.png"
            render(ass, at, out)
            got = ink(out)
            if got is None:
                print(f"  {v.key:13s} {who}: NO INK at t={at} -- skipped")
                row[who] = 0.0
                continue
            top, bot = got
            if who == "D":
                margin = PLAY_H - (SPLIT - GAP + cur.get("D", 0.0))
                lead = (PLAY_H - margin) - bot
            else:
                margin = SPLIT + GAP - cur.get("B", 0.0)
                lead = top - margin
            row[who] = float(lead)
            print(f"  {v.key:13s} {who}: ink {top}..{bot}  lead {lead:+.0f}")
        leads[v.key] = row
    (VD / "leads.json").write_text(json.dumps(leads, indent=1), encoding="utf-8")
    print(f"\nwrote {VD / 'leads.json'}")


if __name__ == "__main__":
    main()
