"""Command line entry point.

    boyd doctor                 check the environment before trusting a cron job
    boyd discover               list new dockets, touch nothing else
    boyd run [--dry-run]        the daily pipeline
    boyd run --case <case_key>  render one specific defendant's case
    boyd run --moment <key>     render one judged MOMENT (the real product)
    boyd docket [--days N]      Boyd's upcoming hearings, before they air
    boyd who <name>             jail record + custody status for a defendant
    boyd archive                snapshot the county's expiring 7-day jail data
    boyd approve <case_key>     record approval and publish a held clip
    boyd reject <case_key>      record rejection with a reason
    boyd stats                  reliability ledger and promotion readiness
    boyd bank                   banked runner-up cases
    boyd repeats                defendants who came back — the BACK AGAIN lane
    boyd oncamera <case_key>    is anyone in the other Zoom window?
    boyd moments [--top N]      where Judge Boyd chews somebody out
    boyd auth youtube           one-time OAuth
    boyd cleanup                remove stale scratch files
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config
from .pipeline import Pipeline, setup_logging
from .publish import YouTubePublisher, publish_pair
from . import moments as _moments
from .oncamera import analyse, detect_layout, sample_frames
from .transcribe import Transcript
from .repeats import find_episodes, qualifying
from .state import Store


def _ant_profile_active() -> bool:
    """An unset ANTHROPIC_API_KEY does not mean there are no credentials — the
    SDK also reads an `ant auth login` profile. Absent CLI is not an error."""
    if shutil.which("ant") is None:
        return False
    try:
        return subprocess.run(
            ["ant", "auth", "status"], capture_output=True, text=True, timeout=15
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def cmd_doctor(args: argparse.Namespace) -> int:
    print("boyd doctor\n" + "=" * 60)
    ok = True

    for tool, why in [
        ("yt-dlp", "downloads captions and video sections"),
        ("ffmpeg", "cuts and renders clips"),
        ("ffprobe", "measures rendered durations"),
    ]:
        path = shutil.which(tool)
        print(f"  [{'ok ' if path else 'MISS'}] {tool:10s} {path or '-- ' + why}")
        ok &= bool(path)

    try:
        cfg = load_config()
        print(f"  [ok ] config          autonomy.mode={cfg.get('autonomy.mode')}")
    except Exception as exc:
        print(f"  [MISS] config         -- {exc}")
        return 1

    # Only check the credential the configured backend actually needs.
    backend = cfg.get("analysis.backend", "claude_cli")
    if backend == "claude_cli":
        claude = shutil.which("claude")
        print(f"  [{'ok ' if claude else 'MISS'}] claude CLI     "
              f"{claude or '-- required by analysis.backend=claude_cli'}")
        ok &= bool(claude)
        if claude:
            print(f"  [ok ] auth           via Claude Code login (no API key needed)")
    else:
        try:
            import anthropic  # noqa: F401
            print("  [ok ] anthropic SDK")
        except ImportError:
            print("  [MISS] anthropic SDK  -- pip install anthropic")
            ok = False
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("  [ok ] ANTHROPIC_API_KEY")
        elif _ant_profile_active():
            print("  [ok ] credentials via `ant auth` profile")
        else:
            print("  [MISS] ANTHROPIC_API_KEY -- set it in config/.env, run `ant auth login`,")
            print("                             or set analysis.backend: claude_cli")
            ok = False

    if cfg.get("publish.youtube.enabled"):
        token = cfg.root / "config" / "youtube_token.json"
        secret = cfg.root / "config" / "youtube_client_secret.json"
        if token.exists():
            print("  [ok ] YouTube OAuth token")
        elif secret.exists():
            print("  [warn] YouTube client secret present, not yet authorized "
                  "-- run: boyd auth youtube")
        else:
            print("  [warn] YouTube not configured -- fine while autonomy.mode=manual")

    print("=" * 60)
    print("ready" if ok else "not ready — resolve the MISS lines above")
    return 0 if ok else 1


def cmd_discover(args: argparse.Namespace) -> int:
    pipe = Pipeline()
    setup_logging(pipe.cfg, args.verbose)
    for d in pipe.discover():
        print(f"  {d.video_id}  {d.docket_date or '??????????':10s}  "
              f"{d.duration_s / 60:6.0f}min  {d.session:9s}  {d.title[:60]}")
    pipe.close()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    pipe = Pipeline()
    setup_logging(pipe.cfg, args.verbose)
    if getattr(args, "moment", None):
        one = pipe.run_moment(args.moment, dry_run=args.dry_run)
        results = [one] if one else []
    elif args.case:
        one = pipe.run_case(args.case, dry_run=args.dry_run)
        results = [one] if one else []
    else:
        results = pipe.run_daily(limit=args.limit, dry_run=args.dry_run)
    pipe.cleanup()
    pipe.close()

    if not results:
        print("\nno clips produced this run")
        return 0

    print(f"\n{len(results)} clip pair(s) produced:")
    for r in results:
        print(f"  {r['review_dir']}")
        print(f"    long-form: {r['longform']['title']}")
        if r["short"]:
            print(f"    short:     {r['short']['title']}")
    if pipe.cfg.get("autonomy.mode") == "manual":
        print("\nautonomy.mode=manual — review the folders above, then:")
        print("  boyd approve <case_key>   (case_key is in manifest.json)")
    return 0


def cmd_docket(args: argparse.Namespace) -> int:
    """Who is scheduled in front of Boyd, before it airs."""
    from datetime import date, timedelta
    from . import records

    start = date.today()
    rows = records.hearings(start, start + timedelta(days=args.days))
    if not rows:
        print("no hearings found — re-scrape the judicial officer id "
              "(see records.JUDGE_BOYD_ID)")
        return 1

    by_day: dict[str, list[dict]] = {}
    for r in rows:
        by_day.setdefault(r["hearing_date"] or "?", []).append(r)

    for day in sorted(by_day, key=lambda d: (len(d), d)):
        print(f"\n{day}  ({len(by_day[day])} hearings)")
        for r in by_day[day][: args.limit]:
            print(f"  {str(r['hearing_time']):>8}  {str(r['hearing_type'])[:26]:26s} "
                  f"{str(r['defendant'])[:28]:28s} {r['case_number']}")
    print(f"\n{len(rows)} hearings total")
    return 0


def cmd_who(args: argparse.Namespace) -> int:
    """Jail record for a name. Candidates, not an identification."""
    from . import records

    res = records.custody_status(args.name)
    print(f"{res['total_hits']} raw hits, {len(res['people'])} distinct SO numbers\n")
    for p in res["people"][: args.limit]:
        status = "IN CUSTODY" if p["in_custody"] else "released"
        print(f"  SO {p['so_number']:>8}  {p['booking_count']:>3} bookings  "
              f"{status:10s}  {str(p['name'])[:32]:32s} "
              f"{p['first_booking']}..{p['latest_booking']}")
        for c in p["latest_charges"][:3]:
            print(f"        {c[:70]}")
    print("\nNames are not identities — confirm SONumber before asserting "
          "anything on camera.")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    """Snapshot the county's 7-day jail activity window before it expires."""
    from . import records

    out = Path(args.out or "data/jail-activity")
    res = records.archive_jail_activity(out, days_back=args.days_back)
    print(f"archived {res['saved']} new file(s), {res['skipped']} already held, "
          f"{res['missing']} unavailable -> {out}")
    if res["missing"]:
        print("  (missing days are normal at the edges of the 7-day window)")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    case = store.get_case(args.case_key)
    if case is None:
        print(f"unknown case: {args.case_key}")
        return 1

    store.record_decision(args.case_key, "approved", args.reason or "")

    conn = store._conn  # noqa: SLF001 -- narrow read, no public accessor needed
    clips = {
        row["kind"]: dict(row)
        for row in conn.execute("SELECT * FROM clips WHERE case_key = ?", (args.case_key,))
    }
    if not clips:
        print("approval recorded (no rendered clips found for this case)")
        store.close()
        return 0

    if cfg.get("autonomy.mode") == "manual":
        print("approval recorded. autonomy.mode=manual, so nothing was published.")
        print("Set autonomy.mode to 'assisted' or 'auto' in config/pipeline.yaml to publish.")
        store.close()
        return 0

    if store.case_published(args.case_key):
        print(f"{args.case_key} is already published — not uploading again.")
        print("Approval was still recorded. Use --force only if you mean to duplicate.")
        store.close()
        return 0

    report = publish_pair(
        cfg, store,
        longform=clips.get("longform"),
        short=clips.get("short"),
        context={"hook_line": case.get("hook_quote", "")},
    )
    print(json.dumps(report, indent=2, default=str))
    store.close()
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    store.record_decision(
        args.case_key, "rejected", args.reason or "", safety_related=args.safety
    )
    print(f"rejected {args.case_key}" + (" (safety-related)" if args.safety else ""))
    store.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    r = store.reliability()

    print("reliability ledger\n" + "=" * 50)
    print(f"  decisions recorded    {r['total_decisions']}")
    print(f"  approved              {r['approved']}")
    print(f"  approval rate         {r['approval_rate'] if r['approval_rate'] is not None else '--'}")
    print(f"  consecutive approvals {r['consecutive_approvals']}")
    print(f"  safety rejects        {r['safety_rejects']}")

    gate = cfg.require("autonomy.promotion_gate")
    ready, why = store.promotion_ready(
        gate["min_consecutive_approvals"], gate["max_safety_rejects"]
    )
    print("\nautonomy\n" + "=" * 50)
    print(f"  current mode          {cfg.get('autonomy.mode')}")
    print(f"  promotion to 'auto'   {'READY' if ready else 'not yet'} — {why}")
    if ready and cfg.get("autonomy.mode") != "auto":
        print("\n  To promote: set autonomy.mode: auto in config/pipeline.yaml")
    store.close()
    return 0


def cmd_bank(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    rows = store.banked_cases(args.limit)
    if not rows:
        print("bank is empty")
    for row in rows:
        print(f"  {row['case_key']:28s} score {row['total_score']:5.1f}  "
              f"{(row['defendant'] or '?')[:24]:24s} {row['proceeding_type']}")
    store.close()
    return 0


def cmd_repeats(args: argparse.Namespace) -> int:
    """Defendants who appear across two or more dockets.

    The measured 1.36x format on the niche's #1 channel, buildable entirely
    from material already scored and on disk. See src/boydclips/repeats.py for
    the measurement and config analysis.repeat_defendant for the gate.
    """
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    rc = dict(cfg.get("analysis.repeat_defendant", {}) or {})
    if args.all:
        rc = {**rc, "enabled": True, "min_best_score": 0.0,
              "require_all_safety_pass": False}
    eps = qualifying(store.conn, rc) if not args.all else [
        e for e in find_episodes(store.conn) if e.dockets >= 2]
    if not eps:
        print("no repeat defendants found"
              + ("" if rc.get("enabled", False)
                 else "  (analysis.repeat_defendant.enabled is false)"))
        store.close()
        return 0
    total = sum(e.total_s for e in eps) / 60
    print(f"{len(eps)} repeat defendants — {total:.0f} min of scored material\n")
    for e in eps[: args.limit]:
        flag = "" if e.all_safe else "  [!] a hearing failed safety"
        print(f"  {e.defendant[:26]:28s} {len(e.hearings)}x across "
              f"{e.dockets} dockets   best {e.best_score:5.1f}   "
              f"{e.total_s/60:5.1f} min{flag}")
        if args.verbose:
            for h in e.hearings:
                print(f"        {h['case_key']:26s} score {h['total_score'] or 0:5.1f}  "
                      f"{(h['proceeding_type'] or '?')[:34]}")
    store.close()
    return 0


def cmd_oncamera(args: argparse.Namespace) -> int:
    """Sample a few frames and report whether anyone is actually on camera.

    The rubric reads a transcript and cannot see an empty tile, so a contested
    sentencing full of lawyers and witnesses can score 90 while the feed is a
    black Zoom name card. This costs about 6 x 0.5s of video and answers that
    before anything is downloaded. See src/boydclips/oncamera.py.
    """
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    case = store.get_case(args.case_key)
    store.close()
    if not case:
        print(f"no such case: {args.case_key}")
        return 1
    out = cfg.path("paths.out") / "oncam" / args.case_key.replace(":", "_")
    frames = sorted(out.glob("f*.png")) if not args.refresh else []
    if len(frames) < 2:
        frames = sample_frames(case["video_id"], case["start_s"],
                               case["end_s"], n=args.frames, out_dir=out)
    if len(frames) < 2:
        print("could not sample frames — is the stream still public?")
        return 1
    v = analyse(frames, detect_layout(frames))
    for t in v.tiles:
        print(f"  {t.name:6} detail {t.detail:8.1f}  black {t.dark:5.2f}  "
              f"faces {t.faces}   {'LIVE' if t.live else 'DEAD'}")
    print(f"\n{args.case_key}  {case.get('defendant') or '?'}")
    print(f"  {'USABLE' if v.usable else 'NOT USABLE'} — {v.reason}")
    print(f"  frames in {out}")
    return 0 if v.usable else 2


def cmd_moments(args: argparse.Namespace) -> int:
    """Rank every cached transcript for the moments Judge Boyd goes off.

    The product is a MOMENT, not a case — see src/boydclips/moments.py for the
    two dead ends that preceded this and why frequency mining cannot find a
    riff. Pure text: no model, no network, no video.
    """
    import textwrap
    cfg = load_config()
    work = cfg.path("paths.work")
    files = sorted(work.glob("*/*.transcript.json"))
    if args.video:
        files = [f for f in files if args.video in f.name]
    if not files:
        print(f"no cached transcripts under {work}")
        return 1

    loaded, texts = [], []
    for f in files:
        try:
            t = Transcript.from_json(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        turns = _moments.judicial_turns(t)
        if turns:
            loaded.append(t)
            texts.extend(txt for _a, _b, txt in turns)
    if not texts:
        print(f"{len(files)} transcripts read, no judge riffs found")
        return 0

    idf = _moments.build_idf(texts)
    found: list = []
    for t in loaded:
        found.extend(_moments.scan(t, idf))
    found.sort(key=lambda m: -m.score)
    print(f"{len(files)} transcripts, {len(texts)} riff-length turns, "
          f"{len(found)} moments\n")
    for i, m in enumerate(found[: args.top], 1):
        print(f"{i:>3}. {m.score:6.1f}  {m.words:>4}w  {m.video_id} @{m.clock}"
              + (f"   {', '.join(m.labels[:4])}" if m.labels else ""))
        print(f"     {m.url}")
        print(textwrap.fill(m.text[:400], 92, initial_indent="     > ",
                            subsequent_indent="       "))
        print()

    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps([{
            "video_id": m.video_id, "start_s": m.start_s, "end_s": m.end_s,
            "score": m.score, "novelty": m.novelty, "you_rate": m.you_rate,
            "i_rate": m.i_rate, "labels": m.labels, "words": m.words,
            "url": m.url, "text": m.text} for m in found], indent=2),
            encoding="utf-8")
        print(f"wrote {len(found)} moments to {out}")
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.platform == "youtube":
        YouTubePublisher(cfg).authorize()
        print("YouTube authorized — token saved to config/youtube_token.json")
        return 0
    print(f"no interactive auth flow for {args.platform}")
    return 1


def cmd_cleanup(args: argparse.Namespace) -> int:
    pipe = Pipeline()
    setup_logging(pipe.cfg, args.verbose)
    pipe.cleanup()
    pipe.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="boyd", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor").set_defaults(func=cmd_doctor)
    sub.add_parser("discover").set_defaults(func=cmd_discover)

    run = sub.add_parser("run")
    run.add_argument("--moment", help="render a judged moment, e.g. zHchVGBX9iA:10721")
    run.add_argument("--dry-run", action="store_true",
                     help="analyse and select, but download and render nothing")
    run.add_argument("--limit", type=int, default=None,
                     help="override output.clips_per_day")
    run.add_argument("--case", default=None, metavar="CASE_KEY",
                     help="render one specific scored case instead of the "
                          "day's top pick (see `boyd bank` for keys)")
    run.set_defaults(func=cmd_run)

    docket = sub.add_parser("docket")
    docket.add_argument("--days", type=int, default=14,
                        help="days ahead to look (default 14)")
    docket.add_argument("--limit", type=int, default=100,
                        help="max hearings printed per day")
    docket.set_defaults(func=cmd_docket)

    who = sub.add_parser("who")
    who.add_argument("name", help='defendant name, e.g. "De Hoyos"')
    who.add_argument("--limit", type=int, default=10)
    who.set_defaults(func=cmd_who)

    archive = sub.add_parser("archive")
    archive.add_argument("--out", default=None,
                         help="output dir (default data/jail-activity)")
    archive.add_argument("--days-back", type=int, default=7)
    archive.set_defaults(func=cmd_archive)

    approve = sub.add_parser("approve")
    approve.add_argument("case_key")
    approve.add_argument("--reason", default="")
    approve.set_defaults(func=cmd_approve)

    reject = sub.add_parser("reject")
    reject.add_argument("case_key")
    reject.add_argument("--reason", default="")
    reject.add_argument("--safety", action="store_true",
                        help="mark as a safety-related rejection (blocks autonomy promotion)")
    reject.set_defaults(func=cmd_reject)

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    bank = sub.add_parser("bank")
    bank.add_argument("--limit", type=int, default=20)
    bank.set_defaults(func=cmd_bank)

    auth = sub.add_parser("auth")
    auth.add_argument("platform", choices=["youtube", "tiktok", "instagram"])
    auth.set_defaults(func=cmd_auth)

    repeats = sub.add_parser("repeats")
    repeats.add_argument("--limit", type=int, default=40)
    repeats.add_argument("--verbose", "-v", action="store_true",
                         help="list each hearing in the episode")
    repeats.add_argument("--all", action="store_true",
                         help="ignore the score and safety gate")
    repeats.set_defaults(func=cmd_repeats)

    oncam = sub.add_parser("oncamera")
    oncam.add_argument("case_key")
    oncam.add_argument("--frames", type=int, default=6)
    oncam.add_argument("--refresh", action="store_true",
                       help="re-sample instead of reusing kept frames")
    oncam.set_defaults(func=cmd_oncamera)

    mom = sub.add_parser("moments")
    mom.add_argument("--top", type=int, default=20)
    mom.add_argument("--video", help="restrict to one docket id")
    mom.add_argument("--json", help="also write every moment to this path")
    mom.set_defaults(func=cmd_moments)

    sub.add_parser("cleanup").set_defaults(func=cmd_cleanup)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
