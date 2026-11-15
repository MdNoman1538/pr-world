"""Review memory and the reviewer's track record (SQLite).

Plays the role the research gives to a persistent memory layer (e.g. Mem0): consistency across
reviews, and lessons from human feedback. It also measures trust: per dimension, how many findings
humans accepted vs rejected, and how many escapes (problems the reviewer missed) were reported.
Trust is earned per area and drops after escapes.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List

from .models import Finding, Review

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, created_at TEXT, repo TEXT, base TEXT, head TEXT, requirement_id TEXT,
  tier TEXT, decision TEXT, n_findings INTEGER, n_dropped INTEGER, models TEXT, owner TEXT);
CREATE TABLE IF NOT EXISTS findings (
  run_id TEXT, finding_id TEXT, dimension TEXT, source TEXT, severity TEXT, title TEXT, claim TEXT,
  file TEXT, line INTEGER, kept INTEGER, drop_reason TEXT,
  status TEXT DEFAULT 'open', note TEXT, decided_by TEXT, decided_at TEXT,
  PRIMARY KEY (run_id, finding_id));
CREATE TABLE IF NOT EXISTS escapes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, run_id TEXT, dimension TEXT, note TEXT, reported_by TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Memory:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(runs)")}
        if "head_sha" not in cols:   # upgrade a v1 memory file
            self.db.execute("ALTER TABLE runs ADD COLUMN head_sha TEXT")
            self.db.commit()

    def save_review(self, r: Review) -> None:
        self.db.execute("INSERT OR REPLACE INTO runs (run_id, created_at, repo, base, head, requirement_id, tier, "
                        "decision, n_findings, n_dropped, models, owner, head_sha) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (r.run_id, r.created_at, r.repo, r.base, r.head, r.requirement_id, r.tier.tier.value,
                         r.decision, len(r.findings), len(r.dropped_findings), str(r.models), r.owner, r.head_sha))
        for f in r.findings + r.dropped_findings:
            self.db.execute("INSERT OR REPLACE INTO findings (run_id, finding_id, dimension, source, severity, title, "
                            "claim, file, line, kept, drop_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (r.run_id, f.id, f.dimension.value, f.source, f.severity.value, f.title, f.claim,
                             f.file, f.line_start, int(f.kept), f.drop_reason))
        self.db.commit()

    def feedback(self, run_id: str, finding_id: str, verdict: str, note: str, by: str) -> bool:
        cur = self.db.execute("UPDATE findings SET status=?, note=?, decided_by=?, decided_at=? "
                              "WHERE run_id=? AND finding_id=?", (verdict, note, by, _now(), run_id, finding_id))
        self.db.commit()
        return cur.rowcount > 0

    def escape(self, run_id: str, dimension: str, note: str, by: str) -> None:
        self.db.execute("INSERT INTO escapes (created_at, run_id, dimension, note, reported_by) VALUES (?,?,?,?,?)",
                        (_now(), run_id, dimension, note, by))
        self.db.commit()

    def track_record(self) -> Dict[str, Dict]:
        out: Dict[str, Dict] = {}
        for dim, status, n in self.db.execute(
                "SELECT dimension, status, COUNT(*) FROM findings WHERE kept=1 GROUP BY dimension, status"):
            out.setdefault(dim, {"accepted": 0, "rejected": 0, "open": 0, "escapes": 0})
            if status in ("accepted", "rejected", "open"):
                out[dim][status] += n
        for dim, n in self.db.execute("SELECT dimension, COUNT(*) FROM escapes GROUP BY dimension"):
            out.setdefault(dim, {"accepted": 0, "rejected": 0, "open": 0, "escapes": 0})["escapes"] = n
        for dim, d in out.items():
            judged = d["accepted"] + d["rejected"]
            d["precision"] = round(d["accepted"] / judged, 2) if judged else None
            if d["escapes"] > 0:
                d["trust"] = "lowered after escape(s): more human review"
            elif judged < 10:
                d["trust"] = "not enough feedback yet (need 10+ judged findings)"
            elif (d["precision"] or 0) >= 0.8:
                d["trust"] = "earned"
            else:
                d["trust"] = "watch: many rejected findings"
        return out

    def rejected_notes(self, limit: int = 12) -> str:
        rows = self.db.execute("SELECT dimension, title, note FROM findings WHERE status='rejected' "
                               "ORDER BY decided_at DESC LIMIT ?", (limit,)).fetchall()
        return "\n".join(f"- [{d}] '{t}' was rejected by a human" + (f": {n}" if n else "") for d, t, n in rows)

    def totals(self) -> Dict:
        runs = self.db.execute("SELECT COUNT(*), SUM(n_findings), SUM(n_dropped) FROM runs").fetchone()
        dec = dict(self.db.execute("SELECT decision, COUNT(*) FROM runs GROUP BY decision").fetchall())
        return {"runs": runs[0] or 0, "findings_shown": runs[1] or 0, "findings_filtered": runs[2] or 0,
                "decisions": dec}


    # ------------------------------------------------------------ familiarity and iteration delta
    def past_findings_for(self, path: str, limit: int = 5) -> List[str]:
        rows = self.db.execute("SELECT f.run_id, f.severity, f.title, f.status FROM findings f "
                               "WHERE f.file=? AND f.kept=1 ORDER BY f.run_id DESC LIMIT ?", (path, limit)).fetchall()
        return [f"{run}: [{sev}] {title} ({status})" for run, sev, title, status in rows]

    def previous_run(self, repo: str, base: str, head: str, exclude_run: str):
        return self.db.execute("SELECT run_id, head_sha, decision, created_at FROM runs WHERE repo=? AND base=? "
                               "AND head=? AND run_id<>? ORDER BY created_at DESC, run_id DESC LIMIT 1",
                               (repo, base, head, exclude_run)).fetchone()

    def kept_findings(self, run_id: str):
        return self.db.execute("SELECT finding_id, dimension, severity, title, file, line, status FROM findings "
                               "WHERE run_id=? AND kept=1", (run_id,)).fetchall()
