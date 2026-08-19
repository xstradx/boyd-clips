"""Mine every cached transcript for the moments Judge Boyd goes off.

    python scripts/mine_moments.py                 # top 25 across the archive
    python scripts/mine_moments.py --top 60
    python scripts/mine_moments.py --video <id>
    python scripts/mine_moments.py --json out.json

Two passes, because novelty is only meaningful against the whole corpus:
  1. read every transcript, segment into her turns, build corpus-wide IDF
  2. re-score each turn against that IDF and rank

No model, no network, no video. Runs over 352 transcripts in seconds.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import moments                    # noqa: E402
from boydclips.transcribe import Transcript      # noqa: E402


def arg(name, default=None, cast=str):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main() -> int:
    top = arg("--top", 25, int)
    only = arg("--video")
    dump = arg("--json")

    files = sorted((ROOT / "work").glob("*/*.transcript.json"))
    if only:
        files = [f for f in files if only in f.name]
    print(f"pass 1/2 — reading {len(files)} transcripts, building corpus IDF...")

    loaded, texts, failed = [], [], 0
    for f in files:
        try:
            t = Transcript.from_json(f.read_text(encoding="utf-8"))
        except Exception:
            failed += 1
            continue
        jt = moments.judicial_turns(t)
        if jt:
            loaded.append(t)
            texts.extend(txt for _a, _b, txt in jt)
    idf = moments.build_idf(texts)
    print(f"  {len(loaded)} transcripts with judge turns, {len(texts)} riff-length "
          f"turns, {len(idf) - 1} vocabulary terms ({failed} unreadable)")

    print("pass 2/2 — scoring...")
    found = []
    for t in loaded:
        found.extend(moments.scan(t, idf))
    found.sort(key=lambda m: -m.score)
    print(f"  {len(found)} candidate moments\n")

    for i, m in enumerate(found[:top], 1):
        print(f"{i:>3}. {m.score:6.1f}  nov {m.novelty:.3f}  you {m.you_rate:5.1f}  "
              f"I {m.i_rate:5.1f}  tells {m.tell_score:4.1f}  {m.words:>4}w  "
              f"{m.video_id} @{m.clock}")
        if m.labels:
            print(f"      {', '.join(m.labels[:6])}")
        print(f"      {m.url}")
        print(textwrap.fill(m.text[:750], 94, initial_indent="      > ",
                            subsequent_indent="        "))
        print()

    if dump:
        Path(dump).write_text(json.dumps([{
            "video_id": m.video_id, "start_s": m.start_s, "end_s": m.end_s,
            "score": m.score, "novelty": m.novelty, "tells": m.tell_score,
            "you_rate": m.you_rate, "i_rate": m.i_rate,
            "labels": m.labels, "words": m.words, "url": m.url, "text": m.text,
        } for m in found], indent=2), encoding="utf-8")
        print(f"wrote {len(found)} moments to {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
