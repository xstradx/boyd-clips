"""Measure every render on disk, so the pass threshold comes from a
distribution instead of two data points."""
import sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import importlib.util
spec = importlib.util.spec_from_file_location("vr", ROOT / "scripts" / "verify_render.py")
vr = importlib.util.module_from_spec(spec); spec.loader.exec_module(vr)

APPROVED = {"2026-04-27_JgvW7oCQxuI_6698", "2026-05-04_mvGmUbuS0sU_1358"}
rows = []
for d in sorted((ROOT / "out" / "review").iterdir()):
    v = d / "short.mp4"
    if not v.exists() or v.stat().st_size < 100_000:
        continue
    try:
        m = vr.measure(vr.sample(v, 5))
    except SystemExit:
        continue
    except Exception as e:
        print(f"  {d.name}: {e}"); continue
    tag = "APPROVED" if d.name in APPROVED else ""
    rows.append((m["coverage"], d.name, m["black"], tag))
rows.sort(reverse=True)
print(f"{'coverage':>9}{'black':>8}  folder")
for cov, name, blk, tag in rows:
    print(f"{100*cov:>8.1f}%{100*blk:>7.1f}%  {name} {tag}")
import statistics as st
c = [r[0] for r in rows]
print(f"\nn={len(c)}  median {100*st.median(c):.1f}%  min {100*min(c):.1f}%  max {100*max(c):.1f}%")
