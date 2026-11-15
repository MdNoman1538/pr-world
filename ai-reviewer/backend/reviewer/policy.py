"""The rulebook (review-policy.yaml) and the deterministic rule engine.

Humans own the policy; code enforces it. The LLM never sets or lowers the tier:
it may only *raise* it (see gate.py), and everything here is plain, testable code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

import yaml

from .git_tools import PullRequest
from .models import TIER_ORDER, Tier, TierDecision


@lru_cache(maxsize=512)
def _glob_re(glob: str) -> re.Pattern:
    i, out = 0, ""
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            out += "(?:.*/)?"; i += 3; continue
        if glob.startswith("**", i):
            out += ".*"; i += 2; continue
        out += {"*": "[^/]*", "?": "[^/]"}.get(c, re.escape(c))
        i += 1
    return re.compile("^" + out + "$", re.I)


def matches(path: str, globs: List[str]) -> bool:
    return any(_glob_re(g).match(path) for g in globs or [])


def max_tier(*tiers: Tier) -> Tier:
    return max(tiers, key=lambda t: TIER_ORDER[t])


def raise_one(t: Tier) -> Tier:
    return {Tier.LOW: Tier.MEDIUM, Tier.MEDIUM: Tier.HIGH, Tier.HIGH: Tier.HIGH}[t]


@dataclass
class Policy:
    raw: Dict
    path: str

    @property
    def version(self) -> str:
        return str(self.raw.get("version", "unversioned"))

    @property
    def approved_by(self) -> Optional[str]:
        return self.raw.get("approved_by") or None

    @property
    def areas(self) -> List[Dict]:
        return self.raw.get("areas", [])

    @property
    def content_rules(self) -> List[Dict]:
        return self.raw.get("content_rules", [])

    @property
    def change_rules(self) -> Dict:
        return self.raw.get("change_rules", {})

    @property
    def no_go(self) -> List[Dict]:
        return self.raw.get("no_go", [])

    @property
    def gates(self) -> Dict:
        return self.raw.get("gates", {})

    def area_for(self, path: str) -> Optional[Dict]:
        """Most specific (highest-tier) area matching a path."""
        hits = [a for a in self.areas if matches(path, a.get("paths", []))]
        if not hits:
            return None
        return max(hits, key=lambda a: TIER_ORDER[Tier(a.get("tier", "medium"))])

    def is_test(self, path: str) -> bool:
        return matches(path, self.change_rules.get("test_paths", []))

    def is_docs(self, path: str) -> bool:
        return matches(path, self.change_rules.get("docs_paths", []))


def load_policy(path: str) -> Policy:
    with open(path, encoding="utf-8") as fh:
        return Policy(yaml.safe_load(fh) or {}, path)


def load_plan(path: Optional[str]) -> Optional[List[str]]:
    """A plan is the approved list of paths/globs the change may touch."""
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return list(data.get("allowed_paths", []))


def decide_tier(pr: PullRequest, policy: Policy, plan: Optional[List[str]] = None) -> TierDecision:
    default = Tier(policy.raw.get("default_tier", "medium"))
    tier = Tier.LOW
    reasons: List[str] = []
    guarded: List[str] = []
    out_of_plan: List[str] = []
    rules = policy.change_rules

    non_doc = [f for f in pr.files if not policy.is_docs(f.path)]
    if not non_doc:
        reasons.append("Docs-only change (change_rules.docs_paths)")
        tier = Tier(rules.get("docs_only_tier", "low"))

    for f in pr.files:
        area = policy.area_for(f.path)
        if area:
            t = Tier(area.get("tier", "medium"))
            if TIER_ORDER[t] > TIER_ORDER[Tier.LOW]:
                reasons.append(f"{f.path}: area '{area.get('name')}' is {t.value} ({area.get('why', '')})".strip())
            tier = max_tier(tier, t)
            if area.get("guarded"):
                guarded.append(f.path)
        elif not policy.is_docs(f.path) and not policy.is_test(f.path):
            tier = max_tier(tier, default)
            reasons.append(f"{f.path}: no area in policy → default tier {default.value}")

        if matches(f.path, rules.get("dependency_files", [])):
            t = Tier(rules.get("dependency_tier", "high"))
            tier = max_tier(tier, t)
            reasons.append(f"{f.path}: dependency/build file changed → {t.value}")

        added = "\n".join(l for h in f.hunks for l in h.added)
        for rule in policy.content_rules:
            if added and re.search(rule["pattern"], added):
                t = Tier(rule.get("tier", "high"))
                tier = max_tier(tier, t)
                reasons.append(f"{f.path}: content rule '{rule['name']}' matched → {t.value}")

        for ng in policy.no_go:
            if matches(f.path, ng.get("paths", [])):
                tier = Tier.HIGH
                guarded.append(f.path)
                reasons.append(f"{f.path}: no-go zone ({ng.get('why', '')}) → AI may flag, never clear")

        if plan is not None and not matches(f.path, plan):
            out_of_plan.append(f.path)

    total = sum(f.n_added + f.n_removed for f in pr.files)
    big = int(policy.gates.get("large_change_lines", 400))
    if total > big:
        tier = raise_one(tier)
        reasons.append(f"Large change ({total} lines > {big}) → one tier up")
    if out_of_plan:
        tier = raise_one(tier)
        reasons.append(f"{len(out_of_plan)} file(s) outside the approved plan → one tier up")

    signoffs = int(policy.gates.get(f"{tier.value}_signoffs", 2 if tier == Tier.HIGH else 1))
    return TierDecision(tier=tier, reasons=reasons or ["No rule matched beyond the default"],
                        guarded_paths=sorted(set(guarded)), out_of_plan=out_of_plan,
                        signoffs_required=signoffs)


OPTIMIZATION_DEFAULT = r"(?i)\b(optimi[sz]\w*|performance|perf\b|faster|speed[- ]?up|allocation[- ]free|zero[- ]alloc\w*|" \
                       r"benchmark|throughput|latency|hot ?path|stackalloc|Span<)"


def optimization_context(policy: Policy, *texts: str) -> bool:
    """Research: AI 'optimization' changes are the most likely to introduce memory-safety flaws."""
    pat = policy.change_rules.get("optimization_pattern", OPTIMIZATION_DEFAULT)
    return any(t and re.search(pat, t) for t in texts)
