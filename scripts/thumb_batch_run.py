"""Run scripts/thumb_direct_rerun.py for the five 2026-09-06 batch cases one
after another (the image sessions share one Codex quota window) and log each
result. Started hidden from PowerShell so no console window appears."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ["2024-03-07_dAKO7myCd-g_8340", "2024-07-30_jdzBCVXENUk_3840", "2024-03-25_bHAuH5U4NYI_4383",
        "2026-04-27_H_hXwF2dl7E_3540", "2026-05-04_mvGmUbuS0sU_6650"]


def main() -> int:
    for d in (sys.argv[1:] or DIRS):
        review = ROOT / "out" / "review" / d
        t0 = time.time()
        print(f"START {d} {time.strftime('%H:%M:%S')}", flush=True)
        log = ROOT / "out" / "batch_2026-09-06" / f"thumb2_{d}.log"
        with log.open("w", encoding="utf-8") as fh:
            rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "thumb_direct_rerun.py"), str(review)],
                                stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT)).returncode
        print(f"DONE {d} rc={rc} {time.time() - t0:.0f}s {time.strftime('%H:%M:%S')}", flush=True)
    print("ALL DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
