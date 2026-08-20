"""Locate competitor clips inside our own docket transcripts.

Their clips are labels. Someone already watched the stream and decided which
90 seconds were worth cutting; aligning that text back into our word-level
transcripts turns each clip into a ground-truth span in OUR corpus - a docket
id and a start/end second. That is a training set we did not have to watch
anything to build.

Method is shingle matching, not fuzzy search. Take 10-word windows from the
clip, hash them, then stream every transcript once looking only for hashes we
actually need. Two passes so nothing large is held in memory: 148 clips give a
few thousand hashes, against roughly 7M words of docket.

Captions are of a public government livestream. They are used here only to
locate moments in the original public source.
"""
from __future__ import annotations
import json, re, sys, glob, os
from collections import defaultdict

W = 10          # shingle length in words
STEP = 3        # sample every Nth position in a clip

def norm_words(text: str) -> list[str]:
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"[^A-Za-z' ]", " ", text)
    return [w for w in text.lower().split() if w]

def vtt_words(path: str) -> list[str]:
    """Rolling-window captions repeat each line 2-3x; keep first appearance."""
    out: list[str] = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:")) or "-->" in line:
            continue
        ws = norm_words(line)
        if not ws:
            continue
        # drop the overlap with what we already have
        for k in range(min(len(ws), len(out)), 0, -1):
            if out[-k:] == ws[:k]:
                ws = ws[k:]
                break
        out.extend(ws)
    return out

def shingles(ws: list[str], step: int = 1):
    for i in range(0, len(ws) - W + 1, step):
        yield i, hash(" ".join(ws[i:i + W]))

def main():
    # All channels that clip her, not just the first one found. Court Trials TV
    # publishes at a 1,024s median against Courtroom Time's 60-minute
    # compilations, so its spans are four times sharper a statement of "this is
    # the part worth watching". Skip .en-orig, which duplicates .en.
    subs = sorted(g for g in glob.glob("research/reference/*/subs/*.vtt")
                  if ".en-orig." not in g)
    trans = sorted(glob.glob("work/*/*.transcript.json"))
    print(f"clips: {len(subs)}   transcripts: {len(trans)}", flush=True)

    # pass 1 - what to look for
    want: dict[int, list[tuple[str, int]]] = defaultdict(list)
    clip_len: dict[str, int] = {}
    for p in subs:
        cid = os.path.basename(p).split(".")[0]
        ws = vtt_words(p)
        clip_len[cid] = len(ws)
        for i, h in shingles(ws, STEP):
            want[h].append((cid, i))
    print(f"distinct shingles sought: {len(want)}", flush=True)

    # pass 2 - stream the dockets
    hits: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for n, tp in enumerate(trans, 1):
        try:
            d = json.load(open(tp, encoding="utf-8"))
        except Exception:
            continue
        vid = d.get("video_id") or os.path.basename(tp).split(".")[0]
        words = d.get("words") or []
        toks, times = [], []
        for it in words:
            w = norm_words(it.get("w", ""))
            for x in w:
                toks.append(x); times.append(it.get("t", 0.0))
        for i, h in shingles(toks, 1):
            if h in want:
                for cid, _ in want[h]:
                    hits[cid].append((vid, times[i]))
        if n % 50 == 0:
            print(f"  scanned {n}/{len(trans)} dockets, clips matched so far: {len(hits)}", flush=True)

    # Common courtroom phrases ("do you understand you have the right to") match
    # all over a docket, so taking min/max of the hits reported three-hour spans
    # for two-minute clips - the counts were right and the spans meaningless.
    # Cluster instead, keep the densest run, and check it against the clip's
    # real duration from the catalog.
    cat = {}
    try:
        raw = json.load(open("research/reference/courtroomtime/catalog.json", encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("videos") or list(raw.values())
        for r in rows:
            if isinstance(r, dict) and r.get("id"):
                cat[r["id"]] = r
    except Exception:
        pass
    # The other channels were catalogued by the scan, not by a json file.
    for f in glob.glob("state/scan/*.txt"):
        if f.endswith(("_boyd_ids.txt", "channels.txt", "targets.txt", "boydsearch.txt")):
            continue
        try:
            for line in open(f, encoding="utf-8", errors="replace"):
                parts = line.rstrip().split(chr(124))
                if len(parts) < 4:
                    continue
                try:
                    dur = float(parts[0])
                except ValueError:
                    continue
                cat.setdefault(parts[2], {"id": parts[2], "dur": dur})
        except Exception:
            pass

    GAP = 90.0            # seconds of silence that ends a cluster

    os.makedirs("state", exist_ok=True)
    out, rejected = {}, 0
    for cid, hs in hits.items():
        by_vid = defaultdict(list)
        for vid, t in hs:
            by_vid[vid].append(t)
        best = None
        for vid, ts in by_vid.items():
            ts.sort()
            run = [ts[0]]
            for t in ts[1:]:
                if t - run[-1] <= GAP:
                    run.append(t)
                else:
                    if best is None or len(run) > best[2]:
                        best = (vid, run[0], len(run), run[-1])
                    run = [t]
            if best is None or len(run) > best[2]:
                best = (vid, run[0], len(run), run[-1])
        if not best:
            continue
        vid, start, n, end = best
        span = end - start
        true_dur = (cat.get(cid) or {}).get("dur") or 0
        ok = n >= 8 and span >= 15 and (not true_dur or span <= true_dur * 2.5 + 60)
        if not ok:
            rejected += 1
            continue
        out[cid] = {"video_id": vid, "start_s": round(start, 1),
                    "end_s": round(end, 1), "span_s": round(span, 1),
                    "clip_dur_s": true_dur, "anchors": n,
                    "clip_words": clip_len.get(cid, 0)}
    json.dump(out, open("state/clip_alignment.json", "w", encoding="utf-8"), indent=1)
    print(f"\nMATCHED {len(out)} / {len(subs)} clips  (rejected {rejected} as implausible)")
    print("-> state/clip_alignment.json\n")
    print(f"  {'clip':<12} {'docket':<12} {'start':>9} {'span':>8} {'clipdur':>8}  anchors")
    for cid, v in sorted(out.items(), key=lambda kv: -kv[1]["anchors"])[:15]:
        print(f"  {cid:<12} {v['video_id']:<12} {v['start_s']:9.1f} "
              f"{v['span_s']:8.1f} {v['clip_dur_s']:8}  {v['anchors']}")

if __name__ == "__main__":
    main()
