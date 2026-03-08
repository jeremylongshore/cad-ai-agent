"""Objective intelligence models for two-axis intent classification.

Defines RequestClass (8 values), ObjectiveTag (15 values), DocumentFamilyHint (20 families),
AnalysisResult, RecommendationSet, and StageGate models for the multi-stage
reasoning pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RequestClass(StrEnum):
    """Primary request class — what kind of response the user needs.

    8 values covering all user intent categories.
    """

    UNDERSTAND = "understand"
    ESTIMATE = "estimate"
    RECOMMEND = "recommend"
    OPTIMIZE = "optimize"
    MODIFY = "modify"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    VALIDATE = "validate"


class ObjectiveTag(StrEnum):
    """Domain context — what the user is trying to achieve.

    15 values covering cross-family objectives.
    """

    COST_REDUCTION = "cost_reduction"
    LABOR_REDUCTION = "labor_reduction"
    AREA_CHANGE = "area_change"
    AESTHETICS = "aesthetics"
    QUANTITY_ESTIMATION = "quantity_estimation"
    CUSTOMER_COMMUNICATION = "customer_communication"
    CONTRACTOR_COMMUNICATION = "contractor_communication"
    REVIEWER_COMMUNICATION = "reviewer_communication"
    CONSTRUCTABILITY = "constructability"
    COMPLIANCE = "compliance"
    REVISION_EXPLANATION = "revision_explanation"
    SPACE_COUNT = "space_count"
    EQUIPMENT_COUNT = "equipment_count"
    LAYOUT_IMPROVEMENT = "layout_improvement"
    MISSING_ITEMS = "missing_items"


class DocumentFamilyHint(StrEnum):
    """Inferred document family — refines output phrasing, never gates capability.

    20 families detected from layer names, block names, and text content.
    """

    RESIDENTIAL_ARCHITECTURAL = "residential_architectural"
    COMMERCIAL_ARCHITECTURAL = "commercial_architectural"
    STRUCTURAL = "structural"
    CIVIL_SITE = "civil_site"
    LANDSCAPE = "landscape"
    ELECTRICAL = "electrical"
    MECHANICAL = "mechanical"
    PLUMBING = "plumbing"
    FIRE_SAFETY = "fire_safety"
    INTERIOR_DESIGN = "interior_design"
    KITCHEN_BATH = "kitchen_bath"
    PERMIT_SET = "permit_set"
    AS_BUILT = "as_built"
    SHOP_FABRICATION = "shop_fabrication"
    FACILITY_MAINTENANCE = "facility_maintenance"
    SURVEY_BOUNDARY = "survey_boundary"
    CONSTRUCTION_LOGISTICS = "construction_logistics"
    SOLAR_ENERGY = "solar_energy"
    SIGNAGE_WAYFINDING = "signage_wayfinding"
    UNKNOWN = "unknown"


class ObjectiveClassification(BaseModel):
    """Result of two-axis objective classification."""

    request_class: RequestClass
    objective_tag: ObjectiveTag | None = None
    document_family: DocumentFamilyHint = DocumentFamilyHint.UNKNOWN
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "heuristic"
    matched_patterns: list[str] = Field(default_factory=list)
    classification_time_ms: float = 0.0


class AnalysisResult(BaseModel):
    """Output of the analyze stage — evidence-based drawing analysis."""

    summary: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    cost_drivers: list[dict[str, Any]] = Field(default_factory=list)
    area_metrics: dict[str, float] = Field(default_factory=dict)
    quantity_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class RecommendationOption(BaseModel):
    """A single recommendation with tradeoffs."""

    title: str
    description: str
    estimated_impact: str
    tradeoffs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    operations_hint: list[str] = Field(default_factory=list)


class RecommendationSet(BaseModel):
    """Output of the recommend stage — ranked options for the user."""

    options: list[RecommendationOption] = Field(default_factory=list)
    selected_index: int | None = None


class StageGate(BaseModel):
    """Checkpoint between pipeline stages — inspectable by the user."""

    stage_name: str
    status: Literal["pending", "active", "completed", "rejected", "skipped"] = "pending"
    output_summary: str = ""
    requires_user_input: bool = False
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    output_data: dict[str, Any] = Field(default_factory=dict)


class StagePipelineDefinition(BaseModel):
    """Defines which stages run for a given (class, objective) pair."""

    stages: list[str]  # e.g. ["analyze", "recommend", "plan", "preview"]
    output_mode: str = "full"  # "direct", "staged", "full"
    description: str = ""
