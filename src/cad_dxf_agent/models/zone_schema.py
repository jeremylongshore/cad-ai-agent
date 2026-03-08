"""Zone detection models for room/space inference.

Represents enclosed areas detected from closed LWPOLYLINE boundaries
and connected LINE segment cycles. Used by the detect_zones stage handler.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

from .cad_schema import Point2D


def _deterministic_zone_id(boundary: list[Point2D], source_handles: list[str]) -> str:
    """Generate a deterministic zone ID from boundary + source handles.

    Same drawing input always produces the same ID, enabling stable
    cross-session references and reproducible test assertions.
    """
    parts = [f"{p.x:.6f},{p.y:.6f}" for p in boundary]
    parts.extend(sorted(source_handles))
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return digest[:12]


class DetectedZone(BaseModel):
    """A single enclosed zone detected from drawing geometry."""

    zone_id: str = ""
    boundary: list[Point2D]
    area: float
    perimeter: float
    centroid: Point2D
    inferred_type: str | None = None
    source_handles: list[str] = Field(default_factory=list)
    confidence: float = 1.0

    def model_post_init(self, __context: object) -> None:
        """Auto-generate deterministic zone_id if not provided."""
        if not self.zone_id:
            self.zone_id = _deterministic_zone_id(self.boundary, self.source_handles)


class ZoneDetectionResult(BaseModel):
    """Aggregate result of zone detection across the drawing."""

    zones: list[DetectedZone] = Field(default_factory=list)
    total_area: float = 0.0
    zone_count: int = 0
    confidence: float = 0.0
    method: str = "polyline_and_line_tracing"
    warnings: list[str] = Field(default_factory=list)
