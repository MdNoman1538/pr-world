"""Offline end-to-end tests (no API key, no network). Run: python -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))

import make_sample_repo  # noqa: E402
from reviewer.orchestrator import Options, run_review  # noqa: E402
from reviewer.api import bundle  # noqa: E402


class OfflinePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.repo = os.path.join(cls.tmp, "repo")
        make_sample_repo.main(cls.repo)

    def run_it(self, fixture, memory="m.db"):
        opts = Options(repo=self.repo, base="master", head="ju26-issue-9999", requirement_id="ISSUE-9999",
                       requirement_file=os.path.join(ROOT, "examples", "ISSUE-9999.md"), owner="Tester",
                       policy=os.path.join(ROOT, "review-policy.yaml"), offline=True, mock=fixture,
                       out_dir=os.path.join(self.tmp, "runs"), memory_path=os.path.join(self.tmp, memory),
                       verbose=False)
        return run_review(opts)

    def test_1_fixture_review(self):
        r = self.run_it(os.path.join(ROOT, "examples", "mock_fixture.json"))
        self.assertEqual(r.decision, "BLOCKED")
        self.assertEqual(r.tier.tier.value, "high")
        dropped = {f.id: f.drop_reason for f in r.dropped_findings}
        self.assertIn("hallucination", dropped["C03"])          # evidence not in file (code check)
        self.assertIn("Q2 hallucination", dropped["C04"])       # validator Q2
        self.assertIn("Duplicate of C01", dropped["S01"])       # validator duplicate
        self.assertIn("Q1 nitpick", dropped["T02"])             # validator Q1 + policy
        kept = {f.id: f for f in r.findings}
        self.assertTrue({"C01", "C02", "T01"} <= set(kept))
        self.assertTrue(kept["C01"].patch.startswith("--- a/"))  # fix agent patch
        self.assertEqual(r.radar["counts"]["tangled"], 2)       # radar
        self.assertIn("Scope", {a.area for a in r.areas})
        self.assertEqual(r.funnel["patches"], 3)
        run_dir = os.path.join(self.tmp, "runs", r.run_id)
        for f in ("review.json", "review.md", "graph.json", "context.txt", "llm_log.jsonl"):
            self.assertTrue(os.path.exists(os.path.join(run_dir, f)), f)
        g = json.load(open(os.path.join(run_dir, "graph.json")))
        self.assertTrue(any(c["changed"] for c in g["cities"]))
        self.assertTrue(any(r_["kind"] == "call" for r_ in g["roads"]))
        self.assertTrue(os.path.exists(os.path.join(run_dir, "bundle.json")))
        self.assertEqual(bundle(run_dir)["schema"], "ai-reviewer-bundle/1")

    def test_2_iteration_delta(self):
        r1 = self.run_it(os.path.join(ROOT, "examples", "mock_fixture.json"), "delta.db")
        make_sample_repo.iterate(self.repo)
        r2 = self.run_it(os.path.join(ROOT, "examples", "mock_fixture_iteration2.json"), "delta.db")
        self.assertEqual(r2.delta["previous_run"], r1.run_id)
        self.assertTrue(any("Length limit" in x["title"] for x in r2.delta["fixed"]))
        self.assertTrue(r2.delta["still_open"])

    def test_3_cli_help(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "review.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
