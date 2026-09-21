"""Assemble the upload package for the 2026-09-06 five-story batch.

    python scripts/batch_package.py

Reads each review directory's manifest + REVIEW.txt, applies the text
corrections the review found (the packager wrote "Judge Melisa Boyd" once;
the judge is Stephanie Boyd), censors profanity in every text field, picks the
mastered long-form when one exists, and writes out/batch_2026-09-06/PACKAGE.json
plus one PACKAGE_<slot>.txt per case for the Studio session. The schedule is
one long + its short per day starting 2026-09-07: long 3:00 PM, short 7:00 PM
America/Chicago (no configured times exist in config/pipeline.yaml).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips.censor import censor  # noqa: E402

OUT = ROOT / "out" / "batch_2026-09-06"

# slot order: (day, review dir name, short label)
SLOTS = [
    ("2026-09-07", "2024-03-07_dAKO7myCd-g_8340", "garcia"),
    ("2026-09-08", "2024-07-30_jdzBCVXENUk_3840", "diaz"),
    ("2026-09-09", "2024-03-25_bHAuH5U4NYI_4383", "alonzo"),
    ("2026-09-10", "2026-04-27_H_hXwF2dl7E_3540", "robinson"),
    ("2026-09-11", "2026-05-04_mvGmUbuS0sU_6650", "rodriguez"),   # Miosek re-scored HOLD 71 on its full span
]
LONG_TIME, SHORT_TIME = "3:00 PM", "7:00 PM"

# Short titles reviewed against the short's OWN body text (the packager
# titles the case before SHORTS_EDITOR_V2 picks the mini-story). Each passed
# tools/check_title.py with its transcript on 2026-09-06.
SHORT_TITLE_OVERRIDES = {
    "diaz": "Her Dad's Last Words Were \"What's Up, Angel?\" Read Aloud at Sentencing",
    "robinson": "Judge Boyd: \"Nobody Has Clean Hands.\" Then She Lists Her Issues.",
    "garcia": "\"Which Do You Choose?\" Judge Boyd Offers Jail or a Conviction",
}

FIXES = [
    (re.compile(r"Judge Melis+a Boyd", re.I), "Judge Stephanie Boyd"),
    (re.compile(r"Judge Boyd's 187th District courtroom"), "Judge Boyd's 187th District Court"),
]


def fix_text(s: str) -> str:
    for rx, rep in FIXES:
        s = rx.sub(rep, s)
    return censor(s)


def read_review_description(review: Path) -> str:
    txt = (review / "REVIEW.txt").read_text(encoding="utf-8")
    m = re.search(r"DESCRIPTION \(long-form\)\n-+\n(.*?)\n\n-{10,}", txt, re.S)
    return m.group(1).strip() if m else ""


def main() -> int:
    pkg: list[dict] = []
    for day, name, label in SLOTS:
        review = ROOT / "out" / "review" / name
        if not (review / "manifest.json").exists():
            pkg.append({"day": day, "label": label, "missing": str(review)})
            continue
        m = json.loads((review / "manifest.json").read_text(encoding="utf-8"))
        o = m["outputs"]
        lf = o["longform"]
        sh = o.get("short") or {}
        th = o.get("thumbnail") or {}
        lf_file = next((review / n for n in ("longform_master2.mp4", "longform_mastered.mp4", "longform.mp4")
                        if (review / n).exists()), None)
        desc = fix_text(read_review_description(review))
        entry = {
            "day": day, "label": label, "case_key": m.get("case_key") or f"{m['source']['video_id']}:{int(m['case']['start_s'])}",
            "review_dir": str(review),
            "long": {"title": fix_text(lf["title"]), "file": str(lf_file), "publish": f"{day} {LONG_TIME}",
                     "description": desc, "duration_s": lf.get("duration_s"), "coldopen": lf.get("coldopen")},
            "short": {"title": fix_text(SHORT_TITLE_OVERRIDES.get(label) or sh.get("title") or ""),
                      "packager_title": sh.get("title"),
                      "file": str(review / "short.mp4") if sh else None,
                      "publish": f"{day} {SHORT_TIME}", "duration_s": sh.get("duration_s"),
                      "description": None},   # filled after the long-form ID exists
            "thumbnail": {"file": th.get("file_path"), "mode": th.get("mode"), "candidates": th.get("candidates"),
                          "status": th.get("status")},
            "packaging": {k: m["packaging"].get(k) for k in ("hook_line", "thumbnail_quote", "thumbnail_quote_yellow",
                                                             "title_support_quote", "hook_verified")},
        }
        pkg.append(entry)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "PACKAGE.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")
    for e in pkg:
        if "missing" in e:
            print(f"{e['day']} {e['label']}: MISSING {e['missing']}")
            continue
        lines = [f"# {e['day']}  {e['label']}  ({e['case_key']})", "",
                 f"LONG  {e['long']['publish']}", f"  file:  {e['long']['file']}", f"  title: {e['long']['title']}", "",
                 e["long"]["description"], "",
                 f"SHORT {e['short']['publish']}", f"  file:  {e['short']['file']}", f"  title: {e['short']['title']}", "",
                 f"THUMB {e['thumbnail']['file']}  ({e['thumbnail']['mode']}, {e['thumbnail']['status']})", ""]
        (OUT / f"PACKAGE_{e['day']}_{e['label']}.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"{e['day']} {e['label']}: long {e['long']['duration_s']}s '{e['long']['title']}' | short "
              f"{e['short']['duration_s']}s '{e['short']['title']}' | thumb {e['thumbnail']['mode']}/{e['thumbnail']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
