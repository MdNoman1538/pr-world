"""Data shapes used across the pipeline.

Two groups:
- LLM output schemas (SpecialistOutput, ValidatorOutput): kept deliberately simple
  (strings, numbers, enums, lists) so Gemini's structured-output mode accepts them.
- Internal records (Finding, AreaResult, Review, ...): what the pipeline stores and reports.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- enums
class Severity(str, Enum):
    BLOCKER = "Blocker"        # correctness / safety error: may lock the merge
    SHOULD_FIX = "ShouldFix"   # maintainability debt: never locks on its own
    NIT = "Nit"                # optional polish: suppressed by default


class Dimension(str, Enum):
    CORRECTNESS = "correctness"
    ARCHITECTURE = "architecture"
    SAFETY = "safety"
    TESTS = "tests"
    MAINTAINABILITY = "maintainability"
    PERFORMANCE = "performance"


class Alignment(str, Enum):
    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


class AreaStatus(str, Enum):
    VERIFIED = "verified"      # closed with evidence by tools/AI
    HUMAN = "human"            # needs a named human to check and sign
    BLOCKED = "blocked"        # a rule is broken: merge locked
    NOT_CHECKED = "not_checked"  # the check that covers this area did not run (off, failed or out of budget)


class Tier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


TIER_ORDER = {Tier.LOW: 0, Tier.MEDIUM: 1, Tier.HIGH: 2}


# ------------------------------------------------------------ LLM output schemas
class LLMFinding(BaseModel):
    title: str = Field(description="One-line summary of the problem")
    claim: str = Field(description="What is wrong and why it matters, 1-3 sentences")
    severity: Severity
    file: str = Field(description="Repo-relative path exactly as shown in the context")
    line_start: int = Field(description="Line number in the NEW file version, as tagged in the context")
    line_end: int
    evidence: str = Field(description="Exact code copied from the context that shows the problem")
    requirement_link: str = Field(description="Requirement sentence this relates to, or 'none'")
    confidence: float = Field(description="0.0-1.0, how sure you are this is a real problem")
    suggested_fix: str = Field(description="Short concrete fix, or empty")


class LLMRefusal(BaseModel):
    topic: str = Field(description="What you could not decide")
    reason: str = Field(description="Why it cannot be decided from the evidence available")


class SpecialistOutput(BaseModel):
    orientation: str = Field(description="Phase 1: what the change does and why it exists, in 2-4 sentences")
    requirement_alignment: Alignment
    alignment_reason: str
    findings: List[LLMFinding]
    refusals: List[LLMRefusal]
    checked: List[str] = Field(description="Checklist items you actually examined")


class ValidatorVerdict(BaseModel):
    finding_id: str
    q1_nitpick: bool = Field(description="Q1 nitpick check: is this only a cosmetic suggestion or formatting/style preference?")
    q2_hallucination: bool = Field(description="Q2 hallucination check: does it describe a non-existent bug or make wrong "
                                               "assumptions about the surrounding code?")
    q3_severity: Severity = Field(description="Q3 severity scoring: the true technical impact")
    duplicate_of: str = Field(description="finding_id of a kept finding this repeats, or empty")
    reason: str = Field(description="Short chain-of-thought summary of the decision")


class ValidatorOutput(BaseModel):
    verdicts: List[ValidatorVerdict]


class RadarItem(BaseModel):
    id: str = Field(description="R1, R2, ... one per acceptance criterion / requirement statement")
    text: str = Field(description="The requirement statement, short")
    status: str = Field(description="covered | partial | missing")
    hunk_ids: List[str] = Field(description="Hunks that implement or test this item")
    reason: str


class RadarHunk(BaseModel):
    hunk_id: str
    classification: str = Field(description="aligned | supporting | tangled | unclear")
    item_ids: List[str]
    reason: str


class RadarOutput(BaseModel):
    items: List[RadarItem]
    hunks: List[RadarHunk]


class FixProposal(BaseModel):
    finding_id: str
    file: str
    old_code: str = Field(description="Exact contiguous lines copied from the NEW file version to replace")
    new_code: str = Field(description="Replacement lines")
    explanation: str
    confidence: float


class FixOutput(BaseModel):
    fixes: List[FixProposal]


# ---------------------------------------------------------------- internal records
class Finding(BaseModel):
    id: str
    dimension: Dimension
    source: str                      # "specialist:<dim>" or "sensor:<name>"
    title: str
    claim: str
    severity: Severity
    file: str = ""
    line_start: int = 0
    line_end: int = 0
    evidence: str = ""
    requirement_link: str = "none"
    confidence: float = 1.0
    suggested_fix: str = ""
    evidence_verified: Optional[bool] = None   # deterministic check of file/line/snippet
    validator: Optional[dict] = None           # Q1-Q3 verdict
    kept: bool = True
    drop_reason: str = ""
    anchor: List[List] = []                    # [[line_no, text, changed?], ...] code around the cited line
    patch: str = ""                            # unified diff from the fix agent (applies to PR head)
    patch_explanation: str = ""
    delta: str = ""                            # new | still-open (iteration delta)


class Refusal(BaseModel):
    source: str
    topic: str
    reason: str


class SensorResult(BaseModel):
    name: str
    ran: bool
    passed: Optional[bool] = None
    summary: str
    details: List[str] = []
    log_file: str = ""                         # evidence bundle: full log, relative to the run folder


class AreaResult(BaseModel):
    area: str
    status: AreaStatus
    reason: str
    evidence: List[str] = []


class TierDecision(BaseModel):
    tier: Tier
    reasons: List[str]
    guarded_paths: List[str] = []
    out_of_plan: List[str] = []
    signoffs_required: int = 1


class Review(BaseModel):
    run_id: str
    created_at: str
    repo: str
    base: str
    head: str
    requirement_id: str
    requirement_text_present: bool
    owner: str
    policy_version: str
    policy_approved_by: Optional[str]
    models: dict
    changed_files: List[str]
    tier: TierDecision
    orientation: str
    requirement_alignment: str
    sensors: List[SensorResult]
    findings: List[Finding]
    dropped_findings: List[Finding]
    refusals: List[Refusal]
    areas: List[AreaResult]
    decision: str                    # BLOCKED | NEEDS_HUMAN | READY_FOR_SIGNOFF (never "approved")
    decision_reason: str
    not_checked: List[str]
    track_record: dict = {}
    head_sha: str = ""
    radar: Optional[dict] = None     # requirement radar: items + hunks
    funnel: dict = {}                # proposed → evidence-verified → validator-kept → shown
    familiarity: dict = {}           # path -> {recent_commits, past_findings}
    delta: dict = {}                 # iteration delta vs the previous review of this branch
    optimization_context: bool = False
    commit_messages: List[str] = []
    ai_error: str = ""               # set when the model calls failed: the review is code-only
    # v3 platform
    settings: dict = {}              # fingerprint, badge, preset, warnings (what this review ran with)
    coverage: dict = {}              # per area: level, plugins on, plugins off (why)
    plugins_run: List[str] = []
    not_checked_plugins: List[dict] = []   # [{plugin, area, reason}]
    requirement_check: Optional[dict] = None
    panel: Optional[dict] = None
    investigations: Optional[dict] = None
    cost: dict = {}                  # model calls, cost, by role, budget
    integrations: List[dict] = []    # what was posted where (or dry-run payloads)
