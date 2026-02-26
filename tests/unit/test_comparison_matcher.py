"""Tests for comparison/matcher.py — entity matching."""

from __future__ import annotations

from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import (
    ComparisonConfig,
    GeometrySnapshot,
)
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_complex_pair,
    make_identical_pair,
    make_moved_entity_pair,
)


class TestFingerprintMatching:
    """Exact fingerprint match tests."""

    def test_identical_files_all_matched(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        result = match_entities(m_snaps, r_snaps)
        assert len(result.pairs) == len(m_snaps)
        assert len(result.master_only) == 0
        assert len(result.revision_only) == 0

    def test_empty_lists(self):
        result = match_entities([], [])
        assert len(result.pairs) == 0
        assert len(result.master_only) == 0
        assert len(result.revision_only) == 0

    def test_master_only(self):
        snap = GeometrySnapshot(
            handle="A1",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        result = match_entities([snap], [])
        assert len(result.pairs) == 0
        assert len(result.master_only) == 1
        assert len(result.revision_only) == 0

    def test_revision_only(self):
        snap = GeometrySnapshot(
            handle="B1",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        result = match_entities([], [snap])
        assert len(result.pairs) == 0
        assert len(result.master_only) == 0
        assert len(result.revision_only) == 1


class TestNearestNeighborMatching:
    """Greedy nearest-neighbor match tests."""

    def test_moved_entity_matched(self, tmp_path):
        """A moved entity should be matched via nearest-neighbor."""
        master, revision = make_moved_entity_pair(tmp_path, dx=0.1, dy=0.1)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        result = match_entities(m_snaps, r_snaps)
        # The slightly moved line should match via NN (within tolerance)
        assert len(result.pairs) >= 1

    def test_far_moved_entity_unmatched(self, tmp_path):
        """Entity moved beyond tolerance should NOT match."""
        master, revision = make_moved_entity_pair(tmp_path, dx=100, dy=100)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        config = ComparisonConfig(tolerance=0.25)
        result = match_entities(m_snaps, r_snaps, config)
        # The line should be unmatched (too far)
        # At least some entities should be in master_only or revision_only
        total_unmatched = len(result.master_only) + len(result.revision_only)
        assert total_unmatched > 0

    def test_different_types_not_matched(self):
        """Entities of different types should never be paired."""
        m_snap = GeometrySnapshot(
            handle="A",
            entity_type=EntityType.LINE,
            layer="S",
            points=[Point2D(x=5, y=5), Point2D(x=15, y=5)],
        )
        r_snap = GeometrySnapshot(
            handle="B",
            entity_type=EntityType.TEXT,
            layer="S",
            points=[Point2D(x=5, y=5)],
            text_content="Hello",
        )
        result = match_entities([m_snap], [r_snap])
        assert len(result.pairs) == 0
        assert len(result.master_only) == 1
        assert len(result.revision_only) == 1

    def test_different_layers_not_matched(self):
        """Same geometry on different layers should not match."""
        m_snap = GeometrySnapshot(
            handle="A",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        r_snap = GeometrySnapshot(
            handle="B",
            entity_type=EntityType.LINE,
            layer="NOTES",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        result = match_entities([m_snap], [r_snap])
        # Fingerprint includes layer, so these won't match
        assert len(result.pairs) == 0


class TestAddedRemovedPair:
    def test_detects_added_and_removed(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        result = match_entities(m_snaps, r_snaps)
        # One shared entity should match, rest should be orphans
        assert len(result.pairs) >= 1
        assert len(result.master_only) >= 1  # "Old Note" removed
        assert len(result.revision_only) >= 1  # "New Note" added


class TestComplexPair:
    def test_complex_matching(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        result = match_entities(m_snaps, r_snaps)
        # Should have some pairs and some orphans
        assert len(result.pairs) >= 1
        total = len(result.pairs) + len(result.master_only) + len(result.revision_only)
        assert total > 0
