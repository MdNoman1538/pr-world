"""Export the "world" graph for the dashboard (Zone A: architecture and call-graph map).

World vocabulary (from our concept):
  country = business/policy area   city = file   member = changed method/property
  road    = call between files     fog  = changed member with no test references
  pin     = changed file           heat = churn (how often the file changed in history)

Everything here comes from code facts (git, the rulebook, the context builder). The model draws no roads.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .context import PRContext
from .git_tools import PullRequest, churn, list_files
from .models import Finding, Severity
from .policy import Policy


def _area(policy: Policy, path: str) -> Dict:
    a = policy.area_for(path)
    if a:
        return {"name": a.get("name", "?"), "tier": a.get("tier", "medium"), "guarded": bool(a.get("guarded")),
                "why": a.get("why", "")}
    if policy.is_test(path):
        return {"name": "Tests", "tier": "low", "guarded": False, "why": "test code"}
    if policy.is_docs(path):
        return {"name": "Docs", "tier": "low", "guarded": False, "why": "documentation"}
    return {"name": "Unmapped", "tier": policy.raw.get("default_tier", "medium"), "guarded": False,
            "why": "no area in the rulebook"}


def build_graph(pr: PullRequest, policy: Policy, ctx: PRContext, findings: List[Finding],
                max_repo_files: int = 20000) -> Dict:
    changed = {f.path: f for f in pr.files}
    # every country of the world, sized by its file count at head
    countries: Dict[str, Dict] = {}
    for path in list_files(pr.repo, pr.head)[:max_repo_files]:
        if not path.endswith((".cs", ".csproj", ".props", ".targets")) and path not in changed:
            continue
        a = _area(policy, path)
        c = countries.setdefault(a["name"], {**a, "id": a["name"], "files": 0, "touched": False, "changed": 0})
        c["files"] += 1

    cities: Dict[str, Dict] = {}

    def city(path: str, role: str) -> Dict:
        if path not in cities:
            a = _area(policy, path)
            countries.setdefault(a["name"], {**a, "id": a["name"], "files": 0, "touched": False, "changed": 0})
            cities[path] = {"id": path, "name": path.split("/")[-1], "path": path, "country": a["name"],
                            "tier": a["tier"], "role": role, "changed": path in changed,
                            "n_added": changed[path].n_added if path in changed else 0,
                            "n_removed": changed[path].n_removed if path in changed else 0,
                            "status": changed[path].status if path in changed else "",
                            "churn": churn(pr.repo, pr.head, path), "members": [], "findings": {},
                            "is_test": policy.is_test(path), "hop": 0 if path in changed else 1}
        return cities[path]

    for p in changed:
        city(p, "changed")
    edges: Dict[tuple, Dict] = {}
    for im in ctx.impact:
        target = city(im.file, "changed")
        target["members"].append({"name": im.member, "callers": len(im.callers), "tests": len(im.test_refs),
                                  "untested": bool(im.callers) and not im.test_refs})
        for c in im.callers:
            src_path, _, line = c.partition(":")
            if src_path == im.file:
                continue
            src = city(src_path, "test" if policy.is_test(src_path) else "caller")
            key = (src_path, im.file)
            e = edges.setdefault(key, {"source": src_path, "target": im.file, "calls": 0, "members": [],
                                       "kind": "test" if src["is_test"] else "call"})
            e["calls"] += 1
            if im.member not in e["members"]:
                e["members"].append(im.member)
    # status of each road: fog when the member it carries has no tests
    untested_members = {(im.file, im.member) for im in ctx.impact if im.callers and not im.test_refs}
    for (src, dst), e in edges.items():
        e["fog"] = e["kind"] == "call" and any((dst, m) in untested_members for m in e["members"])
        e["guarded_crossing"] = cities[src]["country"] != cities[dst]["country"] and (
            countries[cities[dst]["country"]].get("guarded") or countries[cities[src]["country"]].get("guarded"))

    for f in findings:
        if f.file in cities:
            sev = f.severity.value
            cities[f.file]["findings"][sev] = cities[f.file]["findings"].get(sev, 0) + 1
    for c in cities.values():
        countries[c["country"]]["touched"] = True
        if c["changed"]:
            countries[c["country"]]["changed"] += 1

    # country-level roads aggregated from city roads
    croads: Dict[tuple, Dict] = defaultdict(lambda: {"calls": 0, "fog": False, "guarded_crossing": False})
    for e in edges.values():
        a, b = cities[e["source"]]["country"], cities[e["target"]]["country"]
        if a == b:
            continue
        r = croads[(a, b)]
        r.update(source=a, target=b)
        r["calls"] += e["calls"]
        r["fog"] |= e["fog"]
        r["guarded_crossing"] |= bool(e["guarded_crossing"])
    return {"countries": sorted(countries.values(), key=lambda c: (-int(c["touched"]), c["name"])),
            "cities": list(cities.values()), "roads": list(edges.values()), "country_roads": list(croads.values())}
