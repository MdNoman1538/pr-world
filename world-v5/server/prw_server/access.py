"""Per-user data: the server cuts every data file down to what one user may see (E2, E4, E7).

Rule: a module the user can Read (or more) is sent in full. A locked module (Overview only) keeps its block,
its name (or "Restricted module N" when names are hidden) and its risk colour, and the fact that it changed or is
affected. Everything inside it is removed: classes, methods, code, routes, flows, finding text, quoted code, notes.
Links into a locked module end at its block. Text written by the AI is cleaned of the locked names and file paths.
"""
import glob
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from .store import RANK

REDACTED = "[restricted]"


class Data:
    """Reads the viewer data folder once per file change and keeps the node -> module map."""

    def __init__(self, folder: str):
        self.folder = os.path.abspath(folder)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._map_key = None
        self.node_module: Dict[str, str] = {}
        self.node_name: Dict[str, str] = {}
        self.file_module: Dict[str, str] = {}
        self.module_tier: Dict[str, str] = {}

    def path(self, rel: str) -> Optional[str]:
        rel = os.path.normpath(rel).lstrip("/\\")
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        p = os.path.join(self.folder, rel)
        return p if os.path.isfile(p) and os.path.abspath(p).startswith(self.folder + os.sep) else None

    def load(self, rel: str) -> Optional[Any]:
        p = self.path(rel)
        if not p:
            return None
        m = os.path.getmtime(p)
        with self._lock:
            hit = self._cache.get(p)
            if hit and hit[0] == m:
                return hit[1]
        with open(p, encoding="utf-8") as fh:
            v = json.load(fh)
        with self._lock:
            self._cache[p] = (m, v)
        return v

    def refresh_map(self) -> None:
        files = sorted(glob.glob(os.path.join(self.folder, "worlds", "*.json")))
        key = tuple((f, os.path.getmtime(f)) for f in files)
        if key == self._map_key:
            return
        nm, nn, fm, tier = {}, {}, {}, {}
        for f in files:
            w = self.load(os.path.relpath(f, self.folder)) or {}
            for n in w.get("nodes", []):
                mod = n.get("module") or ""
                nm[n["id"]] = mod
                nn[n["id"]] = n.get("name") or ""
                if n.get("file"):
                    fm[n["file"]] = mod
                if n.get("kind") == "module":
                    tier[mod] = (n.get("attrs") or {}).get("tier", "")
        self.node_module, self.node_name, self.file_module, self.module_tier = nm, nn, fm, tier
        self._map_key = key

    def modules(self) -> List[str]:
        self.refresh_map()
        return sorted(m for m in set(self.node_module.values()) if m)

    def module_of_file(self, path: str) -> str:
        self.refresh_map()
        if path in self.file_module:
            return self.file_module[path]
        m = re.search(r"/Modules/([A-Za-z0-9_]+)/", "/" + (path or ""))
        if m:
            return m.group(1)
        return ""


class View:
    """What one user may see. levels: module -> overview/read/review/sign."""

    def __init__(self, data: Data, levels: Dict[str, str], hide_all_names: bool = False, hidden_names: Optional[List[str]] = None,
                 star_level: str = "overview"):
        self.data = data
        data.refresh_map()
        self.levels = levels
        self.star = star_level
        mods = data.modules()
        self.locked: Set[str] = {m for m in mods if RANK.get(self.level(m), 0) < RANK["read"]}
        hidden = set(hidden_names or [])
        self.alias: Dict[str, str] = {}
        n = 0
        for m in sorted(self.locked):
            if hide_all_names or m in hidden:
                n += 1
                self.alias[m] = f"Restricted module {n}"
        self._scrub = self._build_scrub()

    # ------------------------------------------------------------------ basics
    def level(self, module: str) -> str:
        return self.levels.get(module) or self.star

    def can(self, module: str, level: str) -> bool:
        return RANK.get(self.level(module), 0) >= RANK[level]

    def mod_of(self, node_id: str) -> str:
        m = self.data.node_module.get(node_id)
        if m is None:
            if node_id.startswith("module:"):
                return node_id[len("module:"):]
            return ""   # unknown node: treated as locked below unless the user can read every module
        return m

    def node_locked(self, node_id: str) -> bool:
        m = self.mod_of(node_id)
        if not m:
            return RANK.get(self.star, 0) < RANK["read"]
        return m in self.locked

    def file_locked(self, path: str) -> bool:
        if not path:
            return False
        m = self.data.module_of_file(path)
        if not m:
            return RANK.get(self.star, 0) < RANK["read"]
        return m in self.locked

    def mname(self, module: str) -> str:
        return self.alias.get(module, module)

    def mid(self, module: str) -> str:
        return "module:" + self.mname(module)

    def map_id(self, node_id: str) -> str:
        """Readable node -> itself; node in a locked module -> that module's block."""
        if not self.node_locked(node_id):
            return node_id
        m = self.mod_of(node_id)
        return self.mid(m) if m else "module:~unknown"

    @property
    def cut(self) -> bool:
        return bool(self.locked)

    # ------------------------------------------------------------------ text cleaning (E7 safe version)
    def _build_scrub(self):
        if not self.locked:
            return None
        readable_names = {nm for nid, nm in self.data.node_name.items() if not self.node_locked(nid)}
        words: Set[str] = set()
        for nid, nm in self.data.node_name.items():
            nm = (nm or "").split("(")[0]
            # only code-like names (LoanService, GetForCurrentUserAsync, ILedger, fee_cap2): plain words such as
            # "Loan" or "Apply" are business words and stay readable
            code_like = bool(re.search(r"[a-z][A-Z]|^I[A-Z][a-z]|[_0-9]", nm))
            if self.node_locked(nid) and len(nm) >= 4 and code_like and nm not in readable_names and not nm.startswith("module"):
                words.add(nm)
        paths = {f for f, m in self.data.file_module.items() if m in self.locked}
        alt = sorted(paths, key=len, reverse=True) + sorted(words, key=len, reverse=True)
        pats = []
        if alt:
            pats.append((re.compile("|".join(r"(?<![\w/.])" + re.escape(a) + r"(?![\w])" for a in alt)), REDACTED))
        for m, a in self.alias.items():
            pats.append((re.compile(r"(?<![\w])" + re.escape(m) + r"(?![\w])"), a))
            pats.append((re.compile(r"Bank\.Modules\." + re.escape(m) + r"[\w.]*"), REDACTED))
        for m in self.locked - set(self.alias):
            pats.append((re.compile(r"Bank\.Modules\." + re.escape(m) + r"\.[\w.]+"), f"Bank.Modules.{m}.{REDACTED}"))
        return pats

    def scrub(self, s: Any) -> Any:
        if not self._scrub or not isinstance(s, str) or not s:
            return s
        for rx, rep in self._scrub:
            s = rx.sub(rep, s)
        return s

    def scrub_all(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.scrub(obj)
        if isinstance(obj, list):
            return [self.scrub_all(v) for v in obj]
        if isinstance(obj, dict):
            return {k: self.scrub_all(v) for k, v in obj.items()}
        return obj

    # ------------------------------------------------------------------ world map
    def world(self, w: Dict) -> Dict:
        if not self.cut:
            return w
        out = {k: v for k, v in w.items() if k not in ("nodes", "edges", "flows", "dataflow", "files", "constitutions")}
        nodes = []
        size: Dict[str, int] = {}
        for n in w.get("nodes", []):
            if n.get("kind") in ("type", "table", "method", "ctor", "property", "field", "endpoint", "state", "column"):
                size[n.get("module") or ""] = size.get(n.get("module") or "", 0) + 1
        for n in w.get("nodes", []):
            m = n.get("module") or ""
            if not self.node_locked(n["id"]):
                nodes.append(n)
            elif n.get("kind") == "module":
                attrs = n.get("attrs") or {}
                nodes.append({"id": self.mid(m), "kind": "module", "name": self.mname(m), "parent": None, "module": self.mname(m),
                              "layer": None, "file": None, "line": 0, "end_line": 0,
                              "attrs": {"tier": attrs.get("tier"), "locked": True, "level": self.level(m), "size": size.get(m, 0),
                                        **({} if m in self.alias else {"area": attrs.get("area")})}})
        out["nodes"] = nodes
        out["edges"] = self.edges(w.get("edges", []))
        out["flows"] = {k: v for k, v in (w.get("flows") or {}).items() if not self.node_locked(k)}
        out["dataflow"] = {k: v for k, v in (w.get("dataflow") or {}).items() if not self.node_locked(k)}
        out["files"] = {k: v for k, v in (w.get("files") or {}).items() if not self.file_locked(k)}
        out["constitutions"] = {k: v for k, v in (w.get("constitutions") or {}).items() if k not in self.locked}
        out["stats"] = self.scrub_all(w.get("stats") or {})
        out["cut"] = self.cut_info()
        return out

    def edges(self, edges: List[Dict]) -> List[Dict]:
        seen: Dict[Tuple[str, str, str], Dict] = {}
        for e in edges:
            s, t = self.map_id(e["source"]), self.map_id(e["target"])
            if s == t and (s != e["source"] or t != e["target"]):
                continue                      # inside one locked module: not shown
            if s == e["source"] and t == e["target"]:
                seen[(s, t, e["kind"], e.get("file"), e.get("line"))] = e
                continue
            key = (s, t, e["kind"], None, None)
            if key in seen:
                seen[key]["count"] = seen[key].get("count", 1) + e.get("count", 1)
            else:
                seen[key] = {"source": s, "target": t, "kind": e["kind"], "certainty": e.get("certainty"),
                             "count": e.get("count", 1), "into_locked": True}
        return list(seen.values())

    def triples(self, rows: List) -> List:
        out, seen = [], set()
        for r in rows or []:
            s, t = self.map_id(r[0]), self.map_id(r[1])
            if s == t and (s != r[0] or t != r[1]):
                continue
            k = (s, t, r[2] if len(r) > 2 else "")
            if k not in seen:
                seen.add(k)
                out.append([s, t] + list(r[2:]))
        return out

    def cut_info(self) -> Dict:
        return {"locked_modules": sorted(self.mname(m) for m in self.locked),
                "note": "Parts of the bank you cannot open are shown as closed blocks. Ask the module owner for access."}

    # ------------------------------------------------------------------ PR diff
    def diff(self, d: Dict) -> Dict:
        if not self.cut or not d:
            return d
        out = dict(d)
        changed, locked_count = {}, {}
        for k, v in (d.get("changed") or {}).items():
            if self.node_locked(k):
                m = self.mid(self.mod_of(k)) if self.mod_of(k) else "module:~unknown"
                changed.setdefault(m, "contains")
                locked_count[m] = locked_count.get(m, 0) + 1
            else:
                changed[k] = v
        out["changed"] = changed
        out["removed_nodes"] = [x for x in d.get("removed_nodes", []) if not self.node_locked(x if isinstance(x, str) else x.get("id", ""))]
        for key in ("new_edges", "removed_edges", "hot_edges"):
            out[key] = self.triples(d.get(key))
        for key in ("upstream", "downstream"):
            mm = {}
            for k, v in (d.get(key) or {}).items():
                mk = self.map_id(k)
                mm[mk] = min(v, mm.get(mk, v)) if isinstance(v, (int, float)) else v
            out[key] = mm
        for key in ("up_via", "down_via"):
            mm = {}
            for k, v in (d.get(key) or {}).items():
                mk = self.map_id(k)
                if mk in mm:
                    continue
                if isinstance(v, list) and v:
                    v = [self.map_id(v[0])] + list(v[1:])
                mm[mk] = v
            out[key] = mm
        out["modules"] = {self.mname(m): s for m, s in (d.get("modules") or {}).items()}
        un, seen = [], set()
        for x in d.get("untested_changed", []):
            y = self.map_id(x)
            if y not in seen:
                seen.add(y)
                un.append(y)
        out["untested_changed"] = un
        out["changed_lines"] = {f: v for f, v in (d.get("changed_lines") or {}).items() if not self.file_locked(f)}
        out["locked_changes"] = locked_count
        out["cut"] = self.cut_info()
        return out

    # ------------------------------------------------------------------ findings (review engine output)
    def finding(self, f: Dict) -> Dict:
        if not self.file_locked(f.get("file", "")):
            return self.scrub_all(f)
        m = self.data.module_of_file(f.get("file", ""))
        return {"id": f.get("id"), "severity": f.get("severity"), "dimension": f.get("dimension"), "source": f.get("source"),
                "title": f"Finding in {self.mname(m) or 'a restricted module'} (no access)", "claim": "", "evidence": "",
                "file": "", "line_start": 0, "line_end": 0, "locked": True, "module": self.mname(m), "confidence": f.get("confidence"),
                "drop_reason": f.get("drop_reason", "")}

    def finding_locked(self, review: Dict, fid: str) -> bool:
        for f in (review or {}).get("findings", []) + (review or {}).get("dropped_findings", []):
            if f.get("id") == fid:
                return self.file_locked(f.get("file", ""))
        return False

    def review(self, r: Dict) -> Dict:
        if not self.cut or not r:
            return r
        out = self.scrub_all({k: v for k, v in r.items() if k not in ("findings", "dropped_findings", "fixes", "patches")})
        out["findings"] = [self.finding(f) for f in r.get("findings", [])]
        out["dropped_findings"] = [self.finding(f) for f in r.get("dropped_findings", [])]
        for key in ("fixes", "patches"):
            if key in r:
                out[key] = [self.scrub_all(p) for p in (r.get(key) or []) if not self.file_locked((p or {}).get("file", ""))]
        locked_ids = {f["id"] for f in out["findings"] + out["dropped_findings"] if f.get("locked")}
        for key in ("panel", "investigations"):
            blk = out.get(key)
            if isinstance(blk, dict):
                inner = "votes" if key == "panel" else "cases"
                if isinstance(blk.get(inner), dict):
                    blk[inner] = {k: ({"outcome": v.get("outcome"), "verdict": v.get("verdict"), "locked": True} if k in locked_ids else v)
                                  for k, v in blk[inner].items()}
        rc = out.get("requirement_check")
        if isinstance(rc, dict):
            for it in rc.get("items", []):
                it["proof"] = [p if not self.file_locked(p.get("file", "")) else
                               {"id": p.get("id"), "file": "", "line": 0, "text": "Proof in a module you cannot open",
                                "evidence": "", "grounded": p.get("grounded"), "locked": True} for p in it.get("proof", [])]
            rc["behaviours"] = [b for b in rc.get("behaviours", []) if not self.file_locked(b.get("file", ""))]
        out["cut"] = self.cut_info()
        return out

    # ------------------------------------------------------------------ PR notes (plain-language feedback)
    def notes(self, n: Dict, review: Optional[Dict] = None) -> Dict:
        if not self.cut or not n:
            return n
        out = self.scrub_all({k: v for k, v in n.items() if k not in ("notes", "units", "roll", "findings_at", "findings", "verdict")})
        out["notes"] = {k: self.scrub_all(v) for k, v in (n.get("notes") or {}).items() if not self.node_locked(k)}
        out["units"] = {k: self.scrub_all(v) for k, v in (n.get("units") or {}).items() if not self.node_locked(k)}
        out["roll"] = {k: self.roll(v) for k, v in (n.get("roll") or {}).items() if k == "pr" or not self.node_locked(k)}
        out["findings_at"] = {k: v for k, v in (n.get("findings_at") or {}).items() if not self.node_locked(k)}
        fl = []
        for f in n.get("findings", []):
            if review and self.finding_locked(review, f.get("id")):
                fl.append({"id": f.get("id"), "severity": f.get("severity"), "dimension": f.get("dimension"),
                           "title": "Finding in a module you cannot open", "locked": True})
            else:
                fl.append(self.scrub_all(f))
        out["findings"] = fl
        vd = dict(n.get("verdict") or {})
        reasons = []
        for r in vd.get("reasons", []):
            locked = (r.get("node") and self.node_locked(r["node"])) or (review and r.get("finding") and self.finding_locked(review, r["finding"]))
            if locked:
                m = self.mod_of(r["node"]) if r.get("node") else ""
                reasons.append({"kind": r.get("kind"), "level": r.get("level"), "locked": True, "node": self.map_id(r["node"]) if r.get("node") else None,
                                "text": f"An item in {self.mname(m) or 'a module you cannot open'} needs attention (no access to details)",
                                "detail": "", "claim": ""})
            else:
                r2 = self.scrub_all({k: v for k, v in r.items() if k != "nodes"})
                if "nodes" in r:
                    r2["nodes"] = list(dict.fromkeys(self.map_id(x) for x in r["nodes"]))
                reasons.append(r2)
        vd["reasons"] = reasons
        vd["risk_areas"] = [{"module": self.mname(a.get("module", "")), "why": self.scrub(a.get("why", ""))} for a in vd.get("risk_areas", [])]
        out["verdict"] = vd
        out["safe_version"] = True
        out["cut"] = self.cut_info()
        return out

    def roll(self, r: Dict) -> Dict:
        """Counts stay (they are the evidence for trust); the names of locked methods in 'weakest' do not."""
        out = {}
        for side, v in (r or {}).items():
            if isinstance(v, dict) and "weakest" in v:
                v = {**v, "weakest": [w for w in v["weakest"] if not self.node_locked(w[0])]}
            out[side] = v
        return out

    # ------------------------------------------------------------------ small files
    def meaning(self, m: Dict) -> Dict:
        if not self.cut:
            return m
        return {k: v for k, v in (m or {}).items() if not self.node_locked(k)}

    def index(self, idx: Dict) -> Dict:
        if not self.cut or not idx:
            return idx
        out = dict(idx)
        out["prs"] = [self.scrub_all(p) for p in idx.get("prs", [])]
        out["cut"] = self.cut_info()
        return out
