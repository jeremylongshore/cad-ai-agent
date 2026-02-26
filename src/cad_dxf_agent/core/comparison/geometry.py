"""Geometry extraction — reads ezdxf entities into GeometrySnapshot objects."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import ezdxf

from ...models.cad_schema import EntityType, Point2D
from ...models.comparison_schema import ComparisonConfig, GeometrySnapshot

logger = logging.getLogger(__name__)

# Entity types we know how to extract geometry from
_EXTRACTABLE_TYPES = {t.value for t in EntityType}


def extract_snapshots(
    dxf_path: str | Path,
    config: ComparisonConfig | None = None,
) -> list[GeometrySnapshot]:
    """Extract GeometrySnapshot objects from all model-space entities in a DXF.

    Args:
        dxf_path: Path to the DXF file.
        config: Optional comparison config for layer/type filtering.

    Returns:
        List of GeometrySnapshot with full point data per entity.
    """
    config = config or ComparisonConfig()
    dxf_path = Path(dxf_path)

    if not dxf_path.exists():
        raise FileNotFoundError(f"DXF file not found: {dxf_path}")

    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    ignored_upper = {layer.upper() for layer in config.ignored_layers}
    focus_types = (
        {t.value for t in config.focus_entity_types} if config.focus_entity_types else None
    )

    snapshots: list[GeometrySnapshot] = []

    for entity in msp:
        dxf_type = entity.dxftype()

        if dxf_type not in _EXTRACTABLE_TYPES:
            continue

        if focus_types and dxf_type not in focus_types:
            continue

        layer = entity.dxf.layer
        if layer.upper() in ignored_upper:
            continue

        snap = _extract_one(entity, dxf_type)
        if snap is not None:
            snapshots.append(snap)

    return snapshots


def _extract_one(
    entity: ezdxf.entities.DXFGraphic,
    dxf_type: str,
) -> GeometrySnapshot | None:
    """Extract full geometry from a single ezdxf entity."""
    handle = entity.dxf.handle
    layer = entity.dxf.layer
    points: list[Point2D] = []
    text_content: str | None = None
    block_name: str | None = None
    attributes: dict[str, Any] = {}

    try:
        if dxf_type == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            points = [Point2D(x=start.x, y=start.y), Point2D(x=end.x, y=end.y)]

        elif dxf_type == "LWPOLYLINE":
            raw = list(entity.get_points(format="xy"))  # type: ignore[attr-defined]
            points = [Point2D(x=p[0], y=p[1]) for p in raw]

        elif dxf_type == "TEXT":
            insert = entity.dxf.insert
            points = [Point2D(x=insert.x, y=insert.y)]
            text_content = entity.dxf.text

        elif dxf_type == "MTEXT":
            insert = entity.dxf.insert
            points = [Point2D(x=insert.x, y=insert.y)]
            text_content = entity.text  # type: ignore[attr-defined]

        elif dxf_type == "INSERT":
            insert = entity.dxf.insert
            points = [Point2D(x=insert.x, y=insert.y)]
            block_name = entity.dxf.name

        elif dxf_type == "CIRCLE":
            center = entity.dxf.center
            points = [Point2D(x=center.x, y=center.y)]
            attributes["radius"] = entity.dxf.radius

        elif dxf_type == "ARC":
            center = entity.dxf.center
            points = [Point2D(x=center.x, y=center.y)]
            attributes["radius"] = entity.dxf.radius
            attributes["start_angle"] = entity.dxf.start_angle
            attributes["end_angle"] = entity.dxf.end_angle

        elif dxf_type == "POLYLINE":
            try:
                vertices = list(entity.vertices)  # type: ignore[attr-defined]
                points = [Point2D(x=v.dxf.location.x, y=v.dxf.location.y) for v in vertices]
            except Exception:
                logger.debug("POLYLINE %s: vertex read failed", handle)
                return None

        elif dxf_type == "DIMENSION":
            text_content = entity.dxf.get("text", "") or ""
            try:
                insert = entity.dxf.insert
                points = [Point2D(x=insert.x, y=insert.y)]
            except Exception:
                try:
                    defpoint = entity.dxf.defpoint
                    points = [Point2D(x=defpoint.x, y=defpoint.y)]
                except Exception:
                    logger.debug("DIMENSION %s: no insert or defpoint", handle)
                    return None

        elif dxf_type == "ELLIPSE":
            center = entity.dxf.center
            points = [Point2D(x=center.x, y=center.y)]
            attributes["ratio"] = entity.dxf.ratio
            major = entity.dxf.major_axis
            attributes["major_axis"] = (major.x, major.y, major.z)

        elif dxf_type == "SPLINE":
            try:
                ctrl = list(entity.control_points)  # type: ignore[attr-defined]
                points = [Point2D(x=p[0], y=p[1]) for p in ctrl]
            except Exception:
                logger.debug("SPLINE %s: control point read failed", handle)
                return None

        elif dxf_type == "HATCH":
            try:
                paths = entity.paths  # type: ignore[attr-defined]
                if paths:
                    for path in paths:
                        for v in getattr(path, "vertices", []):
                            points.append(Point2D(x=v[0], y=v[1]))
            except Exception:
                logger.debug("HATCH %s: boundary read failed", handle)
            if not points:
                return None

        elif dxf_type == "MLEADER":
            try:
                ctx = entity.context  # type: ignore[attr-defined]
                if hasattr(ctx, "mtext") and ctx.mtext:
                    text_content = ctx.mtext.default_content
                    points = [Point2D(x=ctx.mtext.insert.x, y=ctx.mtext.insert.y)]
            except Exception:
                logger.debug("MLEADER %s: context read failed", handle)
                return None

        elif dxf_type == "LEADER":
            try:
                vertices = list(entity.vertices)  # type: ignore[attr-defined]
                points = [Point2D(x=v.x, y=v.y) for v in vertices]
            except Exception:
                logger.debug("LEADER %s: vertex read failed", handle)
                return None

        elif dxf_type == "SOLID":
            try:
                for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                    vtx = getattr(entity.dxf, attr, None)
                    if vtx is not None:
                        points.append(Point2D(x=vtx.x, y=vtx.y))
            except Exception:
                logger.debug("SOLID %s: vertex read failed", handle)
                return None

        else:
            return None

    except Exception:
        logger.debug("Failed to extract geometry from %s %s", dxf_type, handle)
        return None

    if not points:
        return None

    return GeometrySnapshot(
        handle=handle,
        entity_type=EntityType(dxf_type),
        layer=layer,
        points=points,
        text_content=text_content,
        block_name=block_name,
        attributes=attributes,
    )
