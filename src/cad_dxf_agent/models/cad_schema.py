"""CAD domain schemas: entities, layers, and drawing context."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EntityType(StrEnum):
    """Supported entity types."""

    LINE = "LINE"
    LWPOLYLINE = "LWPOLYLINE"
    TEXT = "TEXT"
    MTEXT = "MTEXT"
    INSERT = "INSERT"
    # V2 types — structural drawings
    CIRCLE = "CIRCLE"
    ARC = "ARC"
    DIMENSION = "DIMENSION"
    HATCH = "HATCH"
    SPLINE = "SPLINE"
    POLYLINE = "POLYLINE"
    ELLIPSE = "ELLIPSE"
    SOLID = "SOLID"
    LEADER = "LEADER"


class Point2D(BaseModel):
    """2D coordinate."""

    x: float
    y: float


class TextProvenance(StrEnum):
    """Source of text data, ordered by trust (highest first)."""

    NATIVE_CAD_TEXT = "native_cad_text"
    BLOCK_ATTRIBUTE_TEXT = "block_attribute_text"
    VECTOR_OUTLINE_TEXT = "vector_outline_text"
    RASTER_OCR_TEXT = "raster_ocr_text"


class TextGeometry(BaseModel):
    """Text rendering geometry extracted from native CAD entities."""

    height: float | None = None
    rotation: float = Field(default=0.0, description="Rotation in degrees [0, 360)")
    halign: int = Field(default=0, description="Horizontal alignment (0=left,1=center,2=right)")
    valign: int = Field(
        default=0, description="Vertical alignment (0=baseline,1=bottom,2=mid,3=top)"
    )
    width_factor: float = Field(default=1.0, description="Character width scale factor")
    oblique: float = Field(default=0.0, description="Oblique angle in degrees")
    attachment_point: int | None = Field(
        default=None, description="MTEXT attachment point (1-9, top-left to bottom-right)"
    )
    char_height: float | None = Field(
        default=None, description="MTEXT character height (overrides height if set)"
    )
    provenance: TextProvenance = TextProvenance.NATIVE_CAD_TEXT


class EntityRef(BaseModel):
    """Reference to a DXF entity with identity and location context."""

    handle: str = Field(description="DXF entity handle (unique within the drawing)")
    entity_type: EntityType
    layer: str
    space: str = Field(default="Model", description="Space: 'Model' or layout name")
    insert_point: Point2D | None = None
    text_content: str | None = None
    block_name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    text_geometry: TextGeometry | None = None


class LayerRule(BaseModel):
    """Rule associated with a drawing layer."""

    name: str
    protected: bool = False
    visible: bool = True
    frozen: bool = False
    color: int | None = None


class LayoutInfo(BaseModel):
    """Metadata about a DXF layout (paper space tab)."""

    name: str
    entity_count: int = 0


class LoadWarning(BaseModel):
    """Warning generated during DXF loading."""

    code: str
    message: str
    severity: str = "info"  # "info" | "warning" | "error"
    details: dict[str, Any] = Field(default_factory=dict)


class DrawingContext(BaseModel):
    """Normalized context model for a loaded DXF drawing."""

    file_path: str
    entities: list[EntityRef] = Field(default_factory=list)
    layers: list[LayerRule] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    layouts: list[LayoutInfo] = Field(default_factory=list)
    unsupported_entity_types: list[str] = Field(default_factory=list)
    load_warnings: list[LoadWarning] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    def get_entity_by_handle(self, handle: str) -> EntityRef | None:
        for entity in self.entities:
            if entity.handle == handle:
                return entity
        return None

    def get_protected_layers(self) -> list[str]:
        return [layer.name for layer in self.layers if layer.protected]
