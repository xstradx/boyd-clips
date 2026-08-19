"""The confound nobody controlled: calendar time."""
import os, sys, json, datetime as dt
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import numpy as np, stats_util as S

meta = {}
for l in open("ct_meta.jsonl", encoding="utf-8"):
    l = l.strip()
    if not l:
        continue
    try:
        j = json.loads(l)
    except Exception:
        continue
    if "views" in j and "upload_date" in j:
        meta[j["id"].lstrip("\ufeff")] = j
print("videos with upload_date + views:", len(meta))
rows = [(k, v["views"], v["dur"], v["upload_date"]) for k, v in meta.items()
        if v.get("views", 0) > 0]
band = [r for r in rows if 2700 <= r[2] <= 4200]
print("length-matched band:", len(band))

def days(s):
    d = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return (dt.date(2026, 8, 18) - d).days

age = np.array([days(r[3]) for r in band], float)
lv = np.array([np.log10(r[1]) for r in band])
print("age range: %.0f..%.0f days" % (age.min(), age.max()))
print("SPEARMAN(age_days, log10 views) = %+.3f   n=%d" % (S.spearman(age, lv), len(band)))
print("SPEARMAN(dur,      log10 views) = %+.3f" % S.spearman([r[2] for r in band], lv))

# views by age quartile
o = np.argsort(age)
for qi in range(4):
    sl = o[qi * len(o) // 4:(qi + 1) * len(o) // 4]
    print("  age Q%d  %4.0f-%4.0f days  median views %8d  n=%d" %
          (qi + 1, age[sl].min(), age[sl].max(),
           int(np.median([band[i][1] for i in sl])), len(sl)))

# Where do OUR 72 transcript docs sit?
import corpus
docs = corpus.load()
b2 = [d for d in docs if 2700 <= d["dur"] <= 4200]
b2.sort(key=lambda d: -d["views"])
k = len(b2) // 3
for lab, g in (("HI", b2[:k]), ("LO", b2[-k:])):
    a = [days(meta[d["id"]]["upload_date"]) for d in g if d["id"] in meta]
    if a:
        print("  transcript %s: n=%d with dates, median age %.0f days" %
              (lab, len(a), np.median(a)))
