"""The gate: every area ends as verified, human or blocked. The AI can lock; it can never approve.

Final decision is one of:
  BLOCKED            a rule or a verified Blocker finding locks the merge
  NEEDS_HUMAN        some areas need a named human to check and sign
  READY_FOR_SIGNOFF  all areas verified; the named owner still signs (never auto-merged)
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

from .context import PRContext
from .models import (AreaResult, AreaStatus, Dimension, Finding, Refusal, SensorResult, Severity,
                     SpecialistOutput, Tier, TierDecision)
from .policy import Policy

V, H, B = AreaStatus.VERIFIED, AreaStatus.HUMAN, AreaStatus.BLOCKED


def _sensor(sensors: List[SensorResult], name: str) -> Optional[SensorResult]:
    return next((s for s in sensors if s.name == name), None)


def _by(findings: List[Finding], dim: Dimension, sev: Optional[Severity] = None) -> List[Finding]:
    return [f for f in findings if f.dimension == dim and (sev is None or f.severity == sev)]


def _ids(fs: List[Finding]) -> List[str]:
    return [f"{f.id} {f.file}:{f.line_start}" for f in fs]


def overall_alignment(outputs: Dict[Dimension, SpecialistOutput]) -> Tuple[str, str]:
    """Correctness specialist owns the requirement verdict; others are a tie-break."""
    if Dimension.CORRECTNESS in outputs:
        o = outputs[Dimension.CORRECTNESS]
        return o.requirement_alignment.value, o.alignment_reason
    votes = Counter(o.requirement_alignment.value for o in outputs.values())
    if not votes:
        return "unknown", "No specialist produced a verdict"
    v, _ = votes.most_common(1)[0]
    return v, "Majority of specialists"


def evaluate(*, tier: TierDecision, policy: Policy, sensors: List[SensorResult], findings: List[Finding],
             outputs: Dict[Dimension, SpecialistOutput], ctx: PRContext, requirement_present: bool,
             plan_given: bool, radar: Optional[Dict] = None) -> Tuple[List[AreaResult], str, str, TierDecision,
                                                                       List[str]]:
    areas: List[AreaResult] = []
    not_checked: List[str] = []

    # AI may RAISE the tier (never lower it): a verified safety Blocker makes it high.
    if _by(findings, Dimension.SAFETY, Severity.BLOCKER) and tier.tier != Tier.HIGH:
        tier = tier.model_copy(update={"tier": Tier.HIGH, "signoffs_required": int(policy.gates.get("high_signoffs", 2)),
                                       "reasons": tier.reasons + ["Raised to high: verified safety Blocker"]})

    # WHAT: does it do what the requirement asks?
    align, why = overall_alignment(outputs)
    if not requirement_present:
        areas.append(AreaResult(area="What", status=H, reason="No requirement text supplied: intent cannot be "
                                "verified. Pass --req-file or --issue."))
    elif align == "met" and radar and any(i["status"] == "missing" for i in radar.get("items", [])):
        miss = [f"{i['id']}: {i['text']}" for i in radar["items"] if i["status"] == "missing"]
        areas.append(AreaResult(area="What", status=H, reason="Specialists say met, but the requirement radar finds "
                                "items with no implementing code", evidence=miss[:5]))
    elif align == "met":
        areas.append(AreaResult(area="What", status=V, reason=f"Change meets the requirement: {why}"))
    elif align == "not_met":
        areas.append(AreaResult(area="What", status=B, reason=f"Requirement not met: {why}"))
    else:
        areas.append(AreaResult(area="What", status=H, reason=f"Requirement match is {align}: {why}"))

    # WHERE: risk tier from the rulebook
    if tier.tier == Tier.HIGH or tier.guarded_paths:
        g = f"; guarded/no-go: {', '.join(tier.guarded_paths)}" if tier.guarded_paths else ""
        areas.append(AreaResult(area="Where", status=H, reason=f"Tier HIGH → full human read and "
                                f"{tier.signoffs_required} sign-off(s) required{g}", evidence=tier.reasons[:6]))
    else:
        areas.append(AreaResult(area="Where", status=V, reason=f"Tier {tier.tier.value.upper()} per rulebook",
                                evidence=tier.reasons[:6]))

    # WHY: is the change linked to an approved requirement?
    if requirement_present:
        areas.append(AreaResult(area="Why", status=V, reason="Linked to a requirement"))
    else:
        areas.append(AreaResult(area="Why", status=H, reason="No linked requirement"))

    # PLAN: scope vs approved plan
    if plan_given:
        if tier.out_of_plan:
            guarded_oop = [p for p in tier.out_of_plan if p in tier.guarded_paths]
            areas.append(AreaResult(area="Plan", status=B if guarded_oop else H,
                                    reason=("Out-of-plan change in a guarded area: " if guarded_oop else
                                            "Files outside the approved plan: ") + ", ".join(tier.out_of_plan)))
        else:
            areas.append(AreaResult(area="Plan", status=V, reason="All changed files are inside the approved plan"))
    else:
        not_checked.append("Scope vs approved plan (no --plan given)")

    # SCOPE: requirement radar (tangled hunks = changes the requirement did not ask for)
    if radar and radar.get("ran"):
        tangled = [h for h in radar["hunks"] if h.get("classification") == "tangled"]
        unclear = [h for h in radar["hunks"] if h.get("classification") == "unclear"]
        guarded_t = [h for h in tangled if h["file"] in tier.guarded_paths]
        ev = [f"{h['id']} {h['file']}:{h['start']} ({h.get('reason', '')})" for h in tangled + unclear][:6]
        if guarded_t:
            areas.append(AreaResult(area="Scope", status=B, reason=f"{len(guarded_t)} unrequested change(s) in a "
                                    "guarded area", evidence=ev))
        elif tangled or unclear:
            areas.append(AreaResult(area="Scope", status=H, reason=f"{len(tangled)} tangled and {len(unclear)} "
                                    "unclear hunk(s) not traced to the requirement", evidence=ev))
        else:
            areas.append(AreaResult(area="Scope", status=V, reason="Every hunk traced to a requirement item or "
                                    "supports one"))
    else:
        not_checked.append("Requirement radar (" + ((radar or {}).get("note") or "not built") + ")")

    # SECURITY
    sec_block = [f for f in findings if f.dimension == Dimension.SAFETY and f.severity == Severity.BLOCKER]
    sec_fix = [f for f in findings if f.dimension == Dimension.SAFETY and f.severity == Severity.SHOULD_FIX]
    pkg = _sensor(sensors, "package_check")
    if sec_block:
        areas.append(AreaResult(area="Security", status=B, reason="Safety Blocker(s) found", evidence=_ids(sec_block)))
    elif sec_fix or (pkg and not pkg.ran):
        r = "Safety concerns to check" if sec_fix else "Added packages could not be verified"
        areas.append(AreaResult(area="Security", status=H, reason=r, evidence=_ids(sec_fix)))
    else:
        areas.append(AreaResult(area="Security", status=V, reason="No secrets, no unverified packages, "
                                "no safety findings"))

    # BUILD
    build = _sensor(sensors, "dotnet_build")
    if build and build.ran and build.passed is False:
        areas.append(AreaResult(area="Build", status=B, reason="Build failed", evidence=build.details[:5]))
    elif build and build.ran:
        areas.append(AreaResult(area="Build", status=V, reason="Build succeeded"))
    else:
        not_checked.append(f"Build ({build.summary if build else 'not run'})")

    # TESTS (passing tests are evidence, never proof on their own)
    test = _sensor(sensors, "dotnet_test")
    t_block = _by(findings, Dimension.TESTS, Severity.BLOCKER)
    t_fix = _by(findings, Dimension.TESTS, Severity.SHOULD_FIX)
    if test and test.ran and test.passed is False:
        areas.append(AreaResult(area="Tests", status=B, reason="Tests failed", evidence=test.details[:5]))
    elif t_block:
        areas.append(AreaResult(area="Tests", status=B, reason="Test-quality Blocker(s)", evidence=_ids(t_block)))
    elif t_fix:
        areas.append(AreaResult(area="Tests", status=H, reason="Test weakening or gaps to check",
                                evidence=_ids(t_fix)))
    elif not (test and test.ran):
        areas.append(AreaResult(area="Tests", status=H, reason="Tests were not run by the reviewer (use --test); "
                                "test quality was reviewed from code only"))
    else:
        areas.append(AreaResult(area="Tests", status=V, reason="Tests passed and no weakening found"))

    if not (test and test.ran):
        not_checked.append(f"Test run ({test.summary if test else 'not run'})")

    # CORRECTNESS / ARCHITECTURE / MAINTAINABILITY
    for dim, name in ((Dimension.CORRECTNESS, "Correctness"), (Dimension.ARCHITECTURE, "Architecture"),
                      (Dimension.MAINTAINABILITY, "Maintainability"), (Dimension.PERFORMANCE, "Performance")):
        bl, sf = _by(findings, dim, Severity.BLOCKER), _by(findings, dim, Severity.SHOULD_FIX)
        if dim not in outputs and not bl and not sf:
            areas.append(AreaResult(area=name, status=H, reason="Not reviewed (specialist failed or skipped)"))
        elif bl:
            areas.append(AreaResult(area=name, status=B, reason=f"{len(bl)} Blocker(s)", evidence=_ids(bl)))
        elif sf and dim == Dimension.CORRECTNESS:
            areas.append(AreaResult(area=name, status=H, reason=f"{len(sf)} concern(s) to check", evidence=_ids(sf)))
        else:
            extra = f"; {len(sf)} ShouldFix noted (does not hold the merge)" if sf else ""
            areas.append(AreaResult(area=name, status=V, reason=f"No blocking issue{extra}", evidence=_ids(sf)))

    # IMPACT (code-graph lite)
    untested = [im for im in ctx.impact if im.callers and not im.test_refs]
    wide = [im for im in ctx.impact if len(im.callers) >= 20]
    if untested or (wide and tier.tier == Tier.HIGH):
        ev = [f"{im.member}: {len(im.callers)} callers, no test references" for im in untested][:6] + \
             [f"{im.member}: {len(im.callers)} callers" for im in wide][:4]
        areas.append(AreaResult(area="Impact", status=H, reason="Changed members reach untested or many callers",
                                evidence=ev))
    else:
        areas.append(AreaResult(area="Impact", status=V,
                                reason=f"{len(ctx.impact)} changed member(s); callers covered by tests or none"))

    for fc in ctx.files:
        if fc.truncated:
            not_checked.append(f"Part of {fc.path} (context truncated)")

    statuses = [a.status for a in areas]
    if B in statuses:
        decision = "BLOCKED"
        reason = "Merge locked: " + "; ".join(f"{a.area}: {a.reason}" for a in areas if a.status == B)
    elif H in statuses:
        decision = "NEEDS_HUMAN"
        reason = "A named human must check: " + ", ".join(a.area for a in areas if a.status == H)
    else:
        decision = "READY_FOR_SIGNOFF"
        reason = "All areas verified with evidence. The named owner still signs; the AI never approves."
        if tier.tier == Tier.LOW and policy.gates.get("auto_pass_low_tier", False):
            reason += " Low tier: one-click owner confirmation is allowed by policy."
    if not policy.approved_by:
        reason += ". WARNING: review-policy.yaml is not approved by a named human yet."
    return areas, decision, reason, tier, not_checked
