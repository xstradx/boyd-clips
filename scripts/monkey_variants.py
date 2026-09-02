# -*- coding: utf-8 -*-
"""Build genuinely DIFFERENT Spider Monkey thumbnails, then prove they differ.

Nathan, 2026-08-31: "Make more versions of the thumbnails like different
variations".

The trap this avoids: six parameter tweaks of one layout is not six variations.
Measured on this channel already - our four live thumbnails score 0.32 layout
self-similarity against the competitor set's 0.09, which is what "now it looks
just a like" was pointing at. So every variant below changes the LAYOUT (who is
in it, where, and at what weight), and the set is measured with
thumbeng/variety.py afterwards. Anything above the 0.30 limit against another
variant is reported, not quietly shipped as a choice.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
WORK = r"D:/Boyd Clips/thumbwork/MONKEY"
OUTDIR = os.path.join(WORK, "variants")
CFG = os.path.join(ROOT, "config", "cases.json")

# Each entry is a DIFFERENT COMPOSITION, not a different number.
VARIANTS = [
    dict(tag="V1_monkeyL_boydR",
         note="monkey and Boyd equal weight, monkey left",
         case=dict(defendant_src="monkey_cut.png", def_c=[350, 400],
                   jud_c=[950, 400]),
         white="Where's the", yellow="spider monkey?", kicker=None, arrow=False),

    dict(tag="V2_mirrored",
         note="mirrored - Boyd left, monkey right",
         case=dict(defendant_src="monkey_cut.png", def_c=[930, 400],
                   jud_c=[340, 400]),
         white="Where's the", yellow="spider monkey?", kicker=None, arrow=False),

    dict(tag="V3_threeup_circled",
         note="the original two-up plus the monkey circled between them",
         case=dict(defendant_src="defendant_surgical.png", def_c=[338, 392],
                   jud_c=[942, 392],
                   extra=dict(png="monkey_cut.png", h=420, cx=640, cy=380,
                              spotlight=250, spotlight_strength=0.45,
                              circle=True, circle_pad=1.14, circle_thickness=11)),
         white="Where's the", yellow="spider monkey?", kicker=None, arrow=False),

    dict(tag="V4_threeup_kicker_arrow",
         note="house style - two-up, kicker, arrow, monkey small between",
         case=dict(defendant_src="defendant_surgical.png", def_c=[338, 392],
                   jud_c=[942, 392],
                   extra=dict(png="monkey_cut.png", h=300, cx=640, cy=330,
                              spotlight=200, spotlight_strength=0.40)),
         white="Where's the", yellow="spider monkey?",
         kicker="SHE STOPPED THE PLEA...", arrow=True),

    dict(tag="V5_named_hook",
         note="same as V1 but the monkey has a NAME - Boyd says it on the record",
         case=dict(defendant_src="monkey_cut.png", def_c=[350, 400],
                   jud_c=[950, 400]),
         white="She stopped a plea", yellow="for THIS", kicker=None, arrow=False),

    dict(tag="V6_boyd_dominant",
         note="Boyd big and reacting, monkey smaller and circled off to one side",
         case=dict(defendant_src="defendant_surgical.png", def_c=[240, 430],
                   jud_c=[900, 380], face_h=390,
                   extra=dict(png="monkey_cut.png", h=330, cx=610, cy=420,
                              spotlight=230, spotlight_strength=0.5,
                              circle=True, circle_pad=1.18, circle_thickness=10)),
         white="Where's the", yellow="spider monkey?", kicker=None, arrow=False),
]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    base = json.load(open(CFG, encoding="utf-8"))
    original = json.loads(json.dumps(base["MONKEY"]))   # deep copy to restore
    built = []
    try:
        for v in VARIANTS:
            case = json.loads(json.dumps(original))
            for k in ("extra", "defendant_src", "def_c", "jud_c", "face_h",
                      "solo", "defendant_nudge", "arrow_xy"):
                case.pop(k, None)
            case.update(v["case"])
            base["MONKEY"] = case
            json.dump(base, open(CFG, "w", encoding="utf-8"), indent=1)

            out = os.path.join(OUTDIR, v["tag"] + ".jpg")
            cmd = [sys.executable, "-W", "ignore",
                   os.path.join(ROOT, "tools", "thumb_pipeline.py"), "MONKEY",
                   "--work", WORK, "--out", out,
                   "--white", v["white"], "--yellow", v["yellow"]]
            if v.get("kicker"):
                cmd += ["--kicker", v["kicker"]]
            if not v.get("arrow", True):
                cmd += ["--no-arrow"]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
            tail = [l for l in (r.stdout or "").splitlines()
                    if l.strip().startswith(("PASS", "FAIL", "FLAG", "GATES"))]
            ok = any("GATES PASS" in l for l in tail)
            gates = " ".join(l.split()[1] + ":" + l.split()[0] for l in tail
                             if l.strip().startswith(("PASS", "FAIL", "FLAG")))
            print(f"  {v['tag']:<26} {'OK  ' if ok else 'FAIL'}  {gates}")
            if not ok and not os.path.exists(out):
                err = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
                print(f"      {err.strip()[:200]}")
            if os.path.exists(out):
                built.append((v["tag"], out, v["note"], ok))
    finally:
        base["MONKEY"] = original
        json.dump(base, open(CFG, "w", encoding="utf-8"), indent=1)
        print("\n  (cases.json restored to its original MONKEY config)")

    # PROVE they are different from each other, not six tweaks of one.
    if len(built) > 1:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from thumbeng import variety as V
        print("\n  pairwise layout similarity (limit %.2f - above it they are "
              "the same layout):" % V.SIM_LIMIT)
        worst = 0.0
        for i in range(len(built)):
            for j in range(i + 1, len(built)):
                s = V.layout_sim(built[i][1], built[j][1])
                worst = max(worst, s)
                flag = "  <- SAME LAYOUT" if s >= V.SIM_LIMIT else ""
                print(f"    {built[i][0][:22]:<24} vs {built[j][0][:22]:<24} "
                      f"{s:+.3f}{flag}")
        print(f"\n  worst pair {worst:.3f}   "
              f"{'these are genuinely different' if worst < V.SIM_LIMIT else 'SOME ARE THE SAME LAYOUT'}")
    return built


if __name__ == "__main__":
    main()
