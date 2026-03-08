"""Stage pipeline executor — runs typed stages with gate checkpoints.

Executes the stages defined by a StagePipelineDefinition in order,
collecting StageGate checkpoints for each stage. Each stage handler
receives the accumulated context and returns output data.

Stage handlers are registered by name and called in sequence. If a stage
handler is not registered, the stage is skipped (logged as warning).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    StageGate,
    StagePipelineDefinition,
)

logger = logging.getLogger(__name__)


class StageHandler(Protocol):
    """Protocol for stage handlers.

    Each handler receives:
    - classification: the two-axis classification result
    - context: accumulated data from prior stages + initial drawing context
    - prompt: the original user prompt

    Returns a dict of output data to merge into context for subsequent stages.
    """

    def execute(
        self,
        classification: ObjectiveClassification,
        context: dict[str, Any],
        prompt: str,
    ) -> dict[str, Any]: ...


class StageExecutionResult:
    """Result of executing a stage pipeline."""

    def __init__(
        self,
        *,
        gates: list[StageGate],
        output: dict[str, Any],
        output_mode: str,
        total_time_ms: float,
    ) -> None:
        self.gates = gates
        self.output = output
        self.output_mode = output_mode
        self.total_time_ms = total_time_ms

    @property
    def completed_stages(self) -> list[str]:
        return [g.stage_name for g in self.gates if g.status == "completed"]

    @property
    def skipped_stages(self) -> list[str]:
        return [g.stage_name for g in self.gates if g.status == "skipped"]

    @property
    def all_completed(self) -> bool:
        return all(g.status in ("completed", "skipped") for g in self.gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gates": [g.model_dump() for g in self.gates],
            "output": self.output,
            "output_mode": self.output_mode,
            "total_time_ms": self.total_time_ms,
            "completed_stages": self.completed_stages,
            "skipped_stages": self.skipped_stages,
        }


class StagePipelineExecutor:
    """Executes stage pipelines with registered handlers and gate checkpoints."""

    def __init__(self) -> None:
        self._handlers: dict[str, StageHandler] = {}

    def register(self, stage_name: str, handler: StageHandler) -> None:
        """Register a handler for a named stage."""
        self._handlers[stage_name] = handler

    def has_handler(self, stage_name: str) -> bool:
        return stage_name in self._handlers

    def execute(
        self,
        *,
        pipeline: StagePipelineDefinition,
        classification: ObjectiveClassification,
        initial_context: dict[str, Any],
        prompt: str,
    ) -> StageExecutionResult:
        """Execute all stages in the pipeline definition.

        Stages run in order. Each stage's output is merged into context
        for subsequent stages. A StageGate checkpoint is recorded for each.
        """
        start = time.monotonic()
        gates: list[StageGate] = []
        context = dict(initial_context)

        for stage_name in pipeline.stages:
            gate = StageGate(stage_name=stage_name, status="active")

            handler = self._handlers.get(stage_name)
            if handler is None:
                logger.warning("No handler for stage '%s', skipping", stage_name)
                gate.status = "skipped"
                gate.output_summary = f"No handler registered for '{stage_name}'"
                gates.append(gate)
                continue

            stage_start = time.monotonic()
            try:
                output = handler.execute(
                    classification=classification,
                    context=context,
                    prompt=prompt,
                )
                stage_ms = (time.monotonic() - stage_start) * 1000

                # Merge output into accumulated context
                context.update(output)

                gate.status = "completed"
                gate.output_summary = output.get("summary", f"Stage '{stage_name}' completed")
                gate.output_data = {
                    "stage_time_ms": stage_ms,
                    **{k: v for k, v in output.items() if k != "summary"},
                }
            except Exception:
                stage_ms = (time.monotonic() - stage_start) * 1000
                logger.exception("Stage '%s' failed", stage_name)
                gate.status = "rejected"
                gate.output_summary = f"Stage '{stage_name}' failed"
                gate.output_data = {"stage_time_ms": stage_ms}

            gates.append(gate)

            # Stop pipeline if a stage was rejected
            if gate.status == "rejected":
                # Mark remaining stages as skipped
                remaining_idx = pipeline.stages.index(stage_name) + 1
                for remaining in pipeline.stages[remaining_idx:]:
                    gates.append(StageGate(
                        stage_name=remaining,
                        status="skipped",
                        output_summary=f"Skipped due to '{stage_name}' failure",
                    ))
                break

        total_ms = (time.monotonic() - start) * 1000
        return StageExecutionResult(
            gates=gates,
            output=context,
            output_mode=pipeline.output_mode,
            total_time_ms=total_ms,
        )

    @property
    def registered_stages(self) -> list[str]:
        return list(self._handlers.keys())
