"""Generate a self-contained editing page for one hearing.

Nathan asked three times where he could edit a short, and the honest answer was
nowhere - he had been given a command line with --seg flags. This is the page:
scrub the long-form, mark in and out, reorder or delete segments, and copy a
ready-to-run command.

No server. The page sits beside the mp4 in READY-TO-REVIEW and loads it with a
relative src, so it survives being closed, reopened and rebooted - unlike the
served pages, which kept being killed.

Player time is relative to the long-form file; short_chain.py wants absolute
source seconds, so the page adds the hearing's start offset for you.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Edit __NAME__</title>
<style>
:root{--bg:#0e1013;--card:#171a1f;--line:#262b33;--fg:#e7e9ee;--dim:#9aa3b2;--go:#2ea36b;--accent:#6ea8fe;--warn:#c0483f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:16px;margin:0 0 10px}
video{width:100%;max-height:56vh;background:#000;border-radius:10px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}
button{background:#1f2530;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:8px 14px;font-size:14px;cursor:pointer;font-family:inherit}
button:hover{border-color:#3a424f}
.pri{background:var(--go);border-color:var(--go);color:#fff;font-weight:600}
.acc{background:var(--accent);border-color:var(--accent);color:#08121f;font-weight:600}
.dim{color:var(--dim);font-size:13px}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--dim);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.7px}
td.n{font-variant-numeric:tabular-nums}
.mini{padding:3px 9px;font-size:13px}
#cmd{width:100%;background:#0b0d10;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:10px;font:12px ui-monospace,Consolas,monospace;min-height:92px;margin-top:8px}
kbd{background:#1f2530;border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-size:12px}
.tot{font-weight:600}
.over{color:var(--warn)}
</style></head><body><div class="wrap">
<h1>__NAME__ &mdash; mark the bits you want</h1>
<video id="v" src="__FILE__" controls preload="metadata"></video>
<div class="row">
  <button class="pri" onclick="markIn()">Mark IN <kbd>i</kbd></button>
  <button class="pri" onclick="markOut()">Mark OUT <kbd>o</kbd></button>
  <button onclick="nudge(-5)">&minus;5s</button>
  <button onclick="nudge(-1)">&minus;1s</button>
  <button onclick="nudge(1)">+1s</button>
  <button onclick="nudge(5)">+5s</button>
  <span class="dim" id="now">0:00.0</span>
  <span class="dim">pending in: <b id="pin">-</b></span>
</div>
<table id="tbl"><thead><tr><th>#</th><th>start</th><th>end</th><th>length</th><th>source secs</th><th></th></tr></thead><tbody id="rows"></tbody></table>
<div class="row"><span class="tot" id="total">nothing marked</span></div>
<div class="row">
  <button class="acc" onclick="copyCmd()">Copy the build command</button>
  <button onclick="clearAll()">Clear all</button>
  <span class="dim" id="msg"></span>
</div>
<textarea id="cmd" readonly></textarea>
<p class="dim">Segments play in the order listed &mdash; move one to the top to make it the hook.
Reordering is fine on shorts, never on the long-form. Paste the command into a terminal in
<code>__ROOT__</code>, or send it to Claude.</p>
</div>
<script>
var BASE = __BASE__;            // long-form t=0 sits here in the source
var VIDEO = "__VID__";
var OUT = "__OUTNAME__";
var segs = [];
var pendingIn = null;
var v = document.getElementById("v");

function fmt(t){ var m=Math.floor(t/60), s=(t%60); return m+":"+(s<10?"0":"")+s.toFixed(1); }
function tick(){ document.getElementById("now").textContent = fmt(v.currentTime||0); }
v.addEventListener("timeupdate", tick);

function markIn(){ pendingIn = v.currentTime; document.getElementById("pin").textContent = fmt(pendingIn); }
function markOut(){
  if (pendingIn === null){ flash("mark IN first"); return; }
  var a = pendingIn, b = v.currentTime;
  if (b <= a){ flash("OUT must be after IN"); return; }
  segs.push({a:a, b:b}); pendingIn = null;
  document.getElementById("pin").textContent = "-";
  render();
}
function nudge(d){ v.currentTime = Math.max(0, (v.currentTime||0) + d); }
function del(i){ segs.splice(i,1); render(); }
function up(i){ if(i>0){ var t=segs[i-1]; segs[i-1]=segs[i]; segs[i]=t; render(); } }
function down(i){ if(i<segs.length-1){ var t=segs[i+1]; segs[i+1]=segs[i]; segs[i]=t; render(); } }
function play(i){ v.currentTime = segs[i].a; v.play(); }
function clearAll(){ segs=[]; pendingIn=null; render(); }

function render(){
  var tb = document.getElementById("rows"), h = "";
  var tot = 0;
  for (var i=0;i<segs.length;i++){
    var s = segs[i], len = s.b - s.a; tot += len;
    h += "<tr><td class=n>"+(i+1)+"</td><td class=n>"+fmt(s.a)+"</td><td class=n>"+fmt(s.b)+"</td>"
      +  "<td class=n>"+len.toFixed(1)+"s</td>"
      +  "<td class=n>"+(BASE+s.a).toFixed(1)+":"+(BASE+s.b).toFixed(1)+"</td><td>"
      +  "<button class=mini onclick='play("+i+")'>play</button> "
      +  "<button class=mini onclick='up("+i+")'>&uarr;</button> "
      +  "<button class=mini onclick='down("+i+")'>&darr;</button> "
      +  "<button class=mini onclick='del("+i+")'>x</button></td></tr>";
  }
  tb.innerHTML = h;
  var el = document.getElementById("total");
  el.textContent = segs.length ? (segs.length+" segments, "+tot.toFixed(1)+"s total"
     + (tot>60 ? "  - OVER the 60s Shorts limit" : "")) : "nothing marked";
  el.className = "tot" + (tot>60 ? " over" : "");
  document.getElementById("cmd").value = build();
  try{ localStorage.setItem("edit_"+VIDEO, JSON.stringify(segs)); }catch(e){}
}
function build(){
  if (!segs.length) return "";
  var parts = [];
  for (var i=0;i<segs.length;i++)
    parts.push("--seg " + (BASE+segs[i].a).toFixed(1) + ":" + (BASE+segs[i].b).toFixed(1));
  // tools/short_chain.py, never scripts/make_short.py (2026-09-02): the raw
  // render has none of the engine's gates. check_short_entry.py proves it.
  return "python tools/short_chain.py --video " + VIDEO + " " + parts.join(" ")
       + " --out \\"" + OUT + "\\"";
}
function copyCmd(){
  var c = document.getElementById("cmd");
  if (!c.value){ flash("mark something first"); return; }
  c.focus(); c.select();
  var ok=false; try{ ok = document.execCommand("copy"); }catch(e){}
  flash(ok ? "copied" : "select the text above and copy");
}
function flash(m){ document.getElementById("msg").textContent = m;
  setTimeout(function(){ document.getElementById("msg").textContent=""; }, 2500); }

document.addEventListener("keydown", function(e){
  if (e.target.tagName === "TEXTAREA") return;
  var k = e.key.toLowerCase();
  if (k === "i") markIn();
  else if (k === "o") markOut();
  else if (k === "j") nudge(-5);
  else if (k === "l") nudge(5);
  else if (k === " ") { e.preventDefault(); if (v.paused) v.play(); else v.pause(); }
});
try{ var st = localStorage.getItem("edit_"+VIDEO); if (st) segs = JSON.parse(st)||[]; }catch(e){}
render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="long-form mp4 in READY-TO-REVIEW")
    ap.add_argument("--video", required=True, help="source youtube id")
    ap.add_argument("--base", type=float, required=True,
                    help="source seconds at the long-form's t=0")
    ap.add_argument("--out", default=None, help="name for the short it will build")
    args = ap.parse_args()

    name = Path(args.file).name
    outname = args.out or str(OUTDIR / ("SHORT_" + Path(args.file).stem + ".mp4"))
    html = (PAGE.replace("__NAME__", name)
                .replace("__FILE__", name)
                .replace("__VID__", args.video)
                .replace("__BASE__", "%.1f" % args.base)
                .replace("__OUTNAME__", outname.replace("\\", "\\\\"))
                .replace("__ROOT__", str(ROOT)))
    dest = OUTDIR / ("EDIT_" + Path(args.file).stem + ".html")
    dest.write_text(html, encoding="utf-8")
    print("wrote " + str(dest))
    print("  video base offset: %.1fs" % args.base)


if __name__ == "__main__":
    main()
