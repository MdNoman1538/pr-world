#!/usr/bin/env python3
"""Serve PR World (viewer2/dist) for one person, without sign-in: every module is open. For teams use ../server."""
import functools
import http.server
import json
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
DATA = os.path.join(os.path.dirname(HERE), "viewer", "data")


def trust_view():
    """PRW_TRUST_VIEW=level|percent, from the environment or ../../ai-reviewer/.env (only this key is read)."""
    v = os.environ.get("PRW_TRUST_VIEW")
    if not v:
        env = os.path.join(os.path.dirname(os.path.dirname(HERE)), "ai-reviewer", ".env")
        try:
            for line in open(env, encoding="utf-8"):
                if line.strip().startswith("PRW_TRUST_VIEW="):
                    v = line.split("=", 1)[1].split("#", 1)[0].strip().strip('"\'')
        except OSError:
            pass
    return "percent" if (v or "").lower() == "percent" else "level"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == "/data/settings.json":
            body = json.dumps({"trust_view": trust_view()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/data/"):
            rel = os.path.normpath(clean[len("/data/"):]).lstrip("/\\")
            if rel.startswith(".."):
                return os.path.join(DATA, "__nope__")
            return os.path.join(DATA, rel)
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=DIST))
    print(f"Loan World v2: http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
