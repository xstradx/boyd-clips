"""Find the moments Nathan actually wants: "she went there."

Not humour and not a courtroom reaction. Nathan's spec, in his words: dead
serious but funny to us, "or like oh damn", and it counts when she scolds
someone harshly too. One shape, two flavours - a ridiculous excuse demolished,
or something genuinely bad scolded.

Two earlier attempts failed and are recorded so nobody repeats them:

  * [laughter] markers surfaced staff banter between cases. The room does not
    laugh at these; someone is facing prison. Wrong signal entirely.
  * Scoring her language for novelty found the punchlines by accident but could
    not find more, because the setup is what makes them findable.

The discriminator here is that she puts HERSELF in it - her nose, her mind, her
walk to work in heels, her hair getting wet. First person and second person
together, at length, is her comparing herself to the person in front of her.
Procedural speech carries neither.
"""
from __future__ import annotations
import json, glob, os, re

FIRST  = re.compile(r"\b(i|i'm|i've|i'll|my|me|myself)\b", re.I)
SECOND = re.compile(r"\b(you|you're|your|you've|you'll|yourself)\b", re.I)
# She turns the screw with rhetorical setups rather than volume.
RHET   = re.compile(r"\bguess what\b|\byou know what\b|\bhere'?s the thing\b|"
                    r"\bdo you know how many\b|\blet me tell you\b|\blet me ask you\b|"
                    r"\bi'?m going to tell you\b|\byou know what'?s going to happen\b|"
                    r"\bdo you think\b|\bwhat do you think\b|\bi always tell\b", re.I)
VERDICT= re.compile(r"\bthat'?s not a\b|\bthat'?s what\b|\bnobody'?s obligated\b|"
                    r"\byou'?re an adult\b|\byou'?re a grown\b|\bthose were\b|"
                    r"\bthat'?s a choice\b|\bmade the choice\b|\bno excuse\b|"
                    r"\bstop\b|\bdon'?t\b", re.I)
EXCUSE = re.compile(r"\bi couldn'?t\b|\bi didn'?t have\b|\bstole my\b|\bmy ride\b|"
                    r"\bwasn'?t my fault\b|\bi didn'?t know\b|\bi forgot\b|"
                    r"\bi was going to\b|\bi tried to\b|\bnobody told me\b|"
                    r"\bit was a mistake\b|\bi lost my\b|\bmy phone\b", re.I)
PROC   = re.compile(r"\bcause number\b|\bmotion to\b|\bstate'?s exhibit\b|\breset\b|"
                    r"\bcall the docket\b|\bplea of\b|\barraign\b|\bapproach the bench\b|"
                    r"\braise your right hand\b|\bsolemnly swear\b|\bcourt reporter\b", re.I)



# --- speaker attribution -------------------------------------------------
# The >> markers are reliable: median turn is 8 words, p90 is 40, and only
# ~0.9% of turns look merged. But this finder only considers turns of 55-320
# words, and the rare merges are all long - so they were over-represented at
# the top of the ranking and produced a garbage first result.
#
# Validated against seven moments known to be real and three known to be junk:
# 5/7 good kept, 3/3 junk rejected.
DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?am|sir)\b|\bthank you,? judge\b", re.I)
CTRL  = re.compile(r"\ball right\b|\bhave a seat\b|\bthe court\b|\bcounsel\b|"
                   r"\bwe can go off\b|\bi'?m going to\b|\bhere'?s the thing\b|"
                   r"\blet me ask you\b|\bguess what\b", re.I)
BACK  = re.compile(r"\b(yeah|okay|oh|mhm|uh-huh|right|yep|mm)\b", re.I)


def is_boyd(txt, nxt):
    """Is this turn hers, or did someone else's speech get absorbed into it?

    Deference is the giveaway: people say "your honour" and "yes ma'am" TO her,
    so finding it inside a turn means the turn is not purely hers. Backchannel
    density catches the rest - a merged block carries both sides of a
    conversation and is thick with "yeah / okay / oh"; a riff is not.

    Known gap: where the transcript genuinely merged a short reply into a long
    Boyd turn, a real moment is dropped. That costs recall, not precision, and
    precision is what a ranked list needs.
    """
    wc = len(txt.split())
    if DEFER.search(txt):
        return False
    if wc >= 60 and len(BACK.findall(txt)) / (wc / 100.0) >= 7:
        return False
    return bool(CTRL.search(txt)) or bool(nxt and DEFER.search(nxt))

def turns(words):
    cur_t, buf, out = None, [], []
    for it in words:
        w = it.get("w", "")
        if w.strip().startswith(">>"):
            if buf:
                out.append((cur_t, " ".join(buf)))
            buf, cur_t = [], it.get("t", 0.0)
            w = w.strip()[2:]
        if cur_t is None:
            cur_t = it.get("t", 0.0)
        if w.strip():
            buf.append(w.strip())
    if buf:
        out.append((cur_t, " ".join(buf)))
    return out


def main():
    rows = []
    for tp in sorted(glob.glob("work/*/*.transcript.json")):
        try:
            d = json.load(open(tp, encoding="utf-8"))
        except Exception:
            continue
        vid = d.get("video_id") or os.path.basename(tp).split(".")[0]
        ts = turns(d.get("words") or [])
        for i, (t, txt) in enumerate(ts):
            wc = len(txt.split())
            if not (55 <= wc <= 320):
                continue
            proc = len(PROC.findall(txt))
            if proc >= 2:
                continue
            nxt = ts[i + 1][1] if i + 1 < len(ts) else ""
            if not is_boyd(txt, nxt):
                continue                       # someone else's speech in here
            f = len(FIRST.findall(txt))
            s = len(SECOND.findall(txt))
            if f < 3 or s < 5:
                continue                       # not her comparing herself to them
            per100 = 100.0 / wc
            setup = " ".join(x[1] for x in ts[max(0, i - 3):i])
            sc = 0.0
            sc += min(24, f * per100 * 2.6)          # she is in it
            sc += min(24, s * per100 * 2.2)          # aimed at them
            sc += min(20, len(RHET.findall(txt)) * 9.0)
            sc += min(14, len(VERDICT.findall(txt)) * 4.5)
            sc += min(14, len(EXCUSE.findall(setup)) * 7.0)   # the setup
            sc -= proc * 8
            if wc < 70:
                sc -= 6
            rows.append({"video_id": vid, "t": round(t, 1), "score": round(sc, 1),
                         "words": wc, "first": f, "second": s,
                         "rhet": len(RHET.findall(txt)),
                         "excuse_in_setup": len(EXCUSE.findall(setup)),
                         "setup": setup[-260:], "bench": txt})
    rows.sort(key=lambda r: -r["score"])
    os.makedirs("state", exist_ok=True)
    json.dump(rows[:500], open("state/wentthere.json", "w", encoding="utf-8"), indent=1)
    print(f"candidates: {len(rows)}   -> state/wentthere.json (top 500)\n")
    for r in rows[:10]:
        t = int(r["t"])
        print(f"[{r['score']:5.1f}] youtu.be/{r['video_id']}?t={max(0,t-12)}  "
              f"({t//3600}:{(t%3600)//60:02d}:{t%60:02d})  "
              f"{r['words']}w  I={r['first']} you={r['second']} rhet={r['rhet']} "
              f"excuse={r['excuse_in_setup']}")
        if r["excuse_in_setup"]:
            print(f"    SETUP: ...{re.sub(r's+',' ',r['setup']).strip()[-170:]}")
        print(f"    BOYD:  {re.sub(r'  +',' ',r['bench']).strip()[:330]}\n")


if __name__ == "__main__":
    main()
