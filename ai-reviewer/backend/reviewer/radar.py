"""Requirement radar: trace every changed hunk to a requirement item (aligned / supporting / tangled / unclear)
and every requirement item to the hunks that cover it (covered / partial / missing).

Research basis: tangled changes (unrelated edits mixed into a PR) hide defects and slow review; the dashboard's
"PR-Issue Requirement Radar" zone proves the PR satisfies the linked issue. Hunk ids are produced by code and the
model's answer is validated against them, so the radar cannot invent changes.
"""
from __future__ import annotations

from typing import Dict, List

from .git_tools import PullRequest
from .models import RadarOutput
from .prompts import RADAR_SYSTEM, radar_prompt

CLASSES = {"aligned", "supporting", "tangled", "unclear"}
STATUSES = {"covered", "partial", "missing"}


def extract_hunks(pr: PullRequest, max_lines: int = 30) -> List[Dict]:
    hunks, n = [], 0
    for f in pr.files:
        for h in f.hunks:
            n += 1
            end = h.new_start + max(h.new_len, 1) - 1
            hunks.append({"id": f"H{n:02d}", "file": f.path, "start": h.new_start, "end": end,
                          "added": h.added[:max_lines], "removed": h.removed[:max_lines],
                          "n_added": h.new_len, "n_removed": h.old_len})
        if not f.hunks:
            n += 1
            hunks.append({"id": f"H{n:02d}", "file": f.path, "start": 0, "end": 0, "added": [], "removed": [],
                          "n_added": 0, "n_removed": 0, "note": "binary or rename-only"})
    return hunks


def hunks_text(hunks: List[Dict]) -> str:
    rows = []
    for h in hunks:
        rows.append(f"[{h['id']}] {h['file']} new lines {h['start']}-{h['end']}")
        rows += [f"  - {t}" for t in h["removed"]] + [f"  + {t}" for t in h["added"]]
    return "\n".join(rows)


def build_radar(client, model: str, pr: PullRequest, requirement_text: str) -> Dict:
    hunks = extract_hunks(pr)
    known = {h["id"] for h in hunks}
    result = {"items": [], "hunks": hunks, "counts": {}, "ran": False, "note": ""}
    if not requirement_text.strip():
        result["note"] = "No requirement text: radar not built"
        for h in hunks:
            h.update(classification="unclear", item_ids=[], reason="no requirement")
        return _count(result)
    try:
        out: RadarOutput = client.generate(role="radar", model=model, system=RADAR_SYSTEM,
                                           prompt=radar_prompt(requirement_text, hunks_text(hunks)),
                                           schema=RadarOutput)
    except Exception as e:  # never fail the whole review on the radar
        result["note"] = f"Radar call failed: {e}"
        for h in hunks:
            h.update(classification="unclear", item_ids=[], reason="radar failed")
        return _count(result)
    result["ran"] = True
    item_ids = {i.id for i in out.items}
    by_hunk = {x.hunk_id: x for x in out.hunks if x.hunk_id in known}
    for h in hunks:
        x = by_hunk.get(h["id"])
        cls = (x.classification.lower().strip() if x else "unclear")
        h.update(classification=cls if cls in CLASSES else "unclear",
                 item_ids=[i for i in (x.item_ids if x else []) if i in item_ids],
                 reason=x.reason if x else "not classified by the model")
    for it in out.items:
        st = it.status.lower().strip()
        result["items"].append({"id": it.id, "text": it.text, "status": st if st in STATUSES else "partial",
                                "hunk_ids": [h for h in it.hunk_ids if h in known], "reason": it.reason})
    return _count(result)


def _count(result: Dict) -> Dict:
    c: Dict[str, int] = {}
    for h in result["hunks"]:
        c[h.get("classification", "unclear")] = c.get(h.get("classification", "unclear"), 0) + 1
    for it in result["items"]:
        c["item_" + it["status"]] = c.get("item_" + it["status"], 0) + 1
    result["counts"] = c
    return result
