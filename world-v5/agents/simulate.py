"""Simulate a team of agents building the Loans module PR by PR, and record everything for the world viewer.

  python agents/simulate.py              # real run: Gemini agents, dotnet build/test, Roslyn cartographer, reviewer
  python agents/simulate.py --mock       # rehearsal: reference code instead of model calls (no API cost)
  python agents/simulate.py --no-dotnet  # no .NET SDK: skip build/test, lite cartographer (links marked as guesses)
Resumable: finished PRs are skipped unless --fresh.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml  # noqa: E402

from common import (BANK, PLAN, REVIEWER, ROOT, RUNS, SEED, VIEW, compile_errors, dotnet_major, git, in_scope,  # noqa: E402
                    load_env, models, read_tree, say, sh, tolerant_replace, write_json)
import agents as A  # noqa: E402
import world_diff  # noqa: E402
import world_lite  # noqa: E402

BUILDER = "Builder Agent|builder@agents.local"
TESTER = "Test Agent|tester@agents.local"
PLATFORM = "Platform Team|platform@bank.local"
MERGER = "Simulation (stands in for the human sign-off)|simulation@agents.local"


class Run:
    def __init__(self, a):
        self.a = a
        self.mock = a.mock
        self.models = models()
        self.major = None if a.no_dotnet else dotnet_major()
        self.dotnet = self.major is not None
        if not a.no_dotnet and not self.dotnet:
            say("No .NET SDK found: skipping build/test and using the lite cartographer (links will be marked as guesses).")
        self.tfm_major = self.major or 8
        self.prs = yaml.safe_load((PLAN / "prs.yaml").read_text())["prs"]
        self.key = {b["pr"]: b for b in yaml.safe_load((PLAN / "answer_key.yaml").read_text())["bugs"]}
        self.conventions = (PLAN / "conventions.md").read_text()
        self.platform_api = (PLAN / "platform_api.md").read_text()
        RUNS.mkdir(parents=True, exist_ok=True)
        (VIEW / "worlds").mkdir(parents=True, exist_ok=True)
        (VIEW / "diffs").mkdir(parents=True, exist_ok=True)
        (VIEW / "reviews").mkdir(parents=True, exist_ok=True)
        self.state_path = RUNS / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() and not a.fresh else {"prs": {}}
        from reviewer.llm import make_client
        self.client = make_client("" if self.mock else None, str(RUNS / "agent_log.jsonl"), 0.2)
        self.cartographer = None

    # ------------------------------------------------------------------ setup
    def setup_bank(self):
        if self.a.fresh and BANK.exists():
            # nothing is deleted: the previous run (bank, runs, viewer data) moves to archive/<time>
            arc = ROOT / "archive" / time.strftime("%Y%m%d-%H%M%S")
            arc.mkdir(parents=True, exist_ok=True)
            shutil.move(str(BANK), str(arc / "bank"))
            (arc / "runs").mkdir(exist_ok=True)
            for p in [RUNS / d for d in ("reviews", ".reviewer", "_answer_key")] + list(RUNS.glob("PR-*")) + [self.state_path]:
                if p.exists():
                    shutil.move(str(p), str(arc / "runs" / p.name))
            if VIEW.exists():
                shutil.move(str(VIEW), str(arc / "viewer-data"))
            for d in ("worlds", "diffs", "reviews"):
                (VIEW / d).mkdir(parents=True, exist_ok=True)
            say(f"Previous run kept in {arc.relative_to(ROOT)}")
        if (BANK / ".git").exists():
            return
        say("Creating Nordbank from the seed (platform: Auth, Accounts, Ledger, Audit, Notifications; 8 modules to be built by the agents)")
        shutil.copytree(SEED, BANK)
        for csproj in BANK.rglob("*.csproj"):
            t = csproj.read_text().replace("__TFM__", f"net{self.tfm_major}.0").replace("__EF__", f"{self.tfm_major}.0.*")
            csproj.write_text(t)
        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-q", "-m", "Seed: Nordbank platform (Auth, Accounts, Ledger, Audit, Notifications)", author=PLATFORM)
        ok, errs = self.build()
        if not ok:
            say("WARNING: the seed does not build:\n  " + "\n  ".join(errs[:10]))

    def build_cartographer(self):
        if not self.dotnet:
            self.cartographer = None
            return
        src = RUNS / "_tools" / "src"
        out = RUNS / "_tools" / "cartographer"
        dll = out / "Cartographer.dll"
        if dll.exists():
            self.cartographer = dll
            return
        shutil.rmtree(src, ignore_errors=True)
        shutil.copytree(ROOT / "tools" / "Cartographer", src)
        p = src / "Cartographer.csproj"
        p.write_text(p.read_text().replace("__TFM__", f"net{self.tfm_major}.0"))
        say("Building the Roslyn cartographer (first time only)")
        code, log = sh(["dotnet", "build", str(p), "-c", "Release", "-o", str(out), "-nologo", "-v", "q"], cwd=ROOT, timeout=900)
        (RUNS / "_tools" / "build.log").write_text(log)
        if code == 0 and dll.exists():
            self.cartographer = dll
        else:
            say("WARNING: Roslyn cartographer did not build; using the lite cartographer. See runs/_tools/build.log")
            for e in compile_errors(log)[:8]:
                say("   " + e)
            self.cartographer = None

    # ------------------------------------------------------------------ dotnet
    def build(self):
        if not self.dotnet:
            return True, []
        code, out = sh(["dotnet", "build", "tests/Bank.Tests/Bank.Tests.csproj", "-nologo", "-v", "q"], timeout=900)
        return code == 0, compile_errors(out) if code else []

    def test(self, rd: Path) -> Dict:
        if not self.dotnet:
            return {"ran": False, "reason": "no .NET SDK"}
        tdir = rd / "tests"
        shutil.rmtree(tdir, ignore_errors=True)
        code, out = sh(["dotnet", "test", "tests/Bank.Tests/Bank.Tests.csproj", "--no-build", "-nologo",
                        "--logger", "trx;LogFileName=results.trx", "--results-directory", str(tdir)], timeout=1200)
        (rd / "test.log").write_text(out)
        res = {"ran": True, "exit_code": code, "passed": 0, "failed": 0, "failed_tests": [], "tests": []}
        trx = next(iter(tdir.rglob("*.trx")), None) if tdir.exists() else None
        if trx:
            ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
            root = ET.parse(trx).getroot()
            for r in root.iter("{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}UnitTestResult"):
                name, outcome = r.get("testName"), r.get("outcome")
                msg = r.find(".//t:Message", ns)
                res["tests"].append({"name": name, "outcome": outcome, "message": (msg.text or "")[:400] if msg is not None else ""})
                if outcome == "Passed":
                    res["passed"] += 1
                elif outcome == "Failed":
                    res["failed"] += 1
                    res["failed_tests"].append(name)
        return res

    # ------------------------------------------------------------------ cartography
    def world_at(self, sha: str) -> Dict:
        path = VIEW / "worlds" / f"{sha}.json"
        if path.exists():
            return json.loads(path.read_text())
        current = git("rev-parse", "--abbrev-ref", "HEAD")
        dirty = git("status", "--porcelain")
        if dirty:
            raise RuntimeError("working tree not clean before cartography:\n" + dirty)
        git("checkout", "-q", sha)
        try:
            data = None
            if self.cartographer:
                code, out = sh(["dotnet", str(self.cartographer), str(BANK), str(path), sha], timeout=600)
                if code == 0 and path.exists():
                    data = json.loads(path.read_text())
                    errs = data.get("stats", {}).get("compile_errors", 0)
                    say(f"   cartographer (Roslyn) {sha[:7]}: {len(data['nodes'])} things, {len(data['edges'])} links"
                        + (f", {errs} unresolved references" if errs else ""))
                else:
                    say("   Roslyn cartographer failed, falling back to lite:\n" + out[-800:])
            if data is None:
                data = world_lite.build(BANK, path, sha)
                say(f"   cartographer (lite) {sha[:7]}: {len(data['nodes'])} things, {len(data['edges'])} links")
        finally:
            git("checkout", "-q", current)
        self.add_tiers(data)
        write_json(path, data)
        return data

    def add_tiers(self, world: Dict):
        pol = yaml.safe_load((PLAN / "review-policy.yaml").read_text())
        import fnmatch
        tier_of = {}
        for n in world["nodes"]:
            f = n.get("file")
            if not f or n["kind"] != "type":
                continue
            for area in pol["areas"]:
                if any(fnmatch.fnmatch(f, g) for g in area["paths"]):
                    tier_of.setdefault(n["module"], (area["tier"], area["name"], area.get("why", ""), area.get("guarded", False)))
                    break
        order = {"low": 0, "medium": 1, "high": 2}
        for n in world["nodes"]:
            if n["kind"] == "module":
                t = tier_of.get(n["id"][7:], ("high" if n["id"] == "module:Database" else pol.get("default_tier", "medium"), "", "", False))
                n["attrs"].update({"tier": t[0], "area": t[1], "why": t[2] or ("All tables of the bank" if n["id"] == "module:Database" else ""), "guarded": t[3]})
        world["policy"] = {"version": pol.get("version"), "approved_by": pol.get("approved_by")}

    # ------------------------------------------------------------------ agents
    def requirement(self, pr, rd) -> str:
        if self.mock:
            issue = A.template_issue(pr)
        else:
            say("   Requirement agent: writing the issue")
            issue = self.client.generate(role="requirement", model=self.models["requirement"], system=A.REQUIREMENT_SYSTEM,
                                         prompt=f"Product owner's brief for {pr['id']} ({pr['title']}):\n{pr['brief']}\n\n"
                                                f"Public contract the team agreed:\n{pr['contract']}\n\nBank coding conventions:\n{self.conventions}",
                                         schema=A.IssueOut)
        md = A.issue_markdown(pr, issue)
        (rd / "issue.md").write_text(md)
        return md

    def apply_files(self, files, scope) -> List[str]:
        rejected = []
        for f in files:
            path = f.path.replace("\\", "/").lstrip("./")
            if not in_scope(path, scope) or not path.endswith(".cs"):
                rejected.append(path)
                continue
            dest = BANK / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f.content if f.content.endswith("\n") else f.content + "\n")
        return rejected

    def builder(self, pr, issue_md, rd) -> Dict:
        """Writes the PR, one commit per step in pr['commits'] (or one commit). Real run only: no reference code.
        If a step still does not compile after the fix rounds, the PR is recorded as failed (nothing is faked)."""
        steps = pr.get("commits") or [{"title": pr["title"], "brief": "Implement the whole issue."}]
        rec = {"source": "model", "attempts": 0, "rejected_paths": [], "errors": [], "fallback": False, "files": [], "commits": []}
        for i, st in enumerate(steps, 1):
            code = read_tree(["src/**/*.cs", "src/**/CONSTITUTION.md"])
            context = "\n\n".join(f"===== {p} =====\n{t}" for p, t in code.items())
            step_txt = (f"\n\nTHIS COMMIT ({i} of {len(steps)}): {st['title']}\n{st['brief']}\n"
                        "Implement only this step now (earlier steps are already in the code base); the code must compile after it."
                        if len(steps) > 1 else "")
            prompt = (f"{issue_md}{step_txt}\n\nALLOWED SCOPE (glob): {pr['scope']}\n\nCODING CONVENTIONS:\n{self.conventions}\n\n"
                      f"CURRENT CODE BASE (src):\n{context}")
            say(f"   Builder: writing code" + (f" — commit {i}/{len(steps)}: {st['title']}" if len(steps) > 1 else ""))
            out = self.client.generate(role="builder", model=self.models["builder"], system=A.BUILDER_SYSTEM, prompt=prompt, schema=A.BuilderOut)
            rec["attempts"] += 1
            mine = [f.path for f in out.files]
            rec["files"] = sorted(set(rec["files"]) | set(mine))
            rec["rejected_paths"] += self.apply_files(out.files, pr["scope"])
            ok, errs = self.build()
            rounds = 0
            while not ok and rounds < 4:
                rounds += 1
                say(f"   Builder: build failed ({len(errs)} errors) — fix round {rounds}")
                cur = {p: (BANK / p).read_text() for p in mine if (BANK / p).exists()}
                fix = (f"{issue_md}{step_txt}\n\nYour code does not compile. Errors:\n" + "\n".join(errs) +
                       "\n\nYOUR FILES:\n" + "\n\n".join(f"===== {p} =====\n{t}" for p, t in cur.items()) +
                       f"\n\nCODE BASE (src):\n{context}\n\nReturn the corrected COMPLETE files you need to change.")
                out2 = self.client.generate(role="builder-fix", model=self.models["builder"], system=A.BUILDER_SYSTEM, prompt=fix, schema=A.BuilderOut)
                rec["attempts"] += 1
                mine = sorted(set(mine) | {f.path for f in out2.files})
                rec["files"] = sorted(set(rec["files"]) | set(mine))
                rec["rejected_paths"] += self.apply_files(out2.files, pr["scope"])
                ok, errs = self.build()
            if not ok:
                say(f"   Builder could not produce compiling code for step {i}: the PR is recorded as failed")
                rec.update(build_ok=False, errors=errs, failed_step=i)
                return rec
            msg = (out.commit_message or st["title"]).strip()
            git("add", "-A")
            git("commit", "-q", "--allow-empty", "-m", f"{pr['id']}: {msg}", author=BUILDER)
            rec["commits"].append({"step": i, "title": st["title"], "message": msg, "sha": git("rev-parse", "HEAD")})
            rec["commit_message"] = msg
            rec.setdefault("notes", out.notes)
        rec["build_ok"] = True
        return rec

    def planter(self, pr, rd) -> Optional[Dict]:
        bug = self.key.get(pr["id"])
        if not bug:
            return None
        rec = {"id": bug["id"], "pr": pr["id"], "category": bug["category"], "description": bug["description"].strip(),
               "applied": False, "method": None, "file": None, "lines": None}
        before = read_tree(pr["scope"])

        def record(path, old, new, method, expl=""):
            sm = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines())
            spans = [(j1 + 1, max(j1 + 1, j2)) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
            rec.update(applied=True, method=method, file=path, lines=[min(s[0] for s in spans), max(s[1] for s in spans)] if spans else None,
                       explanation=expl)

        feedback = ""
        for attempt in (1, 2):
            say("   Bug planter: inserting the hidden defect" + (" (second try)" if attempt == 2 else ""))
            try:
                out = self.client.generate(role="planter", model=self.models["planter"], system=A.PLANTER_SYSTEM,
                                           prompt=f"DEFECT TO INSERT:\n{bug['description']}{feedback}\n\nFILES:\n" +
                                                  "\n\n".join(f"===== {p} =====\n{t}" for p, t in before.items() if p.endswith('.cs')),
                                           schema=A.PlantOut)
                applied, missed = [], []
                for e in out.edits:
                    p = e.path.replace("\\", "/").lstrip("./")
                    if p not in before:
                        missed.append(f"{p}: not a file you were given")
                        continue
                    cur = (BANK / p).read_text()
                    new = tolerant_replace(cur, e.find, e.replace)
                    if new is None:
                        missed.append(f"{p}: the `find` text was not found exactly once")
                        continue
                    (BANK / p).write_text(new)
                    applied.append(p)
                ok, errs = self.build() if applied else (False, [])
                if applied and ok:
                    p = applied[0]
                    record(p, before[p], (BANK / p).read_text(), "llm", out.explanation)
                    break
                for p, t in before.items():
                    (BANK / p).write_text(t)
                feedback = ("\n\nYOUR LAST ATTEMPT FAILED: " + ("; ".join(missed) if missed else "") +
                            (" The code no longer compiled: " + "; ".join(errs[:5]) if applied and not ok else "") +
                            ". Copy `find` verbatim from the files below.")
            except Exception as ex:  # a planter failure must not stop the simulation
                say(f"   Bug planter failed: {str(ex)[:200]}")
                for p, t in before.items():
                    (BANK / p).write_text(t)
        if not rec["applied"]:
            say("   Bug planter: could not insert the defect into this code (recorded)")
        write_json(RUNS / "_answer_key" / f"{pr['id']}.json", rec)
        return rec

    def tester(self, pr, issue_md, rd) -> Dict:
        rec = {"source": "reference" if self.mock else "model", "files": [], "dropped": False, "attempts": 0}
        if not pr.get("tests_file"):
            rec["note"] = "No tests for a text-only change."
            return rec
        testkit = (BANK / "tests/Bank.Tests/TestKit.cs").read_text()
        example = (BANK / "tests/Bank.Tests/LedgerTests.cs").read_text()
        existing = sorted(p.relative_to(BANK).as_posix() for p in (BANK / "tests").rglob("*.cs") if "/bin/" not in str(p) and "/obj/" not in str(p))
        ns = "Bank.Tests." + pr["tests_file"].split("/")[-2]
        prompt = (f"{issue_md}\n\nWRITE THE TESTS TO: {pr['tests_file']} (namespace {ns})\n\nPLATFORM API:\n{self.platform_api}\n\n"
                  f"TestKit.cs:\n{testkit}\n\nSTYLE EXAMPLE (LedgerTests.cs):\n{example}\n\nEXISTING TEST FILES: {existing}")
        say("   Test agent: writing tests from the requirement (blind to the code)")
        folder = pr["tests_file"].rsplit("/", 1)[0]
        scope = [folder + "/*.cs"]
        out = self.client.generate(role="tester", model=self.models["tester"], system=A.TESTER_SYSTEM, prompt=prompt, schema=A.TestOut)
        rec["attempts"] = 1
        rejected = self.apply_files(out.files, scope)
        rec["files"] = [f.path for f in out.files if f.path not in rejected]
        ok, errs = self.build()
        while not ok and rec["attempts"] < 3:
            say(f"   Test agent: tests do not compile ({len(errs)} errors) — fix round {rec['attempts']}")
            mine = {p: (BANK / p).read_text() for p in rec["files"] if (BANK / p).exists()}
            out = self.client.generate(role="tester-fix", model=self.models["tester"], system=A.TESTER_SYSTEM,
                                       prompt=prompt + "\n\nYOUR TEST FILE DOES NOT COMPILE:\n" + "\n".join(errs) +
                                       "\n\nYOUR FILE:\n" + "\n".join(mine.values()) + "\n\nReturn the corrected complete file.",
                                       schema=A.TestOut)
            rec["attempts"] += 1
            self.apply_files(out.files, scope)
            ok, errs = self.build()
        if not ok:
            say("   Test agent: tests still do not compile — dropping them (recorded)")
            for p in rec["files"]:
                (BANK / p).unlink(missing_ok=True)
            rec.update(dropped=True, errors=errs, files=[])
        return rec

    # ------------------------------------------------------------------ reviewer
    def review(self, pr, branch, rd) -> Dict:
        if self.a.no_review:
            return {"skipped": True}
        out_dir = RUNS / "reviews"
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(REVIEWER / "backend" / "review.py"), "--memory", str(RUNS / ".reviewer" / "memory.db"), "review",
               "--repo", str(BANK), "--base", "main", "--head", branch, "--req-id", pr["id"], "--req-file", str(rd / "issue.md"),
               "--owner", self.a.owner, "--policy", str(PLAN / "review-policy.yaml"), "--out", str(out_dir), "--offline",
               "--workers", "3", "--fast-model", self.models["reviewer"], "--strong-model", self.models["reviewer"]]
        cfg = (str(Path(self.a.config).resolve()) if self.a.config else None) or (str(REVIEWER / "backend" / "prworld.yaml") if (REVIEWER / "backend" / "prworld.yaml").exists() else None)
        if cfg:
            cmd += ["--config", cfg]          # team settings: coverage, models per role, budget (v5)
        if self.mock:
            cmd.append("--mock")
        if self.dotnet:
            cmd += ["--build", "--test", "--build-target", "tests/Bank.Tests/Bank.Tests.csproj", "--test-target", "tests/Bank.Tests/Bank.Tests.csproj"]
        (RUNS / ".reviewer").mkdir(parents=True, exist_ok=True)
        say("   Reviewer: reviewing the PR (specialists, validator, radar, fixes)")
        before = {p.name for p in out_dir.iterdir()}
        code, log = sh(cmd, cwd=REVIEWER, timeout=3600)
        (rd / "review.log").write_text(log)
        new = sorted((p for p in out_dir.iterdir() if p.name not in before and (p / "review.json").exists()), key=lambda p: p.stat().st_mtime)
        if not new:
            say("   Reviewer produced no report (see runs/%s/review.log)" % pr["id"])
            return {"error": log[-1500:], "exit_code": code}
        r = json.loads((new[-1] / "review.json").read_text())
        return {"run_dir": str(new[-1].relative_to(ROOT)), "run_id": r.get("run_id"), "decision": r.get("decision"),
                "reason": r.get("decision_reason"), "tier": (r.get("tier") or {}).get("tier"), "ai_error": r.get("ai_error"),
                "exit_code": code, "review": r}

    # ------------------------------------------------------------------ one PR
    def run_pr(self, pr):
        pid, branch = pr["id"], pr["id"].lower()
        rd = RUNS / pid
        shutil.rmtree(rd, ignore_errors=True)
        rd.mkdir(parents=True)
        say(f"== {pid} [{pr.get('type', 'feature')}]: {pr['title']}")
        missing = [d for d in pr.get("depends_on", []) if (self.state["prs"].get(d) or {}).get("status", "merged") != "merged"
                   or d not in self.state["prs"]]
        if missing:
            say(f"   Skipped: depends on {', '.join(missing)}, which did not merge")
            self.state.setdefault("not_merged", {})[pid] = {"id": pid, "title": pr["title"], "status": "skipped",
                                                            "reason": f"depends on {', '.join(missing)}"}
            write_json(self.state_path, self.state)
            return
        git("checkout", "-q", "main")
        base = git("rev-parse", "HEAD")
        git("checkout", "-q", "-B", branch)

        issue_md = self.requirement(pr, rd)
        b = self.builder(pr, issue_md, rd)
        if not b.get("build_ok"):
            write_json(rd / "builder.json", b)
            git("checkout", "-q", "--", ".")
            git("clean", "-q", "-fd")
            git("checkout", "-q", "main")
            git("branch", "-q", "-D", branch)
            self.state.setdefault("not_merged", {})[pid] = {"id": pid, "title": pr["title"], "status": "build failed",
                                                            "reason": f"Builder code did not compile (step {b.get('failed_step')})",
                                                            "errors": b.get("errors", [])[:8]}
            write_json(self.state_path, self.state)
            return
        planted = self.planter(pr, rd)
        if planted and planted["applied"]:
            git("add", "-A")
            git("commit", "-q", "--amend", "--no-edit", author=BUILDER)
        t = self.tester(pr, issue_md, rd)
        if t["files"]:
            git("add", "-A")
            git("commit", "-q", "-m", f"{pid}: tests from the requirement", author=TESTER)
        ok, errs = self.build()
        tests = self.test(rd) if ok else {"ran": False, "reason": "build failed", "errors": errs}
        head = git("rev-parse", "HEAD")

        wb = self.world_at(base)
        wh = self.world_at(head)
        _, diff_text = sh(["git", "diff", "-U0", f"{base}..{head}"])
        d = world_diff.diff(wb, wh, diff_text)
        write_json(VIEW / "diffs" / f"{pid}.json", d)

        rv = self.review(pr, branch, rd)
        findings = []
        if rv.get("review"):
            for f in rv["review"].get("findings", []):
                findings.append({k: f.get(k) for k in ("id", "dimension", "severity", "title", "claim", "file", "line_start", "line_end",
                                                       "evidence", "evidence_verified", "suggested_fix", "patch", "requirement_link", "source", "confidence")})
            write_json(VIEW / "reviews" / f"{pid}.json", {"decision": rv["decision"], "reason": rv["reason"], "tier": rv["tier"],
                                                          "ai_error": rv.get("ai_error"), "findings": findings,
                                                          "areas": rv["review"].get("areas", []), "run_id": rv.get("run_id"),
                                                          "sensors": [{k: s.get(k) for k in ("name", "result", "summary")} for s in rv["review"].get("sensors", [])]})
            say(f"   Reviewer decision: {rv['decision']} (tier {rv['tier']}, {len(findings)} findings)")
        git("checkout", "-q", "main")
        git("merge", "-q", "--no-ff", branch, "-m", f"Merge {pid}: {pr['title']} (reviewer: {rv.get('decision', 'n/a')})", author=MERGER)
        merged = git("rev-parse", "HEAD")

        self.state.get("not_merged", {}).pop(pid, None)
        rec = {"id": pid, "title": pr["title"], "type": pr.get("type", "feature"), "status": "merged",
               "branch": branch, "base": base, "head": head, "merged": merged,
               "issue": issue_md, "builder": b, "tests": tests, "tester": t,
               "review": {k: v for k, v in rv.items() if k != "review"}, "findings": len(findings),
               "planted": bool(planted and planted["applied"]), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.state["prs"][pid] = rec
        write_json(self.state_path, self.state)
        write_json(rd / "record.json", rec)

    # ------------------------------------------------------------------ meaning layer
    def meaning(self, world: Dict) -> Dict:
        out = {}
        nodes = [n for n in world["nodes"] if n["kind"] in ("module", "type") and not (n.get("attrs") or {}).get("is_test")]
        for n in nodes:
            s = (n.get("attrs") or {}).get("summary")
            if s:
                out[n["id"]] = {"summary": s, "source": "doc comment"}
        if self.mock:
            return out
        todo = [n for n in nodes if n["id"] not in out]
        cache_p = RUNS / "meaning_cache.json"
        cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
        kids = {}
        for n in world["nodes"]:
            kids.setdefault(n.get("parent"), []).append(n)
        def facts(n):
            if n["kind"] == "module":
                c = world.get("constitutions", {}).get(n["name"], "")
                return f"[{n['id']}] module {n['name']}. Constitution: {c[:600]}"
            a = n.get("attrs") or {}
            mem = ", ".join(f"{k['kind']} {(k.get('attrs') or {}).get('signature', k['name'])}" for k in kids.get(n["id"], [])[:14])
            return f"[{n['id']}] {a.get('type_kind', 'type')} in {n['module']}/{n['layer']}: {a.get('signature', n['name'])}. Members: {mem}"
        pending = [n for n in todo if facts(n) not in cache]
        for i in range(0, len(pending), 25):
            batch = pending[i:i + 25]
            try:
                say(f"   Cartographer-AI: describing {len(batch)} elements")
                res = self.client.generate(role="meaning", model=self.models["meaning"], system=A.MEANING_SYSTEM,
                                           prompt="Describe each element (use the id in brackets):\n" + "\n".join(facts(n) for n in batch),
                                           schema=A.MeaningOut)
                by = {m.id.strip("[]"): m.summary for m in res.items}
                for n in batch:
                    if n["id"] in by:
                        cache[facts(n)] = by[n["id"]]
            except Exception as ex:
                say(f"   Cartographer-AI failed: {str(ex)[:160]}")
        write_json(cache_p, cache)
        for n in todo:
            if facts(n) in cache:
                out[n["id"]] = {"summary": cache[facts(n)], "source": "AI (unverified meaning)"}
        return out

    # ------------------------------------------------------------------ scorecard + viewer index
    def scorecard(self) -> Dict:
        bugs = []
        for pid, rec in self.state["prs"].items():
            k = RUNS / "_answer_key" / f"{pid}.json"
            if not k.exists():
                continue
            bug = json.loads(k.read_text())
            rv = VIEW / "reviews" / f"{pid}.json"
            findings = json.loads(rv.read_text())["findings"] if rv.exists() else []
            wh = json.loads((VIEW / "worlds" / f"{rec['head']}.json").read_text())
            member = None
            if bug.get("applied") and bug.get("lines"):
                l1, l2 = bug["lines"]
                cands = [n for n in wh["nodes"] if n.get("file") == bug["file"] and n["kind"] in ("method", "ctor", "property")
                         and (n.get("line") or 0) <= l2 and (n.get("end_line") or 0) >= l1]
                if cands:
                    member = min(cands, key=lambda n: (n["end_line"] - n["line"]))
            caught = []
            for f in findings:
                if not bug.get("applied") or f.get("file") != bug.get("file"):
                    continue
                fl1, fl2 = f.get("line_start") or 0, f.get("line_end") or f.get("line_start") or 0
                near = bug["lines"] and fl1 <= bug["lines"][1] + 6 and fl2 >= bug["lines"][0] - 6
                inside = member and member["line"] <= fl1 <= member["end_line"]
                if near or inside:
                    caught.append({"id": f["id"], "severity": f["severity"], "title": f["title"]})
            failed = (rec.get("tests") or {}).get("failed_tests", [])
            bugs.append({**bug, "member": member["id"] if member else None, "member_name": member["name"] if member else None,
                         "caught_by_reviewer": caught, "failed_tests_in_pr": failed,
                         "verdict": "caught by reviewer" if caught else ("tests failed in this PR" if failed else "missed")})
        prs = []
        for pid, rec in self.state["prs"].items():
            rv = VIEW / "reviews" / f"{pid}.json"
            r = json.loads(rv.read_text()) if rv.exists() else {}
            matched = {c["id"] for b in bugs if b["pr"] == pid for c in b["caught_by_reviewer"]}
            prs.append({"id": pid, "decision": r.get("decision"), "tier": r.get("tier"), "findings": len(r.get("findings", [])),
                        "matched_planted": len(matched), "other_findings": len(r.get("findings", [])) - len(matched),
                        "tests": {k: (rec.get("tests") or {}).get(k) for k in ("passed", "failed")},
                        "builder": {k: rec["builder"].get(k) for k in ("source", "attempts", "fallback")}})
        clean = [p for p in prs if p["id"] not in {b["pr"] for b in bugs}]
        for p in clean:
            rv = VIEW / "reviews" / f"{p['id']}.json"
            fs = json.loads(rv.read_text())["findings"] if rv.exists() else []
            p["clean"] = True
            p["critical_on_clean"] = [{"id": f["id"], "title": f["title"]} for f in fs if f.get("severity") == "Blocker"]
        sc = {"bugs": bugs, "prs": prs,
              "summary": {"planted": sum(1 for b in bugs if b.get("applied")),
                          "caught_by_reviewer": sum(1 for b in bugs if b["caught_by_reviewer"]),
                          "tests_failed": sum(1 for b in bugs if b["failed_tests_in_pr"] and not b["caught_by_reviewer"]),
                          "missed": sum(1 for b in bugs if b["verdict"] == "missed"),
                          "not_planted": sum(1 for b in bugs if not b.get("applied")),
                          "clean_prs": len(clean),
                          "clean_prs_with_critical": sum(1 for p in clean if p["critical_on_clean"])},
              "note": "Other findings are not automatically false alarms: a human must judge them."}
        write_json(VIEW / "scorecard.json", sc)
        return sc

    def export(self):
        git("checkout", "-q", "main")
        main = git("rev-parse", "HEAD")
        seed = git("rev-list", "--max-parents=0", "HEAD")
        wm = self.world_at(main)
        self.world_at(seed)
        write_json(VIEW / "meaning.json", self.meaning(wm))
        sc = self.scorecard()
        index = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "mode": {"mock": self.mock, "dotnet": self.dotnet, "cartographer": wm.get("generated_by"),
                          "models": {} if self.mock else self.models},
                 "main": main, "seed": seed,
                 "prs": [{k: v for k, v in self.state["prs"][p["id"]].items()} for p in self.prs if p["id"] in self.state["prs"]],
                 "not_merged": [self.state.get("not_merged", {})[p["id"]] for p in self.prs if p["id"] in self.state.get("not_merged", {})],
                 "scorecard": sc["summary"]}
        write_json(VIEW / "index.json", index)
        say(f"Viewer data ready: {VIEW.relative_to(ROOT)}  (planted {sc['summary']['planted']}, "
            f"caught by reviewer {sc['summary']['caught_by_reviewer']}, missed {sc['summary']['missed']})")

    def main(self):
        self.setup_bank()
        self.build_cartographer()
        only = set(self.a.only.split(",")) if self.a.only else None
        for pr in self.prs:
            if only and pr["id"] not in only:
                continue
            if pr["id"] in self.state["prs"] and not self.a.redo:
                say(f"== {pr['id']} already done (use --fresh to start over)")
                continue
            self.run_pr(pr)
        self.export()


def cli():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--no-dotnet", action="store_true", help="skip dotnet build/test; lite cartographer")
    p.add_argument("--no-review", action="store_true", help="skip the reviewer")
    p.add_argument("--fresh", action="store_true", help="delete the bank repo and all runs, start from the seed")
    p.add_argument("--redo", action="store_true", help="run PRs again even if already done")
    p.add_argument("--only", help="comma list, e.g. PR-1,PR-2")
    p.add_argument("--export-only", action="store_true", help="only rebuild viewer data from finished runs")
    p.add_argument("--owner", default="Md Abdullah Al Noman", help="named human accountable for the PRs")
    p.add_argument("--config", help="team settings for the reviewer (default: ../ai-reviewer/backend/prworld.yaml if it exists)")
    a = p.parse_args()
    if a.mock:
        sys.exit("Nordbank has no rehearsal mode: every PR is written by the agents. Run without --mock.")
    load_env()
    r = Run(a)
    if a.export_only:
        r.build_cartographer()
        r.export()
    else:
        r.main()


if __name__ == "__main__":
    cli()
