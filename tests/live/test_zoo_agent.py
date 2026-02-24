"""Zoo × Agent matrix — diverse drawings through real LLM.

Each scenario combines a factory-built DXF drawing with a realistic prompt,
runs the full pipeline through the real Gemini agent, and verifies structural
integrity of the output.

Run with:
  CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/test_zoo_agent.py -v -m live_api -s
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RuleConfig
from tests.helpers.dxf_factory import (
    create_dense_drawing,
    create_mixed_entity_drawing,
    create_overlapping_drawing,
    create_structural_drawing,
    create_unicode_drawing,
)

logger = logging.getLogger(__name__)


@dataclass
class ZooScenario:
    """A drawing + prompt combination for the zoo × agent matrix."""

    name: str
    dxf_builder: Callable[..., Path]
    builder_kwargs: dict
    prompt: str
    min_ops: int = 0  # 0 = may legitimately produce no ops


SCENARIOS = [
    ZooScenario(
        name="dense_move",
        dxf_builder=create_dense_drawing,
        builder_kwargs={"count": 500},
        prompt="Move the text label 'E1' five units east",
        min_ops=0,
    ),
    ZooScenario(
        name="mixed_delete_text",
        dxf_builder=create_mixed_entity_drawing,
        builder_kwargs={},
        prompt="Delete the text that says 'Sample Text'",
        min_ops=0,
    ),
    ZooScenario(
        name="unicode_rename",
        dxf_builder=create_unicode_drawing,
        builder_kwargs={},
        prompt="Rename the text '\u67f1A' to 'Column-A'",
        min_ops=0,
    ),
    ZooScenario(
        name="overlapping_move",
        dxf_builder=create_overlapping_drawing,
        builder_kwargs={},
        prompt="Move the entity named 'Overlap-A' north by 10 units",
        min_ops=0,
    ),
    ZooScenario(
        name="structural_multi_op",
        dxf_builder=create_structural_drawing,
        builder_kwargs={},
        prompt="Move column mark A-1 east by 2 feet and rename label B-2 to 'B-2R'",
        min_ops=0,
    ),
]


@pytest.mark.live_api
class TestZooAgentMatrix:
    """Zoo × Agent matrix: diverse drawings through real Gemini."""

    @pytest.mark.parametrize(
        "scenario",
        SCENARIOS,
        ids=[s.name for s in SCENARIOS],
    )
    def test_scenario_pipeline(
        self,
        scenario: ZooScenario,
        gcp_project: str,
        gcp_location: str,
        tmp_path: Path,
    ):
        """Run one zoo scenario through the full pipeline."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        # Build the DXF
        dxf_path = scenario.dxf_builder(tmp_path, **scenario.builder_kwargs)
        source_ctx = load_dxf(dxf_path)
        planner_ctx = build_planner_context(source_ctx)
        original_count = source_ctx.entity_count

        logger.info(
            "Scenario '%s': %d entities, prompt: %s",
            scenario.name,
            original_count,
            scenario.prompt,
        )

        # Plan with real Gemini (timeout is acceptable — LLM latency varies)
        from cad_dxf_agent.llm.errors import PlannerTimeoutError

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        try:
            changeset = provider.plan(scenario.prompt, planner_ctx)
        except PlannerTimeoutError:
            logger.warning("Scenario '%s': agent timed out (acceptable)", scenario.name)
            pytest.skip(f"Agent timed out for scenario '{scenario.name}'")

        assert changeset is not None
        assert changeset.planner_trace is not None
        logger.info(
            "Scenario '%s': %d ops, %d turns",
            scenario.name,
            changeset.op_count,
            changeset.planner_trace.total_turns,
        )

        # Validate
        result = validate_changeset(changeset, source_ctx, RuleConfig())

        # Apply & save if valid ops exist
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / f"{scenario.name}_output.dxf"
            engine = EditEngine(dxf_path)
            engine.apply_changeset(changeset)
            engine.save(out_path)

            assert out_path.exists(), f"Output DXF not created for {scenario.name}"

            # Round-trip integrity: re-load the output
            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count >= 1, f"Output DXF has no entities for {scenario.name}"
            logger.info(
                "Scenario '%s': output has %d entities (was %d)",
                scenario.name,
                out_ctx.entity_count,
                original_count,
            )
        else:
            logger.info(
                "Scenario '%s': skipped apply (%d blockers, %d ops)",
                scenario.name,
                len(result.blockers),
                changeset.op_count,
            )
