"""Plug-and-play: every reviewer part is a plugin with a manifest; coverage levels pick which ones run, per area.

A plugin manifest says what the plugin checks, what it needs, what it costs and what you lose without it.
The locked core is not a plugin and is always on: evidence check, gate and label rules, trust level, audit list,
access control and the world map.

Contract (enforced by the core, not by the plugin):
- a plugin's findings must use the evidence format (file, line, quoted code); the evidence check drops the rest
- a plugin that did not run is reported as NOT CHECKED for the areas it covers, never as passed
- in regulated mode (allow_unsigned: false) only built-in plugins and company plugins with a valid signature load
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import yaml

from .platform_config import REQUIRED_IN_FULL, PlatformConfig

KINDS = ["specialist", "agent", "sensor", "lens", "provider", "integration"]


@dataclass
class Plugin:
    id: str
    kind: str
    name: str
    checks: str
    area: str                       # gate area it covers (Correctness, Security, Tests, What, Build, ...)
    cost_calls: float = 0.0         # model calls per PR (estimate)
    needs: List[str] = field(default_factory=list)
    loses: str = ""                 # what you lose when it is off
    version: str = "1.0"
    source: str = "built-in"        # built-in | company | outside
    signed: bool = True
    levels: List[str] = field(default_factory=list)   # coverage levels that include it
    prompt: str = ""                # company specialists: their checklist / instructions
    command: str = ""               # outside tools: command that writes SARIF/Stryker JSON
    report: str = ""                # outside tools: path of the report file
    format: str = ""                # sarif | stryker

    def manifest(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if k not in ("prompt",)}


E, F = "essential", "full"
BUILTIN: List[Plugin] = [
    Plugin("specialist.correctness", "specialist", "Correctness reviewer", "Logic errors, wrong results, broken contracts",
           "Correctness", 1, ["code"], "Logic bugs are only caught by tests", levels=[E, F]),
    Plugin("specialist.safety", "specialist", "Security reviewer (OWASP)", "OWASP Top 10, access checks, data exposure",
           "Security", 1, ["code"], "Security weaknesses are only caught by sensors", levels=[E, F]),
    Plugin("specialist.tests", "specialist", "Test reviewer", "Missing or weak tests for the change",
           "Tests", 1, ["code"], "Gaps in the tests go unnoticed", levels=[F]),
    Plugin("specialist.architecture", "specialist", "Architecture reviewer", "Module boundaries, layering, coupling",
           "Architecture", 1, ["code"], "Boundary breaks between modules go unnoticed", levels=[F]),
    Plugin("specialist.maintainability", "specialist", "Maintainability reviewer", "Readability, duplication, naming",
           "Maintainability", 1, ["code"], "Hard-to-maintain code goes unnoticed", levels=[F]),
    Plugin("specialist.performance", "specialist", "Performance reviewer", "Hot paths, allocations, N+1 queries",
           "Performance", 1, ["code"], "Slow code goes unnoticed", levels=[F]),
    Plugin("validator", "agent", "Validator (Q1-Q3)", "Removes nitpicks and made-up problems, sets true severity",
           "Correctness", 1, ["findings"], "More noise and false alarms reach people", levels=[E, F]),
    Plugin("validator_panel", "agent", "Validator panel", "2-5 different models vote on each Critical finding",
           "Correctness", 2, ["findings"], "A single model decides every Critical", levels=[F]),
    Plugin("investigator", "agent", "Investigator", "Searches the code and runs one test to confirm a Critical",
           "Correctness", 3, ["findings", "repo"], "Critical findings are not confirmed before people see them", levels=[F]),
    Plugin("requirement_check", "agent", "Requirement check", "Analyst, interpreter and judge: does the PR do what was asked",
           "What", 3, ["requirement"], "No proof that each requirement item is met", levels=[F]),
    Plugin("radar", "agent", "Requirement radar", "Traces each change to a requirement item; flags tangled changes",
           "Scope", 1, ["requirement"], "Unrelated changes mixed into the PR are not flagged", levels=[F]),
    Plugin("fixer", "agent", "Fix agent", "Ready-to-apply patch for Critical and Major findings",
           "Correctness", 1, ["findings"], "No suggested patches", levels=[F]),
    Plugin("writer", "agent", "Plain-language writer", "Rewrites feedback for the person who signs",
           "Feedback", 1, ["findings"], "Feedback stays in the reviewer's technical words", levels=[E, F]),
    Plugin("blind_tests", "agent", "Blind test agent", "Writes tests from the requirement without seeing the code",
           "Tests", 2, ["requirement", "dotnet"], "No independent test evidence", levels=[E, F]),
    Plugin("sensor.secrets", "sensor", "Secret scan", "Keys and passwords in the diff", "Security", 0, [], "Leaked secrets", levels=[E, F]),
    Plugin("sensor.packages", "sensor", "Package check", "Packages that do not exist (slopsquatting)", "Security", 0, ["network"],
           "Fake packages slip in", levels=[E, F]),
    Plugin("sensor.test_weakening", "sensor", "Test weakening", "Deleted or weakened assertions", "Tests", 0, [],
           "Tests quietly weakened to pass", levels=[E, F]),
    Plugin("sensor.removed_guards", "sensor", "Removed guards", "Removed null, auth and range checks", "Security", 0, [],
           "Removed safety checks", levels=[E, F]),
    Plugin("sensor.risky_code", "sensor", "Risky code", "Unsafe code, reflection, crypto use", "Security", 0, [],
           "Risky constructs go unflagged", levels=[E, F]),
    Plugin("sensor.build_test", "sensor", "Build and tests", "Compiles the PR and runs every test", "Build", 0, ["dotnet"],
           "No proof that it compiles or that tests pass", levels=[E, F]),
]
for _l in ["risk", "calls", "apis", "events", "data", "security", "tests"]:
    BUILTIN.append(Plugin(f"lens.{_l}", "lens", f"{_l.capitalize()} lens", f"Shows {_l} facts for the PR on the map", "View", 0,
                          levels=[E, F]))
for _p in ["gemini", "openai", "anthropic", "local"]:
    BUILTIN.append(Plugin(f"provider.{_p}", "provider", f"{_p.capitalize()} models", "Model provider", "Models", 0, levels=[E, F]))
for _i in ["github", "gitlab", "azure_devops", "slack", "jira"]:
    BUILTIN.append(Plugin(f"integration.{_i}", "integration", _i.replace("_", " ").title(), "Posts the review summary", "Integrations", 0))

SENSOR_IDS = {"secret_scan": "sensor.secrets", "package_check": "sensor.packages", "test_integrity": "sensor.test_weakening",
              "removed_guards": "sensor.removed_guards", "risky_code": "sensor.risky_code", "dotnet_build": "sensor.build_test",
              "dotnet_test": "sensor.build_test"}


def plugin_signature(manifest_text: str, secret: str) -> str:
    return hmac.new(secret.encode(), manifest_text.encode(), hashlib.sha256).hexdigest()


def load_company(dir_path: str, allow_unsigned: bool) -> (List[Plugin], List[str]):
    """Company plugins: <dir>/<id>/manifest.yaml (+ prompt.md for specialists). Returns (plugins, problems)."""
    out, problems = [], []
    if not dir_path or not os.path.isdir(dir_path):
        return out, problems
    secret = os.environ.get("PRW_PLUGIN_SIGNING_KEY", "")
    for name in sorted(os.listdir(dir_path)):
        mf = os.path.join(dir_path, name, "manifest.yaml")
        if not os.path.exists(mf):
            continue
        text = open(mf, encoding="utf-8").read()
        m = yaml.safe_load(text) or {}
        sig_file = os.path.join(dir_path, name, "manifest.sig")
        signed = bool(secret and os.path.exists(sig_file) and
                      hmac.compare_digest(open(sig_file).read().strip(), plugin_signature(text, secret)))
        if not signed and not allow_unsigned:
            problems.append(f"company plugin '{name}' not loaded: it is not signed and this policy allows signed plugins only")
            continue
        kind = m.get("kind", "specialist")
        if kind not in ("specialist", "sensor"):
            problems.append(f"company plugin '{name}': kind must be specialist or sensor")
            continue
        prompt = ""
        if kind == "specialist":
            pp = os.path.join(dir_path, name, m.get("prompt_file", "prompt.md"))
            if not os.path.exists(pp):
                problems.append(f"company plugin '{name}': missing {os.path.basename(pp)}")
                continue
            prompt = open(pp, encoding="utf-8").read()
        pid = f"company.{m.get('id', name)}"
        out.append(Plugin(pid, kind, m.get("name", name), m.get("checks", ""), m.get("area", "Correctness"),
                          float(m.get("cost_calls", 1 if kind == "specialist" else 0)), m.get("needs", []),
                          m.get("loses", ""), str(m.get("version", "1.0")), "company", signed,
                          m.get("levels", ["full"]), prompt, m.get("command", ""), m.get("report", ""), m.get("format", "sarif")))
    return out, problems


class Registry:
    def __init__(self, cfg: PlatformConfig, base_dir: str = "."):
        self.cfg = cfg
        cdir = cfg.get("plugins", "company_dir", default="")
        if cdir and not os.path.isabs(cdir):
            cdir = os.path.join(base_dir, cdir)
        self.company, self.problems = load_company(cdir, bool(cfg.get("plugins", "allow_unsigned", default=True)))
        self.all: Dict[str, Plugin] = {p.id: p for p in BUILTIN + self.company}

    def catalog(self) -> List[Dict]:
        return [p.manifest() for p in self.all.values()]

    def enabled_for_level(self, level: str) -> Set[str]:
        base = level
        cov = self.cfg.get("coverage", default={}) or {}
        if level == "custom":
            base = (cov.get("custom") or {}).get("base", "essential")
        ids = {pid for pid, p in self.all.items() if base in p.levels}
        if level == "custom":
            ids |= set((cov.get("custom") or {}).get("enable", []))
            ids -= set((cov.get("custom") or {}).get("disable", []))
        ids |= set(self.cfg.get("plugins", "enable", default=[]) or [])
        return ids

    def resolve(self, area: Optional[str], tier: Optional[str]) -> Dict:
        """Plugins that run for one area, plus what is switched off and why."""
        level = self.cfg.level_for(area, tier)
        on = self.enabled_for_level(level)
        disabled = set(self.cfg.get("plugins", "disable", default=[]) or [])
        waivers = {(w["plugin"], w["area"]) for w in self.cfg.get("plugins", "waivers", default=[]) or []}
        off_reason: Dict[str, str] = {}
        for pid in list(on & disabled):
            if level == "full" and pid in REQUIRED_IN_FULL and (pid, area or "*") not in waivers and (pid, "*") not in waivers:
                off_reason[pid] = "kept on: required in Full; switching it off needs a signed waiver"
                continue
            on.discard(pid)
            off_reason[pid] = "switched off by the team policy" + (" (signed waiver)" if (pid, area or "*") in waivers else "")
        for pid, p in self.all.items():
            if pid not in on and pid not in off_reason and F in p.levels and p.kind not in ("lens", "provider", "integration"):
                off_reason[pid] = f"not part of {level.capitalize()} coverage"
        return {"level": level, "on": on, "off": off_reason}

    def estimate_calls(self, ids: Set[str]) -> float:
        return round(sum(self.all[i].cost_calls for i in ids if i in self.all), 1)
