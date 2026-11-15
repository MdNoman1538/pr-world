"""Write the review as JSON (machine) and Markdown (human)."""
from __future__ import annotations

import json
import os

from .models import AreaStatus, Review, Severity

ICON = {AreaStatus.VERIFIED: "VERIFIED", AreaStatus.HUMAN: "HUMAN CHECK", AreaStatus.BLOCKED: "BLOCKED",
        AreaStatus.NOT_CHECKED: "NOT CHECKED"}


def write_json(review: Review, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(review.model_dump_json(indent=2))


def _finding_md(f) -> str:
    loc = f"`{f.file}:{f.line_start}`" if f.file else ""
    ev_lines = "\n".join("  " + l.strip() for l in f.evidence.strip().splitlines())
    ev = f"\n\n  ```\n{ev_lines}\n  ```" if f.evidence else ""
    fix = f"\n\n  Suggested fix: {f.suggested_fix}" if f.suggested_fix else ""
    if f.patch:
        p = "\n".join("  " + l for l in f.patch.rstrip().splitlines())
        fix += f"\n\n  Ready-to-apply patch ({f.patch_explanation}):\n\n  ```diff\n{p}\n  ```"
    delta = f" · {f.delta}" if f.delta else ""
    req = f"\n\n  Requirement: {f.requirement_link}" if f.requirement_link and f.requirement_link != "none" else ""
    val = ""
    if f.validator and "q3_severity" in f.validator:
        val = f" · validator Q1-Q3: {f.validator.get('reason', '')}"
    conf = f" · confidence {f.confidence:.2f}" if f.source.startswith("specialist") else ""
    note = f" · {f.drop_reason}" if f.drop_reason and f.kept else ""
    return (f"- **[{f.severity.value}] {f.id} · {f.title}** ({f.dimension.value}, {f.source}{conf}{val}{note}{delta})"
            f" {loc}\n\n  {f.claim}{ev}{req}{fix}\n")


def write_markdown(r: Review, path: str) -> None:
    L = []
    L.append(f"# AI review · {r.head} → {r.base}")
    L.append("")
    L.append(f"**Decision: {r.decision}** · Tier **{r.tier.tier.value.upper()}** · "
             f"{r.tier.signoffs_required} sign-off(s) required · Requirement **{r.requirement_id}** · "
             f"Owner: **{r.owner}**")
    L.append("")
    if r.ai_error:
        L.append(f"> **AI REVIEW FAILED.** {r.ai_error}")
        L.append("")
    L.append(f"> {r.decision_reason}")
    L.append("")
    L.append("The AI review is advice with evidence. It is not an approval. A named human owns the decision.")
    L.append("")
    L.append("## What the change does (orientation)")
    L.append("")
    L.append(r.orientation or "(not available)")
    L.append("")
    L.append(f"Requirement alignment: **{r.requirement_alignment}**")
    if r.optimization_context:
        L.append("")
        L.append("Optimization context detected: research shows AI optimizations most often introduce "
                 "memory-safety flaws, so safety and performance were reviewed with extra care.")
    L.append("")
    if r.delta and r.delta.get("previous_run"):
        L.append("## Since the last review of this branch")
        L.append("")
        L.append(f"{r.delta['summary']} (previous run `{r.delta['previous_run']}`, decision "
                 f"{r.delta.get('previous_decision')}).")
        for x in r.delta.get("fixed", []):
            L.append(f"- Fixed: [{x['severity']}] {x['title']} ({x['file']})")
        for x in r.delta.get("still_open", []):
            L.append(f"- Still open: [{x['severity']}] {x['title']} (now {x['now_id']})")
        L.append("")
    if r.radar:
        L.append("## Requirement radar")
        L.append("")
        if r.radar.get("note"):
            L.append(r.radar["note"])
            L.append("")
        if r.radar.get("items"):
            L.append("| Item | Requirement | Status | Hunks | Why |")
            L.append("| --- | --- | --- | --- | --- |")
            for it in r.radar["items"]:
                L.append(f"| {it['id']} | {it['text']} | {it['status'].upper()} | {', '.join(it['hunk_ids']) or '-'} "
                         f"| {it['reason']} |")
            L.append("")
        L.append("| Hunk | File:lines | Classification | Items | Why |")
        L.append("| --- | --- | --- | --- | --- |")
        for h in r.radar.get("hunks", []):
            L.append(f"| {h['id']} | {h['file']}:{h['start']}-{h['end']} | {h.get('classification', '')} | "
                     f"{', '.join(h.get('item_ids', [])) or '-'} | {h.get('reason', '')} |")
        L.append("")
    if r.requirement_check and r.requirement_check.get("ran") and r.requirement_check.get("items"):
        rc = r.requirement_check
        c = rc["counts"]
        L.append("## Does the code do what the requirement says?")
        L.append("")
        L.append(f"Analyst (saw only the requirement) and interpreter (saw only the code) worked blind; a judge matched them. "
                 f"{c['met']} met · {c['partly']} partly · {c['missing']} missing · {c['contradicted']} contradicted · "
                 f"{c['no_evidence']} without grounded proof · {c['unclear']} unclear.")
        L.append("")
        L.append("| Item | Requirement | Result | Proof | Why |")
        L.append("| --- | --- | --- | --- | --- |")
        for it in rc["items"]:
            proof = "; ".join(f"{e['file']}:{e['line']}" + ("" if e.get("grounded") else " (not found)") for e in it.get("proof", [])) or "-"
            L.append(f"| {it['id']} | {it['text']} | {it['status'].replace('_', ' ')} | {proof} | {it.get('reason', '')} |")
        L.append("")
    if r.panel and r.panel.get("ran") and r.panel.get("votes"):
        L.append("## Second opinion on Critical findings (validator panel)")
        L.append("")
        for fid, v in r.panel["votes"].items():
            L.append(f"- {fid}: {v['real']} of {v['answered']} reviewers say real → {v['outcome']}")
        L.append("")
    if r.investigations and r.investigations.get("cases"):
        L.append("## Investigator")
        L.append("")
        for fid, c in r.investigations["cases"].items():
            L.append(f"- {fid}: {c['verdict']} after {len(c.get('steps', []))} step(s). {c.get('reason', '')}")
        L.append("")
    if r.not_checked_plugins:
        L.append("## Not checked (never counted as passed)")
        L.append("")
        for n in r.not_checked_plugins:
            L.append(f"- {n['plugin']} · {n['area']} · {n['reason']}")
        L.append("")
    if r.funnel:
        fu = r.funnel
        L.append(f"Noise funnel: {fu.get('proposed_by_specialists', 0)} proposed by specialists → "
                 f"{fu.get('evidence_verified', 0)} with verified evidence ({fu.get('dropped_hallucinated_evidence', 0)} "
                 f"hallucinated dropped) → {fu.get('dropped_by_validator', 0)} removed by validator → "
                 f"{fu.get('shown', 0)} shown (incl. {fu.get('sensor_findings', 0)} deterministic sensor findings); "
                 f"{fu.get('patches', 0)} ready-to-apply patch(es).")
        L.append("")
    L.append("## Every area")
    L.append("")
    L.append("| Area | Status | Reason |")
    L.append("| --- | --- | --- |")
    for a in r.areas:
        ev = ("<br>" + "<br>".join(a.evidence[:4])) if a.evidence else ""
        L.append(f"| {a.area} | {ICON[a.status]} | {a.reason}{ev} |")
    L.append("")
    blockers = [f for f in r.findings if f.severity == Severity.BLOCKER]
    others = [f for f in r.findings if f.severity != Severity.BLOCKER]
    L.append(f"## What the AI found ({len(r.findings)} shown, {len(r.dropped_findings)} filtered as noise)")
    L.append("")
    if not r.findings:
        L.append("No findings survived evidence checking and validation.")
    for f in blockers + others:
        L.append(_finding_md(f))
    L.append("## What the AI refused to decide, and why")
    L.append("")
    if not r.refusals:
        L.append("Nothing.")
    for x in r.refusals:
        L.append(f"- **{x.topic}** ({x.source}): {x.reason}")
    L.append("")
    L.append("## What was NOT checked")
    L.append("")
    for n in r.not_checked or ["Everything in scope was checked."]:
        L.append(f"- {n}")
    L.append("")
    L.append("## Deterministic sensors")
    L.append("")
    L.append("| Sensor | Ran | Result |")
    L.append("| --- | --- | --- |")
    for s in r.sensors:
        res = "n/a" if s.passed is None else ("pass" if s.passed else "FAIL")
        log = f" (log: `{s.log_file}`)" if s.log_file else ""
        L.append(f"| {s.name} | {'yes' if s.ran else 'no'} | {res}: {s.summary}{log} |")
    L.append("")
    L.append("## Risk tier reasons (rulebook)")
    L.append("")
    for x in r.tier.reasons:
        L.append(f"- {x}")
    L.append("")
    if r.dropped_findings:
        L.append("## Filtered out before you saw them (audit)")
        L.append("")
        L.append("| ID | Source | Title | Why it was filtered |")
        L.append("| --- | --- | --- | --- |")
        for f in r.dropped_findings:
            L.append(f"| {f.id} | {f.source} | {f.title} | {f.drop_reason} |")
        L.append("")
    if r.track_record:
        L.append("## Reviewer track record (from human feedback)")
        L.append("")
        L.append("| Dimension | Accepted | Rejected | Escapes | Precision | Trust |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for d, t in sorted(r.track_record.items()):
            L.append(f"| {d} | {t['accepted']} | {t['rejected']} | {t['escapes']} | {t['precision']} | {t['trust']} |")
        L.append("")
    L.append("## Sign-off (to be completed by the named owner)")
    L.append("")
    checked = ", ".join(a.area for a in r.areas if a.status == AreaStatus.VERIFIED) or "none"
    human = ", ".join(a.area for a in r.areas if a.status == AreaStatus.HUMAN) or "none"
    L.append(f"- Checked by AI and tools: {checked}")
    L.append(f"- Must be checked by a human: {human}")
    L.append(f"- Not checked: {'; '.join(r.not_checked) or 'none'}")
    L.append("- Residual risk I accept: ______________________________")
    L.append(f"- Signed: ______________________ (owner)" + ("   ______________________ (second signer)"
                                                            if r.tier.signoffs_required > 1 else ""))
    L.append("")
    L.append("---")
    L.append(f"Run `{r.run_id}` · {r.created_at} · policy {r.policy_version} "
             f"(approved by: {r.policy_approved_by or 'NOT APPROVED'}) · models: {r.models} · "
             f"changed files: {len(r.changed_files)}")
    if r.settings:
        L.append("")
        L.append(f"Settings: {r.settings.get('badge')}")
    if r.cost:
        L.append(f"Model calls: {r.cost.get('calls')} · cost {r.cost.get('cost_eur')} EUR (budget {r.cost.get('budget')})")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
