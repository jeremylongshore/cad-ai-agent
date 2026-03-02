"""Tests for bundle export — dry-run and full export."""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.comparison.applier import RevisionApplier
from cad_dxf_agent.core.comparison.approval import build_initial_approvals
from cad_dxf_agent.core.comparison.bundle import dry_run, export_bundle
from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from cad_dxf_agent.core.comparison.revision_ops import comparison_result_to_ops
from cad_dxf_agent.models.comparison_schema import (
    ApplyResult,
    ApprovalConfig,
    ApprovalSet,
)
from tests.helpers.comparison_factory import make_moved_entity_pair


@pytest.fixture
def comparison_pair(tmp_path):
    """Create a moved-entity pair and run comparison."""
    master, revision = make_moved_entity_pair(tmp_path)
    engine = ComparisonEngine()
    result = engine.compare(master, revision)
    return master, revision, result


class TestDryRun:
    def test_creates_changelog_files(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        out = tmp_path / "dry_output"
        outputs = dry_run(master, revision, result, out)

        assert (out / "changelog.json").exists()
        assert (out / "changelog.txt").exists()
        assert outputs.changelog is not None

    def test_creates_overlay(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        out = tmp_path / "dry_output"
        outputs = dry_run(master, revision, result, out)

        assert outputs.diff_overlay_path is not None
        assert outputs.diff_overlay_path.exists()

    def test_does_not_modify_master(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        original_size = master.stat().st_size
        original_mtime = master.stat().st_mtime

        dry_run(master, revision, result, tmp_path / "dry_output")

        assert master.stat().st_size == original_size
        assert master.stat().st_mtime == original_mtime


class TestExportBundle:
    def _run_full_pipeline(self, master, revision, result, output_dir):
        """Helper: convert → approve → apply → export."""
        ops = comparison_result_to_ops(result)
        config = ApprovalConfig(auto_approve_threshold=0.0)
        aset = build_initial_approvals(ops, config)

        doc = ezdxf.readfile(str(master))
        applier = RevisionApplier(doc)
        apply_result = applier.apply(ops, aset)

        return export_bundle(master, revision, result, apply_result, ops, aset, doc, output_dir)

    def test_all_files_created(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        out = tmp_path / "bundle"
        bundle = self._run_full_pipeline(master, revision, result, out)

        assert Path(bundle.updated_master_path).exists()
        assert Path(bundle.changelog_json_path).exists()
        assert Path(bundle.changelog_text_path).exists()
        assert Path(bundle.apply_result_path).exists()
        assert (out / "run_metadata.json").exists()

    def test_naming_convention(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        out = tmp_path / "bundle"
        bundle = self._run_full_pipeline(master, revision, result, out)

        updated = Path(bundle.updated_master_path)
        assert updated.name.startswith("master.updated.")
        assert updated.suffix == ".dxf"
        assert bundle.run_id in updated.name

    def test_original_unchanged(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        original_bytes = master.read_bytes()
        out = tmp_path / "bundle"
        self._run_full_pipeline(master, revision, result, out)

        assert master.read_bytes() == original_bytes

    def test_metadata_complete(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        out = tmp_path / "bundle"
        bundle = self._run_full_pipeline(master, revision, result, out)

        meta = json.loads((out / "run_metadata.json").read_text())
        assert meta["run_id"] == bundle.run_id
        assert "created_at" in meta
        assert "ops_count" in meta
        assert "approved_count" in meta
        assert "success_count" in meta

    def test_metadata_has_hashes_and_versions(self, comparison_pair, tmp_path):
        master, revision, result = comparison_pair
        out = tmp_path / "bundle"
        self._run_full_pipeline(master, revision, result, out)

        meta = json.loads((out / "run_metadata.json").read_text())
        assert "master_hash" in meta
        assert "revision_hash" in meta
        assert len(meta["master_hash"]) == 64  # SHA-256 hex digest
        assert len(meta["revision_hash"]) == 64
        assert "ezdxf_version" in meta
        assert "pipeline_version" in meta

    def test_alignment_result_in_bundle(self, comparison_pair, tmp_path):
        """Bundle includes alignment_result.json when alignment is present."""
        from cad_dxf_agent.models.comparison_schema import (
            AlignmentMethod,
            AlignmentResult,
        )

        master, revision, result = comparison_pair
        result.alignment_result = AlignmentResult(
            method=AlignmentMethod.translation,
            confidence=0.95,
            translation=(5.0, 3.0),
        )

        out = tmp_path / "bundle"
        bundle = self._run_full_pipeline(master, revision, result, out)

        assert bundle.alignment_result_path is not None
        ar_path = Path(bundle.alignment_result_path)
        assert ar_path.exists()

        ar_data = json.loads(ar_path.read_text())
        assert ar_data["method"] == "translation"
        assert ar_data["confidence"] == 0.95

    def test_no_alignment_result_when_absent(self, comparison_pair, tmp_path):
        """No alignment_result.json when alignment was not used."""
        master, revision, result = comparison_pair
        out = tmp_path / "bundle"
        bundle = self._run_full_pipeline(master, revision, result, out)

        assert bundle.alignment_result_path is None
        assert not (out / "alignment_result.json").exists()

    def test_empty_apply_result(self, tmp_path):
        """Bundle with no ops produces valid output."""
        master_path = tmp_path / "master.dxf"
        revision_path = tmp_path / "revision.dxf"
        doc = ezdxf.new(dxfversion="R2018")
        doc.saveas(str(master_path))
        doc.saveas(str(revision_path))

        engine = ComparisonEngine()
        result = engine.compare(master_path, revision_path)

        apply_result = ApplyResult(run_id="empty000")
        aset = ApprovalSet()

        out = tmp_path / "bundle"
        bundle = export_bundle(master_path, revision_path, result, apply_result, [], aset, doc, out)

        assert Path(bundle.updated_master_path).exists()
        assert bundle.run_id == "empty000"
