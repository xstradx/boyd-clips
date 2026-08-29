"""Static server WITH HTTP Range support, for testing the editor pages.

python -m http.server ignores Range entirely, so Chrome cannot seek inside a
large mp4 served by it - a seek to 211s silently stayed at 1.2s and looked like
an editor bug. Video seeking cannot be verified without this.
"""
from __future__ import annotations

import os
import re
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RangeHandler(SimpleHTTPRequestHandler):
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
            return super().copyfile(src, dst)
        left = limit
        while left > 0:
            chunk = src.read(min(64 * 1024, left))
            if not chunk:
                break
            try:
                dst.write(chunk)
            except (BrokenPipeError, ConnectionAbortedError):
                return
            left -= len(chunk)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
    os.chdir(sys.argv[2] if len(sys.argv) > 2 else ".")
    HTTPServer(("127.0.0.1", port), RangeHandler).serve_forever()
