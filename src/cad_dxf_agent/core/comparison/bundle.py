"""Bundle export — dry-run outputs and full revision-apply bundles."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import ezdxf

from ...models.comparison_schema import (
    ApplyResult,
    ApprovalSet,
    ComparisonResult,
    RevisionOp,
    RunBundle,
)
from .engine import ComparisonEngine, ComparisonOutputs

logger = logging.getLogger(__name__)

# Shared engine instance — stateless, safe to reuse.
_engine = ComparisonEngine()


def dry_run(
    master_path: str | Path,
    revision_path: str | Path,
    comparison_result: ComparisonResult,
    output_dir: str | Path,
) -> ComparisonOutputs:
    """Generate overlay + changelog without modifying the master.

    Delegates to ComparisonEngine.generate_outputs() to avoid duplication.
    """
    return _engine.generate_outputs(master_path, revision_path, comparison_result, output_dir)


def export_bundle(
    master_path: str | Path,
    revision_path: str | Path,
    comparison_result: ComparisonResult,
    apply_result: ApplyResult,
    ops: list[RevisionOp],
    approval_set: ApprovalSet,
    updated_doc: ezdxf.document.Drawing,
    output_dir: str | Path,
) -> RunBundle:
    """Export a complete revision-apply bundle.

    Creates:
      - master.updated.<run_id>.dxf  (modified master)
      - diff_overlay.dxf             (visual diff)
      - changelog.json / .txt        (change descriptions)
      - apply_result.json            (apply outcome)
      - run_metadata.json            (full run context)

    Never overwrites the original master file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = apply_result.run_id
    now = datetime.now(UTC).isoformat()

    # Save updated master
    updated_name = f"master.updated.{run_id}.dxf"
    updated_path = output_dir / updated_name
    updated_doc.saveas(str(updated_path))

    # Delegate overlay + changelog to ComparisonEngine
    outputs = _engine.generate_outputs(master_path, revision_path, comparison_result, output_dir)
    overlay_path_str = str(outputs.diff_overlay_path) if outputs.diff_overlay_path else None

    # Write apply result
    apply_result_path = output_dir / "apply_result.json"
    apply_result_path.write_text(apply_result.model_dump_json(indent=2), encoding="utf-8")

    # Write metadata
    metadata = {
        "run_id": run_id,
        "created_at": now,
        "master_path": str(master_path),
        "revision_path": str(revision_path),
        "ops_count": len(ops),
        "approved_count": len(approval_set.approved_op_ids),
        "rejected_count": len(approval_set.rejected_op_ids),
        "success_count": apply_result.success_count,
        "failure_count": apply_result.failure_count,
    }
    metadata_path = output_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    changelog_json_path = output_dir / "changelog.json"
    changelog_text_path = output_dir / "changelog.txt"

    return RunBundle(
        run_id=run_id,
        created_at=now,
        master_path=str(master_path),
        revision_path=str(revision_path),
        updated_master_path=str(updated_path),
        overlay_path=overlay_path_str,
        changelog_json_path=str(changelog_json_path),
        changelog_text_path=str(changelog_text_path),
        apply_result_path=str(apply_result_path),
        bundle_dir=str(output_dir),
        metadata=metadata,
    )
