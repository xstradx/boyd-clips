"""Rate candidate moments so the ranking is fitted to Nathan, not to a rival.

Serves http://127.0.0.1:8825 . Ratings save to state/labels.json on every click
and survive restarts.

Every weight in this project is currently fitted to @courtroomtime, because
`publications` has zero rows and there is no data at all about Nathan's own
audience. Thirty labels from him outrank all of it. Skips are worth as much as
posts: a set of positives alone yields correlates, not causes.

Reads state/wentthere.json, written by scripts/find_wentthere.py.
"""

from __future__ import annotations

import html
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDS = ROOT / "state" / "wentthere.json"
LABELS = ROOT / "state" / "labels.json"
PORT = 8825
SHOW = 30


def load_labels() -> dict:
    if LABELS.exists():
        try:
            return json.loads(LABELS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def clean(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:n] + ("..." if len(s) > n else "")


def key(c: dict) -> str:
    return "%s:%d" % (c["video_id"], int(c["t"]))


def hhmmss(t: int) -> str:
    return "%d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60)


def candidates() -> list:
    rows = json.loads(CANDS.read_text(encoding="utf-8"))
    return rows[:SHOW]


CSS = """
:root{--bg:#0e1013;--card:#171a1f;--line:#262b33;--fg:#e7e9ee;--dim:#9aa3b2;
--yes:#2ea36b;--no:#c0483f;--maybe:#8a7d3f;--accent:#6ea8fe}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;background:rgba(14,16,19,.96);
border-bottom:1px solid var(--line);padding:14px 22px;z-index:5}
h1{margin:0;font-size:17px;letter-spacing:.2px}
.sub{color:var(--dim);font-size:13px;margin-top:3px}
.wrap{max-width:920px;margin:0 auto;padding:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin-bottom:14px}
.card.rated-yes{border-left:3px solid var(--yes)}
.card.rated-no{border-left:3px solid var(--no)}
.card.rated-maybe{border-left:3px solid var(--maybe)}
.top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.rank{color:var(--dim);font-variant-numeric:tabular-nums;font-size:13px}
.score{background:#1f2530;border:1px solid var(--line);border-radius:5px;
padding:1px 7px;font-size:12px;color:var(--dim)}
a.watch{color:var(--accent);text-decoration:none;font-size:13px}
a.watch:hover{text-decoration:underline}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.9px;
color:var(--dim);margin:12px 0 4px}
.setup{color:var(--dim);font-style:italic;border-left:2px solid var(--line);
padding-left:11px}
.boyd{white-space:pre-wrap}
.btns{display:flex;gap:8px;margin-top:14px}
button{background:#1f2530;color:var(--fg);border:1px solid var(--line);
border-radius:7px;padding:7px 15px;font-size:13px;cursor:pointer;
font-family:inherit}
button:hover{border-color:#3a424f}
button.on-yes{background:var(--yes);border-color:var(--yes);color:#fff}
button.on-no{background:var(--no);border-color:var(--no);color:#fff}
button.on-maybe{background:var(--maybe);border-color:var(--maybe);color:#fff}
.done{text-align:center;color:var(--dim);padding:26px;font-size:13px}
"""

JS = """
async function rate(k, v, el){
  var card = el.closest('.card');
  var cur = card.getAttribute('data-rating') || '';
  var next = (cur === v) ? '' : v;
  await fetch('/rate', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({key:k, rating:next})});
  card.setAttribute('data-rating', next);
  card.className = 'card' + (next ? ' rated-' + next : '');
  var bs = card.querySelectorAll('.btns button');
  for (var i=0;i<bs.length;i++){
    var b = bs[i];
    b.className = (b.getAttribute('data-v') === next && next) ? 'on-'+next : '';
  }
  var all = document.querySelectorAll('.card');
  var n = 0;
  for (var j=0;j<all.length;j++){ if (all[j].getAttribute('data-rating')) n++; }
  document.getElementById('count').textContent = n;
}
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path != "/rate":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        labels = load_labels()
        k, r = body.get("key"), body.get("rating")
        if r:
            labels[k] = r
        else:
            labels.pop(k, None)
        LABELS.parent.mkdir(parents=True, exist_ok=True)
        LABELS.write_text(json.dumps(labels, indent=1), encoding="utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        rows = candidates()
        labels = load_labels()
        done = sum(1 for c in rows if labels.get(key(c)))
        out = []
        out.append("<!doctype html><meta charset=utf-8><title>Rate moments</title>")
        out.append("<style>" + CSS + "</style>")
        out.append("<header><h1>Does this belong on the channel?</h1><div class=sub>")
        out.append("Top %d of 1,140 candidates &middot; <b id=count>%d</b> rated"
                   " &middot; saves on every click &middot; skips matter as much"
                   " as posts</div></header><div class=wrap>" % (len(rows), done))

        for i, c in enumerate(rows, 1):
            k = key(c)
            r = labels.get(k, "")
            t = int(c["t"])
            url = "https://youtu.be/%s?t=%d" % (c["video_id"], max(0, t - 12))
            cls = ("card rated-" + r) if r else "card"
            out.append('<div class="%s" data-rating="%s">' % (cls, r))
            out.append('<div class=top><span class=rank>#%d</span>'
                       '<span class=score>%s</span>'
                       '<a class=watch href="%s" target=_blank rel=noreferrer>'
                       '&#9654; watch at %s</a>'
                       '<span class=rank>%s</span></div>'
                       % (i, c["score"], url, hhmmss(t), c["video_id"]))
            if c.get("setup") and c.get("excuse_in_setup"):
                out.append('<div class=label>the excuse</div><div class=setup>%s</div>'
                           % html.escape(clean(c["setup"], 230)))
            out.append('<div class=label>what she says</div><div class=boyd>%s</div>'
                       % html.escape(clean(c["bench"], 700)))
            btn = ('<button data-v="%s" class="%s" onclick="rate(&quot;%s&quot;,'
                   '&quot;%s&quot;,this)">%s</button>')
            out.append('<div class=btns>')
            out.append(btn % ("yes", "on-yes" if r == "yes" else "", k, "yes", "Post this"))
            out.append(btn % ("no", "on-no" if r == "no" else "", k, "no", "Skip"))
            out.append(btn % ("maybe", "on-maybe" if r == "maybe" else "", k, "maybe", "Unsure"))
            out.append("</div></div>")

        out.append('<div class=done>Ratings land in state/labels.json. '
                   'Close the window when you are done &mdash; nothing is lost.</div>')
        out.append("</div><script>" + JS + "</script>")
        body = "".join(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    if not CANDS.exists():
        print("no candidates - run scripts/find_wentthere.py first")
        return
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/" % PORT
    print("rating %d moments -> %s" % (SHOW, url))
    print("ratings save to %s" % LABELS)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
