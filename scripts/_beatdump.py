import json
from pathlib import Path

d = json.load(open(Path("work/JgvW7oCQxuI/JgvW7oCQxuI.transcript.json"), encoding="utf-8"))
w = d["words"] if isinstance(d, dict) and "words" in d else d


def dump(a, b, label):
    print(f"----- {label}  [{a}-{b}]")
    parts = []
    for x in w:
        t = x.get("t")
        if t is None or not (a <= t <= b):
            continue
        parts.append("%.1f:%s" % (t, x.get("w", "")))
    print(" ".join(parts))
    print()


dump(6928, 6948, "HOOK + escalation")
dump(6948, 6962, "VERIFY / we will Google")
dump(8310, 8328, "TURN / google found nothing")
dump(8556, 8576, "BUTTON / I dont believe it")
dump(8746, 8764, "SENTENCE")
