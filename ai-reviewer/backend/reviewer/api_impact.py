"""API impact: which APIs (methods, properties, constructors) the PR changed, how, and who is affected.

For every changed member:
  - change type: new | signature (contract changed) | body (same contract, new behaviour) | removed
  - visibility (public / protected / internal / private) → breaking = contract change on a public/protected API
  - signature before and after
  - call flow: direct callers (hop 1) and their callers (hop 2), each resolved to "File::Member",
    with its rulebook area and whether any test reaches it
All facts come from git and code parsing (name-based "code graph lite"); no model is involved.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .context import PRContext, Span, member_spans
from .git_tools import PullRequest, file_at, grep
from .policy import Policy

_VIS = ("public", "protected", "internal", "private")


def _signature(lines: List[str], span: Span) -> str:
    out = []
    for i in range(span.start - 1, min(len(lines), span.start + 5)):
        l = lines[i].strip()
        if l.startswith("[") and l.endswith("]") and not out:   # attribute line
            continue
        out.append(l)
        if "{" in l or "=>" in l or l.endswith(";"):
            break
    sig = " ".join(out)
    sig = re.split(r"\s*(\{|=>)", sig)[0].strip()
    return re.sub(r"\s+", " ", sig)


def _visibility(sig: str) -> str:
    for v in _VIS:
        if re.search(rf"\b{v}\b", sig):
            return "protected" if v == "protected" else v
    return "private"


_MODS = {"public", "private", "protected", "internal", "static", "virtual", "override", "abstract", "sealed",
         "async", "unsafe", "extern", "new", "readonly", "partial", "ref"}


def _kind(sig: str, name: str) -> str:
    m = re.search(rf"\b{re.escape(name)}\s*(<[^>]*>)?\s*\(", sig)
    if not m:
        return "property"
    before = [w for w in re.sub(r"\[[^\]]*\]", " ", sig[:m.start()]).split() if w not in _MODS]
    return "method" if before else "constructor"


class _Files:
    def __init__(self, repo: str):
        self.repo = repo
        self.cache: Dict[Tuple[str, str], Tuple[List[str], List[Span]]] = {}

    def get(self, rev: str, path: str) -> Tuple[List[str], List[Span]]:
        key = (rev, path)
        if key not in self.cache:
            text = file_at(self.repo, rev, path) or ""
            spans = member_spans(text)[0] if path.endswith(".cs") else []
            self.cache[key] = (text.splitlines(), spans)
        return self.cache[key]


def _enclosing(spans: List[Span], line: int) -> Optional[Span]:
    c = [s for s in spans if s.kind == "member" and s.start <= line <= s.end]
    return min(c, key=lambda s: s.end - s.start) if c else None


def build_api_impact(pr: PullRequest, policy: Policy, ctx: PRContext, max_apis: int = 30,
                     max_callers: int = 15, max_hop2: int = 8) -> Dict:
    files = _Files(pr.repo)
    nodes: Dict[str, Dict] = {}
    edges: Dict[Tuple[str, str], Dict] = {}
    grep_cache: Dict[str, List[str]] = {}

    def area(path: str) -> Tuple[str, str]:
        a = policy.area_for(path)
        if a:
            return a.get("name", "?"), a.get("tier", "medium")
        if policy.is_test(path):
            return "Tests", "low"
        return "Unmapped", policy.raw.get("default_tier", "medium")

    def node(path: str, member: str, hop: int) -> str:
        nid = f"{path}::{member}"
        if nid not in nodes:
            an, tier = area(path)
            nodes[nid] = {"id": nid, "member": member, "file": path, "area": an, "tier": tier,
                          "is_test": policy.is_test(path), "hop": hop, "tested": False}
        else:
            nodes[nid]["hop"] = min(nodes[nid]["hop"], hop)
        return nid

    def edge(src: str, dst: str, where: str) -> None:
        e = edges.setdefault((src, dst), {"source": src, "target": dst, "count": 0, "lines": []})
        e["count"] += 1
        if len(e["lines"]) < 5:
            e["lines"].append(where)

    def callers_of(member: str) -> List[str]:
        if member not in grep_cache:
            grep_cache[member] = grep(pr.repo, pr.head, rf"\b{re.escape(member)}\s*(<[^>]*>)?\s*\(", 400)
        return grep_cache[member]

    def resolve(row: str) -> Optional[Tuple[str, str, int]]:
        parts = row.split(":", 2)
        if len(parts) < 2 or not parts[1].isdigit():
            return None
        path, line = parts[0], int(parts[1])
        lines, spans = files.get(pr.head, path)
        sp = _enclosing(spans, line)
        return (path, sp.name if sp else "(top level)", line)

    apis: List[Dict] = []
    changed_by_file = {f.path: f for f in pr.files}
    test_members: List[Dict] = []
    for im in ctx.impact:
        if len(apis) >= max_apis:
            break
        f = changed_by_file.get(im.file)
        if policy.is_test(im.file):     # test code is evidence, not an API: list it separately
            test_members.append({"name": im.member, "file": im.file, "new": bool(f and f.status == "A")})
            continue
        h_lines, h_spans = files.get(pr.head, im.file)
        added = set(f.added_line_numbers) if f else set()
        cands = [s for s in h_spans if s.kind == "member" and s.name == im.member]
        span = next((s for s in cands if any(s.start <= l <= s.end for l in added)), cands[0] if cands else None)
        if span is None:
            continue
        sig_after = _signature(h_lines, span)
        old_path = (f.old_path if f and f.old_path else im.file)
        b_lines, b_spans = files.get(pr.merge_base, old_path) if f and f.status != "A" else ([], [])
        b_cands = [s for s in b_spans if s.kind == "member" and s.name == im.member]
        b_sigs = [_signature(b_lines, s) for s in b_cands]
        if not b_cands:
            change, sig_before = "new", ""
        elif sig_after in b_sigs:
            change, sig_before = "body", sig_after
        else:
            change, sig_before = "signature", b_sigs[0]
        vis = _visibility(sig_after)
        api_id = node(im.file, im.member, 0)
        nodes[api_id]["api"] = True

        hop1_ids: List[str] = []
        tests: List[str] = []
        for row in callers_of(im.member):
            r = resolve(row)
            if not r:
                continue
            path, member, line = r
            if path == im.file and span.start <= line <= span.end:
                continue                                   # the definition itself / recursion
            if any(s.name == im.member and s.start == line for s in files.get(pr.head, path)[1]):
                continue                                   # another definition with the same name
            nid = node(path, member, 1)
            edge(nid, api_id, f"{path}:{line}")
            if nodes[nid]["is_test"]:
                tests.append(nid)
            elif nid not in hop1_ids:
                hop1_ids.append(nid)
        nodes[api_id]["tested"] = bool(tests)

        for nid in hop1_ids[:max_callers]:
            member = nodes[nid]["member"]
            if member == "(top level)":
                continue
            reached_by_test = False
            n2 = 0
            for row in callers_of(member):
                r = resolve(row)
                if not r:
                    continue
                path, m2, line = r
                if f"{path}::{m2}" == nid:
                    continue
                if any(s.name == member and s.start == line for s in files.get(pr.head, path)[1]):
                    continue
                if policy.is_test(path):
                    reached_by_test = True
                if n2 >= max_hop2:
                    continue
                n2 += 1
                nid2 = node(path, m2, 2)
                edge(nid2, nid, f"{path}:{line}")
                if nodes[nid2]["is_test"]:
                    reached_by_test = True
            nodes[nid]["tested"] = reached_by_test

        untested = [n for n in hop1_ids if not nodes[n]["tested"]]
        areas = sorted({nodes[n]["area"] for n in hop1_ids})
        apis.append({
            "id": api_id, "name": im.member, "file": im.file, "line": span.start, "area": nodes[api_id]["area"],
            "tier": nodes[api_id]["tier"], "visibility": vis, "kind": _kind(sig_after, im.member), "change": change,
            "breaking": change in ("signature",) and vis in ("public", "protected") and not policy.is_test(im.file),
            "sig_before": sig_before, "sig_after": sig_after, "callers": hop1_ids, "tests": tests,
            "untested_callers": untested, "caller_areas": areas, "more_callers": max(0, len(hop1_ids) - max_callers)})

    # members that existed before and are gone now (removed APIs)
    for f in pr.files:
        if not f.path.endswith(".cs") or f.status == "A" or policy.is_test(f.path):
            continue
        b_lines, b_spans = files.get(pr.merge_base, f.old_path or f.path)
        h_names = {s.name for s in files.get(pr.head, f.path)[1]} if f.status != "D" else set()
        for s in b_spans:
            if s.kind != "member" or s.name in h_names or any(a["name"] == s.name and a["file"] == f.path for a in apis):
                continue
            sig = _signature(b_lines, s)
            vis = _visibility(sig)
            api_id = node(f.path, s.name, 0)
            nodes[api_id]["api"] = True
            hop1 = []
            for row in callers_of(s.name):
                r = resolve(row)
                if r:
                    nid = node(r[0], r[1], 1)
                    edge(nid, api_id, f"{r[0]}:{r[2]}")
                    hop1.append(nid)
            apis.append({"id": api_id, "name": s.name, "file": f.path, "line": s.start, "area": nodes[api_id]["area"],
                         "tier": nodes[api_id]["tier"], "visibility": vis, "kind": _kind(sig, s.name), "change": "removed",
                         "breaking": vis in ("public", "protected") and not policy.is_test(f.path),
                         "sig_before": sig, "sig_after": "",
                         "callers": hop1, "tests": [], "untested_callers": hop1, "caller_areas":
                             sorted({nodes[n]["area"] for n in hop1}), "more_callers": 0})
            if len(apis) >= max_apis + 10:
                break

    order = {"removed": 0, "signature": 1, "new": 3, "body": 2}
    apis.sort(key=lambda a: (not a["breaking"], order.get(a["change"], 9), -len(a["callers"])))
    return {"apis": apis, "nodes": nodes, "edges": list(edges.values()), "test_members": test_members,
            "method": "name-based caller search at the PR head (code-graph lite); overloads and reflection are not "
                      "distinguished",
            "summary": {"apis": len(apis), "breaking": sum(1 for a in apis if a["breaking"]),
                        "signature": sum(1 for a in apis if a["change"] == "signature"),
                        "removed": sum(1 for a in apis if a["change"] == "removed"),
                        "new": sum(1 for a in apis if a["change"] == "new"),
                        "body": sum(1 for a in apis if a["change"] == "body"),
                        "untested_callers": len({n for a in apis for n in a["untested_callers"]})}}
