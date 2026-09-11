"""Fail-closed drawing CRS resolution and WGS84 transformation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ezdxf.math import Matrix44
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError

from ..models.cad_schema import CRSSource, DrawingCRS, DrawingUnit, Point2D
from .units import conversion_factor


class CRSResolutionError(ValueError):
    """A supplied or embedded CRS exists but cannot be resolved safely."""


class MissingCRSError(ValueError):
    """A geospatial transform was requested for a drawing without a CRS."""


def _normalized_crs(value: Any, source: CRSSource) -> DrawingCRS:
    try:
        parsed = CRS.from_user_input(value)
    except CRSError as exc:
        raise CRSResolutionError(f"Invalid {source.value} CRS: {exc}") from exc
    authority = parsed.to_authority()
    definition = f"{authority[0]}:{authority[1]}" if authority else parsed.to_wkt()
    return DrawingCRS(definition=definition, name=parsed.name, source=source)


def resolve_drawing_crs(
    document: Any,
    dxf_path: str | Path,
    override: Any | None = None,
) -> DrawingCRS | None:
    """Resolve CRS with deterministic precedence: caller, sibling PRJ, DXF GEODATA.

    Any present but invalid source raises ``CRSResolutionError``. Returning
    ``None`` therefore means no CRS metadata was supplied, never that malformed
    metadata was silently ignored.
    """
    if override is not None:
        return _normalized_crs(override, CRSSource.CALLER)

    prj_path = Path(dxf_path).with_suffix(".prj")
    if prj_path.is_file():
        try:
            definition = prj_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CRSResolutionError(f"Cannot read CRS sidecar {prj_path}: {exc}") from exc
        if not definition:
            raise CRSResolutionError(f"CRS sidecar is empty: {prj_path}")
        return _normalized_crs(definition, CRSSource.PRJ)

    try:
        geodata = document.modelspace().get_geodata()
    except Exception as exc:
        raise CRSResolutionError(f"Cannot inspect DXF GEODATA: {exc}") from exc
    if geodata is None:
        return None

    try:
        matrix, epsg = geodata.get_crs_transformation()
        resolved = _normalized_crs(f"EPSG:{epsg}", CRSSource.DXF_GEODATA)
    except Exception as exc:
        raise CRSResolutionError(f"Invalid or unsupported DXF GEODATA: {exc}") from exc
    return resolved.model_copy(update={"drawing_to_crs_matrix": tuple(matrix)})


def _require_crs(crs: DrawingCRS | None) -> DrawingCRS:
    if crs is None:
        raise MissingCRSError(
            "Drawing has no CRS; pass crs=... to load_dxf(), add a sibling .prj, "
            "or provide supported DXF GEODATA."
        )
    return crs


def validate_crs_units(crs: DrawingCRS | None, drawing_unit: DrawingUnit) -> None:
    """Reject a known DXF unit that contradicts the resolved projected CRS."""
    if crs is None or drawing_unit is DrawingUnit.UNITLESS:
        return
    parsed = CRS.from_user_input(crs.definition)
    if not parsed.is_projected:
        raise CRSResolutionError(
            f"DXF $INSUNITS={drawing_unit.name.lower()} conflicts with geographic CRS "
            f"{crs.definition}; use unitless longitude/latitude coordinates or a projected CRS."
        )
    if crs.source is CRSSource.DXF_GEODATA:
        # GEODATA's affine matrix includes its declared horizontal unit scale.
        return
    axis_factor = parsed.axis_info[0].unit_conversion_factor if parsed.axis_info else None
    if axis_factor is None:
        raise CRSResolutionError(f"Cannot determine coordinate units for {crs.definition}")
    drawing_factor = conversion_factor(drawing_unit, DrawingUnit.METERS)
    if not abs(drawing_factor - axis_factor) <= max(abs(axis_factor), 1.0) * 1e-9:
        raise CRSResolutionError(
            f"DXF $INSUNITS={drawing_unit.name.lower()} conflicts with {crs.definition} "
            f"axis unit {parsed.axis_info[0].unit_name}; correct $INSUNITS or choose a "
            "matching CRS."
        )


def _apply_matrix(point: Point2D, values: tuple[float, ...], *, inverse: bool) -> Point2D:
    matrix = Matrix44(values)
    if inverse:
        matrix.inverse()
    transformed = matrix.transform((point.x, point.y, point.z or 0.0))
    return Point2D(
        x=transformed.x,
        y=transformed.y,
        z=transformed.z if point.z is not None else None,
    )


def drawing_to_wgs84(point: Point2D, crs: DrawingCRS | None) -> Point2D:
    """Transform one drawing point to longitude/latitude in WGS84."""
    resolved = _require_crs(crs)
    source_point = point
    if resolved.drawing_to_crs_matrix is not None:
        source_point = _apply_matrix(point, resolved.drawing_to_crs_matrix, inverse=False)
    transformer = Transformer.from_crs(resolved.definition, "EPSG:4326", always_xy=True)
    if source_point.z is None:
        longitude, latitude = transformer.transform(source_point.x, source_point.y)
        return Point2D(x=longitude, y=latitude)
    longitude, latitude, elevation = transformer.transform(
        source_point.x, source_point.y, source_point.z
    )
    return Point2D(x=longitude, y=latitude, z=elevation)


def wgs84_to_drawing(point: Point2D, crs: DrawingCRS | None) -> Point2D:
    """Transform a WGS84 longitude/latitude point into drawing coordinates."""
    resolved = _require_crs(crs)
    transformer = Transformer.from_crs("EPSG:4326", resolved.definition, always_xy=True)
    if point.z is None:
        x, y = transformer.transform(point.x, point.y)
        transformed = Point2D(x=x, y=y)
    else:
        x, y, z = transformer.transform(point.x, point.y, point.z)
        transformed = Point2D(x=x, y=y, z=z)
    if resolved.drawing_to_crs_matrix is not None:
        return _apply_matrix(transformed, resolved.drawing_to_crs_matrix, inverse=True)
    return transformed
