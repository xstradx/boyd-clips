"""Calibrate the evidentiary-hearing detector against cases with KNOWN visuals.

Ground truth established by rendering them or by pulling frames today:

  SHOOTABLE   Thompson  JgvW7oCQxuI:6698  approved short, tight 2-up
  SHOOTABLE   Rodriguez mvGmUbuS0sU:1358  approved short, faces legible
  SHOOTABLE   McCaskill RzjGikNbHMA:8485  camera OK, podium exchange
  SHOOTABLE   Kilpatrick pgHDPyKdcQs:316  camera OK, podium exchange
  UNUSABLE    Miosek    cj9gKdNcJdk:5277  bench trial -> wide room shot
  UNUSABLE    Measeck   9R1jJ_QX1Wg:8262  same trial, other sitting
  UNUSABLE    Blackburn 4zkUTUavW4I:116   family testimony -> 3-4 tile grid
  UNUSABLE    Pena      oL6lV6gCyOc:3047  contested PSI -> camera off entirely

If the detector cannot separate these two groups it is not worth wiring in.
"""
import sys, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from boydclips import hearingtype
from boydclips.transcribe import Transcript

TRUTH = [
    ("SHOOTABLE", "Thompson  ", "JgvW7oCQxuI", 6698, 6958),
    ("SHOOTABLE", "Rodriguez ", "mvGmUbuS0sU", 1358, 2012),
    ("SHOOTABLE", "McCaskill ", "RzjGikNbHMA", 8485, 8917),
    ("SHOOTABLE", "Kilpatrick", "pgHDPyKdcQs", 316, 676),
    ("UNUSABLE ", "Miosek    ", "cj9gKdNcJdk", 5277, 8043),
    ("UNUSABLE ", "Measeck   ", "9R1jJ_QX1Wg", 8262, 11982),
    ("UNUSABLE ", "Blackburn ", "4zkUTUavW4I", 116, 2145),
    ("UNUSABLE ", "Pena      ", "oL6lV6gCyOc", 3047, 6115),
]

c = sqlite3.connect(ROOT / "state" / "pipeline.db"); c.row_factory = sqlite3.Row
print(f"{'truth':11}{'case':12}{'min':>7}  markers                  verdict")
ok = 0
for truth, name, vid, a, b in TRUTH:
    # exact span from the DB where we have it
    r = c.execute("SELECT start_s, end_s FROM cases WHERE video_id=? AND "
                  "abs(start_s-?)<2", (vid, a)).fetchone()
    if r:
        a, b = r["start_s"], r["end_s"]
    cache = ROOT / "work" / vid / f"{vid}.transcript.json"
    if not cache.exists():
        print(f"{truth:11}{name:12}{'':>7}  no cached transcript")
        continue
    t = Transcript.from_json(cache.read_text(encoding="utf-8"))
    text = t.text_between(a, b)
    v = hearingtype.classify(text, (b - a) / 60.0)
    got = "CONTESTED" if v.contested else "clean"
    hit = (v.contested and truth.strip() == "UNUSABLE") or (
        not v.contested and truth.strip() == "SHOOTABLE")
    ok += hit
    key = {k: v.hits.get(k, 0) for k in ("pass_witness", "objection", "exhibit")}
    print(f"{truth:11}{name:12}{v.minutes:>7.1f}  pass={key['pass_witness']:<3}"
          f"obj={key['objection']:<4}exh={key['exhibit']:<4}{got:10} "
          f"{'OK' if hit else '<<< MISCLASSIFIED'}")
    if v.contested:
        print(f"{'':31}{v.reason}")
print(f"\n{ok}/{len(TRUTH)} classified correctly")
