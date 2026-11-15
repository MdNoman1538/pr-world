"""Backend JSON API. It serves review DATA only; the dashboard UI is a separate app (../frontend).

  GET  /api/health                        → {"ok": true, "version": ...}
  GET  /api/runs                          → [{run_id, head, base, decision, tier, created_at}]
  GET  /api/runs/<run_id>                 → bundle {review, graph, evidence, signoff?, feedback}
  POST /api/feedback  {run_id, finding_id, verdict: accepted|rejected, by, note}
  POST /api/signoff   {run_id, record, owner}

Binds to 127.0.0.1 only. CORS allows the frontend origin (default: any localhost origin).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import unquote

from . import __version__
from .memory import Memory

_RUN_RE = re.compile(r"^[\w.\-]+$")
_LOCAL_ORIGIN = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$")


def _read(path: str, limit: int = 300_000) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read(limit + 1)
    return text if len(text) <= limit else text[:limit] + "\n… (truncated)"


def bundle(run_dir: str, memory: Optional[Memory] = None) -> Dict:
    """The data contract between backend and frontend (also written to <run>/bundle.json)."""
    with open(os.path.join(run_dir, "review.json"), encoding="utf-8") as fh:
        review = json.load(fh)
    graph = {"countries": [], "cities": [], "roads": [], "country_roads": []}
    gp = os.path.join(run_dir, "graph.json")
    if os.path.exists(gp):
        with open(gp, encoding="utf-8") as fh:
            graph = json.load(fh)
    evidence = {}
    for s in review.get("sensors", []):
        lf = s.get("log_file")
        if lf and os.path.exists(os.path.join(run_dir, lf)):
            evidence[lf] = _read(os.path.join(run_dir, lf))
    out = {"schema": "ai-reviewer-bundle/1", "review": review, "graph": graph, "evidence": evidence, "feedback": {}}
    sp = os.path.join(run_dir, "signoff.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as fh:
            out["signoff"] = json.load(fh)
    if memory is not None:
        rows = memory.db.execute("SELECT finding_id, status FROM findings WHERE run_id=? AND status<>'open'",
                                 (review["run_id"],)).fetchall()
        out["feedback"] = {fid: st for fid, st in rows}
        out["review"]["track_record"] = memory.track_record()
    return out


def write_bundle(run_dir: str, memory: Optional[Memory] = None) -> str:
    path = os.path.join(run_dir, "bundle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle(run_dir, memory), fh)
    return path


def list_runs(runs_dir: str):
    rows = []
    if not os.path.isdir(runs_dir):
        return rows
    for name in sorted(os.listdir(runs_dir), reverse=True):
        p = os.path.join(runs_dir, name, "review.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    r = json.load(fh)
                rows.append({"run_id": r["run_id"], "head": r["head"], "base": r["base"], "decision": r["decision"],
                             "created_at": r["created_at"], "tier": r["tier"]["tier"],
                             "ai_error": bool(r.get("ai_error"))})
            except Exception:
                continue
    return rows


class _Handler(BaseHTTPRequestHandler):
    runs_dir = "runs"
    memory_path = ".reviewer/memory.db"
    allow_origin = ""          # "" = any localhost origin

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if (self.allow_origin and origin == self.allow_origin) or (not self.allow_origin and _LOCAL_ORIGIN.match(origin)) \
                or origin == "null":     # a dashboard opened from a file
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        if path == "/api/health":
            return self._json({"ok": True, "version": __version__})
        if path == "/api/runs":
            return self._json(list_runs(self.runs_dir))
        if path.startswith("/api/runs/"):
            run_id = path[len("/api/runs/"):]
            run_dir = os.path.join(self.runs_dir, run_id)
            if not _RUN_RE.match(run_id) or not os.path.exists(os.path.join(run_dir, "review.json")):
                return self._json({"error": "no such run"}, 404)
            return self._json(bundle(run_dir, Memory(self.memory_path)))
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(min(n, 1_000_000)) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "bad json"}, 400)
        run_id = str(data.get("run_id", ""))
        if not _RUN_RE.match(run_id):
            return self._json({"ok": False, "error": "bad run id"}, 400)
        mem = Memory(self.memory_path)
        if self.path == "/api/feedback":
            verdict = data.get("verdict")
            if verdict not in ("accepted", "rejected"):
                return self._json({"ok": False, "error": "verdict must be accepted or rejected"}, 400)
            ok = mem.feedback(run_id, str(data.get("finding_id", "")), verdict, str(data.get("note", "")),
                              str(data.get("by", "")) or "dashboard")
            return self._json({"ok": ok, "track_record": mem.track_record(), "error": "" if ok else "no such finding"})
        if self.path == "/api/signoff":
            run_dir = os.path.join(self.runs_dir, run_id)
            if not os.path.isdir(run_dir):
                return self._json({"ok": False, "error": "no such run"}, 404)
            rec = {"record": str(data.get("record", ""))[:20000], "owner": str(data.get("owner", ""))[:200],
                   "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with open(os.path.join(run_dir, "signoff.json"), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, indent=2)
            return self._json({"ok": True})
        return self._json({"ok": False, "error": "unknown endpoint"}, 404)


def serve_api(runs_dir: str, memory_path: str, port: int = 8765, allow_origin: str = "") -> None:
    _Handler.runs_dir, _Handler.memory_path, _Handler.allow_origin = runs_dir, memory_path, allow_origin
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"[backend] API on http://127.0.0.1:{port}/api  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
