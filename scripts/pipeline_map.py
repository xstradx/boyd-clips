"""A visual map of the pipeline, with a note button on every stage.

Serves http://127.0.0.1:8824 . Notes save to state/pipeline_notes.json and
survive restarts.

Stage descriptions are written against the CODE, not against the design docs -
several places in this repo describe behaviour that was never wired, so each
card names the function that actually runs and the config key that actually
controls it. Live counts are read from state/pipeline.db at page load, so the
numbers are real rather than remembered.
"""

from __future__ import annotations

import html
import json
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "state" / "pipeline_notes.json"
DB = ROOT / "state" / "pipeline.db"
PORT = 8824


def counts() -> dict:
    out = {"dockets": 0, "cases": 0, "eligible": 0, "clips": 0,
           "published": 0, "ledger": 0, "sources": 0}
    try:
        db = sqlite3.connect(DB)
        db.row_factory = sqlite3.Row
        out["dockets"] = db.execute("select count(*) c from dockets").fetchone()["c"]
        out["cases"] = db.execute("select count(*) c from cases").fetchone()["c"]
        out["clips"] = db.execute("select count(*) c from clips").fetchone()["c"]
        out["published"] = db.execute("select count(*) c from publications").fetchone()["c"]
        out["ledger"] = db.execute("select count(*) c from ledger").fetchone()["c"]
        n = 0
        for r in db.execute("select payload from cases"):
            p = json.loads(r["payload"])
            if p.get("eligible") and (p.get("safety") or {}).get("safety_pass"):
                n += 1
        out["eligible"] = n
    except Exception:
        pass
    out["sources"] = len(list((ROOT / "work").glob("*/*_*-*.mp4")))
    return out


# (id, group, title, what it does, function that runs, config key, status)
STAGES = [
    ("discover", "INPUT", "1 · Discover",
     "Lists recent streams from the court's channel and keeps the ones not already finished. Metadata only — no video is fetched here.",
     "pipeline.discover() → discover.list_recent()",
     "source.channel_url · scan_depth 8 · min_duration_s 900 · max_age_days 4",
     "ok"),
    ("transcribe", "INPUT", "2 · Transcribe",
     "Pulls YouTube's own auto-captions as word-level timings. This is why a 3-hour docket costs about a dollar: no video is downloaded to read it.",
     "transcribe.get_transcript()",
     "transcription.source auto_captions · whisper_fallback true",
     "ok"),
    ("segment", "BRAIN", "3 · Segment",
     "Claude splits one docket into individual cases with start/end times.",
     "Analyzer.segment() ← prompts/segment_cases.md",
     "analysis.model · analysis.effort",
     "ok"),
    ("gate", "BRAIN", "4 · Safety gate + rubric",
     "Safety rules run FIRST and can reject outright. Survivors get scored on the 5-part rubric. Runs before anything is downloaded, so a rejected case costs nothing.",
     "Analyzer.score() ← prompts/score_cases.md + spec/SAFETY_RULES.md",
     "analysis.gates.min_total_score 50 · rubric_weights (sum 100)",
     "warn"),
    ("rank", "BRAIN", "5 · Rank",
     "Re-orders cases that already passed. Notoriety blends charge severity with press coverage; banger.py scores the transcript for the beats that separate winners from losers on the rival channel. Neither can promote a case past a gate.",
     "notoriety.rank() · banger.score()",
     "analysis.notoriety.rubric_weight 0.7",
     "new"),
    ("select", "BRAIN", "6 · Select the day's pick",
     "Takes the top scorer and re-checks it against the FULL transcript before spending a download. THIS IS THE VOLUME CHOKE POINT — it takes one case per docket.",
     "pipeline.run_daily() → picks = eligible[:clips_per_day]",
     "output.clips_per_day = 1   ← 275 eligible cases queue behind this",
     "block"),
    ("download", "BUILD", "7 · Download the section",
     "Fetches only the minutes that get published, not the 3-hour stream. Broke today: Google now serves ANDROID_VR URLs as a short prefix and ffmpeg's open-ended range request gets a 403. Fixed by forcing the web_embedded client.",
     "render.download_section()",
     "SECTION_PLAYER_CLIENTS (web_embedded first)",
     "fixed"),
    ("trim", "BUILD", "8 · Cut",
     "Merges recessed-and-recalled sittings, removes dead air over 4s, enforces the duration bounds. The trimmer existed for weeks and the daily path never called it — every automated long-form shipped with ~21% silence until today.",
     "render.detect_silences() + plan_silence_trim()",
     "trim_dead_air true · dead_air_s 4.0 · min 120s · max 3480s (58 min)",
     "fixed"),
    ("longform", "BUILD", "9 · Render long-form",
     "Branded sting on the front, then the case, watermark over the body only. The intro parameter existed since the function was written and nothing ever passed one.",
     "render.render_longform()",
     "intro_enabled true · sting_v2.mp4 (2.6s) · crf 20",
     "fixed"),
    ("short", "BUILD", "10 · Render short",
     "Hook-first vertical cut. duo_fill crops each Zoom tile to the half-canvas so there is no black anywhere; captions move to whoever is speaking, using ECAPA speaker embeddings.",
     "render.render_short(tile_crops=…) · diarize.diarize()",
     "vertical_mode duo_fill · Anton 140 · slot_margins boyd 700 / defendant 1020",
     "fixed"),
    ("thumb", "BUILD", "11 · Thumbnail",
     "Frame grabbed at a 'hot moment' — a timestamp where the transcript shows Boyd delivering a hammer line — then the judge is traced out and composited over the courtroom plate, and the whole thing is graded.",
     "thumbnail.build() → scripts/make_thumbnail_v2.py",
     "subject_w 0.52 · subject_cx 0.78 · sat_gain 1.45 · arrow off",
     "warn"),
    ("package", "BUILD", "12 · Titles + description",
     "Claude writes the title, description and thumbnail quote AFTER the sittings are merged — it used to run before, so descriptions stopped at the recess.",
     "Analyzer.package() ← prompts/package_post.md",
     "title 50-65 chars · quote 3-6 words · names Judge Boyd",
     "fixed"),
    ("publish", "OUT", "13 · Publish",
     "Long-form goes first so its URL exists before the short's description is written. Currently refuses everything: the API locks uploads from unaudited projects to private with no appeal, and autonomy is manual.",
     "publish.publish_pair()",
     "autonomy.mode manual · api_audited FALSE ← hard refusal",
     "block"),
    ("ledger", "OUT", "14 · Record",
     "Where approvals and view counts would be stored, and what the 30-approval promotion gate reads. Both tables are empty, so nothing can learn from outcomes yet.",
     "Store.record_publication() / ledger",
     "autonomy promotion gate: 30 consecutive approvals",
     "block"),
]

STATUS = {
    "ok": ("#2e7d32", "working"),
    "fixed": ("#1565c0", "fixed today"),
    "new": ("#6a1b9a", "new today"),
    "warn": ("#ef6c00", "needs a decision"),
    "block": ("#c62828", "BLOCKED"),
}


def load_notes() -> dict:
    if NOTES.is_file():
        try:
            return json.loads(NOTES.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        f = parse_qs(self.rfile.read(n).decode("utf-8"))
        notes = load_notes()
        sid = f.get("stage", [""])[0]
        txt = f.get("note", [""])[0].strip()
        if sid and txt:
            notes.setdefault(sid, []).append(txt)
            NOTES.parent.mkdir(parents=True, exist_ok=True)
            NOTES.write_text(json.dumps(notes, indent=1), encoding="utf-8")
        self.send_response(303)
        self.send_header("Location", f"/#{sid}")
        self.end_headers()

    def do_GET(self):
        c = counts()
        notes = load_notes()
        groups: dict[str, list] = {}
        for s in STAGES:
            groups.setdefault(s[1], []).append(s)

        body = []
        for gname, items in groups.items():
            body.append(f'<h2 class=grp>{gname}</h2>')
            for sid, _g, title, what, fn, cfg, status in items:
                colour, label = STATUS[status]
                mine = notes.get(sid, [])
                notehtml = "".join(
                    f'<div class=note>{html.escape(t)}</div>' for t in mine)
                body.append(f"""
<div class=card id="{sid}">
  <div class=head>
    <span class=title>{title}</span>
    <span class=badge style="background:{colour}">{label}</span>
  </div>
  <div class=what>{html.escape(what)}</div>
  <div class=fn>{html.escape(fn)}</div>
  <div class=cfg>{html.escape(cfg)}</div>
  {notehtml}
  <details><summary>+ add a note</summary>
    <form method=POST action="/note">
      <input type=hidden name=stage value="{sid}">
      <textarea name=note rows=3 placeholder="what's wrong / what should this do instead"></textarea>
      <button type=submit>Save note</button>
    </form>
  </details>
</div>
<div class=arrow>&#9662;</div>""")

        page = f"""<!doctype html><meta charset=utf-8><title>Boyd pipeline</title><style>
*{{box-sizing:border-box}}
body{{font:15px/1.5 system-ui;background:#0d0d0d;color:#e8e8e8;margin:0;padding:28px;max-width:820px;margin:0 auto}}
h1{{font-size:23px;margin:0 0 4px}}
.stats{{color:#8a8a8a;font-size:13px;margin-bottom:8px}}
.stats b{{color:#e8e8e8}}
.grp{{font-size:12px;letter-spacing:.14em;color:#777;margin:26px 0 8px;font-weight:700}}
.card{{background:#181818;border:1px solid #2b2b2b;border-radius:10px;padding:14px 16px}}
.head{{display:flex;justify-content:space-between;align-items:center;gap:10px}}
.title{{font-size:17px;font-weight:700}}
.badge{{font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:20px;letter-spacing:.05em;white-space:nowrap}}
.what{{color:#c4c4c4;font-size:14px;margin:8px 0}}
.fn{{font:12px ui-monospace,Consolas,monospace;color:#6fb2e8;margin-bottom:3px}}
.cfg{{font:12px ui-monospace,Consolas,monospace;color:#7a7a7a}}
.arrow{{text-align:center;color:#3a3a3a;font-size:19px;line-height:1;margin:3px 0}}
.note{{background:#20262e;border-left:3px solid #4a9eda;padding:7px 10px;margin:9px 0 0;font-size:13.5px;border-radius:0 5px 5px 0;white-space:pre-wrap}}
details{{margin-top:9px}}
summary{{cursor:pointer;color:#8a8a8a;font-size:12.5px}}
textarea{{width:100%;background:#0d0d0d;color:#e8e8e8;border:1px solid #333;border-radius:6px;padding:8px;font:13px system-ui;margin-top:7px;resize:vertical}}
button{{margin-top:6px;padding:7px 15px;border:0;border-radius:6px;background:#c00;color:#fff;font-weight:600;cursor:pointer}}
</style>
<h1>How the pipeline actually works</h1>
<div class=stats>
 <b>{c['dockets']}</b> dockets &middot; <b>{c['cases']}</b> cases scored &middot;
 <b>{c['eligible']}</b> eligible &middot; <b>{c['sources']}</b> sources downloaded &middot;
 <b>{c['clips']}</b> clips rendered &middot; <b>{c['published']}</b> published
</div>
<div class=stats>Every stage below names the function that really runs and the config key that really controls it. Notes save to state/pipeline_notes.json.</div>
{''.join(body)}
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))


def main() -> int:
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"pipeline map on {url}   (ctrl-c to stop)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nnotes ->", NOTES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
