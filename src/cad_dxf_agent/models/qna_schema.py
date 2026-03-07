"""Q&A domain models — question types, region context, and structured answers.

Deterministic Q&A pipeline types. No LLM dependency — all classification
and answer generation uses keyword patterns and template formatting.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .cad_schema import EntityRef
from .region_schema import BoundingBox
from .response_schema import EvidenceRef


class QnaQuestionType(StrEnum):
    """Classified question types for deterministic answer generation."""

    ENTITY_LIST = "entity_list"
    TEXT_SEARCH = "text_search"
    LAYER_QUERY = "layer_query"
    REGION_SUMMARY = "region_summary"
    ENTITY_COUNT = "entity_count"
    DIMENSION_QUERY = "dimension_query"
    BLOCK_QUERY = "block_query"
    ENTITY_LOOKUP = "entity_lookup"


class RegionContext(BaseModel):
    """Pre-built context for a region (or whole drawing) ready for Q&A."""

    entities: list[EntityRef] = Field(default_factory=list)
    text_entities: list[EntityRef] = Field(default_factory=list)
    dimension_entities: list[EntityRef] = Field(default_factory=list)
    block_refs: list[EntityRef] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    layer_counts: dict[str, int] = Field(default_factory=dict)
    block_names: list[str] = Field(default_factory=list)
    entity_count: int = 0
    total_drawing_entities: int = 0
    confidence: float = 1.0
    ambiguity_flags: list[str] = Field(default_factory=list)
    is_whole_drawing: bool = False
    bounds: BoundingBox | None = None


class QnaAnswer(BaseModel):
    """Structured answer from the deterministic Q&A pipeline."""

    question_type: QnaQuestionType
    answer_text: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = 1.0
    ambiguity_flags: list[str] = Field(default_factory=list)
    entity_count: int = 0
    region_context_summary: dict[str, Any] = Field(default_factory=dict)
