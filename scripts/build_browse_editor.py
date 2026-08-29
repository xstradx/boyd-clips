"""Editor: watch the hearing, pick moments, assemble a short.

Nathan asked for this three times, then twice more to fix it:
  "I need it to be easier to use easier layout maybe too"
  "Too cluttered but I would like you to add 3 sec option and keep the 1"
  "Maybe make the buttons different shape idk more satisfying easy to use"

So this version drops the timeline strip, the filter dropdown, the eight-column
table and the always-visible command box. Two columns: the player and your
short on the left, the moment list on the right.

Trim steps are 1s and 3s per end, grouped as segmented controls rather than
loose buttons. Controls are pill-shaped with a real press state, because he
asked for it to feel good rather than just work.

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

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>__NAME__</title>
<style>
:root{--bg:#0d0f13;--card:#161a20;--line:#252b34;--fg:#eceef2;--dim:#8b93a1;
--go:#2ea36b;--go2:#37bd7c;--accent:#6ea8fe;--warn:#d3574c;--p5:#e3b640}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{display:grid;grid-template-columns:352px 1fr;gap:26px;padding:20px;max-width:1260px;margin:0 auto}
@media(max-width:900px){.wrap{grid-template-columns:1fr}}
video{width:100%;background:#000;border-radius:14px;display:block}

button{font-family:inherit;cursor:pointer;border:1px solid var(--line);
background:#1c222b;color:var(--fg);border-radius:999px;padding:9px 17px;font-size:14px;
transition:transform .06s ease,background .12s ease,border-color .12s ease;
box-shadow:0 1px 0 rgba(255,255,255,.04) inset}
button:hover{background:#232b36;border-color:#3d4753}
button:active{transform:translateY(1px) scale(.985);background:#191f27}
.go{background:var(--go);border-color:transparent;color:#fff;font-weight:600}
.go:hover{background:var(--go2)}
.acc{background:var(--accent);border-color:transparent;color:#08121f;font-weight:700}
.acc:hover{filter:brightness(1.08)}
.s{padding:5px 12px;font-size:13px}
.dim{color:var(--dim);font-size:13px}
.bar{display:flex;gap:9px;align-items:center;margin:12px 0;flex-wrap:wrap}

/* trim steps as one segmented control, not four loose buttons */
.seg{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:#161b22}
.seg button{border:0;border-radius:0;background:transparent;padding:5px 11px;font-size:13px;
font-variant-numeric:tabular-nums;box-shadow:none}
.seg button+button{border-left:1px solid var(--line)}
.seg button:hover{background:#242c37}
.seg button:active{background:#2e3844;transform:none}

h2{font-size:11.5px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);
margin:0 0 11px;font-weight:600;display:flex;gap:10px;align-items:center}
.m{border-bottom:1px solid var(--line);padding:13px 4px;display:flex;gap:11px;align-items:flex-start;
border-radius:9px;transition:background .12s ease}
.m:hover{background:#141920}
.pn{font-size:11px;font-weight:800;border-radius:999px;padding:3px 9px;background:#1c222b;
color:var(--dim);flex:none;min-width:26px;text-align:center}
.p5{background:var(--p5);color:#151515}.p4{background:#2f6b4c;color:#fff}
.mt{flex:1;min-width:0}
.ml{font-weight:600;margin-bottom:2px}
.mw{color:var(--dim);font-size:13px}
.clip{border:1px solid var(--line);border-radius:13px;padding:12px 14px;margin-bottom:10px;
background:var(--card);transition:border-color .12s ease}
.clip:hover{border-color:#39414d}
.ch{display:flex;gap:8px;align-items:center;margin-bottom:9px}
.ci{font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ct{color:var(--dim);font-size:12px;font-variant-numeric:tabular-nums;flex:none}
.edge{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--dim);flex-wrap:wrap}
.tot{font-weight:600}.over{color:var(--warn)}
#cmd{width:100%;background:#0a0d11;color:var(--fg);border:1px solid var(--line);
border-radius:11px;padding:11px;font:12px ui-monospace,Consolas,monospace;min-height:72px;display:none}
kbd{background:#1c222b;border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:12px}
.list{max-height:66vh;overflow:auto}
.lane{display:flex;gap:3px;height:44px;background:#0a0d11;border:1px solid var(--line);border-radius:10px;padding:4px;margin-bottom:10px;overflow:hidden}
.blk{position:relative;background:linear-gradient(180deg,#2f7f57,#256744);border-radius:7px;min-width:14px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:11px;color:#dff3e8;overflow:hidden;transition:filter .12s ease}
.blk:hover{filter:brightness(1.18)}
.blk.sel{outline:2px solid var(--accent);outline-offset:-2px}
.lane .empty{color:var(--dim);font-size:12px;margin:auto}
.scrub{-webkit-appearance:none;appearance:none;width:100%;height:26px;background:transparent;margin:10px 0 2px;cursor:pointer;display:block}
.scrub::-webkit-slider-runnable-track{height:10px;border-radius:999px;background:linear-gradient(90deg,var(--go) 0%,var(--go) var(--pct,0%),#232a34 var(--pct,0%),#232a34 100%)}
.scrub::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:22px;height:22px;border-radius:50%;background:#fff;border:3px solid var(--go);margin-top:-6px;box-shadow:0 2px 6px rgba(0,0,0,.45);transition:transform .08s ease}
.scrub:active::-webkit-slider-thumb{transform:scale(1.18)}
.scrub::-moz-range-track{height:10px;border-radius:999px;background:#232a34}
.scrub::-moz-range-thumb{width:20px;height:20px;border-radius:50%;background:#fff;border:3px solid var(--go)}
</style></head><body><div class="wrap">

<div>
  <video id="v" src="__FILE__" controls preload="metadata"></video>
  <input id="scrub" class="scrub" type="range" min="0" max="1000" value="0" step="1">
  <div class="bar">
    <span class="seg">
      <button onclick="nudge(-5)">-5s</button>
      <button onclick="nudge(-1)">-1s</button>
      <button onclick="nudge(1)">+1s</button>
      <button onclick="nudge(5)">+5s</button>
    </span>
    <span class="dim"><b id="now">0:00</b></span>
  </div>
  <div class="bar">
    <button class="go" onclick="markIn()">Start</button>
    <button class="go" onclick="markOut()">End</button>
    <span class="dim">from <b id="pin">-</b> &middot; <kbd>i</kbd> <kbd>o</kbd></span>
  </div>

  <h2 style="margin-top:24px">your short</h2>
  <div id="lane" class="lane"></div>
  <div class="bar"><button class="s" onclick="splitHere()">Split at playhead</button><span class="dim">cut a section out: split, then delete the piece</span></div>
  <div id="clips"></div>
  <div class="bar"><span class="tot" id="total">nothing yet</span></div>
  <div class="bar">
    <button class="acc" onclick="copyCmd()">Copy command</button>
    <button onclick="clearAll()">Clear</button>
    <span class="dim" id="msg"></span>
  </div>
  <textarea id="cmd" readonly></textarea>
</div>

<div>
  <h2>moments <button class="s" id="tog" onclick="toggleAll()">show all</button></h2>
  <div class="list" id="panel"></div>
</div>

</div>
<script>
var BASE = __BASE__, VIDEO = "__VID__", OUT = "__OUTNAME__";
var M = __MOMENTS__;
var picks = [], pendingIn = null, showAll = false, stopAt = null;
var v = document.getElementById("v");

function fmt(t){ var m=Math.floor(t/60), s=Math.floor(t%60); return m+":"+(s<10?"0":"")+s; }
v.addEventListener("timeupdate", function(){
  document.getElementById("now").textContent = fmt(v.currentTime||0);
  if (stopAt !== null && v.currentTime >= stopAt){ v.pause(); stopAt = null; }
});
var sc = document.getElementById("scrub");
var dragging = false;
sc.addEventListener("input", function(){
  dragging = true; stopAt = null;
  var d = v.duration || 0;
  if (d) v.currentTime = d * (sc.value / 1000);
});
sc.addEventListener("change", function(){ dragging = false; });
function syncScrub(){
  var d = v.duration || 0;
  if (!d || dragging) return;
  var f = v.currentTime / d;
  sc.value = Math.round(f * 1000);
  sc.style.setProperty("--pct", (f * 100).toFixed(2) + "%");
}
v.addEventListener("timeupdate", syncScrub);
v.addEventListener("loadedmetadata", syncScrub);
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
function seek(t){ stopAt=null; v.currentTime=Math.max(0,t-BASE); v.play(); }
function nudge(d){ stopAt=null; v.currentTime=Math.max(0,(v.currentTime||0)+d); }

function toggleAll(){
  showAll = !showAll;
  document.getElementById("tog").textContent = showAll ? "best only" : "show all";
  renderMoments();
}
function renderMoments(){
  var h = "";
  for (var i=0;i<M.length;i++){
    var m = M[i];
    if (!showAll && m.punch < 4) continue;
    var c = m.punch>=5 ? "pn p5" : (m.punch>=4 ? "pn p4" : "pn");
    h += "<div class=m><span class='"+c+"'>"+m.punch+"</span><div class=mt>"
      +  "<div class=ml>"+esc(m.label)+"</div><div class=mw>"+esc(m.what)+"</div></div>"
      +  "<div style='flex:none;display:flex;gap:7px'>"
      +  "<button class=s onclick='seek("+m.start+")'>play</button>"
      +  "<button class='s go' onclick='addM("+i+")'>add</button></div></div>";
  }
  document.getElementById("panel").innerHTML = h || "<div class=dim>none</div>";
}
function addM(i){ picks.push({a:M[i].start, b:M[i].end, label:M[i].label}); render(); }
function markIn(){ pendingIn = v.currentTime + BASE;
  document.getElementById("pin").textContent = fmt(v.currentTime); }
function markOut(){
  if (pendingIn === null){ flash("press Start first"); return; }
  var b = v.currentTime + BASE;
  if (b <= pendingIn){ flash("End must come after Start"); return; }
  picks.push({a:pendingIn, b:b, label:"my clip"});
  pendingIn = null; document.getElementById("pin").textContent = "-"; render();
}
function trim(k, which, d){
  var p = picks[k];
  if (which === 0) p.a = Math.min(p.b - 0.5, Math.max(0, p.a + d));
  else             p.b = Math.max(p.a + 0.5, p.b + d);
  stopAt = null;
  v.currentTime = Math.max(0, (which === 0 ? p.a : p.b - 1.5) - BASE);
  v.play(); render();
}
function playp(k){ var p=picks[k]; stopAt=p.b-BASE; v.currentTime=Math.max(0,p.a-BASE); v.play(); }
function del(k){ picks.splice(k,1); render(); }
function up(k){ if(k>0){ var t=picks[k-1]; picks[k-1]=picks[k]; picks[k]=t; render(); } }
function down(k){ if(k<picks.length-1){ var t=picks[k+1]; picks[k+1]=picks[k]; picks[k]=t; render(); } }
function clearAll(){ picks=[]; pendingIn=null; sel=-1; render(); }
var sel = -1;
function pick(k){ sel = k; playp(k); render(); }

// CapCut's core move: split, then delete a piece. That is how a section comes
// out of the middle of a clip - trimming only ever moves the two outer edges.
function splitHere(){
  var t = (v.currentTime || 0) + BASE;
  for (var k=0;k<picks.length;k++){
    var p = picks[k];
    if (t > p.a + 0.4 && t < p.b - 0.4){
      var right = {a:t, b:p.b, label:p.label};
      p.b = t;
      picks.splice(k+1, 0, right);
      sel = k+1; render(); flash("split");
      return;
    }
  }
  flash("park the playhead inside a clip first");
}
function drawLane(){
  var tot = 0;
  for (var k=0;k<picks.length;k++) tot += picks[k].b - picks[k].a;
  var el = document.getElementById("lane");
  if (!picks.length){ el.innerHTML = "<span class=empty>no clips yet</span>"; return; }
  var h = "";
  for (var k=0;k<picks.length;k++){
    var len = picks[k].b - picks[k].a;
    var pct = Math.max(3, 100 * len / tot);
    h += "<div class='blk" + (k===sel ? " sel" : "") + "' style='flex:" + pct.toFixed(2)
      +  "' onclick='pick(" + k + ")' title='" + esc(picks[k].label) + "'>"
      +  (pct > 7 ? (k+1) : "") + "</div>";
  }
  el.innerHTML = h;
}

function render(){
  var h = "", tot = 0;
  for (var k=0;k<picks.length;k++){
    var p = picks[k], len = p.b - p.a; tot += len;
    h += "<div class=clip><div class=ch><span class=ci>"+(k+1)+". "+esc(p.label)+"</span>"
      +  "<span class=ct>"+len.toFixed(1)+"s</span>"
      +  "<button class=s onclick='playp("+k+")'>play</button>"
      +  "<button class=s onclick='up("+k+")'>&uarr;</button>"
      +  "<button class=s onclick='down("+k+")'>&darr;</button>"
      +  "<button class=s onclick='del("+k+")'>x</button></div>"
      +  "<div class=edge><span>start</span><span class=seg>"
      +  "<button onclick='trim("+k+",0,-3)'>-3s</button>"
      +  "<button onclick='trim("+k+",0,-1)'>-1s</button>"
      +  "<button onclick='trim("+k+",0,1)'>+1s</button>"
      +  "<button onclick='trim("+k+",0,3)'>+3s</button></span>"
      +  "<span style='margin-left:8px'>end</span><span class=seg>"
      +  "<button onclick='trim("+k+",1,-3)'>-3s</button>"
      +  "<button onclick='trim("+k+",1,-1)'>-1s</button>"
      +  "<button onclick='trim("+k+",1,1)'>+1s</button>"
      +  "<button onclick='trim("+k+",1,3)'>+3s</button></span></div></div>";
  }
  document.getElementById("clips").innerHTML = h;
  drawLane();
  var el = document.getElementById("total");
  el.textContent = picks.length
      ? (picks.length + " clips, " + tot.toFixed(0) + "s" + (tot > 60 ? "   OVER 60s" : ""))
      : "nothing yet";
  el.className = "tot" + (tot > 60 ? " over" : "");
  document.getElementById("cmd").value = build();
  try{ localStorage.setItem("browse_"+VIDEO, JSON.stringify(picks)); }catch(e){}
  renderMoments();
}
function build(){
  if (!picks.length) return "";
  var f = [];
  for (var k=0;k<picks.length;k++)
    f.push("--seg " + picks[k].a.toFixed(1) + ":" + picks[k].b.toFixed(1));
  var q = String.fromCharCode(34);
  return "python scripts/make_short.py --video " + VIDEO + " " + f.join(" ")
       + " --no-captions --out " + q + OUT + q;
}
function copyCmd(){
  var c = document.getElementById("cmd");
  if (!c.value){ flash("add a clip first"); return; }
  c.style.display = "block"; c.focus(); c.select();
  var ok=false; try{ ok = document.execCommand("copy"); }catch(e){}
  flash(ok ? "copied" : "select and copy");
}
function flash(m){ document.getElementById("msg").textContent = m;
  setTimeout(function(){ document.getElementById("msg").textContent=""; }, 2500); }
document.addEventListener("keydown", function(e){
  if (e.target.tagName === "TEXTAREA") return;
  var k = e.key.toLowerCase();
  if (k === "i") markIn();
  else if (k === "o") markOut();
  else if (k === " "){ e.preventDefault(); if (v.paused) v.play(); else v.pause(); }
});
try{ var st = localStorage.getItem("browse_"+VIDEO); if (st) picks = JSON.parse(st)||[]; }catch(e){}
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
                .replace("__MOMENTS__", json.dumps(moments))
                .replace("__OUTNAME__", outname.replace("\\", "\\\\")))
    dest = OUTDIR / ("BUILD_" + args.video + ".html")
    dest.write_text(html, encoding="utf-8")
    print("wrote " + str(dest))
    print("  %d moments, base %.1fs" % (len(moments), args.base))


if __name__ == "__main__":
    main()
