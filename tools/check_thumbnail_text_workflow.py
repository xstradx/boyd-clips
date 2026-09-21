"""Regression entry for source-grounded copy and controlled thumbnail text tests."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    tests = ["tests/test_thumbnail_copy.py", "tests/test_thumbnail_hook_quality.py",
             "tests/test_thumbnail_text_test.py", "tests/test_thumbnail_text_readiness.py",
             "tests/test_thumbnail_visible.py"]
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=ROOT)
    print("SELFTEST_PASS thumbnail_text_workflow" if result.returncode == 0
          else "SELFTEST_FAIL thumbnail_text_workflow")
    raise SystemExit(result.returncode)
