"""Orchestrator: runs the whole v2 pipeline for one PR and writes the outputs.

  Tier 1  rule engine (tier, optimization trap) → deterministic sensors (+ evidence logs)
  Tier 2  context engine: AST slices, impact (code graph lite), familiarity (history + memory)
  Tier 3  6 specialists in parallel (fast model)
  Tier 4  evidence check (code) → validator Q1 nitpick / Q2 hallucination / Q3 severity (strong model)
          → requirement radar (strong model) → fix agent patches (strong model)
  Gate    areas → BLOCKED / NEEDS_HUMAN / READY_FOR_SIGNOFF, iteration delta, memory, reports, graph.json
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from . import sensors as sensor_mod
from .context import build_context
from .delta import compute_delta
from .fixer import suggest_fixes
from .gate import evaluate, overall_alignment
from .git_tools import load_pr, recent_commits, rev_sha
from .api import write_bundle
from .api_impact import build_api_impact
from .graph import build_graph
from .llm import make_client
from .agents_v3 import investigate, requirement_check, validator_panel
from .models import AreaResult, AreaStatus, Finding, Severity
from .outside import post_all, run_outside_tool
from .platform_config import PlatformConfig, load_config
from .plugins import SENSOR_IDS, Registry
from .providers import RoutedClient
from .prompts import specialist_system
from .memory import Memory
from .models import Dimension, Refusal, Review, Tier
from .policy import decide_tier, load_plan, load_policy, optimization_context, raise_one
from .radar import build_radar
from .report import write_json, write_markdown
from .specialists import run_specialists
from .validator import check_evidence, run_validator


@dataclass
class Options:
    repo: str
    base: str
    head: str
    requirement_id: str = "UNSPECIFIED"
    requirement_file: Optional[str] = None
    issue: Optional[str] = None                 # owner/repo#123 → fetched from GitHub
    owner: str = "UNASSIGNED"
    plan: Optional[str] = None
    policy: str = "review-policy.yaml"
    strategy: str = "leftflow"
    dimensions: List[str] = field(default_factory=lambda: [d.value for d in Dimension])
    build: bool = False
    test: bool = False
    build_target: Optional[str] = None
    test_target: Optional[str] = None
    test_filter: Optional[str] = None
    timeout: int = 1800
    offline: bool = False
    mock: Optional[str] = None                 # None = real Gemini; "" = mock defaults; path = fixture
    fast_model: str = os.environ.get("GEMINI_FAST_MODEL", "gemini-3.8-flash")
    strong_model: str = os.environ.get("GEMINI_STRONG_MODEL", "gemini-4-hydrogen")
    temperature: float = 0.1
    out_dir: str = "runs"
    memory_path: str = ".reviewer/memory.db"
    max_context_chars: int = 120_000
    workers: int = 6
    radar: bool = True
    fixes: bool = True
    verbose: bool = True
    config: Optional[str] = None             # prworld.yaml (team policy); None = Full coverage everywhere
    pr_number: Optional[str] = None          # for integrations (GitHub/GitLab/Azure DevOps)
    issue_key: Optional[str] = None          # for the Jira integration


def _log(opts: Options, msg: str) -> None:
    if opts.verbose:
        print(f"[reviewer] {msg}", flush=True)


def fetch_issue(issue: str, timeout: float = 10.0) -> str:
    m = re.match(r"^([\w.-]+)/([\w.-]+)#(\d+)$", issue.strip())
    if not m:
        raise ValueError("--issue must look like owner/repo#123")
    url = f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/issues/{m.group(3)}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ai-reviewer"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return f"# {data.get('title', '')}\n\nSource: {data.get('html_url', url)}\n\n{data.get('body') or ''}"


def _anchor(lines: List[str], start: int, end: int, changed: set, pad: int = 3) -> List[List]:
    if not lines or start < 1:
        return []
    a, b = max(1, min(start, end) - pad), min(len(lines), max(start, end) + pad)
    return [[n, lines[n - 1], n in changed] for n in range(a, b + 1)]


def run_review(opts: Options) -> Review:
    t0 = time.time()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"[^\w.-]", "_", opts.head)[-40:]
    base_id, n = run_id, 1
    while os.path.exists(os.path.join(opts.out_dir, run_id)):   # two runs in the same second
        n += 1
        run_id = f"{base_id}-{n}"
    out = os.path.join(opts.out_dir, run_id)
    os.makedirs(out, exist_ok=True)
    log_path = os.path.join(out, "llm_log.jsonl")

    # ---------------------------------------------------------------- requirement
    req_text = ""
    if opts.requirement_file:
        with open(opts.requirement_file, encoding="utf-8") as fh:
            req_text = fh.read()
    elif opts.issue:
        _log(opts, f"fetching requirement from GitHub issue {opts.issue}")
        try:
            req_text = fetch_issue(opts.issue)
        except Exception as e:
            _log(opts, f"could not fetch issue ({e}); continuing without requirement text")
    if req_text:
        with open(os.path.join(out, "requirement.md"), "w", encoding="utf-8") as fh:
            fh.write(req_text)

    # ---------------------------------------------------------------- tier 1
    policy = load_policy(opts.policy)
    plan = load_plan(opts.plan)
    _log(opts, f"loading PR {opts.base}...{opts.head} from {opts.repo}")
    pr = load_pr(opts.repo, opts.base, opts.head)
    head_sha = rev_sha(opts.repo, opts.head)
    _log(opts, f"{len(pr.files)} changed file(s), {len(pr.commit_messages)} commit(s), head {head_sha[:10]}")

    tier = decide_tier(pr, policy, plan)
    optimization = optimization_context(policy, req_text, "\n".join(pr.commit_messages))
    if optimization and policy.change_rules.get("optimization_raises_tier", True) and tier.tier != Tier.HIGH:
        new_tier = raise_one(tier.tier)
        tier = tier.model_copy(update={
            "tier": new_tier, "signoffs_required": int(policy.gates.get(f"{new_tier.value}_signoffs", 1)),
            "reasons": tier.reasons + ["Optimization context (research: optimization trap) → one tier up"]})
    elif optimization:
        tier.reasons.append("Optimization context detected (research: optimization trap)")
    _log(opts, f"rulebook tier: {tier.tier.value} ({tier.signoffs_required} sign-off(s))"
               + (" · optimization trap" if optimization else ""))

    # ---------------------------------------------------------------- platform settings and plugins
    if opts.config:
        cfg = load_config(opts.config)
    else:   # no team settings file: legacy behaviour = everything on, the models given on the command line
        fast, strong = {"provider": "gemini", "model": opts.fast_model}, {"provider": "gemini", "model": opts.strong_model}
        cfg = load_config(overrides={
            "preset": "balanced",
            "coverage": {"default": "full", "by_tier": {"high": "full", "medium": "full", "low": "full"}},
            "models": {"default": fast, "roles": {
                "specialist": fast, "change_interpreter": fast, "writer": fast,
                "validator": strong, "radar": strong, "fixer": strong, "investigator": strong,
                "requirement_analyst": strong, "requirement_judge": strong, "panel": [strong, fast]}},
            "budget": {"max_calls": 200}})
    for w in cfg.warnings:
        _log(opts, f"settings: {w}")
    registry = Registry(cfg, base_dir=os.path.dirname(os.path.abspath(opts.config)) if opts.config else ".")
    for p in registry.problems:
        _log(opts, f"plugins: {p}")
    coverage, file_plugins, local_only_areas = {}, {}, set(cfg.get("local_only", default=[]) or [])
    touches_local_only = False
    for f in pr.files:
        a = policy.area_for(f.path) or {}
        name = a.get("name") or "(no area)"
        t = a.get("tier") or policy.raw.get("default_tier", "medium")
        if name not in coverage:
            r = registry.resolve(name, t)
            coverage[name] = {"tier": t, "level": r["level"], "on": sorted(r["on"]), "off": r["off"], "files": []}
        coverage[name]["files"].append(f.path)
        file_plugins[f.path] = set(coverage[name]["on"])
        if name in local_only_areas:
            touches_local_only = True
    def on_anywhere(pid):
        return any(pid in s for s in file_plugins.values())
    def files_for(pid):
        return [p for p, s in file_plugins.items() if pid in s]
    plugins_run: List[str] = []
    _log(opts, "coverage: " + "; ".join(f"{k} → {v['level']}" for k, v in coverage.items())
         + (" · local-only area touched: code stays on this machine" if touches_local_only else ""))

    # Tier 1 sensors and Tier 2 context engine are independent: run them in parallel
    _log(opts, f"parallel: deterministic sensors | context ({opts.strategy} slices) → API impact")
    def _sensors():
        return sensor_mod.run_all(
            pr, policy, offline=opts.offline, build=opts.build, test=opts.test, target=opts.build_target,
            test_target=opts.test_target, test_filter=opts.test_filter, timeout=opts.timeout,
            evidence_dir=os.path.join(out, "evidence"))

    def _context_and_api():
        c = build_context(pr, policy, strategy=opts.strategy)
        return c, build_api_impact(pr, policy, c)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_sensors, f_ctx = pool.submit(_sensors), pool.submit(_context_and_api)
        sensor_results, sensor_findings = f_sensors.result()
        ctx, api = f_ctx.result()
    kept_results, kept_sensor_findings = [], []
    for sres in sensor_results:
        pid = SENSOR_IDS.get(sres.name)
        if pid and not on_anywhere(pid) and sres.ran:
            sres = sres.model_copy(update={"ran": False, "summary": f"Switched off by the coverage level ({pid})"})
        kept_results.append(sres)
        if sres.ran or not pid:
            plugins_run.append(pid) if pid and pid not in plugins_run else None
    sensor_findings = [f for f in sensor_findings if on_anywhere(SENSOR_IDS.get(f.source.replace("sensor:", ""), "sensor.secrets"))
                       or not f.source.startswith("sensor:")]
    sensor_results = kept_results
    for cp in [p for p in registry.company if p.kind == "sensor" and on_anywhere(p.id)]:
        sres, sfs = run_outside_tool(cp, opts.repo, ctx.head_text, os.path.join(out, "evidence"))
        sensor_results.append(sres)
        sensor_findings.extend(sfs)
        if sres.ran:
            plugins_run.append(cp.id)
    ctx_text = ctx.render(opts.max_context_chars)
    with open(os.path.join(out, "context.txt"), "w", encoding="utf-8") as fh:
        fh.write(ctx_text + "\n\n# IMPACT\n" + ctx.render_impact())
    api_lines = []
    for a in api["apis"][:20]:
        api_lines.append(f"- {a['visibility']} {a['kind']} {a['name']} ({a['file']}): {a['change'].upper()}"
                         + (" BREAKING" if a["breaking"] else "")
                         + (f"; before: `{a['sig_before']}` after: `{a['sig_after']}`" if a["change"] == "signature" else "")
                         + f"; {len(a['callers'])} direct caller(s) in {', '.join(a['caller_areas']) or 'no area'}"
                         + f"; {len(a['untested_callers'])} caller(s) not reached by any test; {len(a['tests'])} test(s)")
    api_text = "\n".join(api_lines) or "No changed C# APIs detected."

    memory = Memory(opts.memory_path)
    familiarity = {}
    for f in pr.files:
        familiarity[f.path] = {"recent_commits": recent_commits(opts.repo, pr.merge_base, f.path, 5),
                               "past_findings": memory.past_findings_for(f.path, 5)}
    fam_text = "\n".join(
        f"- {p}: history: " + ("; ".join(d["recent_commits"][:3]) or "new file")
        + (" | past review findings: " + "; ".join(d["past_findings"]) if d["past_findings"] else "")
        for p, d in familiarity.items())

    client = RoutedClient(cfg, log_path, mock=opts.mock, local_only_active=touches_local_only)
    models = {r: ("mock" if opts.mock is not None else f"{m['provider']}/{m['model']}")
              for r, m in [(k, cfg.model_for(k)) for k in ["specialist", "validator", "radar", "fixer", "investigator",
                                                          "requirement_analyst", "change_interpreter", "requirement_judge"]]}
    models["panel"] = "mock" if opts.mock is not None else [f"{m['provider']}/{m['model']}" for m in cfg.panel_models()]
    models["parser"] = ctx.parser
    models["specialists"] = models["specialist"]

    area_notes = []
    for f in pr.files:
        a = policy.area_for(f.path)
        area_notes.append(f"- {f.path} [{f.status}, +{f.n_added}/-{f.n_removed}]: "
                          + (f"area '{a.get('name')}' ({a.get('tier')}): {a.get('why', '')}" if a else "no area"))
    sensor_text = "\n".join(f"- {s.name}: {'ran' if s.ran else 'NOT RUN'}; {s.summary}" for s in sensor_results)
    sensor_text += "\n" + "\n".join(f"  - {f.id} {f.title} at {f.file}:{f.line_start}" for f in sensor_findings)
    dims = [Dimension(d) for d in opts.dimensions if on_anywhere(f"specialist.{d}")]
    prompt_inputs = dict(
        requirement_id=opts.requirement_id, requirement_text=req_text,
        commit_messages="\n---\n".join(pr.commit_messages)[:6000],
        tier_text=f"Tier {tier.tier.value.upper()}; sign-offs {tier.signoffs_required}; reasons:\n"
                  + "\n".join(f"- {r}" for r in tier.reasons[:15]),
        area_notes="\n".join(area_notes)[:6000], sensor_text=sensor_text[:6000],
        impact_text=("API changes (code facts):\n" + api_text + "\n\nCallers and test references:\n"
                     + ctx.render_impact())[:8000], memory_notes=memory.rejected_notes(), context_text=ctx_text,
        familiarity_text=fam_text[:4000])

    # ---------------------------------------------------------------- tier 3
    _log(opts, f"parallel: {len(dims)} specialist(s) on {models['specialists']}"
               + (f" | requirement radar on {models['radar']}" if opts.radar else ""))
    radar_pool = ThreadPoolExecutor(max_workers=1)
    radar_future = radar_pool.submit(build_radar, client, opts.strong_model, pr, req_text) if (opts.radar and on_anywhere("radar")) else None
    req_pool = ThreadPoolExecutor(max_workers=1)
    req_future = req_pool.submit(requirement_check, client, req_text, ctx, ctx_text) if on_anywhere("requirement_check") else None
    outputs, llm_findings, refusals, errors = run_specialists(client, opts.fast_model, dims, prompt_inputs,
                                                               max_workers=max(1, opts.workers),
                                                               optimization=optimization)
    for e in errors:
        _log(opts, f"specialist error: {e}")
    plugins_run += [f"specialist.{d.value}" for d in outputs]
    # company specialists: their own checklist, the same evidence format and the same checks after them
    for cp in [p for p in registry.company if p.kind == "specialist" and on_anywhere(p.id)]:
        dim = Dimension.SAFETY if cp.area.lower() in ("security", "safety") else Dimension.CORRECTNESS
        try:
            from .models import SpecialistOutput
            from .prompts import specialist_prompt
            co = client.generate(role=f"specialist:{cp.id}", system=specialist_system(dim, optimization) +
                                 "\n\nCOMPANY CHECKLIST (" + cp.name + "):\n" + cp.prompt, prompt=specialist_prompt(**prompt_inputs),
                                 schema=SpecialistOutput)
            for i, lf in enumerate(co.findings, start=1):
                llm_findings.append(Finding(id=f"K{len(plugins_run)}{i:02d}", dimension=dim, source=f"specialist:{cp.id}", **lf.model_dump()))
            plugins_run.append(cp.id)
        except Exception as e:
            errors.append(f"{cp.id}: {e}")
    ai_error = ""
    if dims and not outputs:
        first = errors[0] if errors else "unknown error"
        hint = re.search(r"use (models/)?([\w.\-]+) for", first)
        ai_error = ("All specialist model calls failed, so NO AI review was performed (only code checks ran). "
                    f"First error: {first[:400]}"
                    + (f" | Hint: the API suggests the model '{hint.group(2)}'; set GEMINI_FAST_MODEL / "
                       "GEMINI_STRONG_MODEL in .env (see: python review.py models)." if hint else ""))
        _log(opts, "!" * 70)
        _log(opts, "AI REVIEW FAILED: " + ai_error)
        _log(opts, "!" * 70)

    # ---------------------------------------------------------------- tier 4
    proposed = len(llm_findings)
    _log(opts, f"evidence check on {proposed} proposed finding(s)")
    verified, dropped_ev = check_evidence(sensor_findings + llm_findings, ctx)
    n_verified = sum(1 for f in verified if f.source.startswith("specialist"))
    _log(opts, f"validator Q1-Q3 ({models['validator']}) on {n_verified} grounded LLM finding(s)")
    gates = dict(policy.gates)
    gates["min_blocker_confidence"] = cfg.get("thresholds", "min_blocker_confidence", default=gates.get("min_blocker_confidence", 0.6))
    gates["show_nits"] = cfg.get("thresholds", "show_nits", default=gates.get("show_nits", False))
    if on_anywhere("validator"):
        final, dropped_val, verr = run_validator(client, opts.strong_model, verified, ctx_text, req_text, gates)
        if not verr:
            plugins_run.append("validator")
    else:
        final, dropped_val, verr = verified, [], []
        refusals.append(Refusal(source="validator", topic="Noise filtering", reason="The validator is off at this coverage level; findings are shown unvalidated."))
    for e in verr:
        _log(opts, e)
        refusals.append(Refusal(source="validator", topic="Noise filtering",
                                reason="Validator call failed; findings are shown unvalidated."))

    radar = radar_future.result() if radar_future else None
    radar_pool.shutdown()
    if radar and radar.get("ran"):
        plugins_run.append("radar")
    req_check = None
    if req_future:
        try:
            req_check = req_future.result()
            if req_check.get("ran"):
                plugins_run.append("requirement_check")
        except Exception as e:
            req_check = {"ran": False, "reason": f"requirement check failed: {str(e)[:300]}"}
            _log(opts, req_check["reason"])
    req_pool.shutdown()

    panel = None
    if on_anywhere("validator_panel") and final:
        size = int(cfg.get("thresholds", "panel_size", default=2))
        _log(opts, f"validator panel ({size} models) on Critical findings")
        try:
            panel = validator_panel(client, final, ctx_text, size)
            if panel.get("ran"):
                plugins_run.append("validator_panel")
        except Exception as e:
            panel = {"ran": False, "error": str(e)[:300]}
    investigations = None
    if on_anywhere("investigator") and any(f.severity == Severity.BLOCKER for f in final):
        steps = int(cfg.get("thresholds", "investigator_max_steps", default=6))
        _log(opts, f"investigator on Critical findings (max {steps} steps each)")
        def _run_test(filt):
            rs = sensor_mod.dotnet_build_and_test(pr, True, True, opts.build_target, opts.test_target, filt, opts.timeout, None)
            return "\n".join(f"{r.name}: {'passed' if r.passed else 'FAILED' if r.ran else 'not run'} - {r.summary}\n" + "\n".join(r.details[:20]) for r in rs)
        try:
            investigations = investigate(client, final, ctx, opts.repo, opts.head, steps, allow_test=opts.test, run_test=_run_test)
            plugins_run.append("investigator")
        except Exception as e:
            investigations = {"ran": False, "error": str(e)[:300]}
    if radar and radar.get("note"):
        _log(opts, radar["note"])

    fix_stats = {}
    if opts.fixes and final and on_anywhere("fixer"):
        _log(opts, f"fix agent ({models['fixer']})")
        fix_stats = suggest_fixes(client, opts.strong_model, final, ctx, ctx_text, out)
        _log(opts, f"patches: {fix_stats.get('applied', 0)} ready, {fix_stats.get('rejected', 0)} discarded")

    changed_lines = {f.path: set(f.added_line_numbers) for f in pr.files}
    norm = lambda s: re.sub(r"\s+", "", s or "")
    for f in final + dropped_ev + dropped_val:
        lines = ctx.head_text.get(f.file, [])
        anchor = _anchor(lines, f.line_start, f.line_end, changed_lines.get(f.file, set()))
        ev = norm(f.evidence)
        in_head = bool(ev) and ev in norm("".join(t for _, t, _ in anchor))
        in_removed = bool(ev) and ev in norm(ctx.removed_text.get(f.file, ""))
        # evidence quoting removed code: show the quote, not unrelated new lines
        f.anchor = [] if (in_removed and not in_head) else anchor

    for s in sensor_results:
        if not s.ran:
            refusals.append(Refusal(source=f"sensor:{s.name}", topic=s.name, reason=s.summary))

    areas, decision, decision_reason, tier, not_checked = evaluate(
        tier=tier, policy=policy, sensors=sensor_results, findings=final, outputs=outputs, ctx=ctx,
        requirement_present=bool(req_text.strip()), plan_given=plan is not None, radar=radar)
    # ---------------------------------------------------------------- not checked (locked rule: never shown as passed)
    if fix_stats:
        plugins_run.append("fixer")
    not_checked_plugins = []
    for area_name, c in coverage.items():
        for pid, why in c["off"].items():
            if pid.startswith(("lens.", "provider.", "integration.")):
                continue
            not_checked_plugins.append({"plugin": pid, "area": area_name, "reason": why})
    for e in errors:
        m = re.match(r"(specialist:[\w.]+)", e)
        not_checked_plugins.append({"plugin": (m.group(1).replace(":", ".") if m else "specialist"), "area": "(all touched)",
                                    "reason": ("budget reached" if "budget" in e or "cost cap" in e else
                                               "local-only area: code was not sent to an outside model" if "local-only" in e else
                                               "the model call failed") + f": {e[:160]}"})
    for role in client.refused:
        not_checked_plugins.append({"plugin": role, "area": "(all touched)", "reason": "budget reached: not run"})
    SPEC_AREA = {"correctness": "Correctness", "architecture": "Architecture", "maintainability": "Maintainability",
                 "performance": "Performance", "safety": "Security", "tests": "Tests"}
    for d, area_label in SPEC_AREA.items():
        pid = f"specialist.{d}"
        if on_anywhere(pid):
            continue
        for ar in areas:
            if ar.area == area_label and ar.status in (AreaStatus.VERIFIED, AreaStatus.HUMAN) and not any(
                    f.dimension.value == d for f in final):
                ar.status = AreaStatus.NOT_CHECKED
                ar.reason = f"Not checked: the {d} reviewer is off at this coverage level" + (
                    " (code sensors still ran)" if d in ("safety", "tests") else "")
    if req_check and req_check.get("ran") and not req_check.get("items"):
        areas.append(AreaResult(area="Requirement", status=AreaStatus.HUMAN,
                                reason="No checkable requirement items were found. A named human must read the requirement."))
    elif req_check and req_check.get("ran"):
        c = req_check["counts"]
        if c["contradicted"]:
            areas.append(AreaResult(area="Requirement", status=AreaStatus.BLOCKED, reason=f"{c['contradicted']} requirement item(s) contradicted by the code",
                                    evidence=[f"{i['id']}: {i['text']}" for i in req_check["items"] if i["status"] == "contradicted"][:6]))
        elif c["missing"] or c["partly"] or c["no_evidence"]:
            areas.append(AreaResult(area="Requirement", status=AreaStatus.HUMAN,
                                    reason=f"{c['missing']} missing, {c['partly']} partly met, {c['no_evidence']} without grounded proof",
                                    evidence=[f"{i['id']}: {i['text']} ({i['status']})" for i in req_check["items"] if i["status"] != "met"][:6]))
        else:
            areas.append(AreaResult(area="Requirement", status=AreaStatus.VERIFIED, reason=f"All {req_check['met']} checkable item(s) met, each with code proof"))
    elif req_check and not req_check.get("ran"):
        areas.append(AreaResult(area="Requirement", status=AreaStatus.NOT_CHECKED,
                                reason="Not checked: " + str(req_check.get("reason") or req_check.get("error") or "the requirement check did not run")))
        not_checked_plugins.append({"plugin": "requirement_check", "area": "(all touched)", "reason": str(req_check.get("reason") or "did not run")})
    elif not on_anywhere("requirement_check"):
        areas.append(AreaResult(area="Requirement", status=AreaStatus.NOT_CHECKED, reason="Not checked: the requirement check is off at this coverage level"))
    statuses = [a.status for a in areas]
    if AreaStatus.BLOCKED in statuses:
        decision = "BLOCKED"
        decision_reason = "Merge locked: " + "; ".join(f"{a.area}: {a.reason}" for a in areas if a.status == AreaStatus.BLOCKED)
    elif AreaStatus.HUMAN in statuses:
        decision = "NEEDS_HUMAN"
        decision_reason = "A named human must check: " + ", ".join(a.area for a in areas if a.status == AreaStatus.HUMAN)
    else:
        decision = "READY_FOR_SIGNOFF"
        decision_reason = "All checked areas verified with evidence. The named owner still signs; the AI never approves."
    nc_areas = [a.area for a in areas if a.status == AreaStatus.NOT_CHECKED]
    if nc_areas:
        decision_reason += " Not checked: " + ", ".join(nc_areas) + "."
    if not policy.approved_by:
        decision_reason += " WARNING: review-policy.yaml is not approved by a named human yet."
    align, _ = overall_alignment(outputs)
    orientation = (outputs[Dimension.CORRECTNESS].orientation if Dimension.CORRECTNESS in outputs
                   else next((o.orientation for o in outputs.values()), ""))

    funnel = {"proposed_by_specialists": proposed,
              "evidence_verified": n_verified,
              "dropped_hallucinated_evidence": len(dropped_ev),
              "dropped_by_validator": sum(1 for f in dropped_val if f.source.startswith("specialist")),
              "sensor_findings": len(sensor_findings),
              "shown": len(final),
              "patches": fix_stats.get("applied", 0)}

    review = Review(
        run_id=run_id, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), repo=opts.repo,
        base=opts.base, head=opts.head, requirement_id=opts.requirement_id,
        requirement_text_present=bool(req_text.strip()), owner=opts.owner, policy_version=policy.version,
        policy_approved_by=policy.approved_by, models=models, changed_files=pr.changed_paths, tier=tier,
        orientation=orientation, requirement_alignment=align, sensors=sensor_results, findings=final,
        dropped_findings=dropped_ev + dropped_val, refusals=refusals, areas=areas, decision=decision,
        decision_reason=decision_reason, not_checked=not_checked, head_sha=head_sha, radar=radar, funnel=funnel,
        familiarity=familiarity, optimization_context=optimization, commit_messages=pr.commit_messages,
        ai_error=ai_error,
        settings={"fingerprint": cfg.fingerprint, "badge": cfg.badge(sorted(set(plugins_run)), len(registry.company)),
                  "preset": cfg.preset, "warnings": cfg.warnings + registry.problems, "approved_by": cfg.get("approved_by"),
                  "file": opts.config},
        coverage={k: {**v, "on": v["on"], "estimate_calls": registry.estimate_calls(set(v["on"]))} for k, v in coverage.items()},
        plugins_run=sorted(set(p for p in plugins_run if p)), not_checked_plugins=not_checked_plugins,
        requirement_check=req_check, panel=panel, investigations=investigations, cost=client.summary())
    if ai_error:
        review.decision_reason = "AI REVIEW DID NOT RUN — code checks only. " + review.decision_reason
    review.delta = compute_delta(memory, opts.repo, opts.base, opts.head, run_id, head_sha, final)
    memory.save_review(review)
    review.track_record = memory.track_record()

    graph = build_graph(pr, policy, ctx, final)
    graph["api"] = api
    with open(os.path.join(out, "graph.json"), "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=1)
    try:
        review.integrations = post_all(cfg, review, out, opts.pr_number, opts.issue_key)
    except Exception as e:
        review.integrations = [{"error": str(e)[:300]}]
    write_json(review, os.path.join(out, "review.json"))
    write_markdown(review, os.path.join(out, "review.md"))
    write_bundle(out, memory)          # data contract for the frontend (read-only copy)
    usage = getattr(client, "usage", {})
    _log(opts, f"done in {time.time() - t0:.1f}s · {getattr(client, 'calls', 0)} LLM call(s) · tokens {usage}")
    _log(opts, f"DECISION: {decision}")
    _log(opts, f"report: {os.path.join(out, 'review.md')}")
    _log(opts, f"data for the dashboard: {os.path.join(out, 'bundle.json')}  (API: python review.py api)")
    return review
