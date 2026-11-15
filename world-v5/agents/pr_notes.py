"""PR notes and trust per change, for the v3 viewer.

  python agents/pr_notes.py            # AI notes (Gemini, one call per PR) + trust evidence
  python agents/pr_notes.py --no-ai    # facts-only notes + trust evidence (no API calls)
  python agents/pr_notes.py --only PR-3

Reads  viewer/data/index.json, worlds/, diffs/, reviews/   (written by simulate.py)
Writes viewer/data/notes/<PR>.json

Trust (no invented weights):
  unit      = a changed (or affected) method/constructor outside the tests, or a changed setting / default value
  evidence  = verified      : every test that reaches it ran and passed            (rubric E4)
              contradicted  : a test that reaches it failed, or a Critical finding (or a Major one about
                              correctness/security) sits on it                             (rubric E0)
              not_run       : tests reach it but were not run
              none          : no test reaches it; only the reviewer looked          (rubric E1)
  score     = verified / units   -- ISO/IEC 25023 functional-correctness style ratio (X = A/B)
  affected  = same, but a test only counts if it ALSO reaches a changed unit
              (it crosses the link from the change into the affected code)
  roll-up   = counts summed per class / module / PR; "held back by" lists the weakest units.
  confidence= Jeffreys estimate (verified + 1/2) / (units + 1): one number that does not overreact to small PRs
              (1 of 1 -> 75%, not 100%), with its equal-tailed 95% interval as the range
              (Jeffreys interval: recommended for small n by Brown, Cai & DasGupta 2001).
  failures  = only failures NEW in this PR count (compared with the PR's base); a failure is
              "broken test" when the error points into the test's own code (the message names a test class)
              rather than an assertion about the code.
  severity  = the engine's Blocker / ShouldFix / Nit are shown as Critical / Major / Minor
              (= Conventional Comments: blocking / non-blocking issue / nitpick)
  label     = fix    : a Critical finding, or a test now disagrees with the code
              check  : anything open (Major findings, broken tests, untested changes, reviewer asks a human)
              ready  : nothing open and every changed unit verified
  Labelled uncalibrated until checked against PRs with known outcomes (planted bugs).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RUNS, VIEW, load_env, models, say, write_json  # noqa: E402

EXEC = ("method", "ctor")
BAD_SEV = ("Blocker", "ShouldFix")


# ------------------------------------------------------------------ world helpers
class W:
    def __init__(self, w: Dict):
        self.w = w
        self.by = {n["id"]: n for n in w["nodes"]}
        for n in w["nodes"]:
            n["attrs"] = n.get("attrs") or {}
        self.kids = defaultdict(list)
        for n in w["nodes"]:
            self.kids[n.get("parent")].append(n)
        self.fwd = defaultdict(list)
        for e in w["edges"]:
            if e["kind"] in ("calls", "resolves", "uses"):
                self.fwd[e["source"]].append(e["target"])

    def behaviour(self, nid: str) -> bool:
        """a unit we can test: a method/ctor with a body (not an interface member, not a record's generated ctor),
        or a setting / default value (a property or field with an initialiser), e.g. a limit or a default currency"""
        n = self.by.get(nid)
        if n and n["kind"] in ("property", "field") and not self.is_test(n) and n["attrs"].get("initializer") is not None:
            return True
        if not n or n["kind"] not in EXEC or self.is_test(n):
            return False
        p = self.by.get(n.get("parent")) or {}
        tk = (p.get("attrs") or {}).get("type_kind")
        return not (tk == "interface" or (n["kind"] == "ctor" and tk == "record"))

    def is_test(self, n) -> bool:
        return bool(n) and (n.get("module") == "Tests" or n["attrs"].get("is_test"))

    def ancestors(self, nid: str) -> List[str]:
        out, cur = [], (self.by.get(nid) or {}).get("parent")
        while cur and cur in self.by:
            out.append(cur)
            cur = self.by[cur].get("parent")
        return out

    def type_of(self, nid: str) -> Optional[str]:
        for a in [nid] + self.ancestors(nid):
            if self.by[a]["kind"] in ("type", "table"):
                return a
        return None

    def innermost(self, file: str, line: int) -> Optional[str]:
        best = None
        for n in self.w["nodes"]:
            if n.get("file") != file or not n.get("line"):
                continue
            if n["kind"] in ("method", "ctor", "property", "field", "type", "endpoint") and n["line"] <= line <= (n.get("end_line") or n["line"]):
                span = (n.get("end_line") or n["line"]) - n["line"]
                if best is None or span < best[0] or (span == best[0] and n["kind"] != "type"):
                    best = (span, n["id"])
        return best[1] if best else None

    def name(self, nid: str) -> str:
        n = self.by.get(nid)
        if not n:
            return nid
        p = self.by.get(n.get("parent"))
        if n["name"].startswith("<Main>"):
            return "Program startup"
        nm = n["name"] + ("()" if n["kind"] in EXEC else "")
        return f"{p['name']}.{nm}" if p and p["kind"] == "type" and n["kind"] != "type" else nm


# ------------------------------------------------------------------ tests -> nodes
def test_index(w: W) -> Dict[str, List[str]]:
    idx = defaultdict(list)
    for n in w.w["nodes"]:
        if n["kind"] == "method" and w.is_test(n) and n["id"].startswith("M:"):
            idx[n["id"][2:].split("(")[0]].append(n["id"])
    return idx


def failure_cause(message: str, test_classes) -> str:
    m = (message or "").strip()
    if m.startswith("Assert."):
        return "assertion"          # the code gave a different result than the test expects
    if any(c + "." in m for c in test_classes):
        return "broken"             # the error points into the test's own code
    return "crash"                  # an exception: test or code, a human decides


def test_results(w: W, tests: Dict, base_failed: set) -> Dict[str, Dict]:
    """test node id -> outcome: passed | failed (new, counts) | broken (new, test-side) | inherited | not_run"""
    idx = test_index(w)
    classes = {n["name"] for n in w.w["nodes"] if n["kind"] == "type" and w.is_test(n)}
    out: Dict[str, Dict] = {}
    if not tests or not tests.get("ran"):
        for ids in idx.values():
            for t in ids:
                if w.by[t]["attrs"].get("is_test"):
                    out[t] = {"outcome": "not_run", "cases": 0, "failed_cases": 0, "message": "", "cause": None}
        return out
    rank = {"passed": 0, "inherited": 1, "broken": 2, "failed": 3}
    for case in tests.get("tests") or []:
        base = case["name"].split("(")[0]
        for t in idx.get(base, []):
            r = out.setdefault(t, {"outcome": "passed", "cases": 0, "failed_cases": 0, "message": "", "cause": None})
            r["cases"] += 1
            if case.get("outcome") == "Passed":
                continue
            r["failed_cases"] += 1
            msg = (case.get("message") or "").strip()
            if case["name"] in base_failed:
                o, cause = "inherited", "inherited"
            else:
                cause = failure_cause(msg, classes)
                o = "broken" if cause == "broken" else "failed"
            if rank[o] > rank[r["outcome"]]:
                r["outcome"], r["cause"] = o, cause
                r["message"] = " ".join(msg.split())[:220]
    return out


def _betacf(a, b, x):
    # continued fraction for the regularized incomplete beta (Numerical Recipes, betacf)
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-30 else 1e-30
        de = d * c
        h *= de
        if abs(de - 1) < 3e-12:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * _betacf(b, a, 1 - x) / b


def _beta_q(p, a, b):
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _ibeta(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def jeffreys(k: int, n: int):
    """Jeffreys estimate (k+1/2)/(n+1) and its equal-tailed 95% interval (Brown, Cai & DasGupta 2001)."""
    if not n:
        return None, None, None
    a, b = k + 0.5, n - k + 0.5
    lo = 0.0 if k == 0 else _beta_q(0.025, a, b)
    hi = 1.0 if k == n else _beta_q(0.975, a, b)
    return round(a / (n + 1), 3), round(lo, 3), round(hi, 3)


def coverage(w: W, starts: List[str], hops: int = 6) -> Dict[str, set]:
    """non-test node -> set of test ids whose call graph reaches it (calls + interface resolves)."""
    cov = defaultdict(set)
    for t in starts:
        seen, q = {t: 0}, deque([t])
        while q:
            cur = q.popleft()
            if seen[cur] >= hops:
                continue
            for nxt in w.fwd.get(cur, []):
                if nxt not in seen:
                    seen[nxt] = seen[cur] + 1
                    q.append(nxt)
                    if not w.is_test(w.by.get(nxt)):
                        cov[nxt].add(t)
    return cov


# ------------------------------------------------------------------ trust
def contradicting(f) -> bool:
    return f["severity"] == "Blocker" or (f["severity"] == "ShouldFix" and (f.get("dimension") or "") in ("correctness", "security"))


def unit_level(test_ids, results, findings) -> str:
    if any(contradicting(f) for f in findings):
        return "contradicted"
    outs = [results.get(t, {}).get("outcome", "not_run") for t in test_ids]
    if "failed" in outs:
        return "contradicted"
    if "passed" in outs:
        return "verified"
    if "not_run" in outs:
        return "not_run"
    return "none"            # no test, or only broken / inherited ones: no usable evidence


def trust(w: W, diff: Dict, review: Dict, tests: Dict, base_failed: set = frozenset()) -> Dict:
    results = test_results(w, tests, set(base_failed))
    cov = coverage(w, list(results))
    fat = defaultdict(list)
    for f in review.get("findings") or []:
        at = w.innermost(f.get("file"), f.get("line_start") or 0)
        f = {k: f.get(k) for k in ("id", "severity", "title", "file", "line_start", "dimension")}
        if at:
            fat[at].append(f)
    changed = [i for i, how in (diff.get("changed") or {}).items()
               if how in ("new", "modified") and w.behaviour(i)]
    chg_set = set(changed)
    affected = [i for i in list(diff.get("upstream") or {}) + list(diff.get("downstream") or {})
                if w.behaviour(i) and i not in chg_set]
    affected = list(dict.fromkeys(affected))
    crossing = set().union(*[cov.get(c, set()) for c in changed]) if changed else set()

    def tests_view(ids):
        by = lambda o: sorted(t for t in ids if results.get(t, {}).get("outcome") == o)
        ps, fs, bs, ins = by("passed"), by("failed"), by("broken"), by("inherited")
        item = lambda t: {"name": w.by[t]["name"], "message": results[t]["message"], "cases": results[t]["failed_cases"], "cause": results[t]["cause"]}
        return {"passed": [w.by[t]["name"] for t in ps][:12], "passed_n": len(ps),
                "failed": [item(t) for t in fs][:12], "failed_n": len(fs),
                "broken": [item(t) for t in bs][:8], "broken_n": len(bs),
                "inherited": [item(t) for t in ins][:8], "inherited_n": len(ins),
                "not_run_n": len(by("not_run"))}

    units = {}
    for u in changed:
        ids = cov.get(u, set())
        units[u] = {"side": "changed", "level": unit_level(ids, results, fat.get(u, [])), "tests": tests_view(ids),
                    "findings": fat.get(u, []), "how": diff["changed"][u]}
    for u in affected:
        ids = cov.get(u, set()) & crossing
        via = (diff.get("up_via") or {}).get(u) or (diff.get("down_via") or {}).get(u)
        units[u] = {"side": "affected", "level": unit_level(ids, results, fat.get(u, [])), "tests": tests_view(ids),
                    "findings": fat.get(u, []), "via": via,
                    "direction": "depends on the change" if u in (diff.get("upstream") or {}) else "reached by the change",
                    "hops": (diff.get("upstream") or {}).get(u) or (diff.get("downstream") or {}).get(u)}

    rank = {"contradicted": 0, "none": 1, "not_run": 2, "verified": 3}
    roll = defaultdict(lambda: {"changed": None, "affected": None})
    for u, rec in units.items():
        for key in [u] + w.ancestors(u) + ["pr"]:
            side = roll[key]
            s = side[rec["side"]] or {"n": 0, "verified": 0, "contradicted": 0, "not_run": 0, "none": 0, "weakest": []}
            s["n"] += 1
            s[rec["level"]] += 1
            s["weakest"].append([u, rec["level"]])
            side[rec["side"]] = s
    for key, side in roll.items():
        for s in side.values():
            if s:
                s["pct"] = round(100 * s["verified"] / s["n"]) if s["n"] else None
                s["conf"], s["lo"], s["hi"] = jeffreys(s["verified"], s["n"])
                s["weakest"] = [x for x in sorted(s["weakest"], key=lambda x: rank[x[1]]) if x[1] != "verified"][:4]
    return {"units": units, "roll": dict(roll), "tests_ran": bool(tests and tests.get("ran")),
            "findings_at": {k: [f["id"] for f in v] for k, v in fat.items()},
            "_results": results, "_cov": cov, "_fat": fat}


# ------------------------------------------------------------------ verdict: label + reasons
# The reviewer engine's areas (What / Where / Why / How ...) in words a human reviewer acts on
AREA_SAY = {
    "What": "The reviewer is not sure the change does everything the requirement asks. Compare the change with the requirement.",
    "Where": "The change touches a sensitive part of the bank. Check that only the intended places changed.",
    "Why": "The reason for the change is not fully clear from the requirement. Confirm it is wanted.",
    "How": "The reviewer has doubts about how the change is built. Look at the design before signing.",
    "Who": "Check that the right people (roles) can use this, and nobody else.",
}


def trust_level(s: Optional[Dict], label: Optional[str], not_checked: List[str]) -> Optional[Dict]:
    """Low / Medium / High: the same fixed rule as the viewer (model.js trustLevel) and the server (policy.py)."""
    if not s or not s.get("n"):
        return None
    n, v, c, lo, hi = s["n"], s.get("verified", 0), s.get("contradicted", 0), s.get("lo"), s.get("hi")
    if c:
        return {"level": "low", "why": f"{c} changed method(s) contradicted by a failing test or a Critical finding"}
    if label == "fix":
        return {"level": "low", "why": "the PR is labelled Fix before merge"}
    if hi is not None and hi < 0.5:
        return {"level": "low", "why": f"only {v} of {n} changed methods are verified; even the top of the 95% range is below one half"}
    if v >= 0.75 * n and lo is not None and lo >= 0.5 and label == "ready":   # High: at least 3 in 4 verified
        if not_checked:
            return {"level": "medium", "why": f"{v} of {n} changed methods are verified, but not checked: " + ", ".join(not_checked)}
        return {"level": "high", "why": f"{v} of {n} changed methods are verified and nothing contradicts them"}
    return {"level": "medium", "why": f"{v} of {n} changed methods verified" + ("; open items remain" if v == n else "")}


def finding_detail(f: Dict) -> Dict:
    return {k: f.get(k) for k in ("claim", "suggested_fix", "file", "line_start", "evidence", "evidence_verified", "dimension", "severity")}


def human_finding(f: Dict, agree: List[str]) -> str:
    """Fallback wording (the notes agent rewrites it): the consequence first, then what to do."""
    claim = (f.get("claim") or "").strip()
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", claim) if x.strip()]
    # prefer sentences that talk about people or money rather than identifiers
    plain = [x for x in sents if not re.search(r"[A-Za-z]+\.[A-Z][A-Za-z]+|_[a-z]|\(\)", x)] or sents[-1:]
    head = plain[-1] if plain else f.get("title", "")
    tail = " Tests agree." if agree else ""
    ask = " Ask for a fix before merging." if f.get("severity") == "Blocker" else " Decide whether it must be fixed now."
    return (head.rstrip(".") + "." + tail + ask).strip()


def verdict(w: W, pr: Dict, review: Dict, tr: Dict, base_id: Optional[str], wb: Optional[W] = None) -> Dict:
    res, cov = tr["_results"], tr["_cov"]
    cases = [c for c in (pr.get("tests") or {}).get("tests") or [] if c.get("outcome") != "Passed"]
    by_out = defaultdict(list)
    for t, r in res.items():
        by_out[r["outcome"]].append(t)
    failing = set(by_out["failed"])
    reasons = []
    CRIT_DIMS = ("correctness", "safety")   # same fixed rule as the reviewer: only these can be Critical
    for f in review.get("findings") or []:
        if f.get("severity") == "Blocker" and (f.get("dimension") or "correctness") not in CRIT_DIMS:
            f["severity"] = "ShouldFix"
        if f.get("severity") != "Blocker":
            continue
        at = w.innermost(f.get("file"), f.get("line_start") or 0)
        agree = sorted(t for t in cov.get(at, set()) if t in failing) if at else []
        reasons.append({"kind": "critical", "level": "fix", "text": f["title"], "finding": f["id"], "node": at,
                        "detail": f"{len(agree)} failing test(s) reach this code" if agree else "no failing test reaches it",
                        "tests": [w.by[t]["name"] for t in agree][:6], **finding_detail(f),
                        "say": human_finding(f, agree)})
    if failing:
        n_cases = sum(res[t]["failed_cases"] for t in failing)
        msgs = defaultdict(int)
        for t in failing:
            msgs[res[t]["message"][:90]] += 1
        reasons.append({"kind": "tests_fail", "level": "fix", "text": f"{len(failing)} test(s) disagree with this PR's code ({n_cases} case(s)); the code or the test must change",
                        "detail": "; ".join(f"{m} ×{c}" for m, c in sorted(msgs.items(), key=lambda x: -x[1])[:3]),
                        "tests": [w.by[t]["name"] for t in sorted(failing)][:8],
                        "say": f"{len(failing)} test{'s' if len(failing) > 1 else ''} written from the requirement expect different behaviour from the code. "
                               "Decide which is right — the code or the test — before this can merge."})
    for f in review.get("findings") or []:
        if f.get("severity") == "ShouldFix":
            reasons.append({"kind": "major", "level": "check", "text": f["title"], "finding": f["id"],
                            "node": w.innermost(f.get("file"), f.get("line_start") or 0), "detail": f.get("dimension") or "",
                            **finding_detail(f), "say": human_finding(f, [])})
    if by_out["broken"]:
        n_cases = sum(res[t]["failed_cases"] for t in by_out["broken"])
        reasons.append({"kind": "broken", "level": "check", "text": f"{len(by_out['broken'])} test(s) are broken: they crash inside the Test agent's own code ({n_cases} case(s)), so they prove nothing either way",
                        "detail": res[by_out["broken"][0]]["message"][:160], "tests": [w.by[t]["name"] for t in sorted(by_out["broken"])][:8],
                        "say": f"{len(by_out['broken'])} test{'s' if len(by_out['broken']) > 1 else ''} cannot run because the test code itself fails, "
                               "so they tell us nothing about this change. Ask for these tests to be repaired."})
    none = [u for u, r in tr["units"].items() if r["side"] == "changed" and r["level"] in ("none", "not_run")]
    n_changed = sum(1 for r in tr["units"].values() if r["side"] == "changed")
    hi_mods = {m for m in {w.by[u]["module"] for u in none} if ((w.by.get("module:" + m) or {}).get("attrs", {}).get("tier") == "high")}
    # untested changes need a person when they sit in a high-risk module or are more than a quarter of the change
    untested_level = "check" if none and (hi_mods or len(none) > 0.25 * max(1, n_changed)) else "info"
    if none:
        reasons.append({"kind": "untested", "level": untested_level, "text": f"{len(none)} changed method(s) have no usable test evidence",
                        "nodes": none[:6], "detail": ", ".join(w.name(u) for u in none[:4]),
                        "say": f"{len(none)} changed part{'s' if len(none) > 1 else ''} of the code {'are' if len(none) > 1 else 'is'} not covered by any working test. "
                               "Read {} yourself or ask for tests.".format("them" if len(none) > 1 else "it")})
    # requirement check (three blind agents): contradicted items must be fixed; missing / unproven items are checked
    rc = review.get("requirement_check") or {}
    if rc.get("ran") and rc.get("items"):
        bad = [i for i in rc["items"] if i.get("status") == "contradicted"]
        open_ = [i for i in rc["items"] if i.get("status") in ("missing", "partly", "no_evidence")]
        for i in bad:
            pf = next((p for p in i.get("proof") or [] if p.get("grounded")), None)
            reasons.append({"kind": "requirement", "level": "fix", "text": f"Requirement {i['id']} is contradicted: {i['text']}",
                            "detail": i.get("reason") or "", **({"file": pf["file"], "line_start": pf["line"]} if pf else {}),
                            "say": f"The code does the opposite of what the requirement asks: “{i['text']}”. {i.get('reason') or ''}".strip()})
        if open_:
            words = {"missing": "missing", "partly": "partly met", "no_evidence": "without code proof"}
            reasons.append({"kind": "requirement", "level": "check",
                            "text": f"{len(open_)} requirement item(s) not shown as met: " + "; ".join(f"{i['id']} {words[i['status']]}" for i in open_[:6]),
                            "detail": " · ".join(f"{i['id']}: {i['text']}" for i in open_[:6]),
                            "say": f"{len(open_)} part{'s' if len(open_) > 1 else ''} of the requirement {'are' if len(open_) > 1 else 'is'} missing, "
                                   "partly done or without code that proves it. Open Requirement to see each one."})
    nc = [a["area"] for a in review.get("areas") or [] if a.get("status") == "not_checked"]
    if nc:
        reasons.append({"kind": "not_checked", "level": "info", "text": "Not checked at this coverage level: " + ", ".join(nc),
                        "say": "Not checked (switched off by the team's coverage level, or did not run): " + ", ".join(nc)
                               + ". Not counted as passed; trust cannot be High."})
    for a in review.get("areas") or []:
        if a.get("status") in ("human", "failed") and a.get("area") not in ("Tests", "Requirement"):
            reasons.append({"kind": "reviewer", "level": "check", "text": f"Reviewer asks a human to check {a['area']}", "detail": (a.get("reason") or "")[:400],
                            "say": AREA_SAY.get(a["area"], f"The reviewer could not settle '{a['area']}' on its own. Please look at it.")})
    # a default value / setting changed: small in code, possibly big for customers -> a person confirms the business decision
    for u, r in tr["units"].items():
        n = w.by[u]
        if r["side"] != "changed" or n["kind"] not in ("property", "field"):
            continue
        new = n["attrs"].get("initializer")
        old = ((wb.by.get(u) or {}).get("attrs") or {}).get("initializer") if wb else None
        if old is not None and new is not None and old != new:
            reasons.append({"kind": "setting", "level": "check", "node": u, "text": f"{w.name(u)} changes from {old} to {new}",
                            "detail": n["attrs"].get("summary") or "",
                            "say": f"A bank-wide value changes: {n['name']} goes from {old} to {new}. Small in code, but it affects "
                                   f"every customer who uses it. Confirm the business owner approved this."})
    if by_out["inherited"]:
        n_cases = sum(res[t]["failed_cases"] for t in by_out["inherited"])
        reasons.append({"kind": "inherited", "level": "info", "text": f"{n_cases} failing case(s) already failed before this PR{' (in ' + base_id + ')' if base_id else ''}: not counted here",
                        "say": f"{n_cases} failing test case(s) were already failing before this PR{' (in ' + base_id + ')' if base_id else ''}; they are not held against it."})
    if not (pr.get("tests") or {}).get("ran"):
        reasons.append({"kind": "no_tests", "level": "check", "text": "Tests were not run", "say": "The tests were not run, so nothing here is verified yet."})
    mods = sorted({w.by[u]["module"] for u in tr["units"] if tr["units"][u]["side"] == "changed"})
    risky = [(m, (w.by.get("module:" + m) or {}).get("attrs", {}).get("why", "")) for m in mods if ((w.by.get("module:" + m) or {}).get("attrs", {}).get("tier") == "high")]
    label = "fix" if any(r["level"] == "fix" for r in reasons) else "check" if any(r["level"] == "check" for r in reasons) else "ready"
    s = (tr["roll"].get("pr") or {}).get("changed")
    if label == "ready" and (not s or s["verified"] < 0.75 * s["n"]):
        label = "check"     # ready needs tests that verify at least three quarters of the changed methods
    order = {"fix": 0, "check": 1, "info": 2}
    reasons.sort(key=lambda r: order[r["level"]])
    return {"label": label, "reasons": reasons, "risk_areas": [{"module": m, "why": y} for m, y in risky],
            "reviewer_gate": review.get("decision"), "failures": {"new": len(failing), "broken": len(by_out["broken"]), "inherited": len(by_out["inherited"]),
                                                                    "cases_failed": len(cases)}}


# ------------------------------------------------------------------ facts-only notes
def span_text(diff, n) -> str:
    rs = [r for r in (diff.get("changed_lines") or {}).get(n.get("file"), [])
          if r[0] <= (n.get("end_line") or n.get("line") or 0) and r[1] >= (n.get("line") or 0)]
    return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in rs[:4])


def facts_notes(w: W, diff: Dict, tr: Dict) -> Dict[str, Dict]:
    notes: Dict[str, Dict] = defaultdict(dict)
    changed = {i: how for i, how in (diff.get("changed") or {}).items() if i in w.by and how in ("new", "modified")}
    new_calls = defaultdict(list)
    for s, t, k in diff.get("new_edges") or []:
        if k in ("calls", "publishes", "writes", "triggers") and t in w.by and not w.is_test(w.by[t]):
            new_calls[s].append((k, t))
    verb = {"calls": "calls", "publishes": "publishes", "writes": "writes to", "triggers": "moves state to"}
    for i, how in changed.items():
        n = w.by[i]
        if n["kind"] in ("module", "layer") or w.is_test(n):
            continue
        if how == "new":
            txt = f"New {n['attrs'].get('type_kind', n['kind']) if n['kind'] == 'type' else n['kind']}."
        else:
            sp = span_text(diff, n)
            txt = f"Modified{' (lines ' + sp + ')' if sp else ''}."
        nc = new_calls.get(i)
        if nc:
            txt += " Now " + ", ".join(f"{verb[k]} {w.name(t)}" for k, t in nc[:4]) + ("…" if len(nc) > 4 else "") + "."
        notes[i]["changed"] = txt
    # classes and modules: what changed inside
    inside = defaultdict(lambda: {"new": [], "modified": []})
    for i, how in changed.items():
        n = w.by[i]
        if w.is_test(n) or n["kind"] in ("module", "layer"):
            continue
        t = w.type_of(i)
        if t and t != i:
            inside[t][how].append(i)
        mod = "module:" + n["module"]
        if n["kind"] in ("type", "table") or (t is None):
            inside[mod][how].append(i)
        elif t and t not in changed and w.by[t]["kind"] == "type" and i not in inside[mod]["modified"]:
            if t not in inside[mod]["modified"]:
                inside[mod]["modified"].append(t)
    for key, d in inside.items():
        if key.startswith("module:"):
            parts = []
            if d["new"]:
                parts.append(f"{len(d['new'])} new ({', '.join(w.by[x]['name'] for x in d['new'][:4])}{'…' if len(d['new']) > 4 else ''})")
            if d["modified"]:
                parts.append(f"{len(d['modified'])} changed ({', '.join(w.by[x]['name'] for x in d['modified'][:4])}{'…' if len(d['modified']) > 4 else ''})")
            if parts:
                notes[key]["changed"] = "Classes: " + "; ".join(parts) + "."
        else:
            n = w.by[key]
            if changed.get(key) == "new":
                notes[key]["changed"] = f"New {n['attrs'].get('type_kind', 'class')} with {len(d['new'])} member(s)."
            else:
                parts = []
                if d["new"]:
                    parts.append("added " + ", ".join(w.by[x]["name"] for x in d["new"][:5]))
                if d["modified"]:
                    parts.append("modified " + ", ".join(w.by[x]["name"] for x in d["modified"][:5]))
                notes[key]["changed"] = ("; ".join(parts) or "Changed") + "."
    # affected
    agg = defaultdict(list)
    for u, rec in tr["units"].items():
        if rec["side"] != "affected":
            continue
        via = rec.get("via") or [None, ""]
        how = "calls the changed code" if rec["direction"] == "depends on the change" else "is now reached by the changed code"
        notes[u]["affected"] = f"{'Depends on' if rec['direction'] == 'depends on the change' else 'Reached by'} the change through {w.name(via[0]) if via[0] else '?'} ({via[1]}), {rec['hops']} hop(s)."
        for a in w.ancestors(u):
            if w.by[a]["kind"] in ("type", "module"):
                agg[a].append((u, how))
    for key, lst in agg.items():
        ups = sum(1 for _, h in lst if h.startswith("calls"))
        downs = len(lst) - ups
        bits = []
        if ups:
            bits.append(f"{ups} part(s) depend on the change")
        if downs:
            bits.append(f"{downs} part(s) are reached by it")
        names = ", ".join(dict.fromkeys(w.by[u]["name"] for u, _ in lst[:4]))
        notes[key]["affected"] = f"{' and '.join(bits)}: {names}{'…' if len(lst) > 4 else ''}."
    return dict(notes)


# ------------------------------------------------------------------ AI notes
def code_of(world: Dict, n: Dict, limit: int = 45) -> str:
    src = (world.get("files") or {}).get(n.get("file") or "")
    if not src or not n.get("line"):
        return ""
    lines = src.splitlines()[n["line"] - 1:(n.get("end_line") or n["line"])]
    return "\n".join(lines[:limit]) + ("\n…" if len(lines) > limit else "")


def ai_prompt(pr, w: W, wbase: Optional[W], diff, tr) -> (str, List[str], List[str]):
    changed = {i: how for i, how in (diff.get("changed") or {}).items() if i in w.by and how in ("new", "modified")}
    real = {i: h for i, h in changed.items() if not w.is_test(w.by[i])}
    ids_changed, parts = [], []
    budget = 26000
    by_type = defaultdict(list)
    for i in real:
        t = w.type_of(i) or i
        by_type[t].append(i)
    for t, mems in by_type.items():
        tn = w.by[t]
        parts.append(f"\n### {tn['module']} / {tn.get('layer', '')} / {tn['name']}  [{t}]  ({changed.get(t, 'contains changes')})")
        ids_changed.append(t)
        for m in mems:
            if m == t:
                continue
            n = w.by[m]
            ids_changed.append(m)
            if n["kind"] not in EXEC:
                parts.append(f"- [{m}] {n['kind']} {n['attrs'].get('signature', n['name'])} ({real[m]})")
                continue
            after = code_of(w.w, n)
            before = code_of(wbase.w, wbase.by[m]) if wbase and m in wbase.by else ""
            block = f"- [{m}] {n['kind']} ({real[m]})\n  AFTER:\n{after}"
            if before and real[m] == "modified":
                block += f"\n  BEFORE:\n{before}"
            if sum(len(p) for p in parts) + len(block) < budget:
                parts.append(block)
            else:
                parts.append(f"- [{m}] {n['kind']} {n['attrs'].get('signature', n['name'])} ({real[m]})")
    mods = sorted({w.by[i]["module"] for i in real})
    ids_changed += ["module:" + m for m in mods]
    aff_types = defaultdict(list)
    for u, rec in tr["units"].items():
        if rec["side"] == "affected":
            t = w.type_of(u)
            if t:
                aff_types[t].append(u)
    ids_aff = []
    lines = []
    for t, us in list(aff_types.items())[:30]:
        ids_aff.append(t)
        for u in us[:4]:
            via = tr["units"][u].get("via") or [None, ""]
            lines.append(f"- in [{t}] {w.name(u)}: {tr['units'][u]['direction']} via {w.name(via[0]) if via[0] else '?'} ({via[1]})")
    aff_mods = sorted({w.by[t]["module"] for t in aff_types})
    ids_aff += ["module:" + m for m in aff_mods]
    prompt = (f"PULL REQUEST {pr['id']}: {pr['title']}\n\nREQUIREMENT (issue):\n{(pr.get('issue') or '')[:3500]}\n\n"
              f"CHANGED CODE (ids in brackets):\n" + "\n".join(parts) +
              f"\n\nMODULES WITH CHANGES: {', '.join('module:' + m for m in mods)}\n\n"
              f"AFFECTED (not changed, but connected to the change):\n" + "\n".join(lines) +
              f"\nMODULES AFFECTED: {', '.join('module:' + m for m in aff_mods)}\n")
    return prompt, ids_changed, ids_aff


SYSTEM = """You write short review notes for a pull request in a bank's code base, for a human reviewer who travels
through a map of the code (module -> class -> method). Each note is shown next to that element on the map.
Rules:
- Describe ONLY what the code shows. Do not judge whether it is correct: tests and the reviewer do that.
- One or two plain sentences, at most 30 words. Name the behaviour, not the syntax ("Approving now pays out the principal").
- 'changed' notes: what changed in that element. Use only ids from the CHANGED list.
- 'affected' notes: how that element is affected by the change and through what. Use only ids from the AFFECTED list.
- headline: one line, what the PR does. summary: 2-3 sentences.
- business: the effect on customers, staff or money (who notices, what is different for them).
  If nothing user-visible changes, say "No user-visible change (structural)."
- business_impact: none | low | medium | high. A small code change can have a high impact
  (defaults, currency, rounding, limits, fees, permissions, who may approve). Say so when it happens."""


def ai_notes(client, model, prompt, ids_c, ids_a):
    from pydantic import BaseModel

    class Note(BaseModel):
        id: str
        text: str

    class NotesOut(BaseModel):
        headline: str
        summary: str
        business: str
        business_impact: str
        changed: List[Note]
        affected: List[Note]

    res = client.generate(role="pr_notes", model=model, system=SYSTEM, prompt=prompt, schema=NotesOut)
    ok_c, ok_a = set(ids_c), set(ids_a)
    out = {"headline": res.headline, "summary": res.summary, "business": res.business,
           "business_impact": res.business_impact.lower().strip() if res.business_impact.lower().strip() in ("none", "low", "medium", "high") else "unknown",
           "notes": defaultdict(dict), "dropped": 0}
    for nt in res.changed:
        i = nt.id.strip("[] ")
        if i in ok_c:
            out["notes"][i]["changed"] = nt.text.strip()
        else:
            out["dropped"] += 1
    for nt in res.affected:
        i = nt.id.strip("[] ")
        if i in ok_a:
            out["notes"][i]["affected"] = nt.text.strip()
        else:
            out["dropped"] += 1
    return out


FEEDBACK_SYSTEM = """You are a senior code reviewer writing feedback for the HUMAN who will sign a pull request in a bank.
For each numbered item, write one or two plain sentences (max 35 words) that say:
what the problem means for customers, staff or money, and what the human should check or ask for.
Avoid code identifiers unless one is needed to find the place; never write as if to another agent.
Do not add new problems; only rewrite the items given."""


def ai_feedback(client, model, pr: Dict, reasons: List[Dict]):
    from pydantic import BaseModel

    class Item(BaseModel):
        n: int
        text: str

    class FeedbackOut(BaseModel):
        items: List[Item]

    lines = []
    for i, r in enumerate(reasons):
        if r["level"] == "info":
            continue
        lines.append(f"{i}. [{r['kind']}] {r['text']}\n   facts: {(r.get('claim') or r.get('detail') or '')[:600]}")
    if not lines:
        return {}
    prompt = f"PR {pr['id']}: {pr['title']}\nREQUIREMENT:\n{(pr.get('issue') or '')[:1500]}\n\nITEMS:\n" + "\n".join(lines)
    res = client.generate(role="pr_feedback", model=model, system=FEEDBACK_SYSTEM, prompt=prompt, schema=FeedbackOut)
    return {it.n: it.text.strip() for it in res.items if 0 <= it.n < len(reasons)}


# ------------------------------------------------------------------ main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-ai", action="store_true", help="facts-only notes, no model calls")
    p.add_argument("--only", help="comma list, e.g. PR-3")
    a = p.parse_args()
    idx = json.loads((VIEW / "index.json").read_text())
    (VIEW / "notes").mkdir(exist_ok=True)
    client, model = None, None
    if not a.no_ai:
        load_env()
        from reviewer.llm import make_client
        client = make_client(None, str(RUNS / "agent_log.jsonl"), 0.2)
        model = models()["meaning"]
    cache_p = RUNS / "notes_cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    only = set(a.only.split(",")) if a.only else None
    worlds: Dict[str, W] = {}

    def world(sha):
        if sha not in worlds:
            f = VIEW / "worlds" / f"{sha}.json"
            worlds[sha] = W(json.loads(f.read_text())) if f.exists() else None
        return worlds[sha]

    for pr in idx["prs"]:
        if only and pr["id"] not in only:
            continue
        w = world(pr["head"])
        if not w:
            say(f"{pr['id']}: no world for {pr['head'][:8]}, skipped")
            continue
        diff = json.loads((VIEW / "diffs" / f"{pr['id']}.json").read_text())
        rv = VIEW / "reviews" / f"{pr['id']}.json"
        review = json.loads(rv.read_text()) if rv.exists() else {"findings": []}
        basepr = next((q for q in idx["prs"] if q["merged"] == pr["base"]), None)
        base_failed = {c["name"] for c in ((basepr or {}).get("tests") or {}).get("tests") or [] if c.get("outcome") != "Passed"}
        tr = trust(w, diff, review, pr.get("tests") or {}, base_failed)
        vd = verdict(w, pr, review, tr, basepr["id"] if basepr else None, world(pr["base"]))
        for k in ("_results", "_cov", "_fat"):
            tr.pop(k, None)
        notes = facts_notes(w, diff, tr)
        fl = [{k: f.get(k) for k in ("id", "severity", "title", "dimension")} for f in review.get("findings") or []]
        out = {"pr": pr["id"], "findings": fl, "source": "facts", "model": None, "headline": pr["title"], "summary": "", "business": "",
               "business_impact": "unknown", "notes": notes, "verdict": vd, **tr}
        if client:
            prompt, ids_c, ids_a = ai_prompt(pr, w, world(pr["base"]), diff, tr)
            key = hashlib.sha256((model + SYSTEM + prompt).encode()).hexdigest()
            try:
                if key not in cache:
                    say(f"{pr['id']}: writing notes ({len(ids_c)} changed, {len(ids_a)} affected elements)")
                    r = ai_notes(client, model, prompt, ids_c, ids_a)
                    r["notes"] = dict(r["notes"])
                    cache[key] = r
                    write_json(cache_p, cache)
                r = cache[key]
                for i, d in r["notes"].items():
                    notes.setdefault(i, {})
                    for side, txt in d.items():
                        notes[i][side + "_facts"] = notes[i].get(side)
                        notes[i][side] = txt
                        notes[i][side + "_src"] = "ai"
                out.update({"source": "ai", "model": model, "headline": r["headline"], "summary": r["summary"],
                            "business": r["business"], "business_impact": r["business_impact"], "notes": notes})
                if r.get("dropped"):
                    say(f"   dropped {r['dropped']} note(s) that named ids outside the PR")
            except Exception as ex:
                say(f"{pr['id']}: AI notes failed ({str(ex)[:160]}); facts-only notes kept")
        if out.get("business_impact") == "high" and not any(r["kind"] == "setting" for r in vd["reasons"]):
            vd["reasons"].insert(0 if vd["label"] != "fix" else len([r for r in vd["reasons"] if r["level"] == "fix"]),
                                 {"kind": "business", "level": "check", "text": "High business impact",
                                  "detail": out.get("business") or "",
                                  "say": "This change has a high impact on customers or money: " + (out.get("business") or "").rstrip(".") +
                                         ". Confirm the business owner agrees."})
            if vd["label"] == "ready":
                vd["label"] = "check"
        if client:
            fprompt = json.dumps([[r["kind"], r["text"], (r.get("claim") or r.get("detail") or "")[:600]] for r in vd["reasons"]])
            fkey = hashlib.sha256((model + FEEDBACK_SYSTEM + pr["id"] + fprompt).encode()).hexdigest()
            try:
                if fkey not in cache:
                    cache[fkey] = {str(k): v for k, v in ai_feedback(client, model, pr, vd["reasons"]).items()}
                    write_json(cache_p, cache)
                for k, txt in cache[fkey].items():
                    vd["reasons"][int(k)]["say_facts"] = vd["reasons"][int(k)].get("say")
                    vd["reasons"][int(k)]["say"] = txt
                    vd["reasons"][int(k)]["say_src"] = "ai"
            except Exception as ex:
                say(f"{pr['id']}: AI feedback wording failed ({str(ex)[:120]}); plain wording kept")
        s = (tr["roll"].get("pr") or {}).get("changed") or {}
        s_ = (tr["roll"].get("pr") or {}).get("changed")
        out["trust"] = trust_level(s_, vd["label"], [a["area"] for a in review.get("areas") or [] if a.get("status") == "not_checked"])
        write_json(VIEW / "notes" / f"{pr['id']}.json", out)
        say(f"{pr['id']}: {vd['label'].upper():5}  notes={out['source']}  verified {s.get('verified', 0)}/{s.get('n', 0)} "
            f"confidence {s.get('conf')} (95% {s.get('lo')}-{s.get('hi')}), contradicted {s.get('contradicted', 0)}  |  new failures {vd['failures']['new']}, "
            f"broken {vd['failures']['broken']}, inherited {vd['failures']['inherited']}")


if __name__ == "__main__":
    main()
