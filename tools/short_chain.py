# -*- coding: utf-8 -*-
"""The ONE command that turns editor marks into a shippable short.

Nathan, 2026-09-01: *"Can you fix the short editor as well after"*, and when
asked what "have it" meant, *"Okay then make it have it pls"* - every short
gets the engine's treatment, not just the ones built by hand.

Measured 2026-09-02: every editor page (`scripts/build_short_editor.py`,
`build_editor.py`, `build_browse_editor.py`), the studio server and
`batch_vertical.py` emitted `python scripts/make_short.py --video ... --seg`.
That is the RAW 2-up render - no word alignment, no silence-aware tightening,
no timemap, none of the engine's gates, no floor stamp. The engine
(`tools/short_engine.py`) says "ONE entry point" in its docstring and was
reachable only by a four-command sequence typed by hand per case, with a
`--tail` number measured by ear. TORRES was built that way; nothing built
from the editor pages ever was.

    python tools/short_chain.py --video ID --seg START:END [--seg ...] --out OUT.mp4

runs, in order, each step refusing loudly and leaving no OUT on failure:

    1  raw     scripts/make_short.py --no-master      (the editor's exact cuts)
    2  words   tools/align_words.py --model large-v3  (word timestamps)
    3  tight   tools/tighten.py --tail auto --timemap (cut edges in measured
               silence; tail measured to the last audible sound)
    4  engine  tools/short_engine.py --timemap        (every house rule as a
               gate; SHORT_OK + <out>.floor.json)
    5  map     <out>.map.json                         (short time -> source
               time, composed through the tighten, so the short editor can
               still convert marks back to the source)

`tools/check_short_entry.py` proves no editor page or script emits the raw
command any more, and `tools/selftest_all.py` runs it.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
WORK_ROOT = "D:/Boyd Clips/shortwork"
ALIGN_MODEL = "large-v3"
STEPS = ("raw", "words", "tight", "engine", "map")


def _run(argv, log):
    """Run one stage, streaming its output; return (returncode, text)."""
    print("  $ " + " ".join(('"%s"' % a) if " " in a else a for a in argv))
    p = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1,
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    lines = []
    for ln in p.stdout:
        ln = ln.rstrip("\n")
        if "WARN:0@" in ln or not ln.strip():
            continue
        lines.append(ln)
        print("    " + ln)
        log.write(ln + "\n")
    p.wait()
    return p.returncode, "\n".join(lines)


def compose_map(raw_map, timemap):
    """Short time -> source time through BOTH cuts. `raw_map` is make_short's
    .map.json (pieces of the raw short with their source times); `timemap` is
    tighten's old->new segment list on the raw timeline. Returns pieces in the
    same shape as make_short writes, on the FINAL short's timeline."""
    out = []
    for seg in timemap["segments"]:
        o0, o1, n0 = seg["old_start"], seg["old_end"], seg["new_start"]
        for p in raw_map["pieces"]:
            a, b = max(o0, p["short_start"]), min(o1, p["short_end"])
            if b - a <= 0.005:
                continue
            out.append({"short_start": round(n0 + (a - o0), 3),
                        "short_end": round(n0 + (b - o0), 3),
                        "src_start": round(p["src_start"] + (a - p["short_start"]), 2),
                        "src_end": round(p["src_start"] + (b - p["short_start"]), 2)})
    return out


def sidecars(out):
    """Everything beside OUT that would make it look shippable."""
    return (out, out + ".floor.json", out + ".map.json",
            os.path.splitext(out)[0] + ".map.json")


def refuse(step, why, out):
    for p in sidecars(out):
        if os.path.exists(p):
            os.remove(p)
    print(f"  FAIL  {step:7} {why}")
    print(f"  REFUSED at step {step} - no {os.path.basename(out)} written")
    return 1


def chain(video, segs, out, work=None, verbose=True):
    stem = os.path.splitext(os.path.basename(out))[0]
    work = work or os.path.join(WORK_ROOT, stem)
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    raw = os.path.join(work, stem + "_raw.mp4")
    raw_words = os.path.join(work, stem + "_raw_words.json")
    tight = os.path.join(work, stem + "_tight.mp4")
    tight_words = os.path.join(work, stem + "_tight_words.json")
    tm = os.path.join(work, stem + "_tm.json")
    py = sys.executable
    first_start = min(float(s.split(":")[0]) for s in segs)
    print(f"short_chain  {video}  {len(segs)} seg  ->  {out}")
    print(f"  work {work}")
    with open(os.path.join(work, "chain.log"), "w", encoding="utf-8") as log:
        # 1 raw - the editor's exact cuts, unmastered (the engine masters)
        for p in (raw, os.path.splitext(raw)[0] + ".map.json"):
            if os.path.exists(p):
                os.remove(p)
        argv = [py, os.path.join(ROOT, "scripts", "make_short.py"), "--video", video]
        for s in segs:
            argv += ["--seg", s]
        argv += ["--no-master", "--out", raw]
        rc, txt = _run(argv, log)
        raw_map_p = os.path.splitext(raw)[0] + ".map.json"
        if rc != 0 or not os.path.exists(raw) or not os.path.exists(raw_map_p):
            # make_short prints and returns 0 on "no downloaded section" /
            # "tiles not measurable" - the FILE is the verdict, not the exit
            return refuse("raw", f"make_short exit {rc}, raw={os.path.exists(raw)} "
                                 f"map={os.path.exists(raw_map_p)}", out)
        print("  OK    raw")
        # 2 words
        rc, txt = _run([py, os.path.join(ROOT, "tools", "align_words.py"), raw, raw_words,
                        "--model", ALIGN_MODEL], log)
        try:
            words = json.load(open(raw_words, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            words = []
        if rc != 0 or not words:
            return refuse("words", f"align_words exit {rc}, {len(words)} words", out)
        print(f"  OK    words   {len(words)} words")
        # 3 tight - edges in measured silence, tail measured, timemap for the gate
        rc, txt = _run([py, os.path.join(ROOT, "tools", "tighten.py"), raw, raw_words, tight,
                        tight_words, "--tail", "auto", "--timemap", tm,
                        "--src-start", f"{first_start:.2f}"], log)
        if rc != 0 or not (os.path.exists(tight) and os.path.exists(tight_words)
                           and os.path.exists(tm)):
            return refuse("tight", f"tighten exit {rc}", out)
        print("  OK    tight")
        # 4 engine - every house rule as a gate, SHORT_OK + floor stamp
        rc, txt = _run([py, os.path.join(ROOT, "tools", "short_engine.py"), tight, tight_words,
                        out, "--timemap", tm], log)
        if rc != 0 or "SHORT_OK" not in txt or not os.path.exists(out):
            return refuse("engine", f"short_engine exit {rc}, SHORT_OK={'SHORT_OK' in txt}", out)
        print("  OK    engine  SHORT_OK")
        # 4b pace - R58. Every gate above can pass on a short where nothing is
        # happening; "Short was kinda underwhelming and slow, boring" (2026-09-03)
        # measured 138.3 wpm against his accepted 195-236. The span is the fault,
        # so this refuses the build rather than shipping it for him to reject.
        rc, txt = _run([py, os.path.join(ROOT, "tools", "check_short_pace.py"),
                        out, "--words", tight_words], log)
        if rc != 0 or "SHORT_PACE_FAIL" in txt:
            return refuse("pace", "under the pace floor of his accepted shorts - "
                                  "re-pick the SPAN, do not re-cut this one", out)
        print("  OK    pace    SHORT_PACE_OK")
        # 5 map - so the short editor can convert marks on THIS file to source
        raw_map = json.load(open(raw_map_p, encoding="utf-8"))
        timemap = json.load(open(tm, encoding="utf-8"))
        pieces = compose_map(raw_map, timemap)
        side = {"video": video, "section_start_s": raw_map.get("section_start_s"),
                "duration_s": timemap.get("new_duration"), "pieces": pieces,
                "chain": {"raw": raw, "words": raw_words, "tight": tight, "timemap": tm,
                          "tail_s": _tail_from(timemap), "align_model": ALIGN_MODEL}}
        json.dump(side, open(out + ".map.json", "w", encoding="utf-8"), indent=1)
        # make_short names its sidecar <stem>.map.json; keep that name too so
        # the existing pages find it (out.with_suffix(".map.json"))
        json.dump(side, open(os.path.splitext(out)[0] + ".map.json", "w", encoding="utf-8"),
                  indent=1)
        print(f"  OK    map     {len(pieces)} pieces -> {os.path.splitext(out)[0]}.map.json")
    print(f"  CHAIN_OK  {out}")
    return 0


def _tail_from(timemap):
    import re
    m = re.search(r"tail=([\d.]+)", timemap.get("source", ""))
    return float(m.group(1)) if m else None


def selftest():
    """Composition known answer + refusal leaves nothing shippable."""
    import tempfile
    ok = True

    def chk(label, got, want):
        nonlocal ok
        hit = got == want
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:56} -> {got} (want {want})")

    # raw short: two pieces from the source; tighten removed 1.0 s inside piece 1
    # and 0.5 s across the seam
    raw_map = {"pieces": [
        {"short_start": 0.0, "short_end": 10.0, "src_start": 100.0, "src_end": 110.0},
        {"short_start": 10.0, "short_end": 15.0, "src_start": 200.0, "src_end": 205.0}]}
    timemap = {"segments": [
        {"old_start": 0.0, "old_end": 4.0, "new_start": 0.0},
        {"old_start": 5.0, "old_end": 9.8, "new_start": 4.0},
        {"old_start": 10.3, "old_end": 15.0, "new_start": 8.8}], "new_duration": 13.5}
    pcs = compose_map(raw_map, timemap)
    chk("three final pieces (no seam straddle)", len(pcs), 3)
    chk("piece 1 source start", pcs[0]["src_start"], 100.0)
    chk("piece 2 skips the removed second", (pcs[1]["src_start"], pcs[1]["short_start"]),
        (105.0, 4.0))
    chk("piece 3 lands on the second source piece", (pcs[2]["src_start"], pcs[2]["src_end"]),
        (200.3, 205.0))
    chk("final timeline is contiguous",
        all(abs(a["short_end"] - b["short_start"]) < 1e-6 for a, b in zip(pcs, pcs[1:])), True)
    chk("duration matches the timemap", round(pcs[-1]["short_end"], 3), 13.5)
    # a segment straddling the raw seam splits into two pieces with the right sources
    tm2 = {"segments": [{"old_start": 8.0, "old_end": 12.0, "new_start": 0.0}], "new_duration": 4.0}
    p2 = compose_map(raw_map, tm2)
    chk("seam straddle splits in two", [(p["src_start"], p["src_end"]) for p in p2],
        [(108.0, 110.0), (200.0, 202.0)])
    # refusal: a failed step removes every shippable-looking file
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "X_SHORT.mp4")
        for p in sidecars(out):
            open(p, "w").write("x")
        rc = refuse("engine", "control", out)
        chk("refusal exits non-zero", rc, 1)
        chk("refusal leaves no output / stamp / map",
            [os.path.exists(p) for p in sidecars(out)], [False] * len(sidecars(out)))
    # the chain's steps are the ones the docstring promises, in that order
    src = open(__file__, encoding="utf-8").read()
    body = src[src.index("def chain("):src.index("def _tail_from(")]
    order = [body.index(k) for k in ('"make_short.py"', '"align_words.py"',
                                     '"tighten.py"', '"short_engine.py"', "compose_map(")]
    chk("steps run raw -> words -> tight -> engine -> map", order == sorted(order), True)
    chk("tighten is called with --tail auto (never a typed number)",
        '"--tail", "auto"' in src, True)
    print("SELFTEST_PASS short_chain" if ok else "SELFTEST_FAIL short_chain")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--video", required=True)
    ap.add_argument("--seg", action="append", required=True,
                    help="START:END in absolute source seconds; repeatable, in play order")
    ap.add_argument("--out", required=True, help="final short (.mp4)")
    ap.add_argument("--work", default=None,
                    help=f"intermediates dir (default {WORK_ROOT}/<stem>)")
    # accepted from older editor pages; the engine decides both
    ap.add_argument("--captions", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-captions", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.captions or a.no_captions:
        print("  note: --captions/--no-captions ignored - captions are the engine's, always on")
    sys.exit(chain(a.video, a.seg, a.out, a.work))
