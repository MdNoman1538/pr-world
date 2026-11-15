"""Validator: deterministic evidence check, then LLM Q1-Q3 filtering, then policy thresholds.

Order matters:
1. Evidence check (code, not AI): the cited file/line must exist and the quoted snippet must be there.
   Hallucinated findings are dropped here, before any model can be persuaded by them.
2. Q1-Q3 chain-of-thought re-scoring by a (stronger) model, as defined in the research specification:
   Q1 nitpick check (cosmetic/style → tag Nit), Q2 hallucination check (non-existent bug → eliminate),
   Q3 severity scoring (true impact → Blocker / ShouldFix / Nit). Duplicates are merged.
3. Policy thresholds: low-confidence Blockers are demoted; Nits are hidden unless the policy shows them.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .context import PRContext, evidence_matches
from .models import Dimension, Finding, Severity, ValidatorOutput
from .prompts import VALIDATOR_SYSTEM, validator_prompt


def check_evidence(findings: List[Finding], ctx: PRContext) -> Tuple[List[Finding], List[Finding]]:
    kept, dropped = [], []
    for f in findings:
        if f.source.startswith("sensor:"):
            kept.append(f)
            continue
        ok = evidence_matches(ctx, f.file, f.line_start, f.line_end, f.evidence)
        f.evidence_verified = ok
        if ok:
            kept.append(f)
        else:
            f.kept = False
            f.drop_reason = "Evidence not found at the cited file/lines (possible hallucination)"
            dropped.append(f)
    return kept, dropped


def _format(findings: List[Finding]) -> str:
    rows = []
    for f in findings:
        rows.append(f"[id={f.id}] [severity={f.severity.value}] [dimension={f.dimension.value}] "
                    f"{f.file}:{f.line_start}-{f.line_end}\n  title: {f.title}\n  claim: {f.claim}\n"
                    f"  evidence: {f.evidence}\n  confidence: {f.confidence}")
    return "\n".join(rows)


def run_validator(client, model: str, findings: List[Finding], ctx_text: str, requirement_text: str,
                  gates: Dict) -> Tuple[List[Finding], List[Finding], List[str]]:
    errors: List[str] = []
    llm_findings = [f for f in findings if f.source.startswith("specialist:")]
    sensor_findings = [f for f in findings if f.source.startswith("sensor:")]
    kept: List[Finding] = list(sensor_findings)
    dropped: List[Finding] = []

    if llm_findings:
        try:
            out: ValidatorOutput = client.generate(role="validator", model=model, system=VALIDATOR_SYSTEM,
                                                   prompt=validator_prompt(_format(llm_findings), ctx_text,
                                                                           requirement_text),
                                                   schema=ValidatorOutput)
            verdicts = {v.finding_id: v for v in out.verdicts}
        except Exception as e:
            errors.append(f"validator failed: {e}")
            verdicts = {}
        for f in llm_findings:
            v = verdicts.get(f.id)
            if v is None:
                # no verdict: keep, but mark unvalidated so the human knows
                f.validator = {"status": "not validated"}
                kept.append(f)
                continue
            f.validator = v.model_dump()
            if v.q2_hallucination:
                f.kept = False
                f.drop_reason = f"Q2 hallucination check: {v.reason}"
                dropped.append(f)
                continue
            if v.duplicate_of and v.duplicate_of != f.id:
                f.kept = False
                f.drop_reason = f"Duplicate of {v.duplicate_of}"
                dropped.append(f)
                continue
            f.severity = Severity.NIT if v.q1_nitpick else v.q3_severity
            kept.append(f)

    final: List[Finding] = []
    min_conf = float(gates.get("min_blocker_confidence", 0.6))
    show_nits = bool(gates.get("show_nits", False))
    for f in kept:
        # fixed rule: Critical is for correctness and safety errors only. Missing tests, design, readability and
        # speed are real but never lock a merge on their own: they become Major (the reason stays on the finding).
        if f.severity == Severity.BLOCKER and f.dimension not in (Dimension.CORRECTNESS, Dimension.SAFETY):
            f.severity = Severity.SHOULD_FIX
            f.drop_reason = f"Capped at Major: a {f.dimension.value} finding is never Critical on its own"
        if f.severity == Severity.BLOCKER and f.confidence < min_conf:
            f.severity = Severity.SHOULD_FIX
            f.drop_reason = f"Demoted from Blocker: confidence {f.confidence} < {min_conf}"
        if f.severity == Severity.NIT and not show_nits:
            f.kept = False
            f.drop_reason = "Q1 nitpick: suppressed by policy (gates.show_nits=false)" if (f.validator or {}).get(
                "q1_nitpick") else "Nit suppressed by policy (gates.show_nits=false)"
            dropped.append(f)
            continue
        final.append(f)
    order = {Severity.BLOCKER: 0, Severity.SHOULD_FIX: 1, Severity.NIT: 2}
    final.sort(key=lambda f: (order[f.severity], f.dimension.value, f.file, f.line_start))
    return final, dropped, errors
