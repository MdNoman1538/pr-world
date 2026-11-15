"""Reviewer agents added in v3: requirement check (3 blind roles), validator panel, investigator.

Design rules (locked):
- Blind roles: the requirement analyst sees only the requirement; the change interpreter sees only the code;
  the judge sees only their two lists. Nobody sees the other side's input.
- Every claim about code must quote code that the evidence check finds at the cited lines; a "met" without
  grounded code is downgraded to "no evidence".
- The panel and the investigator can confirm or dispute a Critical finding; they never delete it: a disputed
  finding is shown as Major with the votes, and stays in the audit list.
Research: Lu et al. 2025 (multi-role review, Q1-Q3); AgentCoder (blind test design); Panickssery et al. 2024 and
Zheng et al. 2023 (a model judging its own work favours it, so the panel uses different models).
"""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .context import PRContext, evidence_matches
from .git_tools import file_at, grep
from .models import Finding, Severity


# ---------------------------------------------------------------------------------------------- schemas
class ReqItem(BaseModel):
    id: str = Field(description="R1, R2, ... one checkable statement each")
    text: str = Field(description="One short, checkable statement taken from the requirement")
    kind: str = Field(description="behaviour | constraint | non-functional")
    testable: bool = Field(description="Could a test or a code reading decide it?")
    unclear: str = Field(description="What is ambiguous about it, or empty")


class ReqItems(BaseModel):
    items: List[ReqItem]


class Behaviour(BaseModel):
    id: str = Field(description="B1, B2, ...")
    text: str = Field(description="What the changed code does, in one plain sentence")
    file: str
    line_start: int
    line_end: int
    evidence: str = Field(description="Exact code copied from the context that does this")


class Behaviours(BaseModel):
    behaviours: List[Behaviour]


class Judgement(BaseModel):
    item_id: str
    status: str = Field(description="met | partly | missing | contradicted | unclear")
    behaviour_ids: List[str] = Field(description="Behaviours that prove the status (empty for missing)")
    reason: str


class Judgements(BaseModel):
    results: List[Judgement]
    extra_behaviours: List[str] = Field(description="Behaviour ids that serve no requirement item (unrequested changes)")


class PanelVote(BaseModel):
    real: bool = Field(description="Is this a real problem in the code shown? (Q2: false = a made-up problem)")
    nitpick: bool = Field(description="Q1: is it only cosmetic?")
    severity: str = Field(description="Q3: Blocker | ShouldFix | Nit")
    reason: str


class InvestigatorStep(BaseModel):
    action: str = Field(description="search | read | run_test | conclude")
    argument: str = Field(description="search: a regex; read: path:start-end; run_test: a dotnet test filter; conclude: empty")
    verdict: str = Field(description="when action=conclude: confirmed | rejected | unsure; else empty")
    evidence: str = Field(description="when concluding: the exact code or test output that decides it")
    reason: str


# ---------------------------------------------------------------------------------------------- prompts
ANALYST_SYS = """You are the REQUIREMENT ANALYST. You see only the requirement, never the code.
Split it into small, checkable statements (R1, R2, ...). Keep the author's meaning; do not invent features.
Mark statements that are vague in 'unclear' instead of guessing. Include limits, edge values and error cases
that the requirement states (for example 'exactly 5,000 EUR', 'fee capped at 20 EUR')."""
INTERPRETER_SYS = """You are the CHANGE INTERPRETER. You see only the changed code, never the requirement.
List what the changed code actually does (B1, B2, ...), one plain sentence each, including edge values,
error handling and side effects. Every behaviour must quote the exact code that does it, with the file and
the line numbers as tagged in the context. Do not guess intent; describe behaviour."""
JUDGE_SYS = """You are the JUDGE. You see two lists only: requirement items (from an analyst who never saw the code)
and behaviours (from an interpreter who never saw the requirement). For each item decide:
met (behaviours fully do it), partly (some of it), missing (no behaviour does it), contradicted (a behaviour
does the opposite or a different value), unclear (the item itself is ambiguous). Cite behaviour ids as proof.
List behaviours that serve no item as extra_behaviours. Be strict on exact values and limits."""
PANEL_SYS = """You are one member of a VALIDATOR PANEL. Other models vote independently. Judge ONE finding against
the code shown: Q1 is it only a nitpick? Q2 is it a real problem (false if the code does not show it)?
Q3 how severe (Blocker = must not merge, ShouldFix = real but not blocking, Nit = cosmetic)? Be concrete."""
INVESTIGATOR_SYS = """You are the INVESTIGATOR. Confirm or reject ONE Critical finding before a person sees it.
Each turn choose one action: search (regex over the repository's C# files), read (path:start-end of a file at
the PR head), run_test (a dotnet test filter; only if allowed), or conclude. Conclude as soon as the evidence
decides it. 'confirmed' and 'rejected' must quote the exact code or test output that decides it."""


def _num(items: List[str]) -> str:
    return "\n".join(items)


# ---------------------------------------------------------------------------------------------- requirement check
def requirement_check(client, req_text: str, ctx: PRContext, ctx_text: str) -> Dict:
    if not req_text.strip():
        return {"ran": False, "reason": "No requirement text was supplied."}
    # analyst and interpreter run in parallel and never see each other's input
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(client.generate, role="requirement:analyst", system=ANALYST_SYS,
                         prompt=f"REQUIREMENT:\n{req_text[:12000]}", schema=ReqItems)
        fi = pool.submit(client.generate, role="requirement:interpreter", system=INTERPRETER_SYS,
                         prompt=f"CHANGED CODE (line-tagged slices):\n{ctx_text}", schema=Behaviours)
        items, beh = fa.result().items, fi.result().behaviours
    grounded = {}
    for b in beh:
        ok = evidence_matches(ctx, b.file, b.line_start, b.line_end, b.evidence)
        grounded[b.id] = ok
    beh_text = _num([f"[{b.id}] {b.text} ({b.file}:{b.line_start}){'' if grounded[b.id] else ' [NOT GROUNDED]'}" for b in beh])
    item_text = _num([f"[{i.id}] ({i.kind}{', unclear: ' + i.unclear if i.unclear else ''}) {i.text}" for i in items])
    judge = client.generate(role="requirement:judge", system=JUDGE_SYS,
                            prompt=f"REQUIREMENT ITEMS:\n{item_text}\n\nBEHAVIOURS OF THE CHANGE:\n{beh_text}", schema=Judgements)
    by_b = {b.id: b for b in beh}
    results = []
    for it in items:
        j = next((r for r in judge.results if r.item_id == it.id), None)
        status = j.status if j else "missing"
        proof = [b for b in (j.behaviour_ids if j else []) if b in by_b]
        good = [b for b in proof if grounded.get(b)]
        note = ""
        if status in ("met", "partly", "contradicted") and not good:
            note = "downgraded: no behaviour with grounded code was cited"
            status = "no_evidence"
        results.append({"id": it.id, "text": it.text, "kind": it.kind, "testable": it.testable, "unclear": it.unclear,
                        "status": status, "reason": (j.reason if j else "the judge gave no result for this item"), "note": note,
                        "proof": [{"id": b, "text": by_b[b].text, "file": by_b[b].file, "line": by_b[b].line_start,
                                   "evidence": by_b[b].evidence[:400], "grounded": grounded.get(b, False)} for b in proof]})
    counts = {k: sum(1 for r in results if r["status"] == k) for k in ["met", "partly", "missing", "contradicted", "unclear", "no_evidence"]}
    n = len([r for r in results if r["testable"]]) or len(results)
    met = sum(1 for r in results if r["status"] == "met" and (r["testable"] or not n))
    conf = (met + 0.5) / (n + 1) if n else None
    extra = [{"id": b, "text": by_b[b].text, "file": by_b[b].file, "line": by_b[b].line_start}
             for b in judge.extra_behaviours if b in by_b]
    return {"ran": True, "items": results, "counts": counts, "testable": n, "met": met,
            "conf": round(conf, 3) if conf is not None else None, "extra_behaviours": extra,
            "behaviours": [{**b.model_dump(), "grounded": grounded[b.id]} for b in beh]}


# ---------------------------------------------------------------------------------------------- validator panel
def validator_panel(client, findings: List[Finding], ctx_text: str, size: int) -> Dict:
    crit = [f for f in findings if f.kept and f.severity == Severity.BLOCKER]
    report = {"ran": bool(crit), "size": size, "votes": {}}
    if not crit:
        return report
    jobs = []
    for f in crit:
        desc = (f"FINDING {f.id}: {f.title}\nClaim: {f.claim}\nAt {f.file}:{f.line_start}-{f.line_end}\nQuoted code:\n{f.evidence}\n\n"
                f"CODE CONTEXT:\n{ctx_text[:60000]}")
        for i in range(size):
            jobs.append((f, i, desc))

    def vote(job):
        f, i, desc = job
        try:
            return f.id, i, client.generate(role=f"panel:{i}", system=PANEL_SYS, prompt=desc, schema=PanelVote), None
        except Exception as e:
            return f.id, i, None, str(e)[:300]

    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
        results = list(pool.map(vote, jobs))
    for f in crit:
        vs = [(i, v, err) for fid, i, v, err in results if fid == f.id]
        ok = [v for _, v, e in vs if v is not None]
        real = sum(1 for v in ok if v.real and not v.nitpick)
        rec = {"members": len(vs), "answered": len(ok), "real": real,
               "votes": [{"member": i, **(v.model_dump() if v else {"error": err})} for i, v, err in vs]}
        if len(ok) < 2:
            rec["outcome"] = "not enough votes"
        elif real * 2 > len(ok):
            rec["outcome"] = "confirmed"
        else:
            rec["outcome"] = "disputed"
            f.severity = Severity.SHOULD_FIX
            f.drop_reason = ""
        f.validator = {**(f.validator or {}), "panel": rec}
        report["votes"][f.id] = rec
    return report


# ---------------------------------------------------------------------------------------------- investigator
def _tool(action: str, arg: str, repo: str, head: str, allow_test: bool, run_test) -> str:
    if action == "search":
        try:
            re.compile(arg)
        except re.error:
            return "invalid regex"
        rows = grep(repo, head, arg, max_hits=40)
        return "\n".join(rows) or "no matches"
    if action == "read":
        m = re.match(r"^(.+?):(\d+)-(\d+)$", arg.strip())
        if not m:
            return "use path:start-end"
        text = file_at(repo, head, m.group(1))
        if text is None:
            return "file not found at the PR head"
        lines = text.splitlines()
        a, b = max(1, int(m.group(2))), min(len(lines), int(m.group(3)), int(m.group(2)) + 80)
        return "\n".join(f"{n}| {lines[n - 1]}" for n in range(a, b + 1))
    if action == "run_test":
        if not allow_test:
            return "running tests is not allowed in this review (tests were not requested)"
        return run_test(arg)
    return "unknown action"


def investigate(client, findings: List[Finding], ctx: PRContext, repo: str, head: str, max_steps: int,
                allow_test: bool = False, run_test=None) -> Dict:
    crit = [f for f in findings if f.kept and f.severity == Severity.BLOCKER]
    report = {"ran": bool(crit), "cases": {}}
    for f in crit:
        steps, transcript, tests_run = [], "", 0
        verdict, evidence, reason = "unsure", "", "step limit reached"
        for n in range(1, max_steps + 1):
            prompt = (f"FINDING {f.id}: {f.title}\nClaim: {f.claim}\nAt {f.file}:{f.line_start}\nQuoted:\n{f.evidence}\n\n"
                      f"Tools: search, read, {'run_test, ' if allow_test else ''}conclude. Step {n} of {max_steps}.\n"
                      f"TRANSCRIPT SO FAR:\n{transcript or '(none)'}")
            try:
                st = client.generate(role="investigator", system=INVESTIGATOR_SYS, prompt=prompt, schema=InvestigatorStep)
            except Exception as e:
                reason = f"investigator call failed: {str(e)[:200]}"
                break
            if st.action == "conclude":
                verdict, evidence, reason = (st.verdict if st.verdict in ("confirmed", "rejected", "unsure") else "unsure"), st.evidence, st.reason
                if verdict in ("confirmed", "rejected") and not _grounded_anywhere(st.evidence, ctx, transcript):
                    reason += " (downgraded to unsure: the quoted evidence was not found in the code or the tool output)"
                    verdict = "unsure"
                steps.append({"step": n, "action": "conclude", "verdict": verdict, "reason": st.reason})
                break
            if st.action == "run_test":
                tests_run += 1
                if tests_run > 1:
                    out = "only one test run is allowed per investigation"
                else:
                    out = _tool(st.action, st.argument, repo, head, allow_test, run_test)
            else:
                out = _tool(st.action, st.argument, repo, head, allow_test, run_test)
            out = out[:3000]
            steps.append({"step": n, "action": st.action, "argument": st.argument[:200], "result": out[:600], "reason": st.reason})
            transcript += f"\n[{n}] {st.action} {st.argument}\n{out}\n"
        case = {"verdict": verdict, "evidence": evidence[:600], "reason": reason, "steps": steps}
        if verdict == "rejected":
            f.severity = Severity.SHOULD_FIX
        f.validator = {**(f.validator or {}), "investigation": case}
        report["cases"][f.id] = case
    return report


def _grounded_anywhere(snippet: str, ctx: PRContext, transcript: str) -> bool:
    norm = lambda s: re.sub(r"\s+", "", s or "")
    t = norm(snippet)
    if len(t) < 6:
        return False
    if t in norm(transcript):
        return True
    return any(t in norm("".join(lines)) for lines in ctx.head_text.values())


def jeffreys(k: int, n: int) -> Optional[float]:
    return None if n <= 0 else (k + 0.5) / (n + 1)
