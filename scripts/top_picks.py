"""Rank every case in the bank by PREDICTED PERFORMANCE, not by rubric score alone.

The rubric answers "will this hold a stranger's attention". It does not answer
"will this video do well", because three things measured on 2026-08-18 sit
outside it entirely:

  1. LENGTH. Within-channel, decile-normalised, on Court Trials TV Network
     (899 videos, the #1 channel in this niche): 0-10m 0.55x, 10-20m 0.92x,
     20-30m 1.62x, 30-40m 2.53x. Raw medians 6.2K / 11K / 20K / 32K. A great
     6-minute hearing is worth less than a good 25-minute one.

  2. THE RETURN APPEARANCE. Titles announcing a defendant is back run a median
     15,000 views against 11,000 for one-offs (n=348 vs 551) at the same
     runtime, and the lift holds inside every duration band. 1.36x.

  3. WHETHER ANYONE IS ON CAMERA. A hard gate, not a multiplier. Arnold Pena
     scores highest in the bank on BOTH rubrics and his feed is a black Zoom
     name card for all 51 minutes. See oncamera.py.

  4. WHETHER THE HEARING TAKES EVIDENCE. Nathan, 2026-08-18: "we can't even
     use that video it's a bench trial." The moment a witness is sworn the
     courtroom camera pulls back to a wide room shot and there is no face to
     show. This is UPSTREAM of the camera probe and catches cases the probe
     passes — Miosek reads as two live tiles and is still a wide empty room.
     See hearingtype.py; 8/8 on the cases whose visuals we have verified.

So:  value = rubric_score x length_multiplier x repeat_multiplier
     gated on: safety_pass AND shortable AND not evidentiary AND on camera

Episodes are the unit, not hearings — a defendant's hearings concatenate into
one "Watch Both Cases" video, which is both the winning format and the way a
6-minute hearing gets over the 20-minute floor.

    python scripts/top_picks.py            # top 5
    python scripts/top_picks.py --top 15 --probe
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import hearingtype, oncamera, repeats   # noqa: E402
from boydclips.config import load_config           # noqa: E402
from boydclips.state import Store                  # noqa: E402
from boydclips.transcribe import Transcript        # noqa: E402

# Measured within-channel on Court Trials TV, full catalogue. Applied to the
# EPISODE's total runtime, since that is what gets published.
LENGTH_MULT = [(600, 0.55), (1200, 0.92), (1800, 1.62), (2400, 2.53), (10**9, 2.53)]
REPEAT_MULT = 1.36


def length_mult(seconds: float) -> float:
    for cap, m in LENGTH_MULT:
        if seconds < cap:
            return m
    return LENGTH_MULT[-1][1]


def main() -> int:
    top_n = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 5
    probe = "--probe" in sys.argv
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))

    cases = [dict(r) for r in store.conn.execute(
        "SELECT case_key, video_id, defendant, proceeding_type, total_score, "
        "safety_pass, shortable, start_s, end_s, payload FROM cases")]
    dates = {v: d for v, d in store.conn.execute(
        "SELECT video_id, docket_date FROM dockets")}

    # Only cases carrying CURRENT-rubric dimensions. scripts/rescore.py rewrites
    # these in place, so a case it has not reached yet still holds an old-rubric
    # number on a different scale and must not be ranked beside a new one.
    NEW = {"pushback", "boyd_register", "receipt", "consequence"}
    fresh = []
    for c in cases:
        try:
            p = json.loads(c["payload"] or "{}")
        except Exception:
            continue
        if not (set((p.get("scores") or {}).keys()) & NEW):
            continue
        c["p"] = p
        fresh.append(c)
    print(f"{len(fresh)} of {len(cases)} cases carry current-rubric scores")

    # Episodes: a repeat defendant's hearings publish as one video. Everything
    # else is its own single-hearing episode.
    eps = repeats.find_episodes(store.conn)
    in_ep = {h["case_key"] for e in eps for h in e.hearings}
    fresh_by_key = {c["case_key"]: c for c in fresh}

    groups = []
    for e in eps:
        hs = [fresh_by_key[h["case_key"]] for h in e.hearings
              if h["case_key"] in fresh_by_key]
        if hs:
            groups.append((e.defendant, hs, True))
    for c in fresh:
        if c["case_key"] not in in_ep:
            groups.append((c["defendant"] or "?", [c], False))

    ranked = []
    for name, hs, is_repeat in groups:
        if not all(h["safety_pass"] for h in hs):
            continue
        best = max(hs, key=lambda h: h["total_score"] or 0)
        if not best["shortable"]:
            continue
        total_s = sum(max(0.0, (h["end_s"] or 0) - (h["start_s"] or 0)) for h in hs)
        score = best["total_score"] or 0
        value = score * length_mult(total_s) * (REPEAT_MULT if is_repeat else 1.0)
        ranked.append({"name": name, "hs": hs, "best": best, "repeat": is_repeat,
                       "total_s": total_s, "score": score, "value": value})
    ranked.sort(key=lambda r: -r["value"])

    # ---- evidentiary filter, applied before anything expensive -----------
    _tr: dict[str, object] = {}

    def transcript_for(vid: str):
        if vid not in _tr:
            cache = ROOT / "work" / vid / f"{vid}.transcript.json"
            _tr[vid] = (Transcript.from_json(cache.read_text(encoding="utf-8"))
                        if cache.exists() else None)
        return _tr[vid]

    kept, dropped_ev, no_tr = [], 0, 0
    for r in ranked:
        h = r["best"]
        t = transcript_for(h["video_id"])
        if t is None:
            no_tr += 1
            continue
        v = hearingtype.classify(t.text_between(h["start_s"], h["end_s"]),
                                 (h["end_s"] - h["start_s"]) / 60.0)
        if v.contested:
            dropped_ev += 1
            if len(kept) < 12:
                print(f"  BENCH TRIAL, dropped: {r['name'][:24]:26} "
                      f"({r['value']:.0f})  {v.reason}")
            continue
        r["hearing"] = v
        kept.append(r)
    print(f"  {dropped_ev} evidentiary hearings excluded, "
          f"{no_tr} skipped for no cached transcript, {len(kept)} remain")
    ranked = kept

    cam_path = ROOT / "state" / "oncamera.json"
    cam = json.loads(cam_path.read_text()) if cam_path.exists() else {}

    picked = []
    for r in ranked:
        if len(picked) >= top_n:
            break
        k = r["best"]["case_key"]
        v = cam.get(k)
        if v is None and probe:
            out = ROOT / "out" / "oncam" / k.replace(":", "_")
            frames = sorted(out.glob("f*.png")) or oncamera.sample_frames(
                r["best"]["video_id"], r["best"]["start_s"], r["best"]["end_s"],
                n=6, out_dir=out)
            if len(frames) >= 2:
                a = oncamera.analyse(frames, oncamera.detect_layout(frames))
                v = {"usable": a.usable, "reason": a.reason,
                     "faces": max((t.faces for t in a.tiles), default=0)}
            else:
                v = {"usable": None, "reason": "could not sample"}
            cam[k] = v
            cam_path.write_text(json.dumps(cam, indent=2))
            print(f"  probed {k}: {'OK' if v['usable'] else 'DEAD'}")
        if v is None:
            continue
        if not v.get("usable"):
            print(f"  skipped {r['name'][:22]} ({r['value']:.0f}) — {v.get('reason','')[:60]}")
            continue
        r["cam"] = v
        picked.append(r)

    print("\n" + "=" * 94)
    for i, r in enumerate(picked, 1):
        mult = length_mult(r["total_s"])
        print(f"\n{i}. {r['name']}   value {r['value']:.0f}")
        print(f"   rubric {r['score']:.1f}  x  length {mult:.2f} "
              f"({r['total_s']/60:.1f} min)  x  {'repeat 1.36' if r['repeat'] else 'one-off 1.00'}")
        print(f"   {len(r['hs'])} hearing(s), {dates.get(r['hs'][0]['video_id'],'?')}"
              f" -> {dates.get(r['hs'][-1]['video_id'],'?')}  best={r['best']['case_key']}")
        p = r["best"]["p"]
        if p.get("hook_quote"):
            print(textwrap.fill(f'HOOK: "{p["hook_quote"].strip()}"', 92,
                                initial_indent="   ", subsequent_indent="         "))
        for h in r["hs"]:
            s = (h["p"].get("summary") or "").strip()
            if s:
                print(f"   -- {h['case_key']}  {h['proceeding_type']}  "
                      f"{(h['end_s']-h['start_s'])/60:.1f}m  score {h['total_score']:.1f}")
                print(textwrap.fill(s, 92, initial_indent="      ", subsequent_indent="      "))
        sc = p.get("scores") or {}
        for dim in ("pushback", "boyd_register", "receipt", "consequence"):
            d = sc.get(dim)
            if d and (d.get("score") or 0) >= 45:
                print(textwrap.fill(f"{dim} {d['score']}: {d.get('justification','')}", 92,
                                    initial_indent="   * ", subsequent_indent="     "))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
