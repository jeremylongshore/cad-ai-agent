"""Integration tests for the comparison engine — full pipeline through session.

Tests the complete flow: load DXF → compare with revision → verify results → verify outputs.
Uses real ezdxf operations, no mocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_circle_pair,
    make_complex_pair,
    make_identical_pair,
    make_modified_text_pair,
    make_moved_entity_pair,
)


@pytest.mark.integration
class TestComparisonPipeline:
    """Full pipeline: extract → match → classify → generate outputs."""

    def test_identical_files_zero_changes(self, tmp_path: Path):
        master, revision = make_identical_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        assert result.total_changes == 0
        assert result.summary.get("unchanged", 0) > 0

    def test_moved_entity_detected(self, tmp_path: Path):
        master, revision = make_moved_entity_pair(tmp_path, dx=10.0, dy=5.0)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        assert result.total_changes > 0
        # Movement may classify as moved or as removed+added depending on
        # whether fingerprint matching succeeds (handle differences between files)
        has_movement = result.summary.get("moved", 0) > 0 or (
            result.summary.get("removed", 0) > 0 and result.summary.get("added", 0) > 0
        )
        assert has_movement

    def test_added_removed_detected(self, tmp_path: Path):
        master, revision = make_added_removed_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        assert result.total_changes > 0
        assert result.summary.get("added", 0) > 0 or result.summary.get("removed", 0) > 0

    def test_modified_text_detected(self, tmp_path: Path):
        master, revision = make_modified_text_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        assert result.total_changes > 0
        # Text change may classify as modified or removed+added
        has_text_change = result.summary.get("modified", 0) > 0 or (
            result.summary.get("removed", 0) > 0 and result.summary.get("added", 0) > 0
        )
        assert has_text_change

    def test_circle_radius_change_detected(self, tmp_path: Path):
        master, revision = make_circle_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        assert result.total_changes > 0

    def test_complex_pair_all_change_types(self, tmp_path: Path):
        master, revision = make_complex_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        assert result.total_changes > 0
        # Complex pair should have multiple change categories
        non_zero = sum(1 for k, v in result.summary.items() if k != "unchanged" and v > 0)
        assert non_zero >= 2, f"Expected multiple change types, got: {result.summary}"


@pytest.mark.integration
class TestComparisonOutputs:
    """Verify diff overlay DXF and changelog generation."""

    def test_generates_diff_overlay_dxf(self, tmp_path: Path):
        master, revision = make_added_removed_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        output_dir = tmp_path / "output"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        assert outputs.diff_overlay_path is not None
        assert outputs.diff_overlay_path.exists()
        assert outputs.diff_overlay_path.suffix == ".dxf"
        assert outputs.diff_overlay_path.stat().st_size > 0

    def test_diff_overlay_has_colored_layers(self, tmp_path: Path):
        import ezdxf

        master, revision = make_added_removed_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        output_dir = tmp_path / "output"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        doc = ezdxf.readfile(str(outputs.diff_overlay_path))
        layer_names = {layer.dxf.name for layer in doc.layers}
        # At least some overlay layers should exist
        overlay_layers = {"AI_ADDED", "AI_REMOVED", "AI_MODIFIED", "AI_MOVED"}
        assert overlay_layers.intersection(layer_names), (
            f"No overlay layers found. Layers: {layer_names}"
        )

    def test_diff_overlay_does_not_modify_master(self, tmp_path: Path):
        master, revision = make_added_removed_pair(tmp_path)
        master_bytes_before = master.read_bytes()

        engine = ComparisonEngine()
        result = engine.compare(master, revision)
        engine.generate_outputs(master, revision, result, tmp_path / "output")

        assert master.read_bytes() == master_bytes_before

    def test_generates_changelog(self, tmp_path: Path):
        master, revision = make_complex_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        output_dir = tmp_path / "output"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        changelog = outputs.changelog
        assert changelog is not None

        # JSON output is valid
        import json

        parsed = json.loads(changelog.to_json())
        assert "summary" in parsed
        assert "entries" in parsed
        assert len(parsed["entries"]) > 0

    def test_changelog_text_is_readable(self, tmp_path: Path):
        master, revision = make_complex_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        output_dir = tmp_path / "output"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        text = outputs.changelog.to_text()
        assert len(text) > 0
        assert "CHANGE LOG" in text

    def test_identical_files_minimal_outputs(self, tmp_path: Path):
        master, revision = make_identical_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        output_dir = tmp_path / "output"
        outputs = engine.generate_outputs(master, revision, result, output_dir)

        # Overlay still created (may have no extra entities)
        assert outputs.diff_overlay_path is not None
        # Changelog exists but has no non-unchanged entries
        import json

        parsed = json.loads(outputs.changelog.to_json())
        assert len(parsed["entries"]) == 0

    def test_output_dir_created_automatically(self, tmp_path: Path):
        master, revision = make_added_removed_pair(tmp_path)
        engine = ComparisonEngine()
        result = engine.compare(master, revision)

        output_dir = tmp_path / "deeply" / "nested" / "output"
        assert not output_dir.exists()
        engine.generate_outputs(master, revision, result, output_dir)
        assert output_dir.exists()


@pytest.mark.integration
class TestComparisonWebSessionFlow:
    """Test comparison through the web session layer (no HTTP, direct session)."""

    def test_session_stores_comparison_result(self, tmp_path: Path):
        from web.backend.session import SessionManager

        mgr = SessionManager()
        session = mgr.create(user_id="test-user")

        # Simulate upload
        import shutil

        master, revision = make_added_removed_pair(tmp_path)
        session_dir = Path("/tmp/cad-sessions") / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(master), str(session.original_path))

        # Run comparison
        engine = ComparisonEngine()
        result = engine.compare(session.original_path, revision)
        session.comparison_result = result

        assert session.comparison_result is not None
        assert session.comparison_result.total_changes > 0

        # Cleanup
        mgr.delete(session.session_id)

    def test_session_stores_changelog(self, tmp_path: Path):
        from web.backend.session import SessionManager

        mgr = SessionManager()
        session = mgr.create(user_id="test-user")

        master, revision = make_complex_pair(tmp_path)
        session_dir = Path("/tmp/cad-sessions") / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        import shutil

        shutil.copy2(str(master), str(session.original_path))

        engine = ComparisonEngine()
        result = engine.compare(session.original_path, revision)
        output_dir = session_dir / "comparison"
        outputs = engine.generate_outputs(session.original_path, revision, result, output_dir)

        session.comparison_result = result
        session.comparison_changelog = outputs.changelog
        session.diff_overlay_path = outputs.diff_overlay_path

        assert session.comparison_changelog is not None
        assert session.diff_overlay_path is not None
        assert session.diff_overlay_path.exists()

        # Cleanup
        mgr.delete(session.session_id)
