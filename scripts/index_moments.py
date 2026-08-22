"""Index one hearing into browsable moments with timestamps and descriptions.

Nathan: "if I scroll down there's clips of best moments and descriptions on the
side so I could look thru and if I wanted to can piece the short together".

So the editor needs a moment list, not just a scrubber. The transcript is sent
in timestamped windows and the model returns spans with one-line descriptions.
Timestamps are the model's, checked against the transcript before use - a span
that does not sit inside the hearing is dropped rather than shown.
"""
from __future__ import annotations
import argparse, glob, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips.llm import ClaudeCliBackend      # noqa: E402

SYSTEM = """You index a court hearing into MOMENTS a short-form editor could use.

You get the transcript in windows, each line prefixed with its start time in
seconds. Return the moments worth clipping, in order.

A moment is a self-contained exchange - a question and its answer, a riff, a
ruling. Between 8 and 45 seconds. Not the whole hearing, not single words.

For each: start and end in seconds (use the prefixes you were given), a short
label of 3-6 words, and one sentence saying what happens.

Include the dull-but-structural ones too (plea formalities, conditions) and mark
them low. Rate punch 1-5: 5 is something that would stop a scroll, 1 is
procedure. Be strict with 5s."""

SCHEMA = {"type":"object","required":["moments"],"properties":{"moments":{"type":"array","items":{
    "type":"object","required":["start","end","label","what","punch"],"properties":{
        "start":{"type":"number"},"end":{"type":"number"},"label":{"type":"string"},
        "what":{"type":"string"},"punch":{"type":"integer"}}}}}}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--model", default="claude-opus-5")
    args = ap.parse_args()
    ws = json.load(open(glob.glob(str(ROOT/"work"/args.video/"*.transcript.json"))[0],
                        encoding="utf-8"))["words"]
    seg = [(x.get("t",0.0), x.get("w","")) for x in ws
           if args.start <= x.get("t",0.0) <= args.end]
    lines, cur, t0 = [], [], None
    for t, w in seg:
        if t0 is None: t0 = t
        cur.append(w)
        if len(cur) >= 18:
            lines.append("[%d] %s" % (int(t0), re.sub(r"\s+"," "," ".join(cur))))
            cur, t0 = [], None
    if cur: lines.append("[%d] %s" % (int(t0 or args.start), " ".join(cur)))
    print("transcript lines: %d  (%.1f min)" % (len(lines), (args.end-args.start)/60))
    be = ClaudeCliBackend(model=args.model, timeout_s=1200)
    out = []
    CH = 90
    for i in range(0, len(lines), CH):
        block = "\n".join(lines[i:i+CH])
        try:
            d = be.complete(SYSTEM, "Index these moments.\n\n"+block, SCHEMA, "idx-%d"%i)
        except Exception as e:
            print("  chunk %d failed: %s" % (i, str(e)[:120])); continue
        for m in d.get("moments", []):
            if args.start <= m["start"] < m["end"] <= args.end and 5 <= m["end"]-m["start"] <= 70:
                out.append(m)
        print("  %d/%d lines -> %d moments" % (min(i+CH,len(lines)), len(lines), len(out)))
    out.sort(key=lambda m: m["start"])
    p = ROOT/"state"/("moments_%s.json" % args.video)
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    import collections
    print("\nmoments: %d" % len(out))
    print("punch  :", dict(sorted(collections.Counter(m["punch"] for m in out).items())))
    print("-> %s" % p)

if __name__ == "__main__":
    main()
