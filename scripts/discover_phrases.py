"""Mine Judge Boyd's CHEW-OUT vocabulary from the corpus.

FIRST ATTEMPT, RECORDED SO IT IS NOT RETRIED: split turns into JUDICIAL vs
OTHER using authority-phrase seeds, then mine n-grams enriched in judicial
turns. That was circular - the seeds define the split, so seed phrases came
back with lift in the thousands - and it surfaced only procedural boilerplate
("the court will find there's sufficient evidence", "raise your right hand").
Correct, useless, and not what anybody wants to watch.

THE RIGHT CONTRAST, which this does: among turns that are ALREADY hers, split
by LENGTH. A short judicial turn is procedure - calling the case, taking the
plea, reading conditions. A long one is her going off: the riff, the lecture,
the chew-out. Nathan, 2026-08-18: "when she chews people out."

So mine n-grams enriched in LONG judicial turns against SHORT ones. Both sides
are the same speaker, so anything that survives is about REGISTER, not about
who is talking.
"""
import re, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from boydclips.transcribe import Transcript

# Only used to decide "is this the bench speaking". Deliberately boring.
JUDICIAL_SEED = re.compile(
    r"\b(the court (will|is|finds|orders|accepts)|i'?m going to (sentence|order|find|accept)"
    r"|do you understand|sustained|overruled|have a seat|raise your right hand"
    r"|you'?re (placed on|sentenced to)|i'?ll accept|community supervision"
    r"|deferred adjudication|go (on|off) the record|anything further"
    r"|call(ing)? the next|court costs)\b", re.I)

# Anything containing these is procedural no matter how long it runs, and
# would otherwise flood the LONG side with plea colloquy and condition-reading.
BOILER = re.compile(
    r"\b(sufficient evidence|exhibits one and attachments|application for deferred"
    r"|state jail facility|court costs|fine probated|no contact with"
    r"|report to the (probation|community supervision)|urinalysis|restitution in the amount"
    r"|right to appeal|waive)\b", re.I)

LONG_WORDS = 70      # a riff
SHORT_WORDS = 30     # procedure


def turns(t):
    idx = [i for i, w in enumerate(t.words) if ">>" in w.w]
    out = []
    for a, b in zip(idx, idx[1:] + [len(t.words)]):
        txt = " ".join(w.w for w in t.words[a:b]).replace(">>", " ").strip()
        if txt:
            out.append((t.words[a].t, txt))
    return out


def ngrams(text, n):
    ws = re.findall(r"[a-z']+", text.lower())
    return [" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)]


files = sorted((ROOT / "work").glob("*/*.transcript.json"))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200
files = files[:limit]

long_c, short_c = collections.Counter(), collections.Counter()
n_long = n_short = 0
samples = []
for f in files:
    try:
        t = Transcript.from_json(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    for ts, txt in turns(t):
        if not JUDICIAL_SEED.search(txt):
            continue
        n = len(txt.split())
        if n >= LONG_WORDS and not BOILER.search(txt):
            n_long += 1
            for k in (3, 4, 5):
                long_c.update(set(ngrams(txt, k)))
            if len(samples) < 4000:
                samples.append((t.video_id, ts, txt))
        elif n <= SHORT_WORDS:
            n_short += 1
            for k in (3, 4, 5):
                short_c.update(set(ngrams(txt, k)))

print(f"{len(files)} transcripts | LONG judicial turns {n_long} | SHORT {n_short}\n")
rows = []
for g, cl in long_c.items():
    if cl < 8:
        continue
    cs = short_c.get(g, 0)
    lift = (cl / max(1, n_long)) / ((cs + 0.5) / max(1, n_short))
    if lift > 2.0:
        rows.append((lift, cl, cs, g))
rows.sort(reverse=True)
print(f"{'phrase':44}{'long':>6}{'short':>7}{'lift':>8}")
for lift, cl, cs, g in rows[:80]:
    print(f"{g:44}{cl:>6}{cs:>7}{lift:>8.1f}")

print("\n\n=== 6 LONGEST RIFFS FOUND (raw) ===")
for vid, ts, txt in sorted(samples, key=lambda s: -len(s[2]))[:6]:
    print(f"\n-- {vid} @{int(ts)}s  ({len(txt.split())} words)")
    print("   https://www.youtube.com/watch?v=%s&t=%ds" % (vid, max(0, int(ts) - 5)))
    print("   " + txt[:900])
