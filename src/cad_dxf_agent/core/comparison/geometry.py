"""Geometry extraction — reads ezdxf entities into GeometrySnapshot objects."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import ezdxf

from ...models.cad_schema import EntityType, Point2D
from ...models.comparison_schema import (
    BBoxRegion,
    ComparisonConfig,
    ComparisonProfile,
    GeometrySnapshot,
)
from ...otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Entity types we know how to extract geometry from
_EXTRACTABLE_TYPES = {t.value for t in EntityType}


def extract_snapshots(
    dxf_path: str | Path,
    config: ComparisonConfig | None = None,
    _profile_warnings: list[str] | None = None,
) -> list[GeometrySnapshot]:
    """Extract GeometrySnapshot objects from all model-space entities in a DXF.

    Args:
        dxf_path: Path to the DXF file.
        config: Optional comparison config for layer/type filtering.
        _profile_warnings: If provided, profile warnings are appended to this list.

    Returns:
        List of GeometrySnapshot with full point data per entity.
    """
    with tracer.start_as_current_span("cad.compare.extract_snapshots") as span:
        config = config or ComparisonConfig()
        dxf_path = Path(dxf_path)

        span.set_attribute("cad.compare.file", dxf_path.name)

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

        if config.profile:
            pre_profile_count = len(snapshots)
            profile = config.profile

            # Auto-detect titleblock region if no exclude_regions set
            if not profile.exclude_regions:
                detected = detect_titleblock_region(snapshots)
                if detected is not None:
                    profile = profile.model_copy(update={"exclude_regions": [detected]})

            snapshots = apply_profile(snapshots, profile)

            if _profile_warnings is not None:
                _profile_warnings.extend(
                    check_profile_warnings(pre_profile_count, snapshots, profile)
                )

        span.set_attribute("cad.compare.entities_extracted", len(snapshots))
        span.set_attribute("cad.compare.ignored_layers", len(config.ignored_layers))

        return snapshots


def apply_profile(
    snapshots: list[GeometrySnapshot],
    profile: ComparisonProfile,
) -> list[GeometrySnapshot]:
    """Filter snapshots through a ComparisonProfile.

    Filter order (each step reduces the list):
    1. Entity type — keep only matching types if include_entity_types is set
    2. Layer include — keep only layers matching at least one regex
    3. Layer exclude — drop layers matching any regex
    4. Region exclude — drop entities whose centroid falls inside any exclude_regions
    """
    result = snapshots

    # 1. Entity type filter
    if profile.include_entity_types:
        allowed = {t for t in profile.include_entity_types}
        result = [s for s in result if s.entity_type in allowed]

    # 2. Layer include (keep only matching)
    if profile.include_layers:
        compiled = [re.compile(p, re.IGNORECASE) for p in profile.include_layers]
        result = [s for s in result if any(r.search(s.layer) for r in compiled)]

    # 3. Layer exclude (drop matching)
    if profile.exclude_layers:
        compiled = [re.compile(p, re.IGNORECASE) for p in profile.exclude_layers]
        result = [s for s in result if not any(r.search(s.layer) for r in compiled)]

    # 4. Region exclude (drop centroids inside any bbox)
    if profile.exclude_regions:
        regions = profile.exclude_regions
        result = [
            s for s in result if not any(r.contains(s.centroid.x, s.centroid.y) for r in regions)
        ]

    return result


# Title-block layer patterns (case-insensitive) — mirrors structural() preset
_TITLEBLOCK_PATTERNS = [
    re.compile(r"^title", re.IGNORECASE),
    re.compile(r"^seal", re.IGNORECASE),
    re.compile(r"^revision", re.IGNORECASE),
    re.compile(r"^border", re.IGNORECASE),
]


def detect_titleblock_region(
    snapshots: list[GeometrySnapshot],
    padding: float = 5.0,
) -> BBoxRegion | None:
    """Auto-detect the title block region from entities on title-related layers.

    Returns a BBoxRegion covering all points on matching layers (with padding),
    or None if no title-block entities are found.
    """
    all_pts: list[tuple[float, float]] = []
    for snap in snapshots:
        if any(p.search(snap.layer) for p in _TITLEBLOCK_PATTERNS):
            for pt in snap.points:
                all_pts.append((pt.x, pt.y))

    if not all_pts:
        return None

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    return BBoxRegion(
        min_x=min(xs) - padding,
        min_y=min(ys) - padding,
        max_x=max(xs) + padding,
        max_y=max(ys) + padding,
    )


def check_profile_warnings(
    before_count: int,
    after_snapshots: list[GeometrySnapshot],
    profile: ComparisonProfile,
) -> list[str]:
    """Check for suspicious profile filtering results.

    Returns a list of warning strings (empty if everything looks fine).
    """
    if before_count == 0:
        return []

    after_count = len(after_snapshots)
    excluded_count = before_count - after_count
    excluded_pct = excluded_count / before_count

    warnings: list[str] = []

    if after_count == 0:
        warnings.append(
            f"Profile '{profile.name}' excluded all {before_count} entities — "
            "no geometry remains for comparison."
        )
        return warnings

    if excluded_pct > 0.80:
        warnings.append(
            f"Profile '{profile.name}' excluded {excluded_pct:.0%} of entities "
            f"({excluded_count}/{before_count})."
        )

    if profile.include_entity_types:
        from ...models.cad_schema import EntityType

        structural_types = {EntityType.LINE, EntityType.LWPOLYLINE}
        remaining_types = {s.entity_type for s in after_snapshots}
        if not remaining_types & structural_types:
            warnings.append(
                f"Profile '{profile.name}' filtered out all LINE/LWPOLYLINE entities — "
                "structural geometry may be missing."
            )

    return warnings


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
