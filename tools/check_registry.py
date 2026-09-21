# -*- coding: utf-8 -*-
"""Which checks exist, which are WIRED IN, and which have gone orphaned.

WHY THIS FILE EXISTS
Audited 2026-08-31: this repo had 11 verification scripts and SIX were
referenced by nothing at all.

    audit_cuts             0 references   <- then found 5 of 5 cuts defective
    check_vertical         0 references
    validate_oncamera      0 references
    verify_Q3_detail       0 references   <- stale limit, failed everything
    verify_Q4_light        0 references
    verify_thumb_metrics   0 references
    verify_thumb           8 references   <- the only one genuinely protecting

The failure mode is not that checks were never written. Nathan named a defect,
a detector got written for it, and then the detector was never called by the
path that ships. So the same defect shipped again and he became the regression
test - which CLAUDE.md already diagnosed for thumbnails and which nobody ever
fixed for video.

Worse, two of them had gone STALE and would fail every build:
  * verify_Q3_detail enforced an arrow size from before Nathan resized the arrow
    himself on 2026-08-29, and compared a GLOW-INCLUSIVE pixel count against a
    POLYGON-ONLY reference - an 8.4x mismatch. It could never pass.
  * A checker that cries wolf gets dropped. That is how it dies quietly.

So this file is the standing answer to "what else are we missing": it lists
every check, says whether anything calls it, and refuses to be silent about the
ones nothing calls.

    python tools/check_registry.py            # the audit
    python tools/check_registry.py --selftest # prove it can detect an orphan
"""
import os
import re
import sys
import glob

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# A check is any script whose job is to say yes or no about a built artifact.
PATTERNS = ("verify_*.py", "audit_*.py", "check_*.py", "validate_*.py")

# Not a check, but the same failure: a FINISHING stage that exists, is correct,
# and is called by nothing. Found 2026-08-31 - assemble_final.py carries a
# two-pass loudnorm targeting exactly the right numbers (I=-14.0, TP=-1.5,
# LRA=7.0) and a limiter, with a docstring explaining why the limiter must come
# after loudnorm. Nothing invokes it, so every shipped video measures -21 LUFS
# with 5dB of headroom unused, i.e. audibly quieter than everything beside it in
# a feed. Watched here so it cannot go quiet again.
ALSO_WATCH = ("assemble_final.py",)
SEARCH_DIRS = ("scripts", "tools", "src")

# Scripts that are deliberately standalone - a human runs them, nothing should
# call them. Listed explicitly so "orphaned" always means "unintentionally
# orphaned", and so adding to this list is a visible decision.
INTENTIONALLY_MANUAL = {
    "check_registry",          # this file
}


def find_checks():
    out = {}
    for d in SEARCH_DIRS:
        for pat in tuple(PATTERNS) + tuple(ALSO_WATCH):
            for p in glob.glob(os.path.join(ROOT, d, pat)):
                out[os.path.splitext(os.path.basename(p))[0]] = os.path.relpath(p, ROOT)
    return dict(sorted(out.items()))


SELF = "tools" + os.sep + "check_registry.py"
# Top-level entry points are run by a person or by CI, so having no code caller
# is correct for them, not a gap. Keep this list SHORT - adding a checker here
# to quiet the gate is exactly the failure this gate exists to catch.
ENTRYPOINTS = {"check_registry", "selftest_all"}


def _strip_docstrings(src):
    """Blank out every docstring. Falls back to the original text if the file
    does not parse - a syntax error elsewhere must not silently turn this into
    'no references found', which would report a wired check as an orphan."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.splitlines()
    kill = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                kill.add(ln)
    return "\n".join("" if i + 1 in kill else l for i, l in enumerate(lines))


def references(name, own_path):
    """Files that name this module. Text search, deliberately: a check can be
    invoked by import, by subprocess, or from a Makefile/CI line, and an
    import-graph walk would miss the last two and report a false orphan."""
    hits = []
    for d in SEARCH_DIRS + (".",):
        for ext in ("*.py", "*.md", "*.ps1", "*.sh", "*.yml", "*.yaml", "*.toml"):
            for p in glob.glob(os.path.join(ROOT, d, ext)):
                rel = os.path.relpath(p, ROOT)
                # EXCLUDE THIS FILE. Its docstring names every check in the
                # repo, so without this it manufactures one reference for each
                # and reports "no orphans" - the orphan detector inventing the
                # evidence that there are none. Its own selftest caught this on
                # first run, via a control name that cannot exist anywhere.
                if rel == own_path or rel == SELF or "__pycache__" in rel:
                    continue
                try:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        txt = f.read()
                except OSError:
                    continue
                # STRIP COMMENTS FIRST. A comment naming a script is not a call,
                # and this bit immediately: after the cut gate went in,
                # audit_cuts showed 1 "reference" which was the COMMENT
                # explaining why it exists. A registry that counts prose as
                # protection is the exact failure it was built to detect.
                if rel.endswith(".py"):
                    txt = "\n".join(ln.split("#", 1)[0] for ln in txt.splitlines())
                    # AND DOCSTRINGS. Stripping only '#' comments was not
                    # enough: master_audio.py's DOCSTRING explains that it
                    # replaces assemble_final.py, and that mention alone made
                    # assemble_final read as wired - dropping the true orphan
                    # count from 8 to 7 and hiding the exact file whose absence
                    # left every video 7dB quiet. Prose about a module is not a
                    # call to it, wherever the prose lives.
                    txt = _strip_docstrings(txt)
                elif rel.endswith((".ps1", ".sh")):
                    # Shell entry points execute checks too. Count an actual
                    # Python command, never an example in a comment or echo.
                    txt = re.sub(r"(?s)<#.*?#>", "", txt)
                    txt = "\n".join(ln.split("#", 1)[0] for ln in txt.splitlines())
                    command = (r"^\s*(?:&\s*)?(?:python(?:\d(?:\.\d+)?)?(?:\.exe)?|py(?:\.exe)?)"
                               r"\s+[^\r\n]*\b" + re.escape(name) + r"\.py\b")
                    if not re.search(command, txt, re.M):
                        continue
                # INVOCATION, not mention: an import, an importlib call, a
                # subprocess on the .py, or a direct .main()/.run()/.selftest().
                # Erring toward UNDER-counting is the safe direction here - it
                # flags something for review rather than silently calling it
                # protected.
                n = re.escape(name)
                inv = (
                    r"^\s*(?:from|import)\s+[\w.]*\b" + n + r"\b",
                    r"import_module\([^)]*\b" + n + r"\b",
                    r"\b" + n + r"\.py\b",
                    r"\b" + n + r"\s*\.\s*(?:main|run|selftest|check)\s*\(",
                )
                if any(re.search(rx, txt, re.M) for rx in inv):
                    hits.append(rel)
    return sorted(set(hits))


def audit():
    checks = find_checks()
    rows, orphans, doc_only = [], [], []
    for name, path in checks.items():
        if name in INTENTIONALLY_MANUAL:
            continue
        refs = references(name, path)
        code_refs = [r for r in refs if r.endswith((".py", ".ps1", ".sh"))]
        rows.append((name, path, len(code_refs), len(refs)))
        if not code_refs:
            (doc_only if refs else orphans).append(name)

    print("CHECK REGISTRY  (%d checks found)" % len(rows))
    print()
    print("  %-26s %-34s %s" % ("check", "path", "called by"))
    for name, path, nc, na in sorted(rows, key=lambda r: (r[2], r[0])):
        flag = "  ORPHAN" if (nc == 0 and name not in ENTRYPOINTS) else ""
        if name in ENTRYPOINTS and nc == 0:
            flag = "  entry point"
        print("  %-26s %-34s %d code / %d total%s" % (name, path, nc, na, flag))

    print()
    if orphans or doc_only:
        print("ORPHANED - nothing in the codebase calls these, so they are")
        print("protecting nothing. Each is either wired in, deleted, or added to")
        print("INTENTIONALLY_MANUAL with a reason:")
        for n in sorted(set(orphans + doc_only)):
            print("    %s" % n)
        print()
        print("A check nobody runs is a comment. Measured 2026-08-31: six of")
        print("these were orphaned and one of them, audit_cuts, immediately")
        print("found 5 of 5 cuts defective in a short that had already shipped.")
    else:
        print("no orphans: every check is called by something")
    return 1 if (orphans or doc_only) else 0


def selftest():
    """Prove the audit can actually detect an orphan, against a control whose
    answer is known before the number is read."""
    ok = True
    checks = find_checks()
    if len(checks) < 5:
        print("  FAIL found %d checks, expected many more" % len(checks))
        ok = False
    else:
        print("  discovery: found %d check scripts" % len(checks))

    # KNOWN POSITIVE: verify_thumb is called from many places.
    if "verify_thumb" in checks:
        n = len([r for r in references("verify_thumb", checks["verify_thumb"])
                 if r.endswith(".py")])
        print("  known-wired  verify_thumb -> %d code references (want >0)" % n)
        if n == 0:
            print("  FAIL a known-wired check reads as an orphan"); ok = False

    # KNOWN NEGATIVE: a name that cannot possibly be referenced.
    n = len(references("verify_this_name_does_not_exist_anywhere", "nope.py"))
    print("  known-orphan control -> %d references (want 0)" % n)
    if n != 0:
        print("  FAIL the reference search finds things that do not exist"); ok = False

    print("SELFTEST_PASS check_registry" if ok else "SELFTEST_FAIL check_registry")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else audit())
