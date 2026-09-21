"""Deterministic integrity check of src/boydclips/render.py after the
2026-09-06 accidental revert + reconstruction. Prints PASS/FAIL per item
and exits non-zero on any FAIL.

    python tools/render_integrity_check.py
"""
from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RENDER = ROOT / "src" / "boydclips" / "render.py"
PIPELINE = ROOT / "src" / "boydclips" / "pipeline.py"
BACKUP_CURRENT = ROOT / "backups" / "render.py.2026-09-06-polish"
BACKUP_PRE = ROOT / "backups" / "render.py.2026-09-06-pre-chunkbuild-recovered"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


src = RENDER.read_text(encoding="utf-8")

# 1. compiles + imports
try:
    compile(src, str(RENDER), "exec")
    for m in ("boydclips.render", "boydclips.pipeline", "boydclips.shorts_editor", "boydclips.captions", "boydclips.layout"):
        importlib.import_module(m)
    check("compiles_and_imports", True, "render, pipeline, shorts_editor, captions, layout import")
except Exception as exc:  # noqa: BLE001
    check("compiles_and_imports", False, repr(exc))

# 2. backups agree with the file on disk
if BACKUP_CURRENT.exists():
    same = BACKUP_CURRENT.read_text(encoding="utf-8") == src
    check("matches_post_patch_backup", same, f"{BACKUP_CURRENT.name} {'identical' if same else 'DIFFERS'}")
else:
    check("matches_post_patch_backup", False, "backup missing")
if BACKUP_PRE.exists():
    # functions that legitimately changed after the recovery: the chunk-build
    # rail (2026-09-06) and the visual polish pass (same day)
    ALLOWED = {"build_rail_ass", "duo_punch_filter", "render_short", "camera_clarity_filter", "encode_args",
               "measure_caption_centering", "calibrate_caption_positions", "_max_abs", "_mean_abs", "ass_font_scale"}

    def fn_bodies(text: str) -> dict[str, str]:
        t = ast.parse(text)
        return {n.name: ast.get_source_segment(text, n) or "" for n in t.body if isinstance(n, ast.FunctionDef)}

    pre, cur = fn_bodies(BACKUP_PRE.read_text(encoding="utf-8")), fn_bodies(src)
    changed = {k for k in set(pre) | set(cur) if pre.get(k) != cur.get(k)}
    unexpected = sorted(changed - ALLOWED)
    check("only_expected_functions_changed_since_recovery", not unexpected and bool(changed),
          f"changed vs the recovered pre-chunk snapshot: {sorted(changed)}" if not unexpected
          else f"UNEXPECTED changes in: {unexpected}")
else:
    check("only_expected_functions_changed_since_recovery", False, "pre-chunk snapshot missing")

# 3. accepted SHORTS_EDITOR_V2 renderer features
tree = ast.parse(src)
defs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
need = {
    "duo_punch_filter": "fixed 50/50 layout with punch-ins inside the tiles",
    "camera_grade_filter": "per-camera grade before assembly",
    "short_grade_filter": "common floor stage",
    "build_rail_ass": "kinetic rail captions",
    "visual_qc": "post-render visual QC (divider, contact sheet)",
    "measure_divider_y": "divider measurement",
    "map_words_to_timeline": "authoritative word timeline",
    "render_short": "short renderer",
    "_watermark_chain": "watermark overlay",
}
for fn, why in need.items():
    check(f"def:{fn}", fn in defs, why)


def body_of(name: str) -> str:
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n) or ""
    return ""


dp = body_of("duo_punch_filter")
check("duo_punch:tile_filters", "tile_filters" in dp, "duo_punch_filter takes per-tile filter chains")
check("duo_punch:fixed_divider", ("960" in dp or "DIVIDER" in dp or "h // 2" in dp or "h / 2" in dp or "half" in dp.lower()),
      "50/50 stack (divider at half height)")
cg = body_of("camera_grade_filter")
check("camera_grade:curves", "curves" in cg, "camera_grade_filter builds the defendant curve from config")
sg = body_of("short_grade_filter")
check("short_grade:no_brightness_branch", "short_floor_no_brightness" in sg and "brightness=" in sg,
      "short_floor_no_brightness strips the floor's brightness term")
rail = body_of("build_rail_ass")
check("rail:chunk_events", "new_range" in rail and "pop_from" in rail and "Alignment" in src,
      "one event per reveal chunk with the pop on the new chunk")
check("rail:fixed_anchor", "an4" in rail and "pos(" in rail, "left-anchored at the pre-centred x on the 960 rail")
check("rail:no_end_card", not re.search(r"FULL (VIDEO|CASE)|end_card|endcard", rail, re.I), "no end card in the rail builder")
rs = body_of("render_short")
check("render_short:duo_punch_wired", "duo_punch" in rs and "tile_filters" in rs or "duo_punch_filters" in rs,
      "render_short passes duo_punch windows + per-tile filters")
wm = body_of("_watermark_chain")
check("watermark:strict_missing", "FileNotFoundError" in wm and "configured watermark not found" in wm,
      "a configured but missing mark raises (intended current behaviour); disabled -> null pass-through")
check("watermark:disabled_passthrough", "null[" in wm, "disabled mark passes the labels through")

# 4. pipeline wiring of the V2 short
ps = PIPELINE.read_text(encoding="utf-8")
ptree = ast.parse(ps)
v2 = ""
for n in ast.walk(ptree):
    if isinstance(n, ast.FunctionDef) and n.name == "_short_v2":
        v2 = ast.get_source_segment(ps, n) or ""
check("pipeline:_short_v2_present", bool(v2), "pipeline._short_v2")
for needle, why in (("camera_grade_filter", "per-camera grades"), ("layout.compose", "fixed layout composition"),
                    ("overlay_layout", "overlay collision QC"), ("calibrate_caption_positions", "rail captions (built + centred by the calibration)"),
                    ("plan_captions", "captions V3 chunk-build"), ("visual_qc", "post-render visual QC"),
                    ("kinetic_qc", "caption QC gates")):
    check(f"pipeline:{needle}", needle in v2, why)
check("pipeline:no_end_card", not re.search(r"end_card|FULL VIDEO|FULL CASE", v2, re.I), "no end card in the V2 path")

# 5. the configured watermark asset exists (strict behaviour would otherwise refuse the render)
try:
    from boydclips.config import load_config  # type: ignore
    sh = load_config().require("output.short")
    from boydclips import render as _r
    wmc = sh.get("watermark", _r.DEFAULT_WATERMARK)          # same default rule as _watermark_chain
    ok = wmc in (None, False, "") or Path(str(wmc)).is_file()
    check("watermark:asset_present", ok, f"output.short.watermark -> {wmc!r} ({'exists' if ok else 'MISSING'}; "
          f"{'configured' if 'watermark' in sh else 'DEFAULT_WATERMARK'})")
    check("grade:option_b", sh.get("color", {}).get("source") == "short_floor_no_brightness" and sh["color"].get("defendant", {}).get("curve"),
          f"color.source={sh.get('color', {}).get('source')!r}, defendant curve set, boyd curve={sh['color'].get('boyd', {}).get('curve')!r}")
except Exception as exc:  # noqa: BLE001
    check("watermark:asset_present", False, repr(exc))

# 6. tests
r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"], cwd=ROOT, capture_output=True, text=True)
tail = [l for l in r.stdout.splitlines() if re.search(r"\d+ (passed|failed)", l)]
check("tests", r.returncode == 0, tail[-1] if tail else r.stdout[-300:])

bad = [x for x in results if not x[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:45s} {detail}")
print(f"\n{len(results) - len(bad)}/{len(results)} checks pass")
sys.exit(1 if bad else 0)
