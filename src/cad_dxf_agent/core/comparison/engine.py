"""Comparison engine — top-level orchestrator for DXF comparison."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ...models.comparison_schema import ComparisonConfig, ComparisonResult
from ...otel import get_tracer
from .alignment import align_drawings, apply_alignment
from .canonical import assign_stable_ids, sort_changes, sort_snapshots
from .changelog import ChangeLog, generate_changelog
from .classifier import classify_changes
from .diff_overlay import write_diff_overlay
from .geometry import extract_snapshots
from .matcher import match_entities

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


@dataclass
class ComparisonOutputs:
    """Paths and data produced by the comparison engine."""

    result: ComparisonResult
    changelog: ChangeLog
    diff_overlay_path: Path | None = None
    master_path: Path = field(default_factory=lambda: Path())
    revision_path: Path = field(default_factory=lambda: Path())


class ComparisonEngine:
    """Orchestrates the full comparison pipeline.

    Usage::

        engine = ComparisonEngine()
        result = engine.compare("master.dxf", "revision.dxf")
        outputs = engine.generate_outputs("master.dxf", result, output_dir)
    """

    def compare(
        self,
        master_path: str | Path,
        revision_path: str | Path,
        config: ComparisonConfig | None = None,
    ) -> ComparisonResult:
        """Run the full comparison pipeline: extract → match → classify.

        Args:
            master_path: Path to the master (original) DXF.
            revision_path: Path to the revision (modified) DXF.
            config: Optional comparison configuration.

        Returns:
            ComparisonResult with all classified changes.
        """
        with tracer.start_as_current_span("cad.compare.engine.compare") as span:
            span.set_attribute("cad.compare.master_path", Path(master_path).name)
            span.set_attribute("cad.compare.revision_path", Path(revision_path).name)

            config = config or ComparisonConfig()

            profile_warnings: list[str] = []

            logger.info("Extracting geometry from master: %s", Path(master_path).name)
            master_snaps = extract_snapshots(
                master_path, config, _profile_warnings=profile_warnings
            )

            logger.info("Extracting geometry from revision: %s", Path(revision_path).name)
            revision_snaps = extract_snapshots(
                revision_path, config, _profile_warnings=profile_warnings
            )

            # Canonical model: assign stable IDs and sort deterministically
            if config.use_canonical:
                span.set_attribute("cad.compare.canonical", True)
                logger.info("Applying canonical model (stable IDs + deterministic sort)")
                master_snaps = assign_stable_ids(master_snaps)
                revision_snaps = assign_stable_ids(revision_snaps)
                master_snaps = sort_snapshots(master_snaps)
                revision_snaps = sort_snapshots(revision_snaps)

            # Alignment: transform revision to master coordinate system
            alignment_result = None
            if config.alignment.enabled:
                span.set_attribute("cad.compare.alignment", True)
                logger.info("Running alignment ladder")
                alignment_result = align_drawings(master_snaps, revision_snaps, config.alignment)
                span.set_attribute("cad.align.method", alignment_result.method.value)
                span.set_attribute("cad.align.confidence", alignment_result.confidence)

                if alignment_result.confidence > 0:
                    revision_snaps = apply_alignment(revision_snaps, alignment_result)
                    logger.info(
                        "Alignment applied: method=%s confidence=%.4f",
                        alignment_result.method.value,
                        alignment_result.confidence,
                    )
                else:
                    logger.warning(
                        "Alignment failed: %s",
                        alignment_result.guidance or "no guidance",
                    )

            logger.info(
                "Matching entities: %d master, %d revision",
                len(master_snaps),
                len(revision_snaps),
            )
            match_result = match_entities(master_snaps, revision_snaps, config)

            # Log match statistics with confidence
            confidences = [p.confidence for p in match_result.pairs]
            ambiguous_count = sum(1 for p in match_result.pairs if p.ambiguous)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            logger.info(
                "Matched %d pairs (avg confidence=%.3f, %d ambiguous), "
                "%d master-only, %d revision-only",
                len(match_result.pairs),
                avg_conf,
                ambiguous_count,
                len(match_result.master_only),
                len(match_result.revision_only),
            )
            classified = classify_changes(match_result, config)

            # Build final result: sort if canonical, attach alignment
            final_changes = classified.changes
            if config.use_canonical:
                final_changes = sort_changes(final_changes)

            result = ComparisonResult(
                changes=final_changes,
                summary=classified.summary,
                config=classified.config,
                alignment_result=alignment_result,
                warnings=profile_warnings,
            )

            logger.info("Classification: %s", result.summary)

            span.set_attribute("cad.compare.total_changes", result.total_changes)

            return result

    def generate_outputs(
        self,
        master_path: str | Path,
        revision_path: str | Path,
        result: ComparisonResult,
        output_dir: str | Path,
    ) -> ComparisonOutputs:
        """Generate all output artifacts from a comparison result.

        Args:
            master_path: Path to the master DXF (base for overlay).
            revision_path: Path to the revision DXF.
            result: Classified comparison result.
            output_dir: Directory for output files.

        Returns:
            ComparisonOutputs with paths to generated files.
        """
        with tracer.start_as_current_span("cad.compare.engine.generate_outputs") as span:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate change log
            changelog = generate_changelog(result)

            # Write change log files
            changelog_json_path = output_dir / "changelog.json"
            changelog_json_path.write_text(changelog.to_json(), encoding="utf-8")

            changelog_text_path = output_dir / "changelog.txt"
            changelog_text_path.write_text(changelog.to_text(), encoding="utf-8")

            # Generate diff overlay DXF
            overlay_target = output_dir / "diff_overlay.dxf"
            diff_overlay_path: Path | None = overlay_target
            overlay_generated = False
            try:
                write_diff_overlay(master_path, result, overlay_target)
                overlay_generated = True
            except Exception as e:
                span.record_exception(e)
                logger.error("Failed to generate diff overlay", exc_info=True)
                diff_overlay_path = None

            span.set_attribute("cad.compare.overlay_generated", overlay_generated)
            span.set_attribute("cad.compare.changelog_entries", len(changelog.entries))

            return ComparisonOutputs(
                result=result,
                changelog=changelog,
                diff_overlay_path=diff_overlay_path,
                master_path=Path(master_path),
                revision_path=Path(revision_path),
            )
