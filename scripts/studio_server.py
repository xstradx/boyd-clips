"""Serve the studio pages and render from them.

Two jobs, both needed because a file:// page cannot do either:

  * HTTP Range, so Chrome can seek inside a 500MB mp4. python -m http.server
    ignores Range entirely, and a seek to 211s silently stayed at 1.2s - which
    made the editor look broken when it was not.

  * POST /render, so the Render button actually renders instead of handing over
    a command to paste into a terminal.

Start it with Studio.bat on the Desktop, or:
    python scripts/studio_server.py

Nothing here writes outside READY-TO-REVIEW, and /render only ever invokes
make_short.py with parsed floats - never a shell string.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"
PORT = 8799

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def run_render(job_id: str, video: str, segs: list, out: str, captions: bool) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / "make_short.py"),
           "--video", video, "--out", out]
    for a, b in segs:
        cmd += ["--seg", "%.2f:%.2f" % (a, b)]
    if captions:
        cmd.append("--captions")

    with LOCK:
        JOBS[job_id] = {"state": "running", "line": "starting", "out": out}
    try:
        p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
        last = ""
        for line in p.stdout:                       # type: ignore[union-attr]
            line = line.strip()
            if line:
                last = line
                with LOCK:
                    JOBS[job_id]["line"] = line[:200]
        p.wait()
        ok = p.returncode == 0 and Path(out).exists()
        with LOCK:
            JOBS[job_id]["state"] = "done" if ok else "failed"
            JOBS[job_id]["line"] = last[:200] if last else ("exit %d" % p.returncode)
            if ok:
                JOBS[job_id]["size_mb"] = round(Path(out).stat().st_size / 1e6, 1)
                JOBS[job_id]["name"] = Path(out).name
    except Exception as exc:                        # noqa: BLE001
        with LOCK:
            JOBS[job_id] = {"state": "failed", "line": str(exc)[:200]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(OUTDIR), **kw)

    # ---------- rendering ----------
    def do_POST(self):                              # noqa: N802
        if self.path != "/render":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            video = str(body["video"])
            if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video):
                raise ValueError("bad video id")
            segs = [(float(a), float(b)) for a, b in body["segs"]]
            if not segs or any(b <= a for a, b in segs):
                raise ValueError("bad segments")
            name = re.sub(r"[^A-Za-z0-9._-]", "_", str(body.get("name") or "SHORT_custom"))
            if not name.lower().endswith(".mp4"):
                name += ".mp4"
            out = str(OUTDIR / name)                # always inside READY-TO-REVIEW
        except Exception as exc:                    # noqa: BLE001
            self._json(400, {"error": str(exc)})
            return

        job_id = uuid.uuid4().hex[:10]
        threading.Thread(target=run_render, daemon=True,
                         args=(job_id, video, segs, out, bool(body.get("captions")))).start()
        self._json(200, {"job": job_id})

    def do_GET(self):                               # noqa: N802
        if self.path.startswith("/status/"):
            with LOCK:
                self._json(200, JOBS.get(self.path.rsplit("/", 1)[-1],
                                         {"state": "unknown"}))
            return
        if self.path == "/alive":
            self._json(200, {"ok": True})
            return
        super().do_GET()

    def _json(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    # ---------- Range, so seeking works ----------
    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return super().send_head()

        size = os.path.getsize(path)
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_error(416)
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._limit = end - start + 1
        return f

    def copyfile(self, src, dst):
        limit = getattr(self, "_limit", None)
        if limit is None:
            try:
                return super().copyfile(src, dst)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
        left = limit
        while left > 0:
            chunk = src.read(min(64 * 1024, left))
            if not chunk:
                break
            try:
                dst.write(chunk)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
            left -= len(chunk)

    def log_message(self, *a):
        pass


class Threaded(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main() -> None:
    pages = sorted(OUTDIR.glob("STUDIO_*.html"))
    srv = Threaded(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"studio server on {url}")
    print(f"  serving {OUTDIR}")
    if pages:
        print("  pages:")
        for p in pages:
            print(f"    {url}{p.name}")
        webbrowser.open(url + pages[-1].name)
    else:
        print("  no STUDIO_*.html yet - run scripts/studio.py --video <id>")
    print("\nleave this window open while you edit. Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
