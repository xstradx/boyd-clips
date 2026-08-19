"""Pick the best of four thumbnails, round after round, and record why.

Five thumbnail defects shipped in a row because one variant was rendered,
eyeballed, corrected on one axis, and shipped again. A single image gives no
signal - there is nothing to compare it against, so "wrong" only ever arrives
from the user afterwards. Four side by side turns it into a preference, and a
preference is data.

Every pick appends to state/thumb_prefs.json: which variant won, the axis
values behind it, and any note typed in the box. Over a few rounds that file
answers the questions currently being guessed at - is 0.34 or 0.38 the better
subject width, does 0.72 or 0.78 read better, is punchy too much.

The notes box exists for the case the buttons cannot express: all four are
wrong. That is a finding too, and it is the one a picker without a text field
throws away.

    python scripts/thumb_picker.py          # serves http://127.0.0.1:8823
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ROOT / "out" / "thumbvariants"
PREFS = ROOT / "state" / "thumb_prefs.json"
PORT = 8823

# Cases queued for review. Anything already rendered under out/thumbvariants
# is picked up automatically, so this is just the seed order.
QUEUE: list[str] = []


def load_prefs() -> dict:
    if PREFS.is_file():
        try:
            return json.loads(PREFS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"picks": [], "notes": []}


def save_prefs(data: dict) -> None:
    PREFS.parent.mkdir(parents=True, exist_ok=True)
    PREFS.write_text(json.dumps(data, indent=1), encoding="utf-8")


def pending_cases() -> list[str]:
    done = {p["case_key"] for p in load_prefs()["picks"]}
    out = []
    if VARIANTS.is_dir():
        for d in sorted(VARIANTS.iterdir()):
            if not d.is_dir() or not (d / "manifest.json").is_file():
                continue
            key = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["case_key"]
            if key not in done:
                out.append(key)
    return out


def summarise() -> str:
    """What the picks say so far. Plain counts - no inference from n=2."""
    prefs = load_prefs()
    if not prefs["picks"]:
        return "No picks yet."
    from collections import Counter
    w = Counter(str(p["variant"].get("subject_w")) for p in prefs["picks"])
    cx = Counter(str(p["variant"].get("subject_cx")) for p in prefs["picks"])
    g = Counter(str(p["variant"].get("grade")) for p in prefs["picks"])
    n = len(prefs["picks"])
    return (f"{n} pick(s) &middot; width {dict(w)} &middot; "
            f"centre {dict(cx)} &middot; grade {dict(g)}")


PAGE = """<!doctype html><meta charset=utf-8><title>Thumbnail picker</title><style>
*{{box-sizing:border-box}} body{{font:15px/1.45 system-ui;background:#0e0e0e;color:#eee;margin:0;padding:24px}}
h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#888;font-size:13px;margin-bottom:18px}}
.wrap{{display:flex;gap:22px;align-items:flex-start;max-width:1500px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex:1}}
.card{{background:#1a1a1a;border:2px solid #2e2e2e;border-radius:10px;overflow:hidden;cursor:pointer;transition:.12s}}
.card:hover{{border-color:#c00;transform:translateY(-2px)}}
.card img{{width:100%;display:block}}
.meta{{padding:7px 10px;font-size:12px;color:#999;display:flex;justify-content:space-between}}
.side{{width:290px;flex:none;background:#171717;border:1px solid #2e2e2e;border-radius:10px;padding:16px}}
textarea{{width:100%;height:130px;background:#0e0e0e;color:#eee;border:1px solid #333;border-radius:6px;padding:9px;font:13px system-ui;resize:vertical}}
button{{width:100%;margin-top:9px;padding:10px;border:0;border-radius:6px;background:#c00;color:#fff;font-weight:600;font-size:14px;cursor:pointer}}
button.alt{{background:#333}}
.stat{{margin-top:14px;padding-top:12px;border-top:1px solid #2e2e2e;color:#888;font-size:12px}}
.done{{text-align:center;padding:70px 20px;color:#888}}
</style>
<h1>Which one works?</h1>
<div class=sub>{sub}</div>
<div class=wrap>
  <div class=grid>{cards}</div>
  <div class=side>
    <div style="font-weight:600;margin-bottom:7px">Something wrong with all of them?</div>
    <form method=POST action="/note">
      <input type=hidden name=case value="{case}">
      <textarea name=note placeholder="e.g. text is still too close to his face, or the judge is too small, or all four look washed out"></textarea>
      <button class=alt type=submit>Send note &amp; skip</button>
    </form>
    <div class=stat>{stats}</div>
  </div>
</div>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet
        pass

    def _html(self, body: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):                                     # noqa: N802
        u = urlparse(self.path)
        if u.path.startswith("/img/"):
            p = VARIANTS / u.path[len("/img/"):]
            if p.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                self.wfile.write(p.read_bytes())
                return
            self.send_error(404)
            return

        if u.path == "/pick":
            q = parse_qs(u.query)
            case, vfile = q["case"][0], q["v"][0]
            d = VARIANTS / case.replace(":", "_")
            man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            variant = next((v for v in man["variants"] if v["file"] == vfile), {})
            prefs = load_prefs()
            prefs["picks"].append({"case_key": case, "variant": variant})
            save_prefs(prefs)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        cases = pending_cases()
        if not cases:
            self._html("<style>body{font:16px system-ui;background:#0e0e0e;"
                       "color:#eee;padding:60px;text-align:center}</style>"
                       f"<h2>All caught up.</h2><p>{summarise()}</p>")
            return

        case = cases[0]
        d = VARIANTS / case.replace(":", "_")
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        cards = "".join(
            f'<a class=card href="/pick?case={case}&v={v["file"]}">'
            f'<img src="/img/{case.replace(":", "_")}/{v["file"]}">'
            f'<div class=meta><span>w {v["subject_w"]} &middot; cx {v["subject_cx"]}</span>'
            f'<span>{v["grade"]}</span></div></a>'
            for v in man["variants"])
        self._html(PAGE.format(
            cards=cards, case=case, stats=summarise(),
            sub=f'{case} &mdash; &ldquo;{man["white"]} <b style="color:#ffd24a">'
                f'{man["yellow"]}</b>&rdquo; &middot; {len(cases)} case(s) queued'))

    def do_POST(self):                                    # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(n).decode("utf-8"))
        prefs = load_prefs()
        prefs["notes"].append({"case_key": form.get("case", [""])[0],
                               "note": form.get("note", [""])[0]})
        # A note means none of the four were right, so the case is retired from
        # the queue rather than shown again unchanged.
        prefs["picks"].append({"case_key": form.get("case", [""])[0],
                               "variant": {}, "rejected_all": True})
        save_prefs(prefs)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def main() -> int:
    if not VARIANTS.is_dir() or not any(VARIANTS.iterdir()):
        print("No variants yet. Generate some first:")
        print("  python scripts/thumb_variants.py <case_key>")
        return 1
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"picker on {url}   (ctrl-c to stop)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped. preferences ->", PREFS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
