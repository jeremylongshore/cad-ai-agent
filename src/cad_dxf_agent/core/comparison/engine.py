"""Comparison engine — top-level orchestrator for DXF comparison."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ...models.comparison_schema import ComparisonConfig, ComparisonResult
from .changelog import ChangeLog, generate_changelog
from .classifier import classify_changes
from .diff_overlay import write_diff_overlay
from .geometry import extract_snapshots
from .matcher import match_entities

logger = logging.getLogger(__name__)


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
        config = config or ComparisonConfig()

        logger.info("Extracting geometry from master: %s", Path(master_path).name)
        master_snaps = extract_snapshots(master_path, config)

        logger.info("Extracting geometry from revision: %s", Path(revision_path).name)
        revision_snaps = extract_snapshots(revision_path, config)

        logger.info(
            "Matching entities: %d master, %d revision",
            len(master_snaps),
            len(revision_snaps),
        )
        match_result = match_entities(master_snaps, revision_snaps, config)

        logger.info(
            "Matched %d pairs, %d master-only, %d revision-only",
            len(match_result.pairs),
            len(match_result.master_only),
            len(match_result.revision_only),
        )
        result = classify_changes(match_result, config)

        logger.info("Classification: %s", result.summary)
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
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate change log
        changelog = generate_changelog(result)

        # Write change log files
        changelog_json_path = output_dir / "changelog.json"
        changelog_json_path.write_text(changelog.to_json())

        changelog_text_path = output_dir / "changelog.txt"
        changelog_text_path.write_text(changelog.to_text())

        # Generate diff overlay DXF
        overlay_target = output_dir / "diff_overlay.dxf"
        diff_overlay_path: Path | None = overlay_target
        try:
            write_diff_overlay(master_path, result, overlay_target)
        except Exception:
            logger.error("Failed to generate diff overlay", exc_info=True)
            diff_overlay_path = None

        return ComparisonOutputs(
            result=result,
            changelog=changelog,
            diff_overlay_path=diff_overlay_path,
            master_path=Path(master_path),
            revision_path=Path(revision_path),
        )
