"""Live tests for the validation feedback loop against real Vertex AI.

These tests verify that the planner's validation feedback loop works
end-to-end with real Gemini API calls.  When the LLM produces a changeset
with validation blockers, the loop should re-call Gemini with corrective
feedback, giving the agent a chance to self-correct.

Run with:
    CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/test_validation_feedback.py -v -m live_api -s
"""

from __future__ import annotations

import logging

import pytest

from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.llm.planner import run_planner
from cad_dxf_agent.models.config_schema import RuleConfig

logger = logging.getLogger(__name__)


def _make_rule_config() -> RuleConfig:
    return RuleConfig(
        protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"],
        max_move_distance=1000.0,
    )


@pytest.mark.live_api
class TestValidationFeedbackLoop:
    """Validation feedback loop self-corrects invalid changesets via Gemini."""

    def test_protected_layer_self_correction(
        self, gcp_project, structural_context, planner_context
    ):
        """Agent should self-correct when targeting a protected layer.

        Ask the agent to edit text on the TITLE layer.  The first attempt
        should produce a blocker.  After feedback the agent should either
        refuse (empty changeset) or target a different, non-protected entity.
        """
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project)
        rule_config = _make_rule_config()

        changeset = run_planner(
            "Change the title text on the TITLE layer to read 'NEW TITLE'",
            planner_context,
            provider=provider,
            context=structural_context,
            rule_config=rule_config,
        )

        # After the feedback loop, the final changeset should either:
        # - have no blockers (agent fixed its mistake), OR
        # - be empty (agent refused the impossible request)
        result = validate_changeset(changeset, structural_context, rule_config)
        if changeset.op_count > 0:
            assert not result.blockers, (
                f"Agent failed to self-correct after feedback: "
                f"{[b.message for b in result.blockers]}"
            )
        # Empty changeset is also acceptable — means agent refused

    def test_nonexistent_handle_self_correction(
        self, gcp_project, structural_context, planner_context
    ):
        """Agent should self-correct when referencing a nonexistent handle.

        Ask the agent to move entity handle 'ZZZZZ' which doesn't exist.
        After validation feedback the agent should pick a valid handle.
        """
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project)
        rule_config = _make_rule_config()

        changeset = run_planner(
            "Move entity with handle ZZZZZ ten units east",
            planner_context,
            provider=provider,
            context=structural_context,
            rule_config=rule_config,
        )

        result = validate_changeset(changeset, structural_context, rule_config)
        if changeset.op_count > 0:
            assert not result.blockers, (
                f"Agent failed to self-correct after feedback: "
                f"{[b.message for b in result.blockers]}"
            )

    def test_valid_request_no_retry(self, gcp_project, structural_context, planner_context):
        """A valid request should succeed on first attempt with no retries."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project)
        rule_config = _make_rule_config()

        changeset = run_planner(
            "Move the first line on the COLUMNS layer 10 units east",
            planner_context,
            provider=provider,
            context=structural_context,
            rule_config=rule_config,
        )

        assert changeset is not None
        assert changeset.op_count >= 1
        result = validate_changeset(changeset, structural_context, rule_config)
        assert not result.blockers
