"""Tests for ObjectiveClassifier — two-axis heuristic classification."""

import pytest

from cad_dxf_agent.llm.objective_classifier import ObjectiveClassifier
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.objective_schema import (
    DocumentFamilyHint,
    ObjectiveTag,
    RequestClass,
)
from cad_dxf_agent.models.response_schema import TaskFamily


@pytest.fixture
def classifier():
    return ObjectiveClassifier()


class TestRequestClassClassification:
    """Test Axis 1: RequestClass detection."""

    @pytest.mark.parametrize(
        "prompt,expected",
        [
            ("compare these two drawings", RequestClass.COMPARE),
            ("what changed between revisions", RequestClass.COMPARE),
            ("diff the plans", RequestClass.COMPARE),
            ("validate this drawing for completeness", RequestClass.VALIDATE),
            ("check for missing dimensions", RequestClass.VALIDATE),
            ("is this code compliant", RequestClass.VALIDATE),
            ("verify the notes are consistent", RequestClass.VALIDATE),
            ("audit this plan set", RequestClass.VALIDATE),
            ("make this cheaper", RequestClass.OPTIMIZE),
            ("reduce cost by 20%", RequestClass.OPTIMIZE),
            ("optimize the layout", RequestClass.OPTIMIZE),
            ("simplify the design", RequestClass.OPTIMIZE),
            ("move the wall 3 feet north", RequestClass.MODIFY),
            ("delete the door", RequestClass.MODIFY),
            ("add a window here", RequestClass.MODIFY),
            ("rotate this block", RequestClass.MODIFY),
            ("recommend a better layout", RequestClass.RECOMMEND),
            ("suggest improvements", RequestClass.RECOMMEND),
            ("what options do I have", RequestClass.RECOMMEND),
            ("how much would this cost", RequestClass.ESTIMATE),
            ("count all the doors", RequestClass.ESTIMATE),
            ("how many windows are there", RequestClass.ESTIMATE),
            ("generate a takeoff", RequestClass.ESTIMATE),
            ("summarize this drawing", RequestClass.SUMMARIZE),
            ("describe this plan for the homeowner", RequestClass.SUMMARIZE),
            ("give me an overview", RequestClass.SUMMARIZE),
            ("explain to the contractor", RequestClass.SUMMARIZE),
            ("what is on layer WALLS", RequestClass.UNDERSTAND),
            ("where is the front door", RequestClass.UNDERSTAND),
            ("show me the title block", RequestClass.UNDERSTAND),
        ],
    )
    def test_request_class(self, classifier, prompt, expected):
        result = classifier.classify(prompt)
        assert result.request_class == expected, (
            f"Prompt '{prompt}' classified as {result.request_class}, expected {expected}"
        )

    def test_empty_prompt(self, classifier):
        result = classifier.classify("")
        assert result.request_class == RequestClass.UNDERSTAND
        assert result.confidence == 1.0

    def test_whitespace_prompt(self, classifier):
        result = classifier.classify("   ")
        assert result.request_class == RequestClass.UNDERSTAND


class TestObjectiveTagClassification:
    """Test Axis 2: ObjectiveTag detection."""

    @pytest.mark.parametrize(
        "prompt,expected_tag",
        [
            ("how much does this cost", ObjectiveTag.COST_REDUCTION),
            ("reduce labor hours", ObjectiveTag.LABOR_REDUCTION),
            ("shrink the room to 200 sq ft", ObjectiveTag.AREA_CHANGE),
            ("all the fixtures and devices", ObjectiveTag.EQUIPMENT_COUNT),
            ("how many rooms are there", ObjectiveTag.SPACE_COUNT),
            ("summarize for the contractor", ObjectiveTag.CONTRACTOR_COMMUNICATION),
            ("present to the homeowner", ObjectiveTag.CUSTOMER_COMMUNICATION),
            ("prepare for the plan reviewer", ObjectiveTag.REVIEWER_COMMUNICATION),
            ("improve the layout spacing", ObjectiveTag.LAYOUT_IMPROVEMENT),
            ("check for missing dimensions", ObjectiveTag.MISSING_ITEMS),
            ("is this ADA compliant", ObjectiveTag.COMPLIANCE),
            ("what changed in revision 3", ObjectiveTag.REVISION_EXPLANATION),
            ("is this constructable", ObjectiveTag.CONSTRUCTABILITY),
            ("what does this look like aesthetically", ObjectiveTag.AESTHETICS),
        ],
    )
    def test_objective_tag(self, classifier, prompt, expected_tag):
        result = classifier.classify(prompt)
        assert result.objective_tag == expected_tag, (
            f"Prompt '{prompt}' tagged as {result.objective_tag}, expected {expected_tag}"
        )


class TestTwoAxisCombination:
    """Test combined RequestClass + ObjectiveTag classification."""

    def test_optimize_cost(self, classifier):
        result = classifier.classify("make this design cheaper to build")
        assert result.request_class == RequestClass.OPTIMIZE
        assert result.objective_tag == ObjectiveTag.COST_REDUCTION

    def test_estimate_spaces(self, classifier):
        result = classifier.classify("how many rooms are in this plan")
        assert result.request_class == RequestClass.ESTIMATE
        assert result.objective_tag == ObjectiveTag.SPACE_COUNT

    def test_summarize_for_contractor(self, classifier):
        result = classifier.classify("summarize for the contractor")
        assert result.request_class == RequestClass.SUMMARIZE
        assert result.objective_tag == ObjectiveTag.CONTRACTOR_COMMUNICATION

    def test_validate_compliance(self, classifier):
        result = classifier.classify("validate ADA compliance")
        assert result.request_class == RequestClass.VALIDATE
        assert result.objective_tag == ObjectiveTag.COMPLIANCE


class TestClassifyWithFamily:
    """Test fallback to TaskFamily when heuristic confidence is low."""

    def test_high_confidence_ignores_family(self, classifier):
        result = classifier.classify_with_family(
            "compare the drawings",
            TaskFamily.QNA,
        )
        assert result.request_class == RequestClass.COMPARE

    def test_low_confidence_uses_family(self, classifier):
        result = classifier.classify_with_family(
            "xyzzy gibberish",
            TaskFamily.TAKEOFF_ESTIMATE,
        )
        assert result.request_class == RequestClass.ESTIMATE
        assert result.source == "family_fallback"

    def test_medium_confidence_preserved(self, classifier):
        # "cost" matches COST_REDUCTION tag, infers OPTIMIZE at 0.75
        result = classifier.classify_with_family(
            "cost",
            TaskFamily.QNA,
        )
        assert result.request_class == RequestClass.OPTIMIZE
        assert result.confidence == 0.75


class TestTagFallbackInference:
    """When no RequestClass pattern matches, infer from ObjectiveTag."""

    def test_missing_items_infers_validate(self, classifier):
        result = classifier.classify("incomplete drawing")
        assert result.request_class == RequestClass.VALIDATE

    def test_layout_improvement_infers_recommend(self, classifier):
        result = classifier.classify("layout density")
        assert result.request_class == RequestClass.RECOMMEND

    def test_space_count_infers_estimate(self, classifier):
        result = classifier.classify("rooms in the floor plan")
        assert result.request_class == RequestClass.ESTIMATE

    def test_contractor_comm_infers_summarize(self, classifier):
        result = classifier.classify("for the contractor")
        assert result.request_class == RequestClass.SUMMARIZE


class TestClassificationMetadata:
    """Test metadata fields on ObjectiveClassification."""

    def test_confidence_range(self, classifier):
        result = classifier.classify("move the wall")
        assert 0.0 <= result.confidence <= 1.0

    def test_matched_patterns_populated(self, classifier):
        result = classifier.classify("compare these drawings")
        assert len(result.matched_patterns) > 0

    def test_classification_time_positive(self, classifier):
        result = classifier.classify("what is this")
        assert result.classification_time_ms >= 0.0

    def test_source_is_heuristic(self, classifier):
        result = classifier.classify("count all doors")
        assert result.source == "heuristic"


def _make_context(
    *,
    layers: list[str] | None = None,
    blocks: list[str] | None = None,
    texts: list[tuple[str, str]] | None = None,
) -> DrawingContext:
    """Build a minimal DrawingContext for family detection tests."""
    layer_rules = [LayerRule(name=n) for n in (layers or ["0"])]
    entities: list[EntityRef] = []
    for i, (text, layer) in enumerate(texts or [], start=1):
        entities.append(EntityRef(
            handle=hex(i),
            entity_type=EntityType.TEXT,
            layer=layer,
            text_content=text,
            insert_point=Point2D(x=0, y=0),
        ))
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=layer_rules,
        blocks=blocks or [],
    )


class TestFamilyDetectionWiring:
    """Test that classify() populates document_family when context is provided."""

    def test_classify_without_context_is_unknown(self, classifier):
        result = classifier.classify("count all columns")
        assert result.document_family == DocumentFamilyHint.UNKNOWN

    def test_classify_with_structural_context(self, classifier):
        ctx = _make_context(
            layers=["STRUCTURAL", "COLUMN_GRID", "BEAM", "NOTES"],
            texts=[("Column C-4", "NOTES"), ("Foundation detail", "NOTES")],
        )
        result = classifier.classify("count all columns", context=ctx)
        assert result.document_family == DocumentFamilyHint.STRUCTURAL

    def test_classify_with_family_passes_context(self, classifier):
        ctx = _make_context(
            layers=["PLANTING", "IRRIGATION", "LANDSCAPE"],
            texts=[("Tree Oak 24in", "PLANTING"), ("Shrub Boxwood", "PLANTING")],
        )
        result = classifier.classify_with_family(
            "how many trees", TaskFamily.QNA, context=ctx,
        )
        assert result.document_family == DocumentFamilyHint.LANDSCAPE

    def test_empty_prompt_with_context_still_detects_family(self, classifier):
        ctx = _make_context(
            layers=["ELECTRICAL", "LIGHTING", "PANEL"],
            texts=[("Panel A", "PANEL"), ("Circuit 20A", "ELECTRICAL")],
        )
        result = classifier.classify("", context=ctx)
        assert result.document_family == DocumentFamilyHint.ELECTRICAL
        assert result.request_class == RequestClass.UNDERSTAND

    def test_backward_compatible_no_context(self, classifier):
        """Existing calls without context still work unchanged."""
        result = classifier.classify("move the wall")
        assert result.request_class == RequestClass.MODIFY
        assert result.document_family == DocumentFamilyHint.UNKNOWN
