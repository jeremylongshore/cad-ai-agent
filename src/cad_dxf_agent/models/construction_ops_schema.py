"""Construction operations schemas -- grid/bay analysis, markup-to-redline reports,
batch condition detection, and field summaries.

All deterministic (no LLM). Outputs surface confidence, caveats, and evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .cad_schema import Point2D
from .response_schema import EvidenceRef

# ---------------------------------------------------------------------------
# 10.1 -- Grid / Bay Summary
# ---------------------------------------------------------------------------


class GridDirection(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class GridLine(BaseModel):
    direction: GridDirection
    label: str = ""
    position: float
    layer: str
    entity_handle: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Bay(BaseModel):
    label: str  # e.g. "A-B"
    direction: GridDirection
    start_line: str  # label of start grid line
    end_line: str  # label of end grid line
    dimension: float
    unit: str = "drawing_units"


class GridSummaryResult(BaseModel):
    grid_lines: list[GridLine] = Field(default_factory=list)
    bays: list[Bay] = Field(default_factory=list)
    drawing_summary: str = ""
    grid_pattern_description: str = ""
    methodology: str = "deterministic_grid_analysis"
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_flags: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 10.2 -- Markup-to-Redline
# ---------------------------------------------------------------------------


class RevisionCloudInfo(BaseModel):
    cloud_handle: str
    layer: str
    bounds: tuple[Point2D, Point2D]  # (min_point, max_point)
    vertex_count: int


class RedlineEntry(BaseModel):
    cloud: RevisionCloudInfo
    affected_entities: list[EvidenceRef] = Field(default_factory=list)
    affected_layers: list[str] = Field(default_factory=list)
    entity_count: int = 0
    description: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RedlineReportResult(BaseModel):
    entries: list[RedlineEntry] = Field(default_factory=list)
    total_clouds: int = 0
    total_affected_entities: int = 0
    methodology: str = "deterministic_cloud_analysis"
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_flags: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 10.3 -- Batch Repeated-Condition
# ---------------------------------------------------------------------------


class ConditionGroup(BaseModel):
    name: str
    exemplar_handles: list[str] = Field(default_factory=list)
    instances: list[dict[str, Any]] = Field(default_factory=list)
    total_instances: int = 0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)


class BatchConditionResult(BaseModel):
    groups: list[ConditionGroup] = Field(default_factory=list)
    total_groups: int = 0
    total_instances: int = 0
    methodology: str = "deterministic_batch_condition_detection"
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_flags: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 10.4 -- Field Summary
# ---------------------------------------------------------------------------


class FieldSectionType(StrEnum):
    GRID_SUMMARY = "grid_summary"
    TAKEOFF_SUMMARY = "takeoff_summary"
    REVISION_CHANGES = "revision_changes"
    LAYOUT_NOTES = "layout_notes"
    CONDITION_REPORT = "condition_report"
    GENERAL_NOTES = "general_notes"


class FieldSection(BaseModel):
    section_type: FieldSectionType
    title: str
    content: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)


class FieldSummary(BaseModel):
    title: str = "Construction Field Summary"
    sections: list[FieldSection] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_flags: list[str] = Field(default_factory=list)
    omitted_sections: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
