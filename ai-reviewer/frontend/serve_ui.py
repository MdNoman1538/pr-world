#!/usr/bin/env python3
"""Frontend dev server: serves this folder (static files only) on http://127.0.0.1:8780.

The dashboard calls the backend API (default http://127.0.0.1:8765, see config.js).
No backend code is imported here: the two apps are independent and talk over HTTP.
"""
import argparse
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED = {"/", "/index.html", "/app.js", "/style.css", "/d3.min.js", "/config.js"}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path.split("?")[0] not in ALLOWED:
            self.send_error(404)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8780)
    a = p.parse_args()
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(Handler, directory=HERE))
    print(f"[frontend] dashboard on http://127.0.0.1:{a.port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
