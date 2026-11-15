"""PR World platform settings (prworld.yaml): what a team may change, and what nobody may change.

Three layers (see docs/CUSTOMIZE.md):
  1. Locked core   - research-backed rules, never configurable (LOCKED below; refused if present in the file)
  2. Team policy   - this file, validated against SCHEMA; values outside the allowed ranges are refused
  3. Personal view - per user, in the app (never changes what the reviewer decides)

Every review records the fingerprint and a one-line badge of the settings it ran with.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PRESET_DIR = os.path.join(HERE, "presets")

LEVELS = ["essential", "full", "custom"]
ROLES = ["specialist", "validator", "panel", "radar", "fixer", "investigator", "requirement_analyst",
         "change_interpreter", "requirement_judge", "writer", "builder", "tester", "draft_policy"]
PROVIDERS = ["gemini", "openai", "anthropic", "local", "mock"]

# The locked core: these switches do not exist. A file that tries to set them is refused, with the reason.
LOCKED = {
    "evidence_check": "No evidence, no finding: a finding must quote real code at the cited line.",
    "allow_ai_approve": "The AI never approves; a named human (or a policy a named human signed) decides.",
    "ai_can_lower_tier": "The AI can raise risk, never lower it.",
    "blind_tests": "The test agent never sees the code it tests.",
    "count_inherited_failures": "Only new test failures count; failures from before the PR are shown, not counted.",
    "label_rules": "Labels are computed by code rules, not by a model.",
    "confidence_formula": "The confidence math (Jeffreys estimate) is fixed.",
    "trust_level_rules": "Low / Medium / High are computed by fixed rules from counted evidence.",
    "delete_dropped_findings": "Nothing is deleted: dropped findings stay in the audit list.",
    "server_side_access": "Access is always enforced on the server.",
    "audit_log": "Access, signatures and settings changes are always logged.",
    "unchecked_counts_as_passed": "A check that did not run is shown as 'Not checked', never as passed.",
}

MODEL = {"type": "object", "additionalProperties": False, "required": ["provider", "model"],
         "properties": {"provider": {"enum": PROVIDERS}, "model": {"type": "string", "minLength": 1}}}

SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "prworld.yaml",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "version": {"type": "string"},
        "preset": {"enum": ["strict-bank", "balanced", "fast-team", "critical-only"]},
        "approved_by": {"type": ["string", "null"]},
        "approved_on": {"type": ["string", "null"]},
        "rulebook": {"type": "string"},
        "coverage": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "default": {"enum": LEVELS},
                "by_tier": {"type": "object", "additionalProperties": False,
                            "properties": {t: {"enum": LEVELS} for t in ["high", "medium", "low"]}},
                "by_area": {"type": "object", "additionalProperties": {"enum": LEVELS}},
                "custom": {"type": "object", "additionalProperties": False,
                           "properties": {"base": {"enum": ["essential", "full"]},
                                          "enable": {"type": "array", "items": {"type": "string"}},
                                          "disable": {"type": "array", "items": {"type": "string"}}}},
            }},
        "plugins": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "enable": {"type": "array", "items": {"type": "string"}},
                "disable": {"type": "array", "items": {"type": "string"}},
                "company_dir": {"type": "string"},
                "allow_unsigned": {"type": "boolean"},
                "waivers": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["plugin", "area", "signed_by", "reason"],
                    "properties": {"plugin": {"type": "string"}, "area": {"type": "string"},
                                   "signed_by": {"type": "string", "minLength": 2}, "signed_on": {"type": "string"},
                                   "reason": {"type": "string", "minLength": 5}}}},
            }},
        "models": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "default": MODEL,
                "local_model": MODEL,
                "roles": {"type": "object", "additionalProperties": False,
                          "properties": {**{r: MODEL for r in ROLES if r != "panel"},
                                         "panel": {"type": "array", "items": MODEL, "minItems": 2, "maxItems": 5}}},
                "providers": {"type": "object", "additionalProperties": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"base_url": {"type": "string"}, "key_env": {"type": ["string", "null"]},
                                   "price_in_per_mtok": {"type": "number", "minimum": 0},
                                   "price_out_per_mtok": {"type": "number", "minimum": 0},
                                   "temperature": {"type": "number", "minimum": 0, "maximum": 1}}}},
            }},
        "budget": {
            "type": "object", "additionalProperties": False,
            "properties": {"max_calls": {"type": "integer", "minimum": 1, "maximum": 200},
                           "max_cost_eur": {"type": "number", "minimum": 0, "maximum": 500},
                           "timeout_s": {"type": "integer", "minimum": 60, "maximum": 14400},
                           "call_timeout_s": {"type": "integer", "minimum": 10, "maximum": 900}}},
        "thresholds": {
            "type": "object", "additionalProperties": False,
            "properties": {"min_blocker_confidence": {"type": "number", "minimum": 0.5, "maximum": 0.9},
                           "panel_size": {"type": "integer", "minimum": 2, "maximum": 5},
                           "investigator_max_steps": {"type": "integer", "minimum": 1, "maximum": 12},
                           "show_nits": {"type": "boolean"}}},
        "local_only": {"type": "array", "items": {"type": "string"}},
        "integrations": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "dry_run": {"type": "boolean"},
                "github": {"type": "object", "additionalProperties": False,
                           "properties": {"repo": {"type": "string"}, "token_env": {"type": "string"}, "api": {"type": "string"}}},
                "gitlab": {"type": "object", "additionalProperties": False,
                           "properties": {"project": {"type": "string"}, "token_env": {"type": "string"}, "api": {"type": "string"}}},
                "azure_devops": {"type": "object", "additionalProperties": False,
                                 "properties": {"org_url": {"type": "string"}, "project": {"type": "string"},
                                                "repo": {"type": "string"}, "token_env": {"type": "string"}}},
                "slack": {"type": "object", "additionalProperties": False, "properties": {"webhook_env": {"type": "string"}}},
                "jira": {"type": "object", "additionalProperties": False,
                         "properties": {"base_url": {"type": "string"}, "user_env": {"type": "string"},
                                        "token_env": {"type": "string"}}},
            }},
        "view_defaults": {
            "type": "object", "additionalProperties": False,
            "properties": {"trust_view": {"enum": ["level", "percent"]},
                           "severity_min": {"enum": ["Nit", "ShouldFix", "Blocker"]},
                           "lenses": {"type": "array", "items": {"enum": ["risk", "calls", "apis", "events", "data", "security", "tests"]}},
                           "layout": {"enum": ["map", "split", "read"]},
                           "density": {"enum": ["compact", "comfortable"]},
                           "theme": {"enum": ["dark", "light"]},
                           "language": {"enum": ["en"]},
                           "start": {"enum": ["list", "world", "feedback"]}}},
        "access": {"type": "object", "additionalProperties": False,
                   "properties": {"hide_restricted_names": {"type": "boolean"},
                                  "restricted_names": {"type": "array", "items": {"type": "string"}},
                                  "emergency_max_hours": {"type": "integer", "minimum": 1, "maximum": 24}}},
        "merge_policy": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "protected_areas": {"type": "array", "items": {"type": "string"}},
                "rules": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["name", "max_tier", "signed_by"],
                    "properties": {"name": {"type": "string"}, "max_tier": {"enum": ["low", "medium"]},
                                   "max_severity": {"enum": ["none", "Nit", "ShouldFix"]},
                                   "min_trust": {"enum": ["medium", "high"]},
                                   "signed_by": {"type": "string", "minLength": 2}, "signed_on": {"type": "string"},
                                   "signature": {"type": "string"}}}},
            }},
    },
}

# Plugins a "full" module may not lose without a signed waiver.
REQUIRED_IN_FULL = ["specialist.correctness", "specialist.safety", "specialist.tests", "validator", "validator_panel",
                    "requirement_check", "sensor.secrets", "sensor.test_weakening", "sensor.removed_guards"]


class ConfigError(ValueError):
    pass


def deep_merge(base: Dict, over: Dict) -> Dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _locked_hits(obj: Any, path: str = "") -> List[str]:
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k in LOCKED:
                hits.append(f"'{p}' cannot be set: {LOCKED[k]}")
            hits += _locked_hits(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _locked_hits(v, f"{path}[{i}]")
    return hits


def validate(raw: Dict) -> List[str]:
    """Return a list of human-readable problems (empty = valid)."""
    problems = _locked_hits(raw)
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return problems + ["jsonschema is not installed; run pip install -r requirements.txt"]
    v = jsonschema.Draft202012Validator(SCHEMA)
    for e in sorted(v.iter_errors(raw), key=lambda e: list(e.path)):
        where = ".".join(str(p) for p in e.path) or "(top level)"
        msg = e.message
        if e.validator == "additionalProperties":
            msg = msg.replace("Additional properties are not allowed", "Unknown setting")
        problems.append(f"{where}: {msg}")
    return problems


def load_preset(name: str) -> Dict:
    p = os.path.join(PRESET_DIR, f"{name}.yaml")
    if not os.path.exists(p):
        raise ConfigError(f"Unknown preset '{name}'")
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class PlatformConfig:
    raw: Dict                      # as written in the file
    resolved: Dict                 # preset + file, the values actually used
    path: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    # ---------------------------------------------------------------- simple getters
    def get(self, *keys, default=None):
        cur: Any = self.resolved
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    @property
    def preset(self) -> str:
        return self.resolved.get("preset", "balanced")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical(self.resolved).encode()).hexdigest()[:12]

    # ---------------------------------------------------------------- coverage
    def level_for(self, area_name: Optional[str], tier: Optional[str]) -> str:
        cov = self.get("coverage", default={}) or {}
        if area_name and area_name in (cov.get("by_area") or {}):
            return cov["by_area"][area_name]
        if tier and tier in (cov.get("by_tier") or {}):
            return cov["by_tier"][tier]
        return cov.get("default", "essential")

    def model_for(self, role: str) -> Dict:
        roles = self.get("models", "roles", default={}) or {}
        if role in roles and role != "panel":
            return roles[role]
        return self.get("models", "default", default={"provider": "gemini", "model": "gemini-3.8-flash"})

    def panel_models(self) -> List[Dict]:
        p = self.get("models", "roles", "panel")
        if p:
            return p[: int(self.get("thresholds", "panel_size", default=len(p)))]
        return [self.model_for("validator")]

    def badge(self, plugins_run: Optional[List[str]] = None, company: int = 0) -> str:
        cov = self.get("coverage", default={}) or {}
        parts = [f"{self.preset} preset", f"default {cov.get('default', 'essential')}"]
        bt = cov.get("by_tier") or {}
        if bt.get("high") == "full":
            parts.append("Full on high-risk")
        if company:
            parts.append(f"{company} company plugin{'s' if company != 1 else ''}")
        if plugins_run is not None:
            parts.append(f"{len(plugins_run)} plugins ran")
        if self.get("local_only"):
            parts.append(f"local-only: {', '.join(self.get('local_only'))}")
        if not self.resolved.get("approved_by"):
            parts.append("settings NOT approved")
        return " · ".join(parts) + f" · #{self.fingerprint}"

    def public(self) -> Dict:
        """Settings safe to show to users (no key names of providers' secrets needed for display)."""
        r = copy.deepcopy(self.resolved)
        for prov in (r.get("models", {}).get("providers") or {}).values():
            prov.pop("key_env", None)
        return r


def _model_warnings(resolved: Dict) -> List[str]:
    w = []
    roles = (resolved.get("models") or {}).get("roles") or {}
    default = (resolved.get("models") or {}).get("default") or {}

    def fam(m):
        return (m or default).get("provider"), (m or default).get("model")
    builder = fam(roles.get("builder"))
    for judge in ["validator", "requirement_judge"]:
        if fam(roles.get(judge)) == builder:
            w.append(f"'{judge}' uses the same model as 'builder' ({builder[0]}/{builder[1]}): shared blind spots and "
                     "self-preference are likely. Use a different model family for judging (research: Panickssery et al. 2024).")
    panel = roles.get("panel") or []
    if panel and len({(p["provider"], p["model"]) for p in panel}) < len(panel):
        w.append("The validator panel repeats a model; a panel only helps when its members differ.")
    seen = {}
    for r, m in roles.items():
        if r == "panel":
            continue
        seen.setdefault(fam(m), []).append(r)
    for k, rs in seen.items():
        if len(rs) >= 4:
            w.append(f"{len(rs)} roles share {k[0]}/{k[1]} ({', '.join(rs)}).")
    return w


def load_config(path: Optional[str] = None, overrides: Optional[Dict] = None) -> PlatformConfig:
    """Load prworld.yaml (or only the default preset when path is None) and validate it."""
    raw: Dict = {}
    if path:
        if not os.path.exists(path):
            raise ConfigError(f"Settings file not found: {path}")
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    if overrides:
        raw = deep_merge(raw, overrides)
    problems = validate(raw)
    if problems:
        raise ConfigError("The settings file was refused:\n- " + "\n- ".join(problems))
    preset = load_preset(raw.get("preset", "balanced"))
    resolved = deep_merge(preset, raw)
    resolved.setdefault("preset", raw.get("preset", "balanced"))
    problems = validate(resolved)
    if problems:  # a preset must also pass; this guards hand-edited preset files
        raise ConfigError("The resolved settings were refused:\n- " + "\n- ".join(problems))
    cfg = PlatformConfig(raw=raw, resolved=resolved, path=path)
    cfg.warnings = _model_warnings(resolved)
    if not resolved.get("approved_by"):
        cfg.warnings.append("The settings file is not approved: set approved_by and approved_on (a named human).")
    return cfg


def schema_json() -> str:
    return json.dumps(SCHEMA, indent=2)


def list_presets() -> List[Dict]:
    """Presets for the setup wizard: name, first comment line and coverage."""
    out = []
    for f in sorted(os.listdir(PRESET_DIR)):
        if f.endswith(".yaml"):
            name = f[:-5]
            with open(os.path.join(PRESET_DIR, f), encoding="utf-8") as fh:
                text = fh.read()
            first = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), "")
            raw = yaml.safe_load(text) or {}
            out.append({"name": name, "about": first, "coverage": raw.get("coverage", {}), "budget": raw.get("budget", {})})
    return out
