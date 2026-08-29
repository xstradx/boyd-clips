"""Studio: a real timeline editor for assembling a short.

Nathan, five passes in: "there's a lot of stuff missing and confusing and I
can't delete mistakes and stuff".

The previous four pages were the same shape with different paint - a source
player plus a list of numbers, and a command to copy. That shape is the fault.
In CapCut you look at the thing you are BUILDING, you drag its edges, and every
action is undoable. So this is not a restyle of the list:

  * the timeline is the document. Blocks sized in real pixels-per-second,
    dragged to reorder, edges dragged to trim, zoomable.
  * PLAY SHORT plays the assembled edit back-to-back with a playhead running
    across the timeline, so the cut is watched rather than imagined.
  * every mutation goes through push() into an undo stack. Ctrl+Z / Ctrl+Y,
    plus visible buttons, plus Delete on the selection. Nothing is permanent.
  * split at the playhead, then delete a half - that is how a section comes out
    of the middle, which trimming edges can never do.

Times in the moment index are absolute source seconds; the player runs on the
vertical full-length cut, so BASE is subtracted to seek and added back when the
build command is written.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>__NAME__</title>
<style>
:root{
  /* Surfaces are pure neutral, R=G=B, because this UI surrounds picture.
     Adobe Spectrum: "fully desaturated grays to prevent the misinterpretation of
     colors due to chromatic adaptation caused by the user interface". Resolve
     ships the same as a toggle, citing "the blue-gray UI's potential to bias the
     eye". Ratios below are measured against the panel. */
  --bg:#111111;          /* Spectrum dark background-base */
  --panel:#1b1b1b;       /* background-layer-1 */
  --card:#222222;        /* background-layer-2 */
  --line:#3a3a3a;        /* divider, decorative           Radix grayDark 6 */
  --line2:#484848;       /* interactive component border  Radix grayDark 7 */
  --line3:#8a8a8a;       /* focus ring / strong border    4.99:1 */
  --dim:#afafaf;         /* muted text                    7.85:1 */
  --fg:#dbdbdb;          /* body text                    12.44:1 */
  --hi:#f2f2f2;          /* high contrast                15.39:1 */
  --faint:#8a8a8a;       /* 4.99:1 - the old faint grey was below AA */
  /* one job per hue: blue acts, teal is your material, yellow is the standout,
     red is position. */
  --go:#0090ff;          /* Radix blueDark 9   5.28:1 */
  --go2:#3b9eff;         /* hover  10          6.17:1 */
  --acc:#70b8ff;         /* accent text / outline 11   8.19:1 */
  --onAcc:#111111;       /* white on #0090ff is 3.26:1 and FAILS AA */
  --warn:#ff9592;        /* Radix redDark 11   8.17:1 */
  --gold:#ffe629;        /* Radix yellowDark 9 13.62:1 */
  --clip:#1c6961; --clip2:#145751;   /* tealDark 6 / 5 */
  --clipb:#207e73;       /* tealDark 7  3.52:1 - carries the clip boundary */
  /* surfaces that are not text or accent, so a theme can move all of them */
  --btn:#262626; --btnH:#303030; --btnA:#1e1e1e;
  --seg:#242424; --segH:#2e2e2e; --segA:#383838;
  --sunken:#0d0d0d; --chip:#2a2a2a; --row:#191919; --rowH:#232323;
  --sub:#171717; --pick:#10304d; --lineH:#5a5a5a;
  --used:#12211f; --overBg:#0d1a26; --stage:#1b1b1b;
  --dangerBg:#2a1212; --dangerLine:#7d3a34; --dangerFg:#f0cfca;
  --hookBg:#241f08; --hookLine:#5a4a1a; --hookFg:#f0e6c8;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);overflow:hidden;
  font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;user-select:none}

/* ---- frame: header / work area / timeline dock ---- */
.app{display:flex;flex-direction:column;height:100vh}
.hdr{display:flex;align-items:center;gap:14px;padding:9px 16px;
  border-bottom:1px solid var(--line);background:var(--panel);flex:none}
.hdr .ttl{font-weight:650;font-size:14px;letter-spacing:.2px}
.hdr .sub{color:var(--faint);font-size:12px}
.themes{display:inline-flex;gap:5px;align-items:center}
.th{padding:4px 9px;font-size:11.5px;border-radius:7px;background:var(--btn);
  display:inline-flex;align-items:center;gap:6px;color:var(--dim)}
.th i{width:9px;height:9px;border-radius:50%;display:inline-block;
  box-shadow:0 0 0 1px rgba(128,128,128,.35)}
.th.on{color:var(--hi);border-color:var(--line3);background:var(--btnA)}
.spacer{flex:1}
.work{flex:1;display:grid;grid-template-columns:minmax(340px,460px) 1fr;gap:0;min-height:0}
@media(max-width:1100px){.work{grid-template-columns:minmax(280px,380px) 1fr}}
.stage{display:flex;flex-direction:column;align-items:center;padding:10px 14px;
  min-height:0;overflow:hidden;background:var(--stage)}
/* the video takes whatever is left AFTER the controls, never more. Letting it be
   max-height:100% of the stage pushed the transport row out of the box and under
   the timeline dock - measured at 2048x950: stage ended 754, buttons drew to 787. */
.vwrap{flex:1;min-height:0;width:100%;display:flex;align-items:center;justify-content:center}
.stage video{max-height:100%;max-width:100%;background:#000;border-radius:12px;
  box-shadow:0 8px 32px rgba(0,0,0,.55);display:block}
.ctl{flex:none;width:100%;display:flex;flex-direction:column;align-items:center;padding-top:6px}
.side{border-left:1px solid var(--line);background:var(--panel);
  display:flex;flex-direction:column;min-height:0}
.dock{flex:none;border-top:1px solid var(--line);background:var(--panel);
  padding:10px 14px 14px}

/* ---- controls ---- */
button{font:inherit;font-size:13px;cursor:pointer;color:var(--fg);
  background:var(--btn);border:1px solid var(--line2);border-radius:8px;padding:7px 13px;
  transition:background .12s,border-color .12s,transform .05s,opacity .12s}
button:hover:not(:disabled){background:var(--btnH);border-color:var(--lineH)}
button:active:not(:disabled){transform:translateY(1px)}
button:disabled{opacity:.32;cursor:default}
.go{background:var(--go);border-color:transparent;color:var(--onAcc);font-weight:650}
.go:hover:not(:disabled){background:var(--go2)}
.acc{background:var(--go);border-color:transparent;color:var(--onAcc);font-weight:700}
.dngr:hover:not(:disabled){background:var(--dangerBg);border-color:var(--dangerLine);color:var(--dangerFg)}
.sm{padding:4px 9px;font-size:12px;border-radius:7px}
.ico{padding:6px 10px;font-size:14px;line-height:1}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.row.nowrap{flex-wrap:nowrap;justify-content:center;white-space:nowrap}
.dim{color:var(--dim);font-size:12.5px}
.faint{color:var(--faint);font-size:12px}
.num{font-variant-numeric:tabular-nums}
kbd{background:var(--btn);border:1px solid var(--line2);border-bottom-width:2px;
  border-radius:5px;padding:0 5px;font-size:11px;color:var(--dim);font-family:inherit}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.seg button{border:0;border-radius:0;background:var(--seg);padding:6px 10px;font-size:12px}
.seg button+button{border-left:1px solid var(--line2)}

/* ---- scrub ---- */
.scrub{-webkit-appearance:none;appearance:none;width:100%;max-width:520px;height:22px;
  background:transparent;cursor:pointer;display:block;margin:10px 0 2px}
.scrub::-webkit-slider-runnable-track{height:6px;border-radius:99px;
  background:linear-gradient(90deg,var(--acc) 0 var(--pct,0%),#242b35 var(--pct,0%) 100%)}
.scrub::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;
  background:#fff;margin-top:-5px;box-shadow:0 1px 5px rgba(0,0,0,.6)}
.scrub::-moz-range-track{height:6px;border-radius:99px;background:var(--seg)}
.scrub::-moz-range-thumb{width:14px;height:14px;border-radius:50%;background:#fff;border:0}

/* ---- moments ---- */
.sh{padding:11px 14px;border-bottom:1px solid var(--line);display:flex;
  align-items:center;gap:9px;flex:none}
.sh h2{margin:0;font-size:11px;text-transform:uppercase;letter-spacing:1.1px;
  color:var(--dim);font-weight:650}
.list{overflow-y:auto;flex:1;padding:8px;display:grid;align-content:start;gap:calc(6px * var(--pad,1));
  grid-template-columns:repeat(auto-fill,minmax(var(--colW,330px),1fr))}
.m{display:flex;gap:10px;padding:calc(9px * var(--pad,1)) calc(10px * var(--pad,1));border-radius:10px;align-items:flex-start;
  cursor:pointer;transition:background .1s,border-color .1s;background:var(--row);
  border:1px solid var(--segH)}
.m:hover{background:var(--rowH);border-color:#3a3a3a}
.pn{flex:none;min-width:24px;height:22px;border-radius:6px;background:var(--chip);color:var(--dim);
  font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center}
.p5{background:var(--gold);color:var(--onAcc)}.p4{background:var(--clipb);color:var(--hi)}
.mt{flex:1;min-width:0}
.ml{font-weight:600;font-size:13px}
.mw{color:var(--dim);font-size:12px;margin-top:1px}
.madd{flex:none;opacity:0;transition:opacity .12s}
.m:hover .madd{opacity:1}
.in-use{outline:1px solid var(--clipb);background:var(--used)}
.sug{flex:none;padding:9px 12px;border-bottom:1px solid var(--line);background:var(--sub)}
.plans{display:flex;gap:7px;flex-wrap:wrap}
.plan{border:1px solid var(--line2);background:#222222;border-radius:9px;padding:6px 12px;
  font-size:12.5px;text-align:left;line-height:1.35}
.plan b{display:block;font-weight:650}
.plan span{color:var(--dim);font-size:11px;font-variant-numeric:tabular-nums}
.plan.on{border-color:var(--acc);background:var(--pick);color:#fff}
.plan.on span{color:#b9d3ff}
.sugwhy{margin-top:8px;font-size:12.5px;color:var(--dim);line-height:1.45}
.sugwhy b{color:var(--fg)}
.hookline{margin-top:7px;padding:7px 9px;border-radius:8px;background:var(--hookBg);
  border:1px solid var(--hookLine);font-size:12.5px;line-height:1.45;color:var(--hookFg)}
.hookline b{color:var(--gold)}
.rl{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.7px;
  text-transform:uppercase;padding:1px 6px;border-radius:5px;margin-right:6px;vertical-align:1px}
.rl-hook{background:var(--go);color:var(--onAcc)}
.rl-payoff{background:var(--gold);color:var(--onAcc)}
.rl-escalation{background:var(--clipb);color:var(--hi)}
.rl-setup{background:var(--line2);color:var(--fg)}
.rl-filler{background:var(--card);color:var(--dim)}
.rl-case2{background:#e5484d;color:var(--onAcc)}
.warnline{margin-top:7px;padding:8px 10px;border-radius:8px;background:var(--dangerBg);
  border:1px solid var(--dangerLine);font-size:12.5px;line-height:1.45;color:var(--dangerFg)}
.warnline b{color:#ff9d90}
.note{color:var(--dim);font-size:12px;margin-top:3px;font-style:italic}
body.noRoles .note{display:none}
body.noWhy .whyline,body.noWhy .sugwhy{display:none}
.best{box-shadow:0 0 0 1px var(--gold) inset}
.mwrap{display:flex;flex-direction:column;gap:0}
.mwrap.open .m{border-color:var(--acc);border-bottom-left-radius:0;border-bottom-right-radius:0}
.trim{border:1px solid var(--acc);border-top:0;border-radius:0 0 10px 10px;
  background:var(--btnA);padding:9px 11px 10px}
.mr{font-size:12px;margin-bottom:6px}
.mr .chg{color:var(--gold);font-weight:650}
.tl{display:flex;align-items:center;gap:9px;margin:3px 0}
.tl>span{width:34px;flex:none;font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.6px}
.seg.tiny{flex:none}
.seg.tiny button{padding:3px 7px;font-size:11px;font-variant-numeric:tabular-nums}
.tsl{-webkit-appearance:none;appearance:none;flex:1;height:18px;background:transparent;cursor:pointer}
.tsl::-webkit-slider-runnable-track{height:5px;border-radius:99px;background:var(--seg)}
.tsl::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;border-radius:50%;
  background:var(--acc);margin-top:-5px;box-shadow:0 1px 4px rgba(0,0,0,.6)}
.tsl::-moz-range-track{height:5px;border-radius:99px;background:var(--seg)}
.tsl::-moz-range-thumb{width:13px;height:13px;border-radius:50%;background:var(--acc);border:0}
.trow{display:flex;align-items:center;gap:7px;margin-top:8px}

/* ---- timeline ---- */
.tlbar{display:flex;align-items:center;gap:8px;margin-bottom:9px;flex-wrap:wrap}
.tot{font-weight:650;font-variant-numeric:tabular-nums}
.over{color:var(--warn)}
.track{position:relative;height:var(--trackH,88px);background:var(--sunken);border:1px solid var(--line);
  border-radius:10px;overflow-x:auto;overflow-y:hidden;padding:22px 8px 8px}
.ruler{position:absolute;top:0;left:8px;height:18px;pointer-events:none}
.tick{position:absolute;top:0;height:18px;border-left:1px solid var(--chip);
  padding-left:4px;font-size:10px;color:var(--faint);line-height:18px}
.strip{position:relative;height:52px;display:flex;gap:2px;min-width:100%}
.blk{position:relative;height:100%;border-radius:8px;flex:none;overflow:hidden;
  background:linear-gradient(180deg,var(--clip),var(--clip2));border:1px solid var(--clipb);
  display:flex;align-items:center;justify-content:center;cursor:grab;
  transition:filter .1s,box-shadow .1s}
.blk:hover{filter:brightness(1.15)}
.blk.sel{border-color:var(--acc);box-shadow:0 0 0 2px rgba(110,168,254,.45)}
.blk.drag{opacity:.55;cursor:grabbing}
.blk .lb{font-size:11px;color:var(--hi);padding:0 12px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;pointer-events:none;text-align:center}
.hnd{position:absolute;top:0;bottom:0;width:9px;cursor:ew-resize;background:#0000;
  display:flex;align-items:center;justify-content:center}
.hnd:hover{background:#ffffff28}
.hnd:after{content:"";width:2px;height:20px;border-radius:2px;background:#ffffff70}
.hnd.l{left:0}.hnd.r{right:0}
/* drop targets: a dashed box opens where the moment will land */
.slot{height:100%;flex:none;border:2px dashed var(--acc);border-radius:8px;
  background:rgba(110,168,254,.12);display:flex;align-items:center;justify-content:center;
  color:var(--acc);font-size:11px;font-weight:650;transition:width .12s ease}
.slot.open{width:120px}
.slot.rest{border-color:#3a3a3a;background:var(--sub);color:var(--faint);font-weight:500;
  width:140px;border-style:dashed}
.track.over{border-color:var(--acc);background:#0a0f18}
.m{cursor:grab}
.m.dragging{opacity:.45}
.ph{position:absolute;top:0;bottom:0;width:2px;background:var(--warn);
  box-shadow:0 0 0 1px #111111, 0 0 8px rgba(255,149,146,.55);
  pointer-events:none;display:none;z-index:6}
.ph .grab{position:absolute;top:0;left:-8px;width:18px;height:16px;border-radius:4px;
  background:var(--warn);pointer-events:auto;cursor:ew-resize;
  box-shadow:0 0 0 1px #111111, 0 1px 4px rgba(0,0,0,.6)}
.ph .grab:after{content:"";position:absolute;left:6px;top:4px;width:6px;height:8px;
  border-left:1px solid #11111190;border-right:1px solid #11111190}
.ph .grab:hover{filter:brightness(1.15)}
/* the strip above the clips scrubs the short; the clips themselves stay clickable */
.szone{position:absolute;top:0;left:8px;height:20px;cursor:ew-resize;z-index:5}
.gap{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  color:var(--faint);font-size:12.5px;pointer-events:none}
.det{margin-top:9px;min-height:34px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.whyline{flex-basis:100%;font-size:12px;color:var(--dim);line-height:1.4;margin-top:2px}
.whyline b{color:#9fb6d8;font-weight:650}
@media(max-height:900px){.whyline{margin-top:0}}
#cmd{width:100%;margin-top:9px;background:var(--sunken);color:var(--fg);border:1px solid var(--line);
  border-radius:9px;padding:10px;font:11.5px ui-monospace,Consolas,monospace;
  min-height:60px;display:none;user-select:text}
/* short screens: this machine is 4096x1152, so height is the scarce axis */
@media (max-height:900px){
  .track{height:74px;padding-top:20px}
  .strip{height:44px}
  .dock{padding:8px 14px 10px}
  .scrub{margin:6px 0 0}
  .hdr{padding:6px 16px}
  .det{margin-top:6px;min-height:30px}
}
@media (max-height:760px){
  .track{height:64px;padding-top:18px}
  .strip{height:36px}
  .m{padding:6px 8px}
}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);
  background:var(--btn);border:1px solid var(--line2);border-radius:9px;padding:9px 16px;
  font-size:13px;opacity:0;pointer-events:none;transition:opacity .2s;z-index:50}
.toast.on{opacity:1}
.sheet{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:70;display:none;
  align-items:flex-start;justify-content:flex-end}
.sheet.on{display:flex}
.sheetIn{background:var(--panel);border-left:1px solid var(--line2);height:100%;
  width:400px;max-width:94vw;overflow-y:auto;padding:16px 18px 30px;
  box-shadow:-14px 0 40px rgba(0,0,0,.5)}
.sheetIn h3{margin:0 0 14px;font-size:11px;letter-spacing:1.1px;text-transform:uppercase;
  color:var(--dim);display:flex;justify-content:space-between;align-items:center}
.sheetIn h3 span{cursor:pointer;font-size:19px;color:var(--faint)}
.grp{margin-bottom:15px}
.grp>label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.8px;
  color:var(--faint);margin-bottom:6px}
.opts{display:flex;flex-wrap:wrap;gap:6px}
.opts button{padding:6px 11px;font-size:12.5px;border-radius:8px;background:var(--btn);
  color:var(--dim);display:inline-flex;align-items:center;gap:6px}
.opts button.on{background:var(--go);border-color:transparent;color:var(--onAcc);font-weight:650}
.opts button i{width:10px;height:10px;border-radius:50%;display:inline-block;
  box-shadow:0 0 0 1px rgba(128,128,128,.4)}
.note2{margin:6px 0 0;font-size:11.5px;color:var(--faint);line-height:1.4}
.help{position:fixed;right:18px;bottom:18px;z-index:60;display:none;
  background:var(--card);border:1px solid var(--line2);border-radius:12px;
  padding:14px 16px;box-shadow:0 12px 40px rgba(0,0,0,.55);max-width:390px}
.help h3{margin:0 0 9px;font-size:11px;letter-spacing:1.1px;text-transform:uppercase;
  color:var(--dim);display:flex;justify-content:space-between;align-items:center}
.help h3 span{cursor:pointer;font-size:17px;color:var(--faint)}
.help dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:12.5px}
.help dt{color:var(--hi);font-weight:650;white-space:nowrap}
.help dd{margin:0;color:var(--dim)}
.help i{color:var(--faint);font-style:normal}
</style></head><body>

<div class="app">
  <div class="hdr">
    <span class="ttl">Texas Trial Tracker</span>
    <span class="sub">__NAME__</span>
    <span class="spacer"></span>
    <button class="sm" onclick="openSettings()" title="appearance and behaviour">&#9881; Settings</button>
    <button class="sm" id="bundo" onclick="undo()">&#8630; Undo</button>
    <button class="sm" id="bredo" onclick="redo()">Redo &#8631;</button>
  </div>

  <div class="work">
    <div class="stage">
      <div class="vwrap"><video id="v" src="__FILE__" preload="metadata"></video></div>
      <div class="ctl">
        <input id="scrub" class="scrub" type="range" min="0" max="2000" value="0">
        <div class="row nowrap">
          <span class="seg">
            <button onclick="nudge(-10)">&minus;10</button>
            <button onclick="nudge(-1)">&minus;1</button>
            <button onclick="nudge(-0.2)">&minus;.2</button>
            <button onclick="nudge(0.2)">+.2</button>
            <button onclick="nudge(1)">+1</button>
            <button onclick="nudge(10)">+10</button>
          </span>
          <span class="dim num" id="now">0:00.0</span>
        </div>
        <div class="row nowrap" style="margin-top:2px">
          <button class="go" onclick="markIn()">Start <kbd>i</kbd></button>
          <button class="go" onclick="markOut()">End <kbd>o</kbd></button>
          <span class="faint">from <b id="pin">&mdash;</b></span>
        </div>
      </div>
    </div>

    <div class="side">
      <div class="sh">
        <h2>Suggested cuts</h2>
        <span class="faint" id="sugby"></span>
        <span class="spacer"></span>
        <button class="sm" id="tog" onclick="toggleAll()">show all</button>
      </div>
      <div class="sug" id="sug"></div>
      <div class="list" id="panel"></div>
    </div>
  </div>

  <div class="dock">
    <div class="tlbar">
      <b style="font-size:11px;text-transform:uppercase;letter-spacing:1.1px;color:var(--dim)">Your short</b>
      <button class="sm go" id="bprev" onclick="transport()">&#9654; Play short</button>
      <button class="sm" onclick="setHead(0,true)" title="back to the start">&#9198;</button>
      <span class="dim num" id="hpos">0:00.0 / 0:00.0</span>
      <button class="sm" onclick="splitHere()" id="bsplit">Split <kbd>s</kbd></button>
      <button class="sm" onclick="helpOverlay()" title="keyboard shortcuts">?</button>
      <span class="spacer"></span>
      <span class="tot" id="total">empty</span>
      <span class="faint" id="done"></span>
      <span id="mixwarn" style="display:none;color:var(--warn);font-weight:650;font-size:12px">
        &#9888; this short mixes two defendants</span>
      <span class="seg">
        <button onclick="zoom(0.6)">&minus;</button>
        <button onclick="fitZoom()">fit</button>
        <button onclick="zoom(1.65)">+</button>
      </span>
      <button class="sm acc" id="brender" onclick="doRender()">Render</button>
      <button class="sm dngr" onclick="clearAll()">Clear</button>
    </div>

    <div class="track" id="track" oncontextmenu="return false;"
         ondragover="overTrack(event)" ondrop="dropMoment(event)" ondragleave="leaveTrack(event)">
      <div class="ruler" id="ruler"></div>
      <div class="szone" id="szone" onpointerdown="headDown(event)"></div>
      <div class="strip" id="strip"></div>
      <div class="ph" id="ph"><div class="grab" onpointerdown="headDown(event)"></div></div>
      <div class="gap" id="gap">Add a moment from the right, or mark Start / End on the player</div>
    </div>

    <div class="det" id="det"></div>
    <textarea id="cmd" readonly></textarea>
  </div>
</div>
<div class="toast" id="toast"></div>

<div class="sheet" id="sheet" onclick="if(event.target===this) closeSettings()">
 <div class="sheetIn">
  <h3>Settings <span onclick="closeSettings()">&times;</span></h3>

  <div class="grp"><label>Theme</label><div class="opts" id="optTheme"></div></div>
  <div class="grp"><label>Accent</label><div class="opts" id="optAccent"></div>
    <p class="note2">Buttons, selection and the recommended-hook badge.</p></div>
  <div class="grp"><label>Clip colour</label><div class="opts" id="optClip"></div></div>
  <div class="grp"><label>Playhead</label><div class="opts" id="optHead"></div></div>

  <div class="grp"><label>Density</label><div class="opts" id="optDensity"></div>
    <p class="note2">How much fits on screen. Your display is short, so Compact shows more moments.</p></div>
  <div class="grp"><label>Text size</label><div class="opts" id="optText"></div></div>
  <div class="grp"><label>Timeline height</label><div class="opts" id="optTrack"></div></div>
  <div class="grp"><label>Moment columns</label><div class="opts" id="optCols"></div></div>

  <div class="grp"><label>Snapping</label><div class="opts" id="optSnap"></div>
    <p class="note2">Hold <b>Shift</b> to suspend it mid-drag, or press <b>N</b>.</p></div>
  <div class="grp"><label>Show</label><div class="opts" id="optShow"></div></div>

  <div class="grp"><label></label>
    <button class="sm" onclick="resetSettings()">Reset everything to defaults</button></div>
 </div>
</div>
<div class="help" id="help">
  <h3>Keys <span onclick="helpOverlay()">&times;</span></h3>
  <dl>
    <dt>Space</dt><dd>play / stop</dd>
    <dt>J K L</dt><dd>back 2s &middot; stop &middot; play, again to speed up</dd>
    <dt>I O</dt><dd>mark start / end of a custom clip</dd>
    <dt>S <i>or</i> Ctrl+B</dt><dd>split at the playhead</dd>
    <dt>Q W</dt><dd>cut off before / after the playhead</dd>
    <dt>Del</dt><dd>delete the selected clip <i>(or right-click it)</i></dd>
    <dt>Ctrl+Z / Y</dt><dd>undo / redo</dd>
    <dt>&larr; &rarr;</dt><dd>nudge 1s &middot; Shift for 10s</dd>
    <dt>Home / End</dt><dd>start / end of your short</dd>
    <dt>, .</dt><dd>slip the clip &mdash; same length, different take</dd>
    <dt>Shift+Z</dt><dd>fit the timeline, again to go back</dd>
    <dt>= &minus;</dt><dd>zoom in / out &middot; or Ctrl+wheel</dd>
    <dt>N</dt><dd>snapping on / off</dd>
    <dt>Shift <i>held</i></dt><dd>suspend snapping while dragging</dd>
    <dt>?</dt><dd>this card</dd>
  </dl>
</div>

<script>
var BASE = __BASE__, VIDEO = "__VID__", OUT = "__OUTNAME__";
var M = __MOMENTS__;
var SUG = __SUGGEST__;                      // from scripts/suggest_edit.py (Opus)
var SPLIT = __SPLIT__;                      // source second a 2nd defendant starts, or -1
var ROLE = {};
(SUG.roles || []).forEach(function(r){ ROLE[r.i] = r; });
var HOOK = (SUG.hook && SUG.hook.i !== undefined) ? SUG.hook.i : -1;
var curPlan = -1;
var KEY = "studio_" + VIDEO;

var clips = [];             // {a,b,label}  absolute SOURCE seconds
var hist = [], future = []; // undo / redo stacks of serialized clip lists
var sel = -1, pendingIn = null, showAll = false, stopAt = null;
var head = 0;                 // seconds into the assembled short; exists whether
                              // or not it is playing, so it can be dragged
var pps = 14;               // timeline pixels per second
var prevIdx = -1;           // index of clip being previewed, -1 = not previewing
var v = document.getElementById("v");

/* ---------------- themes ----------------
   Two palettes in and "I don't like those colors either" both times, so this
   stops being my guess: pick one and it sticks. Each is internally coordinated -
   surfaces, clip colour, playhead and accent move together, never one hue at a
   time. */
var THEMES = {
  graphite: {name:"Graphite", dot:"#0090ff", v:{
    bg:"#111111", panel:"#1b1b1b", card:"#222222", stage:"#1b1b1b",
    line:"#3a3a3a", line2:"#484848", line3:"#8a8a8a", lineH:"#5a5a5a",
    dim:"#afafaf", fg:"#dbdbdb", hi:"#f2f2f2", faint:"#8a8a8a",
    go:"#0090ff", go2:"#3b9eff", acc:"#70b8ff", onAcc:"#111111",
    warn:"#ff9592", gold:"#ffe629",
    clip:"#1c6961", clip2:"#145751", clipb:"#207e73",
    btn:"#262626", btnH:"#303030", btnA:"#1e1e1e",
    seg:"#242424", segH:"#2e2e2e", segA:"#383838",
    sunken:"#0d0d0d", chip:"#2a2a2a", row:"#191919", rowH:"#232323",
    sub:"#171717", pick:"#10304d", used:"#12211f", overBg:"#0d1a26",
    dangerBg:"#2a1212", dangerLine:"#7d3a34", dangerFg:"#f0cfca",
    hookBg:"#241f08", hookLine:"#5a4a1a", hookFg:"#f0e6c8"}},

  midnight: {name:"Midnight", dot:"#7c8cff", v:{
    bg:"#0b0d14", panel:"#12151f", card:"#191d2a", stage:"#12151f",
    line:"#262b3a", line2:"#343a4d", line3:"#7f889f", lineH:"#4a5266",
    dim:"#a6aec4", fg:"#dbe0ec", hi:"#f4f6fb", faint:"#7f889f",
    go:"#7c8cff", go2:"#9aa6ff", acc:"#b9c1ff", onAcc:"#0b0d14",
    warn:"#ff8fa3", gold:"#ffd166",
    clip:"#2b3f7a", clip2:"#1f2f5c", clipb:"#4c66b8",
    btn:"#1c2130", btnH:"#252b3d", btnA:"#161a26",
    seg:"#181d29", segH:"#222839", segA:"#2b3247",
    sunken:"#080a10", chip:"#222839", row:"#141824", rowH:"#1c2130",
    sub:"#0f121b", pick:"#1e2a55", used:"#16233f", overBg:"#111a30",
    dangerBg:"#2a1220", dangerLine:"#7d3450", dangerFg:"#f5ccd8",
    hookBg:"#2a2210", hookLine:"#5c4a1e", hookFg:"#f5e7c4"}},

  ember: {name:"Ember", dot:"#ff8f2b", v:{
    bg:"#0d0b0a", panel:"#171412", card:"#211d1a", stage:"#171412",
    line:"#332e29", line2:"#443d36", line3:"#8f857b", lineH:"#574f46",
    dim:"#b8ada3", fg:"#e6ded7", hi:"#f9f4f0", faint:"#8f857b",
    go:"#ff8f2b", go2:"#ffa552", acc:"#ffc48a", onAcc:"#1a1005",
    warn:"#ff7a6b", gold:"#ffd60a",
    clip:"#3d4a52", clip2:"#2c363c", clipb:"#6b8894",
    btn:"#231f1c", btnH:"#2e2925", btnA:"#1b1815",
    seg:"#1f1b18", segH:"#2b2622", segA:"#36302b",
    sunken:"#0a0908", chip:"#2b2622", row:"#191614", rowH:"#231f1c",
    sub:"#141110", pick:"#3d2a12", used:"#1c2429", overBg:"#2a1c0c",
    dangerBg:"#2e1310", dangerLine:"#82392f", dangerFg:"#f3d0c9",
    hookBg:"#2b2109", hookLine:"#63491a", hookFg:"#f7e8c2"}},

  studio: {name:"Studio", dot:"#4a9eff", v:{
    bg:"#1a1d21", panel:"#22262b", card:"#2b3036", stage:"#22262b",
    line:"#3a4048", line2:"#4b525b", line3:"#8b949e", lineH:"#5d656f",
    dim:"#aab3bd", fg:"#dde3ea", hi:"#f5f8fb", faint:"#8b949e",
    go:"#4a9eff", go2:"#6bb0ff", acc:"#a8cfff", onAcc:"#0b1220",
    warn:"#ff8b82", gold:"#f0c14b",
    clip:"#2d5468", clip2:"#22404f", clipb:"#5590ad",
    btn:"#2c3138", btnH:"#363c45", btnA:"#252a30",
    seg:"#272c33", segH:"#31373f", segA:"#3b424b",
    sunken:"#15181b", chip:"#31373f", row:"#212529", rowH:"#2a2f35",
    sub:"#1d2126", pick:"#1f3a55", used:"#1e3340", overBg:"#16283a",
    dangerBg:"#31191a", dangerLine:"#8a4340", dangerFg:"#f2d2d0",
    hookBg:"#302810", hookLine:"#6b5a26", hookFg:"#f7ebc8"}},

  void: {name:"Void", dot:"#e8e8e8", v:{
    bg:"#000000", panel:"#0a0a0a", card:"#131313", stage:"#000000",
    line:"#242424", line2:"#333333", line3:"#7d7d7d", lineH:"#454545",
    dim:"#a4a4a4", fg:"#d6d6d6", hi:"#f0f0f0", faint:"#7d7d7d",
    go:"#e8e8e8", go2:"#ffffff", acc:"#c8c8c8", onAcc:"#000000",
    warn:"#ff6b6b", gold:"#ffd400",
    clip:"#1a1a1a", clip2:"#101010", clipb:"#4f4f4f",
    btn:"#161616", btnH:"#212121", btnA:"#0d0d0d",
    seg:"#131313", segH:"#1e1e1e", segA:"#282828",
    sunken:"#000000", chip:"#1c1c1c", row:"#0d0d0d", rowH:"#171717",
    sub:"#080808", pick:"#262626", used:"#141414", overBg:"#141414",
    dangerBg:"#1e0c0c", dangerLine:"#6b2b2b", dangerFg:"#efc7c7",
    hookBg:"#1c1704", hookLine:"#4a3d10", hookFg:"#efe2b8"}}
};
var ACCENTS = {
  blue:{n:"Blue", go:"#0090ff", go2:"#3b9eff", acc:"#70b8ff", onAcc:"#08121f"},
  amber:{n:"Amber", go:"#ff9f0a", go2:"#ffb340", acc:"#ffd08a", onAcc:"#1a1005"},
  violet:{n:"Violet", go:"#a78bfa", go2:"#c4b5fd", acc:"#ddd6fe", onAcc:"#150f24"},
  green:{n:"Green", go:"#30d158", go2:"#5ee27c", acc:"#a7f3bf", onAcc:"#052012"},
  red:{n:"Red", go:"#ff453a", go2:"#ff6b62", acc:"#ffb3ae", onAcc:"#200604"},
  white:{n:"White", go:"#e8e8e8", go2:"#ffffff", acc:"#c8c8c8", onAcc:"#000000"}
};
var CLIPC = {
  teal:{n:"Teal", clip:"#1c6961", clip2:"#145751", clipb:"#207e73"},
  slate:{n:"Slate", clip:"#33414d", clip2:"#26313a", clipb:"#5b7285"},
  indigo:{n:"Indigo", clip:"#2b3f7a", clip2:"#1f2f5c", clipb:"#4c66b8"},
  plum:{n:"Plum", clip:"#4a2c56", clip2:"#372040", clipb:"#7b4d8c"},
  olive:{n:"Olive", clip:"#4a4a26", clip2:"#38381c", clipb:"#7f7f3f"},
  grey:{n:"Grey", clip:"#2e2e2e", clip2:"#232323", clipb:"#5f5f5f"}
};
var HEADC = {
  red:{n:"Red", warn:"#ff6b6b"}, pink:{n:"Pink", warn:"#ff9592"},
  white:{n:"White", warn:"#ffffff"}, yellow:{n:"Yellow", warn:"#ffd400"},
  cyan:{n:"Cyan", warn:"#5ee0ff"}
};
var DENSITY = {compact:{n:"Compact", pad:0.82}, normal:{n:"Normal", pad:1},
               roomy:{n:"Roomy", pad:1.18}};
var TEXTSZ  = {s:{n:"Small", px:13}, m:{n:"Normal", px:14}, l:{n:"Large", px:15.5},
               xl:{n:"Larger", px:17}};
var TRACKH  = {auto:{n:"Auto", px:0}, s:{n:"Short", px:62}, m:{n:"Normal", px:88},
               l:{n:"Tall", px:120}, xl:{n:"Tallest", px:160}};
var COLS    = {auto:{n:"Auto", px:330}, wide:{n:"Fewer, wider", px:460},
               tight:{n:"More, narrower", px:250}};

var S = {theme:"ember", accent:"blue", clipc:"teal", headc:"red",
         density:"normal", text:"m", trackh:"auto", cols:"auto",
         snap:"on", showRoles:true, showWhy:true};

function saveS(){ try{ localStorage.setItem("studio_settings", JSON.stringify(S)); }catch(e){} }
function applyAll(){
  applyTheme(S.theme, true);
  var r = document.documentElement, a = ACCENTS[S.accent], c = CLIPC[S.clipc], h = HEADC[S.headc];
  if (a){ r.style.setProperty("--go",a.go); r.style.setProperty("--go2",a.go2);
          r.style.setProperty("--acc",a.acc); r.style.setProperty("--onAcc",a.onAcc); }
  if (c){ r.style.setProperty("--clip",c.clip); r.style.setProperty("--clip2",c.clip2);
          r.style.setProperty("--clipb",c.clipb); }
  if (h){ r.style.setProperty("--warn",h.warn); }
  r.style.setProperty("--pad", DENSITY[S.density].pad);
  document.body.style.fontSize = TEXTSZ[S.text].px + "px";
  var tk = document.getElementById("track");
  if (tk){
    var th = TRACKH[S.trackh];
    // inline beats the @media rule; "auto" clears it and lets the screen decide
    tk.style.height = (th && th.px) ? th.px + "px" : "";
    var st = document.getElementById("strip");
    if (st) st.style.height = (th && th.px) ? (th.px - 36) + "px" : "";
  }
  r.style.setProperty("--colW", COLS[S.cols].px + "px");
  snapOn = S.snap === "on";
  document.body.classList.toggle("noRoles", !S.showRoles);
  document.body.classList.toggle("noWhy", !S.showWhy);
  saveS(); renderTrack(); renderSettings();
}
function setS(k, v){ S[k] = v; applyAll(); }
function openSettings(){ document.getElementById("sheet").classList.add("on"); renderSettings(); }
function closeSettings(){ document.getElementById("sheet").classList.remove("on"); }
function resetSettings(){
  S = {theme:"ember", accent:"blue", clipc:"teal", headc:"red", density:"normal",
       text:"m", trackh:"auto", cols:"auto", snap:"on", showRoles:true, showWhy:true};
  applyAll(); toast("back to defaults");
}
function optRow(id, obj, cur, key, dotKey){
  var el = document.getElementById(id); if (!el) return;
  var h = "";
  for (var k in obj){
    var o = obj[k], dot = dotKey ? o[dotKey] : null;
    h += "<button class='" + (k===cur?"on":"") + "' onclick='setS(\"" + key + "\",\"" + k + "\")'>"
      +  (dot ? "<i style='background:" + dot + "'></i>" : "") + (o.n || o.name) + "</button>";
  }
  el.innerHTML = h;
}
function renderSettings(){
  var names = {}; for (var k in THEMES) names[k] = {n:THEMES[k].name, dot:THEMES[k].v.bg};
  optRow("optTheme", names, S.theme, "theme", "dot");
  optRow("optAccent", ACCENTS, S.accent, "accent", "go");
  optRow("optClip", CLIPC, S.clipc, "clipc", "clipb");
  optRow("optHead", HEADC, S.headc, "headc", "warn");
  optRow("optDensity", DENSITY, S.density, "density");
  optRow("optText", TEXTSZ, S.text, "text");
  optRow("optTrack", TRACKH, S.trackh, "trackh");
  optRow("optCols", COLS, S.cols, "cols");
  optRow("optSnap", {on:{n:"On"}, off:{n:"Off"}}, S.snap, "snap");
  var el = document.getElementById("optShow");
  if (el) el.innerHTML =
      "<button class='" + (S.showRoles?"on":"") + "' onclick='S.showRoles=!S.showRoles;applyAll()'>Role tags</button>"
    + "<button class='" + (S.showWhy?"on":"") + "' onclick='S.showWhy=!S.showWhy;applyAll()'>Why lines</button>";
}
var theme = "ember";
function applyTheme(k, fromSettings){
  var t = THEMES[k]; if (!t) return;
  theme = k;
  var r = document.documentElement;
  for (var key in t.v) r.style.setProperty("--" + key, t.v[key]);
  if (!fromSettings){ S.theme = k; applyAll(); }   // re-apply the overrides on top
}


/* ---------------- history: every mutation is reversible ---------------- */
function snap(){ return JSON.stringify(clips); }
function push(){ hist.push(snap()); if (hist.length > 200) hist.shift(); future = []; }
function undo(){
  if (!hist.length){ toast("nothing to undo"); return; }
  future.push(snap()); clips = JSON.parse(hist.pop());
  if (sel >= clips.length) sel = clips.length - 1;
  if (prevIdx >= clips.length) prevIdx = -1;
  render(); toast("undone");
}
function redo(){
  if (!future.length){ toast("nothing to redo"); return; }
  hist.push(snap()); clips = JSON.parse(future.pop());
  if (sel >= clips.length) sel = clips.length - 1;
  if (prevIdx >= clips.length) prevIdx = -1;
  render(); toast("redone");
}

/* ---------------- time helpers ---------------- */
function fmt(t){ var m = Math.floor(t/60), s = t % 60;
  return m + ":" + (s < 10 ? "0" : "") + s.toFixed(1); }
function fmtS(t){ var m = Math.floor(t/60), s = Math.floor(t%60);
  return m + ":" + (s < 10 ? "0" : "") + s; }
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
function dur(){ var t = 0; for (var i=0;i<clips.length;i++) t += clips[i].b - clips[i].a; return t; }
function srcNow(){ return (v.currentTime || 0) + BASE; }
function seekSrc(t){ v.currentTime = Math.max(0, t - BASE); }

/* ---------------- player ---------------- */
/* One transport, not two. There used to be a play button under the video that
   ran the raw hearing and a second one in the dock that ran the assembled short;
   pressing the first left the red line frozen, so the two clocks disagreed and
   the line went stale. Now a single button plays whichever surface was touched
   last - the timeline, or the hearing scrubber. */
var mode = "short";                 // "short" = the edit, "source" = the hearing
function setMode(m){ if (mode !== m){ mode = m; syncTransport(); } }
function transport(){
  if (!v.paused){
    if (prevIdx >= 0) stopShort(); else { v.pause(); stopAt = null; }
    syncTransport(); return;
  }
  if (mode === "short" && clips.length) playShort();
  else { prevIdx = -1; stopAt = null; v.play(); }
  syncTransport();
}
function syncTransport(){
  var b = document.getElementById("bprev");
  if (!b) return;
  b.innerHTML = !v.paused ? "&#10074;&#10074; Stop"
              : (mode === "short" && clips.length ? "&#9654; Play short"
                                                  : "&#9654; Play hearing");
  var ph = document.getElementById("ph");
  if (ph) ph.style.opacity = (mode === "short") ? "1" : ".32";
}
function togglePlay(){ transport(); }
function nudge(d){ setMode("source"); prevIdx = null_prev(); v.currentTime = Math.max(0, (v.currentTime||0) + d); }
function null_prev(){ stopAt = null; return -1; }
// Play one range and stop at its end.
// stopAt used to be armed before the seek landed: if the video happened to sit
// past the new end already, the very next timeupdate still carried the OLD
// currentTime, the stop fired immediately and it froze on a frame near the end
// instead of playing the run-up. Arm it on 'seeked' instead.
function playRange(a, b){
  setMode("source");
  prevIdx = -1; stopAt = null;
  var go = function(){
    v.removeEventListener("seeked", go);
    stopAt = b;
    v.play();
  };
  v.addEventListener("seeked", go);
  seekSrc(a);
  // if it was already sitting exactly there, no 'seeked' fires
  if (Math.abs(v.currentTime - (a - BASE)) < 0.05){ v.removeEventListener("seeked", go); stopAt = b; v.play(); }
}
// Adjusting the START previews forward from it. Adjusting the END previews the
// run-UP to it - Nathan: "instead of starting from the end the video should show
// me the last 5 sec so I could actually see how it's ending".
var TAIL_S = 5.0, LEAD_S = 3.0;
function previewStart(a, b){ playRange(a, Math.min(b, a + LEAD_S)); }
function previewEnd(a, b){ playRange(Math.max(a, b - TAIL_S), b); }
v.addEventListener("play",  syncTransport);
v.addEventListener("pause", syncTransport);

var sc = document.getElementById("scrub"), dragScrub = false;
sc.addEventListener("input", function(){
  dragScrub = true; prevIdx = -1; stopAt = null; setMode("source");
  if (v.duration) v.currentTime = v.duration * (sc.value / 2000);
});
sc.addEventListener("change", function(){ dragScrub = false; });

v.addEventListener("timeupdate", function(){
  document.getElementById("now").textContent = fmt(v.currentTime || 0);
  if (v.duration && !dragScrub){
    var f = v.currentTime / v.duration;
    sc.value = Math.round(f * 2000);
    sc.style.setProperty("--pct", (f*100).toFixed(2) + "%");
  }
  if (stopAt !== null && srcNow() >= stopAt){ v.pause(); stopAt = null; }
  if (prevIdx >= 0) previewTick();
});

/* ---------------- the playhead ---------------- */
function headToSrc(t){
  var acc = 0;
  for (var k=0;k<clips.length;k++){
    var len = clips[k].b - clips[k].a;
    if (t < acc + len || k === clips.length - 1)
      return {k:k, t:clips[k].a + Math.max(0, Math.min(len, t - acc))};
    acc += len;
  }
  return null;
}
function srcToHead(){
  if (prevIdx < 0 || !clips[prevIdx]) return head;
  var acc = 0;
  for (var k=0;k<prevIdx;k++) acc += clips[k].b - clips[k].a;
  return acc + Math.max(0, srcNow() - clips[prevIdx].a);
}
function setHead(t, seekToo){
  setMode("short");
  head = Math.max(0, Math.min(dur(), t));
  if (seekToo){
    var r = headToSrc(head);
    if (r){ prevIdx = -1; stopAt = null; seekSrc(r.t); sel = r.k; }
  }
  drawPlayhead(); renderDetail();
}
// dragging the red line, or clicking the ruler above the clips
var headDrag = false;
function headDown(e){
  e.preventDefault(); e.stopPropagation();
  if (!clips.length) return;
  headDrag = true;
  headMove(e);
  window.addEventListener("pointermove", headMove);
  window.addEventListener("pointerup", headUp);
}
function headMove(e){
  if (!headDrag) return;
  var strip = document.getElementById("strip").getBoundingClientRect();
  setHead(snapHead((e.clientX - strip.left) / pps, e.shiftKey), true);
}
function headUp(){
  headDrag = false;
  window.removeEventListener("pointermove", headMove);
  window.removeEventListener("pointerup", headUp);
}

/* ---------------- preview: watch the EDIT, not the source ---------------- */
function playing(){ return prevIdx >= 0 && !v.paused; }
function playShort(){
  if (!clips.length){ toast("nothing on the timeline yet"); return; }
  if (prevIdx >= 0){ stopShort(); return; }         // same button stops it
  if (head >= dur() - 0.05) head = 0;               // at the end, start over
  var r = headToSrc(head);
  if (!r) return;
  prevIdx = r.k; sel = r.k; stopAt = null;
  seekSrc(r.t); v.play(); render();
}
function stopShort(){
  head = srcToHead();                               // leave the line where it stopped
  prevIdx = -1; stopAt = null; v.pause(); render();
}
function previewTick(){
  var c = clips[prevIdx];
  if (!c){ prevIdx = -1; drawPlayhead(); return; }
  var t = srcNow();
  if (t >= c.b - 0.03 || t < c.a - 1.5){
    if (prevIdx + 1 < clips.length){
      prevIdx++; sel = prevIdx; seekSrc(clips[prevIdx].a); render();
    } else { head = dur(); prevIdx = -1; v.pause(); toast("end of short"); render(); }
  }
  head = srcToHead();
  drawPlayhead();
}
function drawPlayhead(){
  var ph = document.getElementById("ph");
  if (!clips.length){ ph.style.display = "none"; return; }
  // prevIdx can outlive the clip it points at - undo restores a shorter list
  if (prevIdx >= clips.length) prevIdx = -1;
  var off = (prevIdx >= 0) ? srcToHead() : head;
  off = Math.max(0, Math.min(dur(), off));
  ph.style.display = "block";
  ph.style.left = (8 + off*pps - document.getElementById("track").scrollLeft) + "px";
  syncTransport();
  var hp = document.getElementById("hpos");
  if (hp) hp.textContent = fmt(off) + " / " + fmt(dur());
}

/* ---------------- building the timeline ---------------- */
function addClip(a, b, label){
  setMode("short");
  push();
  clips.push({a:a, b:b, label:label || "clip"});
  sel = clips.length - 1; render();
}
function markIn(){ setMode("source"); pendingIn = srcNow(); document.getElementById("pin").textContent = fmt(pendingIn - BASE); }
function markOut(){
  if (pendingIn === null){ toast("press Start first"); return; }
  var b = srcNow();
  if (b <= pendingIn + 0.3){ toast("End must be after Start"); return; }
  addClip(pendingIn, b, "custom");
  pendingIn = null; document.getElementById("pin").textContent = "—";
}
function addMoment(i){
  var m = M[i];
  addClip(momA(i), momB(i), m.label || ("moment " + (i+1)));
  toast("added — " + (m.label || "moment"));
}
function del(i){
  if (i < 0 || i >= clips.length) return;
  push(); clips.splice(i,1);
  if (sel >= clips.length) sel = clips.length - 1;
  prevIdx = -1; render(); toast("deleted — Ctrl+Z brings it back");
}
function dupe(i){
  push();
  clips.splice(i+1, 0, {a:clips[i].a, b:clips[i].b, label:clips[i].label});
  sel = i+1; render();
}
function move(i, d){
  var j = i + d;
  if (j < 0 || j >= clips.length) return;
  push();
  var t = clips[j]; clips[j] = clips[i]; clips[i] = t;
  sel = j; render();
}
function trim(i, edge, d){
  var c = clips[i]; if (!c) return;
  push();
  if (edge === "a") c.a = Math.min(Math.max(0, c.a + d), c.b - 0.4);
  else             c.b = Math.max(c.b + d, c.a + 0.4);
  render();
  if (edge === "a") previewStart(c.a, c.b); else previewEnd(c.a, c.b);
}
// split, then delete a half - the only way a section comes out of the MIDDLE
function splitHere(){
  var t = srcNow();
  for (var k=0;k<clips.length;k++){
    var c = clips[k];
    if (t > c.a + 0.4 && t < c.b - 0.4){
      push();
      clips.splice(k+1, 0, {a:t, b:c.b, label:c.label});
      c.b = t; sel = k+1; prevIdx = -1; render();
      toast("split — delete either half to cut that bit out");
      return;
    }
  }
  toast("put the playhead inside a clip first");
}
// Nathan: "delete video segments when my mouse is over it and I right click".
// The browser menu is suppressed over the strip so the gesture is unambiguous.
// Undo still holds the clip, and the toast says so.
function rightDelete(e, i){
  e.preventDefault(); e.stopPropagation();
  drag = null;
  del(i);
  return false;
}
function clearAll(){
  if (!clips.length) return;
  push(); clips = []; sel = -1; prevIdx = -1; pendingIn = null; render();
  toast("cleared — Ctrl+Z brings it back");
}
function selectClip(i){
  sel = i;
  playRange(clips[i].a, clips[i].b);
  setMode("short");                 // playRange flips to source; this is the edit
  var acc = 0;
  for (var k=0;k<i;k++) acc += clips[k].b - clips[k].a;
  head = acc;
  render();
}

/* ---------------- drag: trim edges, reorder blocks ---------------- */
var drag = null;
function onDown(e, i, mode){
  if (e.button !== 0) return;          // right button is delete, not drag
  e.preventDefault(); e.stopPropagation();
  drag = {i:i, mode:mode, x0:e.clientX, moved:false,
          a0:clips[i].a, b0:clips[i].b, target:i};
  sel = i; prevIdx = -1; render();
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}
function onMove(e){
  if (!drag) return;
  var dx = e.clientX - drag.x0;
  if (Math.abs(dx) > 4) drag.moved = true;
  var c = clips[drag.i];
  if (drag.mode === "a"){
    c.a = Math.min(Math.max(0, snapEdge(drag.a0 + dx/pps, drag.i, e.shiftKey)), c.b - 0.4);
  } else if (drag.mode === "b"){
    c.b = Math.max(snapEdge(drag.b0 + dx/pps, drag.i, e.shiftKey), c.a + 0.4);
  } else {
    // Reorder. The landing index is how many OTHER blocks the pointer has passed
    // the midpoint of - counting the dragged block itself put it two slots along
    // instead of one, because the splice removes it before re-inserting.
    var blocks = document.querySelectorAll(".blk"), t = 0;
    for (var k=0;k<blocks.length;k++){
      if (k === drag.i) continue;
      var r = blocks[k].getBoundingClientRect();
      if (e.clientX > r.left + r.width/2) t++;
    }
    drag.target = t;
    for (var k2=0;k2<blocks.length;k2++){
      blocks[k2].classList.toggle("drag", k2 === drag.i);
      var rr = blocks[k2].getBoundingClientRect();
      blocks[k2].style.outline = (k2 !== drag.i && e.clientX > rr.left && e.clientX < rr.right)
        ? "2px dashed var(--acc)" : "";
    }
  }
  if (drag.mode !== "move") renderTrack();
}
function onUp(){
  window.removeEventListener("pointermove", onMove);
  window.removeEventListener("pointerup", onUp);
  if (!drag) return;
  var d = drag; drag = null;
  var bl = document.querySelectorAll(".blk");
  for (var q=0;q<bl.length;q++){ bl[q].classList.remove("drag"); bl[q].style.outline = ""; }
  if (!d.moved){ selectClip(d.i); return; }
  if (d.mode === "move"){
    if (d.target !== d.i){
      push();                              // order before the move, so undo restores it
      var c = clips.splice(d.i, 1)[0];
      clips.splice(d.target, 0, c);
      sel = d.target;
    }
  } else {
    // edge drag mutated live for feedback; record the pre-drag state for undo
    var c2 = clips[d.i], na = c2.a, nb = c2.b;
    c2.a = d.a0; c2.b = d.b0; push(); c2.a = na; c2.b = nb;
  }
  render();
}

/* ---------------- drag a moment onto the timeline ---------------- */
// He asked to "drag what I want to a layout of boxes on the timeline". So the
// strip opens a real gap under the pointer and the clip lands exactly there,
// rather than always being appended to the end.
var dragMom = -1, dropIdx = -1, dragShown = false;

function dragMoment(e, i){
  dragMom = i; dropIdx = clips.length; dragShown = false;
  try{ e.dataTransfer.effectAllowed = "copy";
       e.dataTransfer.setData("text/plain", String(i)); }catch(err){}
  e.target.classList.add("dragging");
}
function endDrag(){
  dragMom = -1; dropIdx = -1; dragShown = false;
  document.getElementById("track").classList.remove("over");
  document.querySelectorAll(".m.dragging").forEach(function(el){ el.classList.remove("dragging"); });
  renderTrack();
}
function slotAt(x){
  var blocks = document.querySelectorAll("#strip .blk"), t = blocks.length;
  for (var k=0;k<blocks.length;k++){
    var r = blocks[k].getBoundingClientRect();
    if (x < r.left + r.width/2){ t = k; break; }
  }
  return t;
}
function overTrack(e){
  if (dragMom < 0) return;
  e.preventDefault();
  try{ e.dataTransfer.dropEffect = "copy"; }catch(err){}
  document.getElementById("track").classList.add("over");
  var t = slotAt(e.clientX);
  // must also draw the first time in, or an empty timeline (dropIdx already 0)
  // never opens its box
  if (t !== dropIdx || !dragShown){ dropIdx = t; dragShown = true; renderTrack(); }
}
function leaveTrack(e){
  var r = document.getElementById("track").getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom){
    document.getElementById("track").classList.remove("over");
    dropIdx = -1; renderTrack();
  }
}
function dropMoment(e){
  if (dragMom < 0) return;
  e.preventDefault();
  var m = M[dragMom], at = dropIdx < 0 ? clips.length : dropIdx;
  push();
  clips.splice(at, 0, {a:momA(dragMom), b:momB(dragMom), label:m.label || "moment"});
  sel = at; prevIdx = -1;
  var name = m.label || "moment";
  endDrag(); render();
  toast("dropped at " + (at+1) + " — " + name);
}

/* ---------------- suggested cuts ---------------- */
// keep_s / trim_from come from suggest_edit.py: "end" means drop the tail and
// keep the front, "start" means drop the front and keep the tail.
function planRange(c){
  var m = M[c.i];
  // a and b are written by suggest_edit AFTER snapping to the audio, so prefer
  // them; keep_s/trim_from are only the pre-snap fallback for older files
  if (c.a !== undefined && c.b !== undefined)
    return {a:c.a, b:c.b, label:m.label, why:c.why, snap:c.snap};
  var span = m.end - m.start, keep = Math.min(c.keep_s || span, span);
  if (c.trim_from === "none")  return {a:m.start, b:m.end, label:m.label, why:c.why};
  if (c.trim_from === "start") return {a:m.end - keep, b:m.end, label:m.label, why:c.why};
  return {a:m.start, b:m.start + keep, label:m.label, why:c.why};
}
function loadPlan(k){
  var pl = SUG.plans[k]; if (!pl) return;
  setMode("short");
  push();
  clips = pl.clips.map(planRange);
  curPlan = k; sel = 0; prevIdx = -1; userZoom = false;
  render();
  toast(pl.name + " loaded — " + pl.actual_s + "s. Ctrl+Z to undo");
}
function renderSug(){
  var el = document.getElementById("sug");
  if (!SUG.plans || !SUG.plans.length){ el.style.display = "none"; return; }
  document.getElementById("sugby").textContent = "Opus";
  var h = "<div class='plans'>";
  for (var k=0;k<SUG.plans.length;k++){
    var pl = SUG.plans[k];
    h += "<button class='plan" + (k===curPlan?" on":"") + "' onclick='loadPlan(" + k + ")'>"
      +  "<b>" + esc(pl.name) + "</b><span>" + pl.clips.length + " clips · "
      +  Math.round(pl.actual_s) + "s</span></button>";
  }
  h += "</div>";
  if (curPlan >= 0 && SUG.plans[curPlan])
    h += "<div class='sugwhy'><b>Why:</b> " + esc(SUG.plans[curPlan].why) + "</div>";
  if (SPLIT > 0)
    h += "<div class='warnline'><b>TWO DEFENDANTS IN THIS FILE</b><br>"
      +  "A second case starts at " + fmtS(SPLIT - BASE)
      +  ". Moments past it are marked <span class='rl rl-case2'>2nd case</span> — "
      +  "keep a short to one defendant, and the long-form should end there.</div>";
  if (HOOK >= 0 && M[HOOK] && SUG.hook.why)
    h += "<div class='hookline'><b>BEST HOOK &middot; " + esc(M[HOOK].label) + "</b><br>"
      +  esc(SUG.hook.why) + "</div>";
  el.innerHTML = h;
}

/* ---------------- CapCut-compatible editing keys ----------------
   Bindings read out of the CapCut 9.1.0 shipped keymaps in
   %LOCALAPPDATA%\CapCut\User Data\Config\Shortcut\ - identical across both
   shipped presets, so they are stable:
     Space play/pause · J/K/L transport · I/O range · Q/W cut left/right of the
     playhead · Home/End · Shift+Z zoom fit · Ctrl+wheel zoom · Ctrl suspends snap
   Ctrl+B (split) is from the CapCut web editor bundle.

   Q and W are the two that earn their place here. In a multi-track NLE they
   ripple-trim; with one track and no gaps possible they simply move the near
   edge of the clip under the playhead to the playhead - which is exactly the
   "cut off everything before/after this point" move.                        */
function cutLeft(){                                  // Q - drop what is BEFORE
  var r = headToSrc(head); if (!r) { toast("nothing under the playhead"); return; }
  var c = clips[r.k];
  if (r.t <= c.a + 0.2){ toast("playhead is at the start already"); return; }
  if (r.t >= c.b - 0.2){ toast("that would leave nothing - use W or delete it"); return; }
  push();
  c.a = r.t; sel = r.k;
  // the edit shortened ahead of the playhead, so the playhead now sits exactly
  // on this clip's new start rather than drifting into it
  var acc = 0;
  for (var i=0;i<r.k;i++) acc += clips[i].b - clips[i].a;
  head = acc;
  render();
  toast("cut off everything before the playhead");
}
function cutRight(){                                 // W - drop what is AFTER
  var r = headToSrc(head); if (!r) { toast("nothing under the playhead"); return; }
  var c = clips[r.k];
  if (r.t <= c.a + 0.2){                            // nothing would be left
    del(r.k); toast("clip removed"); return;
  }
  if (r.t >= c.b - 0.2){ toast("playhead is at the end already"); return; }
  push(); c.b = r.t; sel = r.k; render();           // playhead stays put, now on the join
  toast("cut off everything after the playhead");
}

/* Slip: move the source window without changing how long the clip runs. Worth
   having precisely because every clip here is a range into ONE source file,
   which is what a slip edit operates on. */
function slip(d){
  if (sel < 0 || !clips[sel]) { toast("select a clip first"); return; }
  var c = clips[sel], len = c.b - c.a;
  if (c.a + d < 0) return;
  push(); c.a += d; c.b = c.a + len; render();
  previewStart(c.a, c.b);
  toast("slipped " + (d > 0 ? "+" : "") + d + "s - same length, different take");
}

/* Snapping, in SCREEN PIXELS - never seconds. A seconds threshold makes the
   magnet's strength scale with zoom; Shotcut shipped that bug and the symptom
   was "the edge of a clip gets stuck at the playhead and no further expansion is
   possible" (fixed v18.09). Measured constants from the shipped tools:
     Shotcut SNAP 10px / SNAP_TRIM 4px · tldraw 8 · freecut 8 · pireel 8
   Trimming gets the tighter magnet because it needs more precision than moving.

   The clamp is mine and this timeline needs it: at 2 px/s a 60s edit is only
   120px wide, so an 8px magnet would cover 4 seconds - 6.7% of the whole edit.
   Kdenlive kills snapping at high zoom; this kills it at low zoom, same idea.

   SHIFT suspends it, following Kdenlive and OpenCut. Not Ctrl (that is
   right-click on macOS) and not Alt (steals the Windows menu). */
var SNAP_MOVE_PX = 8, SNAP_TRIM_PX = 4, SNAP_MAX_S = 0.5;
var SNAP_RELEASE = 1.5;            // hysteresis, or it chatters on the boundary
var snapOff = false, snapOn = true;
function snapRadius(px){ return Math.min(px / Math.max(pps, 0.001), SNAP_MAX_S); }
function toggleSnap(){ snapOn = !snapOn; toast(snapOn ? "snapping on" : "snapping off"); renderTrack(); }

// Targets in a gapless single track are the playhead, t=0 and the end - never
// clip-to-clip, because every boundary is already coincident with its neighbour.
function snapHead(t, held){
  if (!snapOn || snapOff || held) return t;
  var r = snapRadius(SNAP_MOVE_PX), best = t, bestD = r, acc = 0;
  for (var k=0;k<=clips.length;k++){
    var d = Math.abs(t - acc);
    if (d < bestD){ bestD = d; best = acc; }
    if (k === clips.length) break;
    acc += clips[k].b - clips[k].a;
  }
  return best;
}
// Edge-trim snaps to the PLAYHEAD - the one target that matters here.
function snapEdge(srcT, k, held){
  if (!snapOn || snapOff || held || !clips[k]) return srcT;
  var acc = 0;
  for (var i=0;i<k;i++) acc += clips[i].b - clips[i].a;
  var len = clips[k].b - clips[k].a;
  if (head < acc - len || head > acc + 2 * len) return srcT;
  var underHead = clips[k].a + (head - acc);        // source second at the playhead
  return Math.abs(srcT - underHead) < snapRadius(SNAP_TRIM_PX) ? underHead : srcT;
}

/* Transport. HTML video cannot play backwards, so J steps back rather than
   shuttling in reverse - the one place this is an approximation of CapCut, not
   a match. Repeated L speeds up, K resets and pauses. */
function shuttle(dir){
  if (dir === 0){ v.pause(); v.playbackRate = 1; stopAt = null; syncTransport(); return; }
  if (dir < 0){ setMode("short"); setHead(head - 2, true); return; }
  if (v.paused) transport(); else v.playbackRate = Math.min(4, v.playbackRate * 2);
}
function helpOverlay(){
  var el = document.getElementById("help");
  el.style.display = el.style.display === "block" ? "none" : "block";
}

/* ---------------- render ---------------- */
var userZoom = false;
// Auto-fit on every draw until he zooms deliberately. Adding clips used to push
// the strip past the right edge of the track and leave him scrolling for it.
function autoFit(){
  if (userZoom) return;
  var w = document.getElementById("track").clientWidth - 30, d = dur();
  if (d > 0 && w > 0) pps = Math.max(2, Math.min(90, w/d));
}
function fitZoom(){ userZoom = false; renderTrack(); }
var lastPps = 0;
function fitToggle(){
  if (!userZoom && lastPps){ userZoom = true; pps = lastPps; renderTrack(); return; }
  lastPps = pps; fitZoom();
}
function zoom(f){ userZoom = true; pps = Math.max(1.5, Math.min(140, pps*f)); renderTrack(); }

function renderTrack(){
  autoFit();
  var strip = document.getElementById("strip"), h = "";
  var dragging = dragMom >= 0;
  // the hint overlay only when there is nothing at all going on
  document.getElementById("gap").style.display = (clips.length || dragging) ? "none" : "none";

  for (var i=0;i<=clips.length;i++){
    // a gap opens at the landing position while a moment is being dragged over
    if (dragging && dropIdx === i)
      h += "<div class='slot open'>drop</div>";
    if (i === clips.length) break;
    var c = clips[i], len = c.b - c.a, w = Math.max(20, len*pps);
    h += "<div class='blk" + (i===sel?" sel":"") + "' style='width:" + w.toFixed(1) + "px'"
      +  " onpointerdown='onDown(event," + i + ",\"move\")'"
      +  " oncontextmenu='return rightDelete(event," + i + ")'"
      +  " title='" + esc(c.label) + " · " + len.toFixed(1) + "s  —  right-click to delete'>"
      +  "<span class='lb'>" + (w>70 ? esc(c.label) + "<br>" + len.toFixed(1) + "s" : len.toFixed(0)+"s") + "</span>"
      +  "<div class='hnd l' onpointerdown='onDown(event," + i + ",\"a\")'></div>"
      +  "<div class='hnd r' onpointerdown='onDown(event," + i + ",\"b\")'></div></div>";
  }
  // an empty timeline shows the boxes to aim at, so it reads as a place to drop
  if (!clips.length && !dragging)
    h = "<div class='slot rest'>drag a moment here</div>"
      + "<div class='slot rest'>then another</div>"
      + "<div class='slot rest'>&hellip;</div>";
  strip.innerHTML = h;

  var rl = "", d = dur(), step = pps > 30 ? 1 : (pps > 12 ? 5 : 10);
  for (var t=0; t<=d; t+=step)
    rl += "<span class='tick' style='left:" + (t*pps).toFixed(1) + "px'>" + fmtS(t) + "</span>";
  document.getElementById("ruler").innerHTML = rl;
  // warn on the timeline itself if any clip crosses into the second case
  var mixed = false, has1 = false, has2 = false;
  for (var q=0;q<clips.length;q++){
    if (SPLIT > 0 && clips[q].a >= SPLIT) has2 = true; else has1 = true;
  }
  mixed = has1 && has2;
  var mw = document.getElementById("mixwarn");
  if (mw){ mw.style.display = mixed ? "inline" : "none"; }
  document.getElementById("ruler").style.width = Math.max(0, d*pps) + "px";
  var sz = document.getElementById("szone");
  sz.style.width = Math.max(0, d*pps) + "px";
  sz.style.display = clips.length ? "block" : "none";

  var tot = document.getElementById("total"), n = clips.length;
  tot.textContent = n ? (n + (n===1?" clip · ":" clips · ") + d.toFixed(1) + "s"
                         + (d > 60 ? "  — OVER 60s" : "")) : "empty";
  tot.className = "tot" + (d > 60 ? " over" : "");
  drawPlayhead();
}
document.getElementById("track").addEventListener("scroll", drawPlayhead);
window.addEventListener("resize", function(){ renderTrack(); });

function renderDetail(){
  var el = document.getElementById("det");
  if (sel < 0 || !clips[sel]){
    el.innerHTML = "<span class='faint'>Click a block to trim it · drag its edges · drag it sideways to reorder"
      + " · <kbd>Del</kbd> removes · <kbd>Ctrl</kbd>+<kbd>Z</kbd> undoes anything</span>";
    return;
  }
  var c = clips[sel];
  el.innerHTML =
      "<b class='num' style='font-size:12.5px'>#" + (sel+1) + " " + esc(c.label)
    + " <span class='faint'>" + (c.b-c.a).toFixed(1) + "s</span></b>"
    + "<span class='faint'>start</span><span class='seg'>"
    + "<button onclick='trim(" + sel + ",\"a\",-3)'>&minus;3</button>"
    + "<button onclick='trim(" + sel + ",\"a\",-1)'>&minus;1</button>"
    + "<button onclick='trim(" + sel + ",\"a\",1)'>+1</button>"
    + "<button onclick='trim(" + sel + ",\"a\",3)'>+3</button></span>"
    + "<span class='faint'>end</span><span class='seg'>"
    + "<button onclick='trim(" + sel + ",\"b\",-3)'>&minus;3</button>"
    + "<button onclick='trim(" + sel + ",\"b\",-1)'>&minus;1</button>"
    + "<button onclick='trim(" + sel + ",\"b\",1)'>+1</button>"
    + "<button onclick='trim(" + sel + ",\"b\",3)'>+3</button></span>"
    + "<button class='sm' onclick='selectClip(" + sel + ")'>&#9654; play</button>"
    + "<button class='sm' onclick='move(" + sel + ",-1)'>&larr;</button>"
    + "<button class='sm' onclick='move(" + sel + ",1)'>&rarr;</button>"
    + "<button class='sm' onclick='dupe(" + sel + ")'>duplicate</button>"
    + "<button class='sm dngr' onclick='del(" + sel + ")'>delete</button>"
    + (c.why ? "<div class='whyline'><b>Why this is here:</b> " + esc(c.why)
               + (c.snap ? " <span class='faint'>&mdash; cut snapped: " + esc(c.snap) + "</span>" : "")
               + "</div>" : "");
}

/* --- a moment can be trimmed BEFORE it goes on the timeline --------------
   Nathan: "under the description boxes when I click them I want there to be a
   slider if I want to make it start or end shorter". The index is a machine
   guess at where a moment begins and ends, so it is a starting point, not a
   fact - these two sliders move each end +/-10s and everything downstream (add,
   drag, play, the in-use marker) reads the adjusted value. */
var mAdj = {}, openMom = -1;
function momA(i){ return (mAdj[i] && mAdj[i].a !== undefined) ? mAdj[i].a : M[i].start; }
function momB(i){ return (mAdj[i] && mAdj[i].b !== undefined) ? mAdj[i].b : M[i].end; }
function setAdj(i, which, val){
  if (!mAdj[i]) mAdj[i] = {};
  var m = M[i];
  if (which === "a") mAdj[i].a = Math.min(Math.max(m.start - 10, val), momB(i) - 1);
  else               mAdj[i].b = Math.max(Math.min(m.end + 10, val), momA(i) + 1);
  // update the readout in place - a full re-render would kill the drag
  var r = document.getElementById("mr" + i);
  if (r) r.innerHTML = adjText(i);
  try{ localStorage.setItem(KEY + "_adj", JSON.stringify(mAdj)); }catch(e){}
}
function adjText(i){
  var m = M[i], a = momA(i), b = momB(i);
  var da = a - m.start, db = b - m.end;
  var off = function(d){ return Math.abs(d) < 0.05 ? "" :
      " <span class='chg'>" + (d>0?"+":"") + d.toFixed(1) + "s</span>"; };
  return "<b class='num'>" + (b-a).toFixed(1) + "s</b> <span class='faint'>&nbsp;start "
       + fmtS(a - BASE) + off(da) + " &nbsp;·&nbsp; end " + fmtS(b - BASE) + off(db) + "</span>";
}
// Nathan: "I like the sliders but also as the 1sec buttons" - a slider is good
// for finding the edge, a button is better for landing on it exactly.
function steps(i, which){
  var d = [-1, 1], h = "<span class='seg tiny'>";      // 1s only: his call
  for (var k=0;k<d.length;k++)
    h += "<button onclick='nudgeAdj(" + i + ",\"" + which + "\"," + d[k] + ")'>"
      +  (d[k] > 0 ? "+" : "−") + Math.abs(d[k]) + "</button>";
  return h + "</span>";
}
function nudgeAdj(i, which, d){
  setAdj(i, which, (which === "a" ? momA(i) : momB(i)) + d);
  var L = document.querySelector(".list"), top = L ? L.scrollTop : 0;
  renderMoments();
  L = document.querySelector(".list");
  if (L) L.scrollTop = top;                       // do not jump the list on a click
  if (which === "a") previewStart(momA(i), momB(i));
  else               previewEnd(momA(i), momB(i));
}
function resetAdj(i){ delete mAdj[i]; renderMoments(); }
function playMom(i){ playRange(momA(i), momB(i)); }
function toggleMom(i){
  openMom = (openMom === i) ? -1 : i;
  if (openMom === i) playRange(momA(i), momB(i));   // watch it before dragging it
  else { v.pause(); stopAt = null; }
  renderMoments();
}
function used(m, i){
  for (var k=0;k<clips.length;k++)
    if (Math.abs(clips[k].a - momA(i)) < 1.5) return true;
  return false;
}
function renderMoments(){
  var h = "";
  for (var i=0;i<M.length;i++){
    var m = M[i];
    if (!showAll && m.punch < 4) continue;
    var c = m.punch >= 5 ? "pn p5" : (m.punch >= 4 ? "pn p4" : "pn");
    var open = (openMom === i);

    // The trim panel is a SIBLING under the card, not a child of it: a range
    // input inside a draggable element gets hijacked by the drag gesture.
    h += "<div class='mwrap" + (open ? " open" : "") + "'>"
      +  "<div class='m" + (used(m, i) ? " in-use" : "") + "' draggable='true'"
      +  " ondragstart='dragMoment(event," + i + ")' ondragend='endDrag()'"
      +  " onclick='toggleMom(" + i + ")'>"
      +  "<span class='" + c + "'>" + m.punch + "</span><div class='mt'>"
      +  "<div class='ml'>" + (i===HOOK ? "<span class='rl rl-hook'>best hook</span>" : "")
      +  (SPLIT > 0 && m.start >= SPLIT ? "<span class='rl rl-case2'>2nd case</span>" : "")
      +  esc(m.label) + "</div>"
      +  "<div class='mw'>" + fmtS(momA(i) - BASE) + " · " + Math.round(momB(i)-momA(i)) + "s · "
      +  esc(m.what || "") + "</div>"
      +  (ROLE[i] ? "<div class='note'><span class='rl rl-" + esc(ROLE[i].role) + "'>"
                    + esc(ROLE[i].role) + "</span>" + esc(ROLE[i].note) + "</div>" : "")
      +  "</div>"
      +  "<button class='sm go madd' onclick='event.stopPropagation();addMoment(" + i + ")'>add</button>"
      +  "</div>";

    if (open){
      var lo = (m.start - 10).toFixed(1), hi = (m.end + 10).toFixed(1);
      h += "<div class='trim'>"
        +  "<div class='mr' id='mr" + i + "'>" + adjText(i) + "</div>"
        +  "<div class='tl'><span>start</span>" + steps(i, "a")
        +  "<input class='tsl' type='range' min='" + lo + "' max='" + hi + "' step='0.2'"
        +  " value='" + momA(i).toFixed(1) + "'"
        +  " oninput='setAdj(" + i + ",\"a\",parseFloat(this.value))'"
        +  " onchange='previewStart(momA(" + i + "),momB(" + i + "))'></div>"
        +  "<div class='tl'><span>end</span>" + steps(i, "b")
        +  "<input class='tsl' type='range' min='" + lo + "' max='" + hi + "' step='0.2'"
        +  " value='" + momB(i).toFixed(1) + "'"
        +  " oninput='setAdj(" + i + ",\"b\",parseFloat(this.value))'"
        +  " onchange='previewEnd(momA(" + i + "),momB(" + i + "))'></div>"
        +  "<div class='trow'>"
        +  "<button class='sm' onclick='playMom(" + i + ")'>&#9654; watch</button>"
        +  "<button class='sm' onclick='resetAdj(" + i + ")'>reset</button>"
        +  "<span class='spacer'></span>"
        +  "<span class='faint'>drag the card up to the timeline</span>"
        +  "<button class='sm go' onclick='addMoment(" + i + ")'>add</button>"
        +  "</div></div>";
    }
    h += "</div>";
  }
  document.getElementById("panel").innerHTML = h || "<p class='faint' style='padding:12px'>none</p>";
}
function toggleAll(){
  showAll = !showAll;
  document.getElementById("tog").textContent = showAll ? "best only" : "show all";
  renderMoments();
}

function render(){
  renderTrack(); renderDetail(); renderMoments(); renderSug();
  document.getElementById("bundo").disabled = !hist.length;
  document.getElementById("bredo").disabled = !future.length;
  document.getElementById("cmd").value = build();
  try{ localStorage.setItem(KEY, snap()); }catch(e){}
}

/* ---------------- output ---------------- */
function build(){
  if (!clips.length) return "";
  var f = [];
  for (var i=0;i<clips.length;i++)
    f.push("--seg " + clips[i].a.toFixed(1) + ":" + clips[i].b.toFixed(1));
  return "python scripts/make_short.py --video " + VIDEO + " " + f.join(" ") + " --out \"" + OUT + "\"";
}
/* Rendering used to mean copying a command into a terminal. When the studio
   server is up (Studio.bat) the page posts the segments to it and reports back;
   opened straight off disk there is no server, so it falls back to the command. */
var LIVE = location.protocol.indexOf("http") === 0;
var polling = null;
function doRender(){
  if (!clips.length){ toast("timeline is empty"); return; }
  if (!LIVE){ copyCmd(); return; }
  var b = document.getElementById("brender");
  if (polling){ toast("already rendering"); return; }
  b.disabled = true; b.textContent = "Rendering…";
  fetch("/render", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({video: VIDEO, name: OUT.split(/[\/]/).pop(),
                          segs: clips.map(function(c){ return [c.a, c.b]; })})})
   .then(function(r){ return r.json(); })
   .then(function(j){
      if (j.error) throw new Error(j.error);
      polling = setInterval(function(){ poll(j.job); }, 1200);
   })
   .catch(function(e){ b.disabled = false; b.textContent = "Render";
                       toast("render failed: " + e.message); });
}
function poll(job){
  fetch("/status/" + job).then(function(r){ return r.json(); }).then(function(j){
    var b = document.getElementById("brender");
    if (j.state === "running"){ b.textContent = "Rendering…"; toastQuiet(j.line || ""); return; }
    clearInterval(polling); polling = null;
    b.disabled = false; b.textContent = "Render";
    if (j.state === "done"){
      toast("rendered " + (j.name || "") + "  " + (j.size_mb || "?") + " MB");
      var w = document.getElementById("done");
      if (w){ w.innerHTML = "<a href='" + encodeURIComponent(j.name) + "' target='_blank'>"
              + esc(j.name) + "</a> &middot; " + (j.size_mb||"?") + " MB"; }
    } else {
      toast("render failed — " + (j.line || "see the server window"));
    }
  });
}
function toastQuiet(m){
  var t = document.getElementById("toast");
  if (m){ t.textContent = m; t.classList.add("on"); }
}
function copyCmd(){
  var c = document.getElementById("cmd");
  if (!c.value){ toast("timeline is empty"); return; }
  c.style.display = "block"; c.focus(); c.select();
  var ok = false; try{ ok = document.execCommand("copy"); }catch(e){}
  toast(ok ? "command copied — paste it in the terminal" : "select the text and copy");
}
var tmr = null;
function toast(m){
  var t = document.getElementById("toast");
  t.textContent = m; t.classList.add("on");
  clearTimeout(tmr); tmr = setTimeout(function(){ t.classList.remove("on"); }, 2200);
}

/* ---------------- keyboard ---------------- */
document.addEventListener("keydown", function(e){
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
  var k = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && k === "z"){ e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if ((e.ctrlKey || e.metaKey) && k === "y"){ e.preventDefault(); redo(); return; }
  if ((e.ctrlKey || e.metaKey) && k === "b"){ e.preventDefault(); splitHere(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "=" || k === "+")){ e.preventDefault(); zoom(1.65); return; }
  if ((e.ctrlKey || e.metaKey) && k === "-"){ e.preventDefault(); zoom(0.6); return; }
  if (e.ctrlKey || e.metaKey) return;
  if (e.shiftKey && k === "z"){ e.preventDefault(); fitToggle(); return; }
  if (k === "=" || k === "+"){ e.preventDefault(); zoom(1.65); return; }
  if (k === "-" || k === "_"){ e.preventDefault(); zoom(0.6); return; }
  if (k === "n"){ e.preventDefault(); toggleSnap(); return; }
  if (k === ","){ e.preventDefault(); slip(-1); return; }
  if (k === "."){ e.preventDefault(); slip(1); return; }
  if (k === "i") markIn();
  else if (k === "o") markOut();
  else if (k === "s") splitHere();
  else if (k === "q"){ e.preventDefault(); cutLeft(); }
  else if (k === "w"){ e.preventDefault(); cutRight(); }
  else if (k === "j"){ e.preventDefault(); shuttle(-1); }
  else if (k === "k"){ e.preventDefault(); shuttle(0); }
  else if (k === "l"){ e.preventDefault(); shuttle(1); }
  else if (k === "?" || (k === "/" && e.shiftKey)){ e.preventDefault(); helpOverlay(); }
  else if (k === "escape"){ document.getElementById("help").style.display = "none"; }
  else if (k === "delete" || k === "backspace"){ e.preventDefault(); del(sel); }
  else if (k === "arrowleft"){ e.preventDefault(); nudge(e.shiftKey ? -10 : -1); }
  else if (k === "arrowright"){ e.preventDefault(); nudge(e.shiftKey ? 10 : 1); }
  else if (k === " "){ e.preventDefault(); clips.length ? playShort() : togglePlay(); }
  else if (k === "home"){ e.preventDefault(); setHead(0, true); }
  else if (k === "end"){ e.preventDefault(); setHead(dur(), true); }
});
// Ctrl+wheel zooms the timeline, as in CapCut
document.getElementById("track").addEventListener("wheel", function(e){
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  zoom(e.deltaY < 0 ? 1.15 : 0.87);
}, {passive:false});

if (!LIVE){
  var rb = document.getElementById("brender");
  if (rb){ rb.textContent = "Copy command";
           rb.title = "start Studio.bat to render straight from this page"; }
}
try{ var sv = localStorage.getItem("studio_settings");
      if (sv){ var o = JSON.parse(sv); for (var kk in o) S[kk] = o[kk]; } }catch(e){}
if (!THEMES[S.theme]) S.theme = "ember";
applyAll();
try{ var st = localStorage.getItem(KEY); if (st) clips = JSON.parse(st) || []; }catch(e){}
try{ var sa = localStorage.getItem(KEY + "_adj"); if (sa) mAdj = JSON.parse(sa) || {}; }catch(e){}
v.addEventListener("loadedmetadata", function(){ if (clips.length) fitZoom(); });
if (clips.length) fitZoom();
render();
</script></body></html>
"""


# "the court is calling" is how a hearing starts, and find_called_hearings.py
# segments on it. But the court does not always say it: in 2XkPnvstmRQ a second
# defendant's case opens at 13:49 with the parties announcing instead, so the
# phrase-based split merged two hearings into one 19.5-minute span. The moment
# index already spots it ("New case called and announced"), so use that - a short
# must never mix two defendants, and the long-form is one defendant per video.
NEW_CASE = re.compile(
    r"new case|next case|another case|case is called|calling the case"
    r"|parties announce|announce on state|state v\.?\s", re.I)


def second_case_start(moments: list, span_s: float) -> float:
    """Source second where a SECOND hearing appears to begin, else -1."""
    if not moments or span_s <= 0:
        return -1.0
    t0 = moments[0]["start"]
    for m in moments:
        # ignore the opening minutes: the first case is announced too
        if m["start"] - t0 < max(120.0, span_s * 0.25):
            continue
        blob = (m.get("label", "") + " " + m.get("what", ""))
        if NEW_CASE.search(blob):
            return float(m["start"])
    return -1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="mp4 in READY-TO-REVIEW to edit against")
    ap.add_argument("--video", required=True, help="source youtube id")
    ap.add_argument("--base", type=float, required=True,
                    help="source seconds at the file's t=0")
    ap.add_argument("--out", default=None, help="path the short will render to")
    args = ap.parse_args()

    mpath = ROOT / "state" / f"moments_{args.video}.json"
    moments = []
    if mpath.exists():
        raw = json.loads(mpath.read_text(encoding="utf-8"))
        moments = raw.get("moments", raw) if isinstance(raw, dict) else raw
        moments.sort(key=lambda m: m["start"])

    spath = ROOT / "state" / f"suggest_{args.video}.json"
    suggest = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}

    span = (moments[-1]["end"] - moments[0]["start"]) if moments else 0.0
    split_at = second_case_start(moments, span)

    name = Path(args.file).name
    outname = args.out or str(OUTDIR / ("SHORT_" + Path(args.file).stem + ".mp4"))
    html = (PAGE.replace("__NAME__", name)
                .replace("__FILE__", name)
                .replace("__VID__", args.video)
                .replace("__BASE__", "%.1f" % args.base)
                .replace("__MOMENTS__", json.dumps(moments))
                .replace("__SUGGEST__", json.dumps(suggest))
                .replace("__SPLIT__", "%.1f" % split_at)
                .replace("__OUTNAME__", outname.replace("\\", "\\\\")))

    dest = OUTDIR / ("STUDIO_" + args.video + ".html")
    dest.write_text(html, encoding="utf-8")
    print("wrote " + str(dest))
    print("  %d moments, base %.1fs" % (len(moments), args.base))
    print("  %d suggested plans%s" % (len(suggest.get("plans", [])),
                                      "" if suggest else "  (run scripts/suggest_edit.py)"))
    if split_at > 0:
        rel = split_at - args.base
        print("  WARNING: a SECOND case appears to start at %d:%02d (source %.0fs)."
              % (int(rel // 60), int(rel % 60), split_at))
        print("           This span holds two defendants. The long-form should end")
        print("           there, and a short must not mix them - the page marks it.")


if __name__ == "__main__":
    main()
