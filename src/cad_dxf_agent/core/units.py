"""DXF drawing-unit inspection and conversion helpers."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from ..models.cad_schema import DrawingUnit

# Inches represented by one source drawing unit. Survey units use the exact
# US survey-foot definition (1200 / 3937 metres).
_INCHES_PER_UNIT: dict[DrawingUnit, float] = {
    DrawingUnit.INCHES: 1.0,
    DrawingUnit.FEET: 12.0,
    DrawingUnit.MILES: 63_360.0,
    DrawingUnit.MILLIMETERS: 1.0 / 25.4,
    DrawingUnit.CENTIMETERS: 1.0 / 2.54,
    DrawingUnit.METERS: 100.0 / 2.54,
    DrawingUnit.KILOMETERS: 100_000.0 / 2.54,
    DrawingUnit.MICROINCHES: 1e-6,
    DrawingUnit.MILS: 0.001,
    DrawingUnit.YARDS: 36.0,
    DrawingUnit.ANGSTROMS: 1e-10 * 100.0 / 2.54,
    DrawingUnit.NANOMETERS: 1e-9 * 100.0 / 2.54,
    DrawingUnit.MICRONS: 1e-6 * 100.0 / 2.54,
    DrawingUnit.DECIMETERS: 10.0 / 2.54,
    DrawingUnit.DECAMETERS: 1_000.0 / 2.54,
    DrawingUnit.HECTOMETERS: 10_000.0 / 2.54,
    DrawingUnit.GIGAMETERS: 100_000_000_000.0 / 2.54,
    DrawingUnit.ASTRONOMICAL_UNITS: 149_597_870_700.0 * 100.0 / 2.54,
    DrawingUnit.LIGHT_YEARS: 9.4607304725808e15 * 100.0 / 2.54,
    DrawingUnit.PARSECS: 3.085677581491367e16 * 100.0 / 2.54,
    DrawingUnit.US_SURVEY_FEET: (1200.0 / 3937.0) * 100.0 / 2.54,
    DrawingUnit.US_SURVEY_INCHES: (100.0 / 3937.0) * 100.0 / 2.54,
    DrawingUnit.US_SURVEY_YARDS: (3600.0 / 3937.0) * 100.0 / 2.54,
    DrawingUnit.US_SURVEY_MILES: (6_336_000.0 / 3937.0) * 100.0 / 2.54,
}


class DrawingUnitMismatchError(ValueError):
    """Raised when two drawings cannot be converted to a common unit safely."""


def read_drawing_unit(path: str | Path) -> DrawingUnit:
    """Read ``$INSUNITS`` from a DXF, treating invalid values as unitless."""
    doc = ezdxf.readfile(str(path))
    raw = int(doc.header.get("$INSUNITS", 0) or 0)
    try:
        return DrawingUnit(raw)
    except ValueError:
        return DrawingUnit.UNITLESS


def conversion_factor(source: DrawingUnit, target: DrawingUnit) -> float:
    """Return the multiplier for representing source coordinates in target units."""
    if source == target:
        return 1.0
    if DrawingUnit.UNITLESS in (source, target):
        raise DrawingUnitMismatchError(
            f"Cannot convert {source.name.lower()} coordinates to {target.name.lower()}; "
            "set $INSUNITS on both drawings before comparison."
        )
    return _INCHES_PER_UNIT[source] / _INCHES_PER_UNIT[target]


def inches_to_drawing_units(unit: DrawingUnit) -> float:
    """Return how many native drawing units represent one physical inch."""
    if unit == DrawingUnit.UNITLESS:
        return 1.0
    return 1.0 / _INCHES_PER_UNIT[unit]
