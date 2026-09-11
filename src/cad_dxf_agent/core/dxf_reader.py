"""DXF file reader — loads model space and layout entities into DrawingContext."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import ezdxf

from ..models.cad_schema import (
    DrawingContext,
    DrawingUnit,
    EntityGeometry,
    EntityRef,
    EntityType,
    GeometryKind,
    LayerRule,
    LayoutInfo,
    LoadWarning,
    Point2D,
    TextGeometry,
    TextProvenance,
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
        raw_insunits = int(doc.header.get("$INSUNITS", 0) or 0)
        try:
            drawing_unit = DrawingUnit(raw_insunits)
        except ValueError:
            logger.warning("Invalid $INSUNITS value %s; treating drawing as unitless", raw_insunits)
            drawing_unit = DrawingUnit.UNITLESS

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

        # Generate load-time warnings
        warnings = _generate_load_warnings(
            entities, layers, sorted(unsupported), settings.protected_layers
        )

        ctx = DrawingContext(
            file_path=str(file_path),
            drawing_unit=drawing_unit,
            entities=entities,
            layers=layers,
            blocks=blocks,
            layouts=layout_infos,
            unsupported_entity_types=sorted(unsupported),
            load_warnings=warnings,
            metadata={
                "dxf_version": doc.dxfversion,
                "encoding": doc.encoding,
                "insunits": int(drawing_unit),
                "unit_name": drawing_unit.name.lower(),
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
    text_geometry = None

    attributes: dict[str, Any] = {}

    if dxf_type == "LINE":
        start = entity.dxf.start
        insert_point = Point2D(x=start.x, y=start.y)
        end = entity.dxf.end
        attributes["end_point"] = (end.x, end.y)
    elif dxf_type == "LWPOLYLINE":
        points = list(entity.get_points(format="xy"))  # type: ignore[attr-defined]
        if points:
            insert_point = Point2D(x=points[0][0], y=points[0][1])
            attributes["vertices"] = [(p[0], p[1]) for p in points]
            attributes["is_closed"] = entity.closed  # type: ignore[attr-defined]
    elif dxf_type == "TEXT":
        insert = entity.dxf.insert
        insert_point = Point2D(x=insert.x, y=insert.y)
        text_content = entity.dxf.text
        text_geometry = _extract_text_geometry(entity)
    elif dxf_type == "MTEXT":
        insert = entity.dxf.insert
        insert_point = Point2D(x=insert.x, y=insert.y)
        text_content = entity.plain_text()  # type: ignore[attr-defined]
        text_geometry = _extract_mtext_geometry(entity)
        mtext_width = entity.dxf.get("width", None)
        if mtext_width is not None and mtext_width > 0:
            attributes["mtext_width"] = mtext_width
    elif dxf_type == "INSERT":
        insert = entity.dxf.insert
        insert_point = Point2D(x=insert.x, y=insert.y)
        block_name = entity.dxf.name
        insert_xscale = entity.dxf.get("xscale", 1.0)
        insert_yscale = entity.dxf.get("yscale", 1.0)
        insert_rotation = _normalize_rotation(entity.dxf.get("rotation", 0.0))
        attributes["insert_xscale"] = insert_xscale
        attributes["insert_yscale"] = insert_yscale
        attributes["insert_rotation"] = insert_rotation
        # Extract ATTRIB text with geometry.
        # NOTE: text_content/text_geometry use the first ATTRIB only;
        # all ATTRIBs are stored in attributes["attribs"] for full access.
        try:
            attribs = list(entity.attribs)  # type: ignore[attr-defined]
            if attribs:
                attrib_data = {}
                for attrib in attribs:
                    tag = attrib.dxf.tag
                    attrib_data[tag] = {
                        "text": attrib.dxf.text,
                        "height": attrib.dxf.get("height", None),
                        "rotation": attrib.dxf.get("rotation", 0.0),
                    }
                    try:
                        ai = attrib.dxf.insert
                        attrib_data[tag]["insert"] = {"x": ai.x, "y": ai.y}
                    except Exception as e:
                        logger.debug("INSERT %s: attrib insert read failed: %s", handle, e)
                if attrib_data:
                    attributes["attribs"] = attrib_data
                    first = next(iter(attrib_data.values()))
                    text_content = first["text"]
                    # ATTRIB height already reflects INSERT scale in DXF
                    text_geometry = TextGeometry(
                        height=first.get("height"),
                        rotation=_normalize_rotation(first.get("rotation", 0.0)),
                        provenance=TextProvenance.BLOCK_ATTRIBUTE_TEXT,
                        confidence_position=0.95,
                        confidence_rotation=0.95,
                    )
        except AttributeError:
            logger.debug("INSERT %s: entity has no attribs attribute", handle)
        except Exception:
            logger.warning(
                "INSERT %s: unexpected error in attrib extraction", handle, exc_info=True
            )
    elif dxf_type == "CIRCLE":
        center = entity.dxf.center
        insert_point = Point2D(x=center.x, y=center.y)
        attributes["radius"] = entity.dxf.radius
    elif dxf_type == "ARC":
        center = entity.dxf.center
        insert_point = Point2D(x=center.x, y=center.y)
        attributes["radius"] = entity.dxf.radius
        attributes["start_angle"] = entity.dxf.start_angle
        attributes["end_angle"] = entity.dxf.end_angle
    elif dxf_type == "ELLIPSE":
        center = entity.dxf.center
        insert_point = Point2D(x=center.x, y=center.y)
        attributes["ratio"] = entity.dxf.ratio
        major = entity.dxf.major_axis
        attributes["major_axis"] = (major.x, major.y, major.z)
    elif dxf_type == "DIMENSION":
        # Override text or measured value
        text_content = entity.dxf.get("text", "") or ""  # type: ignore[assignment]
        try:
            insert = entity.dxf.insert
            insert_point = Point2D(x=insert.x, y=insert.y)
        except Exception:
            # Some dimension subtypes lack an insert; fall back to defpoint
            try:
                defpoint = entity.dxf.defpoint
                insert_point = Point2D(x=defpoint.x, y=defpoint.y)
            except Exception:
                logger.debug("DIMENSION %s: no insert or defpoint", handle)
    elif dxf_type == "HATCH":
        boundary_vertices: list[tuple[float, float]] = []
        try:
            elevation = entity.dxf.get("elevation", None)
            if elevation is not None:
                insert_point = Point2D(x=0.0, y=0.0)
        except Exception:
            logger.debug("HATCH %s: elevation read failed", handle)
        # Boundary geometry is independent of elevation and is the better
        # planar location signal, so always inspect it when available.
        try:
            paths = entity.paths  # type: ignore[attr-defined]
            if paths:
                for path in paths:
                    for vertex in getattr(path, "vertices", []):
                        boundary_vertices.append((vertex[0], vertex[1]))
                if boundary_vertices:
                    insert_point = Point2D(
                        x=sum(v[0] for v in boundary_vertices) / len(boundary_vertices),
                        y=sum(v[1] for v in boundary_vertices) / len(boundary_vertices),
                    )
        except Exception:
            logger.debug("HATCH %s: centroid computation failed", handle)
        if boundary_vertices:
            attributes["vertices"] = boundary_vertices
            attributes["is_closed"] = True
    elif dxf_type == "SPLINE":
        try:
            control_points = list(entity.control_points)  # type: ignore[attr-defined]
            if control_points:
                cp = control_points[0]
                insert_point = Point2D(x=cp[0], y=cp[1])
                attributes["vertices"] = [(cp[0], cp[1]) for cp in control_points]
        except Exception:
            logger.debug("SPLINE %s: control point read failed", handle)
    elif dxf_type == "POLYLINE":
        try:
            vertices = list(entity.vertices)  # type: ignore[attr-defined]
            if vertices:
                loc = vertices[0].dxf.location
                insert_point = Point2D(x=loc.x, y=loc.y)
                attributes["vertices"] = [(v.dxf.location.x, v.dxf.location.y) for v in vertices]
                attributes["is_closed"] = bool(entity.is_closed)  # type: ignore[attr-defined]
        except Exception:
            logger.debug("POLYLINE %s: vertex read failed", handle)
    elif dxf_type == "MLEADER":
        try:
            ctx = entity.context  # type: ignore[attr-defined]
            if hasattr(ctx, "mtext") and ctx.mtext:
                text_content = ctx.mtext.default_content
                insert_point = Point2D(
                    x=ctx.mtext.insert.x,
                    y=ctx.mtext.insert.y,
                )
        except Exception:
            logger.debug("MLEADER %s: context read failed", handle)
    elif dxf_type == "LEADER":
        try:
            vertices = list(entity.vertices)  # type: ignore[attr-defined]
            if vertices:
                insert_point = Point2D(x=vertices[0].x, y=vertices[0].y)
                attributes["vertices"] = [(v.x, v.y) for v in vertices]
        except Exception:
            logger.debug("LEADER %s: vertex read failed", handle)
    elif dxf_type == "SOLID":
        try:
            solid_vertices = [
                getattr(entity.dxf, name) for name in ("vtx0", "vtx1", "vtx2", "vtx3")
            ]
            insert_point = Point2D(x=solid_vertices[0].x, y=solid_vertices[0].y)
            attributes["vertices"] = [(v.x, v.y) for v in solid_vertices]
            attributes["is_closed"] = True
        except Exception:
            logger.debug("SOLID %s: vtx0 read failed", handle)

    return EntityRef(
        handle=handle,
        entity_type=EntityType(dxf_type),
        layer=layer,
        space=space,
        insert_point=insert_point,
        geometry=_build_entity_geometry(dxf_type, insert_point, attributes),
        text_content=text_content,
        block_name=block_name,
        attributes=attributes,
        text_geometry=text_geometry,
    )


def _build_entity_geometry(
    dxf_type: str,
    insert_point: Point2D | None,
    attributes: dict[str, Any],
) -> EntityGeometry | None:
    """Build the normalized geometry model from parsed entity data."""
    raw_vertices = attributes.get("vertices", [])
    vertices = [Point2D(x=float(v[0]), y=float(v[1])) for v in raw_vertices]

    if dxf_type == "LINE" and insert_point is not None:
        end = attributes.get("end_point")
        if end is not None:
            return EntityGeometry(
                kind=GeometryKind.LINE,
                points=[insert_point, Point2D(x=float(end[0]), y=float(end[1]))],
            )
    if dxf_type in {"LWPOLYLINE", "POLYLINE", "LEADER"} and vertices:
        return EntityGeometry(
            kind=GeometryKind.POLYLINE,
            points=vertices,
            closed=bool(attributes.get("is_closed", False)),
        )
    if dxf_type == "SPLINE" and vertices:
        return EntityGeometry(kind=GeometryKind.SPLINE, points=vertices)
    if dxf_type in {"HATCH", "SOLID"} and vertices:
        return EntityGeometry(kind=GeometryKind.POLYGON, points=vertices, closed=True)
    if dxf_type == "CIRCLE" and insert_point is not None:
        return EntityGeometry(
            kind=GeometryKind.CIRCLE,
            points=[insert_point],
            radius=float(attributes["radius"]),
            closed=True,
        )
    if dxf_type == "ARC" and insert_point is not None:
        return EntityGeometry(
            kind=GeometryKind.ARC,
            points=[insert_point],
            radius=float(attributes["radius"]),
            start_angle=float(attributes["start_angle"]),
            end_angle=float(attributes["end_angle"]),
        )
    if dxf_type == "ELLIPSE" and insert_point is not None:
        return EntityGeometry(
            kind=GeometryKind.ELLIPSE,
            points=[insert_point],
            major_axis=tuple(attributes["major_axis"]),
            ratio=float(attributes["ratio"]),
            closed=True,
        )
    if insert_point is not None:
        return EntityGeometry(kind=GeometryKind.POINT, points=[insert_point])
    return None


def _normalize_rotation(deg: float) -> float:
    """Normalize rotation to [0, 360)."""
    return deg % 360.0


def _extract_text_geometry(entity: ezdxf.entities.DXFGraphic) -> TextGeometry:
    """Extract text geometry from a DXF TEXT entity."""
    dxf = entity.dxf
    return TextGeometry(
        height=dxf.get("height", None),
        rotation=_normalize_rotation(dxf.get("rotation", 0.0)),
        halign=dxf.get("halign", 0),
        valign=dxf.get("valign", 0),
        width_factor=dxf.get("width", 1.0),
        oblique=dxf.get("oblique", 0.0),
        provenance=TextProvenance.NATIVE_CAD_TEXT,
    )


def _extract_mtext_geometry(entity: ezdxf.entities.DXFGraphic) -> TextGeometry:
    """Extract text geometry from a DXF MTEXT entity."""
    dxf = entity.dxf
    return TextGeometry(
        height=dxf.get("char_height", None),
        rotation=_normalize_rotation(dxf.get("rotation", 0.0)),
        attachment_point=dxf.get("attachment_point", None),
        char_height=dxf.get("char_height", None),
        provenance=TextProvenance.NATIVE_CAD_TEXT,
    )


def _generate_load_warnings(
    entities: list[EntityRef],
    layers: list[LayerRule],
    unsupported_types: list[str],
    protected_layer_names: list[str],
) -> list[LoadWarning]:
    """Generate actionable warnings based on loading results."""
    warnings: list[LoadWarning] = []

    # EMPTY_DRAWING: no supported entities at all
    if not entities:
        warnings.append(
            LoadWarning(
                code="EMPTY_DRAWING",
                message="Drawing has 0 supported entities.",
                severity="error",
            )
        )
        return warnings  # No point checking further

    # UNSUPPORTED_TYPES: some entity types were skipped
    if unsupported_types:
        warnings.append(
            LoadWarning(
                code="UNSUPPORTED_TYPES",
                message=(
                    f"{len(unsupported_types)} entity type(s) skipped: "
                    f"{', '.join(unsupported_types)}. These cannot be edited."
                ),
                severity="info",
                details={"types": unsupported_types},
            )
        )

    # ALL_PROTECTED: every entity is on a protected layer
    protected_upper = {p.upper() for p in protected_layer_names}
    editable = [e for e in entities if e.layer.upper() not in protected_upper]
    if not editable:
        warnings.append(
            LoadWarning(
                code="ALL_PROTECTED",
                message="All entities are on protected layers. No editable entities.",
                severity="warning",
            )
        )

    # LARGE_DRAWING: many entities may cause large LLM context
    if len(entities) >= 500:
        warnings.append(
            LoadWarning(
                code="LARGE_DRAWING",
                message=f"Drawing has {len(entities)} entities. LLM context may be large.",
                severity="info",
                details={"entity_count": len(entities)},
            )
        )

    return warnings


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
