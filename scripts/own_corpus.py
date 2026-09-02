"""Measure Texas Trial Tracker's OWN thumbnails against its OWN view counts.

Why this exists, in Nathan's words 2026-08-29: *"what rules are you basing it
off of?"* The honest answer was bad. `thumb_eval.py`'s baseline is 37 rows of
OTHER channels (courtroomtime, Audit, a competitor set), and several HARD gates
are Nathan's past complaints transcribed into numbers. A rule set built from his
corrections can only ever catch mistakes he already caught.

This channel has 28 videos spanning 55 to 865,000 views and nobody had ever
measured its own winners against its own losers. Same creator, same audience,
same niche - the only comparison that controls for all three.

  python scripts/own_corpus.py            # measure and report
  python scripts/own_corpus.py --gates    # do the CURRENT gates predict wins?
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OWN = ROOT / "research" / "reference" / "ttt_own"
sys.path.insert(0, str(SCRIPTS))

# Subject matters more than any thumbnail choice: the Savanah Soto and
# Christopher Preciado trials are a nationally-followed murder case, the Boyd
# docket clips are routine hearings. Mixing them measures the CASE, not the
# thumbnail. Held out by video id so the comparison stays same-format,
# same-subject.
HOT_CASE = {
    "ztBrTKT2Gbk", "y_43R2cDx-A", "6V1pKKVR17k", "VkgyONGqcGk",
    "Y-_2z7D65Rw", "hpvtEyIqBao", "mZDSXG_dt18", "sp3IXJYBFwY",
    "2cHOGjygdqk",
}

METRICS = ["sat_mean", "val_mean", "rms_contrast", "colorfulness",
           "global_detail", "n_faces", "face_max_h_frac", "text_area_frac",
           "text_max_h_frac", "text_on_face_frac", "wcag_min", "clip_hi",
           "clip_lo", "red_frac", "yellow_frac", "n_text_lines_210",
           "ocr_survival_210"]


def load_index():
    rows = []
    for line in (OWN / "own_index.tsv").read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        vid, views, tab, title = parts[0], int(parts[1]), parts[2], parts[3]
        img = OWN / (vid + ".jpg")
        if img.exists():
            rows.append(dict(id=vid, views=views, tab=tab, title=title,
                             img=img, hot=vid in HOT_CASE))
    return rows


def measured(rows):
    import thumb_eval
    out = []
    for r in rows:
        try:
            m = thumb_eval.measure(str(r["img"]))
        except Exception as exc:
            print("  skip %s: %s" % (r["id"], exc))
            continue
        r = dict(r)
        r["m"] = m
        out.append(r)
    return out


def split(rows):
    """Same-format, same-subject: Boyd docket long-forms only."""
    boyd = [r for r in rows if not r["hot"] and r["tab"] == "videos"]
    boyd.sort(key=lambda r: r["views"], reverse=True)
    half = len(boyd) // 2
    return boyd[:half], boyd[half:], boyd


def report(rows):
    top, bot, boyd = split(rows)
    print("Texas Trial Tracker, its OWN thumbnails vs its OWN views")
    print("Boyd-docket long-forms only (the hot murder-trial uploads are held")
    print("out - they measure the case, not the thumbnail).\n")
    print("  %-9s %8s  %s" % ("id", "views", "title"))
    for r in boyd:
        mark = "WIN " if r in top else "LOSE"
        print("  %s %-9s %8d  %s" % (mark, r["id"], r["views"], r["title"][:52]))

    print("\n  n=%d winners, n=%d losers. This is a SMALL sample - read the"
          % (len(top), len(bot)))
    print("  separations as leads to test, never as settled thresholds.\n")

    print("  %-20s %9s %9s %9s  %s" % ("metric", "winners", "losers", "gap", ""))
    leads = []
    for k in METRICS:
        tv = [r["m"].get(k) for r in top if r["m"].get(k) is not None]
        bv = [r["m"].get(k) for r in bot if r["m"].get(k) is not None]
        if len(tv) < 2 or len(bv) < 2:
            continue
        ta, ba = sum(tv) / len(tv), sum(bv) / len(bv)
        spread = max(abs(x - ta) for x in tv) or 1e-9
        gap = (ta - ba) / spread
        flag = ""
        if abs(gap) >= 1.0:
            flag = "<-- separates"
            leads.append((abs(gap), k, ta, ba))
        print("  %-20s %9.3f %9.3f %+9.2f  %s" % (k, ta, ba, gap, flag))

    print("\n  Strongest separations on THIS channel:")
    for g, k, ta, ba in sorted(leads, reverse=True)[:6]:
        direction = "higher" if ta > ba else "lower"
        print("    %-20s winners run %s (%.3f vs %.3f)" % (k, direction, ta, ba))
    if not leads:
        print("    none clear the bar - on this sample no measured metric"
              " separates winners from losers.")


def gates(rows):
    """Do the CURRENT hard gates actually predict this channel's winners?

    If a gate rejects the channel's own best-performing thumbnails, the gate is
    wrong, not the thumbnails. That is the test the repo never ran.
    """
    import thumb_eval
    top, bot, boyd = split(rows)
    print("Do the CURRENT thumb_eval HARD gates track this channel's results?\n")
    print("  %-24s %8s %8s   %s" % ("gate", "winners", "losers", "verdict"))
    for key, ok, _note in thumb_eval.HARD:
        if key == "_geom":
            continue
        def frac(group):
            n = ok_n = 0
            for r in group:
                v = r["m"].get(key)
                try:
                    passed = ok(v, r["m"])
                except Exception:
                    continue
                n += 1
                ok_n += bool(passed)
            return (ok_n / n) if n else None, n
        tf, tn = frac(top)
        bf, bn = frac(bot)
        if tf is None or bf is None:
            continue
        if tf < 0.5:
            verdict = "REJECTS ITS OWN WINNERS - gate is suspect"
        elif tf > bf:
            verdict = "tracks results"
        elif tf == bf:
            verdict = "no signal on this channel"
        else:
            verdict = "INVERTED - losers pass more often"
        print("  %-24s %7.0f%% %7.0f%%   %s" % (key, tf * 100, bf * 100, verdict))
    print("\n  (percentages are how many of each group PASS the gate)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = measured(load_index())
    if not rows:
        print("no measurable thumbnails in %s" % OWN)
        return 1
    if a.json:
        print(json.dumps([{k: v for k, v in r.items() if k != "img"}
                          for r in rows], indent=1, default=str))
        return 0
    if a.gates:
        gates(rows)
    else:
        report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
