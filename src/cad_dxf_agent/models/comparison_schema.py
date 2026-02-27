"""Comparison schemas: geometry snapshots, matching, and diff classification."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from .cad_schema import EntityType, Point2D


class GeometrySnapshot(BaseModel):
    """Full geometry capture of one entity from a DXF file."""

    handle: str = Field(description="DXF entity handle (unique within its file)")
    entity_type: EntityType
    layer: str
    points: list[Point2D] = Field(description="All defining points (ordered)")
    text_content: str | None = None
    block_name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    stable_id: str | None = Field(
        default=None,
        description="Geometry-based stable ID (assigned by assign_stable_ids)",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def centroid(self) -> Point2D:
        """Mean of all defining points."""
        if not self.points:
            return Point2D(x=0.0, y=0.0)
        cx = sum(p.x for p in self.points) / len(self.points)
        cy = sum(p.y for p in self.points) / len(self.points)
        return Point2D(x=cx, y=cy)


class ComparisonConfig(BaseModel):
    """Configuration for a DXF comparison run."""

    tolerance: float = Field(
        default=0.25,
        description="Match threshold in drawing units (1/4 inch default)",
    )
    move_threshold: float = Field(
        default=0.25,
        description="Min displacement to classify as moved vs unchanged",
    )
    ignored_layers: list[str] = Field(default_factory=list)
    focus_entity_types: list[EntityType] | None = Field(
        default=None,
        description="Restrict comparison to these types; None = all",
    )
    use_canonical: bool = Field(
        default=False,
        description="Enable canonical model: stable IDs, deterministic ordering, quantized points",
    )


class ChangeCategory(StrEnum):
    """Classification of a single entity change."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"
    UNCHANGED = "unchanged"


class EntityChange(BaseModel):
    """One classified change between master and revision."""

    category: ChangeCategory
    master_snapshot: GeometrySnapshot | None = Field(
        default=None, description="None for ADDED entities"
    )
    revision_snapshot: GeometrySnapshot | None = Field(
        default=None, description="None for REMOVED entities"
    )
    displacement: Point2D | None = Field(default=None, description="dx, dy for MOVED entities")
    modifications: dict[str, Any] | None = Field(
        default=None, description="What changed for MODIFIED entities"
    )


class MatchResult(BaseModel):
    """Output of the entity matching step."""

    pairs: list[tuple[GeometrySnapshot, GeometrySnapshot]] = Field(
        default_factory=list,
        description="Matched (master, revision) pairs",
    )
    master_only: list[GeometrySnapshot] = Field(
        default_factory=list,
        description="Unmatched master entities (candidates for REMOVED)",
    )
    revision_only: list[GeometrySnapshot] = Field(
        default_factory=list,
        description="Unmatched revision entities (candidates for ADDED)",
    )


class ComparisonResult(BaseModel):
    """Full result of comparing two DXF files."""

    changes: list[EntityChange] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=lambda: {
            "added": 0,
            "removed": 0,
            "modified": 0,
            "moved": 0,
            "unchanged": 0,
        }
    )
    config: ComparisonConfig = Field(default_factory=ComparisonConfig)

    @property
    def total_changes(self) -> int:
        """Count of non-unchanged changes."""
        return (
            self.summary.get("added", 0)
            + self.summary.get("removed", 0)
            + self.summary.get("modified", 0)
            + self.summary.get("moved", 0)
        )


class DiffOverlayLayers:
    """Layer name constants and DXF color codes for diff overlays."""

    ADDED = ("AI_ADDED", 3)  # green
    REMOVED = ("AI_REMOVED", 1)  # red
    MODIFIED = ("AI_MODIFIED", 2)  # yellow
    MOVED = ("AI_MOVED", 4)  # cyan

    ALL = [ADDED, REMOVED, MODIFIED, MOVED]
