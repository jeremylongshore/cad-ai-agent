"""Tests for DXF drawing-unit conversion helpers."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.units import conversion_factor, inches_to_drawing_units
from cad_dxf_agent.models.cad_schema import DrawingUnit


def test_metric_and_imperial_conversion_factors() -> None:
    assert conversion_factor(DrawingUnit.MILLIMETERS, DrawingUnit.INCHES) == pytest.approx(
        1.0 / 25.4
    )
    assert conversion_factor(DrawingUnit.FEET, DrawingUnit.INCHES) == 12.0
    assert inches_to_drawing_units(DrawingUnit.MILLIMETERS) == pytest.approx(25.4)


def test_us_survey_foot_uses_exact_definition() -> None:
    expected_inches = (1200.0 / 3937.0) * 100.0 / 2.54
    assert conversion_factor(DrawingUnit.US_SURVEY_FEET, DrawingUnit.INCHES) == pytest.approx(
        expected_inches
    )
