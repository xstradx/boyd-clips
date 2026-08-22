"""Editor with an indexed moment list beside the player.

Nathan: "make it full length ... but also on the side or maybe if I scroll down
there's clips of best moments and descriptions on the side so I could look thru
and if I wanted to can piece the short together like that".

So: the whole hearing in the player, every indexed moment listed alongside with
a punch rating and a one-line description, click to jump, plus to add. The
chosen moments become the short, in the order picked - reordering is permitted
on shorts and forbidden on long-form.

Moments come from scripts/index_moments.py. Times are absolute source seconds;
the player runs on the vertical full-length cut, so the page subtracts its base
offset to seek and adds it back when writing the command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Build a short - __NAME__</title>
<style>
:root{--bg:#0e1013;--card:#171a1f;--line:#262b33;--fg:#e7e9ee;--dim:#9aa3b2;
--go:#2ea36b;--accent:#6ea8fe;--warn:#c0483f;--p5:#e0b341}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
.top{padding:12px 18px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
h1{font-size:15px;margin:0}
.grid{display:grid;grid-template-columns:minmax(280px,360px) 1fr;gap:18px;padding:16px 18px;align-items:start}
video{width:100%;background:#000;border-radius:10px;max-height:72vh}
.row{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:9px 0}
button{background:#1f2530;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:7px 12px;font-size:14px;cursor:pointer;font-family:inherit}
button:hover{border-color:#3a424f}
.pri{background:var(--go);border-color:var(--go);color:#fff;font-weight:600}
.acc{background:var(--accent);border-color:var(--accent);color:#08121f;font-weight:600}
.dim{color:var(--dim);font-size:13px}
.mini{padding:2px 8px;font-size:13px}
.panel{max-height:78vh;overflow:auto;padding-right:6px}
.m{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:9px 11px;margin-bottom:7px}
.m:hover{border-color:#3a424f}
.m.on{border-color:var(--go)}
.mh{display:flex;gap:8px;align-items:center;margin-bottom:3px}
.badge{font-size:11px;font-weight:700;border-radius:4px;padding:1px 6px;background:#1f2530;color:var(--dim)}
.b5{background:var(--p5);color:#141414}.b4{background:#3d6b4f;color:#fff}
.lab{font-weight:600;font-size:14px}
.what{color:var(--dim);font-size:12.5px;line-height:1.4}
.tm{color:var(--dim);font-size:12px;font-variant-numeric:tabular-nums;margin-left:auto}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:5px 7px;border-bottom:1px solid var(--line);font-size:13.5px}
th{color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.6px}
td.n{font-variant-numeric:tabular-nums}
#cmd{width:100%;background:#0b0d10;color:var(--fg);border:1px solid var(--line);border-radius:8px;
padding:9px;font:12px ui-monospace,Consolas,monospace;min-height:86px;margin-top:7px}
.tot{font-weight:600}.over{color:var(--warn)}
kbd{background:#1f2530;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12px}
select{background:#1f2530;color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:6px 9px;font-family:inherit}
</style></head><body>
<div class="top"><h1>__NAME__</h1>
<span class="dim">__COUNT__ moments &middot; click to preview, <b>+</b> to add &middot;
<kbd>i</kbd>/<kbd>o</kbd> mark your own &middot; <kbd>space</kbd> play</span></div>
<div class="grid">
  <div>
    <video id="v" src="__FILE__" controls preload="metadata"></video>
    <div class="row">
      <button class="pri" onclick="markIn()">IN</button>
      <button class="pri" onclick="markOut()">OUT</button>
      <button onclick="nudge(-2)">&minus;2s</button>
      <button onclick="nudge(2)">+2s</button>
      <span class="dim">at <b id="now">0:00</b></span>
    </div>
    <div class="row"><span class="dim">show</span>
      <select id="filt" onchange="renderMoments()">
        <option value="0">everything</option>
        <option value="4" selected>punch 4 and 5</option>
        <option value="5">punch 5 only</option>
      </select></div>
    <table><thead><tr><th>#</th><th>label</th><th>len</th><th></th></tr></thead><tbody id="rows"></tbody></table>
    <div class="row"><span class="tot" id="total">nothing picked</span></div>
    <div class="row"><button class="acc" onclick="copyCmd()">Copy build command</button>
      <button onclick="clearAll()">Clear</button><span class="dim" id="msg"></span></div>
    <textarea id="cmd" readonly></textarea>
  </div>
  <div class="panel" id="panel"></div>
</div>
<script>
var BASE = __BASE__, VIDEO = "__VID__", OUT = "__OUTNAME__";
var M = __MOMENTS__;
var picks = [], pendingIn = null;
var v = document.getElementById("v");
function fmt(t){var m=Math.floor(t/60),s=Math.floor(t%60);return m+":"+(s<10?"0":"")+s;}
v.addEventListener("timeupdate",function(){document.getElementById("now").textContent=fmt(v.currentTime||0);});
function seek(t){ v.currentTime = Math.max(0, t - BASE); v.play(); }
function renderMoments(){
  var min = parseInt(document.getElementById("filt").value,10), h="";
  for (var i=0;i<M.length;i++){
    var m=M[i]; if (m.punch < min) continue;
    var on = picked(i) ? " on" : "";
    var bc = m.punch>=5 ? "badge b5" : (m.punch>=4 ? "badge b4" : "badge");
    h += "<div class='m"+on+"'><div class=mh><span class='"+bc+"'>"+m.punch+"</span>"
      +  "<span class=lab>"+esc(m.label)+"</span>"
      +  "<span class=tm>"+Math.round(m.end-m.start)+"s</span></div>"
      +  "<div class=what>"+esc(m.what)+"</div><div class=row>"
      +  "<button class=mini onclick='seek("+m.start+")'>play</button>"
      +  "<button class=mini onclick='addM("+i+")'>+ add</button></div></div>";
  }
  document.getElementById("panel").innerHTML = h || "<div class=dim>nothing at that level</div>";
}
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
function picked(i){ for(var k=0;k<picks.length;k++) if(picks[k].i===i) return true; return false; }
function addM(i){ picks.push({i:i, a:M[i].start, b:M[i].end, label:M[i].label}); render(); }
function markIn(){ pendingIn = v.currentTime + BASE; document.getElementById("msg").textContent="IN "+fmt(v.currentTime); }
function markOut(){
  if(pendingIn===null){ flash("mark IN first"); return; }
  var b = v.currentTime + BASE;
  if (b<=pendingIn){ flash("OUT must be after IN"); return; }
  picks.push({i:-1, a:pendingIn, b:b, label:"custom"}); pendingIn=null; render();
}
function nudge(d){ v.currentTime = Math.max(0,(v.currentTime||0)+d); }
function del(k){ picks.splice(k,1); render(); }
function up(k){ if(k>0){var t=picks[k-1];picks[k-1]=picks[k];picks[k]=t;render();} }
function down(k){ if(k<picks.length-1){var t=picks[k+1];picks[k+1]=picks[k];picks[k]=t;render();} }
function playp(k){ seek(picks[k].a); }
function clearAll(){ picks=[]; pendingIn=null; render(); }
function render(){
  var h="", tot=0;
  for(var k=0;k<picks.length;k++){
    var p=picks[k], len=p.b-p.a; tot+=len;
    h += "<tr><td class=n>"+(k+1)+"</td><td>"+esc(p.label)+"</td><td class=n>"+len.toFixed(0)+"s</td><td>"
      + "<button class=mini onclick='playp("+k+")'>play</button> "
      + "<button class=mini onclick='up("+k+")'>&uarr;</button> "
      + "<button class=mini onclick='down("+k+")'>&darr;</button> "
      + "<button class=mini onclick='del("+k+")'>x</button></td></tr>";
  }
  document.getElementById("rows").innerHTML=h;
  var el=document.getElementById("total");
  el.textContent = picks.length ? (picks.length+" picked, "+tot.toFixed(0)+"s"+(tot>60?"  - OVER 60s":"")) : "nothing picked";
  el.className = "tot"+(tot>60?" over":"");
  document.getElementById("cmd").value = build();
  try{ localStorage.setItem("browse_"+VIDEO, JSON.stringify(picks)); }catch(e){}
  renderMoments();
}
function build(){
  if(!picks.length) return "";
  var f=[];
  for(var k=0;k<picks.length;k++) f.push("--seg "+picks[k].a.toFixed(1)+":"+picks[k].b.toFixed(1));
  return "python scripts/make_short.py --video "+VIDEO+" "+f.join(" ")+" --no-captions --out \\""+OUT+"\\"";
}
function copyCmd(){
  var c=document.getElementById("cmd");
  if(!c.value){ flash("pick something first"); return; }
  c.focus(); c.select();
  var ok=false; try{ok=document.execCommand("copy");}catch(e){}
  flash(ok?"copied":"select and copy");
}
function flash(m){ document.getElementById("msg").textContent=m;
  setTimeout(function(){document.getElementById("msg").textContent="";},2500); }
document.addEventListener("keydown",function(e){
  if(e.target.tagName==="TEXTAREA"||e.target.tagName==="SELECT") return;
  var k=e.key.toLowerCase();
  if(k==="i") markIn(); else if(k==="o") markOut();
  else if(k===" "){e.preventDefault(); if(v.paused)v.play(); else v.pause();}
});
try{ var st=localStorage.getItem("browse_"+VIDEO); if(st) picks=JSON.parse(st)||[]; }catch(e){}
render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="video in READY-TO-REVIEW to scrub")
    ap.add_argument("--video", required=True)
    ap.add_argument("--base", type=float, required=True,
                    help="source seconds at the video's t=0")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    mp = ROOT / "state" / ("moments_%s.json" % args.video)
    if not mp.exists():
        print("run index_moments.py first")
        return
    moments = json.loads(mp.read_text(encoding="utf-8"))
    outname = args.out or str(OUTDIR / ("SHORT_" + args.video + ".mp4"))
    html = (PAGE.replace("__NAME__", Path(args.file).name)
                .replace("__FILE__", Path(args.file).name)
                .replace("__VID__", args.video)
                .replace("__BASE__", "%.1f" % args.base)
                .replace("__COUNT__", str(len(moments)))
                .replace("__MOMENTS__", json.dumps(moments))
                .replace("__OUTNAME__", outname.replace("\\", "\\\\")))
    dest = OUTDIR / ("BUILD_" + args.video + ".html")
    dest.write_text(html, encoding="utf-8")
    print("wrote " + str(dest))
    print("  %d moments, base %.1fs" % (len(moments), args.base))


if __name__ == "__main__":
    main()
