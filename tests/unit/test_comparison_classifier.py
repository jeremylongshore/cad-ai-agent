"""Tests for comparison/classifier.py — change classification."""

from __future__ import annotations

from cad_dxf_agent.core.comparison.classifier import classify_changes
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonConfig,
    GeometrySnapshot,
    MatchResult,
)
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_circle_pair,
    make_complex_pair,
    make_empty_vs_populated,
    make_identical_pair,
    make_modified_text_pair,
    make_moved_entity_pair,
)


class TestUnchangedClassification:
    def test_identical_files_all_unchanged(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        mr = match_entities(m_snaps, r_snaps)
        result = classify_changes(mr)
        assert result.summary["unchanged"] == len(m_snaps)
        assert result.summary["added"] == 0
        assert result.summary["removed"] == 0

    def test_empty_match_result(self):
        mr = MatchResult()
        result = classify_changes(mr)
        assert result.total_changes == 0


class TestMovedClassification:
    def test_moved_entity(self, tmp_path):
        master, revision = make_moved_entity_pair(tmp_path, dx=5.0, dy=5.0)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        # Use wider tolerance so the moved line matches via NN
        config = ComparisonConfig(tolerance=20.0, move_threshold=0.25)
        mr = match_entities(m_snaps, r_snaps, config)
        result = classify_changes(mr, config)
        moved = [c for c in result.changes if c.category == ChangeCategory.MOVED]
        assert len(moved) >= 1
        for m in moved:
            assert m.displacement is not None
            assert abs(m.displacement.x) > 0 or abs(m.displacement.y) > 0

    def test_small_move_is_unchanged(self):
        """Move smaller than threshold should be UNCHANGED."""
        m_snap = GeometrySnapshot(
            handle="A",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        r_snap = GeometrySnapshot(
            handle="B",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=0.01, y=0.01), Point2D(x=10.01, y=0.01)],
        )
        mr = MatchResult(pairs=[(m_snap, r_snap)])
        config = ComparisonConfig(tolerance=0.25, move_threshold=0.25)
        result = classify_changes(mr, config)
        assert result.changes[0].category == ChangeCategory.UNCHANGED


class TestAddedRemovedClassification:
    def test_added_and_removed(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        mr = match_entities(m_snaps, r_snaps)
        result = classify_changes(mr)
        assert result.summary["removed"] >= 1
        assert result.summary["added"] >= 1

    def test_empty_master_all_added(self, tmp_path):
        master, revision = make_empty_vs_populated(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        mr = match_entities(m_snaps, r_snaps)
        result = classify_changes(mr)
        assert result.summary["added"] >= 1
        assert result.summary["removed"] == 0

    def test_removed_entity_has_master_snapshot(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        mr = match_entities(m_snaps, r_snaps)
        result = classify_changes(mr)
        removed = [c for c in result.changes if c.category == ChangeCategory.REMOVED]
        for r in removed:
            assert r.master_snapshot is not None
            assert r.revision_snapshot is None

    def test_added_entity_has_revision_snapshot(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        mr = match_entities(m_snaps, r_snaps)
        result = classify_changes(mr)
        added = [c for c in result.changes if c.category == ChangeCategory.ADDED]
        for a in added:
            assert a.revision_snapshot is not None
            assert a.master_snapshot is None


class TestModifiedClassification:
    def test_modified_text(self, tmp_path):
        master, revision = make_modified_text_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        # Same position, different text — NN should match them
        config = ComparisonConfig(tolerance=1.0)
        mr = match_entities(m_snaps, r_snaps, config)
        result = classify_changes(mr, config)
        modified = [c for c in result.changes if c.category == ChangeCategory.MODIFIED]
        assert len(modified) >= 1
        for m in modified:
            assert m.modifications is not None
            assert "text_content" in m.modifications

    def test_modified_circle_radius(self, tmp_path):
        master, revision = make_circle_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        config = ComparisonConfig(tolerance=1.0)
        mr = match_entities(m_snaps, r_snaps, config)
        result = classify_changes(mr, config)
        modified = [c for c in result.changes if c.category == ChangeCategory.MODIFIED]
        assert len(modified) >= 1
        for m in modified:
            assert m.modifications is not None
            assert "radius" in m.modifications


class TestComplexClassification:
    def test_all_categories_present(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        config = ComparisonConfig(tolerance=10.0, move_threshold=0.25)
        mr = match_entities(m_snaps, r_snaps, config)
        result = classify_changes(mr, config)
        categories = {c.category for c in result.changes}
        # Should have at least added + removed
        assert ChangeCategory.ADDED in categories
        assert ChangeCategory.REMOVED in categories

    def test_summary_counts_match_changes(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        config = ComparisonConfig(tolerance=10.0, move_threshold=0.25)
        mr = match_entities(m_snaps, r_snaps, config)
        result = classify_changes(mr, config)
        # Verify counts
        for cat in ChangeCategory:
            expected = sum(1 for c in result.changes if c.category == cat)
            assert result.summary[cat.value] == expected
