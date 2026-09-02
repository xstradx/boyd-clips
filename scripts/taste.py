"""taste.py - collect Nathan's eye as ground truth, then test the model against it.

Nathan offered this, 2026-08-29: *"if you need any info from me like if you need
me to pick what pictures the best from a set of 4 i could do that"*. It is the
most valuable thing available, and here is precisely why.

Views are a CONTAMINATED signal for thumbnail craft. They carry the topic, the
title, the upload timing and the channel's dormancy. Measured consequence: the
rubric eye scored rho=-0.20 against views on the six thumbnails it had not seen,
which says almost nothing about the eye and a lot about the noise.

A forced choice between two thumbnails OF THE SAME VIDEO cancels every one of
those confounds. Same topic, same title, same day - the only variable left is
the craft. That is clean ground truth, and no scraped corpus can produce it.

  python scripts/taste.py serve            # a local page; click the better one
  python scripts/taste.py agree            # does the eye agree with his picks?
  python scripts/taste.py status           # how many picks collected so far

Picks land in research/reference/taste_picks.jsonl, one JSON object per line,
append-only so a session can never overwrite earlier judgements.
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REF = ROOT / "research" / "reference"
PICKS = REF / "taste_picks.jsonl"
sys.path.insert(0, str(SCRIPTS))


def pool():
    """Every thumbnail we could ask about, newest sources first."""
    seen, out = set(), []
    for d in (REF / "ttt_own", ROOT / "work" / "repair",
              REF / "courtroomtime" / "thumbs", REF / "competitor" / "thumbs"):
        if not d.exists():
            continue
        for f in sorted(d.glob("*.jpg")) + sorted(d.glob("*.png")):
            if f.name in seen:
                continue
            seen.add(f.name)
            out.append(f)
    return out


def make_set(items, n=4, rng=None):
    rng = rng or random
    return rng.sample(items, min(n, len(items)))


PAGE = """<!doctype html><meta charset=utf-8>
<title>which one is better?</title>
<style>
 body{background:#111;color:#eee;font:15px system-ui;margin:0;padding:18px}
 h1{font-size:17px;font-weight:600;margin:0 0 4px}
 p.sub{color:#999;margin:0 0 16px}
 .grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;max-width:1500px}
 figure{margin:0;cursor:pointer;border:3px solid #222;border-radius:10px;overflow:hidden;
        transition:border-color .12s,transform .12s;background:#000}
 figure:hover{border-color:#4ea1ff;transform:translateY(-2px)}
 img{width:100%%;display:block}
 figcaption{padding:7px 10px;color:#aaa;font-size:12px;font-family:ui-monospace,monospace}
 .bar{margin:16px 0 0;color:#888;font-size:13px}
 button{background:#222;color:#ddd;border:1px solid #333;border-radius:7px;
        padding:7px 13px;cursor:pointer;font:13px system-ui;margin-right:8px}
 button:hover{background:#2b2b2b}
</style>
<h1>Which of these is the better thumbnail?</h1>
<p class=sub>Judge the craft, not the case. Click one. %(done)d picks recorded so far.</p>
<div class=grid>%(cards)s</div>
<div class=bar>
  <button onclick="pick('__skip__')">skip / too close to call</button>
  <button onclick="pick('__all_bad__')">all four are bad</button>
</div>
<script>
function pick(name){
  fetch('/pick',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({choice:name,candidates:%(cands)s})})
   .then(()=>location.reload());
}
</script>"""

CARD = """<figure onclick="pick('%(name)s')">
  <img src="data:image/jpeg;base64,%(b64)s">
  <figcaption>%(label)s</figcaption></figure>"""


class Handler(BaseHTTPRequestHandler):
    items = []

    def log_message(self, *a):
        pass

    def _count(self):
        if not PICKS.exists():
            return 0
        return sum(1 for line in PICKS.read_text(encoding="utf-8").splitlines()
                   if line.strip())

    def do_GET(self):
        if urlparse(self.path).path != "/":
            self.send_error(404)
            return
        chosen = make_set(self.items, 4)
        cards = "".join(CARD % dict(
            name=f.name,
            label=f.name,
            b64=base64.b64encode(f.read_bytes()).decode("ascii"))
            for f in chosen)
        body = (PAGE % dict(cards=cards, done=self._count(),
                            cands=json.dumps([f.name for f in chosen]))
                ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        rec = dict(choice=data.get("choice"), candidates=data.get("candidates"),
                   ts=__import__("time").strftime("%Y-%m-%dT%H:%M:%S"))
        PICKS.parent.mkdir(parents=True, exist_ok=True)
        with PICKS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print("  recorded: %s  (from %d)" % (rec["choice"], len(rec["candidates"] or [])))
        self.send_response(204)
        self.end_headers()


def serve(port):
    items = pool()
    if len(items) < 2:
        print("not enough thumbnails to compare (found %d)" % len(items))
        return 1
    Handler.items = items
    print("%d thumbnails in the pool" % len(items))
    print("open this and start clicking:  http://127.0.0.1:%d/" % port)
    print("picks append to %s" % PICKS)
    print("ctrl-c when you have had enough - every pick is already saved")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def load_picks():
    if not PICKS.exists():
        return []
    out = []
    for line in PICKS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return [p for p in out
            if p.get("choice") not in (None, "__skip__", "__all_bad__")]


def status():
    all_lines = 0
    if PICKS.exists():
        all_lines = len([l for l in PICKS.read_text(encoding="utf-8").splitlines()
                         if l.strip()])
    usable = load_picks()
    print("%d rows recorded, %d usable (skips and all-bad excluded)"
          % (all_lines, len(usable)))
    if len(usable) < 12:
        print("NOT ENOUGH YET - agreement on fewer than ~12 forced choices is noise.")
        return 1
    print("PICKS_READY")
    return 0


def agree(model):
    """Does the eye pick what Nathan picks? This is the honest validation the
    view-correlation could never be, because a forced choice controls for topic,
    title and timing."""
    import eye as E
    picks = load_picks()
    if not picks:
        print("no usable picks yet - run: python scripts/taste.py serve")
        return 1

    by_name = {f.name: f for f in pool()}
    hits = total = 0
    cache = {}
    for p in picks:
        cands = [c for c in (p["candidates"] or []) if c in by_name]
        if len(cands) < 2 or p["choice"] not in cands:
            continue
        scores = {}
        for c in cands:
            if c not in cache:
                g = E.grade(by_name[c], model)
                cache[c] = g.get("overall") if g.get("ok") else None
            scores[c] = cache[c]
        if any(v is None for v in scores.values()):
            continue
        top = max(scores, key=scores.get)
        total += 1
        hits += (top == p["choice"])
        print("  %-28s nathan=%-28s eye=%-28s %s"
              % ("set of %d" % len(cands), p["choice"], top,
                 "MATCH" if top == p["choice"] else "miss"))

    if not total:
        print("no comparable sets")
        return 1
    chance = sum(1.0 / len([c for c in (p["candidates"] or []) if c in by_name])
                 for p in picks if len([c for c in (p["candidates"] or [])
                                        if c in by_name]) >= 2) / total
    rate = hits / total
    print("\nagreement %d/%d = %.0f%%   (random choice would be %.0f%%)"
          % (hits, total, rate * 100, chance * 100))
    if total < 12:
        print("n=%d is too small to conclude anything. Collect more." % total)
        return 1
    if rate <= chance:
        print("THE EYE DOES NOT MATCH HIS TASTE - the rubric needs work, "
              "and saying so is the point of this check.")
        return 1
    print("EYE_AGREES")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve"); sv.add_argument("--port", type=int, default=8731)
    sub.add_parser("status")
    ag = sub.add_parser("agree")
    ag.add_argument("--model", default="qwen3.6-35b-abliterated-vision")
    a = ap.parse_args()
    if a.cmd == "serve":
        return serve(a.port)
    if a.cmd == "status":
        return status()
    return agree(a.model)


if __name__ == "__main__":
    raise SystemExit(main())
