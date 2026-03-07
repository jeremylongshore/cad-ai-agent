"""Tests for comparison schema models: MatchSummary, ComparePackage, DiffSummaryData,
and enriched ChangeLogEntry fields.
"""

from __future__ import annotations

from cad_dxf_agent.models.comparison_schema import (
    ComparePackage,
    DiffSummaryData,
    MatchSummary,
)


class TestMatchSummary:
    def test_defaults(self):
        ms = MatchSummary()
        assert ms.total_pairs == 0
        assert ms.avg_confidence == 0.0
        assert ms.ambiguous_count == 0
        assert ms.method_distribution == {}

    def test_populated(self):
        ms = MatchSummary(
            total_pairs=10,
            avg_confidence=0.85,
            ambiguous_count=2,
            method_distribution={"fingerprint": 7, "spatial": 3},
        )
        assert ms.total_pairs == 10
        assert ms.avg_confidence == 0.85
        assert ms.ambiguous_count == 2
        assert ms.method_distribution["fingerprint"] == 7
        assert ms.method_distribution["spatial"] == 3

    def test_serialization_roundtrip(self):
        ms = MatchSummary(
            total_pairs=5,
            avg_confidence=0.9,
            ambiguous_count=1,
            method_distribution={"spatial": 5},
        )
        data = ms.model_dump()
        ms2 = MatchSummary(**data)
        assert ms2 == ms


class TestDiffSummaryData:
    def test_defaults(self):
        ds = DiffSummaryData()
        assert ds.headline == "No changes detected"
        assert ds.by_layer == {}
        assert ds.warnings == []

    def test_populated(self):
        ds = DiffSummaryData(
            headline="3 changes: 1 added, 2 moved",
            by_layer={"STRUCTURAL": {"added": 1, "moved": 2}},
            warnings=["1 entity moved >10 units"],
        )
        assert "3 changes" in ds.headline
        assert ds.by_layer["STRUCTURAL"]["added"] == 1
        assert len(ds.warnings) == 1


class TestComparePackage:
    def test_construction(self):
        cp = ComparePackage(
            master_path="/tmp/master.dxf",
            revision_path="/tmp/revision.dxf",
            overlay_path="/tmp/out/diff_overlay.dxf",
            changelog_json_path="/tmp/out/changelog.json",
            changelog_text_path="/tmp/out/changelog.txt",
            metadata_path="/tmp/out/compare_metadata.json",
            created_at="2026-03-06T00:00:00+00:00",
            total_changes=5,
        )
        assert cp.total_changes == 5
        assert cp.master_path == "/tmp/master.dxf"
        assert cp.metadata_path is not None

    def test_defaults(self):
        cp = ComparePackage(
            master_path="m.dxf",
            revision_path="r.dxf",
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert cp.total_changes == 0
        assert cp.overlay_path is None
        assert cp.changelog_json_path is None


class TestChangeLogEntryEnrichment:
    def test_handle_and_confidence_fields(self):
        from cad_dxf_agent.core.comparison.changelog import ChangeLogEntry

        entry = ChangeLogEntry(
            category="moved",
            entity_type="LINE",
            layer="STRUCTURAL",
            description="LINE moved",
            master_handle="A1",
            revision_handle="B2",
            confidence=0.85,
        )
        assert entry.master_handle == "A1"
        assert entry.revision_handle == "B2"
        assert entry.confidence == 0.85

    def test_handle_defaults_none(self):
        from cad_dxf_agent.core.comparison.changelog import ChangeLogEntry

        entry = ChangeLogEntry(
            category="added",
            entity_type="LINE",
            layer="NOTES",
            description="LINE added",
        )
        assert entry.master_handle is None
        assert entry.revision_handle is None
        assert entry.confidence is None
