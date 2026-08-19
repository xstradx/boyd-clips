"""Their descriptions are ranked countdowns: '01:08 - #3 ... 48:08 - #1 ...'.

That is an editorial ranking of WHICH CASE IS BEST, produced by the operator
who clips this exact docket, at the unit we actually deploy on (a case, not a
55-minute upload). Being within-document it holds thumbnail, title, channel
state and calendar time constant by construction -- every confound that
defeated the view-count label.
"""
import os, sys, json, re, collections
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np

TS = re.compile(r"(?m)^\s*(?:(\d+):)?(\d+):(\d+)\s*[-–—]\s*(.*)$")
RANK = re.compile(r"#\s*(\d+)")

meta = {}
for l in open("ct_meta.jsonl", encoding="utf-8"):
    l = l.strip()
    if not l:
        continue
    try:
        j = json.loads(l)
    except Exception:
        continue
    if "desc" in j and "views" in j:
        meta[j["id"].lstrip("\ufeff")] = j

nchap = 0
segs = []
for vid, j in meta.items():
    ch = []
    for m in TS.finditer(j["desc"]):
        h = int(m.group(1) or 0)
        t = h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        ch.append((t, m.group(4).strip()))
    if len(ch) < 3:
        continue
    nchap += 1
    ch.sort()
    for i, (t, lab) in enumerate(ch):
        r = RANK.search(lab)
        if not r:
            continue
        end = ch[i + 1][0] if i + 1 < len(ch) else j.get("dur", t + 600)
        segs.append(dict(vid=vid, rank=int(r.group(1)), start=t, end=end,
                         label=re.sub(r"\*+", "", lab), views=j["views"]))
print("videos with >=3 parsed chapters: %d / %d" % (nchap, len(meta)))
print("ranked segments: %d" % len(segs))
c = collections.Counter(s["rank"] for s in segs)
print("rank distribution:", dict(sorted(c.items())))
byv = collections.Counter(s["vid"] for s in segs)
print("videos contributing segments: %d (mean %.1f segs)" %
      (len(byv), np.mean(list(byv.values()))))
for r in sorted(c):
    d = [s["end"] - s["start"] for s in segs if s["rank"] == r]
    if len(d) > 3:
        print("  #%d  n=%3d  median segment %4.0fs  mean %4.0fs" %
              (r, len(d), np.median(d), np.mean(d)))
sub = "research/reference/courtroomtime/subs"
have = {f.split(".")[0] for f in os.listdir(sub) if f.endswith(".vtt")}
hs = [s for s in segs if s["vid"] in have]
print("\nSEGMENTS WITH TRANSCRIPT: %d across %d videos" %
      (len(hs), len({s['vid'] for s in hs})))
print("  rank dist:", dict(sorted(collections.Counter(s["rank"] for s in hs).items())))
json.dump(segs, open("research/fit/segments.json", "w"), indent=0)
print("\nexamples:")
for s in segs[:6]:
    print("   %s #%d %5d-%5d  %s" % (s["vid"], s["rank"], s["start"], s["end"], s["label"][:52]))
