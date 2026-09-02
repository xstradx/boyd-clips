# -*- coding: utf-8 -*-
"""thumbeng.engine - the one CLI that drives the five modules.

    python tools/thumbeng/engine.py harvest  --channel UCT5Fde6OzBSFRmxw5mPn2CA
    python tools/thumbeng/engine.py measure  --dir "D:/Boyd Clips/READY-TO-POST"
    python tools/thumbeng/engine.py styles   --niche <name>
    python tools/thumbeng/engine.py grammar  --niche <name>
    python tools/thumbeng/engine.py critique --image <path> --niche <name>
    python tools/thumbeng/engine.py compare  A.jpg B.jpg --niche <name>
    python tools/thumbeng/engine.py all      --channel UC... --niche <name>
    python tools/thumbeng/engine.py status   --niche <name>

WHY THIS FILE EXISTS AT ALL, given every module already has its own main():
the five were built in parallel against one written contract, and a contract
does not stop five argument parsers disagreeing about what a niche is, which
stage may assume another stage ran, or what happens when a stage produces
nothing. This module is the single place those questions are answered, and it
is deliberately THIN - it calls the library functions, it does not
re-implement any of them, and it owns no thresholds of its own.

THE ONE PIECE OF REAL LOGIC HERE: niche derivation. `harvest --channel UC...`
with no --niche has to land somewhere deterministic, because every later stage
addresses its work by niche name. It resolves to slug(channel-or-query) and is
PRINTED on the first line of every run, so the name the next command needs is
never something the reader has to guess. Deterministic rather than
timestamped, so re-running the same harvest re-enters the same directory
instead of littering work/thumbeng with near-duplicates.

STAGE ORDER IS ENFORCED, NOT ASSUMED. harvest -> measure -> styles -> grammar
-> critique. Each stage here checks that its input exists and refuses with one
line naming the command that would produce it, rather than letting an empty
list travel three stages downstream and become a grammar built on nothing.
Exit codes: 0 ran, 2 refused (bad arguments or a missing prerequisite),
1 crashed.
"""

import os
import sys
import argparse
import importlib
import time

# --------------------------------------------------------------------- import
# `python -m tools.thumbeng.engine` sets __package__; a bare
# `python tools/thumbeng/engine.py` does not. Both must reach the same modules.
# The REPO ROOT goes on sys.path, never tools/ itself: tools/harvest.py is a
# pre-existing and unrelated courtroom-frame harvester, and putting tools/ on
# the path would let a bare `import harvest` bind the wrong file.
if __package__ in (None, ""):                    # pragma: no cover
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    __package__ = "tools.thumbeng"

from . import (SCHEMA_VERSION, WORK_ROOT, niche_dir, read_json,  # noqa: E402
               slug, utc_now)

# Sibling modules are imported lazily rather than at module scope: `status` and
# `--help` must still work on a machine where sklearn or scipy is mid-upgrade,
# and an import error inside styles.py should not stop someone reading a
# finished grammar.
_MODCACHE = {}


def _mod(name):
    """Import a sibling engine module on demand, raising with the stage named.

    A bare ImportError from three levels down reads as "the engine is broken";
    naming the stage says which one file to look at.
    """
    if name not in _MODCACHE:
        try:
            _MODCACHE[name] = importlib.import_module(__package__ + "." + name)
        except Exception as exc:                 # noqa: BLE001
            raise RuntimeError("stage %r could not be imported: %s: %s"
                               % (name, type(exc).__name__, exc))
    return _MODCACHE[name]


# ------------------------------------------------------------------- printing
def out(text=""):
    """Print without letting a console codepage kill a finished run.

    This terminal's stdout is cp1252. Competitor titles carry em-dashes and
    emoji, and a UnicodeEncodeError on the LAST print of a twelve-minute
    harvest would lose the whole report. Replacing the character is a cosmetic
    loss; the JSONL on disk is UTF-8 and intact.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(str(text).encode(enc, "replace").decode(enc, "replace"))
    try:
        sys.stdout.flush()
    except Exception:                            # noqa: BLE001
        pass


def rule(title):
    out("")
    out("=" * 78)
    out(title)
    out("=" * 78)


def _fail(msg, hint=None):
    """One line to stderr and exit 2. Never a traceback for a foreseeable state."""
    sys.stderr.write("engine: %s\n" % msg)
    if hint:
        sys.stderr.write("        try: %s\n" % hint)
    sys.stderr.flush()
    return 2


# --------------------------------------------------------------- niche naming
def resolve_niche(args, *candidates):
    """Return the niche name for this run, deriving one when --niche is absent.

    Derivation is the first non-empty candidate run through slug(). It is
    deterministic on purpose: `harvest --channel UC...` twice must re-enter the
    same directory rather than create a second one.

    A channel id slugs to its own lowercased id. That is the FALLBACK, not the
    first choice: cmd_harvest asks the network for the channel's display name
    first (see _channel_niche), because the derived name is what every later
    command has to be typed with, and 'uct5fde6ozbsfrmxw5mpn2ca' is a name
    nobody can retype from memory.
    """
    if getattr(args, "niche", None):
        return slug(args.niche)
    for c in candidates:
        if isinstance(c, (list, tuple)):
            c = c[0] if c else None
        if c:
            s = slug(c)
            if s:
                return s
    return ""


def _paths_in(d):
    """Every path the engine knows about, under one already-resolved directory.

    Split out from _niche_paths because `status` enumerates the directories
    that are actually ON DISK, and re-slugging a directory name is not a
    round trip: slug('_dryrun') is 'dryrun', so status printed counts for a
    directory that did not exist and reported zero thumbs for a niche that had
    them. A name from the filesystem is used as-is.
    """
    return {
        "dir": d,
        "thumbs": d + "/thumbs",
        "harvest": d + "/harvest.jsonl",
        "channels": d + "/channels.json",
        "measurements": d + "/measurements.jsonl",
        "csv": d + "/measurements.csv",
        "styles": d + "/styles.json",
        "grammar": d + "/grammar.json",
        "critique": d + "/critique",
        "run": d + "/run.json",
    }


def _niche_paths(niche):
    return _paths_in(niche_dir(niche, create=False))


def _count_images(d):
    """Count IMAGE files in a directory, not directory entries.

    harvest.py writes a '<video_id>.jpg.meta.json' sidecar beside every
    thumbnail it fetches, recording which quality won and at what dimensions.
    Counting entries therefore reported 32 thumbs for a 16-video channel -
    a doubled number in the one place that exists to state the truth about
    what ran.

    The extension set is taken from measure.IMAGE_PATTERNS so it cannot drift
    from what measure_folder will actually pick up, with a literal fallback so
    `status` still answers on a machine where measure.py cannot import (its
    whole point is to work when something else is broken).
    """
    if not os.path.isdir(d):
        return 0
    try:
        exts = set(os.path.splitext(p)[1].lower()
                   for p in _mod("measure").IMAGE_PATTERNS)
    except Exception:                            # noqa: BLE001
        exts = {".jpg", ".jpeg", ".png", ".webp"}
    return sum(1 for f in os.listdir(d)
               if os.path.splitext(f)[1].lower() in exts)


def _channel_niche(hv, channel):
    """Name a channel-only harvest after the channel, not after its id.

    MEASURED, 2026-08-30: a flat listing capped at one row answers in 0.7s and
    carries playlist_channel = 'Texas Trial Tracker'. That is cheap enough to
    spend before a harvest that will take minutes, and it is the difference
    between the next command reading `--niche texas-trial-tracker` and
    `--niche uct5fde6ozbsfrmxw5mpn2ca`.

    Note the field: a flat CHANNEL listing returns channel/channel_id as None
    and carries the name under playlist_channel only. normalise_row already
    knows this; the lookup is repeated here rather than imported because
    normalise_row wants a whole row and this wants one string.

    Returns None on any failure - offline, a private channel, a bad id - so the
    caller falls back to slugging the argument rather than dying on a
    cosmetic lookup.
    """
    try:
        rows = hv.channel_videos(channel, limit=1, timeout=60)
    except Exception:                            # noqa: BLE001
        return None
    for r in rows or []:
        name = (r.get("playlist_channel") or r.get("channel")
                or r.get("playlist_uploader") or r.get("uploader"))
        if name:
            s = slug(name)
            if s:
                return s
    return None


def _resolve_harvest_niche(args):
    """The ONE place a harvest-shaped command decides its niche name.

    cmd_harvest and cmd_all must agree. They did not: cmd_all called
    resolve_niche directly and so skipped the channel-name lookup, which meant
    `engine.py all --channel UCT5...` built a second directory
    'uct5fde6ozbsfrmxw5mpn2ca' beside the 'texas-trial-tracker' that
    `engine.py harvest --channel UCT5...` had already filled - two harvests of
    one channel, and a later --niche pointing at whichever of the two the
    reader happened to remember. Same input, same directory, from either
    entry point.
    """
    if getattr(args, "niche", None):
        return slug(args.niche)
    if args.channel and not args.query:
        named = _channel_niche(_mod("harvest"), args.channel[0])
        if named:
            return named
    return resolve_niche(args, args.channel, args.query)


def _need(path, what, hint):
    """Refuse a stage whose input is missing, naming the command that makes it."""
    if not os.path.exists(path):
        return _fail("no %s at %s" % (what, path), hint)
    return 0


def _banner(niche, stage):
    p = _niche_paths(niche)
    out("niche: %s" % niche)
    out("dir:   %s" % p["dir"])
    out("stage: %s   schema_version=%d   %s"
        % (stage, SCHEMA_VERSION, utc_now()))
    return p


# ==========================================================================
# Stages
# ==========================================================================

def cmd_harvest(args):
    """Find videos in a niche, pull their thumbnails, score each against its own
    channel's normal views-per-day."""
    hv = _mod("harvest")
    if not args.query and not args.channel:
        return _fail("give --query and/or --channel",
                     'engine.py harvest --query "courtroom judge sentencing"')
    niche = _resolve_harvest_niche(args)
    if not niche:
        return _fail("nothing to name the niche after",
                     "engine.py harvest --channel UC... [--niche NAME]")
    args.niche = niche
    p = _banner(niche, "harvest")

    t0 = time.time()
    man = hv.harvest(niche,
                     query=args.query,
                     channel_ids=list(args.channel or []),
                     limit=args.limit,
                     baseline_limit=args.baseline_limit,
                     deepen_channels=not args.no_deepen,
                     fetch_thumbs=not args.no_thumbs,
                     max_thumbs=args.max_thumbs,
                     progress=True)

    rows = hv.load_harvest(niche)
    rule("HARVESTED VIDEOS (top %d)" % args.top)
    out(hv.render_table(rows, top_n=args.top))
    ch = read_json(p["channels"], default={}) or {}
    rule("CHANNEL BASELINES")
    out(hv.render_channels(ch.get("channels", {})))

    rule("HARVEST RESULT")
    out("found=%d  with_thumb=%d  settled=%d  scored=%d  channels=%d  usable=%d"
        % (man["n_found"], man["n_with_thumb"], man["n_settled"],
           man["n_scored"], man["n_channels"], man["n_usable_channels"]))
    for w in man.get("warnings") or []:
        out("warning: %s" % w)
    out("wrote: %s" % man["harvest_jsonl"])
    out("elapsed: %.1fs" % (time.time() - t0))
    out("")
    out("next: python tools/thumbeng/engine.py measure --niche %s" % niche)
    return 0


def cmd_measure(args):
    """Measure every thumbnail into the 133-key vocabulary.

    Two entry shapes. --niche measures that niche's own harvested thumbs and
    defaults source_kind to 'youtube'; --dir measures an arbitrary folder and
    defaults to 'local'. That default is load-bearing rather than cosmetic:
    verify_thumb.py measured that 10 of 12 competitor thumbnails trip the
    posterisation gate purely because YouTube re-encodes them, so critique.py is
    forbidden from raising that gate as a defect on a 'youtube' row. Calling a
    downloaded image 'local' condemns work that is fine.
    """
    ms = _mod("measure")
    if not args.dir and not args.niche:
        return _fail("give --niche or --dir",
                     'engine.py measure --dir "D:/Boyd Clips/READY-TO-POST"')

    if args.dir:
        folder = str(args.dir).replace("\\", "/").rstrip("/")
        if not os.path.isdir(folder):
            return _fail("not a folder: %s" % folder)
        niche = resolve_niche(args, os.path.basename(folder) or "folder")
        source_kind = args.source_kind or "local"
        p = _banner(niche, "measure")
        niche_dir(niche, create=True)
        out("source: %s  (source_kind=%s)" % (folder, source_kind))
        started = utc_now()
        # Default is measure.IMAGE_PATTERNS (jpg/jpeg/png/webp), because a
        # folder of PNGs measured as zero files and called a success is the
        # worse failure. But READY-TO-POST mixes real thumbnails with PNG
        # contact sheets - AB_THUMBNAILS.png measures 30 faces and
        # COURTROOMTIME_WINNERS_vs_LOSERS.png measures 58, which are grids of
        # thumbnails, not thumbnails - so narrowing has to be reachable
        # without editing code.
        pats = tuple(args.pattern) if args.pattern else ms.IMAGE_PATTERNS
        out("pattern: %s" % (list(pats),))
        rows = ms.measure_folder(folder,
                                 out_jsonl=p["measurements"],
                                 out_csv=p["csv"],
                                 pattern=pats,
                                 source_kind=source_kind,
                                 skip_existing=not args.no_cache,
                                 progress=True)
        # measure_niche writes its own manifest; measure_folder does not, so the
        # ad-hoc path records one here rather than leaving a hole in run.json.
        from . import run_manifest
        run_manifest(niche, "measure",
                     {"folder": folder, "source_kind": source_kind},
                     {"n_measured": len(rows),
                      "n_errors": sum(1 for r in rows
                                      if r.get("measure_error"))},
                     started_utc=started, ok=True)
    else:
        niche = slug(args.niche)
        source_kind = args.source_kind or "youtube"
        p = _banner(niche, "measure")
        rc = _need(p["thumbs"], "thumbs/ directory",
                   "engine.py harvest --niche %s --channel UC..." % niche)
        if rc:
            return rc
        out("source: %s  (source_kind=%s)" % (p["thumbs"], source_kind))
        rows = ms.measure_niche(niche, source_kind=source_kind)

    if not rows:
        return _fail("0 images measured",
                     "check the folder actually holds images")

    errs = [r for r in rows if r.get("measure_error")]
    rule("MEASURED")
    out(ms.render_table([r for r in rows if not r.get("measure_error")]))
    rule("MEASURE RESULT")
    out("measured=%d  clean=%d  errors=%d  keys=%d"
        % (len(rows), len(rows) - len(errs), len(errs), len(ms.FEATURE_KEYS)))
    for r in errs:
        out("  error %s: %s" % (r.get("image_id"), r.get("measure_error")))
    out("wrote: %s" % p["measurements"])
    out("wrote: %s" % p["csv"])
    out("")
    # The next step depends on whether this niche has performance data at all.
    # A folder of Nathan's own exports has no harvest.jsonl and never will, so
    # pointing it at `grammar` would be advice that cannot work: grammar needs
    # outlier scores, and a local folder has none.
    if os.path.exists(p["harvest"]):
        out("next: python tools/thumbeng/engine.py grammar --niche %s" % niche)
    else:
        out("note: no harvest.jsonl in this niche, so there are no outlier "
            "scores and `grammar` cannot run here. A folder of local exports "
            "is a set of candidates, not a measured population.")
        out("next: python tools/thumbeng/engine.py critique --image <path> "
            "--niche <a harvested niche>")
    return 0


def cmd_styles(args):
    """Cluster the measured vectors into the niche's recurring styles."""
    st = _mod("styles")
    niche = slug(args.niche or "")
    if not niche:
        return _fail("--niche is required")
    p = _banner(niche, "styles")
    rc = _need(p["measurements"], "measurements.jsonl",
               "engine.py measure --niche %s" % niche)
    if rc:
        return rc
    try:
        res = st.discover_styles(niche, k=args.k, min_members=args.min_members)
    except ValueError as exc:
        # The commonest refusal by far: auto-k needs 10 measured thumbnails, and
        # a 16-video channel that lost some to a fallback quality can sit under
        # it. That is a real limit of the sample, not a crash.
        return _fail(str(exc),
                     "engine.py styles --niche %s --k 2   (forces k)" % niche)
    rule("STYLES")
    out(st.render_styles(res))
    out("")
    out("wrote: %s" % p["styles"])
    out("next: python tools/thumbeng/engine.py grammar --niche %s" % niche)
    return 0


def cmd_grammar(args):
    """Derive what separates this niche's winners from its losers."""
    gr = _mod("grammar")
    niche = slug(args.niche or "")
    if not niche:
        return _fail("--niche is required")
    p = _banner(niche, "grammar")
    rc = _need(p["measurements"], "measurements.jsonl",
               "engine.py measure --niche %s" % niche)
    if rc:
        return rc
    rc = _need(p["harvest"], "harvest.jsonl",
               "engine.py harvest --niche %s --channel UC..." % niche)
    if rc:
        return rc

    # styles.json is optional INPUT, not a prerequisite: build_grammar uses it
    # only to attach a style_summary, and a grammar without one is still a
    # grammar.
    styles = None
    if os.path.exists(p["styles"]):
        try:
            styles = _mod("styles").load_styles(niche)
        except Exception as exc:                 # noqa: BLE001
            out("note: styles.json present but unreadable (%s); building "
                "grammar without it" % exc)

    g = gr.build_grammar(niche, win_at=args.win, lose_at=args.lose,
                         styles=styles)
    rule("NICHE GRAMMAR")
    out(gr.render_grammar(g, top_n=args.top))
    out("")
    out("wrote: %s" % p["grammar"])
    out("next: python tools/thumbeng/engine.py critique --image <path> "
        "--niche %s" % niche)
    return 0


def _infer_source_kind(images):
    """'youtube' when every candidate is a harvested thumbnail, else 'local'.

    This is not a convenience. verify_thumb.py measured that 10 of 12
    competitor thumbnails trip the posterisation gate purely because YouTube
    re-encodes them (quant table sum 736 against 369 for a local export), so
    the contract forbids that gate from raising a defect on a 'youtube' row.
    MEASURED on this machine: the harvested thumb o1S6Kbnckro.jpg scores
    39.0/rebuild when called 'local' and 60.0/fix when called 'youtube', on the
    same pixels - the whole difference is one gate that should never have
    fired. A flat default of 'local' therefore condemns every downloaded
    thumbnail the moment anyone critiques one without remembering the flag.

    The test is positional: anything living under WORK_ROOT/<niche>/thumbs was
    put there by harvest.py and by nothing else. A mixed list falls back to
    'local', which is the conservative direction - it can only over-report.
    """
    if not images:
        return "local"
    root = WORK_ROOT.replace("\\", "/").rstrip("/").lower()
    for img in images:
        a = os.path.abspath(str(img)).replace("\\", "/").lower()
        if not (a.startswith(root + "/") and "/thumbs/" in a):
            return "local"
    return "youtube"


def cmd_critique(args):
    """Score one or more candidates against the niche grammar."""
    cr = _mod("critique")
    niche = slug(args.niche or "") or None
    images = list(args.image or []) + list(getattr(args, "rest", None) or [])
    if not images:
        return _fail("give --image PATH (repeatable)",
                     'engine.py critique --image "D:/x.jpg" --niche court')
    missing = [i for i in images if not os.path.exists(i)]
    if missing:
        return _fail("no such image: %s" % missing[0])

    source_kind = args.source_kind or _infer_source_kind(images)
    if not args.source_kind:
        out("source_kind: %s (inferred from the path; override with "
            "--source-kind)" % source_kind)

    grammar = None
    if niche:
        _banner(niche, "critique")
        p = _niche_paths(niche)
        if os.path.exists(p["grammar"]):
            try:
                grammar = _mod("grammar").load_grammar(niche)
            except Exception as exc:             # noqa: BLE001
                out("note: grammar.json unreadable (%s); principles only" % exc)
        else:
            # Not a refusal. critique() is explicitly designed to run before any
            # harvest exists, and saying so beats pretending a grammar was used.
            out("note: no grammar.json for niche %r - general principles only, "
                "no measured niche findings" % niche)
    else:
        out("niche: (none) - general principles only")

    if len(images) > 1 or args.compare:
        reports, table = cr.compare(images, grammar=grammar, niche=niche,
                                    source_kind=source_kind)
        rule("COMPARE")
        out(table)
        scored = [r for r in reports
                  if isinstance(r.get("overall_score"), (int, float))]
        return 0 if scored else 1

    rep = cr.critique(images[0], niche=niche, grammar=grammar,
                      source_kind=source_kind, top_n=args.top)
    rule("CRITIQUE")
    out(cr.render_report(rep, top_n=args.top))

    # VARIETY. The one question nothing else in this engine asks: how does this
    # compare to YOUR OWN back catalogue rather than to the niche. Reported
    # separately from the defect list on purpose - it carries a different kind
    # of evidence (a measured comparison of your own files) and, crucially, the
    # 2026-08-31 result that NO image feature predicts performance means it must
    # not be dressed up as a performance claim.
    if args.history:
        var = _mod("variety")
        v = var.check(images[0], args.history)
        rule("VARIETY  (vs your own shipped thumbnails)")
        out("  compared against %d shipped thumbnails" % v["n_compared"])
        if v["n_compared"]:
            out("  closest is %s at %.3f   limit %.2f"
                % (v["most_similar_to"], v["max_similarity"], v["limit"]))
            if v["repeats_own_work"]:
                out("  !! REPEATS OWN WORK - this is the layout you already shipped.")
                out("     Measured: our own four sat at mean 0.32 self-similarity "
                    "while the competitor set sat at 0.09.")
                out("     NOT a performance claim: no image feature was found to "
                    "predict outperformance (231 win vs 259 lose, 126 features).")
            else:
                out("  breaks from your recent layouts")
    if niche:
        out("")
        out("wrote: %s/critique/%s.json"
            % (_niche_paths(niche)["dir"],
               cr._safe_stem(rep["candidate"]["image_id"])))
    return 0


def cmd_all(args):
    """Run the whole pipeline in order, stopping at the first stage that refuses.

    styles is treated as ADVISORY: it is the only stage whose refusal is not a
    reason to stop, because grammar.py takes styles.json as optional input and a
    16-video channel routinely sits under the 10 measured thumbnails auto-k
    needs. Stopping the pipeline there would withhold a grammar that the sample
    fully supports.
    """
    if not args.query and not args.channel:
        return _fail("give --query and/or --channel",
                     "engine.py all --channel UC...")
    niche = _resolve_harvest_niche(args)
    if not niche:
        return _fail("nothing to name the niche after")
    args.niche = niche
    for name, fn, fatal in (("harvest", cmd_harvest, True),
                            ("measure", cmd_measure, True),
                            ("styles", cmd_styles, False),
                            ("grammar", cmd_grammar, True)):
        rc = fn(args)
        if rc and fatal:
            sys.stderr.write("engine: pipeline stopped at %s (rc=%d)\n"
                             % (name, rc))
            return rc
        if rc:
            out("note: %s did not run (rc=%d); continuing - it is optional "
                "input to grammar, not a prerequisite" % (name, rc))
    if args.image:
        return cmd_critique(args)
    return 0


def cmd_status(args):
    """Show what has run, when, and with what counts - one read, no guessing.

    Anything this engine builds shows its own state; nobody should have to open
    five JSON files to answer "did the harvest finish".
    """
    if args.niche:
        niches = [niche_dir(args.niche, create=False)]
    else:
        listing = os.listdir(WORK_ROOT) if os.path.isdir(WORK_ROOT) else []
        niches = sorted(WORK_ROOT + "/" + d for d in listing
                        if os.path.isdir(WORK_ROOT + "/" + d))
    if not niches:
        out("no niches under %s" % WORK_ROOT)
        return 0
    for d_abs in niches:
        n = os.path.basename(d_abs)
        if not os.path.isdir(d_abs):
            # A named niche that has never been harvested printed as a row of
            # zeros, which reads as "ran and found nothing" rather than
            # "never ran". Those are different answers.
            out("")
            out("%s  (%s)" % (n, d_abs))
            out("  no such niche on disk - nothing has run for this name")
            continue
        p = _paths_in(d_abs)
        run = read_json(p["run"], default={}) or {}
        stages = run.get("stages", {})
        n_thumbs = _count_images(p["thumbs"])
        n_crit = (len([f for f in os.listdir(p["critique"])
                       if f.lower().endswith(".json")])
                  if os.path.isdir(p["critique"]) else 0)
        out("")
        out("%s  (%s)" % (n, p["dir"]))
        out("  thumbs=%d  critiques=%d" % (n_thumbs, n_crit))
        for stage in ("harvest", "measure", "styles", "grammar"):
            e = stages.get(stage)
            if not e:
                out("  %-8s -" % stage)
                continue
            counts = ", ".join("%s=%s" % (k, v)
                               for k, v in (e.get("counts") or {}).items())
            out("  %-8s %s  %s  %s"
                % (stage, "ok " if e.get("ok") else "FAIL",
                   e.get("finished_utc"), counts))
            if e.get("error"):
                out("           error: %s" % e["error"])
    return 0


def cmd_selftest(args):
    """Run every module's selftest and report one aggregate line.

    Each module already prints SELFTEST_PASS / SELFTEST_FAIL in verify_thumb's
    convention; this only aggregates, so a green line here means N green lines
    above it and not one more checker with an opinion of its own.

    MODULES is derived, not a literal count - the first version hardcoded "5/5"
    and would have kept reporting 5/5 after variety.py joined on 2026-08-31,
    silently never running it.
    """
    bad = []
    MODULES = ("measure", "harvest", "styles", "grammar", "critique", "variety")
    for name in MODULES:
        rule("SELFTEST %s" % name)
        try:
            rc = _mod(name).selftest()
        except Exception as exc:                 # noqa: BLE001
            out("%s raised %s: %s" % (name, type(exc).__name__, exc))
            rc = 1
        if rc:
            bad.append(name)
    rule("ENGINE SELFTEST")
    out("ENGINE_SELFTEST_%s  (%d/%d modules pass)%s"
        % ("FAIL" if bad else "PASS", len(MODULES) - len(bad), len(MODULES),
           ("  failed: " + ", ".join(bad)) if bad else ""))
    return 1 if bad else 0


# ==========================================================================
# CLI
# ==========================================================================

def cmd_ingest(args):
    """Video in: transcript + candidate frames. Ported from the retired
    Projects/thumbnail-engine on 2026-08-31, which was the only place in this
    codebase that could take a VIDEO rather than an image."""
    from . import ingest as I
    try:
        d = I.run(args.video, args.out, model_size=args.asr_model)
    except I.Refused as e:
        out(f"REFUSED: {e}")
        return 3
    out(f"  words={d['words']}  frames={len(d['frames'])}  "
        f"faces_present={d['has_face']}  asr={d['asr_device']}")
    out(f"INGEST_OK frames={len(d['frames'])}")
    return 0


def cmd_understand(args):
    """Name the niche from the video itself, so `harvest --query` does not have
    to be supplied by hand. Also ported 2026-08-31."""
    from . import understand as U
    u = U.run(args.inp, model=args.vision_model)
    for k in ("niche", "search_query", "headline", "subject", "emotion"):
        out(f"  {k:<14} {u[k]}")
    out(f"UNDERSTAND_OK query={u['search_query']!r}")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="engine.py",
        description="thumbnail engine: harvest -> measure -> styles -> "
                    "grammar -> critique",
        epilog="Every stage addresses its work by NICHE name, never a raw "
               "path. When --niche is omitted it is derived from the channel "
               "or query and printed on the first line of the run.")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--niche",
                       help="niche name; becomes work/thumbeng/<slug>")
        return p

    # VIDEO IN. Ported from Projects/thumbnail-engine 2026-08-31 - that project
    # is retired and these were the only two things in it this codebase lacked.
    ing = sub.add_parser("ingest", help="video -> transcript + candidate frames")
    ing.add_argument("--video", required=True)
    ing.add_argument("--out", required=True)
    ing.add_argument("--asr-model", default="small.en")
    ing.set_defaults(fn=cmd_ingest)

    und = sub.add_parser("understand",
                         help="name the niche and a search query FROM the video")
    und.add_argument("--in", dest="inp", required=True)
    und.add_argument("--vision-model", dest="vision_model", default=None)
    und.set_defaults(fn=cmd_understand)

    h = common(sub.add_parser("harvest",
                              help="find videos, pull thumbnails, score outliers"))
    h.add_argument("--channel", action="append", default=[],
                   help="channel id, @handle or URL (repeatable)")
    h.add_argument("--query", help="YouTube search query")
    h.add_argument("--limit", type=int, default=60)
    h.add_argument("--baseline-limit", type=int, default=60)
    h.add_argument("--no-deepen", action="store_true",
                   help="skip the per-channel baseline pass; every "
                        "outlier_score from a search then stays NaN")
    h.add_argument("--no-thumbs", action="store_true")
    h.add_argument("--max-thumbs", type=int, default=None)
    h.add_argument("--top", type=int, default=40)
    h.set_defaults(fn=cmd_harvest)

    m = common(sub.add_parser("measure",
                              help="measure thumbnails into the 133-key vocabulary"))
    m.add_argument("--dir", help="measure an arbitrary folder instead of the "
                                 "niche's own thumbs/")
    m.add_argument("--source-kind", choices=("local", "youtube"), default=None,
                   help="default: local for --dir, youtube for --niche")
    m.add_argument("--no-cache", action="store_true",
                   help="re-measure files already in measurements.jsonl")
    m.add_argument("--pattern", action="append", default=[],
                   help="glob to match inside --dir (repeatable); default is "
                        "jpg/jpeg/png/webp. Narrow it to '*.jpg' on a folder "
                        "that also holds PNG contact sheets.")
    m.set_defaults(fn=cmd_measure)

    s = common(sub.add_parser("styles",
                              help="cluster the niche's recurring styles"))
    s.add_argument("--k", type=int, default=None, help="force k")
    s.add_argument("--min-members", type=int, default=4)
    s.set_defaults(fn=cmd_styles)

    g = common(sub.add_parser("grammar",
                              help="what separates winners from losers here"))
    g.add_argument("--win", type=float, default=None)
    g.add_argument("--lose", type=float, default=None)
    g.add_argument("--top", type=int, default=12)
    g.set_defaults(fn=cmd_grammar)

    c = common(sub.add_parser("critique", help="score a candidate thumbnail"))
    c.add_argument("--history", default=None,
                   help="glob of thumbnails you have already shipped, e.g. "
                        "\"D:/Boyd Clips/thumbwork/*/[A-Z]*_thumb.jpg\". Adds the "
                        "variety check: is this the same layout as your last one?")
    c.add_argument("--image", action="append", default=[],
                   help="candidate image (repeatable)")
    c.add_argument("rest", nargs="*", help="further images, positionally")
    c.add_argument("--source-kind", choices=("local", "youtube"), default=None,
                   help="default: inferred - 'youtube' for a file under a "
                        "niche's thumbs/, 'local' for anything else")
    c.add_argument("--compare", action="store_true",
                   help="force the ranked A/B table even for one image")
    c.add_argument("--top", type=int, default=None)
    c.set_defaults(fn=cmd_critique)

    a = common(sub.add_parser("all",
                              help="harvest -> measure -> styles -> grammar "
                                   "(-> critique)"))
    a.add_argument("--channel", action="append", default=[])
    a.add_argument("--query")
    a.add_argument("--limit", type=int, default=60)
    a.add_argument("--baseline-limit", type=int, default=60)
    a.add_argument("--no-deepen", action="store_true")
    a.add_argument("--no-thumbs", action="store_true")
    a.add_argument("--max-thumbs", type=int, default=None)
    a.add_argument("--top", type=int, default=12)
    a.add_argument("--k", type=int, default=None)
    a.add_argument("--min-members", type=int, default=4)
    a.add_argument("--win", type=float, default=None)
    a.add_argument("--lose", type=float, default=None)
    a.add_argument("--dir", default=None)
    a.add_argument("--source-kind", choices=("local", "youtube"), default=None)
    a.add_argument("--no-cache", action="store_true")
    a.add_argument("--pattern", action="append", default=[])
    a.add_argument("--compare", action="store_true")
    a.add_argument("--image", action="append", default=[])
    a.add_argument("rest", nargs="*")
    a.set_defaults(fn=cmd_all)

    st = common(sub.add_parser("status",
                               help="what has run, when, with what counts"))
    st.set_defaults(fn=cmd_status)

    sub.add_parser("selftest",
                   help="run every module's own selftest"
                   ).set_defaults(fn=cmd_selftest, niche=None)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 2
    # --win/--lose default to None here rather than to the module constants, so
    # engine.py never restates a threshold that grammar.py owns. Filled in from
    # grammar's own defaults at the last moment.
    if args.cmd in ("grammar", "all"):
        gr = _mod("grammar")
        if getattr(args, "win", None) is None:
            args.win = gr.DEFAULT_WIN
        if getattr(args, "lose", None) is None:
            args.lose = gr.DEFAULT_LOSE
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        sys.stderr.write("\nengine: interrupted\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
