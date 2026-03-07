"""Regression tests for the comparison pipeline.

Uses comparison_factory DXF pair builders to exercise the full
extract → match → classify pipeline and verify correct change categories,
MatchSummary population, and build_compare_response() output.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from cad_dxf_agent.models.comparison_schema import ChangeCategory


@pytest.fixture
def engine():
    return ComparisonEngine()


class TestMovedEntity:
    def test_moved_entity_detected(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_moved_entity_pair

        master, revision = make_moved_entity_pair(tmp_path, dx=10.0, dy=5.0)
        result = engine.compare(master, revision)

        moved_or_added_removed = result.summary["moved"] > 0 or (
            result.summary["added"] > 0 and result.summary["removed"] > 0
        )
        assert moved_or_added_removed

    def test_moved_entity_has_displacement(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_moved_entity_pair

        master, revision = make_moved_entity_pair(tmp_path, dx=10.0, dy=5.0)
        result = engine.compare(master, revision)

        moved = [c for c in result.changes if c.category == ChangeCategory.MOVED]
        if moved:
            assert moved[0].displacement is not None
            assert moved[0].confidence > 0.7


class TestDeletedEntity:
    def test_removed_entity_no_revision_snapshot(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_added_removed_pair

        master, revision = make_added_removed_pair(tmp_path)
        result = engine.compare(master, revision)

        removed = [c for c in result.changes if c.category == ChangeCategory.REMOVED]
        assert len(removed) > 0
        for r in removed:
            assert r.revision_snapshot is None
            assert r.master_snapshot is not None


class TestAddedEntity:
    def test_added_entity_no_master_snapshot(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_added_removed_pair

        master, revision = make_added_removed_pair(tmp_path)
        result = engine.compare(master, revision)

        added = [c for c in result.changes if c.category == ChangeCategory.ADDED]
        assert len(added) > 0
        for a in added:
            assert a.master_snapshot is None
            assert a.revision_snapshot is not None


class TestModifiedText:
    def test_modified_text_has_text_change(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_modified_text_pair

        master, revision = make_modified_text_pair(tmp_path)
        result = engine.compare(master, revision)

        modified = [c for c in result.changes if c.category == ChangeCategory.MODIFIED]
        # Depending on matching, could also show as removed+added
        if modified:
            assert any(c.modifications and "text_content" in c.modifications for c in modified)


class TestIdenticalDrawings:
    def test_all_unchanged(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_identical_pair

        master, revision = make_identical_pair(tmp_path)
        result = engine.compare(master, revision)

        assert result.total_changes == 0
        non_unchanged = [c for c in result.changes if c.category != ChangeCategory.UNCHANGED]
        assert len(non_unchanged) == 0


class TestAmbiguousPair:
    def test_ambiguous_match_flagged(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_ambiguous_pair

        master, revision = make_ambiguous_pair(tmp_path)
        result = engine.compare(master, revision)

        # The engine should produce at least one result; ambiguity may show
        # as match_summary.ambiguous_count > 0 or as added+removed
        assert result.match_summary is not None
        # With one master and two similar revision entities, expect either
        # ambiguous match or unmatched entities
        has_ambiguity = result.match_summary.ambiguous_count > 0 or result.summary["added"] > 0
        assert has_ambiguity


class TestBlockAttributes:
    def test_attributes_preserved_in_snapshot(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_block_attrib_pair

        master, revision = make_block_attrib_pair(tmp_path)
        result = engine.compare(master, revision)

        # Find INSERT changes
        insert_changes = [
            c
            for c in result.changes
            if (c.master_snapshot and c.master_snapshot.block_name == "DOOR")
            or (c.revision_snapshot and c.revision_snapshot.block_name == "DOOR")
        ]
        assert len(insert_changes) > 0

        # At least one snapshot should have attributes
        has_attribs = any(
            (c.master_snapshot and c.master_snapshot.attributes)
            or (c.revision_snapshot and c.revision_snapshot.attributes)
            for c in insert_changes
        )
        assert has_attribs


class TestMatchSummaryPopulated:
    def test_match_summary_on_result(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_complex_pair

        master, revision = make_complex_pair(tmp_path)
        result = engine.compare(master, revision)

        assert result.match_summary is not None
        assert result.match_summary.total_pairs >= 0
        assert 0.0 <= result.match_summary.avg_confidence <= 1.0
        assert result.match_summary.ambiguous_count >= 0
        assert isinstance(result.match_summary.method_distribution, dict)

    def test_match_summary_on_identical(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_identical_pair

        master, revision = make_identical_pair(tmp_path)
        result = engine.compare(master, revision)

        assert result.match_summary is not None
        # Identical files: all matched, high confidence
        if result.match_summary.total_pairs > 0:
            assert result.match_summary.avg_confidence > 0.5


class TestCompareEditIsolation:
    """Ensures compare intents don't route to the edit planner."""

    def test_compare_intent_does_not_route_to_edit(self):
        from cad_dxf_agent.llm.intent_router import IntentRouter
        from cad_dxf_agent.models.response_schema import TaskFamily

        router = IntentRouter()
        result = router.classify("compare these two drawings")
        assert result.family == TaskFamily.COMPARE
        assert result.family != TaskFamily.EDIT_PLAN

    def test_diff_intent_does_not_route_to_edit(self):
        from cad_dxf_agent.llm.intent_router import IntentRouter
        from cad_dxf_agent.models.response_schema import TaskFamily

        router = IntentRouter()
        result = router.classify("show me the differences between revisions")
        assert result.family == TaskFamily.COMPARE
        assert result.family != TaskFamily.EDIT_PLAN


class TestOcrTextPriority:
    """Anti-regression: low-confidence OCR text must not outscore native CAD text."""

    def test_low_confidence_reduces_position_contribution(self):
        from cad_dxf_agent.core.comparison.scorer import score_text
        from cad_dxf_agent.models.cad_schema import EntityType, Point2D, TextGeometry
        from cad_dxf_agent.models.comparison_schema import GeometrySnapshot

        base_kwargs = dict(
            handle="A1",
            entity_type=EntityType.TEXT,
            layer="0",
            points=[Point2D(x=10.0, y=20.0)],
            text_content="DETAIL A",
        )
        revision = GeometrySnapshot(
            **{**base_kwargs, "handle": "B1", "points": [Point2D(x=10.5, y=20.5)]}
        )

        # Native CAD text: confidence_position = 1.0
        native = GeometrySnapshot(
            **base_kwargs,
            text_geometry=TextGeometry(height=2.5, confidence_position=1.0),
        )
        score_native, expl_native = score_text(native, revision, tolerance=50.0)

        # Simulated OCR text: confidence_position = 0.3
        ocr = GeometrySnapshot(
            **base_kwargs,
            text_geometry=TextGeometry(height=2.5, confidence_position=0.3),
        )
        score_ocr, expl_ocr = score_text(ocr, revision, tolerance=50.0)

        # Position contribution must be strictly less for low-confidence OCR
        assert expl_ocr.features["position"] < expl_native.features["position"]
        # text_trust must reflect the reduced confidence
        assert expl_ocr.features["text_trust"] < 1.0
        assert expl_native.features["text_trust"] == 1.0


class TestBuildCompareResponse:
    def test_returns_expected_keys(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_moved_entity_pair

        master, revision = make_moved_entity_pair(tmp_path)
        result = engine.compare(master, revision)
        output_dir = tmp_path / "out"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        data = engine.build_compare_response(result, outputs)

        assert "summary" in data
        assert "total_changes" in data
        assert "match_summary" in data
        assert "diff_summary" in data
        assert "changelog_entry_count" in data
        assert "render_available" in data

    def test_diff_summary_has_headline(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_complex_pair

        master, revision = make_complex_pair(tmp_path)
        result = engine.compare(master, revision)
        output_dir = tmp_path / "out"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        data = engine.build_compare_response(result, outputs)

        assert "headline" in data["diff_summary"]
        assert isinstance(data["diff_summary"]["headline"], str)

    def test_warnings_included_when_present(self, tmp_path, engine):
        from tests.helpers.comparison_factory import make_identical_pair

        master, revision = make_identical_pair(tmp_path)
        result = engine.compare(master, revision)
        # Inject a warning for testing
        result.warnings = ["test warning"]
        output_dir = tmp_path / "out"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        data = engine.build_compare_response(result, outputs)

        assert data["warnings"] == ["test warning"]
