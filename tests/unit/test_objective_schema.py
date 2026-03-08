"""Tests for objective_schema models — RequestClass, ObjectiveTag, DocumentFamilyHint."""

from cad_dxf_agent.models.objective_schema import (
    AnalysisResult,
    DocumentFamilyHint,
    ObjectiveClassification,
    ObjectiveTag,
    RecommendationOption,
    RecommendationSet,
    RequestClass,
    StageGate,
    StagePipelineDefinition,
)


class TestRequestClass:
    """RequestClass enum has 8 members."""

    def test_member_count(self):
        assert len(RequestClass) == 8

    def test_all_values(self):
        expected = {
            "understand", "estimate", "recommend", "optimize",
            "modify", "summarize", "compare", "validate",
        }
        assert {v.value for v in RequestClass} == expected

    def test_validate_is_new(self):
        assert RequestClass.VALIDATE == "validate"


class TestObjectiveTag:
    """ObjectiveTag enum has 15 members."""

    def test_member_count(self):
        assert len(ObjectiveTag) == 15

    def test_new_tags_present(self):
        new_tags = {
            "contractor_communication", "reviewer_communication",
            "space_count", "equipment_count",
            "layout_improvement", "missing_items",
        }
        values = {v.value for v in ObjectiveTag}
        assert new_tags.issubset(values)

    def test_original_tags_preserved(self):
        original_tags = {
            "cost_reduction", "labor_reduction", "area_change",
            "aesthetics", "quantity_estimation", "customer_communication",
            "constructability", "compliance", "revision_explanation",
        }
        values = {v.value for v in ObjectiveTag}
        assert original_tags.issubset(values)


class TestDocumentFamilyHint:
    """DocumentFamilyHint enum has 20 members."""

    def test_member_count(self):
        assert len(DocumentFamilyHint) == 20

    def test_unknown_is_default(self):
        assert DocumentFamilyHint.UNKNOWN == "unknown"

    def test_key_families_present(self):
        families = {v.value for v in DocumentFamilyHint}
        assert "residential_architectural" in families
        assert "landscape" in families
        assert "electrical" in families
        assert "structural" in families
        assert "plumbing" in families


class TestObjectiveClassification:
    """ObjectiveClassification model with document_family field."""

    def test_default_document_family(self):
        c = ObjectiveClassification(
            request_class=RequestClass.UNDERSTAND,
            confidence=0.9,
        )
        assert c.document_family == DocumentFamilyHint.UNKNOWN

    def test_all_fields(self):
        c = ObjectiveClassification(
            request_class=RequestClass.VALIDATE,
            objective_tag=ObjectiveTag.MISSING_ITEMS,
            document_family=DocumentFamilyHint.RESIDENTIAL_ARCHITECTURAL,
            confidence=0.85,
            source="heuristic",
            matched_patterns=["\\bmissing\\b"],
        )
        assert c.request_class == RequestClass.VALIDATE
        assert c.objective_tag == ObjectiveTag.MISSING_ITEMS
        assert c.document_family == DocumentFamilyHint.RESIDENTIAL_ARCHITECTURAL

    def test_serialization_roundtrip(self):
        c = ObjectiveClassification(
            request_class=RequestClass.ESTIMATE,
            objective_tag=ObjectiveTag.SPACE_COUNT,
            confidence=0.8,
        )
        d = c.model_dump()
        c2 = ObjectiveClassification(**d)
        assert c2.request_class == c.request_class
        assert c2.objective_tag == c.objective_tag
        assert c2.document_family == c.document_family


class TestAnalysisResult:
    def test_defaults(self):
        r = AnalysisResult(summary="test")
        assert r.confidence == 0.5
        assert r.evidence == []


class TestRecommendationSet:
    def test_with_options(self):
        opt = RecommendationOption(
            title="Remove plants",
            description="Remove 12 plants from east bed",
            estimated_impact="~$2,400 savings",
            tradeoffs=["Reduced screening"],
        )
        rs = RecommendationSet(options=[opt], selected_index=0)
        assert len(rs.options) == 1
        assert rs.selected_index == 0


class TestStageGate:
    def test_default_status(self):
        g = StageGate(stage_name="analyze")
        assert g.status == "pending"
        assert g.timestamp  # auto-set

    def test_completed(self):
        g = StageGate(stage_name="recommend", status="completed", output_summary="3 options")
        assert g.status == "completed"


class TestStagePipelineDefinition:
    def test_stages(self):
        p = StagePipelineDefinition(
            stages=["analyze", "recommend", "plan"],
            output_mode="staged",
        )
        assert len(p.stages) == 3
        assert p.output_mode == "staged"
