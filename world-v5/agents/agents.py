"""The agents of the software company. Each one has a narrow job and its own model.

Requirement agent  (fast)   : brief -> issue with testable acceptance criteria
Builder            (strong) : issue + conventions + code -> complete files (fix loop on compile errors)
Bug planter        (strong) : hidden answer key -> smallest edit that inserts one defect (simulation only)
Test agent         (fast)   : issue + public contract ONLY -> xUnit tests (never sees the implementation)
Cartographer-AI    (fast)   : facts from the Cartographer -> one-line meaning per module/type (labelled as AI)
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class IssueOut(BaseModel):
    title: str
    user_story: str
    acceptance_criteria: List[str]
    out_of_scope: List[str]
    risks: List[str]


class FileChange(BaseModel):
    path: str
    content: str
    why: str


class BuilderOut(BaseModel):
    files: List[FileChange]
    commit_message: str
    notes: str


class Edit(BaseModel):
    path: str
    find: str
    replace: str


class PlantOut(BaseModel):
    edits: List[Edit]
    explanation: str


class TestOut(BaseModel):
    files: List[FileChange]
    notes: str


class Meaning(BaseModel):
    id: str
    summary: str


class MeaningOut(BaseModel):
    items: List[Meaning]


REQUIREMENT_SYSTEM = """You are the Requirement agent in a bank's software team.
Turn the product owner's brief into a precise issue for ONE pull request.
- Do not add features the brief does not ask for. Put tempting extras under out_of_scope.
- Every acceptance criterion must be testable and concrete (amounts, roles, error behaviour).
- Include the security and money rules the brief implies (who may do what; rounding).
- risks: what could go wrong for customers or the bank if this is built wrong."""

BUILDER_SYSTEM = """You are the Builder agent: a senior C# developer in a bank. You write production code for ONE pull request.
Rules:
- Follow the coding conventions exactly. Implement the issue and the public contract exactly (names, signatures, exceptions).
- Return the COMPLETE content of every file you create or change (no diffs, no placeholders, no '...').
- Only touch files inside the allowed scope. Never change tests. Never add NuGet packages.
- The code must compile against the existing code base you are given.
- Read the module's CONSTITUTION.md rules in the code base and follow them.
- Do not write comments that mention reviews, agents or simulations."""

PLANTER_SYSTEM = """You are the Bug planter in a TRAINING SIMULATION that measures whether reviewers catch defects.
Insert exactly ONE defect, as described, into the given code with the smallest natural-looking edit.
- No comments that hint at the defect. Keep the code compiling and the rest of the behaviour unchanged.
- Each edit: `find` must be copied VERBATIM from the file and appear exactly once; `replace` is the new text."""

TESTER_SYSTEM = """You are the Test agent. You have NOT seen the implementation and must not guess its internals.
Write xUnit tests from the requirement and the public contract ONLY.
- Cover every acceptance criterion, including negative cases (wrong user, wrong role, out-of-range amounts, invalid state).
- Use only the public contract, the platform API and the TestKit helpers you are given.
- Build all state through TestKit helpers, public constructors, public properties and the services in the contract.
  Never use reflection, never touch private members, never write raw SQL.
- Look entities up with simple queries (e.g. db.Payments.Single(p => p.Id == id)) after the service call.
- One file at the given path, in the namespace you are given, `using Xunit;`. Test names describe behaviour.
- Include boundary values (exactly at a limit, one cent over) and the people who must NOT be allowed.
- Never weaken a test to make it pass; you cannot run the code anyway."""

MEANING_SYSTEM = """You write the plain-language layer of a software map for bank reviewers.
For each element, write ONE short sentence saying what it is for, based only on the code facts given.
No speculation, no marketing words. If the facts are not enough, say what it is structurally."""


def issue_markdown(pr: dict, issue: IssueOut) -> str:
    ac = "\n".join(f"- [ ] {a}" for a in issue.acceptance_criteria)
    oos = "\n".join(f"- {a}" for a in issue.out_of_scope) or "- (none)"
    risks = "\n".join(f"- {a}" for a in issue.risks) or "- (none)"
    return (f"# {pr['id']}: {issue.title}\n\n**Story.** {issue.user_story}\n\n## Acceptance criteria\n{ac}\n\n"
            f"## Out of scope\n{oos}\n\n## Risks\n{risks}\n\n## Public contract\n```\n{pr['contract'].strip()}\n```\n\n"
            f"## Allowed scope\n" + "\n".join(f"- `{s}`" for s in pr["scope"]) + "\n\n"
            f"_Brief from the product owner:_ {pr['brief'].strip()}\n")


def template_issue(pr: dict) -> IssueOut:
    """Rehearsal mode: a deterministic issue built from the brief (no model call)."""
    sentences = [s.strip() for s in pr["brief"].replace("\n", " ").split(".") if s.strip()]
    return IssueOut(title=pr["title"], user_story=pr["brief"].strip(), acceptance_criteria=[s + "." for s in sentences],
                    out_of_scope=[], risks=["Rehearsal mode: issue generated from the brief without a model."])
