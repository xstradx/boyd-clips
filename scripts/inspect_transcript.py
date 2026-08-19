"""Look at the actual transcript structure before building attribution on it."""
import json, sys, re, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from boydclips.transcribe import Transcript

f = sorted((ROOT/"work").glob("*/*.transcript.json"))[0]
t = Transcript.from_json(f.read_text(encoding="utf-8"))
print("file:", f.name, "| words:", len(t.words), "| source:", t.source)
print("\nfirst 40 word tokens (repr):")
print([w.w for w in t.words[:40]])
print("\ntokens containing '>' anywhere:",
      sum(1 for w in t.words if ">" in w.w))
print("distinct such tokens:", collections.Counter(
    w.w for w in t.words if ">" in w.w).most_common(8))
# how often do turns occur, and how long are they
idx = [i for i, w in enumerate(t.words) if ">>" in w.w]
print(f"\nturn markers: {len(idx)}  over {t.duration_s/60:.0f} min "
      f"= {len(idx)/(t.duration_s/60):.1f}/min")
if len(idx) > 3:
    lens = [idx[i+1]-idx[i] for i in range(len(idx)-1)]
    lens.sort()
    print("turn length in words: median", lens[len(lens)//2], "p90", lens[int(len(lens)*.9)])
    print("\nfirst 6 turns:")
    for a, b in list(zip(idx, idx[1:]))[:6]:
        print("  [%7.1fs] %s" % (t.words[a].t, " ".join(w.w for w in t.words[a:b])[:150]))
# do ANY transcripts carry speaker names?
print("\nscanning 40 transcripts for speaker-name markers ('JUDGE', 'THE COURT'):")
hits = 0
for g in sorted((ROOT/"work").glob("*/*.transcript.json"))[:40]:
    txt = g.read_text(encoding="utf-8")[:200000]
    if re.search(r"THE COURT|JUDGE BOYD:|MR\.|MS\.", txt):
        hits += 1
print(f"  {hits}/40 contain any such marker")
