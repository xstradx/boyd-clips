"""Build segment-level dataset: chaptered case slices with editorial rank."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import corpus, features


def build(root="research/reference/courtroomtime"):
    segs = json.load(open("research/fit/segments.json"))
    sub = os.path.join(root, "subs")
    byvid = {}
    for s in segs:
        byvid.setdefault(s["vid"], []).append(s)
    out = []
    for f in sorted(os.listdir(sub)):
        if not f.endswith(".vtt"):
            continue
        vid = f.split(".")[0]
        if vid not in byvid:
            continue
        text, words = corpus.parse_vtt(os.path.join(sub, f))
        if len(words) < 500:
            continue
        for s in byvid[vid]:
            w = [x for x in words if s["start"] <= x[0] < s["end"]]
            if len(w) < 300:
                continue
            t = " ".join(x[1] for x in w)
            d = dict(s)
            d["words"] = w
            d["text"] = t
            d["nwords"] = len(w)
            d["dur"] = s["end"] - s["start"]
            out.append(d)
    return out


def feats(seg):
    return features.all_feats(seg)
