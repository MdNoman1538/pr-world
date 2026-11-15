"""Compare the world before and after a PR, then trace the impact through the COMPLETE head world.

changed   : things whose code lines changed (modified) or that did not exist before (new)
upstream  : who is affected (callers, endpoints, publishers of events the change handles)  — up to 4 hops
downstream: what the change now reaches (callees, tables, events -> subscribers, states)    — up to 4 hops
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Dict, List, Tuple

MEMBER_KINDS = {"method", "ctor", "property", "field", "endpoint", "state", "column"}


def changed_lines(diff_text: str) -> Tuple[Dict[str, List[Tuple[int, int]]], Dict[str, List[Tuple[int, int]]]]:
    """Parse `git diff -U0` -> {file: [(start,end)]} for new side and old side."""
    new, old, cur_new, cur_old = defaultdict(list), defaultdict(list), None, None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            cur_new = None if line.endswith("/dev/null") else line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("--- "):
            cur_old = None if line.endswith("/dev/null") else line[6:] if line.startswith("--- a/") else line[4:]
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not m:
                continue
            os_, oc, ns, nc = int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)
            if cur_new and nc > 0:
                new[cur_new].append((ns, ns + nc - 1))
            if cur_old and oc > 0:
                old[cur_old].append((os_, os_ + oc - 1))
            if cur_new and nc == 0:          # pure deletion: mark the line where it happened
                new[cur_new].append((ns, ns))
    return dict(new), dict(old)


def _overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def diff(before: Dict, after: Dict, diff_text: str, max_hops: int = 4) -> Dict:
    bn = {n["id"]: n for n in before.get("nodes", [])}
    an = {n["id"]: n for n in after.get("nodes", [])}
    new_ranges, _ = changed_lines(diff_text)

    changed: Dict[str, str] = {}
    for nid, n in an.items():
        if n["kind"] in ("module", "layer"):
            continue
        if nid not in bn and n["kind"] not in ("table",):
            changed[nid] = "new"
            continue
        f, l1, l2 = n.get("file"), n.get("line") or 0, n.get("end_line") or 0
        if f in new_ranges and n["kind"] in MEMBER_KINDS | {"type"}:
            if any(_overlap((l1, l2), r) for r in new_ranges[f]):
                changed[nid] = "modified"
    # a type counts as changed only if it is new, or no member explains the change
    for nid, how in list(changed.items()):
        n = an[nid]
        if n["kind"] == "type" and how == "modified":
            if any(changed.get(c["id"]) for c in an.values() if c.get("parent") == nid):
                changed[nid] = "contains"
    removed = [nid for nid, n in bn.items() if nid not in an and n["kind"] not in ("module", "layer")]

    key = lambda e: (e["source"], e["target"], e["kind"])
    bkeys = {key(e) for e in before.get("edges", [])}
    akeys = {key(e) for e in after.get("edges", [])}
    new_edges = [list(k) for k in sorted(akeys - bkeys)]
    removed_edges = [list(k) for k in sorted(bkeys - akeys)]

    # ---------------- impact traversal over the complete head world
    fwd, rev = defaultdict(list), defaultdict(list)
    subs = defaultdict(list)        # event type -> handler methods
    for e in after.get("edges", []):
        s, t, k = e["source"], e["target"], e["kind"]
        if k == "subscribes":
            subs[t].append(s)
        if k in ("calls", "resolves", "routes", "publishes", "triggers", "writes", "reads", "uses"):
            fwd[s].append((t, k))
            if k in ("calls", "resolves", "routes", "uses"):     # code that reads a changed setting depends on it
                rev[t].append((s, k))
    for ev, handlers in subs.items():
        for h in handlers:
            fwd[ev].append((h, "delivers"))
            rev[h].append((ev, "delivers"))
    for e in after.get("edges", []):            # publishers are upstream of the event they publish
        if e["kind"] == "publishes":
            rev[e["target"]].append((e["source"], "publishes"))

    seeds = [nid for nid, how in changed.items() if how in ("new", "modified") and an[nid]["kind"] != "type"]
    seeds += [nid for nid, how in changed.items() if how in ("new", "modified") and an[nid]["kind"] == "type"
              and not any(c.get("parent") == nid for c in an.values())]

    def bfs(graph):
        hop, via, q = {}, {}, deque()
        for s in seeds:
            hop[s] = 0
            q.append(s)
        while q:
            cur = q.popleft()
            if hop[cur] >= max_hops:
                continue
            for nxt, k in graph.get(cur, []):
                if nxt not in hop:
                    hop[nxt] = hop[cur] + 1
                    via[nxt] = [cur, k]
                    q.append(nxt)
        return {k: v for k, v in hop.items() if v > 0}, via

    up, up_via = bfs(rev)
    down, down_via = bfs(fwd)

    hot = set()
    for via in (up_via, down_via):
        for nid, (src, k) in via.items():
            if k == "delivers":
                hot.add((src, nid, "subscribes-delivery"))
            else:
                hot.add((src, nid, k) if via is down_via else (nid, src, k))

    def module_of(nid):
        n = an.get(nid)
        return n["module"] if n else None

    modules = {}
    for nid in list(up) + list(down):
        m = module_of(nid)
        if m:
            modules.setdefault(m, "impacted")
    for nid in changed:
        m = module_of(nid)
        if m:
            modules[m] = "changed"

    tested = set()
    test_nodes = {nid for nid, n in an.items() if (n.get("attrs") or {}).get("is_test")}
    for e in after.get("edges", []):
        if e["kind"] == "calls" and e["source"] in test_nodes:
            tested.add(e["target"])
    # an interface method counts as tested if its implementation is
    for e in after.get("edges", []):
        if e["kind"] == "resolves" and e["target"] in tested:
            tested.add(e["source"])
    untested = [nid for nid, how in changed.items() if how in ("new", "modified") and an[nid]["kind"] in ("method", "ctor")
                and nid not in tested and not (an[nid].get("attrs") or {}).get("is_test")]

    return {
        "changed": changed, "removed_nodes": removed, "new_edges": new_edges, "removed_edges": removed_edges,
        "upstream": up, "downstream": down, "up_via": up_via, "down_via": down_via,
        "hot_edges": [list(h) for h in sorted(hot)], "modules": modules, "untested_changed": untested,
        "changed_lines": {f: r for f, r in new_ranges.items()},
    }
