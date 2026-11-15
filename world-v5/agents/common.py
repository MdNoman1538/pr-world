"""Shared helpers for the Loan-world agents. No secrets are ever printed or written."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "plan"
BANK = ROOT / "bank"
RUNS = ROOT / "runs"
VIEW = ROOT / "viewer" / "data"
SEED = ROOT / "seed"
REVIEWER = ROOT.parent / "ai-reviewer"

sys.path.insert(0, str(REVIEWER / "backend"))   # reuse the reviewer's Gemini client (structured output + audit log)


def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_env() -> None:
    """Read ../ai-reviewer/.env into the environment (values are never printed)."""
    env = REVIEWER / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def models() -> Dict[str, str]:
    strong = os.environ.get("GEMINI_STRONG_MODEL", "gemini-4-hydrogen")
    fast = os.environ.get("GEMINI_FAST_MODEL", "gemini-3.8-flash")
    return {"builder": strong, "planter": strong, "requirement": fast, "tester": fast, "reviewer": fast, "meaning": fast}


def sh(cmd: List[str], cwd: Path = BANK, timeout: int = 1200, env: Optional[Dict] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **(env or {})})
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, f"timeout after {timeout}s: {' '.join(cmd)}\n{e}"
    except FileNotFoundError as e:
        return 127, str(e)


def git(*args: str, cwd: Path = BANK, author: Optional[str] = None) -> str:
    cmd = ["git"]
    if author:
        name, email = author.split("|")
        cmd += ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    code, out = sh(cmd + list(args), cwd=cwd, timeout=120)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{out}")
    return out.strip()


def dotnet_major() -> Optional[int]:
    code, out = sh(["dotnet", "--version"], cwd=ROOT, timeout=60)
    if code != 0:
        return None
    m = re.match(r"(\d+)\.", out.strip())
    return int(m.group(1)) if m else None


def in_scope(path: str, globs: List[str]) -> bool:
    path = path.replace("\\", "/").lstrip("./")
    if ".." in Path(path).parts or path.startswith("/"):
        return False
    return any(fnmatch.fnmatch(path, g) for g in globs)


def read_tree(globs: List[str], root: Path = BANK) -> Dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "/bin/" in str(p) or "/obj/" in str(p) or "/.git/" in str(p):
            continue
        rel = p.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(rel, g) for g in globs):
            out[rel] = p.read_text(encoding="utf-8")
    return out


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def compile_errors(output: str, limit: int = 30) -> List[str]:
    seen, out = set(), []
    for line in output.splitlines():
        m = re.search(r"([^\s:]+\.cs)\((\d+),\d+\): error (CS\d+): (.+?)(?: \[.*\])?$", line)
        if m:
            key = (m.group(1).split("/bank/")[-1], m.group(2), m.group(3))
            if key in seen:
                continue
            seen.add(key)
            out.append(f"{key[0]}:{m.group(2)} {m.group(3)} {m.group(4)}")
        elif " error " in line and "error CS" not in line and len(out) < limit:
            out.append(line.strip()[:300])
        if len(out) >= limit:
            break
    return out


def tolerant_replace(text: str, find: str, replace: str) -> Optional[str]:
    """Replace `find` once, ignoring indentation differences. Returns None if not found exactly once."""
    if find and text.count(find) == 1:
        return text.replace(find, replace)
    flines = [l.strip() for l in find.strip("\n").splitlines() if l.strip()]
    if not flines:
        return None
    lines = text.splitlines(keepends=True)
    stripped = [l.strip() for l in lines]
    hits = [i for i in range(len(lines) - len(flines) + 1) if stripped[i:i + len(flines)] == flines]
    if len(hits) != 1:
        return None
    i = hits[0]
    indent = re.match(r"\s*", lines[i]).group(0)
    rep = ""
    if replace.strip():
        rlines = replace.strip("\n").splitlines()
        base = min((len(l) - len(l.lstrip()) for l in rlines if l.strip()), default=0)
        rep = "".join(indent + l[base:] + "\n" for l in rlines)
    return "".join(lines[:i]) + rep + "".join(lines[i + len(flines):])
