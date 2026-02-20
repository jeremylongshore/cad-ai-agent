"""Configuration schemas for the application."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .cad_schema import Point2D


class RuleConfig(BaseModel):
    """Validation and protection rule configuration."""

    protected_layers: list[str] = Field(
        default_factory=lambda: ["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]
    )
    protected_blocks: list[str] = Field(default_factory=list)
    max_move_distance: float | None = None
    coordinate_tolerance: float = 1e-6


class RevisionNoteConfig(BaseModel):
    """Configuration for AI revision note insertion."""

    enabled: bool = True
    layer_name: str = "AI_REV_NOTES"
    anchor_point: Point2D = Field(default_factory=lambda: Point2D(x=0.0, y=-50.0))
    text_height: float = 2.5
    prefix: str = "REV"
    revision_number: int = 1
