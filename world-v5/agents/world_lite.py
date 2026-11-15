"""Cartographer-lite: a pattern-based reader for the bank's C# conventions.

Used only when the Roslyn Cartographer cannot run (no .NET SDK). Same output schema as Roslyn,
but every link is marked certainty="guess" (drawn dotted in the viewer) — it matches names, not types.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

WRITE_OPS = {"Add", "AddAsync", "AddRange", "AddRangeAsync", "Update", "UpdateRange", "Remove", "RemoveRange", "Attach"}
VERBS = {"HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT", "HttpDelete": "DELETE", "HttpPatch": "PATCH"}
KEYWORDS = {"if", "for", "foreach", "while", "switch", "catch", "using", "return", "new", "nameof", "typeof", "lock", "await", "throw", "base", "this"}

TYPE_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<mods>(?:(?:public|internal|private|protected|sealed|static|abstract|partial|readonly)\s+)*)"
                     r"(?P<kind>class|interface|record(?:\s+struct)?|enum|struct)\s+(?P<name>\w+)(?P<gen><[^>{(]+>)?\s*"
                     r"(?:\((?P<params>[^)]*)\))?\s*(?::\s*(?P<bases>[^{;\n]+))?", re.M)
MEMBER_RE = re.compile(r"^[ \t]*(?:\[[^\]]*\][ \t]*)*(?P<mods>(?:(?:public|private|protected|internal|static|readonly|async|override|virtual|sealed|const|new)\s+)+)"
                       r"(?P<type>[\w<>\[\],.? ]+?)\s+(?P<name>\w+)(?:<[\w, ]+>)?\s*(?P<rest>\(|\{|=>|=|;)", re.M)
CTOR_RE = r"^[ \t]*(?:public|private|protected|internal)\s+{name}\s*\("


def module_of(rel: str) -> Tuple[str, str]:
    p = rel.split("/")
    if "Modules" in p:
        i = p.index("Modules")
        if i + 1 < len(p):
            return p[i + 1], (p[i + 2] if i + 3 < len(p) else ("Docs" if p[-1].endswith(".md") else "Wiring"))
    if p[0] == "tests":
        return "Tests", (p[2] if len(p) > 3 else "Tests")
    if p[0] == "src" and len(p) > 3:
        return "Platform", p[2]
    return "Platform", "Host"


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def match_brace(text: str, open_pos: int) -> int:
    depth, i, n = 0, open_pos, len(text)
    in_str = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = j if j != -1 else n
            continue
        elif c in "\"'":
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def short(s: str, n: int = 110) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class Lite:
    def __init__(self, root: Path, commit: str = ""):
        self.root, self.commit = root, commit
        self.nodes: List[Dict] = []
        self.by_id: Dict[str, Dict] = {}
        self.edges: List[Dict] = []
        self.eidx: Dict[str, Dict] = {}
        self.files: Dict[str, str] = {}
        self.flows: Dict[str, list] = {}
        self.dataflow: Dict[str, list] = {}
        self.consts: Dict[str, str] = {}
        self.types: Dict[str, Dict] = {}          # simple name -> type node
        self.members: Dict[str, Dict] = {}        # type id -> {name: [member ids]}
        self.tables: Dict[str, str] = {}          # DbSet prop -> table id
        self.entity_table: Dict[str, str] = {}

    # ----------------------------------------------------------- graph helpers
    def node(self, id, kind, name, parent, module, layer, file, line, end, attrs):
        if id in self.by_id:
            return self.by_id[id]
        n = dict(id=id, kind=kind, name=name, parent=parent, module=module, layer=layer, file=file, line=line, end_line=end, attrs=attrs)
        self.nodes.append(n)
        self.by_id[id] = n
        return n

    def layer(self, module, layer):
        mid = "module:" + module
        self.node(mid, "module", module, None, module, None, None, 0, 0, {})
        lid = f"layer:{module}/{layer}"
        self.node(lid, "layer", layer, mid, module, layer, None, 0, 0, {})
        return lid

    def edge(self, s, t, kind, file=None, line=0):
        if s == t or s not in self.by_id or t not in self.by_id:
            return
        k = f"{s}|{t}|{kind}"
        if k in self.eidx:
            self.eidx[k]["count"] += 1
            return
        e = dict(source=s, target=t, kind=kind, file=file, line=line, certainty="guess", count=1)
        self.edges.append(e)
        self.eidx[k] = e

    # ----------------------------------------------------------- build
    def build(self):
        files = sorted(p for p in self.root.rglob("*.cs") if not any(x in p.parts for x in ("bin", "obj", ".git")))
        for p in files:
            self.files[p.relative_to(self.root).as_posix()] = p.read_text(encoding="utf-8")
        for rel, text in self.files.items():
            for m in re.finditer(r"const\s+string\s+(\w+)\s*=\s*\"([^\"]*)\"", text):
                self.consts[m.group(1)] = m.group(2)
        self.constitutions = {}
        for md in self.root.rglob("CONSTITUTION.md"):
            self.constitutions[module_of(md.relative_to(self.root).as_posix())[0]] = md.read_text(encoding="utf-8")
        for rel, text in self.files.items():
            self.declare(rel, text)
        for rel, text in self.files.items():
            self.find_tables(rel, text)
        for rel, text in self.files.items():
            self.find_states(rel, text)
        self.link_types()
        for rel, text in self.files.items():
            self.walk(rel, text)
        for rel, text in self.files.items():
            self.endpoints(rel, text)
        return self

    def declare(self, rel, text):
        module, layer = module_of(rel)
        ns = (re.search(r"^namespace\s+([\w.]+)", text, re.M) or [None, ""])[1]
        for m in TYPE_RE.finditer(text):
            if m.group("ind") and len(m.group("ind")) > 4:
                continue
            name, kind = m.group("name"), m.group("kind").replace("  ", " ")
            start = m.start("kind")
            brace = text.find("{", m.end())
            semi = text.find(";", m.end())
            positional = m.group("params") is not None
            if positional and (semi != -1 and (brace == -1 or semi < brace)):
                body = None
                end = semi
            else:
                end = match_brace(text, brace) if brace != -1 else m.end()
                body = (brace, end)
            tid = f"T:{ns}.{name}"
            bases = [b.strip() for b in re.split(r",(?![^<]*>)", m.group("bases") or "") if b.strip()]
            attrs = {"type_kind": "record" if kind.startswith("record") else kind, "namespace": ns, "bases": bases,
                     "is_test": module == "Tests", "is_event": "IDomainEvent" in bases, "static": "static" in m.group("mods"),
                     "signature": short(text[m.start("mods"):m.end()], 160), "summary": self.summary(text, m.start()),
                     "is_controller": name.endswith("Controller"), "attributes": []}
            n = self.node(tid, "type", name, self.layer(module, layer), module, layer, rel, line_of(text, start), line_of(text, end), attrs)
            n["_body"] = body
            n["_text"] = text
            self.types[name] = n
            self.members[tid] = {}
            if positional:
                for prm in [x.strip() for x in m.group("params").split(",") if x.strip()]:
                    parts = prm.split()
                    if len(parts) >= 2:
                        pid = f"P:{ns}.{name}.{parts[-1]}"
                        self.node(pid, "property", parts[-1], tid, module, layer, rel, line_of(text, start), line_of(text, start),
                                  {"type": " ".join(parts[:-1]), "signature": prm, "pii": False, "visibility": "public"})
                        self.members[tid].setdefault(parts[-1], []).append(pid)
            if body is None:
                continue
            inner = text[body[0] + 1: body[1]]
            off = body[0] + 1
            if kind == "enum":
                for em in re.finditer(r"^\s*(\w+)\s*(?:=\s*\d+)?\s*,?\s*$", inner, re.M):
                    fid = f"F:{ns}.{name}.{em.group(1)}"
                    ln = line_of(text, off + em.start(1))
                    self.node(fid, "field", em.group(1), tid, module, layer, rel, ln, ln, {"enum_member": True, "signature": em.group(1)})
                continue
            depth_map = self.depth_map(inner)
            if kind == "interface":
                inner_pub = re.sub(r"^([ \t]*)(?=[\w<>\[\],.?]+\s+\w+(<[\w, ]+>)?\s*(\(|\{))", r"\1public ", inner, flags=re.M)
                for mm in MEMBER_RE.finditer(inner_pub):
                    if self.depth_map(inner_pub)[mm.start("name")] == 0:
                        self.member(mm, inner_pub, off, text, tid, ns, name, module, layer, rel, shift=len(inner_pub) - len(inner))
                continue
            for mm in MEMBER_RE.finditer(inner):
                if depth_map[mm.start("name")] != 0:
                    continue
                self.member(mm, inner, off, text, tid, ns, name, module, layer, rel)
            for cm in re.finditer(CTOR_RE.format(name=name), inner, re.M):
                if depth_map[cm.start()] != 0:
                    continue
                ps = text[off + cm.end(): text.find(")", off + cm.end())]
                cid = f"M:{ns}.{name}.#ctor"
                b = text.find("{", off + cm.end())
                arrow = text.find("=>", off + cm.end())
                if arrow != -1 and (b == -1 or arrow < b):
                    e = text.find(";", arrow)
                    span = (arrow, e)
                else:
                    e = match_brace(text, b)
                    span = (b, e)
                self.node(cid, "ctor", name, tid, module, layer, rel, line_of(text, off + cm.start()), line_of(text, e),
                          {"params": [x.strip() for x in ps.split(",") if x.strip()], "signature": f"{name}({short(ps, 120)})", "visibility": "public"})["_span"] = span
                self.members[tid].setdefault("#ctor", []).append(cid)

    def depth_map(self, s):
        d, out = 0, []
        for c in s:
            if c == "}":
                d -= 1
            out.append(d)
            if c == "{":
                d += 1
        return out

    def member(self, mm, inner, off, text, tid, ns, tname, module, layer, rel, shift=0):
        mods, typ, name, rest = mm.group("mods"), mm.group("type").strip(), mm.group("name"), mm.group("rest")
        if typ in ("class", "record", "interface", "enum", "struct") or name == tname:
            return
        start = off + mm.start()
        if shift:
            raw = mm.group(0).replace("public ", "", 1).strip()
            k = text.find(raw[:40], off)
            start = k if k != -1 else start
            off = start - mm.start()
        attrs_txt = re.findall(r"\[([\w]+)", text[start: off + mm.start("type")])
        if rest == "(":
            close = self.paren_end(text, off + mm.end() - 1)
            ps = text[off + mm.end(): close]
            after = text[close + 1: close + 4]
            b = text.find("{", close)
            arrow = text.find("=>", close)
            semi = text.find(";", close)
            if shift:
                span = None   # interface member: no body
            elif arrow != -1 and (b == -1 or arrow < b) and (semi == -1 or arrow < semi):
                span = (arrow, text.find(";", arrow))
            elif semi != -1 and (b == -1 or semi < b):
                span = None   # interface method
            else:
                span = (b, match_brace(text, b))
            mid = f"M:{ns}.{tname}.{name}"
            if mid in self.by_id:
                mid += "`" + str(len(self.members[tid].get(name, [])))
            end = line_of(text, span[1]) if span else line_of(text, start)
            if shift:
                ps = mm.string[mm.end(): mm.string.find(")", mm.end())]
            n = self.node(mid, "method", name, tid, module, layer, rel, line_of(text, start), end,
                          {"returns": typ, "async": "async" in mods, "static": "static" in mods,
                           "params": [x.strip() for x in ps.split(",") if x.strip()], "signature": f"{typ} {name}({short(ps, 120)})",
                           "visibility": (re.search(r"public|private|protected|internal", mods) or ["private"])[0],
                           "is_test_case": "Fact" in attrs_txt or "Theory" in attrs_txt, "is_test": module == "Tests",
                           "attributes": attrs_txt, "summary": self.summary(text, start)})
            n["_span"] = span
            self.members[tid].setdefault(name, []).append(mid)
        elif rest in ("{", "=>") or (rest in ("=", ";") and "const" not in mods and not name.startswith("_") and re.search(r"\{\s*get", text[off + mm.end() - 1: off + mm.end() + 40])):
            pid = f"P:{ns}.{tname}.{name}"
            end_pos = text.find(";", off + mm.end()) if rest == "=>" else text.find("}", off + mm.end())
            n = self.node(pid, "property", name, tid, module, layer, rel, line_of(text, start), line_of(text, max(end_pos, start)),
                          {"type": typ, "pii": "Pii" in attrs_txt, "signature": f"{typ} {name}", "static": "static" in mods,
                           "visibility": (re.search(r"public|private|protected|internal", mods) or ["private"])[0],
                           "setter": "private" if "private set" in text[off + mm.end(): off + mm.end() + 60] else "public",
                           "attributes": attrs_txt})
            n["_span"] = (off + mm.end() - 1, end_pos) if rest == "=>" else None
            self.members[tid].setdefault(name, []).append(pid)
        else:
            fid = f"F:{ns}.{tname}.{name}"
            end_pos = text.find(";", off + mm.end() - 1)
            self.node(fid, "field", name, tid, module, layer, rel, line_of(text, start), line_of(text, end_pos),
                      {"type": typ, "const": "const" in mods, "readonly": "readonly" in mods, "static": "static" in mods,
                       "signature": f"{typ} {name}", "visibility": (re.search(r"public|private|protected|internal", mods) or ["private"])[0]})
            self.members[tid].setdefault(name, []).append(fid)

    def paren_end(self, text, i):
        d = 0
        while i < len(text):
            if text[i] == "(":
                d += 1
            elif text[i] == ")":
                d -= 1
                if d == 0:
                    return i
            i += 1
        return i

    def summary(self, text, pos):
        pre = text[max(0, pos - 400): pos]
        m = re.findall(r"<summary>(.*?)</summary>", pre, re.S)
        if not m:
            return None
        tail = pre[pre.rfind("</summary>") + 10:]
        if tail.strip() and not re.fullmatch(r"\s*(\[[^\]]*\]\s*)*", tail):
            return None
        s = re.sub(r'<see cref="(?:[A-Z]:)?([^"]+)"\s*/>', r"\1", m[-1])
        return short(re.sub(r"///|<[^>]+>", " ", s), 300)

    # ----------------------------------------------------------- relations
    def find_tables(self, rel, text):
        for m in re.finditer(r"DbSet<(\w+)>\s+(\w+)", text):
            ent, prop = m.group(1), m.group(2)
            tab = "table:" + prop
            ln = line_of(text, m.start())
            self.node(tab, "table", prop, self.layer("Database", "Tables"), "Database", "Tables", rel, ln, ln, {"entity_name": ent})
            self.tables[prop] = tab
            et = self.types.get(ent)
            if not et:
                continue
            self.by_id[tab]["attrs"]["entity"] = et["id"]
            self.entity_table[et["id"]] = tab
            self.edge(et["id"], tab, "maps", rel, ln)
            for pname, ids in self.members[et["id"]].items():
                for pid in ids:
                    pn = self.by_id[pid]
                    if pn["kind"] != "property" or pn["attrs"].get("static"):
                        continue
                    cid = f"{tab}.{pname}"
                    self.node(cid, "column", pname, tab, "Database", "Tables", pn["file"], pn["line"], pn["line"],
                              {"type": pn["attrs"].get("type"), "pii": pn["attrs"].get("pii", False), "property": pid})
                    self.edge(pid, cid, "maps", pn["file"], pn["line"])

    def find_states(self, rel, text):
        m = re.search(r"AllowedTransitions\s*=", text)
        if not m:
            return
        block_start = text.find("{", m.end())
        block = text[block_start: match_brace(text, block_start)]
        owner = next((t for t in self.types.values() if t["file"] == rel and t["attrs"]["type_kind"] == "class"), None)
        for am in re.finditer(r"\[(\w+)\.(\w+)\]\s*=\s*([^\n]+)", block):
            enum, frm = am.group(1), am.group(2)
            en = self.types.get(enum)
            if not en:
                continue
            en["attrs"]["state_machine"] = True
            if owner:
                owner["attrs"]["states_enum"] = en["id"]
            fid = self.state(en, frm, owner)
            for tm in re.finditer(rf"\b{enum}\.(\w+)", am.group(3)):
                self.edge(fid, self.state(en, tm.group(1), owner), "transitions", rel, line_of(text, block_start + am.start()))

    def state(self, en, name, owner):
        sid = f"state:{en['name']}.{name}"
        f = self.by_id.get(f"F:{en['attrs']['namespace']}.{en['name']}.{name}")
        first = next((n for n in self.nodes if n["parent"] == en["id"] and n["kind"] == "field"), None)
        return self.node(sid, "state", name, en["id"], en["module"], en["layer"], en["file"], f["line"] if f else 0, f["line"] if f else 0,
                         {"machine": en["name"], "owner": owner["id"] if owner else None, "initial": bool(first and first["name"] == name)})["id"]

    def link_types(self):
        for t in list(self.types.values()):
            for b in t["attrs"]["bases"]:
                bm = re.match(r"(\w+)(?:<(\w+)>)?", b)
                bt = self.types.get(bm.group(1)) if bm else None
                if not bt:
                    continue
                kind = "implements" if bt["attrs"]["type_kind"] == "interface" else "inherits"
                self.edge(t["id"], bt["id"], kind, t["file"], t["line"])
                if bt["name"] == "IEventHandler" and bm.group(2) and bm.group(2) in self.types:
                    h = (self.members[t["id"]].get("HandleAsync") or [t["id"]])[0]
                    self.edge(h, self.types[bm.group(2)]["id"], "subscribes", t["file"], t["line"])
                if kind == "implements":
                    for mname, ids in self.members[bt["id"]].items():
                        impl = self.members[t["id"]].get(mname)
                        if impl:
                            for i in ids:
                                self.edge(i, impl[0], "resolves", t["file"], self.by_id[impl[0]]["line"])
            for cid in self.members[t["id"]].get("#ctor", []):
                for prm in self.by_id[cid]["attrs"]["params"]:
                    pt = re.match(r"(\w+)", prm)
                    if pt and pt.group(1) in self.types:
                        self.edge(t["id"], self.types[pt.group(1)]["id"], "injects", t["file"], self.by_id[cid]["line"])

    def field_types(self, tnode):
        out = {}
        for ids in self.members[tnode["id"]].values():
            for i in ids:
                n = self.by_id[i]
                if n["kind"] in ("field", "property"):
                    out[n["name"]] = re.sub(r"[?<].*", "", n["attrs"].get("type", "") or "")
        return out

    def resolve(self, typename, member):
        t = self.types.get(typename)
        if not t:
            return None
        ids = self.members[t["id"]].get(member)
        return ids[0] if ids else None

    def walk(self, rel, text):
        for t in [x for x in self.types.values() if x["file"] == rel]:
            ftypes = self.field_types(t)
            for ids in self.members[t["id"]].values():
                for mid in ids:
                    n = self.by_id[mid]
                    span = n.get("_span")
                    if not span or span[1] <= span[0]:
                        continue
                    body = text[span[0]: span[1] + 1]
                    locals_ = dict(ftypes)
                    for prm in n["attrs"].get("params", []):
                        parts = prm.replace("?", "").split()
                        if len(parts) >= 2:
                            locals_[parts[-1]] = re.sub(r"<.*", "", parts[-2] if parts[-2] not in ("this", "params") else parts[-1])
                    for vm in re.finditer(r"\bvar\s+(\w+)\s*=\s*(?:await\s+)?(?:new\s+(\w+)|_(\w+)\.(\w+))", body):
                        if vm.group(2):
                            locals_[vm.group(1)] = vm.group(2)
                    for vm in re.finditer(r"\b([A-Z]\w+)\s+(\w+)\s*=", body):
                        locals_.setdefault(vm.group(2), vm.group(1))
                    for vm in re.finditer(r"\bvar\s+(\w+)\s*=\s*(?:await\s+)?(?:(\w+)\s*\.\s*)?(\w+)\s*\(", body):
                        obj, meth = vm.group(2), vm.group(3)
                        tgt = self.resolve(locals_.get(obj, obj) if obj else t["name"], meth)
                        if tgt:
                            rt = self.by_id[tgt]["attrs"].get("returns", "")
                            inner_t = re.findall(r"(\w+)\??>*$", rt.replace("?", ""))
                            if inner_t and inner_t[0] in self.types:
                                locals_[vm.group(1)] = inner_t[0]
                    self.effects(mid, body, span[0], text, rel, t, locals_)
                    if n["kind"] in ("method", "ctor"):
                        self.flows[mid] = self.flow(body, span[0], text, locals_, t)
                        self.dataflow[mid] = self.data(n, body, span[0], text, ftypes)

    def effects(self, mid, body, off, text, rel, t, locals_, collect=None):
        out = collect if collect is not None else None
        def add(target, kind, pos):
            ln = line_of(text, off + pos)
            if out is not None:
                out.setdefault(kind, []).append(target)
            else:
                self.edge(mid, target, kind, rel, ln)
        for m in re.finditer(r"\b(?:(\w+)\s*\.\s*)?(\w+)\s*(?:<[^>()]*>)?\s*\(", body):
            obj, meth = m.group(1), m.group(2)
            if meth in KEYWORDS or (obj and obj in ("new",)):
                continue
            target = None
            if obj in (None, "this"):
                if text[max(0, off + m.start() - 4): off + m.start()].strip().endswith("new"):
                    continue
                target = self.resolve(t["name"], meth)
            elif obj in locals_:
                target = self.resolve(locals_[obj], meth)
            elif obj in self.types:
                target = self.resolve(obj, meth)
            if target:
                add(target, "calls", m.start())
        for m in re.finditer(r"PublishAsync\(\s*new\s+(\w+)\s*\(", body):
            if m.group(1) in self.types:
                add(self.types[m.group(1)]["id"], "publishes", m.start())
        for m in re.finditer(r"TransitionTo\(\s*(\w+)\.(\w+)\s*\)", body):
            sid = f"state:{m.group(1)}.{m.group(2)}"
            if sid in self.by_id:
                add(sid, "triggers", m.start())
        for m in re.finditer(r"\b\w+\.(\w+)\s*\.\s*(\w+)", body):
            if m.group(1) in self.tables:
                add(self.tables[m.group(1)], "writes" if m.group(2) in WRITE_OPS else "reads", m.start())
        for m in re.finditer(r"\b(\w+)\.(\w+)\s*[-+]?=(?!=)", body):
            typ = locals_.get(m.group(1))
            tn = self.types.get(typ or "")
            if tn and tn["id"] in self.entity_table and tn["id"] != t["id"]:
                add(self.entity_table[tn["id"]], "writes", m.start())

    # ----------------------------------------------------------- flow (statement tree) and data flow
    def statements(self, s: str, base: int):
        """Split a block's inner text into top-level statements: (start, end, text)."""
        out, i, n = [], 0, len(s)
        while i < n:
            while i < n and s[i] in " \t\r\n":
                i += 1
            if i >= n:
                break
            if s.startswith("//", i):
                i = s.find("\n", i) if s.find("\n", i) != -1 else n
                continue
            start, depth, paren = i, 0, 0
            head = re.match(r"(if|else|foreach|for|while|try|catch|finally|using|switch)\b", s[i:])
            while i < n:
                c = s[i]
                if c == "(":
                    paren += 1
                elif c == ")":
                    paren -= 1
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0 and head and paren == 0:
                        rest = s[i + 1:].lstrip()
                        if re.match(r"(else|catch|finally)\b", rest):
                            i += 1
                            continue
                        i += 1
                        break
                elif c == ";" and depth == 0 and paren == 0:
                    rest = s[i + 1:].lstrip()
                    if head and head.group(1) == "if" and rest.startswith("else"):
                        i += 1
                        continue
                    i += 1
                    break
                elif c == '"':
                    j = i + 1
                    while j < n and s[j] != '"':
                        j += 2 if s[j] == "\\" else 1
                    i = j
                i += 1
            out.append((base + start, base + i, s[start:i].strip()))
        return out

    def flow(self, body, off, text, locals_, t):
        b = body.strip()
        if b.startswith("=>"):
            return [self.step("return", "=> " + short(b[2:].rstrip(";")), off, text, body, locals_, t, off)]
        inner_start = body.find("{") + 1
        return self.block(body[inner_start: body.rfind("}")], off + inner_start, text, locals_, t)

    def block(self, s, base, text, locals_, t):
        steps = []
        for st, en, stmt in self.statements(s, base):
            steps.append(self.parse_stmt(stmt, st, text, locals_, t))
        return steps

    def sub(self, stmt, st, text, locals_, t, after):
        """Body after a header: either a {...} block or a single statement."""
        rest = stmt[after:].lstrip()
        rs = st + len(stmt) - len(stmt[after:].lstrip()) if False else st + stmt.find(rest, after) if rest else st
        if rest.startswith("{"):
            e = match_brace(rest, 0)
            return self.block(rest[1:e], rs + 1, text, locals_, t), rest[e + 1:], rs + e + 1
        return ([self.parse_stmt(rest, rs, text, locals_, t)] if rest else []), "", rs + len(rest)

    def header_end(self, stmt, start):
        i = stmt.find("(", start)
        return self.paren_end(stmt, i) + 1 if i != -1 else start

    def parse_stmt(self, stmt, st, text, locals_, t):
        if stmt.startswith("if"):
            he = self.header_end(stmt, 0)
            o = self.step("if", "if " + short(stmt[2:he].strip(), 92), st, text, stmt[:he], locals_, t, st)
            then, rest, rpos = self.sub(stmt, st, text, locals_, t, he)
            o["then"] = then
            rest_s = rest.lstrip()
            if rest_s.startswith("else"):
                epos = rpos + (len(rest) - len(rest_s)) + 4
                body = rest_s[4:]
                o["else"] = [self.parse_stmt(body.strip(), epos + (len(body) - len(body.lstrip())), text, locals_, t)] if body.strip().startswith("if") \
                    else self.sub(rest_s, rpos + (len(rest) - len(rest_s)), text, locals_, t, 4)[0]
            else:
                o["else"] = []
            return o
        m = re.match(r"(foreach|for|while)\b", stmt)
        if m:
            he = self.header_end(stmt, 0)
            label = stmt[:he]
            fm = re.match(r"foreach\s*\(\s*(?:var|\w+)\s+(\w+)\s+in\s+(.+)\)$", label, re.S)
            text_ = f"for each {fm.group(1)} in {short(fm.group(2), 60)}" if fm else short(label, 92)
            o = self.step("loop", text_, st, text, label, locals_, t, st)
            o["body"] = self.sub(stmt, st, text, locals_, t, he)[0]
            return o
        if stmt.startswith("try"):
            o = self.step("try", "try", st, text, "", locals_, t, st)
            body, rest, rpos = self.sub(stmt, st, text, locals_, t, 3)
            o["body"] = body
            o["catches"] = []
            for cm in re.finditer(r"catch\s*(\([^)]*\))?\s*\{", rest):
                b0 = rest.find("{", cm.start())
                e = match_brace(rest, b0)
                o["catches"].append({"text": "catch " + (cm.group(1) or ""), "line": line_of(text, rpos + cm.start()),
                                     "body": self.block(rest[b0 + 1: e], rpos + b0 + 1, text, locals_, t)})
            return o
        if stmt.startswith("using") and "(" in stmt[:8]:
            he = self.header_end(stmt, 0)
            o = self.step("using", short(stmt[:he], 92), st, text, stmt[:he], locals_, t, st)
            o["body"] = self.sub(stmt, st, text, locals_, t, he)[0]
            return o
        kind = "return" if stmt.startswith("return") else "throw" if stmt.startswith("throw") else "step"
        return self.step(kind, short(stmt), st, text, stmt, locals_, t, st)

    def step(self, kind, label, pos, text, scope, locals_, t, off):
        fx = {}
        if scope:
            self.effects(None, scope, off, text, None, t, locals_, collect=fx)
        return {"kind": kind, "text": label, "line": line_of(text, pos),
                "calls": sorted(set(fx.get("calls", []))), "publishes": sorted(set(fx.get("publishes", []))),
                "triggers": sorted(set(fx.get("triggers", []))),
                "tables": sorted({("writes " if k == "writes" else "reads ") + x for k in ("reads", "writes") for x in fx.get(k, [])})}

    def data(self, n, body, off, text, ftypes):
        out = {}
        for prm in n["attrs"].get("params", []):
            parts = prm.split("=")[0].split()
            if len(parts) >= 2:
                out[parts[-1]] = {"name": parts[-1], "kind": "parameter", "type": " ".join(parts[:-1]), "writes": [n["line"]], "reads": []}
        for m in re.finditer(r"\b(?:var|[A-Z]\w*(?:<[^>]+>)?\??)\s+(\w+)\s*=(?!=)", body):
            out.setdefault(m.group(1), {"name": m.group(1), "kind": "local", "type": "var", "writes": [], "reads": []})
        for name, f in ftypes.items():
            if name.startswith("_"):
                out.setdefault(name, {"name": name, "kind": "field", "type": f, "writes": [], "reads": []})
        for name, v in out.items():
            for m in re.finditer(rf"(?<![\w.])(?:this\.)?{re.escape(name)}\b", body):
                ln = line_of(text, off + m.start())
                after = body[m.end(): m.end() + 4]
                before = body[max(0, m.start() - 4): m.start()]
                w = (re.match(r"\s*[-+*/]?=(?!=)", after) is not None) or after.startswith("++") or after.startswith("--") or before.endswith("var ")
                lst = v["writes"] if w else v["reads"]
                if ln not in lst:
                    lst.append(ln)
        res = [v for v in out.values() if v["writes"] or v["reads"]]
        for v in res:
            v["writes"].sort(); v["reads"].sort()
        return sorted(res, key=lambda v: min(v["writes"] + v["reads"] or [0]))

    # ----------------------------------------------------------- endpoints
    def endpoints(self, rel, text):
        for t in [x for x in self.types.values() if x["file"] == rel and x["name"].endswith("Controller")]:
            head = text[max(0, text.rfind("\n\n", 0, text.find("class " + t["name"])) ): text.find("class " + t["name"])]
            route = (re.search(r'\[Route\("([^"]*)"\)\]', head) or [None, ""])[1]
            cls_auth = self.auth(head)
            for ids in self.members[t["id"]].values():
                for mid in ids:
                    n = self.by_id[mid]
                    if n["kind"] != "method":
                        continue
                    lines = text.splitlines()
                    i, attrs = n["line"] - 1, ""
                    while i >= 0 and (lines[i].strip().startswith("[") or lines[i].strip() == "" or n["line"] - 1 == i):
                        attrs = lines[i] + "\n" + attrs
                        i -= 1
                        if n["line"] - i > 6:
                            break
                    for vm in re.finditer(r"\[(Http\w+)(?:\(\"([^\"]*)\"\))?\]", attrs):
                        verb = VERBS.get(vm.group(1))
                        if not verb:
                            continue
                        full = "/" + "/".join(x for x in (route.strip("/"), (vm.group(2) or "").strip("/")) if x)
                        auth = ["anonymous"] if "AllowAnonymous" in attrs else list(dict.fromkeys(cls_auth + self.auth(attrs)))
                        eid = f"endpoint:{verb} {full}"
                        self.node(eid, "endpoint", f"{verb} {full}", t["id"], t["module"], t["layer"], rel, n["line"], n["line"],
                                  {"verb": verb, "route": full, "auth": auth, "protected": bool(auth) and "anonymous" not in auth, "handler": mid})
                        self.edge(eid, mid, "routes", rel, n["line"])

    def auth(self, s):
        out = []
        for m in re.finditer(r"\[Authorize(?:\(([^)]*)\))?\]", s):
            if not m.group(1):
                out.append("authenticated")
                continue
            for k, v in re.findall(r"(\w+)\s*=\s*([\w.\"-]+)", m.group(1)):
                v = v.strip('"')
                out.append(f"{k.lower()}:{self.consts.get(v.split('.')[-1], v)}")
        return out

    def to_json(self):
        for n in self.nodes:
            n.pop("_body", None); n.pop("_text", None); n.pop("_span", None)
        return {"schema": "bank-world/1", "generated_by": "lite", "commit": self.commit, "nodes": self.nodes, "edges": self.edges,
                "flows": self.flows, "dataflow": self.dataflow, "files": self.files, "constitutions": self.constitutions,
                "stats": {"note": "pattern-based fallback: links are name matches (dotted)"}}


def build(root: Path, out: Path, commit: str = "") -> Dict:
    w = Lite(root, commit).build()
    data = w.to_json()
    out.write_text(json.dumps(data), encoding="utf-8")
    return data


if __name__ == "__main__":
    d = build(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "")
    print(f"lite cartographer: {len(d['nodes'])} things, {len(d['edges'])} links")
