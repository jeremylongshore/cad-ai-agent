"""Canonical accessors and Shapely adapter for typed entity geometry."""

from __future__ import annotations

import math
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from ..models.cad_schema import EntityRef, GeometryKind, Point2D


def _legacy_point(value: Any) -> Point2D:
    """Decode a legacy coordinate tuple without discarding an optional Z."""
    coordinates = list(value)
    return Point2D(
        x=float(coordinates[0]),
        y=float(coordinates[1]),
        z=float(coordinates[2]) if len(coordinates) > 2 else None,
    )


def entity_points(entity: EntityRef) -> list[Point2D]:
    """Return normalized points, with legacy attribute fallback for old payloads."""
    if entity.geometry is not None:
        return list(entity.geometry.points)
    if entity.entity_type.value == "LINE" and entity.insert_point is not None:
        end = entity.attributes.get("end_point")
        if end is not None:
            return [entity.insert_point, _legacy_point(end)]
    if "vertices" in entity.attributes:
        vertices = entity.attributes["vertices"]
        return [_legacy_point(v) for v in vertices]
    return [entity.insert_point] if entity.insert_point is not None else []


def entity_is_closed(entity: EntityRef) -> bool:
    """Return explicit closure from typed geometry or a legacy attribute."""
    if entity.geometry is not None:
        return entity.geometry.closed
    return bool(entity.attributes.get("is_closed", False))


def to_shapely(entity: EntityRef) -> BaseGeometry | None:
    """Convert supported typed entity geometry to a Shapely planar primitive."""
    geometry = entity.geometry
    if geometry is None or not geometry.points:
        return None

    coords = [(point.x, point.y) for point in geometry.points]
    if geometry.kind is GeometryKind.POINT:
        return Point(coords[0])
    if geometry.kind is GeometryKind.LINE:
        return LineString(coords)
    if geometry.kind in {GeometryKind.POLYLINE, GeometryKind.SPLINE}:
        if geometry.closed and len(coords) >= 3:
            return Polygon(coords)
        return LineString(coords) if len(coords) >= 2 else Point(coords[0])
    if geometry.kind is GeometryKind.POLYGON:
        return Polygon(coords)
    if geometry.kind is GeometryKind.CIRCLE and geometry.radius is not None:
        return Point(coords[0]).buffer(geometry.radius)
    if geometry.kind is GeometryKind.ARC and geometry.radius is not None:
        start = geometry.start_angle or 0.0
        end = geometry.end_angle if geometry.end_angle is not None else 360.0
        if end < start:
            end += 360.0
        steps = max(8, int((end - start) / 10.0) + 1)
        center_x, center_y = coords[0]
        arc_points = []
        for index in range(steps + 1):
            angle = math.radians(start + (end - start) * index / steps)
            arc_points.append(
                (
                    center_x + geometry.radius * math.cos(angle),
                    center_y + geometry.radius * math.sin(angle),
                )
            )
        return LineString(arc_points)
    if (
        geometry.kind is GeometryKind.ELLIPSE
        and geometry.major_axis is not None
        and geometry.ratio is not None
    ):
        axis_x, axis_y, _ = geometry.major_axis
        major_radius = math.hypot(axis_x, axis_y)
        circle = Point(coords[0]).buffer(1.0)
        ellipse = affinity.scale(
            circle,
            xfact=major_radius,
            yfact=major_radius * geometry.ratio,
            origin=coords[0],
        )
        return affinity.rotate(
            ellipse,
            math.degrees(math.atan2(axis_y, axis_x)),
            origin=coords[0],
        )
    return None
