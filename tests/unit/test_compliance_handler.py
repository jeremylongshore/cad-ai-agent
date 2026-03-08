"""Tests for the compliance stage handler (EPIC-CAD-21)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.stage_handlers.compliance_handler import (
    ComplianceHandler,
    _build_summary,
    _detect_profile,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.compliance_schema import ComplianceReport
from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    ObjectiveTag,
    RequestClass,
)
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult

# --- Helpers ---


def _make_context(entities=None, layers=None):
    layer_rules = [LayerRule(name=n) for n in (layers or ["0"])]
    return DrawingContext(
        file_path="test.dxf",
        entities=entities or [],
        layers=layer_rules,
    )


def _make_classification():
    return ObjectiveClassification(
        request_class=RequestClass.VALIDATE,
        objective_tag=ObjectiveTag.COMPLIANCE,
        confidence=0.9,
    )


# --- Profile detection ---


class TestDetectProfile:
    def test_ada_keyword(self):
        assert _detect_profile("check ADA compliance") == "ada"

    def test_accessibility_keyword(self):
        assert _detect_profile("is this accessible?") == "ada"

    def test_residential_keyword(self):
        assert _detect_profile("residential code check") == "residential"

    def test_irc_keyword(self):
        assert _detect_profile("IRC compliance") == "residential"

    def test_default_is_ibc(self):
        assert _detect_profile("check compliance") == "ibc-2021"

    def test_empty_prompt_defaults_to_ibc(self):
        assert _detect_profile("") == "ibc-2021"


# --- Summary builder ---


class TestBuildSummary:
    def test_passed_report(self):
        report = ComplianceReport(
            profile_name="ADA",
            findings=[],
            checks_run=["door_widths"],
            violation_count=0,
            warning_count=0,
            pass_count=3,
            zone_count=2,
            entity_count=10,
        )
        summary = _build_summary(report)
        assert "PASSED" in summary
        assert "ADA" in summary

    def test_failed_report(self):
        report = ComplianceReport(
            profile_name="IBC-2021",
            findings=[],
            checks_run=["door_widths"],
            violation_count=2,
            warning_count=1,
            pass_count=0,
            zone_count=0,
            entity_count=5,
        )
        summary = _build_summary(report)
        assert "FAILED" in summary
        assert "2 violation" in summary
        assert "1 warning" in summary


# --- Handler execution ---


class TestComplianceHandler:
    def test_no_drawing_context(self):
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={},
            prompt="check compliance",
        )
        assert result["compliance_report"] is None
        assert "No drawing context" in result["summary"]

    def test_with_empty_drawing(self):
        ctx = _make_context()
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx},
            prompt="check compliance",
        )
        assert result["compliance_report"] is not None
        assert "compliance_score" in result
        assert "compliance_passed" in result
        assert "compliance_findings" in result
        assert isinstance(result["compliance_checks_run"], list)

    def test_with_dict_drawing_context(self):
        ctx = _make_context()
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx.model_dump()},
            prompt="check ADA compliance",
        )
        assert result["compliance_report"] is not None
        assert result["compliance_profile"] == "ada"

    def test_profile_from_prompt_ada(self):
        ctx = _make_context()
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx},
            prompt="check ADA accessibility",
        )
        assert result["compliance_profile"] == "ada"

    def test_profile_from_prompt_residential(self):
        ctx = _make_context()
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx},
            prompt="residential code check",
        )
        assert result["compliance_profile"] == "residential"

    def test_uses_precomputed_zones(self):
        """Handler should use zones from prior detect_zones stage."""
        ctx = _make_context()
        zone = DetectedZone(
            zone_id="z1",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=100, y=0),
                Point2D(x=100, y=50),
                Point2D(x=0, y=50),
            ],
            area=5000.0,
            perimeter=300.0,
            centroid=Point2D(x=50, y=25),
            inferred_type="hallway",
            source_handles=["H1"],
            confidence=1.0,
        )
        zones_result = ZoneDetectionResult(
            zones=[zone],
            total_area=5000.0,
            zone_count=1,
            confidence=1.0,
            warnings=[],
        )
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={
                "drawing_context": ctx,
                "zones": zones_result,
            },
            prompt="check compliance",
        )
        # Should have run checks including corridor checks
        assert result["compliance_report"] is not None

    def test_uses_precomputed_zones_list(self):
        """Handler should reconstruct ZoneDetectionResult from zone list."""
        ctx = _make_context()
        zone = DetectedZone(
            zone_id="z1",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=100, y=0),
                Point2D(x=100, y=50),
                Point2D(x=0, y=50),
            ],
            area=5000.0,
            perimeter=300.0,
            centroid=Point2D(x=50, y=25),
            inferred_type="room",
            source_handles=["H1"],
            confidence=1.0,
        )
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={
                "drawing_context": ctx,
                "zones": [zone],
                "total_area": 5000.0,
                "zone_count": 1,
                "zone_confidence": 1.0,
                "zone_warnings": [],
            },
            prompt="check compliance",
        )
        assert result["compliance_report"] is not None
        assert result["compliance_checks_run"]

    def test_result_keys(self):
        ctx = _make_context()
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx},
            prompt="check compliance",
        )
        expected_keys = {
            "compliance_report",
            "compliance_profile",
            "compliance_score",
            "compliance_passed",
            "compliance_findings",
            "compliance_violations",
            "compliance_warnings",
            "compliance_checks_run",
            "summary",
        }
        assert expected_keys <= set(result.keys())

    def test_score_is_numeric(self):
        ctx = _make_context()
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx},
            prompt="check compliance",
        )
        assert isinstance(result["compliance_score"], (int, float))
        assert 0 <= result["compliance_score"] <= 100

    def test_door_violation_detected(self):
        """Narrow door should produce a violation."""
        entities = [
            EntityRef(
                handle="D1",
                entity_type=EntityType.INSERT,
                layer="DOORS",
                block_name="DOOR_24",
                insert_point=Point2D(x=50, y=50),
                attributes={"width": "24"},
            ),
        ]
        ctx = _make_context(entities=entities, layers=["DOORS"])
        handler = ComplianceHandler()
        result = handler.execute(
            classification=_make_classification(),
            context={"drawing_context": ctx},
            prompt="check compliance",
        )
        violations = [
            f for f in result["compliance_findings"]
            if f["severity"] == "violation"
        ]
        assert len(violations) >= 1
        assert any("door" in v["title"].lower() for v in violations)
