"""Fix suggestion agent: a ready-to-apply patch for each Blocker / ShouldFix finding.

The model proposes (old_code, new_code); code then locates old_code in the PR head file (exact, or whitespace-
tolerant but unique) and builds the unified diff itself, so every patch applies cleanly to the PR head by
construction. Proposals that cannot be located uniquely are discarded, never guessed.
"""
from __future__ import annotations

import difflib
import os
import re
from typing import Dict, List, Optional, Tuple

from .context import PRContext
from .models import Finding, FixOutput, Severity
from .prompts import FIX_SYSTEM, fix_prompt


def _locate(lines: List[str], old: str) -> Optional[Tuple[int, int]]:
    old_lines = [l.rstrip("\r") for l in old.strip("\n").splitlines()]
    if not old_lines:
        return None
    n = len(old_lines)
    exact = [i for i in range(len(lines) - n + 1) if lines[i:i + n] == old_lines]
    if len(exact) == 1:
        return exact[0], exact[0] + n
    norm = lambda s: re.sub(r"\s+", "", s)
    target = [norm(l) for l in old_lines]
    loose = [i for i in range(len(lines) - n + 1) if [norm(l) for l in lines[i:i + n]] == target]
    if len(loose) == 1:
        return loose[0], loose[0] + n
    return None


def _reindent(new: str, original_first_line: str, old_first_line: str) -> List[str]:
    new_lines = new.strip("\n").splitlines()
    want = len(original_first_line) - len(original_first_line.lstrip())
    have = len(old_first_line) - len(old_first_line.lstrip())
    if want == have or not new_lines:
        return new_lines
    delta = want - have
    out = []
    for l in new_lines:
        out.append((" " * delta + l) if delta > 0 else l[min(-delta, len(l) - len(l.lstrip())):])
    return out


def make_patch(path: str, lines: List[str], old: str, new: str) -> Optional[str]:
    loc = _locate(lines, old)
    if loc is None:
        return None
    a, b = loc
    old_first = old.strip("\n").splitlines()[0]
    replacement = _reindent(new, lines[a], old_first)
    updated = lines[:a] + replacement + lines[b:]
    diff = difflib.unified_diff([l + "\n" for l in lines], [l + "\n" for l in updated],
                                fromfile=f"a/{path}", tofile=f"b/{path}", n=3)
    text = "".join(diff)
    return text or None


def suggest_fixes(client, model: str, findings: List[Finding], ctx: PRContext, ctx_text: str,
                  out_dir: str, limit: int = 8) -> Dict:
    targets = [f for f in findings if f.severity in (Severity.BLOCKER, Severity.SHOULD_FIX)
               and f.file in ctx.head_text][:limit]
    stats = {"requested": len(targets), "proposed": 0, "applied": 0, "rejected": 0, "error": ""}
    if not targets:
        return stats
    text = "\n".join(f"[{f.id}] {f.severity.value} {f.file}:{f.line_start}-{f.line_end} {f.title}\n"
                     f"  claim: {f.claim}\n  evidence: {f.evidence}\n  hint: {f.suggested_fix}" for f in targets)
    try:
        out: FixOutput = client.generate(role="fixer", model=model, system=FIX_SYSTEM,
                                         prompt=fix_prompt(text, ctx_text), schema=FixOutput)
    except Exception as e:
        stats["error"] = str(e)
        return stats
    by_id = {f.id: f for f in targets}
    os.makedirs(os.path.join(out_dir, "patches"), exist_ok=True)
    combined = []
    for p in out.fixes:
        stats["proposed"] += 1
        f = by_id.get(p.finding_id)
        lines = ctx.head_text.get(p.file or (f.file if f else ""))
        if f is None or lines is None:
            stats["rejected"] += 1
            continue
        patch = make_patch(f.file, lines, p.old_code, p.new_code)
        if not patch:
            stats["rejected"] += 1
            continue
        f.patch, f.patch_explanation = patch, f"{p.explanation} (fix confidence {p.confidence:.2f})"
        with open(os.path.join(out_dir, "patches", f"{f.id}.patch"), "w", encoding="utf-8") as fh:
            fh.write(patch)
        combined.append(patch)
        stats["applied"] += 1
    return stats
