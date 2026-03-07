"""Schemas for repeated-condition detection (EPIC-CAD-05).

Defines similarity signals, candidate matches, and result containers
for finding repeated conditions in drawings.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .cad_schema import Point2D
from .response_schema import EvidenceRef


class SimilaritySignalType(StrEnum):
    """Types of similarity signals used in repeated-condition scoring."""

    BLOCK_NAME = "block_name"
    TEXT_CONTENT = "text_content"
    GEOMETRY_SHAPE = "geometry_shape"
    LAYER_CONTEXT = "layer_context"
    SPATIAL_PATTERN = "spatial_pattern"
    TEXT_GEOMETRY = "text_geometry"


class ApprovalState(StrEnum):
    """User approval state for a candidate match."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SimilaritySignal(BaseModel):
    """One scoring signal contributing to a match confidence."""

    signal_type: SimilaritySignalType
    score: float = Field(ge=0.0, le=1.0, description="Raw signal score [0-1]")
    weight: float = Field(ge=0.0, le=1.0, description="Signal weight in final score")
    detail: str = ""
    trust_level: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Trust multiplier from text provenance"
    )

    @property
    def weighted_score(self) -> float:
        """Effective contribution: score * weight * trust_level."""
        return self.score * self.weight * self.trust_level


class ConditionMatch(BaseModel):
    """A candidate match for a repeated condition."""

    entity_handles: list[str] = Field(description="Handles of entities in this match")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall match confidence")
    signals: list[SimilaritySignal] = Field(default_factory=list)
    centroid: Point2D
    evidence: list[EvidenceRef] = Field(default_factory=list)
    explanation: str = ""
    approval_state: ApprovalState = ApprovalState.PENDING


class SimilarityConfig(BaseModel):
    """Configuration for repeated-condition search."""

    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    max_results: int = Field(default=50, ge=1)
    search_radius_multiplier: float = Field(
        default=1.5, ge=1.0, description="Multiplied by exemplar radius for search scope"
    )
    block_name_weight: float = 0.30
    text_content_weight: float = 0.25
    geometry_shape_weight: float = 0.20
    layer_context_weight: float = 0.10
    spatial_pattern_weight: float = 0.10
    text_geometry_weight: float = 0.05
    single_entity_min_confidence: float = Field(
        default=0.70, description="Min confidence for single-entity matches"
    )
    block_only_cap: float = Field(
        default=0.80, description="Max confidence for block-only matches without text"
    )
    ambiguity_threshold: float = Field(
        default=0.05, description="Confidence gap below which matches are flagged ambiguous"
    )


class RepeatedConditionResult(BaseModel):
    """Complete result of a repeated-condition search."""

    exemplar_handles: list[str]
    exemplar_centroid: Point2D
    candidates: list[ConditionMatch] = Field(default_factory=list)
    total_found: int = 0
    search_radius: float = 0.0
    summary: str = ""
    ambiguity_flags: list[str] = Field(default_factory=list)
    config: SimilarityConfig = Field(default_factory=SimilarityConfig)
