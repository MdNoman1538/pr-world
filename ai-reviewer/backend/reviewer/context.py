"""Context builder: what each specialist sees.

Research basis (Lu et al., 2025, via the synthesis report):
- Bare diff hunks cause "context collapse" → generic, ungrounded advice.
- AST slicing strategies: OriginalDiff, ParentFunction, LeftFlow (best balance), FullFlow (token bloat).
- Inline line tags ("+105| code") let the model point at exact lines.

Implementation:
- tree-sitter (C#) finds the enclosing member of each changed line when installed;
  otherwise a brace-matching fallback does the same job less precisely.
- LeftFlow here = enclosing member + the class-level fields/properties/constants that the
  changed lines read or write (the definitions the change depends on).
- FullFlow adds signatures of methods called from changed lines.
- An impact section (code-graph lite): callers of each changed member across the repo, and
  whether any test file references it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .git_tools import FileChange, PullRequest, file_at, grep
from .policy import Policy

try:  # optional, precise AST
    import tree_sitter_c_sharp as _tscs
    from tree_sitter import Language as _TSLanguage, Parser as _TSParser
    _CS_LANG = _TSLanguage(_tscs.language())
    TREE_SITTER = True
except Exception:  # pragma: no cover - depends on local install
    TREE_SITTER = False

MEMBER_NODES = {
    "method_declaration", "constructor_declaration", "destructor_declaration", "property_declaration",
    "indexer_declaration", "operator_declaration", "conversion_operator_declaration",
    "local_function_statement", "accessor_declaration", "event_declaration",
}
TYPE_NODES = {"class_declaration", "struct_declaration", "record_declaration", "interface_declaration",
              "enum_declaration"}

_KEYWORDS = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return", "new", "else",
             "do", "try", "finally", "fixed", "checked", "unchecked", "nameof", "typeof", "sizeof", "default",
             "await", "throw", "base", "this", "var", "get", "set", "init", "value", "true", "false", "null"}
_MODIFIERS = ("public|private|protected|internal|static|virtual|override|abstract|sealed|async|unsafe|extern|new|"
              "readonly|partial|implicit|explicit|ref|required|file")
_SIG = re.compile(
    rf"^\s*(?P<mods>(?:(?:{_MODIFIERS})\s+)*)"
    r"(?:(?P<type>[A-Za-z_][\w\.]*(?:<[^()]*?>)?(?:\[\])*\??|\([^()]*\))\s+)?"
    r"(?P<name>[A-Za-z_]\w*|operator\s*\S+)\s*(?:<[^()]*?>)?\s*\((?P<rest>.*)$")
_NOT_TYPES = {"return", "await", "throw", "yield", "else", "case", "new", "using", "lock", "goto", "in", "out",
              "is", "as", "await", "nameof", "typeof", "default", "when", "where", "select", "from"}


def _is_signature(line: str):
    """Strict fallback signature test: declarations, not calls (no '.', '=' or statement keyword before the name)."""
    s = line.strip()
    if not s or s[0] in ".[=:?+-*/&|!(" or s.startswith("//"):
        return None
    m = _SIG.match(line)
    if not m:
        return None
    name, typ, mods = m.group("name"), m.group("type"), m.group("mods").split()
    if name.split()[0] in _KEYWORDS or (typ and typ in _NOT_TYPES):
        return None
    if not typ and not [x for x in mods if x != "new"]:
        return None                                     # bare call like Foo(...)
    head = line[:m.start("name")]
    if "=" in head and "=>" not in head:
        return None
    return name


_PROP = re.compile(r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|new|readonly)\s+)+"
                   r"[\w<>\[\],\.\?]+\s+(?P<name>[A-Za-z_]\w*)\s*(\{|=>)")


@dataclass
class Span:
    start: int  # 1-based inclusive
    end: int
    name: str
    kind: str


@dataclass
class FileContext:
    path: str
    text: str                      # line-tagged slice shown to the model
    members: List[str]             # names of changed members
    strategy: str
    truncated: bool = False


@dataclass
class ImpactInfo:
    member: str
    file: str
    callers: List[str] = field(default_factory=list)       # "path:line"
    test_refs: List[str] = field(default_factory=list)


@dataclass
class PRContext:
    files: List[FileContext]
    impact: List[ImpactInfo]
    head_text: Dict[str, List[str]]                       # path -> lines of the new version
    parser: str
    removed_text: Dict[str, str] = field(default_factory=dict)   # path -> removed lines joined

    def render(self, budget_chars: int) -> str:
        parts, used = [], 0
        for fc in self.files:
            block = f"### FILE: {fc.path}  (slice: {fc.strategy}{', truncated' if fc.truncated else ''})\n{fc.text}\n"
            if used + len(block) > budget_chars:
                parts.append(f"### FILE: {fc.path}  (omitted: context budget reached)\n")
                continue
            parts.append(block)
            used += len(block)
        return "\n".join(parts)

    def render_impact(self) -> str:
        if not self.impact:
            return "No changed C# members detected."
        rows = []
        for im in self.impact:
            callers = ", ".join(im.callers[:8]) + (" …" if len(im.callers) > 8 else "")
            tests = ", ".join(im.test_refs[:5]) or "NONE"
            rows.append(f"- {im.member} ({im.file}): {len(im.callers)} caller(s) [{callers or 'none found'}]; "
                        f"test references: {tests}")
        return "\n".join(rows)


# ------------------------------------------------------------------ member spans
def _spans_tree_sitter(src: str) -> List[Span]:
    parser = _TSParser(_CS_LANG)
    tree = parser.parse(src.encode("utf-8"))
    spans: List[Span] = []

    def walk(node):
        if node.type in MEMBER_NODES or node.type in TYPE_NODES:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8", "replace") if name_node is not None else node.type
            spans.append(Span(node.start_point[0] + 1, node.end_point[0] + 1, name,
                              "type" if node.type in TYPE_NODES else "member"))
        for ch in node.children:
            walk(ch)

    walk(tree.root_node)
    return spans


def _strip_strings(line: str) -> str:
    line = re.sub(r'@?"(?:[^"\\]|\\.)*"', '""', line)
    line = re.sub(r"'(?:[^'\\]|\\.)'", "''", line)
    return line.split("//")[0]


def _spans_fallback(lines: List[str]) -> List[Span]:
    spans: List[Span] = []
    n = len(lines)
    for i, raw in enumerate(lines):
        line = _strip_strings(raw)
        kind = "member"
        name = None
        sig_name = _is_signature(line)
        if sig_name and not line.rstrip().endswith(";"):
            name = sig_name
        else:
            p = _PROP.match(line)
            if p:
                name = p.group("name")
        if re.match(r"^\s*(?:\[[^\]]*\]\s*)*(?:\w+\s+)*(class|struct|record|interface|enum)\s+(\w+)", line):
            name = re.match(r"^\s*(?:\[[^\]]*\]\s*)*(?:\w+\s+)*(class|struct|record|interface|enum)\s+(\w+)", line).group(2)
            kind = "type"
        if not name:
            continue
        # find the body: '{' block or '=>' expression ending with ';'
        depth, opened, end = 0, False, None
        for j in range(i, min(n, i + 2000)):
            s = _strip_strings(lines[j])
            if not opened and "=>" in s and "{" not in s.split("=>")[0] and j - i < 3:
                k = j
                while k < n and not _strip_strings(lines[k]).rstrip().endswith(";"):
                    k += 1
                end = min(k, n - 1)
                break
            for ch in s:
                if ch == "{":
                    depth += 1; opened = True
                elif ch == "}":
                    depth -= 1
            if opened and depth <= 0:
                end = j
                break
            if not opened and s.rstrip().endswith(";") and j > i:
                break
        if end is not None:
            spans.append(Span(i + 1, end + 1, name, kind))
    return spans


def member_spans(src: str) -> Tuple[List[Span], str]:
    if TREE_SITTER:
        try:
            return _spans_tree_sitter(src), "tree-sitter"
        except Exception:
            pass
    return _spans_fallback(src.splitlines()), "fallback"


def _enclosing(spans: List[Span], line: int) -> Optional[Span]:
    cands = [s for s in spans if s.kind == "member" and s.start <= line <= s.end]
    return min(cands, key=lambda s: s.end - s.start) if cands else None


# ------------------------------------------------------------------ flow helpers
_IDENT = re.compile(r"\b[A-Za-z_]\w*\b")
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\(")


def _identifiers(lines: List[str]) -> Set[str]:
    out: Set[str] = set()
    for l in lines:
        for t in _IDENT.findall(_strip_strings(l)):
            if t not in _KEYWORDS and len(t) > 1:
                out.add(t)
    return out


def _definition_lines(lines: List[str], names: Set[str], spans: List[Span]) -> List[int]:
    """Class-level field/property/const declarations (outside members) that declare one of `names`."""
    inside_member = set()
    for s in spans:
        if s.kind == "member":
            inside_member.update(range(s.start, s.end + 1))
    hits = []
    decl = re.compile(r"^\s*(?:\[[^\]]*\]\s*)*(?:(?:public|private|protected|internal|static|readonly|const|volatile|new)\s+)+"
                      r"[\w<>\[\],\.\?]+\s+(\w+)\s*(=|;|\{|=>)")
    for i, l in enumerate(lines, start=1):
        if i in inside_member:
            continue
        m = decl.match(l)
        if m and m.group(1) in names:
            hits.append(i)
    return hits


# ------------------------------------------------------------------ rendering
def _render_window(path: str, new_lines: List[str], ranges: List[Tuple[int, int]], f: FileChange,
                   extra_lines: List[int]) -> str:
    added = set(f.added_line_numbers)
    removed_at: Dict[int, List[Tuple[int, str]]] = {}
    for h in f.hunks:
        if not h.removed:
            continue
        anchor = h.new_start if h.new_len > 0 else h.new_start + 1   # show deletions before this new line
        removed_at.setdefault(anchor, []).extend((h.old_start + i, t) for i, t in enumerate(h.removed))
    show: Set[int] = set()
    for a, b in ranges:
        show.update(range(max(1, a), min(len(new_lines), b) + 1))
    show.update(l for l in extra_lines if 1 <= l <= len(new_lines))
    for anchor in removed_at:
        show.add(min(max(1, anchor), max(1, len(new_lines))))
    out: List[str] = []
    prev = None
    for ln in sorted(show):
        if prev is not None and ln != prev + 1:
            out.append("     ⋮")
        for old_ln, t in removed_at.get(ln, []):
            out.append(f"-{old_ln:>4}| {t}")
        if ln <= len(new_lines):
            mark = "+" if ln in added else " "
            out.append(f"{mark}{ln:>4}| {new_lines[ln - 1]}")
        prev = ln
    tail = len(new_lines) + 1
    for old_ln, t in removed_at.get(tail, []):
        out.append(f"-{old_ln:>4}| {t}")
    return "\n".join(out)


LONG_MEMBER = 80


def _compress(text: str, cap: int) -> str:
    """Shrink a slice to fit `cap` WITHOUT losing changed lines: keep +/- lines with shrinking context."""
    lines = text.splitlines()
    marked = [i for i, l in enumerate(lines) if l[:1] in "+-"]
    for ctx_n in (12, 8, 5, 3, 1, 0):
        keep = set()
        for i in marked:
            keep.update(range(max(0, i - ctx_n), min(len(lines), i + ctx_n + 1)))
        out, prev = [], None
        for i in sorted(keep):
            if prev is not None and i != prev + 1:
                out.append("     ⋮")
            out.append(lines[i])
            prev = i
        s = "\n".join(out)
        if len(s) <= cap:
            return s + "\n     ⋮ (context reduced to fit; every changed line kept)"
    return s[:cap] + "\n     ⋮ (truncated: change too large)"


def build_context(pr: PullRequest, policy: Policy, strategy: str = "leftflow",
                  per_file_chars: int = 14000, max_callers: int = 40) -> PRContext:
    files: List[FileContext] = []
    impact: List[ImpactInfo] = []
    head_text: Dict[str, List[str]] = {}
    parser_used = "tree-sitter" if TREE_SITTER else "fallback"

    for f in pr.files:
        if f.binary:
            files.append(FileContext(f.path, "(binary file changed)", [], "none"))
            continue
        if f.status == "D":
            old = file_at(pr.repo, pr.merge_base, f.path) or ""
            body = "\n".join(f"-{i:>4}| {t}" for i, t in enumerate(old.splitlines()[:200], 1))
            files.append(FileContext(f.path, "(file deleted)\n" + body, [], "deleted"))
            continue
        src = file_at(pr.repo, pr.head, f.path) or ""
        lines = src.splitlines()
        head_text[f.path] = lines
        changed = f.added_line_numbers or [h.new_start for h in f.hunks]

        if not f.path.endswith(".cs") or strategy == "diff":
            ranges = [(max(1, l - 3), l + 3) for l in changed]
            text = _render_window(f.path, lines, ranges, f, [])
            members: List[str] = []
            used = "diff"
        else:
            spans, used_parser = member_spans(src)
            parser_used = used_parser
            ranges, members = [], []
            for l in changed:
                sp = _enclosing(spans, l)
                if sp and sp.end - sp.start > LONG_MEMBER:
                    # long member: keep its signature, a window around the change, and its end
                    ranges += [(sp.start, sp.start + 3), (max(sp.start, l - 20), min(sp.end, l + 20)), (sp.end, sp.end)]
                    if sp.name not in members:
                        members.append(sp.name)
                elif sp:
                    ranges.append((sp.start, sp.end))
                    if sp.name not in members:
                        members.append(sp.name)
                else:
                    ranges.append((max(1, l - 6), l + 6))
            extra: List[int] = []
            if strategy in ("leftflow", "fullflow"):
                changed_text = [lines[l - 1] for l in f.added_line_numbers if 0 < l <= len(lines)]
                changed_text += [t for h in f.hunks for t in h.removed]
                extra = _definition_lines(lines, _identifiers(changed_text), spans)
            text = _render_window(f.path, lines, ranges, f, extra)
            used = strategy
            if strategy == "fullflow":
                calls = set()
                for l in f.added_line_numbers:
                    if 0 < l <= len(lines):
                        calls.update(c for c in _CALL.findall(_strip_strings(lines[l - 1])) if c not in _KEYWORDS)
                sigs = []
                for c in sorted(calls)[:12]:
                    rows = grep(pr.repo, pr.head, rf"^\s*(public|private|protected|internal|static).*\b{re.escape(c)}\s*(<[^>]*>)?\s*\(", 3)
                    sigs.extend(rows)
                if sigs:
                    text += "\n\n# Signatures of methods called from changed lines:\n" + "\n".join(f"  {s}" for s in sigs)

            for m in members:
                rows = grep(pr.repo, pr.head, rf"\b{re.escape(m)}\s*(<[^>]*>)?\s*\(", max_callers + 20)
                callers = [":".join(r.split(":")[:2]) for r in rows]
                callers = [c for c in callers if not c.startswith(f.path + ":")] + \
                          [c for c in callers if c.startswith(f.path + ":")
                           and not any(s.start <= int(c.split(":")[1]) <= s.end for s in spans if s.name == m)]
                tests = [c for c in callers if policy.is_test(c.split(":")[0])]
                impact.append(ImpactInfo(m, f.path, callers[:max_callers], tests))

        truncated = len(text) > per_file_chars
        if truncated:
            text = _compress(text, per_file_chars)
        files.append(FileContext(f.path, text, members, used, truncated))
    removed = {f.path: "\n".join(t for h in f.hunks for t in h.removed) for f in pr.files}
    return PRContext(files, impact, head_text, parser_used, removed)


def evidence_matches(ctx: PRContext, path: str, line_start: int, line_end: int, snippet: str,
                     slack: int = 3) -> bool:
    """Deterministic check that a finding's evidence really exists at (about) the cited lines."""
    norm = lambda s: re.sub(r"\s+", "", s)
    target = norm(snippet)
    if not target:
        return False
    if target in norm(ctx.removed_text.get(path, "")) and len(target) >= 8:
        return True          # evidence quotes a removed line of this file
    lines = ctx.head_text.get(path)
    if lines is None or line_start < 1 or line_start > len(lines) + 1:
        return False
    a = max(1, min(line_start, line_end) - slack)
    b = min(len(lines), max(line_start, line_end) + slack)
    window = norm("".join(lines[a - 1:b]))
    if target in window:
        return True
    # accept if most snippet lines appear in the window (model may trim/merge lines)
    parts = [norm(p) for p in snippet.splitlines() if norm(p)]
    return bool(parts) and sum(1 for p in parts if p in window) / len(parts) >= 0.6
