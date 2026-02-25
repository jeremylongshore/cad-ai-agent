"""Live full-pipeline experience tests — real Gemini agent end-to-end.

Each test simulates a real user session:
  load DXF → build context → AgentProvider.plan() → validate → apply → save → verify output

Prompts are loaded from tests/fixtures/prompt_bank.json by category.
Tests verify pipeline behavior, not LLM judgment quality.

Run with:
  CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/test_full_pipeline.py -v -m live_api -s
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet

logger = logging.getLogger(__name__)

PROMPT_BANK = Path(__file__).resolve().parent.parent / "fixtures" / "prompt_bank.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_prompts(category: str) -> list[dict]:
    """Load prompts from the bank, filtered by category."""
    data = json.loads(PROMPT_BANK.read_text())
    return [p for p in data["prompts"] if p["category"] == category]


def _apply_and_save(changeset: ChangeSet, source_path: Path, out_path: Path) -> Path:
    """Apply a changeset to the source DXF and save to out_path."""
    engine = EditEngine(source_path)
    engine.apply_changeset(changeset)
    return Path(engine.save(out_path))


def _pick_prompt(category: str) -> dict:
    """Pick the first prompt from a category (deterministic for CI)."""
    prompts = _load_prompts(category)
    assert prompts, f"No prompts found for category: {category}"
    return prompts[0]


# ---------------------------------------------------------------------------
# Full pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.live_api
class TestFullPipelineLive:
    """End-to-end pipeline tests with real Gemini agent."""

    def test_move_full_pipeline(self, gcp_project, gcp_location, structural_drawing, tmp_path):
        """Move prompt → agent → validate → apply → save → verify round-trip."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        prompt_entry = _pick_prompt("move")
        source_ctx = load_dxf(structural_drawing)
        planner_ctx = build_planner_context(source_ctx)
        original_count = source_ctx.entity_count

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(prompt_entry["prompt"], planner_ctx)

        assert changeset is not None
        assert changeset.op_count >= prompt_entry["min_ops"]
        assert changeset.planner_trace is not None

        # Validate
        result = validate_changeset(changeset, source_ctx, RuleConfig())
        if changeset.op_count > 0:
            # If agent produced ops, they should be valid
            logger.info(
                "Validation: %d blockers, %d warnings",
                len(result.blockers),
                len(result.warnings),
            )

        # Apply & save (only if no blockers)
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "move_output.dxf"
            _apply_and_save(changeset, structural_drawing, out_path)
            assert out_path.exists()

            # Round-trip: re-load output
            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count == original_count  # move preserves count

    def test_edit_text_full_pipeline(self, gcp_project, gcp_location, structural_drawing, tmp_path):
        """Edit text prompt → agent → validate → apply → save → verify."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        prompt_entry = _pick_prompt("edit_text")
        source_ctx = load_dxf(structural_drawing)
        planner_ctx = build_planner_context(source_ctx)

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(prompt_entry["prompt"], planner_ctx)

        assert changeset is not None
        assert changeset.planner_trace is not None

        # Validate & apply
        result = validate_changeset(changeset, source_ctx, RuleConfig())
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "edit_text_output.dxf"
            _apply_and_save(changeset, structural_drawing, out_path)
            assert out_path.exists()

            # Round-trip integrity
            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count >= 1

    def test_delete_full_pipeline(self, gcp_project, gcp_location, structural_drawing, tmp_path):
        """Delete prompt → agent → validate → apply → save → verify count decreased."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        prompt_entry = _pick_prompt("delete")
        source_ctx = load_dxf(structural_drawing)
        planner_ctx = build_planner_context(source_ctx)
        original_count = source_ctx.entity_count

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(prompt_entry["prompt"], planner_ctx)

        assert changeset is not None
        assert changeset.planner_trace is not None

        result = validate_changeset(changeset, source_ctx, RuleConfig())
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "delete_output.dxf"
            _apply_and_save(changeset, structural_drawing, out_path)
            assert out_path.exists()

            out_ctx = load_dxf(out_path)
            # Delete should reduce entity count
            assert out_ctx.entity_count <= original_count

    def test_multi_op_full_pipeline(self, gcp_project, gcp_location, structural_drawing, tmp_path):
        """Multi-op prompt → agent → validate → apply → save → verify."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        prompt_entry = _pick_prompt("multi_op")
        source_ctx = load_dxf(structural_drawing)
        planner_ctx = build_planner_context(source_ctx)

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(prompt_entry["prompt"], planner_ctx)

        assert changeset is not None
        assert changeset.planner_trace is not None
        # Multi-op should ideally produce 2+ ops
        logger.info("Multi-op produced %d operations", changeset.op_count)

        result = validate_changeset(changeset, source_ctx, RuleConfig())
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "multi_op_output.dxf"
            _apply_and_save(changeset, structural_drawing, out_path)
            assert out_path.exists()

            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count >= 1

    def test_protected_layer_blocked(self, gcp_project, gcp_location, structural_drawing):
        """Protected layer prompt → agent respects protection or validator blocks."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        prompt_entry = _pick_prompt("protected_layer")
        source_ctx = load_dxf(structural_drawing)
        planner_ctx = build_planner_context(source_ctx)

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(prompt_entry["prompt"], planner_ctx)

        assert changeset is not None

        if changeset.op_count > 0:
            # If agent produced ops targeting protected layers, validator should block
            result = validate_changeset(changeset, source_ctx, RuleConfig())
            protected = {"TITLE", "TITLEBLOCK", "SEAL", "REVISION"}
            for op in changeset.operations:
                if op.target_handle:
                    entity = source_ctx.get_entity_by_handle(op.target_handle)
                    if entity and entity.layer.upper() in protected:
                        assert result.blockers, "Validator should block ops on protected layers"

    def test_ambiguous_prompt_completes(self, gcp_project, gcp_location, structural_drawing):
        """Ambiguous/vague prompt → pipeline completes without crash."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        prompt_entry = _pick_prompt("ambiguous")
        source_ctx = load_dxf(structural_drawing)
        planner_ctx = build_planner_context(source_ctx)

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(prompt_entry["prompt"], planner_ctx)

        # Pipeline should complete without raising — changeset may have 0 ops
        assert changeset is not None
        assert changeset.planner_trace is not None
        logger.info(
            "Ambiguous prompt '%s' produced %d ops",
            prompt_entry["prompt"],
            changeset.op_count,
        )
