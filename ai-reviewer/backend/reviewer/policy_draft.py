"""Step 1 of the policy lifecycle: the AI DRAFTS the rulebook from repository signals.

A named human must then edit and approve it (fill `approved_by`). Signals per directory:
file count, risky keywords, history (commits, reverts, bug fixes) and test presence.
Works with Gemini (--llm) or as a deterministic heuristic (default without a key).
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field

from .git_tools import churn_and_reverts, file_at, list_files
from .prompts import DRAFT_POLICY_SYSTEM

KEYWORDS = {
    "unsafe/memory": r"\bunsafe\b|\bstackalloc\b|\bMarshal\.|\bUnsafe\.",
    "security": r"(?i)security|untrusted|sanitiz|authoriz|authenticat",
    "crypto": r"\bSHA\d*\b|\bMD5\b|\bHMAC\b|\bAes\b|RandomNumberGenerator",
    "codegen/reflection": r"\bILGenerator\b|\bDynamicMethod\b|Reflection\.Emit|\bActivator\.",
    "serialization format": r"(?i)\bformatter\b|\bwriter\b|\breader\b|\bserializ",
    "money": r"(?i)\b(amount|balance|payment|currency|ledger)\b",
}


class DraftArea(BaseModel):
    name: str
    paths: List[str]
    tier: str = Field(description="low, medium or high")
    guarded: bool
    why: str


class DraftPolicy(BaseModel):
    areas: List[DraftArea]
    notes: str


def _group(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] in ("src", "tests", "test", "lib"):
        return "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:2])
    return parts[0] if len(parts) > 1 else "(root)"


def collect_signals(repo: str, rev: str, max_files_scanned: int = 3000) -> Dict[str, Dict]:
    files = [f for f in list_files(repo, rev) if f.endswith(".cs")]
    groups: Dict[str, Dict] = defaultdict(lambda: {"files": 0, "keywords": defaultdict(int), "test_files": 0})
    for i, f in enumerate(files):
        g = _group(f)
        groups[g]["files"] += 1
        if re.search(r"(?i)tests?/|\.tests?/|tests?\.cs$", f):
            groups[g]["test_files"] += 1
        if i < max_files_scanned:
            text = file_at(repo, rev, f) or ""
            for k, pat in KEYWORDS.items():
                n = len(re.findall(pat, text))
                if n:
                    groups[g]["keywords"][k] += n
    out = {}
    for g, d in groups.items():
        hist = churn_and_reverts(repo, rev, g if g != "(root)" else ".")
        out[g] = {"files": d["files"], "test_files": d["test_files"], "keywords": dict(d["keywords"]), **hist}
    return out


def heuristic_draft(signals: Dict[str, Dict]) -> DraftPolicy:
    areas = []
    for g, s in sorted(signals.items()):
        kw = s["keywords"]
        if s["test_files"] >= max(1, s["files"] // 2):
            tier, why = "low", "mostly test files"
        elif kw.get("unsafe/memory", 0) or kw.get("crypto", 0) or kw.get("security", 0) > 3:
            tier, why = "high", f"risky keywords {kw}"
        elif s["reverts"] > 0 or s["fixes"] > 10 or kw.get("serialization format", 0) > 50:
            tier, why = "high", f"history: {s['reverts']} reverts, {s['fixes']} fixes; keywords {kw}"
        elif kw.get("codegen/reflection", 0):
            tier, why = "medium", f"code generation/reflection {kw}"
        else:
            tier, why = "medium", "library code, no strong risk signal"
        guarded = kw.get("security", 0) > 3 or kw.get("crypto", 0) > 0
        top = g.split("/")[0]
        if g == "(root)":
            path = "*.cs"
        elif g.count("/") == 1 and top in ("src", "tests", "test", "lib"):
            path = f"{g}/*"          # files directly in this folder; sub-folders are their own areas
        else:
            path = f"{g}/**"
        areas.append(DraftArea(name=g, paths=[path], tier=tier, guarded=guarded, why=why))
    return DraftPolicy(areas=areas, notes="Heuristic draft from keyword and history signals.")


def llm_draft(client, model: str, signals: Dict[str, Dict]) -> DraftPolicy:
    lines = [f"- {g}: {s['files']} .cs files ({s['test_files']} tests); keywords {s['keywords']}; "
             f"history: {s['commits']} commits, {s['reverts']} reverts, {s['fixes']} fix commits"
             for g, s in sorted(signals.items())]
    prompt = "Repository signals per directory:\n" + "\n".join(lines)
    return client.generate(role="draft-policy", model=model, system=DRAFT_POLICY_SYSTEM, prompt=prompt,
                           schema=DraftPolicy)


def write_draft(draft: DraftPolicy, base_policy_path: str, out_path: str, source: str) -> None:
    base = {}
    if os.path.exists(base_policy_path):
        with open(base_policy_path, encoding="utf-8") as fh:
            base = yaml.safe_load(fh) or {}
    base["version"] = "draft-" + source
    base["approved_by"] = None
    base["approved_on"] = None
    base["areas"] = [a.model_dump() for a in draft.areas]
    header = ("# AI-DRAFTED POLICY — NOT APPROVED.\n"
              f"# Source: {source}. Notes: {draft.notes}\n"
              "# A named human must review every area, edit tiers/paths, then set approved_by and approved_on.\n"
              "# content_rules, change_rules, no_go and gates were copied from the base policy.\n\n")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + yaml.safe_dump(base, sort_keys=False, allow_unicode=True))
