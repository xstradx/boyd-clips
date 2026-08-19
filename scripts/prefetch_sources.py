"""Pre-download the source section for the best-scoring cases in the bank.

THE BOTTLENECK THIS FIXES. 273 cases clear the safety gate and the rubric, but
only 27 have a downloaded section, so 246 cannot be rendered, thumbnailed or
shown in the picker. Everything downstream has been choosing from the ~10% of
the bank that happened to be fetched already — including every thumbnail round
so far.

WHY THE OBVIOUS LOOP DOES NOT WORK. `yt-dlp` on this docket does not fail
cleanly under rate limiting; it HANGS. Observed twice: the process alive at 0%
CPU, a `.part` file frozen at a fixed size, no error, no exit. `--retries` does
not help because nothing errored, and `--socket-timeout` does not fire because
the socket is not idle in a way it recognises. A run left alone in that state
sat for roughly nine hours.

So the retry logic here is a STALL WATCHDOG, not an error handler: watch the
`.part` file, and if it stops growing for `stall_s`, kill the process and start
again. That is the only signal that actually distinguishes "throttled" from
"slow", and it is measured from the filesystem rather than from yt-dlp.

Sequential on purpose. Parallel downloads are what provoked the throttling in
the first place, and the goal is a full bank by morning, not a fast burst that
gets the machine blocked.

    python scripts/prefetch_sources.py --top 60
    python scripts/prefetch_sources.py --top 60 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                             # noqa: E402
from boydclips.transcribe import Transcript                      # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "state" / "pipeline.db"

PAD_BEFORE = 24.0
PAD_AFTER = 24.0
STALL_S = 45.0          # no growth for this long = throttled, restart
ATTEMPTS = 2            # per player client; a stall is worth exactly one retry
MAX_ATTEMPTS = 6        # total, across clients — bounds an unattended run
COOLDOWN_S = 8.0        # between cases, to stay under the rate limiter


def attempt_cap_s(span_s: float) -> float:
    """Wall-clock ceiling for one download attempt.

    This used to be a flat 900s on the reasoning that "a section should never
    legitimately take 15 min". That is false for this bank: `--force-keyframes-
    at-cuts` re-encodes, which runs at roughly real time, and the case windows
    are not short — JgvW7oCQxuI_6698-8866 is 36 minutes and JjRfzudxY1w_5043-
    7223 is 36 minutes. Any such case hit the cap, was recorded as "stalled",
    and was retried until the attempts ran out, so it could never be fetched no
    matter how healthy the connection was. The cap exists to catch a frozen
    process, and the stall watchdog already does that from the filesystem, so
    this only needs to be generous enough not to fire on honest work.
    """
    return max(900.0, 3.0 * span_s + 120.0)


def cached_sections(video_id: str) -> list[tuple[float, float]]:
    out = []
    for p in (ROOT / "work" / video_id).glob(f"{video_id}_*-*.mp4"):
        try:
            a, b = p.stem.rsplit("_", 1)[-1].split("-")
            out.append((float(a), float(b)))
        except ValueError:
            continue
    return out


def already_have(video_id: str, start_s: float) -> bool:
    return any(a <= start_s < b for a, b in cached_sections(video_id))


def ranked_cases() -> list[dict]:
    """Eligible, safety-passed cases ordered by banger score."""
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    tcache: dict[str, Transcript] = {}
    rows = []
    for r in db.execute("SELECT video_id, payload FROM cases"):
        p = json.loads(r["payload"])
        if not (p.get("eligible") and (p.get("safety") or {}).get("safety_pass")):
            continue
        vid = r["video_id"]
        tp = ROOT / "work" / vid / f"{vid}.transcript.json"
        if not tp.is_file():
            continue
        rows.append({
            "video_id": vid,
            "case_key": f'{vid}:{int(round(p["start_s"]))}',
            "start_s": float(p["start_s"]),
            "end_s": float(p["end_s"]),
            "name": p.get("defendant_name") or "?",
            "score": float(p.get("total_score") or 0),
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


def fetch(case: dict) -> bool:
    """Download one section, restarting on stall. True if a file landed.

    Two failure modes, two mechanisms. A *stall* is throttling and is retried
    on the same player client (see the watchdog below). A clean non-zero exit
    is usually the whole client being unusable for this video, so the next
    attempt moves down render.SECTION_PLAYER_CLIENTS instead of repeating a
    request that already answered definitively. The default client is last
    because googlevideo now truncates its URLs after ~3 MB, which is what left
    246 of 273 cases unfetched.
    """
    vid = case["video_id"]
    work = ROOT / "work" / vid
    work.mkdir(parents=True, exist_ok=True)
    start = max(0.0, case["start_s"] - PAD_BEFORE)
    end = case["end_s"] + PAD_AFTER
    target = work / f'{vid}_{int(round(case["start_s"]))}_{start:.0f}-{end:.0f}.mp4'

    cap_s = attempt_cap_s(end - start)
    plan = [(c, a) for c in render.SECTION_PLAYER_CLIENTS
            for a in range(1, ATTEMPTS + 1)][:MAX_ATTEMPTS]

    for step, (client, attempt) in enumerate(plan, 1):
        # A .part from a previous attempt may still be held open by a yt-dlp
        # that has not finished dying - Windows raises WinError 32 rather than
        # letting the unlink through, and an unhandled one killed a whole run.
        # A leftover .part is harmless; failing to delete it is not.
        for stale in work.glob("*.part"):
            try:
                stale.unlink()
            except OSError:
                pass

        proc = subprocess.Popen(
            [sys.executable, "-m", "yt_dlp", "--no-warnings", "--ignore-config",
             "--retries", "5", "--fragment-retries", "5", "--extractor-retries", "3",
             "--socket-timeout", "30",
             # Both flags are load-bearing and only work together: node solves
             # the n-signature challenge, without which web_embedded reports
             # "Requested format is not available" and yt-dlp drops back to the
             # truncated default client.
             "--js-runtimes", "node",
             *(() if client == "default" else
               ("--extractor-args", f"youtube:player_client={client}")),
             "--download-sections", f"*{start:.2f}-{end:.2f}",
             "--force-keyframes-at-cuts",
             "-f", "bv*[vcodec^=avc1][height<=720]+ba[acodec^=mp4a]/"
                   "bv*[height<=720]+ba/b[height<=720]/b",
             "-o", str(target),
             f"https://www.youtube.com/watch?v={vid}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        stalled = threading.Event()

        def watchdog() -> None:
            last_size, last_change = -1, time.time()
            began = time.time()
            while proc.poll() is None:
                time.sleep(3)
                size = sum(p.stat().st_size for p in work.glob("*.part")) \
                    + (target.stat().st_size if target.exists() else 0)
                now = time.time()
                if size != last_size:
                    last_size, last_change = size, now
                if now - last_change > STALL_S or now - began > cap_s:
                    stalled.set()
                    proc.kill()
                    return

        th = threading.Thread(target=watchdog, daemon=True)
        th.start()
        proc.wait()
        th.join(timeout=5)

        if target.exists() and target.stat().st_size > 200_000:
            mb = target.stat().st_size / 1e6
            print(f"    ok  {target.name}  {mb:.0f} MB  [{client}]")
            return True
        why = "stalled" if stalled.is_set() else f"exit {proc.returncode}"
        print(f"    {client} attempt {attempt}/{ATTEMPTS} failed ({why})")
        target.unlink(missing_ok=True)
        # A stall is transient, so the retry on this client is worth waiting
        # for. A clean exit means this client has nothing to give, so drop the
        # remaining attempts on it and move on rather than burning the backoff.
        if not stalled.is_set():
            del plan[step:step + ATTEMPTS - attempt]
            continue
        time.sleep(10 * attempt)          # linear backoff between attempts
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    # Fetch what the ARCS need rather than what scores highest in isolation.
    # An arc is only renderable when EVERY chapter is cached, so fetching the
    # single best case from ten different defendants produces zero videos —
    # which is exactly what happened: 1 chapter cached across 13 arcs.
    ap.add_argument("--queue", type=Path, default=None,
                    help="JSON list of {video_id,case_key,start_s,end_s}")
    ap.add_argument("--dry-run", action="store_true")
    # Cases to leave alone. Nathan, 2026-08-18: drop Pena.
    ap.add_argument("--skip", default="", help="comma-separated case keys or video ids")
    a = ap.parse_args()

    if a.queue:
        import json as _json
        cases = _json.loads(a.queue.read_text(encoding="utf-8"))
        cases.sort(key=lambda c: -float(c.get("score") or 0))
    else:
        cases = ranked_cases()
    skip = {x.strip() for x in a.skip.split(",") if x.strip()}
    todo = [c for c in cases
            if not already_have(c["video_id"], c["start_s"])
            and c["case_key"] not in skip and c["video_id"] not in skip][: a.top]
    have = len(cases) - len([c for c in cases
                             if not already_have(c["video_id"], c["start_s"])])
    print(f"{len(cases)} scored cases, {have} already cached, "
          f"fetching top {len(todo)}\n")

    if a.dry_run:
        for c in todo:
            print(f"  {c['score']:6.0f}  {c['case_key']:22} {c['name'][:28]}")
        return 0

    ok = 0
    for i, c in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {c['score']:.0f}  {c['case_key']}  {c['name'][:30]}")
        if fetch(c):
            ok += 1
        time.sleep(COOLDOWN_S)
    print(f"\n{ok}/{len(todo)} fetched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
