"""Outside tools as sensors, and integrations that post the review.

Outside tools (SonarQube, Semgrep, CodeQL, ...) plug in through SARIF 2.1.0; mutation testing (Stryker.NET)
through its JSON report. Their results become findings in the normal evidence format, so the locked evidence
check applies to them exactly as to the built-in reviewers: a result whose code is not at the cited line in the
changed files is dropped.

Integrations post a short summary to GitHub, GitLab, Azure DevOps, Slack or Jira. With integrations.dry_run
(the default) nothing is sent: the exact payloads are written to the run folder for inspection.
"""
from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
from typing import Dict, List, Optional, Tuple

import requests

from .models import Dimension, Finding, SensorResult, Severity

SARIF_LEVEL = {"error": Severity.BLOCKER, "warning": Severity.SHOULD_FIX, "note": Severity.NIT, "none": Severity.NIT}


def _rel(uri: str, repo: str) -> str:
    u = uri.replace("file://", "")
    if os.path.isabs(u) and repo and u.startswith(os.path.abspath(repo)):
        u = os.path.relpath(u, repo)
    return u.lstrip("./")


def read_sarif(path: str, repo: str, head_text: Dict[str, List[str]], tool_id: str) -> Tuple[List[Finding], int]:
    data = json.load(open(path, encoding="utf-8"))
    out, skipped, k = [], 0, 0
    for run in data.get("runs", []):
        tool = (run.get("tool", {}).get("driver", {}) or {}).get("name", tool_id)
        for r in run.get("results", []):
            loc = ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
            f = _rel((loc.get("artifactLocation") or {}).get("uri", ""), repo)
            reg = loc.get("region") or {}
            ln = int(reg.get("startLine", 0) or 0)
            lines = head_text.get(f)
            if not lines or ln < 1 or ln > len(lines):
                skipped += 1           # not in the changed files: outside this PR
                continue
            k += 1
            sev = SARIF_LEVEL.get(r.get("level", "warning"), Severity.SHOULD_FIX)
            text = (r.get("message") or {}).get("text", "")
            dim = Dimension.SAFETY if any(w in (r.get("ruleId", "") + text).lower() for w in ("sec", "inject", "xss", "crypt", "auth")) else Dimension.CORRECTNESS
            out.append(Finding(id=f"X{k:02d}", dimension=dim, source=f"sensor:{tool_id}", title=f"{tool}: {r.get('ruleId', 'rule')}",
                               claim=text[:600], severity=sev, file=f, line_start=ln, line_end=int(reg.get("endLine", ln) or ln),
                               evidence=lines[ln - 1].strip(), confidence=0.9))
    return out, skipped


def read_stryker(path: str, repo: str, head_text: Dict[str, List[str]], tool_id: str) -> Tuple[List[Finding], Dict]:
    """Survived mutants on changed lines become Major findings; the mutation score is reported."""
    data = json.load(open(path, encoding="utf-8"))
    out, k, killed, total = [], 0, 0, 0
    for fname, fdata in (data.get("files") or {}).items():
        f = _rel(fname, repo)
        for m in fdata.get("mutants", []):
            status = m.get("status", "")
            if status in ("Killed", "Timeout"):
                killed += 1
            if status in ("Killed", "Timeout", "Survived", "NoCoverage"):
                total += 1
            if status not in ("Survived", "NoCoverage"):
                continue
            ln = int(((m.get("location") or {}).get("start") or {}).get("line", 0))
            lines = head_text.get(f)
            if not lines or ln < 1 or ln > len(lines):
                continue
            k += 1
            out.append(Finding(id=f"Y{k:02d}", dimension=Dimension.TESTS, source=f"sensor:{tool_id}",
                               title=f"Mutant {status.lower()}: {m.get('mutatorName', 'mutation')}",
                               claim=f"Changing this line ({m.get('replacement', '')}) was not caught by any test.",
                               severity=Severity.SHOULD_FIX, file=f, line_start=ln, line_end=ln, evidence=lines[ln - 1].strip(),
                               confidence=0.95))
    return out, {"mutation_score": round(killed / total, 3) if total else None, "mutants": total, "killed": killed}


def run_outside_tool(plugin, repo: str, head_text: Dict[str, List[str]], evidence_dir: str, timeout: int = 1200) -> Tuple[SensorResult, List[Finding]]:
    log = ""
    if plugin.command:
        try:
            p = subprocess.run(shlex.split(plugin.command), cwd=repo, capture_output=True, text=True, timeout=timeout)
            log = (p.stdout + p.stderr)[-20000:]
        except Exception as e:  # tool missing or timed out: reported as not run
            return SensorResult(name=plugin.id, ran=False, summary=f"{plugin.name} did not run: {e}"), []
    report = plugin.report if os.path.isabs(plugin.report or "") else os.path.join(repo, plugin.report or "")
    if not plugin.report or not os.path.exists(report):
        return SensorResult(name=plugin.id, ran=False, summary=f"{plugin.name}: report not found ({plugin.report})"), []
    try:
        if plugin.format == "stryker":
            fs, extra = read_stryker(report, repo, head_text, plugin.id)
            summary = f"{len(fs)} surviving mutant(s) on changed lines; mutation score {extra['mutation_score']}"
        else:
            fs, skipped = read_sarif(report, repo, head_text, plugin.id)
            summary = f"{len(fs)} result(s) on changed files ({skipped} elsewhere, not part of this PR)"
    except Exception as e:
        return SensorResult(name=plugin.id, ran=False, summary=f"{plugin.name}: could not read the report: {e}"), []
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        with open(os.path.join(evidence_dir, f"{plugin.id}.txt"), "w", encoding="utf-8") as fh:
            fh.write(summary + "\n\n" + log)
    return SensorResult(name=plugin.id, ran=True, passed=not any(f.severity == Severity.BLOCKER for f in fs), summary=summary,
                        log_file=f"evidence/{plugin.id}.txt"), fs


# ---------------------------------------------------------------------------------------------- integrations
LABEL = {"BLOCKED": "Fix before merge", "NEEDS_HUMAN": "Check needed", "READY_FOR_SIGNOFF": "Ready to sign"}


def summary_text(review) -> str:
    crit = [f for f in review.findings if f.severity == Severity.BLOCKER]
    major = [f for f in review.findings if f.severity == Severity.SHOULD_FIX]
    lines = [f"**PR World review: {LABEL.get(review.decision, review.decision)}** (risk tier {review.tier.tier.value})",
             f"{len(crit)} Critical, {len(major)} Major finding(s). The AI does not approve; a named human signs."]
    for f in crit[:5]:
        lines.append(f"- Critical: {f.title} ({f.file}:{f.line_start})")
    nc = sorted({n['area'] for n in review.not_checked_plugins})
    if nc:
        lines.append("Not checked: " + ", ".join(nc))
    if review.requirement_check and review.requirement_check.get("ran"):
        c = review.requirement_check["counts"]
        lines.append(f"Requirement: {c['met']} met, {c['partly']} partly, {c['missing']} missing, {c['contradicted']} contradicted")
    lines.append(f"Settings: {review.settings.get('badge', '')}")
    return "\n".join(lines)


def post_all(cfg, review, out_dir: str, pr_number: Optional[str] = None, issue_key: Optional[str] = None) -> List[Dict]:
    ints = cfg.get("integrations", default={}) or {}
    dry = bool(ints.get("dry_run", True))
    text = summary_text(review)
    done = []

    def send(name, method, url, headers, body):
        rec = {"integration": name, "url": url, "dry_run": dry}
        if dry:
            path = os.path.join(out_dir, f"integration-{name}.json")
            json.dump({"method": method, "url": url, "body": body}, open(path, "w"), indent=1)
            rec["payload_file"] = os.path.basename(path)
        else:
            try:
                r = requests.request(method, url, headers=headers, json=body, timeout=20)
                rec["status"] = r.status_code
            except Exception as e:
                rec["error"] = str(e)[:200]
        done.append(rec)

    def tok(env):
        return os.environ.get(env or "", "")

    if "github" in ints and pr_number:
        g = ints["github"]
        send("github", "POST", f"{g.get('api', 'https://api.github.com')}/repos/{g['repo']}/issues/{pr_number}/comments",
             {"Authorization": f"Bearer {tok(g.get('token_env', 'GITHUB_TOKEN'))}", "Accept": "application/vnd.github+json"}, {"body": text})
    if "gitlab" in ints and pr_number:
        g = ints["gitlab"]
        send("gitlab", "POST", f"{g.get('api', 'https://gitlab.com/api/v4')}/projects/{requests.utils.quote(g['project'], safe='')}/merge_requests/{pr_number}/notes",
             {"PRIVATE-TOKEN": tok(g.get("token_env", "GITLAB_TOKEN"))}, {"body": text})
    if "azure_devops" in ints and pr_number:
        a = ints["azure_devops"]
        auth = base64.b64encode(f":{tok(a.get('token_env', 'AZDO_TOKEN'))}".encode()).decode()
        send("azure_devops", "POST", f"{a['org_url'].rstrip('/')}/{a['project']}/_apis/git/repositories/{a['repo']}/pullRequests/{pr_number}/threads?api-version=7.1",
             {"Authorization": f"Basic {auth}"}, {"comments": [{"parentCommentId": 0, "content": text, "commentType": 1}], "status": 1})
    if "slack" in ints:
        url = tok(ints["slack"].get("webhook_env", "SLACK_WEBHOOK_URL"))
        if url or dry:
            send("slack", "POST", url or "<SLACK_WEBHOOK_URL>", {}, {"text": text})
    if "jira" in ints and issue_key:
        j = ints["jira"]
        auth = base64.b64encode(f"{tok(j.get('user_env', 'JIRA_USER'))}:{tok(j.get('token_env', 'JIRA_TOKEN'))}".encode()).decode()
        send("jira", "POST", f"{j['base_url'].rstrip('/')}/rest/api/3/issue/{issue_key}/comment", {"Authorization": f"Basic {auth}"},
             {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}})
    return done
