"""Read a PR from a local git checkout: changed files, hunks, file versions, commit messages.

The PR is everything on `head` since it branched from `base` (three-dot diff),
which is what GitHub shows in a pull request.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class GitError(RuntimeError):
    pass


def git(repo: str, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    removed: List[str] = field(default_factory=list)   # removed line texts, in order
    added: List[str] = field(default_factory=list)     # added line texts, in order

    @property
    def added_lines(self) -> List[int]:
        return list(range(self.new_start, self.new_start + self.new_len))

    @property
    def removed_lines(self) -> List[int]:
        return list(range(self.old_start, self.old_start + self.old_len))


@dataclass
class FileChange:
    path: str
    status: str                       # A, M, D, R
    old_path: Optional[str] = None
    hunks: List[Hunk] = field(default_factory=list)
    binary: bool = False

    @property
    def added_line_numbers(self) -> List[int]:
        return [n for h in self.hunks for n in h.added_lines]

    @property
    def n_added(self) -> int:
        return sum(h.new_len for h in self.hunks)

    @property
    def n_removed(self) -> int:
        return sum(h.old_len for h in self.hunks)


@dataclass
class PullRequest:
    repo: str
    base: str
    head: str
    merge_base: str
    files: List[FileChange]
    commit_messages: List[str]

    def file(self, path: str) -> Optional[FileChange]:
        return next((f for f in self.files if f.path == path), None)

    @property
    def changed_paths(self) -> List[str]:
        return [f.path for f in self.files]


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_diff(text: str) -> Dict[str, List[Hunk]]:
    out: Dict[str, List[Hunk]] = {}
    current: Optional[str] = None
    hunk: Optional[Hunk] = None
    for line in text.splitlines():
        if line.startswith("diff --git"):
            current, hunk = None, None
            continue
        if line.startswith("+++ "):
            p = line[4:]
            current = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
            if current is not None:
                out.setdefault(current, [])
            continue
        if line.startswith("--- "):
            continue
        m = _HUNK_RE.match(line)
        if m and current is not None:
            hunk = Hunk(int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1))
            out[current].append(hunk)
            continue
        if hunk is None:
            continue
        if line.startswith("+"):
            hunk.added.append(line[1:])
        elif line.startswith("-"):
            hunk.removed.append(line[1:])
    return out


def load_pr(repo: str, base: str, head: str) -> PullRequest:
    mb = git(repo, "merge-base", base, head).strip()
    status = git(repo, "diff", "--name-status", "-M", f"{mb}", head)
    files: List[FileChange] = []
    for row in status.splitlines():
        parts = row.split("\t")
        code = parts[0][0]
        if code == "R":
            files.append(FileChange(path=parts[2], status="R", old_path=parts[1]))
        else:
            files.append(FileChange(path=parts[1], status=code, old_path=parts[1] if code != "A" else None))
    diff = git(repo, "diff", "-U0", "-M", "--no-color", mb, head)
    hunks = _parse_diff(diff)
    deleted_hunks = _parse_deleted(diff)
    for f in files:
        f.hunks = hunks.get(f.path, []) or deleted_hunks.get(f.path, [])
        if f"Binary files" in diff and f.path in diff and not f.hunks and f.status != "D":
            f.binary = True
    log = git(repo, "log", "--format=%B%x00", f"{mb}..{head}")
    msgs = [m.strip() for m in log.split("\x00") if m.strip()]
    return PullRequest(repo, base, head, mb, files, msgs)


def _parse_deleted(text: str) -> Dict[str, List[Hunk]]:
    """Deleted files have '+++ /dev/null'; key them by their '--- a/' path."""
    out: Dict[str, List[Hunk]] = {}
    old: Optional[str] = None
    hunk: Optional[Hunk] = None
    deleting = False
    for line in text.splitlines():
        if line.startswith("diff --git"):
            old, hunk, deleting = None, None, False
        elif line.startswith("--- a/"):
            old = line[6:]
        elif line.startswith("+++ /dev/null") and old:
            deleting = True
            out[old] = []
        elif deleting:
            m = _HUNK_RE.match(line)
            if m:
                hunk = Hunk(int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 0))
                out[old].append(hunk)
            elif hunk is not None and line.startswith("-"):
                hunk.removed.append(line[1:])
    return out


def file_at(repo: str, rev: str, path: str) -> Optional[str]:
    try:
        return git(repo, "show", f"{rev}:{path}")
    except GitError:
        return None


def list_files(repo: str, rev: str) -> List[str]:
    return [p for p in git(repo, "ls-tree", "-r", "--name-only", rev).splitlines() if p]


def grep(repo: str, rev: str, pattern: str, max_hits: int = 50) -> List[str]:
    """`git grep` at a revision. Returns 'path:line:text' rows (rev prefix stripped)."""
    out = git(repo, "grep", "-n", "-I", "-E", pattern, rev, "--", "*.cs", check=False)
    rows = []
    for row in out.splitlines()[:max_hits]:
        rows.append(row[len(rev) + 1:] if row.startswith(rev + ":") else row)
    return rows


def churn_and_reverts(repo: str, rev: str, path_prefix: str, limit: int = 500) -> Dict[str, int]:
    """History signals for policy drafting: commits touching a path and how many were reverts/fixes."""
    log = git(repo, "log", f"-{limit}", "--format=%s", rev, "--", path_prefix, check=False)
    subjects = [s for s in log.splitlines() if s]
    return {
        "commits": len(subjects),
        "reverts": sum(1 for s in subjects if s.lower().startswith("revert")),
        "fixes": sum(1 for s in subjects if re.search(r"\b(fix|bug|hotfix)\b", s, re.I)),
    }


def recent_commits(repo: str, rev: str, path: str, n: int = 5) -> List[str]:
    out = git(repo, "log", f"-{n}", "--format=%h %ad %s", "--date=short", rev, "--", path, check=False)
    return [l for l in out.splitlines() if l]


def churn(repo: str, rev: str, path: str, limit: int = 300) -> int:
    out = git(repo, "log", f"-{limit}", "--format=%h", rev, "--", path, check=False)
    return len([l for l in out.splitlines() if l])


def rev_sha(repo: str, rev: str) -> str:
    return git(repo, "rev-parse", rev, check=False).strip()
