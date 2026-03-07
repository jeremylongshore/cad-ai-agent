"""Bundle export — dry-run outputs and full revision-apply bundles."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import ezdxf

from ...models.comparison_schema import (
    AlignmentResult,
    ApplyResult,
    ApprovalSet,
    ComparePackage,
    ComparisonResult,
    RevisionOp,
    RunBundle,
)
from .engine import ComparisonEngine, ComparisonOutputs

logger = logging.getLogger(__name__)

# Shared engine instance — stateless, safe to reuse.
_engine = ComparisonEngine()


def _file_hash(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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
    alignment_result: AlignmentResult | None = None,
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

    try:
        pipeline_version = importlib.metadata.version("cad-dxf-agent")
    except importlib.metadata.PackageNotFoundError:
        pipeline_version = "unknown"

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
        "master_hash": _file_hash(master_path),
        "revision_hash": _file_hash(revision_path),
        "ezdxf_version": ezdxf.version,
        "pipeline_version": pipeline_version,
    }
    metadata_path = output_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    alignment_result_path_str: str | None = None
    ar = alignment_result or comparison_result.alignment_result
    if ar is not None:
        ar_path = output_dir / "alignment_result.json"
        ar_path.write_text(ar.model_dump_json(indent=2), encoding="utf-8")
        alignment_result_path_str = str(ar_path)

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
        alignment_result_path=alignment_result_path_str,
        bundle_dir=str(output_dir),
        metadata=metadata,
    )


def export_compare_package(
    master_path: str | Path,
    revision_path: str | Path,
    comparison_result: ComparisonResult,
    output_dir: str | Path,
) -> ComparePackage:
    """Export a compare-only package (no apply step required).

    Writes:
      - changelog.json / .txt
      - diff_overlay.dxf
      - compare_metadata.json

    Returns:
        ComparePackage manifest.
    """
    output_dir = Path(output_dir)
    outputs = _engine.generate_outputs(master_path, revision_path, comparison_result, output_dir)
    now = datetime.now(UTC).isoformat()

    try:
        pipeline_version = importlib.metadata.version("cad-dxf-agent")
    except importlib.metadata.PackageNotFoundError:
        pipeline_version = "unknown"

    metadata = {
        "created_at": now,
        "master_path": str(master_path),
        "revision_path": str(revision_path),
        "total_changes": comparison_result.total_changes,
        "summary": comparison_result.summary,
        "master_hash": _file_hash(master_path),
        "revision_hash": _file_hash(revision_path),
        "ezdxf_version": ezdxf.version,
        "pipeline_version": pipeline_version,
    }
    metadata_path = output_dir / "compare_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    changelog_json_path = output_dir / "changelog.json"
    changelog_text_path = output_dir / "changelog.txt"

    return ComparePackage(
        master_path=str(master_path),
        revision_path=str(revision_path),
        overlay_path=str(outputs.diff_overlay_path) if outputs.diff_overlay_path else None,
        changelog_json_path=str(changelog_json_path),
        changelog_text_path=str(changelog_text_path),
        metadata_path=str(metadata_path),
        created_at=now,
        total_changes=comparison_result.total_changes,
    )
