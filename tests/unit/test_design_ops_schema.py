"""Tests for design_ops_schema — layout recommendations, revision summaries,
takeoff candidates, and scope-style summary outputs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.cad_schema import TextProvenance
from cad_dxf_agent.models.design_ops_schema import (
    ChangeSummaryEntry,
    CustomerRevisionSummary,
    LayoutRecommendation,
    LayoutRecommendationResult,
    RecommendationType,
    ScopeSection,
    ScopeSectionType,
    ScopeSummary,
    TakeoffCandidateResult,
    TakeoffConfidence,
    TakeoffItem,
)

# ---------------------------------------------------------------------------
# RecommendationType
# ---------------------------------------------------------------------------


class TestRecommendationType:
    def test_has_all_four_values(self):
        assert len(RecommendationType) == 4

    def test_string_values(self):
        assert RecommendationType.REGION_USAGE == "region_usage"
        assert RecommendationType.PLACEMENT_GUIDANCE == "placement_guidance"
        assert RecommendationType.LAYOUT_ALTERNATIVE == "layout_alternative"
        assert RecommendationType.GENERAL_OBSERVATION == "general_observation"

    def test_is_str_enum(self):
        assert isinstance(RecommendationType.REGION_USAGE, str)


# ---------------------------------------------------------------------------
# LayoutRecommendation
# ---------------------------------------------------------------------------


class TestLayoutRecommendation:
    def test_creation_with_all_fields(self):
        rec = LayoutRecommendation(
            type=RecommendationType.PLACEMENT_GUIDANCE,
            title="Space columns evenly",
            description="Columns are unevenly distributed.",
            rationale="Even spacing reduces coordination errors.",
            confidence=0.85,
            caveats=["Verify against grid plan."],
            affected_layers=["STRUCTURAL"],
            affected_region="Grid A-D",
        )
        assert rec.type == RecommendationType.PLACEMENT_GUIDANCE
        assert rec.title == "Space columns evenly"
        assert rec.confidence == 0.85
        assert rec.caveats == ["Verify against grid plan."]
        assert rec.affected_layers == ["STRUCTURAL"]
        assert rec.affected_region == "Grid A-D"

    def test_defaults(self):
        rec = LayoutRecommendation(
            type=RecommendationType.GENERAL_OBSERVATION,
            title="Observation",
            description="Something was observed.",
            rationale="Because.",
            confidence=0.5,
        )
        assert rec.evidence == []
        assert rec.caveats == []
        assert rec.affected_layers == []
        assert rec.affected_region is None

    def test_confidence_lower_bound(self):
        rec = LayoutRecommendation(
            type=RecommendationType.GENERAL_OBSERVATION,
            title="T",
            description="D",
            rationale="R",
            confidence=0.0,
        )
        assert rec.confidence == 0.0

    def test_confidence_upper_bound(self):
        rec = LayoutRecommendation(
            type=RecommendationType.GENERAL_OBSERVATION,
            title="T",
            description="D",
            rationale="R",
            confidence=1.0,
        )
        assert rec.confidence == 1.0

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            LayoutRecommendation(
                type=RecommendationType.GENERAL_OBSERVATION,
                title="T",
                description="D",
                rationale="R",
                confidence=1.1,
            )


# ---------------------------------------------------------------------------
# LayoutRecommendationResult
# ---------------------------------------------------------------------------


class TestLayoutRecommendationResult:
    def test_defaults(self):
        result = LayoutRecommendationResult()
        assert result.recommendations == []
        assert result.drawing_summary == ""
        assert result.methodology == "deterministic_analysis"
        assert result.total_recommendations == 0
        assert result.aggregate_confidence == 0.0
        assert result.ambiguity_flags == []
        assert result.limitations == []

    def test_serialization_to_dict(self):
        result = LayoutRecommendationResult(
            drawing_summary="10 entities across 3 layers",
            total_recommendations=2,
            aggregate_confidence=0.75,
            ambiguity_flags=["partial_region"],
        )
        data = result.model_dump()
        assert data["drawing_summary"] == "10 entities across 3 layers"
        assert data["total_recommendations"] == 2
        assert data["aggregate_confidence"] == 0.75
        assert "partial_region" in data["ambiguity_flags"]


# ---------------------------------------------------------------------------
# ChangeSummaryEntry
# ---------------------------------------------------------------------------


class TestChangeSummaryEntry:
    def test_creation(self):
        entry = ChangeSummaryEntry(
            change_type="added",
            plain_description="A line was added to the drawing.",
            technical_detail="handle=A1F",
            layer="STRUCTURAL",
            confidence=0.9,
        )
        assert entry.change_type == "added"
        assert entry.plain_description == "A line was added to the drawing."
        assert entry.layer == "STRUCTURAL"
        assert entry.confidence == 0.9

    def test_change_type_field_accepts_any_string(self):
        for change_type in ("added", "removed", "modified", "moved"):
            entry = ChangeSummaryEntry(
                change_type=change_type,
                plain_description="desc",
            )
            assert entry.change_type == change_type

    def test_defaults(self):
        entry = ChangeSummaryEntry(change_type="added", plain_description="desc")
        assert entry.technical_detail == ""
        assert entry.layer is None
        assert entry.evidence == []
        assert entry.confidence == 1.0


# ---------------------------------------------------------------------------
# CustomerRevisionSummary
# ---------------------------------------------------------------------------


class TestCustomerRevisionSummary:
    def test_creation(self):
        summary = CustomerRevisionSummary(
            headline="3 change(s) detected: 1 added, 2 removed",
            change_count=3,
            areas_affected=["STRUCTURAL", "NOTES"],
        )
        assert summary.headline == "3 change(s) detected: 1 added, 2 removed"
        assert summary.change_count == 3
        assert "STRUCTURAL" in summary.areas_affected

    def test_defaults(self):
        summary = CustomerRevisionSummary(headline="No changes detected.")
        assert summary.key_changes == []
        assert summary.overall_assessment == ""
        assert summary.change_count == 0
        assert summary.areas_affected == []
        assert summary.ambiguity_flags == []
        assert summary.caveats == []
        assert summary.missing_context == []

    def test_empty_key_changes(self):
        summary = CustomerRevisionSummary(headline="No changes.", key_changes=[])
        assert summary.key_changes == []


# ---------------------------------------------------------------------------
# TakeoffConfidence
# ---------------------------------------------------------------------------


class TestTakeoffConfidence:
    def test_has_all_four_values(self):
        assert len(TakeoffConfidence) == 4

    def test_string_values(self):
        assert TakeoffConfidence.HIGH == "high"
        assert TakeoffConfidence.MEDIUM == "medium"
        assert TakeoffConfidence.LOW == "low"
        assert TakeoffConfidence.ESTIMATE_ONLY == "estimate_only"

    def test_is_str_enum(self):
        assert isinstance(TakeoffConfidence.HIGH, str)


# ---------------------------------------------------------------------------
# TakeoffItem
# ---------------------------------------------------------------------------


class TestTakeoffItem:
    def test_creation(self):
        item = TakeoffItem(
            name="COLUMN",
            quantity=12,
            unit="ea",
            source_layer="STRUCTURAL",
            source_block_name="COL-A",
            entity_handles=["A1", "A2"],
            confidence=TakeoffConfidence.HIGH,
        )
        assert item.name == "COLUMN"
        assert item.quantity == 12
        assert item.unit == "ea"
        assert item.source_layer == "STRUCTURAL"
        assert item.source_block_name == "COL-A"
        assert item.confidence == TakeoffConfidence.HIGH

    def test_text_provenance_field(self):
        item = TakeoffItem(
            name="Beam count",
            quantity=4,
            source_layer="NOTES",
            text_provenance=TextProvenance.RASTER_OCR_TEXT,
        )
        assert item.text_provenance == TextProvenance.RASTER_OCR_TEXT

    def test_text_provenance_none_by_default(self):
        item = TakeoffItem(name="Beam", quantity=1, source_layer="STRUCTURAL")
        assert item.text_provenance is None

    def test_defaults(self):
        item = TakeoffItem(name="Item", quantity=5, source_layer="LAYER-A")
        assert item.unit is None
        assert item.source_block_name is None
        assert item.entity_handles == []
        assert item.confidence == TakeoffConfidence.MEDIUM
        assert item.caveats == []


# ---------------------------------------------------------------------------
# TakeoffCandidateResult
# ---------------------------------------------------------------------------


class TestTakeoffCandidateResult:
    def test_defaults(self):
        result = TakeoffCandidateResult()
        assert result.items == []
        assert result.methodology == "entity_counting"
        assert result.total_items == 0
        assert result.total_quantity_items == 0
        assert result.aggregate_confidence == TakeoffConfidence.MEDIUM
        assert result.ambiguity_flags == []
        assert result.provenance_warnings == []
        assert result.caveats == []

    def test_with_items(self):
        item = TakeoffItem(name="DOOR", quantity=6, source_layer="DOORS")
        result = TakeoffCandidateResult(items=[item], total_items=1, total_quantity_items=6)
        assert len(result.items) == 1
        assert result.items[0].name == "DOOR"


# ---------------------------------------------------------------------------
# ScopeSectionType
# ---------------------------------------------------------------------------


class TestScopeSectionType:
    def test_has_all_four_values(self):
        assert len(ScopeSectionType) == 4

    def test_string_values(self):
        assert ScopeSectionType.LAYOUT_RECOMMENDATIONS == "layout_recommendations"
        assert ScopeSectionType.REVISION_SUMMARY == "revision_summary"
        assert ScopeSectionType.TAKEOFF_CANDIDATES == "takeoff_candidates"
        assert ScopeSectionType.GENERAL_NOTES == "general_notes"


# ---------------------------------------------------------------------------
# ScopeSection
# ---------------------------------------------------------------------------


class TestScopeSection:
    def test_creation(self):
        section = ScopeSection(
            section_type=ScopeSectionType.LAYOUT_RECOMMENDATIONS,
            title="Layout Recommendations",
            content={"total_recommendations": 2},
            available=True,
            confidence=0.8,
            caveats=["Partial region only."],
        )
        assert section.section_type == ScopeSectionType.LAYOUT_RECOMMENDATIONS
        assert section.title == "Layout Recommendations"
        assert section.content["total_recommendations"] == 2
        assert section.available is True
        assert section.confidence == 0.8

    def test_available_defaults_true(self):
        section = ScopeSection(
            section_type=ScopeSectionType.GENERAL_NOTES,
            title="Notes",
        )
        assert section.available is True

    def test_available_can_be_false(self):
        section = ScopeSection(
            section_type=ScopeSectionType.TAKEOFF_CANDIDATES,
            title="Takeoff",
            available=False,
        )
        assert section.available is False


# ---------------------------------------------------------------------------
# ScopeSummary
# ---------------------------------------------------------------------------


class TestScopeSummary:
    def test_creation(self):
        section = ScopeSection(
            section_type=ScopeSectionType.GENERAL_NOTES,
            title="Notes",
            confidence=0.7,
        )
        summary = ScopeSummary(
            sections=[section],
            aggregate_confidence=0.7,
            ambiguity_flags=["partial_region"],
            caveats=["Region-scoped only."],
        )
        assert len(summary.sections) == 1
        assert summary.aggregate_confidence == 0.7
        assert "partial_region" in summary.ambiguity_flags

    def test_generated_at_auto_set(self):
        summary = ScopeSummary()
        assert summary.generated_at != ""
        # ISO 8601 format — contains a 'T' separator
        assert "T" in summary.generated_at

    def test_caveats_list(self):
        summary = ScopeSummary(caveats=["caveat one", "caveat two"])
        assert len(summary.caveats) == 2

    def test_defaults(self):
        summary = ScopeSummary()
        assert summary.title == "Design Operations Scope Summary"
        assert summary.sections == []
        assert summary.aggregate_confidence == 0.0
        assert summary.ambiguity_flags == []
        assert summary.omitted_sections == []
        assert summary.caveats == []
