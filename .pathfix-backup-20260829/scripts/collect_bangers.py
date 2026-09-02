"""Copy finished renders out to the Desktop review folder.

Written because the batch runner copied only review folders that did not exist
before the render started. Re-rendering a case reuses its folder - the name is
{date}_{video_id}_{start_s} by design - so on every re-run the diff was empty
and nothing was copied, silently, while the renders themselves succeeded.

Resolve by case key instead. Idempotent: run it any time.

    python scripts/collect_bangers.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "out" / "review"
DEST = Path(r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\BANGERS")

# case_key -> filename stem in the Desktop folder
PICKS = {
    "RzjGikNbHMA:8485": "01_McCaskill_smell_like_marijuana",
    "MiNisjOh61c:2309": "02_JoeGarcia_2yrs",
    "JjRfzudxY1w:4468": "03_Terry_71yo",
    "H_hXwF2dl7E:5383": "04_DiamondGarcia",
    "qSyaR2dc_WU:8644": "05_Aguilar_5yrs",
    "JjRfzudxY1w:345": "06_Wilson_1.4TB",
    "JjRfzudxY1w:6142": "07_Carvajal_4th_revoke",
    "X4fifbLpvYs:10421": "08_Escobar_wrong_charge",
    "UtydTa4kZhk:4072": "09_Ganal_custody",
    "m9CleqGwqKk:8346": "10_JoeGonzalezIV",
}

ASSETS = [
    ("longform.mp4", "{stem}.mp4"),
    ("short.mp4", "{stem}_SHORT.mp4"),
    ("thumbnail_quote.jpg", "{stem}.jpg"),
    ("UPLOAD.txt", "{stem}_COPY.txt"),
]


def review_dir_for(case_key: str) -> Path | None:
    """Folders are named {date}_{video_id}_{int(start_s)}."""
    video_id, start_s = case_key.split(":")
    suffix = f"_{video_id}_{int(round(float(start_s)))}"
    hits = [d for d in REVIEW.iterdir() if d.is_dir() and d.name.endswith(suffix)]
    if not hits:
        return None
    # Newest wins if a docket was ever re-dated.
    return max(hits, key=lambda d: d.stat().st_mtime)


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    copied = missing = 0
    for key, stem in PICKS.items():
        d = review_dir_for(key)
        if d is None:
            print(f"  --   {stem}: not rendered yet")
            missing += 1
            continue
        got = []
        for src_name, dest_pattern in ASSETS:
            src = d / src_name
            if src.is_file():
                shutil.copy2(src, DEST / dest_pattern.format(stem=stem))
                got.append(src_name.split(".")[0])
        if got:
            copied += 1
            print(f"  OK   {stem}: {', '.join(got)}")
        else:
            print(f"  --   {stem}: folder exists but holds no outputs")
    print(f"\n{copied} copied, {missing} still pending -> {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
