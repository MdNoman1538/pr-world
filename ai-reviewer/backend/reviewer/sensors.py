"""Deterministic sensors: fast, repeatable checks that run before any LLM.

Research basis: mechanical checks belong to tools, not to the model; unit-test pass rate alone
says little about AI-code quality; AI code can reference packages that do not exist; repeated
AI refinement tends to strip boundary checks. Each sensor returns a SensorResult and, where it
finds something specific, Findings with exact file/line evidence.

Sensors never approve anything. A sensor that could not run is reported as "not checked".
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from typing import List, Tuple

from .git_tools import FileChange, PullRequest, git
from .models import Dimension, Finding, SensorResult, Severity
from .policy import Policy

_counter = {"n": 0}


def _fid() -> str:
    _counter["n"] += 1
    return f"D{_counter['n']:02d}"


def _sensor_finding(name: str, dim: Dimension, sev: Severity, title: str, claim: str,
                    f: FileChange, line: int, evidence: str, fix: str = "") -> Finding:
    return Finding(id=_fid(), dimension=dim, source=f"sensor:{name}", title=title, claim=claim,
                   severity=sev, file=f.path, line_start=line, line_end=line, evidence=evidence.strip(),
                   confidence=1.0, suggested_fix=fix, evidence_verified=True)


def _added_with_lines(f: FileChange) -> List[Tuple[int, str]]:
    return [(h.new_start + i, t) for h in f.hunks for i, t in enumerate(h.added)]


def _removed_with_lines(f: FileChange) -> List[Tuple[int, str, int]]:
    """(old_line, text, new_anchor_line) for removed lines."""
    return [(h.old_start + i, t, h.new_start) for h in f.hunks for i, t in enumerate(h.removed)]


# ------------------------------------------------------------------ secret scan
_SECRET_PATTERNS = [
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ("password literal", r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\"[^\"]{4,}\""),
    ("API key literal", r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*\"[A-Za-z0-9_\-]{12,}\""),
    ("connection string with password", r"(?i)Password\s*=\s*[^;\"]{3,};"),
]


def secret_scan(pr: PullRequest) -> Tuple[SensorResult, List[Finding]]:
    findings: List[Finding] = []
    for f in pr.files:
        for line, text in _added_with_lines(f):
            for name, pat in _SECRET_PATTERNS:
                if re.search(pat, text):
                    findings.append(_sensor_finding(
                        "secrets", Dimension.SAFETY, Severity.BLOCKER, f"Possible {name} added",
                        f"An added line matches the {name} pattern. Secrets must never be committed.",
                        f, line, text, "Remove the value and load it from configuration or a secret store."))
    return SensorResult(name="secret_scan", ran=True, passed=not findings,
                        summary=f"{len(findings)} possible secret(s) in added lines" if findings
                        else "No secret patterns in added lines"), findings


# ------------------------------------------------------------- package check
_PKG_RE = re.compile(r"<Package(?:Reference|Version)\s+[^>]*Include=\"([^\"]+)\"[^>]*?(?:Version=\"([^\"]+)\")?", re.I)


def _nuget_exists(pkg: str, version: str | None, timeout: float = 8.0) -> Tuple[bool | None, str]:
    url = f"https://api.nuget.org/v3-flatcontainer/{pkg.lower()}/index.json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            versions = json.loads(resp.read().decode()).get("versions", [])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "package not found on nuget.org"
        return None, f"nuget.org returned HTTP {e.code}"
    except Exception as e:  # offline, DNS, proxy
        return None, f"could not reach nuget.org ({type(e).__name__})"
    if version and not version.startswith("$") and version.lower() not in [v.lower() for v in versions]:
        return False, f"version {version} not published (latest: {versions[-1] if versions else 'n/a'})"
    return True, "exists on nuget.org"


def package_check(pr: PullRequest, offline: bool = False) -> Tuple[SensorResult, List[Finding]]:
    findings: List[Finding] = []
    details: List[str] = []
    unreachable = False
    added_pkgs = 0
    for f in pr.files:
        if not re.search(r"\.(csproj|props|targets|nuspec|config)$", f.path, re.I):
            continue
        for line, text in _added_with_lines(f):
            for m in _PKG_RE.finditer(text):
                added_pkgs += 1
                pkg, ver = m.group(1), m.group(2)
                if offline:
                    details.append(f"{pkg} {ver or ''}: not checked (offline mode)")
                    unreachable = True
                    continue
                ok, why = _nuget_exists(pkg, ver)
                details.append(f"{pkg} {ver or ''}: {why}")
                if ok is None:
                    unreachable = True
                elif ok is False:
                    findings.append(_sensor_finding(
                        "packages", Dimension.SAFETY, Severity.BLOCKER, f"Package '{pkg}' cannot be verified",
                        f"The PR adds a dependency on '{pkg}' {ver or ''}, but {why}. AI-written code is known to "
                        "reference packages that do not exist, which attackers can register later.",
                        f, line, text, "Use a real, published package and version, or remove the reference."))
    if added_pkgs == 0:
        return SensorResult(name="package_check", ran=True, passed=True,
                            summary="No package references added"), []
    if unreachable and not findings:
        return SensorResult(name="package_check", ran=False, summary="Package registry not reachable; "
                            "added packages NOT verified", details=details), []
    return SensorResult(name="package_check", ran=True, passed=not findings,
                        summary=f"{added_pkgs} added package reference(s) checked against nuget.org",
                        details=details), findings


# ---------------------------------------------------------- test integrity
_ASSERT = re.compile(r"\b(Assert\.\w+|Should\(\)|\.Should\w*\(|Verify\(|Expect\(|Assert\(|CollectionAssert\.|StringAssert\.)")
_TEST_ATTR = re.compile(r"\[(Fact|Theory|Test|TestMethod|TestCase)\b")
_SKIP = re.compile(r"Skip\s*=|\[Ignore\b|\[Explicit\b|Assert\.Inconclusive|Assert\.Ignore|return;\s*//\s*skip", re.I)
_TOLERANCE = re.compile(r"(?i)\b(tolerance|precision|delta|epsilon|within\()")


def test_integrity(pr: PullRequest, policy: Policy) -> Tuple[SensorResult, List[Finding]]:
    """Catch 'pass-by-accident' tests: deleted assertions, deleted tests, new skips, widened tolerances."""
    findings: List[Finding] = []
    test_files = [f for f in pr.files if policy.is_test(f.path) and f.path.endswith(".cs")]
    for f in test_files:
        added = _added_with_lines(f)
        removed = _removed_with_lines(f)
        added_norm = {re.sub(r"\s+", "", t) for _, t in added}
        a_asserts = sum(1 for _, t in added if _ASSERT.search(t))
        r_asserts = [(ol, t, anchor) for ol, t, anchor in removed
                     if _ASSERT.search(t) and re.sub(r"\s+", "", t) not in added_norm]
        if r_asserts:
            ol, t, anchor = r_asserts[0]
            findings.append(_sensor_finding(
                "test_integrity", Dimension.TESTS, Severity.SHOULD_FIX, "Assertions removed from tests",
                f"{len(r_asserts)} existing assertion line(s) were removed and not re-added ({a_asserts} assertion "
                f"line(s) added elsewhere). Check the tests were not weakened to make them pass (first removed "
                f"line shown, old line {ol}).", f, anchor, t,
                "Restore the assertion or explain in the PR why it is no longer valid."))
        r_tests = [(ol, t, anchor) for ol, t, anchor in removed if _TEST_ATTR.search(t)]
        a_tests = sum(1 for _, t in added if _TEST_ATTR.search(t))
        if len(r_tests) > a_tests:
            ol, t, anchor = r_tests[0]
            findings.append(_sensor_finding(
                "test_integrity", Dimension.TESTS, Severity.SHOULD_FIX, "Test methods removed",
                f"{len(r_tests)} test attribute(s) removed, {a_tests} added. A deleted test can hide a regression.",
                f, anchor, t, "Keep the test or justify its removal against the requirement."))
        for line, text in added:
            if _SKIP.search(text):
                findings.append(_sensor_finding(
                    "test_integrity", Dimension.TESTS, Severity.SHOULD_FIX, "Test skipped or ignored",
                    "A test was marked as skipped/ignored in this PR. Skipped tests verify nothing.",
                    f, line, text, "Fix the test instead of skipping it, or link the issue that tracks it."))
        for ol, t, anchor in removed:
            if _TOLERANCE.search(t):
                findings.append(_sensor_finding(
                    "test_integrity", Dimension.TESTS, Severity.SHOULD_FIX, "Test tolerance changed",
                    f"A line with a tolerance/precision setting was changed (old line {ol}). Check it was not widened.",
                    f, anchor, t, "Keep the original tolerance unless the requirement changed."))
    edited = len(test_files)
    return SensorResult(name="test_integrity", ran=True, passed=not findings,
                        summary=(f"{edited} test file(s) edited; {len(findings)} weakening signal(s)"
                                 if edited else "No test files edited")), findings


# ------------------------------------------------------- removed guards
_GUARD = re.compile(r"\bthrow\b|ArgumentNullException|ArgumentOutOfRangeException|ThrowIf\w*\(|"
                    r"\bif\s*\(.*(==\s*null|is\s+null|<\s*0|>=?\s*\w+\.(Length|Count)|\.IsEmpty)|"
                    r"Debug\.Assert|\bchecked\s*\(|ThrowHelper\.")


def removed_guards(pr: PullRequest, policy: Policy) -> Tuple[SensorResult, List[Finding]]:
    findings: List[Finding] = []
    for f in pr.files:
        if not f.path.endswith(".cs") or policy.is_test(f.path):
            continue
        added_norm = {re.sub(r"\s+", "", t) for h in f.hunks for t in h.added}
        for ol, t, anchor in _removed_with_lines(f):
            if _GUARD.search(t) and re.sub(r"\s+", "", t) not in added_norm:
                findings.append(_sensor_finding(
                    "removed_guards", Dimension.CORRECTNESS, Severity.SHOULD_FIX, "Guard or validation removed",
                    f"A validation/throw line was removed (old line {ol}) and not re-added. Repeated AI "
                    "refinement is known to strip boundary checks.", f, anchor, t,
                    "Confirm the check is no longer needed, or restore it."))
    return SensorResult(name="removed_guards", ran=True, passed=not findings,
                        summary=f"{len(findings)} removed guard line(s)" if findings
                        else "No validation/guard lines removed"), findings


# ------------------------------------------------------- risky added code
_RISKY = [
    ("empty catch block", re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}"), Severity.SHOULD_FIX, Dimension.CORRECTNESS,
     "An empty catch silently swallows errors."),
    ("catch-all exception", re.compile(r"catch\s*\(\s*(System\.)?Exception\s*\w*\s*\)"), Severity.NIT,
     Dimension.CORRECTNESS, "Catching every exception can hide real failures; check it is intended."),
    ("TODO/HACK left in code", re.compile(r"//\s*(TODO|HACK|FIXME|XXX)\b", re.I), Severity.NIT,
     Dimension.MAINTAINABILITY, "Unfinished work marker added."),
    ("console output in library code", re.compile(r"\bConsole\.Write(Line)?\("), Severity.NIT,
     Dimension.MAINTAINABILITY, "Library code should not write to the console."),
    ("commented-out code", re.compile(r"^\s*//\s*(var |if\s*\(|return\b|for\s*\(|foreach\s*\(|\w+\s*=\s*[^=]|\w+\(.*\);)"),
     Severity.NIT, Dimension.MAINTAINABILITY, "Commented-out code adds noise; delete it."),
    ("NotImplementedException added", re.compile(r"new\s+NotImplementedException"), Severity.SHOULD_FIX,
     Dimension.CORRECTNESS, "A code path throws NotImplementedException."),
]


def risky_code(pr: PullRequest, policy: Policy) -> Tuple[SensorResult, List[Finding]]:
    findings: List[Finding] = []
    for f in pr.files:
        if not f.path.endswith(".cs"):
            continue
        is_test = policy.is_test(f.path)
        for line, text in _added_with_lines(f):
            for name, pat, sev, dim, claim in _RISKY:
                if is_test and name in ("console output in library code", "catch-all exception"):
                    continue
                if pat.search(text):
                    findings.append(_sensor_finding("risky_code", dim, sev, name.capitalize(), claim, f, line, text))
    return SensorResult(name="risky_code", ran=True, passed=not any(x.severity != Severity.NIT for x in findings),
                        summary=f"{len(findings)} pattern hit(s) in added code"), findings


# ------------------------------------------------------- dotnet build / test
def dotnet_available() -> bool:
    return shutil.which("dotnet") is not None


def _worktree(repo: str, rev: str) -> str:
    d = tempfile.mkdtemp(prefix="ai-reviewer-")
    git(repo, "worktree", "add", "--detach", d, rev)
    return d


def _drop_worktree(repo: str, d: str) -> None:
    git(repo, "worktree", "remove", "--force", d, check=False)
    shutil.rmtree(d, ignore_errors=True)


def _run(cmd: List[str], cwd: str, timeout: int) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {timeout}s"


def _save_log(evidence_dir: str | None, name: str, text: str) -> str:
    if not evidence_dir:
        return ""
    import os
    os.makedirs(evidence_dir, exist_ok=True)
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as fh:
        fh.write(text)
    return f"evidence/{name}"


def dotnet_build_and_test(pr: PullRequest, build: bool, test: bool, target: str | None,
                          test_target: str | None, test_filter: str | None, timeout: int,
                          evidence_dir: str | None = None) -> List[SensorResult]:
    """Build/test the PR head in a temporary git worktree, so the user's checkout is untouched."""
    results: List[SensorResult] = []
    if not (build or test):
        return [SensorResult(name="dotnet_build", ran=False, summary="Build not requested (use --build)"),
                SensorResult(name="dotnet_test", ran=False, summary="Tests not requested (use --test)")]
    if not dotnet_available():
        return [SensorResult(name="dotnet_build", ran=False, summary="dotnet SDK not found on PATH"),
                SensorResult(name="dotnet_test", ran=False, summary="dotnet SDK not found on PATH")]
    wt = _worktree(pr.repo, pr.head)
    try:
        if build:
            cmd = ["dotnet", "build", "-nologo", "-v", "q"] + ([target] if target else [])
            code, out = _run(cmd, wt, timeout)
            tail = out.strip().splitlines()[-25:]
            errs = [l for l in out.splitlines() if ": error " in l][:15]
            results.append(SensorResult(name="dotnet_build", ran=code != -1, passed=code == 0,
                                        summary="Build succeeded" if code == 0 else f"Build failed (exit {code})",
                                        details=errs or tail,
                                        log_file=_save_log(evidence_dir, "dotnet_build.log",
                                                           " ".join(cmd) + "\n\n" + out)))
        else:
            results.append(SensorResult(name="dotnet_build", ran=False, summary="Build not requested"))
        if test:
            cmd = ["dotnet", "test", "-nologo", "-v", "q"] + ([test_target] if test_target else []) + \
                  (["--filter", test_filter] if test_filter else [])
            code, out = _run(cmd, wt, timeout)
            summary_lines = [l.strip() for l in out.splitlines()
                             if re.search(r"(Passed!|Failed!|Total tests|Passed:|Failed:)", l)][:10]
            fails = [l.strip() for l in out.splitlines() if l.strip().startswith("Failed ")][:15]
            results.append(SensorResult(name="dotnet_test", ran=code != -1, passed=code == 0,
                                        summary="Tests passed" if code == 0 else f"Tests failed (exit {code})",
                                        details=(fails + summary_lines) or out.strip().splitlines()[-20:],
                                        log_file=_save_log(evidence_dir, "dotnet_test.log",
                                                           " ".join(cmd) + "\n\n" + out)))
        else:
            results.append(SensorResult(name="dotnet_test", ran=False, summary="Tests not requested"))
    finally:
        _drop_worktree(pr.repo, wt)
    return results


def run_all(pr: PullRequest, policy: Policy, *, offline: bool, build: bool, test: bool,
            target: str | None, test_target: str | None, test_filter: str | None,
            timeout: int, evidence_dir: str | None = None) -> Tuple[List[SensorResult], List[Finding]]:
    _counter["n"] = 0
    results: List[SensorResult] = []
    findings: List[Finding] = []
    for fn in (lambda: secret_scan(pr), lambda: package_check(pr, offline), lambda: test_integrity(pr, policy),
               lambda: removed_guards(pr, policy), lambda: risky_code(pr, policy)):
        r, fs = fn()
        results.append(r)
        findings.extend(fs)
    for r in results:
        body = r.summary + "\n" + "\n".join(r.details) + "\n\n" + "\n".join(
            f"{f.id} {f.title} {f.file}:{f.line_start}\n    {f.evidence}" for f in findings
            if f.source == f"sensor:{r.name.replace('_scan', 's').replace('_check', 's')}" or
            f.source == f"sensor:{r.name}")
        r.log_file = _save_log(evidence_dir, f"{r.name}.txt", body)
    results.extend(dotnet_build_and_test(pr, build, test, target, test_target, test_filter, timeout, evidence_dir))
    return results, findings
