"""E2E smoke test: compare → align → diff → dry-run → apply → verify bundle.

Exercises the full revision pipeline end-to-end using the clean fixture.
Asserts that every expected output file is created and well-formed.
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.comparison.applier import RevisionApplier
from cad_dxf_agent.core.comparison.approval import (
    approve_all_pending,
    build_initial_approvals,
)
from cad_dxf_agent.core.comparison.bundle import dry_run, export_bundle
from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from cad_dxf_agent.core.comparison.revision_ops import comparison_result_to_ops

CLEAN_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "revision" / "clean"
)


@pytest.mark.smoke
class TestRevisionE2E:
    """Full pipeline smoke test on the clean fixture."""

    def test_compare_produces_changes(self):
        engine = ComparisonEngine()
        result = engine.compare(
            CLEAN_FIXTURE / "master.dxf",
            CLEAN_FIXTURE / "revision.dxf",
        )
        assert result.summary is not None
        total = sum(result.summary.values())
        assert total > 0, "Comparison found zero entities"
        non_unchanged = total - result.summary.get("unchanged", 0)
        assert non_unchanged > 0, "No changes detected"

    def test_dry_run_creates_overlay_and_changelog(self, tmp_path):
        engine = ComparisonEngine()
        result = engine.compare(
            CLEAN_FIXTURE / "master.dxf",
            CLEAN_FIXTURE / "revision.dxf",
        )
        outputs = dry_run(
            CLEAN_FIXTURE / "master.dxf",
            CLEAN_FIXTURE / "revision.dxf",
            result,
            tmp_path,
        )
        # Overlay DXF created
        assert outputs.diff_overlay_path is not None
        assert Path(outputs.diff_overlay_path).exists()

        # Changelog files created
        changelog_json = tmp_path / "changelog.json"
        changelog_txt = tmp_path / "changelog.txt"
        assert changelog_json.exists()
        assert changelog_txt.exists()

        # Changelog JSON is valid
        data = json.loads(changelog_json.read_text())
        assert "entries" in data
        assert "summary" in data

    def test_full_apply_and_export_bundle(self, tmp_path):
        # 1. Compare
        engine = ComparisonEngine()
        result = engine.compare(
            CLEAN_FIXTURE / "master.dxf",
            CLEAN_FIXTURE / "revision.dxf",
        )

        # 2. Convert to ops
        ops = comparison_result_to_ops(result)
        assert len(ops) > 0, "No revision ops generated"

        # 3. Approve all
        approval_set = build_initial_approvals(ops)
        approve_all_pending(approval_set)

        # 4. Apply to master copy
        master_doc = ezdxf.readfile(str(CLEAN_FIXTURE / "master.dxf"))
        applier = RevisionApplier(master_doc)
        apply_result = applier.apply(ops, approval_set)
        assert apply_result.success_count > 0, "No ops applied successfully"

        # 5. Export bundle
        bundle_dir = tmp_path / "bundle"
        bundle = export_bundle(
            master_path=CLEAN_FIXTURE / "master.dxf",
            revision_path=CLEAN_FIXTURE / "revision.dxf",
            comparison_result=result,
            apply_result=apply_result,
            ops=ops,
            approval_set=approval_set,
            updated_doc=master_doc,
            output_dir=bundle_dir,
        )

        # 6. Verify bundle completeness
        assert Path(bundle.updated_master_path).exists(), "Updated master missing"
        assert Path(bundle.overlay_path).exists(), "Overlay missing"
        assert Path(bundle.changelog_json_path).exists(), "Changelog JSON missing"
        assert Path(bundle.changelog_text_path).exists(), "Changelog text missing"
        assert Path(bundle.apply_result_path).exists(), "Apply result missing"

        # Metadata file
        metadata_path = bundle_dir / "run_metadata.json"
        assert metadata_path.exists(), "Run metadata missing"
        metadata = json.loads(metadata_path.read_text())
        assert metadata["ops_count"] == len(ops)
        assert metadata["success_count"] > 0

        # Updated master is valid DXF
        updated_doc = ezdxf.readfile(bundle.updated_master_path)
        assert len(list(updated_doc.modelspace())) > 0
