#!/usr/bin/env python3
"""AI Reviewer — command line.

  python review.py check                         # environment check
  python review.py review --repo ../junction26-messagepack-csharp --base master --head ju26-issue-2283 \
         --req-id ISSUE-2283 --issue MessagePack-CSharp/MessagePack-CSharp#2283 --owner "Your Name"
  python review.py draft-policy --repo ../junction26-messagepack-csharp --rev master
  python review.py feedback <run_id> <finding_id> accepted|rejected --by "Your Name" [--note "..."]
  python review.py escape <run_id> <dimension> --note "bug found after merge" --by "Your Name"
  python review.py stats
  python review.py models
  python review.py api                            # backend JSON API on http://127.0.0.1:8765 (UI is ../frontend)
  python review.py bundle <run_id>                # rewrite runs/<run_id>/bundle.json for the frontend

See MANUAL.md for the full guide.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reviewer.models import Dimension  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.environ.get("GEMINI_FAST_MODEL", "gemini-3.8-flash")
STRONG = os.environ.get("GEMINI_STRONG_MODEL", "gemini-4-hydrogen")


def cmd_ping(a) -> int:
    """One tiny structured call per model: proves the key AND the model names work before a long run."""
    from pydantic import BaseModel
    from reviewer.llm import GeminiClient

    class Pong(BaseModel):
        ok: bool

    client = GeminiClient(max_retries=1)
    bad = 0
    for role, model in (("fast", a.fast_model), ("strong", a.strong_model)):
        try:
            client.generate(role="ping", model=model, system="Reply with ok=true.", prompt="ping", schema=Pong)
            print(f"  OK  {role} model {model}")
        except Exception as e:
            bad += 1
            msg = str(e)
            print(f"  --  {role} model {model}: {msg[:300]}")
            import re as _re
            m = _re.search(r"use (models/)?([\w.\-]+) for", msg)
            if m:
                print(f"      → the API suggests '{m.group(2)}'. Put GEMINI_{role.upper()}_MODEL={m.group(2)} in .env")
    return 1 if bad else 0


def cmd_check(_args) -> int:
    ok = True

    def row(name, good, info):
        nonlocal ok
        ok &= good or name.startswith("(optional)")
        print(f"  {'OK ' if good else '-- '} {name}: {info}")

    print("Environment check")
    row("python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])
    row("git", shutil.which("git") is not None, shutil.which("git") or "not found")
    for mod, pip in (("pydantic", "pydantic"), ("yaml", "pyyaml")):
        try:
            __import__(mod)
            row(pip, True, "installed")
        except ImportError:
            row(pip, False, f"pip install {pip}")
    try:
        from google import genai  # noqa: F401
        row("google-genai", True, "installed")
    except ImportError:
        row("google-genai", False, "pip install google-genai")
    from reviewer.context import TREE_SITTER
    row("(optional) tree-sitter C#", TREE_SITTER, "installed (precise AST slices)" if TREE_SITTER else
        "pip install tree-sitter tree-sitter-c-sharp  (fallback slicer is used otherwise)")
    row("(optional) dotnet SDK", shutil.which("dotnet") is not None,
        shutil.which("dotnet") or "not found (build/test sensors unavailable)")
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    row("GEMINI_API_KEY", bool(key), "set" if key else "not set: export GEMINI_API_KEY=...")
    print(f"  models: fast={FAST}  strong={STRONG}  (override with GEMINI_FAST_MODEL / GEMINI_STRONG_MODEL)")
    print("Ready." if ok else "Fix the items marked -- above.")
    return 0 if ok else 1


def cmd_models(_args) -> int:
    from reviewer.llm import GeminiClient
    for m in GeminiClient().list_models():
        print(m)
    return 0


def cmd_review(a) -> int:
    from reviewer.orchestrator import Options, run_review
    opts = Options(
        repo=a.repo, base=a.base, head=a.head, requirement_id=a.req_id, requirement_file=a.req_file,
        issue=a.issue, owner=a.owner, plan=a.plan, policy=a.policy, strategy=a.strategy,
        dimensions=a.dimensions.split(",") if a.dimensions else [d.value for d in Dimension],
        build=a.build, test=a.test, build_target=a.build_target, test_target=a.test_target,
        test_filter=a.test_filter, timeout=a.timeout, offline=a.offline,
        mock=(a.mock if a.mock is not None else None), fast_model=a.fast_model, strong_model=a.strong_model,
        temperature=a.temperature, out_dir=a.out, memory_path=a.memory, max_context_chars=a.max_context_chars,
        workers=a.workers, radar=not a.no_radar, fixes=not a.no_fixes,
        config=a.config, pr_number=a.pr_number, issue_key=a.issue_key)
    review = run_review(opts)
    if review.ai_error:
        return 3
    return {"BLOCKED": 2, "NEEDS_HUMAN": 1, "READY_FOR_SIGNOFF": 0}.get(review.decision, 1) if a.exit_code else 0


def cmd_draft_policy(a) -> int:
    from reviewer.llm import make_client
    from reviewer.policy_draft import collect_signals, heuristic_draft, llm_draft, write_draft
    print(f"[reviewer] collecting signals from {a.repo}@{a.rev} ...")
    signals = collect_signals(a.repo, a.rev)
    if a.llm:
        client = make_client(a.mock, None, 0.1)
        draft, source = llm_draft(client, a.model, signals), f"gemini:{a.model}"
    else:
        draft, source = heuristic_draft(signals), "heuristic"
    write_draft(draft, a.policy, a.out, source)
    print(f"[reviewer] wrote {a.out} ({len(draft.areas)} areas, source: {source}). "
          "Review it, edit it, set approved_by, then use it with --policy.")
    return 0


def cmd_settings(a) -> int:
    from reviewer.platform_config import ConfigError, list_presets, load_config, schema_json
    if a.action == "schema":
        print(schema_json())
        return 0
    if a.action == "presets":
        for p in list_presets():
            print(f"{p['name']:14} {p['about']}")
        return 0
    try:
        c = load_config(a.path)
    except ConfigError as e:
        print("Refused:\n" + str(e))
        return 2
    print(f"OK · {c.badge()}")
    for w in c.warnings:
        print("warning:", w)
    return 0


def cmd_feedback(a) -> int:
    from reviewer.memory import Memory
    ok = Memory(a.memory).feedback(a.run_id, a.finding_id, a.verdict, a.note or "", a.by)
    print("recorded" if ok else "no such run/finding")
    return 0 if ok else 1


def cmd_escape(a) -> int:
    from reviewer.memory import Memory
    Memory(a.memory).escape(a.run_id, a.dimension, a.note, a.by)
    print("escape recorded: trust in this dimension is lowered until precision recovers")
    return 0


def cmd_stats(a) -> int:
    from reviewer.memory import Memory
    m = Memory(a.memory)
    print(json.dumps({"totals": m.totals(), "track_record": m.track_record()}, indent=2))
    return 0


def cmd_api(a) -> int:
    from reviewer.api import serve_api
    serve_api(a.runs, a.memory, a.port, a.allow_origin)
    return 0


def cmd_bundle(a) -> int:
    from reviewer.api import write_bundle
    from reviewer.memory import Memory
    run_dir = a.run if os.path.isdir(a.run) else os.path.join(a.runs, a.run)
    if not os.path.exists(os.path.join(run_dir, "review.json")):
        print(f"no review.json in {run_dir}")
        return 1
    print(write_bundle(run_dir, Memory(a.memory)))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Evidence-first AI reviewer for agent-written pull requests")
    p.add_argument("--memory", default=os.path.join(HERE, ".reviewer", "memory.db"), help="SQLite memory file")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="check the environment").set_defaults(fn=cmd_check)
    sub.add_parser("models", help="list Gemini models available to your key").set_defaults(fn=cmd_models)
    pg = sub.add_parser("ping", help="test the key and both model names with one tiny call each")
    pg.add_argument("--fast-model", default=FAST)
    pg.add_argument("--strong-model", default=STRONG)
    pg.set_defaults(fn=cmd_ping)

    r = sub.add_parser("review", help="review one PR (base...head)")
    r.add_argument("--repo", required=True, help="path to a local git clone")
    r.add_argument("--base", required=True, help="target branch, e.g. master or main")
    r.add_argument("--head", required=True, help="PR branch, e.g. ju26-issue-2283")
    r.add_argument("--req-id", default="UNSPECIFIED", help="requirement ID shown in the report")
    r.add_argument("--req-file", help="requirement text file (markdown)")
    r.add_argument("--issue", help="fetch requirement from GitHub: owner/repo#123")
    r.add_argument("--owner", default="UNASSIGNED", help="named human accountable for this PR")
    r.add_argument("--plan", help="YAML with allowed_paths: [...] (approved scope)")
    r.add_argument("--policy", default=os.path.join(HERE, "review-policy.yaml"))
    r.add_argument("--strategy", default="leftflow", choices=["diff", "parent", "leftflow", "fullflow"])
    r.add_argument("--dimensions", help="comma list, default all: " + ",".join(d.value for d in Dimension))
    r.add_argument("--build", action="store_true", help="run dotnet build on the PR head (temp worktree)")
    r.add_argument("--test", action="store_true", help="run dotnet test on the PR head (temp worktree)")
    r.add_argument("--build-target", help="project/solution to build (default: repo root)")
    r.add_argument("--test-target", help="test project to run")
    r.add_argument("--test-filter", help="dotnet test --filter expression")
    r.add_argument("--timeout", type=int, default=1800, help="seconds per dotnet command")
    r.add_argument("--offline", action="store_true", help="skip network sensors (nuget check)")
    r.add_argument("--mock", nargs="?", const="", default=None,
                   help="no Gemini calls; optional fixture JSON with canned model answers")
    r.add_argument("--fast-model", default=FAST, help="model for the 5 specialists")
    r.add_argument("--strong-model", default=STRONG, help="model for the validator")
    r.add_argument("--temperature", type=float, default=0.1)
    r.add_argument("--out", default=os.path.join(HERE, "runs"))
    r.add_argument("--max-context-chars", type=int, default=120_000)
    r.add_argument("--workers", type=int, default=6, help="parallel specialist calls (use 1-2 on a free-tier key)")
    r.add_argument("--no-radar", action="store_true", help="skip the requirement radar")
    r.add_argument("--no-fixes", action="store_true", help="skip the fix-suggestion agent")
    r.add_argument("--config", help="team settings file (prworld.yaml). Default: Full coverage, Gemini, no integrations")
    r.add_argument("--pr-number", help="PR/MR number, used to post the summary (integrations)")
    r.add_argument("--issue-key", help="Jira issue key, used to post the summary (integrations)")
    r.add_argument("--exit-code", action="store_true", help="exit 2=BLOCKED, 1=NEEDS_HUMAN, 0=READY (for CI)")
    r.set_defaults(fn=cmd_review)

    d = sub.add_parser("draft-policy", help="AI drafts a rulebook from repo signals (human approves)")
    d.add_argument("--repo", required=True)
    d.add_argument("--rev", default="HEAD")
    d.add_argument("--llm", action="store_true", help="use Gemini to draft (default: heuristic)")
    d.add_argument("--model", default=STRONG)
    d.add_argument("--mock", nargs="?", const="", default=None)
    d.add_argument("--policy", default=os.path.join(HERE, "review-policy.yaml"), help="base policy to copy rules from")
    d.add_argument("--out", default=os.path.join(HERE, "review-policy.draft.yaml"))
    d.set_defaults(fn=cmd_draft_policy)

    st = sub.add_parser("settings", help="check a team settings file (prworld.yaml) or print its schema")
    st.add_argument("action", choices=["check", "schema", "presets"])
    st.add_argument("path", nargs="?")
    st.set_defaults(fn=cmd_settings)

    f = sub.add_parser("feedback", help="record a human verdict on a finding")
    f.add_argument("run_id")
    f.add_argument("finding_id")
    f.add_argument("verdict", choices=["accepted", "rejected"])
    f.add_argument("--note")
    f.add_argument("--by", required=True)
    f.set_defaults(fn=cmd_feedback)

    e = sub.add_parser("escape", help="record a problem the reviewer missed (lowers trust)")
    e.add_argument("run_id")
    e.add_argument("dimension", choices=[x.value for x in Dimension])
    e.add_argument("--note", required=True)
    e.add_argument("--by", required=True)
    e.set_defaults(fn=cmd_escape)

    sub.add_parser("stats", help="reviewer track record").set_defaults(fn=cmd_stats)

    ap = sub.add_parser("api", help="start the backend JSON API for the dashboard (frontend is separate)")
    ap.add_argument("--runs", default=os.path.join(HERE, "runs"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--allow-origin", default="", help="exact frontend origin for CORS (default: any localhost)")
    ap.set_defaults(fn=cmd_api)

    bd = sub.add_parser("bundle", help="(re)write <run>/bundle.json, the data file the frontend reads")
    bd.add_argument("run", help="run id or path")
    bd.add_argument("--runs", default=os.path.join(HERE, "runs"))
    bd.set_defaults(fn=cmd_bundle)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
