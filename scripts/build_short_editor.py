"""Editing page for a SHORT, on the short's own timeline.

Nathan: "I meant editing the short cuts".

The catch is that a short is not a slice of the hearing - silence was removed
when it was built, so 14 seconds are missing and a mark at 0:20 in the short is
not 0:20 in the source. short_chain (and make_short) write a .map.json beside each short
recording where every kept piece came from; this page loads it and converts
marks back through it.

A marked range can straddle several pieces, so it becomes one --seg per piece it
overlaps. Rebuilding from source rather than re-trimming the finished file means
captions and framing are regenerated instead of being cut through.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Edit __NAME__</title>
<style>
:root{--bg:#0e1013;--card:#171a1f;--line:#262b33;--fg:#e7e9ee;--dim:#9aa3b2;--go:#2ea36b;--accent:#6ea8fe;--warn:#c0483f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:16px;display:grid;grid-template-columns:340px 1fr;gap:18px}
h1{font-size:16px;margin:0 0 10px;grid-column:1/-1}
video{width:100%;background:#000;border-radius:10px;max-height:70vh}
.row{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:9px 0}
button{background:#1f2530;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:7px 13px;font-size:14px;cursor:pointer;font-family:inherit}
button:hover{border-color:#3a424f}
.pri{background:var(--go);border-color:var(--go);color:#fff;font-weight:600}
.acc{background:var(--accent);border-color:var(--accent);color:#08121f;font-weight:600}
.dim{color:var(--dim);font-size:13px}
table{width:100%;border-collapse:collapse;margin-top:6px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.7px}
td.n{font-variant-numeric:tabular-nums}
.mini{padding:2px 8px;font-size:13px}
#cmd{width:100%;background:#0b0d10;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:10px;font:12px ui-monospace,Consolas,monospace;min-height:110px;margin-top:8px}
kbd{background:#1f2530;border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-size:12px}
.tot{font-weight:600}.over{color:var(--warn)}
</style></head><body><div class="wrap">
<h1>__NAME__ &mdash; trim the short</h1>
<div><video id="v" src="__FILE__" controls preload="metadata"></video>
<div class="row">
  <button class="pri" onclick="markIn()">IN <kbd>i</kbd></button>
  <button class="pri" onclick="markOut()">OUT <kbd>o</kbd></button>
  <button onclick="nudge(-1)">&minus;1s</button>
  <button onclick="nudge(-0.2)">&minus;.2</button>
  <button onclick="nudge(0.2)">+.2</button>
  <button onclick="nudge(1)">+1s</button>
</div>
<div class="row dim">at <b id="now">0:00.0</b> &middot; pending in <b id="pin">-</b> &middot; short is <b>__DUR__s</b></div>
</div>
<div>
<table id="tbl"><thead><tr><th>#</th><th>from</th><th>to</th><th>len</th><th></th></tr></thead><tbody id="rows"></tbody></table>
<div class="row"><span class="tot" id="total">nothing kept &mdash; whole short</span></div>
<div class="row">
  <button class="acc" onclick="copyCmd()">Copy build command</button>
  <button onclick="clearAll()">Clear</button>
  <span class="dim" id="msg"></span>
</div>
<textarea id="cmd" readonly></textarea>
<p class="dim">Mark the parts to <b>keep</b>. They rebuild from the original source, so captions
and framing are regenerated rather than cut through. Order is the play order &mdash; move one to
the top to make it the hook.</p>
</div></div>
<script>
var MAP = __MAP__;
var VIDEO = "__VID__";
var OUT = "__OUTNAME__";
var segs = [], pendingIn = null;
var v = document.getElementById("v");

function fmt(t){ var m=Math.floor(t/60), s=(t%60); return m+":"+(s<10?"0":"")+s.toFixed(1); }
v.addEventListener("timeupdate", function(){ document.getElementById("now").textContent = fmt(v.currentTime||0); });

// a range on the SHORT becomes one or more ranges in the SOURCE
function toSource(a, b){
  var out = [];
  for (var i=0;i<MAP.length;i++){
    var p = MAP[i];
    var s = Math.max(a, p.short_start), e = Math.min(b, p.short_end);
    if (e - s <= 0.05) continue;
    out.push([ p.src_start + (s - p.short_start), p.src_start + (e - p.short_start) ]);
  }
  // join pieces that were adjacent in the source anyway
  var merged = [];
  for (var j=0;j<out.length;j++){
    if (merged.length && out[j][0] - merged[merged.length-1][1] < 0.35)
      merged[merged.length-1][1] = out[j][1];
    else merged.push(out[j]);
  }
  return merged;
}
function markIn(){ pendingIn = v.currentTime; document.getElementById("pin").textContent = fmt(pendingIn); }
function markOut(){
  if (pendingIn === null){ flash("mark IN first"); return; }
  if (v.currentTime <= pendingIn){ flash("OUT must be after IN"); return; }
  segs.push({a:pendingIn, b:v.currentTime}); pendingIn = null;
  document.getElementById("pin").textContent = "-"; render();
}
function nudge(d){ v.currentTime = Math.max(0, (v.currentTime||0) + d); }
function del(i){ segs.splice(i,1); render(); }
function up(i){ if(i>0){ var t=segs[i-1]; segs[i-1]=segs[i]; segs[i]=t; render(); } }
function down(i){ if(i<segs.length-1){ var t=segs[i+1]; segs[i+1]=segs[i]; segs[i]=t; render(); } }
function play(i){ v.currentTime = segs[i].a; v.play(); }
function clearAll(){ segs=[]; pendingIn=null; render(); }

function render(){
  var h="", tot=0;
  for (var i=0;i<segs.length;i++){
    var s=segs[i], len=s.b-s.a; tot+=len;
    h += "<tr><td class=n>"+(i+1)+"</td><td class=n>"+fmt(s.a)+"</td><td class=n>"+fmt(s.b)+"</td>"
      + "<td class=n>"+len.toFixed(1)+"s</td><td>"
      + "<button class=mini onclick='play("+i+")'>play</button> "
      + "<button class=mini onclick='up("+i+")'>&uarr;</button> "
      + "<button class=mini onclick='down("+i+")'>&darr;</button> "
      + "<button class=mini onclick='del("+i+")'>x</button></td></tr>";
  }
  document.getElementById("rows").innerHTML = h;
  var el = document.getElementById("total");
  el.textContent = segs.length ? (segs.length+" kept, "+tot.toFixed(1)+"s"
      + (tot>60 ? "  - OVER 60s" : "")) : "nothing kept - whole short";
  el.className = "tot" + (tot>60 ? " over" : "");
  document.getElementById("cmd").value = build();
  try{ localStorage.setItem("shortedit_"+VIDEO, JSON.stringify(segs)); }catch(e){}
}
function build(){
  if (!segs.length) return "";
  var flags = [];
  for (var i=0;i<segs.length;i++){
    var rs = toSource(segs[i].a, segs[i].b);
    for (var j=0;j<rs.length;j++)
      flags.push("--seg " + rs[j][0].toFixed(1) + ":" + rs[j][1].toFixed(1));
  }
  // tools/short_chain.py, never scripts/make_short.py: the raw render skips
  // word alignment, tightening, the engine's gates and the floor stamp
  // (2026-09-02, "Okay then make it have it pls"). check_short_entry.py proves it.
  return "python tools/short_chain.py --video " + VIDEO + " " + flags.join(" ")
       + " --out \\"" + OUT + "\\"";
}
function copyCmd(){
  var c=document.getElementById("cmd");
  if(!c.value){ flash("mark something first"); return; }
  c.focus(); c.select();
  var ok=false; try{ ok=document.execCommand("copy"); }catch(e){}
  flash(ok ? "copied" : "select and copy");
}
function flash(m){ document.getElementById("msg").textContent=m;
  setTimeout(function(){ document.getElementById("msg").textContent=""; }, 2500); }
document.addEventListener("keydown", function(e){
  if (e.target.tagName === "TEXTAREA") return;
  var k=e.key.toLowerCase();
  if(k==="i") markIn(); else if(k==="o") markOut();
  else if(k==="j") nudge(-1); else if(k==="l") nudge(1);
  else if(k===" "){ e.preventDefault(); if(v.paused) v.play(); else v.pause(); }
});
try{ var st=localStorage.getItem("shortedit_"+VIDEO); if(st) segs=JSON.parse(st)||[]; }catch(e){}
render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--short", required=True, help="the short's mp4 name in READY-TO-REVIEW")
    args = ap.parse_args()

    short = OUTDIR / args.short
    mp = short.with_suffix(".map.json")
    if not mp.exists():
        print("no map beside " + short.name + " - rebuild it with tools/short_chain.py first")
        return
    data = json.loads(mp.read_text(encoding="utf-8"))
    html = (PAGE.replace("__NAME__", short.name)
                .replace("__FILE__", short.name)
                .replace("__MAP__", json.dumps(data["pieces"]))
                .replace("__VID__", data["video"])
                .replace("__DUR__", "%.1f" % data["duration_s"])
                .replace("__OUTNAME__", str(short).replace("\\", "\\\\")))
    dest = OUTDIR / ("EDIT_" + short.stem + ".html")
    dest.write_text(html, encoding="utf-8")
    print("wrote " + str(dest))
    print("  %d pieces, short is %.1fs" % (len(data["pieces"]), data["duration_s"]))


if __name__ == "__main__":
    main()
