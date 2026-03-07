"""Integration tests for the agent tool-use loop using ScriptedAgentProvider.

Tests that scripted tool-call sequences produce correct operations when
routed through the real ToolExecutor with real protection rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RuleConfig
from cad_dxf_agent.models.ops_schema import OpType
from tests.helpers.scripted_provider import ScriptedAgentProvider

TRAJECTORY_DIR = Path(__file__).parent.parent / "fixtures" / "trajectories"


@pytest.mark.integration
class TestScriptedAgentLoop:
    def test_scripted_two_turn_move(self, sample_dxf, tmp_path):
        """Scripted: find entity → move it → verify 1 move_entity op."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)

        # Find an editable entity handle
        editable = next(
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        provider = ScriptedAgentProvider(
            turns=[
                [("find_entities", {"layer": "STRUCTURAL"})],
                [("move_entity", {"handle": editable.handle, "dx": 24.0, "dy": 0.0})],
            ]
        )

        changeset = provider.plan("Move column east by 2 feet", planner_ctx)
        assert changeset.op_count == 1
        assert changeset.operations[0].op_type == OpType.MOVE_ENTITY
        assert changeset.operations[0].params["dx"] == 24.0

        # Validate the changeset
        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        assert validation.valid

    def test_scripted_protected_layer_rejection(self, sample_dxf):
        """Scripted: move on protected layer → 0 ops produced."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)

        title_entity = next(e for e in context.entities if e.layer.upper() == "TITLE")

        provider = ScriptedAgentProvider(
            turns=[
                [("find_entities", {"layer": "TITLE"})],
                [("move_entity", {"handle": title_entity.handle, "dx": 24.0, "dy": 0.0})],
            ]
        )

        changeset = provider.plan("Move the title", planner_ctx)
        # ToolExecutor refuses to queue the op on protected layer → 0 ops
        assert changeset.op_count == 0

    def test_scripted_multi_op(self, sample_dxf):
        """Scripted: two ops in one turn → both queued."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)

        editables = [
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        ]
        assert len(editables) >= 2

        provider = ScriptedAgentProvider(
            turns=[
                [
                    ("move_entity", {"handle": editables[0].handle, "dx": 10, "dy": 0}),
                    ("move_entity", {"handle": editables[1].handle, "dx": -10, "dy": 0}),
                ],
            ]
        )

        changeset = provider.plan("Swap two entities", planner_ctx)
        assert changeset.op_count == 2


@pytest.mark.integration
class TestGoldenTrajectories:
    """Parametrized tests over trajectory fixture files.

    Each trajectory defines a prompt, expected tool-call sequence, and
    expected operation outcomes. The test builds a dynamic ScriptedAgentProvider
    from the trajectory and validates the results.
    """

    @staticmethod
    def _load_trajectories():
        """Load edit trajectory JSON files (skip non-agent-loop fixtures)."""
        trajectories = []
        for path in sorted(TRAJECTORY_DIR.glob("*.json")):
            with open(path) as f:
                data = json.load(f)
            # Skip non-agent-loop fixtures (different format, no expected_turns)
            if data.get("task_family") in ("qna", "repeated_condition"):
                continue
            data["_file"] = path.name
            trajectories.append(data)
        return trajectories

    @pytest.fixture(params=_load_trajectories.__func__(), ids=lambda t: t["_file"])
    def trajectory(self, request):
        return request.param

    def test_trajectory_golden_file(self, sample_dxf, trajectory):
        """Validate that a golden trajectory produces expected op types and counts."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)

        # Build turns from trajectory, resolving __FIRST_MATCH__ handles
        turns = []
        first_editable = next(
            (
                e
                for e in context.entities
                if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
            ),
            None,
        )
        title_entity = next(
            (e for e in context.entities if e.layer.upper() == "TITLE"),
            None,
        )

        for turn_spec in trajectory["expected_turns"]:
            turn_calls = []
            for tc in turn_spec["tool_calls"]:
                args = dict(tc["args"])
                # Resolve placeholder handles
                for key, val in args.items():
                    if val == "__FIRST_MATCH__" and first_editable:
                        args[key] = first_editable.handle
                    elif val == "__TITLE_ENTITY__" and title_entity:
                        args[key] = title_entity.handle
                turn_calls.append((tc["name"], args))
            turns.append(turn_calls)

        provider = ScriptedAgentProvider(turns=turns)
        changeset = provider.plan(trajectory["prompt"], planner_ctx)

        # Verify expected op count
        assert changeset.op_count == trajectory["expected_op_count"]

        # Verify expected op types
        actual_types = [op.op_type.value for op in changeset.operations]
        assert actual_types == trajectory["expected_op_types"]

        # Verify must_not_touch_layers
        for op in changeset.operations:
            if op.target_layer:
                assert op.target_layer.upper() not in [
                    layer.upper() for layer in trajectory["must_not_touch_layers"]
                ]
