"""Turn a moment index into edit suggestions the editor can show.

Nathan: "I want you to suggest how the video should be edited and explain why
and which has the best hook and what not" - and then, when I answered in chat,
"No I meant in the editor".

So the reasoning has to be a file the page can render, not prose in a message,
and it has to be produced per hearing rather than hardcoded for the monkey one.

Three things come back:
  * the best HOOK, with the reason it is the hook
  * a ROLE for every moment (hook / setup / escalation / payoff / filler), so
    the card can say what a clip is FOR rather than only what happens in it
  * two or three PLANS - complete shorts, in play order, each clip carrying the
    reason it sits where it sits

Plans are ordered for the short, where reordering is allowed. The long-form
never gets reordered (SAFETY_RULES R5), so nothing here applies to it.

The model is given Nathan's taste in his own words. Paraphrasing it into
tidier language is exactly how the target drifts, so the quotes are verbatim.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import refine, render            # noqa: E402
from boydclips.llm import ClaudeCliBackend      # noqa: E402

# His words, not my summary of them.
TASTE = """Nathan owns the channel. His taste, in his own words:

  "She goes off on people and really calls people out and people give up their
   right to stay silent and they have to talk"

  "it's also when people have ridiculous excuses"

  "And it's dead serious but funny to us or like oh damn, or when she scolds a
   person for doing something bad so also it's when it's harsh too if that
   makes sense?"

  "Like these videos are like almost funny do you get what I mean?"

  "people really like it when she's harsh"

  "the short is the advert"      (the short exists to pull viewers to the
                                  long-form, so it must open a loop, not
                                  summarise the hearing)

  "You could reorder the shorts for the hook just not long form"
"""

SYSTEM = """You plan how to cut a SHORT from an indexed court hearing.

""" + TASTE + """
You are given the hearing's moments in order, each with an index, a timecode
relative to the hearing, a length, a punch rating 1-5 and a description.

Return:

1. hook - the single moment that should OPEN the short, and why. Judge it on
   whether it stops a scroll with no setup: does it pose a question, or is it
   absurd or harsh on its face? A moment that needs context to land is not a
   hook however good it is later. Do not default to the highest punch rating -
   the best payoff and the best hook are usually different moments.

2. roles - a role for EVERY moment index:
     hook       could open the short cold
     setup      needed so a later moment lands
     escalation raises the temperature
     payoff     lands the arc; the button at the end
     filler     procedure, no use in a short
   plus a short note saying what it is FOR, not what happens in it.

3. plans - two or three complete shorts, each 3 to 6 clips, in PLAY ORDER.
   Aim for 40-50 seconds of raw length. Every cut is afterwards snapped onto the
   real speech boundaries in the audio, which lengthens a plan by roughly 15%,
   so a plan that measures 60s here finishes over the limit. The indexed lengths are longer
   than you need, so for EVERY clip give keep_s: how many seconds of it to keep,
   and trim_from: "start" to drop the front, "end" to drop the tail, or "none"
   if it is already short enough. The sum of keep_s across a plan must land
   between 45 and 60 - add it up before you answer, and drop a clip rather than
   run over. Put that sum in target_s.
   Give each plan a short name and one sentence on what makes it work. Every
   clip carries the reason it sits in that position.
   Make the plans genuinely different from each other - a funny arc and a harsh
   arc are two videos, not two versions of one.

Be concrete and specific to this hearing. Never name the defendant."""

SCHEMA = {
    "type": "object",
    "required": ["hook", "roles", "plans"],
    "properties": {
        "hook": {
            "type": "object", "required": ["i", "why"],
            "properties": {"i": {"type": "integer"}, "why": {"type": "string"}},
        },
        "roles": {
            "type": "array",
            "items": {
                "type": "object", "required": ["i", "role", "note"],
                "properties": {
                    "i": {"type": "integer"},
                    "role": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
        "plans": {
            "type": "array",
            "items": {
                "type": "object", "required": ["name", "why", "target_s", "clips"],
                "properties": {
                    "name": {"type": "string"},
                    "why": {"type": "string"},
                    "target_s": {"type": "number"},
                    "clips": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["i", "why", "keep_s", "trim_from"],
                            "properties": {"i": {"type": "integer"},
                                           "why": {"type": "string"},
                                           "keep_s": {"type": "number"},
                                           "trim_from": {"type": "string"}},
                        },
                    },
                },
            },
        },
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--base", type=float, required=True,
                    help="source seconds at the hearing's t=0, for readable timecodes")
    ap.add_argument("--model", default="claude-opus-5")
    args = ap.parse_args()

    mpath = ROOT / "state" / f"moments_{args.video}.json"
    raw = json.loads(mpath.read_text(encoding="utf-8"))
    moments = raw.get("moments", raw) if isinstance(raw, dict) else raw
    moments.sort(key=lambda m: m["start"])

    lines = []
    for i, m in enumerate(moments):
        t = m["start"] - args.base
        lines.append("[%d] %d:%02d  %ds  punch %d  %s - %s" % (
            i, int(t // 60), int(t % 60), round(m["end"] - m["start"]),
            m["punch"], m["label"], m.get("what", "")))

    print("%d moments -> asking %s" % (len(moments), args.model))
    be = ClaudeCliBackend(model=args.model, timeout_s=900)
    out = be.complete(SYSTEM, "\n".join(lines), SCHEMA, "suggest")

    n = len(moments)
    out["roles"] = [r for r in out.get("roles", []) if 0 <= r["i"] < n]
    good = []
    for p in out.get("plans", []):
        p["clips"] = [c for c in p.get("clips", []) if 0 <= c["i"] < n]
        if p["clips"]:
            full = 0.0
            for c in p["clips"]:
                m = moments[c["i"]]
                span = m["end"] - m["start"]
                full += span
                keep = float(c.get("keep_s") or span)
                c["keep_s"] = round(max(2.0, min(span, keep)), 1)
                if c.get("trim_from") not in ("start", "end", "none"):
                    c["trim_from"] = "end"
            p["full_s"] = round(full, 1)
            p["actual_s"] = round(sum(c["keep_s"] for c in p["clips"]), 1)
            good.append(p)
    out["plans"] = good
    if not (0 <= out.get("hook", {}).get("i", -1) < n):
        out["hook"] = {"i": 0, "why": ""}

    # ---- snap every proposed cut onto the audio ------------------------------
    # The model only ever sees transcript timings, and those say where a WORD is,
    # never where a LINE starts or lands. Measured on the first plan it produced,
    # 5 of 5 cuts were defective: three opened 1.5-3.1s INTO a sentence and four
    # ended mid-word. This is not a prompting problem and cannot be prompted
    # away, so it is corrected here, from the audio, before anything is saved.
    srcs = sorted((ROOT / "work" / args.video).glob(args.video + "_h_*.mp4"))
    if srcs and out.get("plans"):
        src = srcs[0]
        m = re.search(r"_(\d+)-(\d+)\.mp4$", src.name)
        sec = float(m.group(1)) if m else 0.0
        print("snapping cuts to the audio ...")
        sil = render.detect_silences(src, noise_db=-32.0, min_silence_s=0.18)
        fine = render.detect_silences(src, noise_db=-32.0, min_silence_s=0.07)
        for pl in out["plans"]:
            total = 0.0
            for c in pl["clips"]:
                mm = moments[c["i"]]
                span = mm["end"] - mm["start"]
                keep = min(float(c.get("keep_s") or span), span)
                if c.get("trim_from") == "none":
                    a, b = mm["start"], mm["end"]
                elif c.get("trim_from") == "start":
                    a, b = mm["end"] - keep, mm["end"]
                else:
                    a, b = mm["start"], mm["start"] + keep
                na, nb, note = refine.refine(a - sec, b - sec, sil, None, fine)
                c["a"] = round(na + sec, 2)          # what the editor and the
                c["b"] = round(nb + sec, 2)          # renderer both use
                c["snap"] = note
                total += nb - na
            # snapping lengthens a plan, so bring it back under the limit by
            # pulling ends to real boundaries rather than shaving seconds
            segs = [(c["a"] - sec, c["b"] - sec) for c in pl["clips"]]
            segs, fitnotes = refine.fit_to_limit(segs, sil, fine)
            for c, (na2, nb2) in zip(pl["clips"], segs):
                c["a"], c["b"] = round(na2 + sec, 2), round(nb2 + sec, 2)
                c["keep_s"] = round(nb2 - na2, 1)
            pl["actual_s"] = round(sum(b - a for a, b in segs), 1)
            if fitnotes:
                pl["fit"] = fitnotes
        print("  plans now: " + ", ".join("%.0fs" % pl["actual_s"] for pl in out["plans"]))

    dest = ROOT / "state" / f"suggest_{args.video}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote " + str(dest))
    print("  hook: [%d] %s" % (out["hook"]["i"], moments[out["hook"]["i"]]["label"]))
    for p in out["plans"]:
        print("  plan: %-26s %d clips  %.0fs trimmed (from %.0fs)"
              % (p["name"], len(p["clips"]), p["actual_s"], p["full_s"]))


if __name__ == "__main__":
    main()
