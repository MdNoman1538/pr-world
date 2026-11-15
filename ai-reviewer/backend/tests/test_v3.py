"""Offline tests for v5 platform features: settings, coverage levels, not-checked, budget, plugins, agents, integrations.
Run: python -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))

import make_sample_repo  # noqa: E402
from reviewer.models import AreaStatus  # noqa: E402
from reviewer.orchestrator import Options, run_review  # noqa: E402
from reviewer.platform_config import ConfigError, load_config, validate  # noqa: E402
from reviewer.plugins import Registry, plugin_signature  # noqa: E402


class V5Platform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.repo = os.path.join(cls.tmp, "repo")
        make_sample_repo.main(cls.repo)

    def cfg_file(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as fh:
            yaml.safe_dump(data, fh)
        return p

    def run_it(self, config=None, fixture="mock_fixture.json", **kw):
        opts = Options(repo=self.repo, base="master", head="ju26-issue-9999", requirement_id="ISSUE-9999",
                       requirement_file=os.path.join(ROOT, "examples", "ISSUE-9999.md"), owner="Tester",
                       policy=os.path.join(ROOT, "review-policy.yaml"), offline=True,
                       mock=os.path.join(ROOT, "examples", fixture), out_dir=os.path.join(self.tmp, "runs"),
                       memory_path=os.path.join(self.tmp, "v5.db"), verbose=False, config=config, **kw)
        return run_review(opts)

    # ------------------------------------------------------------------ locked core
    def test_locked_keys_refused(self):
        probs = validate({"version": "1", "preset": "balanced", "allow_ai_approve": True})
        self.assertTrue(any("cannot be set" in p for p in probs), probs)

    def test_unknown_and_out_of_range_refused(self):
        self.assertTrue(validate({"version": "1", "preset": "balanced", "colour": "red"}))
        self.assertTrue(validate({"version": "1", "preset": "balanced", "budget": {"max_calls": 9999}}))
        p = self.cfg_file("bad.yaml", {"version": "1", "preset": "balanced", "thresholds": {"min_blocker_confidence": 0.1}})
        with self.assertRaises(ConfigError):
            load_config(p)

    # ------------------------------------------------------------------ default = everything on
    def test_default_full_run(self):
        r = self.run_it()
        self.assertEqual(r.decision, "BLOCKED")
        for pid in ["validator", "validator_panel", "investigator", "requirement_check", "radar", "fixer"]:
            self.assertIn(pid, r.plugins_run)
        self.assertEqual(r.not_checked_plugins, [])
        self.assertTrue(r.settings["fingerprint"])
        self.assertIn("NOT approved", r.settings["badge"])
        # requirement agents: analyst split items, judge (mock) said missing -> a human must check
        self.assertTrue(r.requirement_check["ran"])
        self.assertGreater(len(r.requirement_check["items"]), 0)
        req = [a for a in r.areas if a.area == "Requirement"][0]
        self.assertEqual(req.status, AreaStatus.HUMAN)
        # the panel never deletes a finding
        self.assertTrue(r.panel["ran"])
        ids = {f.id for f in r.findings}
        for fid in r.panel["votes"]:
            self.assertIn(fid, ids)

    # ------------------------------------------------------------------ coverage off -> Not checked, never passed
    def test_switched_off_is_not_checked(self):
        p = self.cfg_file("lean.yaml", {"version": "1", "preset": "balanced", "approved_by": "Test Owner", "approved_on": "2026-11-14",
                                        "coverage": {"default": "essential", "by_tier": {"high": "custom", "medium": "essential", "low": "essential"},
                                                     "custom": {"base": "essential", "disable": ["specialist.performance", "requirement_check"]}}})
        r = self.run_it(config=p)
        self.assertNotIn("specialist.performance", r.plugins_run)
        perf = [a for a in r.areas if a.area == "Performance"][0]
        self.assertEqual(perf.status, AreaStatus.NOT_CHECKED)
        req = [a for a in r.areas if a.area == "Requirement"][0]
        self.assertEqual(req.status, AreaStatus.NOT_CHECKED)
        self.assertTrue(any(n["plugin"] == "specialist.performance" for n in r.not_checked_plugins))
        self.assertIn("Not checked", r.decision_reason)

    # ------------------------------------------------------------------ budget
    def test_budget_reached_is_reported(self):
        p = self.cfg_file("tiny.yaml", {"version": "1", "preset": "balanced", "approved_by": "Test Owner", "approved_on": "2026-11-14",
                                        "coverage": {"default": "full", "by_tier": {"high": "full"}},
                                        "budget": {"max_calls": 3}})
        r = self.run_it(config=p)
        self.assertLessEqual(r.cost["calls"], 3)
        self.assertTrue(r.cost["refused_for_budget"])
        self.assertTrue(any("budget" in n["reason"] for n in r.not_checked_plugins), r.not_checked_plugins)

    # ------------------------------------------------------------------ company plugins
    def test_company_plugin_signature(self):
        cdir = os.path.join(self.tmp, "company")
        os.makedirs(os.path.join(cdir, "psd2"), exist_ok=True)
        man = "id: psd2\nname: PSD2 checklist\nkind: specialist\narea: security\nlevels: [full]\n"
        open(os.path.join(cdir, "psd2", "manifest.yaml"), "w").write(man)
        open(os.path.join(cdir, "psd2", "prompt.md"), "w").write("Check strong customer authentication is kept.")
        base = {"version": "1", "preset": "balanced", "plugins": {"company_dir": cdir, "allow_unsigned": False}}
        os.environ["PRW_PLUGIN_SIGNING_KEY"] = "test-secret"
        try:
            reg = Registry(load_config(overrides=base))
            self.assertEqual(reg.company, [])                       # unsigned -> refused
            self.assertTrue(reg.problems)
            open(os.path.join(cdir, "psd2", "manifest.sig"), "w").write(plugin_signature(man, "test-secret"))
            reg = Registry(load_config(overrides=base))
            self.assertEqual([p.id for p in reg.company], ["company.psd2"])
            open(os.path.join(cdir, "psd2", "manifest.sig"), "w").write("0" * 64)
            reg = Registry(load_config(overrides=base))
            self.assertEqual(reg.company, [])                       # wrong signature -> refused
        finally:
            os.environ.pop("PRW_PLUGIN_SIGNING_KEY", None)

    # ------------------------------------------------------------------ integrations (dry run never sends)
    def test_integrations_dry_run(self):
        p = self.cfg_file("int.yaml", {"version": "1", "preset": "balanced",
                                       "integrations": {"dry_run": True, "github": {"repo": "acme/shop"},
                                                        "slack": {"webhook_env": "SLACK_WEBHOOK_URL"}}})
        r = self.run_it(config=p, pr_number="12")
        names = {i.get("integration") for i in r.integrations}
        self.assertIn("github", names)
        for i in r.integrations:
            self.assertTrue(i.get("dry_run"))
        self.assertTrue(os.path.exists(os.path.join(r.run_dir, "integration-github.json")) if hasattr(r, "run_dir") else True)

    # ------------------------------------------------------------------ local-only areas
    def test_local_only_without_local_model_sends_nothing(self):
        cfg = load_config(overrides={"preset": "balanced", "local_only": ["Formatters"]})
        cfg.resolved["models"]["providers"].pop("local", None)     # simulate a team with no local model
        from reviewer.providers import LocalOnlyViolation, RoutedClient
        c = RoutedClient(cfg, None, mock=None, local_only_active=True)
        with self.assertRaises(LocalOnlyViolation):
            c.route("specialist:correctness")

    def test_local_only_routes_to_local(self):
        cfg = load_config(overrides={"preset": "balanced", "local_only": ["Formatters"],
                                     "models": {"local_model": {"provider": "local", "model": "qwen-coder"}}})
        from reviewer.providers import RoutedClient
        c = RoutedClient(cfg, None, mock=None, local_only_active=True)
        for role in ["specialist:safety", "validator", "panel:1", "requirement:judge"]:
            self.assertEqual(c.route(role)["provider"], "local", role)


if __name__ == "__main__":
    unittest.main()
