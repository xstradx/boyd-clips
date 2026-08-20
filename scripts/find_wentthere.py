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

# Trials are not the product. Nathan, 2026-08-20: when the third camera is on
# the witness chair with someone in it, that is an actual trial, and that is
# not what we are here clipping. Trials read as lawyer-and-witness Q&A, so most
# already fail the tests below - this catches the rest. Measured at 5% of 500
# candidates, and 1 of the top 30.
#
# The stronger check is visual and lives in render.detect_tile_grid(): an empty
# witness chair scores about 1.7 on temporal variance, an occupied one is high.
TRIAL  = re.compile(r"\braise your right hand\b|\bsolemnly swear\b|\bstate calls\b|"
                    r"\bladies and gentlemen of the jury\b|\bmembers of the jury\b|"
                    r"\bjury panel\b|\bvoir dire\b|\bstrike for cause\b|"
                    r"\bcross-examination\b|\bapproach the witness\b|"
                    r"\bsustained\b|\boverruled\b", re.I)

# Bond hearings are what other editors avoid hardest. Measured across 553 of
# their clips aligned onto our own dockets: bond language appears in 0.8% of
# clipped turns against 7.0% outside - 0.12x, an eight-fold avoidance. Trials
# score 0.40x, which confirms Nathan's instruction from a separate source, and
# revocations 1.50x. Plea and sentencing is flat at 1.01x, so it is noise.
#
# This is the one signal today measured against other people's editorial
# choices rather than against this scorer's own output, so it is not circular.
# Applied as a penalty, not an exclusion: 'bond' appears incidentally in
# hearings that are not about bond.
BOND   = re.compile(r"\bbond\b|\bsurety\b|\bpersonal recognizance\b|"
                    r"\bmagistrat\w+\b", re.I)

# She has read the file and says so. This is the strongest signal in Nathan's
# 28 labels - 0.79 hits per post against 0.14 per skip, and present in 36% of
# posts against 14% of skips - and it independently matches the competitor
# study in section 2, which measured 'Boyd produces a receipt' at 6 winners and
# 0 losers. Two unrelated sources, same conclusion, and this scorer previously
# gave it nothing.
RECEIPT = re.compile(r"\bi'?ve read\b|\bi read\b|\bit says\b|"
                     r"\bsays right here\b|\bmy notes\b|\bthe report\b|"
                     r"\baccording to\b|\bi'?m looking at\b|\bthe summary\b|"
                     r"\byour (own )?(text|message|letter)s?\b|\bin front of me\b|"
                     r"\bi know (that )?from reading\b|\brecords? (show|indicate)\b|"
                     r"\bthe file\b|\bindicates?\b", re.I)

# Her questions, split by what they DO. Nathan: 'can you not see where judge
# Boyd asks questions but not just any questions the ones actually worth
# clipping'. He is right, and it is the first signal here that is a speech act
# rather than a word count - which is why the vocabulary features all reversed
# on held-out data and this one did not.
#
# Held out (12 post / 15 skip), per 100 words:
#   challenge question   0.43 post vs 0.07 skip   present 5/12 vs 2/15
#   procedural question  0.04 post vs 0.17 skip   1/12 vs 4/15
#   tag question         0.14 post vs 0.29 skip   2/12 vs 6/15
#
# Small counts, and the patterns were written after reading that batch's
# questions, so this is provisional until it survives a fresh batch.
PROC_Q  = re.compile(r"\b(do|did) you understand\b|\bis that correct\b|"
                     r"\bany objection\w*\b|\bhow do you plead\b", re.I)
TAG_Q   = re.compile(r",?\s*(right|okay|correct)\s*\?", re.I)
CHALL_Q = re.compile(r"[^.?!]*\b(why|what|how|who)\b[^.?!]*\byou\b[^.?!]*\?|"
                     r"[^.?!]*\bdo you (know|think|want|realize|expect)\b[^.?!]*\?|"
                     r"[^.?!]*\bare you (serious|kidding|telling me)\b[^.?!]*\?", re.I)



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


def setup_probe(ts, i):
    """The few turns before this one, used to test the run-up for trial talk."""
    return " ".join(x[1] for x in ts[max(0, i - 3):i])

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
            if TRIAL.search(txt) or TRIAL.search(setup_probe(ts, i)):
                continue                       # a trial, not a docket
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
            # Refitted 2026-08-20 against 28 labelled moments. The previous version
            # scored 61.6 on posts and 62.4 on skips - it did not rank at all. What
            # survives measurement, and nothing else, is used here.
            sc = 0.0
            recpt = len(RECEIPT.findall(txt + ' ' + setup))
            sc += min(30, recpt * 15.0)              # 5.6x separation, dual-confirmed
            
            # Aimed at them, not about herself. you:I was 1.79 on posts, 1.26 on
            # skips, and raw first-person density ran HIGHER on skips - the earlier
            # 'she puts herself in it' weight had the wrong sign.
            ratio = s / max(1.0, float(f))
            sc += min(26, max(0.0, ratio - 0.9) * 20.0)
            sc += min(16, s * per100 * 1.4)
            
            # Kept, but small: these never separated the two piles on their own.
            sc += min(8, len(RHET.findall(txt)) * 4.0)
            sc += min(8, len(VERDICT.findall(txt)) * 2.5)
            
            # The excuse bonus is GONE. Nathan offered ridiculous excuses as an
            # illustration and it was anchored on as a specification; his labels put
            # 1 excuse among 14 posts and 7 among 14 skips. Not inverted into a
            # penalty either - 8 hits cannot tell a bad detector from a bad idea.
            
            # The question layer - the strongest held-out signal so far.
            sc += min(30, len(CHALL_Q.findall(txt)) * 12.0)
            sc -= min(14, len(PROC_Q.findall(txt)) * 7.0)
            sc -= min(12, len(TAG_Q.findall(txt)) * 4.0)

            sc -= proc * 8
            sc -= min(18, len(BOND.findall(txt)) * 6.0)
            if wc > 260:
                sc -= 6                              # posts averaged 159 words, skips 180

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
