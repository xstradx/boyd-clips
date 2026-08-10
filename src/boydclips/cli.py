"""Command line entry point.

    boyd doctor                 check the environment before trusting a cron job
    boyd discover               list new dockets, touch nothing else
    boyd run [--dry-run]        the daily pipeline
    boyd run --case <case_key>  render one specific defendant's case
    boyd approve <case_key>     record approval and publish a held clip
    boyd reject <case_key>      record rejection with a reason
    boyd stats                  reliability ledger and promotion readiness
    boyd bank                   banked runner-up cases
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
    if args.case:
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
    run.add_argument("--dry-run", action="store_true",
                     help="analyse and select, but download and render nothing")
    run.add_argument("--limit", type=int, default=None,
                     help="override output.clips_per_day")
    run.add_argument("--case", default=None, metavar="CASE_KEY",
                     help="render one specific scored case instead of the "
                          "day's top pick (see `boyd bank` for keys)")
    run.set_defaults(func=cmd_run)

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
