"""Pipeline worker — runs plan/apply stages on a background QThread."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from ..core.edit_engine import EditEngine
from ..core.preview_model import PreviewModel
from ..core.revision_notes import insert_revision_note
from ..core.semantic_model import build_planner_context
from ..core.validators import validate_changeset
from ..llm.planner import run_planner
from ..models.cad_schema import DrawingContext
from ..models.changes_schema import ValidationResult
from ..models.config_schema import RevisionNoteConfig, RuleConfig
from ..models.ops_schema import AppliedChange, ChangeSet

logger = logging.getLogger(__name__)


class PipelineStage(StrEnum):
    """Named stages in the plan/apply pipeline."""

    BUILD_CONTEXT = "Build Context"
    RUN_PLANNER = "Run Planner"
    VALIDATE = "Validate"
    PREVIEW = "Preview"
    EDIT_ENGINE = "Edit Engine"
    SAVE = "Save"
    REVISION_NOTES = "Revision Notes"


@dataclass
class StageResult:
    """Timing and outcome for a single pipeline stage."""

    stage: PipelineStage
    duration_ms: float
    success: bool = True
    error: str = ""


@dataclass
class PlanResult:
    """Outcome of a plan run."""

    changeset: ChangeSet
    validation: ValidationResult
    preview: PreviewModel
    stages: list[StageResult] = field(default_factory=list)


@dataclass
class ApplyResult:
    """Outcome of an apply run."""

    applied_changes: list[AppliedChange]
    output_path: str
    note_text: str
    engine_doc: Any  # ezdxf.document.Drawing — kept for EditHistory.push()
    stages: list[StageResult] = field(default_factory=list)


class PipelineWorker(QThread):
    """Runs pipeline stages off the main thread.

    Usage::

        worker = PipelineWorker()
        worker.setup_plan(prompt, context, rule_config)
        worker.plan_succeeded.connect(on_ok)
        worker.plan_failed.connect(on_err)
        worker.start()
    """

    # Signals
    stage_started = Signal(str)
    stage_finished = Signal(str, float)  # stage name, duration_ms
    plan_succeeded = Signal(object)  # PlanResult
    plan_failed = Signal(str)  # error message
    apply_succeeded = Signal(object)  # ApplyResult
    apply_failed = Signal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode: str = ""  # "plan" or "apply"
        self._cancelled = False

        # Plan params
        self._prompt: str = ""
        self._context: DrawingContext | None = None
        self._rule_config: RuleConfig | None = None

        # Apply params
        self._changeset: ChangeSet | None = None
        self._dxf_path: Path | None = None
        self._output_path: str = ""
        self._rev_config: RevisionNoteConfig | None = None

    # ── Setup ──────────────────────────────────────────────────

    def setup_plan(
        self,
        prompt: str,
        context: DrawingContext,
        rule_config: RuleConfig,
    ) -> None:
        """Configure for a plan run. Call before start()."""
        self._mode = "plan"
        self._prompt = prompt
        self._context = context
        self._rule_config = rule_config

    def setup_apply(
        self,
        changeset: ChangeSet,
        dxf_path: Path,
        output_path: str,
        rule_config: RuleConfig,
        rev_config: RevisionNoteConfig,
    ) -> None:
        """Configure for an apply run. Call before start()."""
        self._mode = "apply"
        self._changeset = changeset
        self._dxf_path = dxf_path
        self._output_path = output_path
        self._rule_config = rule_config
        self._rev_config = rev_config

    def cancel(self) -> None:
        """Request cancellation (checked between stages)."""
        self._cancelled = True

    # ── Thread entry ───────────────────────────────────────────

    def run(self) -> None:  # noqa: A003
        """QThread entry point — dispatches to plan or apply."""
        self._cancelled = False
        try:
            if self._mode == "plan":
                self._run_plan()
            elif self._mode == "apply":
                self._run_apply()
            else:
                self.plan_failed.emit(f"Unknown mode: {self._mode}")
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            logger.error("Pipeline worker error: %s", msg)
            if self._mode == "plan":
                self.plan_failed.emit(msg)
            else:
                self.apply_failed.emit(msg)

    # ── Plan pipeline ──────────────────────────────────────────

    def _run_plan(self) -> None:
        assert self._context is not None
        assert self._rule_config is not None
        stages: list[StageResult] = []

        # Stage 1: Build context
        drawing_ctx, sr = self._timed_stage(
            PipelineStage.BUILD_CONTEXT,
            lambda: build_planner_context(self._context),  # type: ignore[arg-type]
        )
        stages.append(sr)
        if not sr.success or self._cancelled:
            self.plan_failed.emit(sr.error or "Cancelled")
            return

        # Stage 2: Run planner
        changeset, sr = self._timed_stage(
            PipelineStage.RUN_PLANNER,
            lambda: run_planner(self._prompt, drawing_ctx),
        )
        stages.append(sr)
        if not sr.success or self._cancelled:
            self.plan_failed.emit(sr.error or "Cancelled")
            return

        # Stage 3: Validate
        validation, sr = self._timed_stage(
            PipelineStage.VALIDATE,
            lambda: validate_changeset(changeset, self._context, self._rule_config),  # type: ignore[arg-type]
        )
        stages.append(sr)
        if not sr.success or self._cancelled:
            self.plan_failed.emit(sr.error or "Cancelled")
            return

        # Stage 4: Preview
        preview, sr = self._timed_stage(
            PipelineStage.PREVIEW,
            lambda: PreviewModel(changeset, self._context, validation),  # type: ignore[arg-type]
        )
        stages.append(sr)
        if not sr.success or self._cancelled:
            self.plan_failed.emit(sr.error or "Cancelled")
            return

        result = PlanResult(
            changeset=changeset,
            validation=validation,
            preview=preview,
            stages=stages,
        )
        self.plan_succeeded.emit(result)

    # ── Apply pipeline ─────────────────────────────────────────

    def _run_apply(self) -> None:
        assert self._changeset is not None
        assert self._dxf_path is not None
        assert self._rule_config is not None
        assert self._rev_config is not None
        stages: list[StageResult] = []

        # Stage 1: Edit engine
        engine, sr = self._timed_stage(
            PipelineStage.EDIT_ENGINE,
            lambda: self._do_apply_engine(),
        )
        stages.append(sr)
        if not sr.success or self._cancelled:
            self.apply_failed.emit(sr.error or "Cancelled")
            return

        engine_obj, results = engine

        # Stage 2: Save
        _, sr = self._timed_stage(
            PipelineStage.SAVE,
            lambda: engine_obj.save(self._output_path),
        )
        stages.append(sr)
        if not sr.success or self._cancelled:
            self.apply_failed.emit(sr.error or "Cancelled")
            return

        # Stage 3: Revision notes
        note_text = ""
        if self._rev_config.enabled:
            note_text, sr = self._timed_stage(
                PipelineStage.REVISION_NOTES,
                lambda: insert_revision_note(
                    self._output_path,
                    self._output_path,
                    results,
                    self._rev_config,  # type: ignore[arg-type]
                ),
            )
            stages.append(sr)
            if not sr.success:
                # Non-fatal: revision note failure doesn't block apply
                logger.warning("Revision note failed: %s", sr.error)

        result = ApplyResult(
            applied_changes=results,
            output_path=self._output_path,
            note_text=note_text,
            engine_doc=engine_obj.doc,
            stages=stages,
        )
        self.apply_succeeded.emit(result)

    def _do_apply_engine(self):
        """Create EditEngine and apply changeset. Returns (engine, results)."""
        engine = EditEngine(self._dxf_path)  # type: ignore[arg-type]
        results = engine.apply_changeset(self._changeset)  # type: ignore[arg-type]
        return engine, results

    # ── Timing helper ──────────────────────────────────────────

    def _timed_stage(self, stage: PipelineStage, func):
        """Run *func*, emit stage signals, and return (result, StageResult)."""
        self.stage_started.emit(stage.value)
        t0 = time.monotonic()
        try:
            result = func()
            duration_ms = (time.monotonic() - t0) * 1000
            sr = StageResult(stage=stage, duration_ms=duration_ms)
            self.stage_finished.emit(stage.value, duration_ms)
            return result, sr
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            sr = StageResult(
                stage=stage,
                duration_ms=duration_ms,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            self.stage_finished.emit(stage.value, duration_ms)
            return None, sr
