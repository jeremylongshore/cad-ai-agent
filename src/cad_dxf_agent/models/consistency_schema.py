"""Cross-drawing consistency checker schemas.

Defines data models for comparing multiple DXF drawing sheets (e.g., floor
plan + RCP + electrical plan) to verify that a drawing set is coordinated.
Checks include: room labels match across sheets, shared block names appear
consistently, layer naming follows convention, entity counts are plausible,
and drawings share the same coordinate origin/scale.

Used by the multi-sheet consistency checker to surface discrepancies before
issue-for-construction release.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConsistencyCategory(StrEnum):
    """Categories of cross-sheet consistency checks."""

    ROOM_LABELS = "room_labels"
    """Room labels should match across sheets."""

    LAYER_NAMING = "layer_naming"
    """Layer naming conventions should be consistent."""

    ENTITY_COUNTS = "entity_counts"
    """Entity counts per type should be plausible across sheets."""

    BLOCK_CONSISTENCY = "block_consistency"
    """Shared block names should appear consistently."""

    COORDINATE_ALIGNMENT = "coordinate_alignment"
    """Drawings should share the same coordinate origin/scale."""

    GENERAL = "general"
    """Uncategorized consistency finding."""


class ConsistencySeverity(StrEnum):
    """Severity levels for consistency findings."""

    ERROR = "error"
    """Definite inconsistency that must be resolved."""

    WARNING = "warning"
    """Possible inconsistency worth reviewing."""

    INFO = "info"
    """Informational note — no action required."""


class ConsistencyFinding(BaseModel):
    """A single consistency issue found between one or more sheets."""

    finding_id: str = Field(..., description="Deterministic identifier for this finding")
    category: ConsistencyCategory
    severity: ConsistencySeverity
    title: str = Field(..., description="Short human-readable summary of the finding")
    description: str = Field(..., description="Detailed explanation of the inconsistency")
    sheet_a: str = Field(..., description="File path of the first (or only) sheet involved")
    sheet_b: str | None = Field(
        default=None,
        description="File path of the second sheet (None for single-sheet findings)",
    )
    entity_handles: list[str] = Field(
        default_factory=list,
        description="Handles of entities directly involved in the finding",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Category-specific structured details (e.g., mismatched label lists)",
    )


class SheetInfo(BaseModel):
    """Metadata and extracted signals for one sheet in a drawing set."""

    file_path: str = Field(..., description="Absolute path to the DXF file")
    family: str = Field(..., description="Detected document family from family_detector")
    layer_count: int = 0
    entity_count: int = 0
    room_labels: list[str] = Field(
        default_factory=list,
        description="Room/space names extracted from the sheet",
    )
    block_names: list[str] = Field(
        default_factory=list,
        description="Unique block names referenced in the sheet",
    )


class ConsistencyReport(BaseModel):
    """Aggregate result of a multi-sheet consistency check run."""

    sheets: list[SheetInfo]
    findings: list[ConsistencyFinding] = Field(default_factory=list)
    checks_run: list[str] = Field(
        default_factory=list,
        description="Names of the individual checks that were executed",
    )
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    @property
    def passed(self) -> bool:
        """True when no ERROR-severity findings were found."""
        return self.error_count == 0

    @property
    def score(self) -> float:
        """Consistency score in [0.0, 1.0].

        Starts at 1.0 and is penalised by errors (−0.20 each) and warnings
        (−0.05 each).  Clamped so it never goes below 0.0.
        """
        raw = 1.0 - (self.error_count * 0.20) - (self.warning_count * 0.05)
        return max(0.0, min(1.0, raw))
