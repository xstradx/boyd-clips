# -*- coding: utf-8 -*-
"""Every checker NAMED in spec/NATHAN_RULES.md must exist and be on the path
that ships - or the rules file must SAY it is not.

WHY THIS FILE EXISTS (measured 2026-09-01)
Nathan, 2026-08-29: "i noticed that i have to keep repeating myself multiple
times for each and every one and you keep brining me the same exact flaws".
The rules file answered with a check table. On 2026-09-01 that table was
measured against the disk:

    verify_set.py         cited 14x   exists in scripts/, only caller is
                                      scripts/thumb_Q3_detail.py (itself dead);
                                      LUMA 122+-12 and ARROW 1500-6000 contradict
                                      config/quality_floor.json; pale check
                                      reads a .meta.json nothing writes
    tools/verify_variety.py  cited    does not exist (the code is thumbeng/variety.py)
    tools/thumb_measure.py   cited    does not exist (retired 2026-08-31)
    "Nothing ships until verify_set.py --check all is clean"  - it never ran once

A checker that exists but is not on the build path is prose with a filename.
check_registry.py asks "does ANYTHING reference this script" - a docstring
counts, a dead script counts. This asks the narrower question that matters:
is it invoked by a file that SHIPS, and does the rules file tell the truth
about that.

STATES (declared in the rules file's checker registry, verified here)
    WIRED    exists AND is invoked by a build-path file
    ORPHAN   exists, nothing on the build path invokes it
    STALE    ORPHAN whose thresholds are known to contradict the current floor
    MISSING  named in the rules file, not on disk
    MANUAL   a human runs it on purpose (sheet builders, this audit)

The registry is the table under "## Checker registry" in NATHAN_RULES.md:
    | `scripts/verify_set.py` | ORPHAN | ... |
Every *.py named ANYWHERE in the rules file must have a row, and the row's
state must match what is measured. Declaring MISSING or ORPHAN honestly passes;
lying passes nothing.

    python tools/check_rules_refs.py             # audit -> ALL_OK / RULES_REFS_FAIL
    python tools/check_rules_refs.py --selftest  # proves it can catch a lie
"""
import os
import re
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
RULES = os.path.join(ROOT, "spec", "NATHAN_RULES.md")

# The files that ship. A checker invoked from anywhere else is not protecting
# a build - thumb_Q3_detail.py called verify_set.py and thumb_Q3_detail.py is
# itself called by nothing.
BUILD_PATH = (
    "tools/thumb_pipeline.py", "tools/thumb.py", "tools/verify_build.py",
    "tools/verify_thumb.py", "tools/make_short.py", "tools/short_engine.py",
    "tools/selftest_all.py", "tools/floor_stamp.py",
    # R48 (2026-09-02): the one short render entry - raw -> words -> tight ->
    # engine. What it invokes is on the shorts path by construction.
    "tools/short_chain.py",
    # R49 (2026-09-02): the long-form builder runs check_coldopen on its output.
    "scripts/build_case_longform.py",
    # R50 (2026-09-02): selftest_all runs the digest; the picker path is manual.
    "tools/banger_digest.py",
    # R51 (2026-09-02): the grade gate, run per build and in selftest_all.
    "tools/check_thumb_grade.py",
)
# The publish path lives in the skills, outside the repo. Read if present.
PUBLISH_PATH = (
    os.path.expanduser("~/.claude/skills/youtube-channel/SKILL.md"),
    os.path.expanduser("~/.claude/skills/boyd-thumbnail/SKILL.md"),
)
STATES = ("WIRED", "ORPHAN", "STALE", "MISSING", "MANUAL")

_SPAN = re.compile(r"`([^`\n]+)`")
# one package level is allowed (tools/thumbeng/variety.py); a bare name is
# looked up in tools/ then scripts/ by resolve()
_PY = re.compile(r"(?<![A-Za-z0-9_/.])((?:tools/|scripts/)?(?:[A-Za-z0-9_]+/)?[A-Za-z0-9_]+\.py)\b")
_ROW = re.compile(r"^\|\s*`((?:tools/|scripts/)?(?:[A-Za-z0-9_]+/)?[A-Za-z0-9_]+\.py)`\s*\|\s*([A-Z]+)\s*\|")


def _stem(name):
    return os.path.splitext(os.path.basename(name))[0]


def resolve(name):
    """Where is it on disk, if anywhere. A bare name is looked up in tools/
    then scripts/ - two copies (caption_short.py) resolve to tools/."""
    if "/" in name:
        p = os.path.join(ROOT, name)
        return p if os.path.exists(p) else None
    for d in ("tools", "scripts"):
        p = os.path.join(ROOT, d, name)
        if os.path.exists(p):
            return p
    return None


def _code_lines(path):
    """Code only: comments and docstrings stripped with tokenize, so a script
    that merely TALKS about another (short_engine lists three legacy paths in
    a tuple it only os.path.exists() on) is not counted as calling it."""
    import io
    import tokenize
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return
    if not path.endswith(".py"):
        for ln in src.splitlines():
            if ln.strip():
                yield ln.strip()
        return
    out = {}
    try:
        prev_type = None
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            # a STRING that starts a logical line is a docstring
            if tok.type == tokenize.STRING and prev_type in (None, tokenize.NEWLINE,
                                                              tokenize.INDENT,
                                                              tokenize.DEDENT,
                                                              tokenize.NL):
                prev_type = tok.type
                continue
            if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                tokenize.DEDENT, tokenize.ENDMARKER):
                out.setdefault(tok.start[0], []).append(tok.string)
            prev_type = tok.type
    except (tokenize.TokenError, SyntaxError):
        for ln in src.splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                yield s
        return
    for k in sorted(out):
        yield " ".join(out[k])


_EXEC = re.compile(r"subprocess|Popen|\brun\(|os\.system|sys\.executable|join\s*\(\s*ROOT")


def _invokes(line, stem, runner=False):
    e = re.escape(stem)
    # selftest_all.py is a runner: every quoted script in its SUITE is
    # executed, the subprocess call just sits on another line
    if runner and re.search(r"[\"'](?:tools/|scripts/)?%s\.py[\"']" % e, line):
        return True
    if re.search(r"^(import|from)\s+%s\b" % e, line):
        return True
    if re.search(r"\b%s\.(run|check|score|main|stamp|audit)\(" % e, line):
        return True
    # a quoted path is an invocation only on a line that executes something;
    # a bare tuple of filenames that gets os.path.exists()'d is not
    if re.search(r"[\"'](?:tools/|scripts/)?%s\.py[\"']" % e, line) and _EXEC.search(line):
        return True
    return False


def wired_by(name):
    stem = _stem(name)
    callers = []
    for rel in BUILD_PATH:
        if _stem(rel) == stem:
            continue
        p = os.path.join(ROOT, rel)
        runner = rel.endswith("selftest_all.py")
        if any(_invokes(ln, stem, runner) for ln in _code_lines(p)):
            callers.append(rel)
    for p in PUBLISH_PATH:
        if os.path.exists(p) and any(re.search(r"\b%s\.py\b" % re.escape(stem), ln)
                                     for ln in _code_lines(p)):
            callers.append("skill:" + os.path.basename(os.path.dirname(p)))
    return callers


def measure(name):
    path = resolve(name)
    if path is None:
        return "MISSING", []
    c = wired_by(name)
    return ("WIRED" if c else "ORPHAN"), c


def audit(rules_path=RULES, verbose=True):
    text = open(rules_path, encoding="utf-8").read()
    named = sorted({m.group(1) for span in _SPAN.finditer(text)
                    for m in _PY.finditer(span.group(1))})
    declared = {}
    for ln in text.splitlines():
        m = _ROW.match(ln)
        if m:
            declared[m.group(1)] = m.group(2)
    # rows may use the resolved path while prose uses the bare name; key by stem
    decl_by_stem = {_stem(k): (k, v) for k, v in declared.items()}

    problems = []
    rows = []
    seen = set()
    for name in named:
        st = _stem(name)
        if st in seen:
            continue
        seen.add(st)
        state, callers = measure(name)
        dec = decl_by_stem.get(st)
        if dec is None:
            problems.append(f"UNDECLARED  {name}: named in the rules, no registry row")
            rows.append((name, "-", state, callers))
            continue
        dpath, dstate = dec
        if dstate not in STATES:
            problems.append(f"BAD STATE   {dpath}: '{dstate}' not in {STATES}")
        elif dstate == "MISSING" and state != "MISSING":
            problems.append(f"NOT MISSING {dpath}: declared MISSING but it exists ({state})")
        elif dstate != "MISSING" and state == "MISSING":
            problems.append(f"PHANTOM     {dpath}: declared {dstate}, not on disk")
        elif dstate == "WIRED" and state != "WIRED":
            problems.append(f"NOT WIRED   {dpath}: declared WIRED, nothing on the build path invokes it")
        elif dstate in ("ORPHAN", "STALE") and state == "WIRED":
            problems.append(f"NOW WIRED   {dpath}: declared {dstate} but {callers} invoke it - update the row")
        rows.append((dpath, dstate, state, callers))
    for dpath in declared:
        if _stem(dpath) not in seen:
            problems.append(f"DEAD ROW    {dpath}: registry row for a script the rules never cite")

    if verbose:
        print(f"  {len(rows)} checker(s) named in {os.path.relpath(rules_path, ROOT)}")
        for name, dstate, state, callers in rows:
            agree = (dstate == state or (dstate == "STALE" and state == "ORPHAN")
                     or (dstate == "MANUAL" and state != "MISSING"))
            flag = "" if agree else "  <-- "
            print(f"    {dstate:8} {state:8} {name:32} {', '.join(callers)}{flag}")
        for p in problems:
            print("  " + p)
        print("ALL_OK" if not problems else f"RULES_REFS_FAIL {len(problems)} problem(s)")
    return problems


def selftest():
    """Three lies and one truth, each with a known answer before it is read."""
    ok = True
    base = open(RULES, encoding="utf-8").read()
    cases = [
        ("phantom declared WIRED must fail",
         "\n| `tools/no_such_checker.py` | WIRED | x |\n\nsee `tools/no_such_checker.py`\n", True),
        ("phantom declared MISSING must pass",
         "\n| `tools/no_such_checker.py` | MISSING | x |\n\nsee `tools/no_such_checker.py`\n", False),
        ("wired checker declared ORPHAN must fail",
         "\n| `tools/verify_build.py` | ORPHAN | x |\n\nsee `tools/verify_build.py`\n", True),
        ("cited but undeclared must fail",
         "\n\nsee `tools/undeclared_thing.py`\n", True),
    ]
    for label, extra, want_fail in cases:
        # strip any real row/mention of the same stem so the case is isolated
        fd, tmp = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        txt = base
        if "verify_build" in extra:
            txt = "\n".join(ln for ln in base.splitlines() if "verify_build.py" not in ln)
        open(tmp, "w", encoding="utf-8").write(txt + extra)
        probs = audit(tmp, verbose=False)
        os.remove(tmp)
        # only the problems about THIS case count - the live file may have its own
        mine = [p for p in probs
                if any(k in p for k in ("no_such_checker", "verify_build", "undeclared_thing"))]
        failed = bool(mine)
        print(f"  {'ok  ' if failed == want_fail else 'FAIL'} {label}: "
              f"{mine[0] if mine else 'no problem raised'}")
        ok = ok and (failed == want_fail)
    print("SELFTEST_PASS check_rules_refs" if ok else "SELFTEST_FAIL check_rules_refs")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    sys.exit(0 if not audit() else 1)
