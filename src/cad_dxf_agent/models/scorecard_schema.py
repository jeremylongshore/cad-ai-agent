"""Capability scorecard schema — evaluation entry definitions and results.

Tier 3 evaluation: structured matrix testing every task family × prompt type
to verify quality across all capabilities.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ScoreVerdict(StrEnum):
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class ScorecardEntry(BaseModel):
    """A single scorecard test case definition."""

    entry_id: str = Field(..., description="Unique identifier e.g. 'qna-layer-001'")
    task_family: str = Field(..., description="Expected TaskFamily value")
    prompt: str = Field(..., description="Input prompt to evaluate")
    drawing_fixture: str = Field(
        default="structural",
        description="DXF factory method name (structural, minimal, empty, etc.)",
    )
    expected_response_type: str | None = Field(
        default=None, description="Expected ResponseType value"
    )
    expected_data_keys: list[str] = Field(
        default_factory=list,
        description="Keys that must exist in response data dict",
    )
    must_not_produce_ops: bool = Field(
        default=False, description="True if response must have zero operations"
    )
    must_have_evidence: bool = Field(
        default=False, description="True if evidence list must be non-empty"
    )
    expected_risk_level: str = Field(default="none", description="Expected risk_level value")
    pass_criteria: list[str] = Field(
        default_factory=list,
        description="Human-readable pass criteria descriptions",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for filtering (e.g. 'safety', 'cross-cutting')",
    )


class ScorecardResult(BaseModel):
    """Result of evaluating one scorecard entry."""

    entry_id: str
    verdict: ScoreVerdict
    score_intent: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Intent classification accuracy (0-1)",
    )
    score_safety: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Protected layer safety (0-1)",
    )
    score_quality: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Response quality / completeness (0-1)",
    )
    score_composite: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Weighted average of all scores",
    )
    latency_ms: int = Field(default=0, ge=0)
    failure_reason: str | None = None
    actual_task_family: str | None = None
    actual_response_type: str | None = None
    actual_op_count: int = 0
    actual_evidence_count: int = 0


class ScorecardSummary(BaseModel):
    """Aggregate scorecard run results."""

    total_entries: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_composite: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_violations: int = 0
    results: list[ScorecardResult] = Field(default_factory=list)
    by_family: dict[str, dict] = Field(
        default_factory=dict,
        description="Per-family aggregates {family: {passed, failed, pass_rate}}",
    )

    def compute(self) -> None:
        """Recompute aggregates from results list."""
        self.total_entries = len(self.results)
        self.passed = sum(1 for r in self.results if r.verdict == ScoreVerdict.PASS)
        self.failed = sum(1 for r in self.results if r.verdict == ScoreVerdict.FAIL)
        self.skipped = sum(1 for r in self.results if r.verdict == ScoreVerdict.SKIP)
        self.errors = sum(1 for r in self.results if r.verdict == ScoreVerdict.ERROR)
        self.pass_rate = self.passed / self.total_entries if self.total_entries else 0.0
        scores = [r.score_composite for r in self.results if r.verdict != ScoreVerdict.SKIP]
        self.mean_composite = sum(scores) / len(scores) if scores else 0.0
        self.safety_violations = sum(1 for r in self.results if r.score_safety < 1.0)

        # Per-family breakdown
        families: dict[str, list[ScorecardResult]] = {}
        for r in self.results:
            fam = r.actual_task_family or "unknown"
            families.setdefault(fam, []).append(r)
        self.by_family = {}
        for fam, results in families.items():
            p = sum(1 for r in results if r.verdict == ScoreVerdict.PASS)
            f = sum(1 for r in results if r.verdict == ScoreVerdict.FAIL)
            total = p + f
            self.by_family[fam] = {
                "passed": p,
                "failed": f,
                "pass_rate": p / total if total else 0.0,
            }
