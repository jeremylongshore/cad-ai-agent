"""DXF file reader — loads model space and layout entities into DrawingContext."""

from __future__ import annotations

import logging
from pathlib import Path

import ezdxf

from ..models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    LayoutInfo,
    Point2D,
)
from ..otel import get_tracer
from ..settings import settings

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

SUPPORTED_TYPES = {t.value for t in EntityType}


def load_dxf(file_path: str | Path) -> DrawingContext:
    """Load a DXF file and build a normalized DrawingContext.

    Loads model space and all named layouts (paper spaces).
    Only supported V1 entity types are indexed.
    Unsupported entity types are recorded but skipped.
    """
    with tracer.start_as_current_span("cad.load_dxf") as span:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"DXF file not found: {file_path}")

        span.set_attribute("cad.file.name", file_path.name)

        doc = ezdxf.readfile(str(file_path))

        entities: list[EntityRef] = []
        unsupported: set[str] = set()
        blocks: list[str] = [block.name for block in doc.blocks if not block.name.startswith("*")]

        # Parse model space
        msp = doc.modelspace()
        for entity in msp:
            dxf_type = entity.dxftype()
            if dxf_type not in SUPPORTED_TYPES:
                unsupported.add(dxf_type)
                continue
            ref = _parse_entity(entity, dxf_type, space="Model")
            if ref is not None:
                entities.append(ref)

        model_count = len(entities)

        # Parse paper space layouts
        layout_infos: list[LayoutInfo] = [
            LayoutInfo(name="Model", entity_count=model_count),
        ]

        for layout in doc.layouts:
            name = layout.name
            if name == "Model":
                continue
            layout_entity_count = 0
            for entity in layout:
                dxf_type = entity.dxftype()
                if dxf_type not in SUPPORTED_TYPES:
                    unsupported.add(dxf_type)
                    continue
                ref = _parse_entity(entity, dxf_type, space=name)
                if ref is not None:
                    entities.append(ref)
                    layout_entity_count += 1
            layout_infos.append(LayoutInfo(name=name, entity_count=layout_entity_count))

        layers = _build_layer_rules(doc)

        if unsupported:
            logger.info(
                "Skipped unsupported entity types: %s",
                ", ".join(sorted(unsupported)),
            )

        ctx = DrawingContext(
            file_path=str(file_path),
            entities=entities,
            layers=layers,
            blocks=blocks,
            layouts=layout_infos,
            unsupported_entity_types=sorted(unsupported),
            metadata={
                "dxf_version": doc.dxfversion,
                "encoding": doc.encoding,
            },
        )

        span.set_attribute("cad.entities.count", len(entities))
        span.set_attribute("cad.layers.count", len(layers))
        span.set_attribute("cad.layouts.count", len(layout_infos))

        return ctx


def _parse_entity(
    entity: ezdxf.entities.DXFGraphic,
    dxf_type: str,
    space: str = "Model",
) -> EntityRef | None:
    """Parse a single DXF entity into an EntityRef."""
    handle = entity.dxf.handle
    layer = entity.dxf.layer

    insert_point = None
    text_content = None
    block_name = None

    if dxf_type == "LINE":
        start = entity.dxf.start
        insert_point = Point2D(x=start.x, y=start.y)
    elif dxf_type == "LWPOLYLINE":
        points = list(entity.get_points(format="xy"))  # type: ignore[attr-defined]
        if points:
            insert_point = Point2D(x=points[0][0], y=points[0][1])
    elif dxf_type == "TEXT":
        insert = entity.dxf.insert
        insert_point = Point2D(x=insert.x, y=insert.y)
        text_content = entity.dxf.text
    elif dxf_type == "MTEXT":
        insert = entity.dxf.insert
        insert_point = Point2D(x=insert.x, y=insert.y)
        text_content = entity.text  # type: ignore[attr-defined]
    elif dxf_type == "INSERT":
        insert = entity.dxf.insert
        insert_point = Point2D(x=insert.x, y=insert.y)
        block_name = entity.dxf.name

    return EntityRef(
        handle=handle,
        entity_type=EntityType(dxf_type),
        layer=layer,
        space=space,
        insert_point=insert_point,
        text_content=text_content,
        block_name=block_name,
    )


def _build_layer_rules(doc: ezdxf.document.Drawing) -> list[LayerRule]:
    """Build layer rules from the DXF layer table, marking protected layers."""
    rules = []
    for layer in doc.layers:
        name = layer.dxf.name
        is_off = layer.is_off() if callable(layer.is_off) else layer.is_off
        is_frozen = layer.is_frozen() if callable(layer.is_frozen) else layer.is_frozen
        rules.append(
            LayerRule(
                name=name,
                protected=name.upper() in [pl.upper() for pl in settings.protected_layers],
                visible=not is_off,
                frozen=bool(is_frozen),
                color=layer.color,
            )
        )
    return rules
