#!/usr/bin/env python3
"""G1 experiment: review the finished Nordbank PRs again under different reviewer set-ups and compare.

Variants (each one is a team settings file, so the run is reproducible):
  A  one model, no requirement check        (the reviewer before v5)
  B  one model, with the requirement check  (analyst, interpreter, judge)
  C  mixed models: B, plus the judge, validator and panel on a different model family
     (needs OPENAI_API_KEY or ANTHROPIC_API_KEY in ../ai-reviewer/.env; skipped and reported otherwise)

For each variant: planted defects caught (same location match as the scorecard), Critical findings on the clean PRs
(false alarms), what the requirement check said on planted vs clean PRs, decisions, model calls and cost.
Writes runs/experiment/<variant>/..., runs/experiment/report.md and viewer/data/experiment.json (admins / test tool).

  python agents/experiment.py                 # all variants, all finished PRs
  python agents/experiment.py --only PR-2,PR-3 --variants A,B
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BANK, PLAN, REVIEWER, RUNS, VIEW, load_env, say, sh, write_json  # noqa: E402

GEMINI_STRONG = os.environ.get("GEMINI_STRONG_MODEL", "gemini-4-hydrogen")
OPENAI_MODEL = os.environ.get("PRW_OPENAI_MODEL", "gpt-4.1")
ANTHROPIC_MODEL = os.environ.get("PRW_ANTHROPIC_MODEL", "claude-sonnet-5-5")
ROLES = ["specialist", "validator", "radar", "fixer", "investigator", "requirement_analyst", "change_interpreter", "requirement_judge", "writer"]


def one_model(model):
    m = {"provider": "gemini", "model": model}
    return {"default": m, "roles": {**{r: m for r in ROLES}, "panel": [m, m]}}


def variants():
    g = {"provider": "gemini", "model": GEMINI_STRONG}
    other = ({"provider": "openai", "model": OPENAI_MODEL} if os.environ.get("OPENAI_API_KEY") else
             {"provider": "anthropic", "model": ANTHROPIC_MODEL} if os.environ.get("ANTHROPIC_API_KEY") else None)
    base = {"version": "1", "preset": "balanced", "approved_by": "experiment runner (test tool)", "approved_on": time.strftime("%Y-%m-%d"),
            "budget": {"max_calls": 200, "max_cost_eur": 50}, "integrations": {"dry_run": True}}
    full = {"default": "full", "by_tier": {"high": "full", "medium": "full", "low": "full"}}
    out = {
        "A": ("One model, no requirement check", {**base, "models": one_model(GEMINI_STRONG),
                                                  "coverage": {**full, "default": "custom", "by_tier": {"high": "custom", "medium": "custom", "low": "custom"},
                                                               "custom": {"base": "full", "disable": ["requirement_check"]}}}, None),
        "B": ("One model, with the requirement check", {**base, "models": one_model(GEMINI_STRONG), "coverage": full}, None),
    }
    if other:
        mixed = one_model(GEMINI_STRONG)
        for r in ("validator", "requirement_judge"):
            mixed["roles"][r] = other
        mixed["roles"]["panel"] = [g, other]
        out["C"] = ("Mixed models: judge, validator and panel on " + other["provider"], {**base, "models": mixed, "coverage": full}, None)
    else:
        out["C"] = ("Mixed models", None, "skipped: no OPENAI_API_KEY or ANTHROPIC_API_KEY in ../ai-reviewer/.env")
    return out


def caught(bug, findings, world_head):
    """Same location match as the scorecard (simulate.py): a finding in the bug's file, near its lines or in its method."""
    if not bug.get("applied"):
        return []
    member = None
    if bug.get("lines"):
        l1, l2 = bug["lines"]
        cands = [n for n in world_head.get("nodes", []) if n.get("file") == bug["file"] and n["kind"] in ("method", "ctor", "property")
                 and (n.get("line") or 0) <= l2 and (n.get("end_line") or 0) >= l1]
        member = min(cands, key=lambda n: n["end_line"] - n["line"]) if cands else None
    hits = []
    for f in findings:
        if f.get("file") != bug.get("file"):
            continue
        fl1, fl2 = f.get("line_start") or 0, f.get("line_end") or f.get("line_start") or 0
        near = bug.get("lines") and fl1 <= bug["lines"][1] + 6 and fl2 >= bug["lines"][0] - 6
        inside = member and member["line"] <= fl1 <= member["end_line"]
        if near or inside:
            hits.append({"id": f["id"], "severity": f["severity"], "title": f["title"]})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma list of PRs")
    ap.add_argument("--variants", default="A,B,C")
    ap.add_argument("--mock", action="store_true", help="plumbing check without model calls (results mean nothing)")
    ap.add_argument("--report-only", action="store_true", help="only rebuild the report from earlier runs")
    a = ap.parse_args()
    load_env()
    state = json.loads((RUNS / "state.json").read_text())
    prs = [p for p in state["prs"] if not a.only or p in a.only.split(",")]
    bugs = {}
    for p in prs:
        k = RUNS / "_answer_key" / f"{p}.json"
        if k.exists():
            b = json.loads(k.read_text())
            if b.get("applied"):
                bugs[p] = b
    vs = variants()
    root = RUNS / "experiment"
    results = {}
    for v in a.variants.split(","):
        title, cfg, skip = vs[v]
        results[v] = {"title": title, "skipped": skip, "prs": {}}
        if skip:
            say(f"Variant {v}: {skip}")
            continue
        vdir = root / v
        vdir.mkdir(parents=True, exist_ok=True)
        cfg_p = vdir / "prworld.yaml"
        cfg_p.write_text(yaml.safe_dump(cfg, sort_keys=False))
        for p in prs:
            rec = state["prs"][p]
            out_p = vdir / f"{p}.json"
            if not a.report_only and not out_p.exists():
                say(f"Variant {v} · {p}: reviewing")
                issue = RUNS / p / "issue.md"
                runs = vdir / "runs"
                runs.mkdir(exist_ok=True)
                before = {x.name for x in runs.iterdir()}
                cmd = [sys.executable, str(REVIEWER / "backend" / "review.py"), "--memory", str(vdir / "memory.db"), "review",
                       "--repo", str(BANK), "--base", rec["base"], "--head", rec["head"],
                       "--req-id", p, "--owner", "experiment", "--policy", str(PLAN / "review-policy.yaml"), "--out", str(runs),
                       "--offline", "--workers", "3", "--config", str(cfg_p)]
                if issue.exists():
                    cmd += ["--req-file", str(issue)]
                if a.mock:
                    cmd.append("--mock")
                code, log = sh(cmd, cwd=REVIEWER, timeout=3600)
                new = sorted((x for x in runs.iterdir() if x.name not in before and (x / "review.json").exists()), key=lambda x: x.stat().st_mtime)
                if not new:
                    say(f"   no review produced (exit {code}); see {vdir / (p + '.log')}")
                    (vdir / f"{p}.log").write_text(log)
                    continue
                out_p.write_text((new[-1] / "review.json").read_text())
            if not out_p.exists():
                continue
            r = json.loads(out_p.read_text())
            wh_p = VIEW / "worlds" / f"{rec['head']}.json"
            wh = json.loads(wh_p.read_text()) if wh_p.exists() else {"nodes": []}
            hit = caught(bugs[p], r.get("findings", []), wh) if p in bugs else []
            rc = r.get("requirement_check") or {}
            results[v]["prs"][p] = {"planted": p in bugs, "caught": bool(hit), "hits": hit, "decision": r.get("decision"),
                                    "critical": sum(1 for f in r.get("findings", []) if f.get("severity") == "Blocker"),
                                    "findings": len(r.get("findings", [])),
                                    "requirement": rc.get("counts") if rc.get("ran") else None,
                                    "calls": (r.get("cost") or {}).get("calls"), "cost_eur": (r.get("cost") or {}).get("cost_eur"),
                                    "not_checked": [n["plugin"] for n in r.get("not_checked_plugins") or []]}
    # summary per variant
    for v, res in results.items():
        rows = res["prs"]
        planted = [x for x in rows.values() if x["planted"]]
        clean = [x for x in rows.values() if not x["planted"]]
        req_flag = lambda x: bool(x["requirement"] and (x["requirement"]["contradicted"] or x["requirement"]["missing"]))  # noqa: E731
        res["summary"] = {"prs": len(rows), "planted": len(planted), "caught": sum(x["caught"] for x in planted),
                          "clean": len(clean), "clean_with_critical": sum(1 for x in clean if x["critical"]),
                          "requirement_flags_on_planted": sum(1 for x in planted if req_flag(x)),
                          "requirement_flags_on_clean": sum(1 for x in clean if req_flag(x)),
                          "calls": sum(x["calls"] or 0 for x in rows.values()), "cost_eur": round(sum(x["cost_eur"] or 0 for x in rows.values()), 3)}
    out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "mock": a.mock, "variants": results,
           "note": ("Caught = a finding at the planted defect's location (same rule as the scorecard). Critical findings on clean PRs "
                    "are candidate false alarms: a human must judge each one. "
                    + ("MOCK RUN: plumbing only, the numbers mean nothing." if a.mock else ""))}
    write_json(VIEW / "experiment.json", out)
    L = ["# Reviewer experiment (G1)", "", out["note"], "", "| Variant | PRs | Planted caught | Critical on clean PRs | Requirement flags: planted / clean | Model calls | Cost EUR |",
         "|---|---|---|---|---|---|---|"]
    for v, res in results.items():
        if res["skipped"]:
            L.append(f"| {v}: {res['title']} | {res['skipped']} | | | | | |")
            continue
        s = res["summary"]
        L.append(f"| {v}: {res['title']} | {s['prs']} | {s['caught']} of {s['planted']} | {s['clean_with_critical']} of {s['clean']} | "
                 f"{s['requirement_flags_on_planted']} / {s['requirement_flags_on_clean']} | {s['calls']} | {s['cost_eur']} |")
    (root).mkdir(parents=True, exist_ok=True)
    (root / "report.md").write_text("\n".join(L) + "\n")
    say("Experiment report: runs/experiment/report.md · viewer/data/experiment.json")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
