"""Zone detection models for room/space inference.

Represents enclosed areas detected from closed LWPOLYLINE boundaries
and connected LINE segment cycles. Used by the detect_zones stage handler.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from .cad_schema import Point2D


class DetectedZone(BaseModel):
    """A single enclosed zone detected from drawing geometry."""

    zone_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    boundary: list[Point2D]
    area: float
    perimeter: float
    centroid: Point2D
    inferred_type: str | None = None
    source_handles: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class ZoneDetectionResult(BaseModel):
    """Aggregate result of zone detection across the drawing."""

    zones: list[DetectedZone] = Field(default_factory=list)
    total_area: float = 0.0
    zone_count: int = 0
    confidence: float = 0.0
    method: str = "polyline_tracing"
    warnings: list[str] = Field(default_factory=list)
