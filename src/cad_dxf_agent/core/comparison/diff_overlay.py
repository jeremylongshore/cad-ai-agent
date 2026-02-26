"""Diff overlay — write color-coded change layers to a DXF file."""

from __future__ import annotations

import logging
from pathlib import Path

import ezdxf

from ...models.cad_schema import Point2D
from ...models.comparison_schema import (
    ChangeCategory,
    ComparisonResult,
    DiffOverlayLayers,
    EntityChange,
    GeometrySnapshot,
)
from ...otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def write_diff_overlay(
    master_path: str | Path,
    comparison_result: ComparisonResult,
    output_path: str | Path,
) -> Path:
    """Write a diff overlay DXF based on comparison results.

    Opens the master DXF, adds overlay layers, duplicates changed entities
    onto the appropriate color-coded layer, and saves to output_path.

    Args:
        master_path: Path to the master DXF (used as the base).
        comparison_result: Classified changes from the comparison engine.
        output_path: Where to save the overlay DXF.

    Returns:
        Path to the saved overlay DXF.
    """
    with tracer.start_as_current_span("cad.compare.write_diff_overlay") as span:
        master_path = Path(master_path)
        output_path = Path(output_path)

        span.set_attribute("cad.compare.output_file", output_path.name)

        doc = ezdxf.readfile(str(master_path))
        msp = doc.modelspace()

        # Create overlay layers
        for layer_name, color_code in DiffOverlayLayers.ALL:
            if layer_name not in doc.layers:
                doc.layers.add(layer_name, color=color_code)

        changes_drawn = 0
        for change in comparison_result.changes:
            if change.category == ChangeCategory.UNCHANGED:
                continue

            try:
                _draw_change(msp, change)
                changes_drawn += 1
            except Exception:
                logger.warning(
                    "Failed to draw overlay for %s change",
                    change.category.value,
                    exc_info=True,
                )

        span.set_attribute("cad.compare.changes_drawn", changes_drawn)

        doc.saveas(str(output_path))
        return output_path


def _draw_change(
    msp: ezdxf.layouts.BaseLayout,
    change: EntityChange,
) -> None:
    """Draw one change onto the appropriate overlay layer."""
    category = change.category

    if category == ChangeCategory.ADDED:
        layer_name = DiffOverlayLayers.ADDED[0]
        snap = change.revision_snapshot
        if snap:
            _draw_snapshot(msp, snap, layer_name)

    elif category == ChangeCategory.REMOVED:
        layer_name = DiffOverlayLayers.REMOVED[0]
        snap = change.master_snapshot
        if snap:
            _draw_snapshot(msp, snap, layer_name)

    elif category == ChangeCategory.MODIFIED:
        layer_name = DiffOverlayLayers.MODIFIED[0]
        # Draw both master (will appear as old) and revision (as new)
        if change.master_snapshot:
            _draw_snapshot(msp, change.master_snapshot, layer_name)
        if change.revision_snapshot:
            _draw_snapshot(msp, change.revision_snapshot, layer_name)

    elif category == ChangeCategory.MOVED:
        layer_name = DiffOverlayLayers.MOVED[0]
        # Draw entity at new position
        if change.revision_snapshot:
            _draw_snapshot(msp, change.revision_snapshot, layer_name)
        # Draw displacement arrow from old centroid to new centroid
        if change.master_snapshot and change.revision_snapshot:
            _draw_arrow(
                msp,
                change.master_snapshot.centroid,
                change.revision_snapshot.centroid,
                layer_name,
            )


def _draw_snapshot(
    msp: ezdxf.layouts.BaseLayout,
    snap: GeometrySnapshot,
    layer: str,
) -> None:
    """Recreate entity geometry on the specified overlay layer."""
    etype = snap.entity_type.value

    if etype == "LINE" and len(snap.points) >= 2:
        msp.add_line(
            (snap.points[0].x, snap.points[0].y),
            (snap.points[1].x, snap.points[1].y),
            dxfattribs={"layer": layer},
        )

    elif etype == "LWPOLYLINE" and len(snap.points) >= 2:
        pts = [(p.x, p.y) for p in snap.points]
        msp.add_lwpolyline(pts, dxfattribs={"layer": layer})

    elif etype in ("TEXT", "MTEXT") and snap.points:
        text = snap.text_content or ""
        if etype == "TEXT":
            msp.add_text(
                text,
                dxfattribs={
                    "layer": layer,
                    "height": 1.0,
                    "insert": (snap.points[0].x, snap.points[0].y),
                },
            )
        else:
            msp.add_mtext(
                text,
                dxfattribs={
                    "layer": layer,
                    "insert": (snap.points[0].x, snap.points[0].y),
                    "char_height": 1.0,
                },
            )

    elif etype == "INSERT" and snap.points:
        # Can't copy block refs without the block def — draw a marker instead
        p = snap.points[0]
        _draw_marker(msp, p, layer, label=snap.block_name or "BLK")

    elif etype == "CIRCLE" and snap.points:
        radius = snap.attributes.get("radius", 1.0)
        msp.add_circle(
            (snap.points[0].x, snap.points[0].y),
            radius=radius,
            dxfattribs={"layer": layer},
        )

    elif etype == "ARC" and snap.points:
        radius = snap.attributes.get("radius", 1.0)
        start_angle = snap.attributes.get("start_angle", 0.0)
        end_angle = snap.attributes.get("end_angle", 360.0)
        msp.add_arc(
            (snap.points[0].x, snap.points[0].y),
            radius=radius,
            start_angle=start_angle,
            end_angle=end_angle,
            dxfattribs={"layer": layer},
        )

    elif etype == "POLYLINE" and len(snap.points) >= 2:
        # Approximate as LWPOLYLINE on the overlay
        pts = [(p.x, p.y) for p in snap.points]
        msp.add_lwpolyline(pts, dxfattribs={"layer": layer})

    elif etype == "ELLIPSE" and snap.points:
        ratio = snap.attributes.get("ratio", 0.5)
        major_axis = snap.attributes.get("major_axis", (5, 0, 0))
        msp.add_ellipse(
            center=(snap.points[0].x, snap.points[0].y),
            major_axis=major_axis,
            ratio=ratio,
            dxfattribs={"layer": layer},
        )

    elif snap.points:
        # Fallback: draw a marker at centroid
        _draw_marker(msp, snap.centroid, layer, label=etype)


def _draw_arrow(
    msp: ezdxf.layouts.BaseLayout,
    from_pt: Point2D,
    to_pt: Point2D,
    layer: str,
) -> None:
    """Draw a simple line from old position to new position."""
    msp.add_line(
        (from_pt.x, from_pt.y),
        (to_pt.x, to_pt.y),
        dxfattribs={"layer": layer},
    )


def _draw_marker(
    msp: ezdxf.layouts.BaseLayout,
    point: Point2D,
    layer: str,
    label: str = "X",
    size: float = 1.0,
) -> None:
    """Draw an X marker with label at the given point."""
    x, y = point.x, point.y
    msp.add_line((x - size, y - size), (x + size, y + size), dxfattribs={"layer": layer})
    msp.add_line((x - size, y + size), (x + size, y - size), dxfattribs={"layer": layer})
    msp.add_text(
        label,
        dxfattribs={"layer": layer, "height": size * 0.8, "insert": (x + size * 1.2, y)},
    )
