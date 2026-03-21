"""Live API test for selection-augmented prompts.

Sends a prompt with [ACTIVE SELECTION] block to Gemini and verifies
the returned ChangeSet targets the specified handle.

Requires:
  - ADC authenticated: gcloud auth application-default login
  - CAD_GCP_PROJECT=cad-dxf-agent
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.live_api,
    pytest.mark.skipif(
        os.getenv("CAD_LLM_PROVIDER", "mock") == "mock",
        reason="Requires live LLM provider (CAD_LLM_PROVIDER != mock)",
    ),
]


@pytest.fixture
def structural_context():
    """Minimal DrawingContext with a movable INSERT entity."""
    from cad_dxf_agent.core.dxf_reader import load_drawing
    from tests.helpers.dxf_factory import make_structural_drawing

    dxf_path = make_structural_drawing()
    return load_drawing(str(dxf_path))


def test_selection_augmented_prompt_targets_handle(structural_context):
    """Gemini resolves [ACTIVE SELECTION] handle without searching."""
    from cad_dxf_agent.core.semantic_model import build_planner_context
    from cad_dxf_agent.llm.planner import run_planner
    from cad_dxf_agent.models.config_schema import RuleConfig

    ctx = structural_context
    # Pick a real entity from the context
    target = None
    for ent in ctx.entities:
        if ent.entity_type.value == "INSERT" and ent.layer.upper() not in {
            "TITLE",
            "TITLEBLOCK",
            "SEAL",
            "REVISION",
        }:
            target = ent
            break

    if target is None:
        pytest.skip("No non-protected INSERT entity in structural fixture")

    handle = target.handle
    layer = target.layer
    block = target.block_name or "BLOCK"
    x = target.insert_point.x if target.insert_point else 0.0
    y = target.insert_point.y if target.insert_point else 0.0

    augmented_prompt = (
        f"[ACTIVE SELECTION]\n"
        f"The user has selected 1 entity in the viewer:\n"
        f'- Handle "{handle}" — INSERT on layer {layer} ({block}) at ({x:.1f}, {y:.1f})\n'
        f'When the user says "selected", "this", "these", or "the selected entity", '
        f"target this entity by the handle(s) listed above.\n"
        f"[/ACTIVE SELECTION]\n\n"
        f"move the selected item 24 inches east"
    )

    planner_context = build_planner_context(ctx)
    rule_config = RuleConfig()

    changeset = run_planner(
        prompt=augmented_prompt,
        drawing_context=planner_context,
        context=ctx,
        rule_config=rule_config,
    )

    assert len(changeset.operations) >= 1, "Expected at least one operation"
    op = changeset.operations[0]
    assert op.target_handle == handle, (
        f"Expected op to target handle '{handle}', got '{op.target_handle}'"
    )
    assert op.op_type.value == "move_entity"
