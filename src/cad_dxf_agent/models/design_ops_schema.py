"""Design operations schemas — layout recommendations, revision summaries,
takeoff candidates, and scope-style summary outputs.

All deterministic (no LLM). Outputs surface confidence, caveats, and evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .cad_schema import TextProvenance
from .response_schema import EvidenceRef

# ---------------------------------------------------------------------------
# 09.1 — Layout Recommendations
# ---------------------------------------------------------------------------


class RecommendationType(StrEnum):
    REGION_USAGE = "region_usage"
    PLACEMENT_GUIDANCE = "placement_guidance"
    LAYOUT_ALTERNATIVE = "layout_alternative"
    GENERAL_OBSERVATION = "general_observation"


class LayoutRecommendation(BaseModel):
    type: RecommendationType
    title: str
    description: str
    rationale: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    affected_layers: list[str] = Field(default_factory=list)
    affected_region: str | None = None


class LayoutRecommendationResult(BaseModel):
    recommendations: list[LayoutRecommendation] = Field(default_factory=list)
    drawing_summary: str = ""
    methodology: str = "deterministic_analysis"
    total_recommendations: int = 0
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_flags: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 09.2 — Customer-Facing Revision Summaries
# ---------------------------------------------------------------------------


class ChangeSummaryEntry(BaseModel):
    change_type: str  # "added", "removed", "modified", "moved"
    plain_description: str
    technical_detail: str = ""
    layer: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CustomerRevisionSummary(BaseModel):
    headline: str
    key_changes: list[ChangeSummaryEntry] = Field(default_factory=list)
    overall_assessment: str = ""
    change_count: int = 0
    areas_affected: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 09.3 — Takeoff Candidate Generation
# ---------------------------------------------------------------------------


class TakeoffConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ESTIMATE_ONLY = "estimate_only"


class TakeoffItem(BaseModel):
    name: str
    quantity: int
    unit: str | None = None
    source_layer: str
    source_block_name: str | None = None
    entity_handles: list[str] = Field(default_factory=list)
    confidence: TakeoffConfidence = TakeoffConfidence.MEDIUM
    caveats: list[str] = Field(default_factory=list)
    text_provenance: TextProvenance | None = None


class TakeoffCandidateResult(BaseModel):
    items: list[TakeoffItem] = Field(default_factory=list)
    methodology: str = "entity_counting"
    total_items: int = 0
    total_quantity_items: int = 0
    aggregate_confidence: TakeoffConfidence = TakeoffConfidence.MEDIUM
    ambiguity_flags: list[str] = Field(default_factory=list)
    provenance_warnings: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 09.4 — Scope-Style Summary
# ---------------------------------------------------------------------------


class ScopeSectionType(StrEnum):
    LAYOUT_RECOMMENDATIONS = "layout_recommendations"
    REVISION_SUMMARY = "revision_summary"
    TAKEOFF_CANDIDATES = "takeoff_candidates"
    GENERAL_NOTES = "general_notes"


class ScopeSection(BaseModel):
    section_type: ScopeSectionType
    title: str
    content: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)


class ScopeSummary(BaseModel):
    title: str = "Design Operations Scope Summary"
    sections: list[ScopeSection] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_flags: list[str] = Field(default_factory=list)
    omitted_sections: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
