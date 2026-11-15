"""Iteration delta: compare this review with the previous review of the same branch.

Research basis: quality degrades across repeated AI refinement rounds without human validation. When an agent
pushes another iteration, the reviewer shows what was fixed, what is still open, and what is new, so regressions
across iterations are visible instead of being reviewed from scratch.
"""
from __future__ import annotations

import difflib
from typing import Dict, List

from .memory import Memory
from .models import Finding


def _same(prev_title: str, prev_dim: str, prev_file: str, f: Finding) -> bool:
    if prev_dim != f.dimension.value or prev_file != f.file:
        return False
    return difflib.SequenceMatcher(None, prev_title.lower(), f.title.lower()).ratio() >= 0.6


def compute_delta(memory: Memory, repo: str, base: str, head: str, run_id: str, head_sha: str,
                  findings: List[Finding]) -> Dict:
    prev = memory.previous_run(repo, base, head, run_id)
    if not prev:
        return {"previous_run": None, "summary": "First review of this branch"}
    prev_id, prev_sha, prev_decision, _ = prev
    prev_rows = memory.kept_findings(prev_id)
    still, fixed = [], []
    matched_now = set()
    for fid, dim, sev, title, file, line, status in prev_rows:
        match = next((f for f in findings if f.id not in matched_now and _same(title, dim, file, f)), None)
        if match:
            matched_now.add(match.id)
            match.delta = "still-open"
            still.append({"previous_id": fid, "now_id": match.id, "title": title, "severity": sev})
        else:
            fixed.append({"previous_id": fid, "title": title, "severity": sev, "file": file})
    new = []
    for f in findings:
        if f.id not in matched_now:
            f.delta = "new"
            new.append({"id": f.id, "title": f.title, "severity": f.severity.value})
    same_commit = bool(prev_sha) and prev_sha == head_sha
    return {"previous_run": prev_id, "previous_decision": prev_decision, "previous_sha": prev_sha,
            "same_commit": same_commit, "fixed": fixed, "still_open": still, "new": new,
            "summary": (f"Re-review of the same commit. " if same_commit else "New iteration since last review. ")
            + f"{len(fixed)} fixed, {len(still)} still open, {len(new)} new"}
