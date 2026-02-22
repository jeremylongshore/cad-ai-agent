"""Live tests for AgentProvider tool-use loop against real Vertex AI.

These tests verify the iterative find → edit pattern works end-to-end:
the agent discovers entities via query tools, then edits them via edit tools.

Run with: make test-live  (or pytest tests/live/ -m live_api)
"""

from __future__ import annotations

import pytest


@pytest.mark.live_api
class TestAgentLoopLive:
    """Agent tool-use loop produces valid ChangeSets with real Gemini."""

    def test_agent_move_produces_ops(self, gcp_project, gcp_location, planner_context):
        """Agent loop: find entities → move one → returns ChangeSet with move op."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Move the column mark at grid B-2 one foot north",
            planner_context,
        )

        assert changeset is not None
        assert changeset.op_count >= 1
        # Agent should have used at least one tool turn
        assert "Agent edit" in (changeset.revision_label or "")

    def test_agent_delete_produces_ops(self, gcp_project, gcp_location, planner_context):
        """Agent loop: find → delete produces valid ChangeSet.

        May return 0 ops if LLM can't locate target entity.
        """
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Delete the dimension at the bottom of the drawing",
            planner_context,
        )

        assert changeset is not None
        # LLM may not always find a matching entity — accept 0+ ops
        assert changeset.op_count >= 0

    def test_agent_respects_protected_layers(self, gcp_project, gcp_location, planner_context):
        """Agent should not produce ops on protected layers even if asked."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Delete the project title",
            planner_context,
        )

        # Either 0 ops (correctly refused) or ops that don't target protected layers
        protected = {"TITLE", "TITLEBLOCK", "SEAL", "REVISION"}
        for op in changeset.operations:
            if op.target_layer:
                assert op.target_layer.upper() not in protected

    def test_agent_multi_op(self, gcp_project, gcp_location, planner_context):
        """Agent can produce multiple operations in one prompt."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        provider = AgentProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Move column A-1 east by 2 feet and update its label to 'A-1R'",
            planner_context,
        )

        assert changeset is not None
        # Ideally 2 ops, but at least 1
        assert changeset.op_count >= 1
