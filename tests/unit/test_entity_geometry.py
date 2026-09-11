"""Tests for typed entity geometry and its planar adapter."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.entity_geometry import (
    entity_is_closed,
    entity_points,
    to_shapely,
)
from cad_dxf_agent.models.cad_schema import (
    EntityGeometry,
    EntityRef,
    EntityType,
    GeometryKind,
    Point2D,
)


def _entity(geometry: EntityGeometry) -> EntityRef:
    return EntityRef(
        handle="1",
        entity_type=EntityType.LWPOLYLINE,
        layer="WALLS",
        geometry=geometry,
    )


def test_typed_polygon_converts_to_shapely() -> None:
    entity = _entity(
        EntityGeometry(
            kind=GeometryKind.POLYLINE,
            points=[
                Point2D(x=0, y=0),
                Point2D(x=10, y=0),
                Point2D(x=10, y=5),
                Point2D(x=0, y=5),
            ],
            closed=True,
        )
    )

    shape = to_shapely(entity)

    assert shape is not None
    assert shape.area == pytest.approx(50.0)
    assert entity_is_closed(entity)
    assert entity_points(entity)[2] == Point2D(x=10, y=5)


def test_circle_adapter_preserves_area() -> None:
    entity = EntityRef(
        handle="2",
        entity_type=EntityType.CIRCLE,
        layer="COLUMNS",
        geometry=EntityGeometry(
            kind=GeometryKind.CIRCLE,
            points=[Point2D(x=3, y=4)],
            radius=2,
            closed=True,
        ),
    )

    shape = to_shapely(entity)

    assert shape is not None
    assert shape.area == pytest.approx(12.546, rel=0.01)


def test_legacy_attributes_remain_readable() -> None:
    entity = EntityRef(
        handle="3",
        entity_type=EntityType.LINE,
        layer="GRID",
        insert_point=Point2D(x=1, y=2),
        attributes={"end_point": (4, 6)},
    )

    assert entity_points(entity) == [Point2D(x=1, y=2), Point2D(x=4, y=6)]


def test_reader_populates_typed_geometry(sample_context) -> None:
    line = next(
        entity for entity in sample_context.entities if entity.entity_type is EntityType.LINE
    )
    circle = next(
        entity for entity in sample_context.entities if entity.entity_type is EntityType.CIRCLE
    )
    polyline = next(
        entity for entity in sample_context.entities if entity.entity_type is EntityType.LWPOLYLINE
    )

    assert line.geometry is not None
    assert line.geometry.kind is GeometryKind.LINE
    assert len(line.geometry.points) == 2
    assert circle.geometry is not None
    assert circle.geometry.radius == 5.0
    assert polyline.geometry is not None
    assert polyline.geometry.closed is True
