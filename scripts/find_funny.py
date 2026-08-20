"""Find Boyd's funny moments using the courtroom's own reaction as the label.

Nathan's target is the register he called "almost funny" - her personality
coming through, riffs and asides and blunt comebacks, not necessarily a
defendant being dismantled. That is hard to specify in patterns and trivial to
observe: the captions record [laughter] when a line lands.

550 markers across 146 of 352 dockets. Clustering them finds sustained bits
rather than single polite laughs, and cross-referencing state/clip_alignment.json
separates what the rival channel already used from what nobody has touched.

An earlier miner had a "banter reject" that discarded her talking between cases.
That filter was removing exactly this material; it is deliberately absent here.
"""
from __future__ import annotations
import json, glob, os, re, collections

LAUGH = re.compile(r"\[\s*(laughter|laughs|laughing|chuckl)", re.I)
CLUSTER_GAP = 75.0     # seconds; laughs closer than this belong to one bit
LEAD_WORDS  = 90       # how much of the run-up to show


def load_alignment():
    try:
        a = json.load(open("state/clip_alignment.json", encoding="utf-8"))
    except Exception:
        return {}
    by_vid = collections.defaultdict(list)
    for cid, v in a.items():
        by_vid[v["video_id"]].append((v["start_s"], v["end_s"], cid))
    return by_vid


def main():
    taken = load_alignment()
    bits = []
    for tp in sorted(glob.glob("work/*/*.transcript.json")):
        try:
            d = json.load(open(tp, encoding="utf-8"))
        except Exception:
            continue
        vid = d.get("video_id") or os.path.basename(tp).split(".")[0]
        ws = d.get("words") or []
        marks = [(i, x.get("t", 0.0)) for i, x in enumerate(ws) if LAUGH.search(x.get("w", ""))]
        if not marks:
            continue
        run = [marks[0]]
        for m in marks[1:]:
            if m[1] - run[-1][1] <= CLUSTER_GAP:
                run.append(m)
            else:
                bits.append((vid, run)); run = [m]
        bits.append((vid, run))

    rows = []
    for vid, run in bits:
        i0, t0 = run[0]
        i1, t1 = run[-1]
        overlap = [c for (s, e, c) in taken.get(vid, []) if not (t1 < s or t0 > e)]
        rows.append({
            "video_id": vid, "start_s": t0, "end_s": t1,
            "laughs": len(run), "idx0": i0, "idx1": i1,
            "clipped_by_rival": overlap[:2],
        })
    rows.sort(key=lambda r: (-r["laughs"], r["video_id"]))

    os.makedirs("state", exist_ok=True)
    json.dump(rows, open("state/funny.json", "w", encoding="utf-8"), indent=1)

    fresh = [r for r in rows if not r["clipped_by_rival"]]
    print(f"laughter bits found:      {len(rows)}")
    print(f"  already used by rival:  {len(rows) - len(fresh)}")
    print(f"  NOT clipped by anyone:  {len(fresh)}")
    print(f"  bits with 3+ laughs:    {sum(1 for r in rows if r['laughs'] >= 3)}")
    print("\n-> state/funny.json\n")

    cache = {}
    def text(vid, a, b):
        if vid not in cache:
            p = glob.glob(f"work/{vid}/{vid}.transcript.json")
            cache[vid] = json.load(open(p[0], encoding="utf-8"))["words"] if p else []
        ws = cache[vid]
        return " ".join(x.get("w", "") for x in ws[max(0, a):b])

    print("=" * 72)
    print("TOP UNMINED BITS - the rival never used these")
    print("=" * 72)
    for r in fresh[:10]:
        t = int(r["start_s"])
        print(f"\n[{r['laughs']} laughs]  youtu.be/{r['video_id']}?t={max(0,t-25)}"
              f"   ({t//3600}:{(t%3600)//60:02d}:{t%60:02d})")
        snip = text(r["video_id"], r["idx0"] - LEAD_WORDS, r["idx1"] + 12)
        snip = re.sub(r"\s+", " ", snip).strip()
        print(f"    ...{snip[-430:]}")


if __name__ == "__main__":
    main()
