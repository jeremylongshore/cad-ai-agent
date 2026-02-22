"""Live tests for one-shot GeminiProvider against real Vertex AI.

These tests call the actual Gemini API and validate that the response
is a structurally valid ChangeSet. They require:
  - GOOGLE_CLOUD_PROJECT env var set
  - Valid GCP credentials (gcloud auth application-default login)
  - pip install -e ".[gemini]"

Run with: make test-live  (or pytest tests/live/ -m live_api)
"""

from __future__ import annotations

import pytest


@pytest.mark.live_api
class TestGeminiOneShotLive:
    """One-shot GeminiProvider returns valid ChangeSets from real prompts."""

    def test_move_entity_prompt(self, gcp_project, gcp_location, planner_context):
        """Gemini produces a valid ChangeSet for a move request."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Move the column mark at grid A-1 two feet east",
            planner_context,
        )

        assert changeset is not None
        assert changeset.op_count >= 1
        for op in changeset.operations:
            assert op.op_type is not None

    def test_edit_text_prompt(self, gcp_project, gcp_location, planner_context):
        """Gemini produces a valid ChangeSet for a text edit."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Change the label at column A-1 to read 'RELOCATED'",
            planner_context,
        )

        assert changeset is not None
        assert changeset.op_count >= 1

    def test_delete_entity_prompt(self, gcp_project, gcp_location, planner_context):
        """Gemini produces a valid ChangeSet for a delete request."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Delete the footing schedule note",
            planner_context,
        )

        assert changeset is not None
        assert changeset.op_count >= 1

    def test_protected_layer_not_targeted(self, gcp_project, gcp_location, planner_context):
        """Gemini should not produce ops targeting protected layers."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Move the text on the NOTES layer 10 units north",
            planner_context,
        )

        protected = {"TITLE", "TITLEBLOCK", "SEAL", "REVISION"}
        for op in changeset.operations:
            if op.target_layer:
                assert op.target_layer.upper() not in protected, (
                    f"Op targets protected layer: {op.target_layer}"
                )

    def test_empty_prompt_returns_changeset(self, gcp_project, gcp_location, planner_context):
        """Even an ambiguous prompt returns a valid (possibly empty) ChangeSet."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Make the drawing better",
            planner_context,
        )

        # Should not crash — may return 0 or more ops
        assert changeset is not None
