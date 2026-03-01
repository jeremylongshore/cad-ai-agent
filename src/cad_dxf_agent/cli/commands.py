"""Command handlers for the cad-revision CLI — one function per subcommand."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

import ezdxf

from ..core.comparison.alignment import align_drawings
from ..core.comparison.applier import RevisionApplier
from ..core.comparison.approval import approve_all_pending, build_initial_approvals
from ..core.comparison.bundle import export_bundle
from ..core.comparison.changelog import generate_changelog
from ..core.comparison.engine import ComparisonEngine
from ..core.comparison.geometry import extract_snapshots
from ..core.comparison.revision_ops import comparison_result_to_ops
from ..core.profiles import load_profile
from ..models.comparison_schema import (
    AlignmentConfig,
    ComparisonConfig,
    ComparisonResult,
)
from . import formatters


def _parse_control_points(
    raw: list[str] | None,
) -> list[tuple[tuple[float, float], tuple[float, float]]] | None:
    """Parse --control-points strings like '0,0:5,3' into typed tuples."""
    if not raw:
        return None
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for token in raw:
        master_str, _, rev_str = token.partition(":")
        if not rev_str:
            raise ValueError(f"Invalid control point format (expected mx,my:rx,ry): {token!r}")
        mx, my = (float(v) for v in master_str.split(","))
        rx, ry = (float(v) for v in rev_str.split(","))
        pairs.append(((mx, my), (rx, ry)))
    return pairs


def _validate_inputs(master: str, revision: str) -> tuple[Path, Path]:
    """Validate that both input files exist, raising FileNotFoundError if not."""
    mp = Path(master)
    rp = Path(revision)
    if not mp.exists():
        raise FileNotFoundError(f"Master DXF not found: {mp}")
    if not rp.exists():
        raise FileNotFoundError(f"Revision DXF not found: {rp}")
    return mp, rp


def _compare_with_profile(
    master_path: Path,
    revision_path: Path,
    args: Namespace,
    **config_kwargs: Any,
) -> ComparisonResult:
    """Run comparison with profile loaded from CLI args."""
    name = getattr(args, "profile", None)
    profile = load_profile(name) if name else None
    config = ComparisonConfig(profile=profile, **config_kwargs)
    engine = ComparisonEngine()
    return engine.compare(master_path, revision_path, config)


def cmd_diff(args: Namespace) -> int:
    """Compare two DXF files and show changes.

    Exit codes: 0 = no changes, 1 = changes found.
    """
    master_path, revision_path = _validate_inputs(args.master, args.revision)

    control_points = _parse_control_points(getattr(args, "control_points", None))
    alignment = AlignmentConfig(enabled=bool(control_points), control_points=control_points)
    result = _compare_with_profile(
        master_path, revision_path, args,
        tolerance=args.tolerance, alignment=alignment,
    )

    if getattr(args, "json", False):
        print(formatters.format_summary_json(result))
    else:
        print(formatters.format_summary(result))

    if getattr(args, "output_dir", None):
        ComparisonEngine().generate_outputs(master_path, revision_path, result, args.output_dir)
        print(f"\nOutputs written to: {args.output_dir}")

    return 0 if result.total_changes == 0 else 1


def cmd_align(args: Namespace) -> int:
    """Align two drawings and show transform details.

    Exit codes: 0 = aligned, 1 = alignment failed.
    """
    master_path, revision_path = _validate_inputs(args.master, args.revision)

    control_points = _parse_control_points(getattr(args, "control_points", None))
    config = AlignmentConfig(
        enabled=True,
        confidence_threshold=args.confidence,
        max_residual=args.max_residual,
        control_points=control_points,
    )

    master_snaps = extract_snapshots(master_path)
    revision_snaps = extract_snapshots(revision_path)
    alignment = align_drawings(master_snaps, revision_snaps, config)

    if getattr(args, "json", False):
        print(formatters.format_alignment_json(alignment))
    else:
        print(formatters.format_alignment(alignment))
        if alignment.guidance:
            print(f"\nGuidance: {alignment.guidance}")

    return 0 if alignment.confidence > 0 else 1


def cmd_dry_run(args: Namespace) -> int:
    """Show proposed ops without applying.

    Exit codes: 0 = no changes, 1 = changes found.
    """
    master_path, revision_path = _validate_inputs(args.master, args.revision)

    result = _compare_with_profile(master_path, revision_path, args)
    ops = comparison_result_to_ops(result)
    approval_set = build_initial_approvals(ops)

    if getattr(args, "json", False):
        print(formatters.format_dry_run_json(result, ops, approval_set))
    else:
        print(formatters.format_dry_run(result, ops, approval_set))

    if getattr(args, "output_dir", None):
        ComparisonEngine().generate_outputs(master_path, revision_path, result, args.output_dir)
        print(f"\nOutputs written to: {args.output_dir}")

    return 0 if result.total_changes == 0 else 1


def cmd_apply(args: Namespace) -> int:
    """Apply revision changes to master, saving to --output path.

    Exit codes: 0 = no changes, 1 = changes applied.
    """
    master_path, revision_path = _validate_inputs(args.master, args.revision)
    output_path = Path(args.output)

    result = _compare_with_profile(master_path, revision_path, args)
    ops = comparison_result_to_ops(result)

    if not ops:
        print("No changes to apply.")
        return 0

    approval_set = build_initial_approvals(ops)
    if args.approve_all:
        approve_all_pending(approval_set)

    doc = ezdxf.readfile(str(master_path))
    applier = RevisionApplier(doc)
    apply_result = applier.apply(ops, approval_set)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(output_path))

    print(f"Applied {apply_result.success_count} ops, {apply_result.failure_count} failures.")
    print(f"Output: {output_path}")

    return 1 if apply_result.success_count > 0 else 0


def cmd_bundle(args: Namespace) -> int:
    """Full pipeline: compare, apply, export bundle.

    Exit codes: 0 = no changes, 1 = bundle created.
    """
    master_path, revision_path = _validate_inputs(args.master, args.revision)

    result = _compare_with_profile(master_path, revision_path, args)
    ops = comparison_result_to_ops(result)

    if not ops:
        print("No changes to bundle.")
        return 0

    approval_set = build_initial_approvals(ops)
    if args.approve_all:
        approve_all_pending(approval_set)

    doc = ezdxf.readfile(str(master_path))
    applier = RevisionApplier(doc)
    apply_result = applier.apply(ops, approval_set)

    bundle = export_bundle(
        master_path=master_path,
        revision_path=revision_path,
        comparison_result=result,
        apply_result=apply_result,
        ops=ops,
        approval_set=approval_set,
        updated_doc=doc,
        output_dir=args.output_dir,
    )

    print(f"Bundle created: {bundle.bundle_dir}")
    print(f"  Run ID: {bundle.run_id}")
    print(f"  Updated master: {bundle.updated_master_path}")
    print(f"  Applied: {apply_result.success_count}, Failed: {apply_result.failure_count}")

    return 1


def cmd_explain(args: Namespace) -> int:
    """Generate and print a human-readable changelog.

    Exit codes: 0 = no changes, 1 = changes found.
    """
    master_path, revision_path = _validate_inputs(args.master, args.revision)

    result = _compare_with_profile(master_path, revision_path, args)
    changelog = generate_changelog(result)

    if getattr(args, "json", False):
        print(changelog.to_json())
    else:
        print(changelog.to_text())

    return 0 if result.total_changes == 0 else 1
