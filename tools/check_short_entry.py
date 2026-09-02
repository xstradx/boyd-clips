# -*- coding: utf-8 -*-
"""Every short render entry routes through tools/short_chain.py.

Nathan, 2026-09-01: *"Can you fix the short editor as well after"*; 2026-09-02,
asked whether every short from the editor pages should get the engine's
treatment: *"Okay then make it have it pls"*.

WHAT WAS WRONG. The three editor pages (`build_short_editor.py`,
`build_editor.py`, `build_browse_editor.py`), the batch renderer and the studio
server's Render button all emitted or called `scripts/make_short.py` - the RAW
cut. The raw cut has no word alignment, no tightening, none of the engine's
gates (R34 reveal, R35 mid-word cuts, R36/R38 window, speaker-side captions,
loudness, floor stamp). TORRES got all of that only because the four commands
were typed by hand; a short from an editor page would have shipped the old way.

WHAT IS MEASURED. A scan of the render entry files:
  1. no non-comment line puts `make_short.py` inside a quoted string (that is
     a command, a shell string or a subprocess argv - an emission);
  2. every file in ENTRY_FILES puts `short_chain.py` inside a quoted string.
Comment lines (`#`, `//`, `*`) are exempt so the files may SAY "never
make_short.py". Prose without quotes is exempt for the same reason.

    python tools/check_short_entry.py            -> SHORT_ENTRY_OK / SHORT_ENTRY_FAIL
    python tools/check_short_entry.py --selftest -> the old studio_server command must FAIL
"""
import glob
import os
import re
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# the files that render shorts - each must route through the chain
ENTRY_FILES = [
    "scripts/build_short_editor.py",
    "scripts/build_editor.py",
    "scripts/build_browse_editor.py",
    "scripts/batch_vertical.py",
    "scripts/studio_server.py",
]
# wider net for NEW render entries that are not yet in ENTRY_FILES
SCAN_GLOBS = ["scripts/*editor*.py", "scripts/studio*.py", "scripts/batch_vertical.py"]
# The one raw render that is NOT a short: scripts/studio.py renders the WHOLE
# hearing as the editor's player file (VERTICAL_<id>.mp4, 10-60 min). The chain
# would refuse it on length and tightening would break the linear player-time
# -> source-time map the editor derives its base offset from. The exemption is
# narrow: the emitting line, or one of the 3 lines above it, must name the
# player file - a short rendered from that file would trip the check.
RAW_ALLOWED = {"scripts/studio.py": "VERTICAL_"}

_RAW = re.compile(r"""["'][^"'\n]*make_short\.py[^"'\n]*["']""")
_CHAIN = re.compile(r"""["'][^"'\n]*short_chain\.py[^"'\n]*["']""")
_COMMENT = re.compile(r"^\s*(#|//|\*)")


def scan_text(text, allow_marker=None):
    """-> (raw_hits, chain_ok). raw_hits = [(lineno, line)] of quoted make_short.py
    on non-comment lines; chain_ok = a quoted short_chain.py exists on one.
    A raw hit is dropped when `allow_marker` appears on its line or within the
    3 lines above (the player-file exemption, RAW_ALLOWED)."""
    raw, chain = [], False
    lines = text.splitlines()
    for i, ln in enumerate(lines, 1):
        if _COMMENT.match(ln):
            continue
        if _RAW.search(ln):
            window = "\n".join(lines[max(0, i - 4):i])
            if not (allow_marker and allow_marker in window):
                raw.append((i, ln.strip()[:100]))
        if _CHAIN.search(ln):
            chain = True
    return raw, chain


def check(root=ROOT, entry_files=ENTRY_FILES, scan_globs=SCAN_GLOBS, verbose=True):
    problems = []
    files = set(entry_files)
    for g in scan_globs:
        files.update(os.path.relpath(p, root).replace("\\", "/")
                     for p in glob.glob(os.path.join(root, g)))
    for rel in sorted(files):
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            problems.append(f"{rel}: missing")
            continue
        raw, chain = scan_text(open(p, encoding="utf-8", errors="replace").read(),
                               allow_marker=RAW_ALLOWED.get(rel))
        for ln_no, ln in raw:
            problems.append(f"{rel}:{ln_no}: emits scripts/make_short.py -> {ln}")
        if rel in entry_files and not chain:
            problems.append(f"{rel}: no tools/short_chain.py entry")
        if verbose:
            print(f"  {'FAIL' if raw or (rel in entry_files and not chain) else 'ok  '} {rel}"
                  f"  raw_hits={len(raw)} chain={'yes' if chain else 'no'}")
    return problems


def selftest():
    ok = True

    def chk(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'MISS'} {name}: got {got!r} want {want!r}")

    # 1. the current tree passes
    chk("current tree has no raw emission", check(verbose=False), [])
    # 2. KNOWN-BAD CONTROL: studio_server.py with the pre-2026-09-02 command
    src = open(os.path.join(ROOT, "scripts/studio_server.py"), encoding="utf-8").read()
    old = src.replace('str(ROOT / "tools" / "short_chain.py")',
                      'str(ROOT / "scripts" / "make_short.py")')
    chk("control text differs from the tree", old != src, True)
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "scripts"))
        with open(os.path.join(td, "scripts", "studio_server.py"), "w", encoding="utf-8") as f:
            f.write(old)
        probs = check(root=td, entry_files=["scripts/studio_server.py"],
                      scan_globs=["scripts/studio*.py"], verbose=False)
        chk("CONTROL old studio_server command is refused",
            any("emits scripts/make_short.py" in p for p in probs), True)
        chk("CONTROL old studio_server has no chain entry",
            any("no tools/short_chain.py entry" in p for p in probs), True)
        # 3. a NEW editor page caught by the glob, not the list
        with open(os.path.join(td, "scripts", "build_new_editor.py"), "w", encoding="utf-8") as f:
            f.write('cmd = "python scripts/make_short.py --video " + V\n')
        probs = check(root=td, entry_files=[], scan_globs=["scripts/*editor*.py"], verbose=False)
        chk("new editor page emitting make_short is caught by the glob",
            any("build_new_editor.py:1" in p for p in probs), True)
    # 4. the player-file exemption is narrow: studio.py passes only because the
    #    VERTICAL_ player file is named beside the call
    st = open(os.path.join(ROOT, "scripts/studio.py"), encoding="utf-8").read()
    raw, _ = scan_text(st, allow_marker="VERTICAL_")
    chk("studio.py player render is exempt", raw, [])
    raw, _ = scan_text(st.replace("VERTICAL_", "SHORT_"), allow_marker="VERTICAL_")
    chk("CONTROL studio.py rendering a SHORT_ raw is refused", len(raw) >= 1, True)
    # 5. comments and prose are exempt; quoted strings are not
    raw, chain = scan_text('# never scripts/make_short.py\n// make_short.py is dead\n'
                           'x = "python tools/short_chain.py --video"\n')
    chk("comment mentions are exempt", raw, [])
    chk("quoted chain entry counts", chain, True)
    raw, _ = scan_text("[PY, str(ROOT / 'scripts' / 'make_short.py'), '--video']\n")
    chk("quoted make_short.py in an argv counts", len(raw), 1)
    raw, _ = scan_text("make_short (and short_chain) write a .map.json\n")
    chk("unquoted prose is exempt", raw, [])
    print("SELFTEST_PASS check_short_entry" if ok else "SELFTEST_FAIL check_short_entry")
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    probs = check()
    for p in probs:
        print("  " + p)
    print("SHORT_ENTRY_OK" if not probs else f"SHORT_ENTRY_FAIL {len(probs)} problem(s)")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
