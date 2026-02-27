"""Determinism smoke tests — verify comparison pipeline produces stable output.

These tests assert that running the same inputs through the pipeline twice
produces identical results. They form the skeleton for cad-ee2 (canonical model)
and will be extended as stable IDs, canonical normalization, and confidence
scoring are added.

Audit context (cad-ee2.1):
- Current identity: GeometrySnapshot.handle stores DXF handle but matching
  uses fingerprint(type|layer|points|text|block_name) NOT handle.
- Current ordering: insertion order from ezdxf, not deterministic across
  independently-created DXF files with same geometry.
- Current disambiguation: none — identical entities on same layer get same
  fingerprint; first-come-first-served matching.
"""

from __future__ import annotations

from cad_dxf_agent.core.comparison.canonical import assign_stable_ids
from cad_dxf_agent.core.comparison.classifier import classify_changes
from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.comparison_schema import ComparisonConfig
from tests.helpers.comparison_factory import (
    make_complex_pair,
    make_identical_pair,
    make_moved_entity_pair,
)


class TestSnapshotDeterminism:
    """Same DXF file extracted twice must produce identical snapshots."""

    def test_same_file_same_snapshots(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps_a = extract_snapshots(master)
        snaps_b = extract_snapshots(master)
        assert len(snaps_a) == len(snaps_b)
        for a, b in zip(snaps_a, snaps_b, strict=True):
            assert a.entity_type == b.entity_type
            assert a.layer == b.layer
            assert a.points == b.points
            assert a.text_content == b.text_content
            assert a.block_name == b.block_name


class TestMatchDeterminism:
    """Same inputs to matcher must produce same pairs in same order."""

    def test_identical_match_twice(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        result_a = match_entities(m_snaps, r_snaps)
        result_b = match_entities(m_snaps, r_snaps)
        assert len(result_a.pairs) == len(result_b.pairs)
        assert len(result_a.master_only) == len(result_b.master_only)
        assert len(result_a.revision_only) == len(result_b.revision_only)

    def test_moved_match_twice(self, tmp_path):
        master, revision = make_moved_entity_pair(tmp_path, dx=0.1, dy=0.1)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        result_a = match_entities(m_snaps, r_snaps)
        result_b = match_entities(m_snaps, r_snaps)
        assert len(result_a.pairs) == len(result_b.pairs)


class TestClassifyDeterminism:
    """Same match result classified twice must produce identical output."""

    def test_classify_twice_identical(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        match_result = match_entities(m_snaps, r_snaps)
        config = ComparisonConfig()
        result_a = classify_changes(match_result, config)
        result_b = classify_changes(match_result, config)
        assert result_a.summary == result_b.summary
        assert len(result_a.changes) == len(result_b.changes)
        for a, b in zip(result_a.changes, result_b.changes, strict=True):
            assert a.category == b.category


class TestEngineDeterminism:
    """Full engine pipeline run twice must produce identical results."""

    def test_engine_compare_twice(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        engine = ComparisonEngine()
        result_a = engine.compare(master, revision)
        result_b = engine.compare(master, revision)
        assert result_a.summary == result_b.summary
        assert len(result_a.changes) == len(result_b.changes)
        for a, b in zip(result_a.changes, result_b.changes, strict=True):
            assert a.category == b.category

    def test_engine_outputs_twice(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)
        out_a = tmp_path / "out_a"
        out_b = tmp_path / "out_b"
        outputs_a = engine.generate_outputs(master, revision, result, out_a)
        outputs_b = engine.generate_outputs(master, revision, result, out_b)
        # Changelog entry count must be identical
        assert len(outputs_a.changelog.entries) == len(outputs_b.changelog.entries)
        for a, b in zip(outputs_a.changelog.entries, outputs_b.changelog.entries, strict=True):
            assert a.category == b.category
            assert a.entity_type == b.entity_type
            assert a.layer == b.layer


class TestCrossFileIdentity:
    """Skeleton tests for stable identity across independently-created DXF files.

    These currently document known limitations that E1 beads will fix:
    - Two DXF files with identical geometry get different DXF handles
    - No stable_id field exists yet on GeometrySnapshot
    - No canonical normalization applied
    """

    def test_handles_are_ezdxf_internal_not_guaranteed_stable(self, tmp_path):
        """DXF handles happen to match for ezdxf-created files but are NOT
        guaranteed stable across real-world DXF exports from different CAD tools.

        This test documents that handles are an implementation accident, not a
        reliable identity mechanism. After E1.B5, stable_id will provide
        geometry-based identity that works across any source.
        """
        master, revision = make_identical_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        assert len(m_snaps) > 0
        # Handles may or may not match — we don't rely on them for cross-file identity
        # The important thing is that matching works via fingerprint, not handle
        m_fps = {(s.entity_type, s.layer, tuple((p.x, p.y) for p in s.points)) for s in m_snaps}
        r_fps = {(s.entity_type, s.layer, tuple((p.x, p.y) for p in s.points)) for s in r_snaps}
        assert m_fps == r_fps  # geometry IS stable; handles are irrelevant

    def test_stable_id_field_exists_but_not_yet_assigned(self, tmp_path):
        """GeometrySnapshot has stable_id field but extract_snapshots doesn't assign it.

        assign_stable_ids() must be called separately to populate stable_id.
        """
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        assert len(snaps) > 0
        # Field exists but is None until assign_stable_ids is called
        assert hasattr(snaps[0], "stable_id")
        assert snaps[0].stable_id is None

    def test_stable_ids_assigned_after_canonicalization(self, tmp_path):
        """assign_stable_ids() populates stable_id on all snapshots."""
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        result = assign_stable_ids(snaps)
        assert all(s.stable_id is not None for s in result)
        # All IDs unique
        ids = [s.stable_id for s in result]
        assert len(set(ids)) == len(ids)

    def test_stable_ids_match_across_identical_files(self, tmp_path):
        """Same geometry in two independently-created DXFs → same stable IDs."""
        master, revision = make_identical_pair(tmp_path)
        m_snaps = assign_stable_ids(extract_snapshots(master))
        r_snaps = assign_stable_ids(extract_snapshots(revision))
        m_ids = sorted(s.stable_id for s in m_snaps)  # type: ignore[arg-type]
        r_ids = sorted(s.stable_id for s in r_snaps)  # type: ignore[arg-type]
        assert m_ids == r_ids


class TestCanonicalEngineDeterminism:
    """Engine with use_canonical=True produces stable, deterministic output."""

    def test_canonical_compare_twice_identical(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        config = ComparisonConfig(use_canonical=True)
        engine = ComparisonEngine()
        result_a = engine.compare(master, revision, config)
        result_b = engine.compare(master, revision, config)
        assert result_a.summary == result_b.summary
        assert len(result_a.changes) == len(result_b.changes)
        for a, b in zip(result_a.changes, result_b.changes, strict=True):
            assert a.category == b.category

    def test_canonical_changes_have_stable_ids(self, tmp_path):
        """When use_canonical=True, matched entities have stable IDs."""
        master, revision = make_identical_pair(tmp_path)
        config = ComparisonConfig(use_canonical=True)
        engine = ComparisonEngine()
        result = engine.compare(master, revision, config)
        for change in result.changes:
            if change.master_snapshot:
                assert change.master_snapshot.stable_id is not None
            if change.revision_snapshot:
                assert change.revision_snapshot.stable_id is not None

    def test_canonical_backward_compat(self, tmp_path):
        """Default config (use_canonical=False) works exactly as before."""
        master, revision = make_complex_pair(tmp_path)
        engine = ComparisonEngine()
        # Default: no canonical model
        result = engine.compare(master, revision)
        assert result.summary is not None
        # No stable IDs assigned
        for change in result.changes:
            if change.master_snapshot:
                assert change.master_snapshot.stable_id is None
