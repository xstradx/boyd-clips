"""Write the rating sheet as one self-contained file on the Desktop.

The served version kept vanishing because it needs a background process, and
when that process is stopped the page dies with it. This has no server: a single
HTML file that is double-clicked. Ratings persist in the browser's own storage,
so closing the tab, rebooting, or coming back tomorrow loses nothing.

Getting the answers back out is a Copy button plus a summary line on screen, so
there is nothing to configure and nothing that can be killed.

Reads state/wentthere.json (scripts/find_wentthere.py).
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDS = ROOT / "state" / "wentthere.json"
SHOW = 30


def desktop() -> Path:
    for p in (Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop"):
        if p.is_dir():
            return p
    return Path.home()


def clean(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:n] + ("..." if len(s) > n else "")


def hhmmss(t: int) -> str:
    return "%d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60)


CSS = """
:root{--bg:#0e1013;--card:#171a1f;--line:#262b33;--fg:#e7e9ee;--dim:#9aa3b2;
--yes:#2ea36b;--no:#c0483f;--maybe:#8a7d3f;--accent:#6ea8fe}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;background:#0e1013;border-bottom:1px solid var(--line);
padding:13px 22px;z-index:5}
h1{margin:0;font-size:17px}
.sub{color:var(--dim);font-size:13px;margin-top:3px}
.wrap{max-width:920px;margin:0 auto;padding:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin-bottom:14px}
.card[data-r="yes"]{border-left:3px solid var(--yes)}
.card[data-r="no"]{border-left:3px solid var(--no)}
.card[data-r="maybe"]{border-left:3px solid var(--maybe)}
.top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.rank{color:var(--dim);font-size:13px}
.score{background:#1f2530;border:1px solid var(--line);border-radius:5px;
padding:1px 7px;font-size:12px;color:var(--dim)}
a.watch{color:var(--accent);text-decoration:none;font-size:13px}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.9px;
color:var(--dim);margin:12px 0 4px}
.setup{color:var(--dim);font-style:italic;border-left:2px solid var(--line);
padding-left:11px}
.btns{display:flex;gap:8px;margin-top:14px}
button{background:#1f2530;color:var(--fg);border:1px solid var(--line);
border-radius:7px;padding:7px 15px;font-size:13px;cursor:pointer;font-family:inherit}
button:hover{border-color:#3a424f}
button.on-yes{background:var(--yes);border-color:var(--yes);color:#fff}
button.on-no{background:var(--no);border-color:var(--no);color:#fff}
button.on-maybe{background:var(--maybe);border-color:var(--maybe);color:#fff}
#bar{position:sticky;bottom:0;background:#12151a;border-top:1px solid var(--line);
padding:12px 22px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
#out{width:100%;background:#0b0d10;color:var(--fg);border:1px solid var(--line);
border-radius:7px;padding:10px;font:12px ui-monospace,Consolas,monospace;
min-height:64px;display:none}
.big{background:var(--accent);border-color:var(--accent);color:#08121f;font-weight:600}
"""

JS = """
// State lives in memory first. localStorage is a bonus, not a dependency -
// browsers commonly refuse it on a file:// page, and the first version of this
// let that exception escape, so every click silently failed and a reload wiped
// everything. Nothing here can throw out of a click handler.
var KEY='boyd_labels_v1';
var STATE=SEED;
try{ var raw=localStorage.getItem(KEY);
     if(raw){ var prev=JSON.parse(raw)||{};
              for(var kk in prev){ if(!(kk in STATE)) STATE[kk]=prev[kk]; } } }catch(e){}

function persist(){ try{ localStorage.setItem(KEY, JSON.stringify(STATE)); }catch(e){} }

function lines(){
  var yes=[],no=[],maybe=[];
  var cards=document.querySelectorAll('.card');
  for(var i=0;i<cards.length;i++){
    var c=cards[i], k=c.getAttribute('data-k'), r=c.getAttribute('data-rank');
    if(STATE[k]==='yes') yes.push(r);
    else if(STATE[k]==='no') no.push(r);
    else if(STATE[k]==='maybe') maybe.push(r);
  }
  return {yes:yes,no:no,maybe:maybe};
}

function paint(){
  var n=0, cards=document.querySelectorAll('.card');
  for(var i=0;i<cards.length;i++){
    var c=cards[i], k=c.getAttribute('data-k'), v=STATE[k]||'';
    c.setAttribute('data-r', v);
    if(v) n++;
    var bs=c.querySelectorAll('.btns button');
    for(var j=0;j<bs.length;j++){
      var b=bs[j];
      b.className=(b.getAttribute('data-v')===v && v) ? 'on-'+v : '';
    }
  }
  document.getElementById('count').textContent=n;
  var L=lines();
  document.getElementById('live').textContent =
    'POST: '+(L.yes.join(', ')||'-')+'   SKIP: '+(L.no.join(', ')||'-')+
    '   UNSURE: '+(L.maybe.join(', ')||'-');
}

function rate(k,v){
  try{
    if(STATE[k]===v){ delete STATE[k]; } else { STATE[k]=v; }
    persist(); paint();
  }catch(e){ alert('click error: '+e.message); }
}

function summary(){
  var L=lines(), NL=String.fromCharCode(10);
  return ['POST: '+(L.yes.join(', ')||'none'),
          'SKIP: '+(L.no.join(', ')||'none'),
          'UNSURE: '+(L.maybe.join(', ')||'none'),
          '',
          JSON.stringify(STATE)].join(NL);
}

function copy(){
  var o=document.getElementById('out');
  o.style.display='block'; o.value=summary(); o.focus(); o.select();
  var done=false;
  try{ done=document.execCommand('copy'); }catch(e){}
  document.getElementById('msg').textContent =
    done ? 'copied - paste it to Claude' : 'select the text above and copy it';
}

if(document.readyState!=='loading'){ paint(); }
else{ document.addEventListener('DOMContentLoaded', paint); }
"""


def main() -> None:
    rows = json.loads(CANDS.read_text(encoding="utf-8"))[:SHOW]

    # Carry forward anything already rated. He rated 24 of these on the served
    # version before it was killed; those went to state/labels.json and must not
    # be asked for again. Unrated cards sort to the top so finishing is quick,
    # while the number on each card stays its original rank.
    prior = {}
    lab = ROOT / "state" / "labels.json"
    if lab.exists():
        try:
            prior = json.loads(lab.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    for i, c in enumerate(rows, 1):
        c["_rank"] = i
        c["_done"] = prior.get("%s:%d" % (c["video_id"], int(c["t"])), "")
    rows.sort(key=lambda c: (1 if c["_done"] else 0, c["_rank"]))
    left = sum(1 for c in rows if not c["_done"])
    out = ["<!doctype html><html><head><meta charset=utf-8>",
           "<title>Rate Boyd moments</title><style>", CSS, "</style></head><body>",
           "<header><h1>Does this belong on the channel?</h1><div class=sub>",
           "<b id=count>0</b> of %d rated &middot; <b>%d left</b> &middot; "
           % (len(rows), left),
           "unrated shown first &middot; skips matter as much as posts"
           "</div></header><div class=wrap>"]

    for c in rows:
        i = c["_rank"]
        k = "%s:%d" % (c["video_id"], int(c["t"]))
        t = int(c["t"])
        url = "https://youtu.be/%s?t=%d" % (c["video_id"], max(0, t - 12))
        out.append('<div class="card" data-k="%s" data-rank="%d" data-r="">' % (k, i))
        out.append('<div class=top><span class=rank>#%d</span>'
                   '<span class=score>%s</span>'
                   '<a class=watch href="%s" target=_blank rel=noreferrer>'
                   '&#9654; watch at %s</a></div>' % (i, c["score"], url, hhmmss(t)))
        if c.get("setup") and c.get("excuse_in_setup"):
            out.append('<div class=label>the excuse</div><div class=setup>%s</div>'
                       % html.escape(clean(c["setup"], 220)))
        out.append('<div class=label>what she says</div><div>%s</div>'
                   % html.escape(clean(c["bench"], 650)))
        b = '<button data-v="%s" onclick="rate(&quot;%s&quot;,&quot;%s&quot;)">%s</button>'
        out.append('<div class=btns>')
        out.append(b % ("yes", k, "yes", "Post this"))
        out.append(b % ("no", k, "no", "Skip"))
        out.append(b % ("maybe", k, "maybe", "Unsure"))
        out.append("</div></div>")

    out.append("</div><div id=bar>")
    out.append('<button class=big onclick="copy()">Copy my answers</button>')
    out.append('<span id=msg class=sub></span>')
    out.append('<div id=live class=sub style="width:100%;font-family:'
               'ui-monospace,Consolas,monospace"></div>')
    out.append('<textarea id=out readonly></textarea></div>')
    out.append("<script>var SEED=" + json.dumps(prior) + ";</script>")
    out.append("<script>" + JS + "</script></body></html>")

    dest = desktop() / "RATE-BOYD-MOMENTS.html"
    dest.write_text("".join(out), encoding="utf-8")
    print("wrote %s (%d cards, %.0f KB)" % (dest, len(rows), dest.stat().st_size / 1024))


if __name__ == "__main__":
    main()
