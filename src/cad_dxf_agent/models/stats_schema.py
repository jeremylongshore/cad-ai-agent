"""Drawing statistics schema for UI display and support reports."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .cad_schema import LoadWarning, Point2D


class DrawingStats(BaseModel):
    """Computed statistics for a loaded DXF drawing."""

    file_name: str
    file_size_bytes: int
    dxf_version: str
    entity_count: int
    editable_entity_count: int
    layer_count: int
    layout_count: int
    block_count: int
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    counts_by_layer: dict[str, int] = Field(default_factory=dict)
    protected_layers: list[str] = Field(default_factory=list)
    unsupported_types: list[str] = Field(default_factory=list)
    coverage_pct: float = 0.0
    load_warnings: list[LoadWarning] = Field(default_factory=list)
    bounding_box: tuple[Point2D, Point2D] | None = None
