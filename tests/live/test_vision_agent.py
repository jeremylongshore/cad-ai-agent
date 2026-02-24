"""Live tests for vision-augmented agent planning against real Vertex AI.

Exercises the full vision flow: render DXF → PNG → describe → agent → changeset.

Run with: CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/test_vision_agent.py -v -m live_api -s
"""

from __future__ import annotations

import pytest


@pytest.mark.live_api
class TestVisionAugmentedAgent:
    """Full pipeline with vision: render → describe → agent → validate → save."""

    @pytest.fixture
    def drawing_png(self, structural_drawing, tmp_path):
        """Render the structural drawing to PNG for vision tests."""
        try:
            from cad_dxf_agent.core.renderer import render_dxf_to_png

            result = render_dxf_to_png(structural_drawing, tmp_path / "vision.png")
            if result.success:
                return result.output_path
        except ImportError:
            pass

        # Fallback: create a minimal PNG with pillow
        try:
            from PIL import Image

            img = Image.new("RGB", (800, 600), "white")
            png_path = tmp_path / "vision.png"
            img.save(str(png_path))
            return png_path
        except ImportError:
            pytest.skip("Neither matplotlib nor Pillow available for PNG creation")

    def test_vision_augmented_move(
        self, gcp_project, gcp_location, planner_context, drawing_png
    ):
        """Agent with vision produces a valid ChangeSet for a move command."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        agent = AgentProvider(
            project=gcp_project,
            location=gcp_location,
            image_path=drawing_png,
        )

        changeset = agent.plan("Move column C-1 two feet east", planner_context)
        assert changeset.op_count >= 1
        assert changeset.planner_trace is not None
        assert changeset.planner_trace.total_turns >= 1

    def test_vision_augmented_delete(
        self, gcp_project, gcp_location, planner_context, drawing_png
    ):
        """Agent with vision can delete an entity."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        agent = AgentProvider(
            project=gcp_project,
            location=gcp_location,
            image_path=drawing_png,
        )

        changeset = agent.plan("Delete the column at grid A-1", planner_context)
        assert changeset.op_count >= 1

    def test_run_planner_with_image_path(
        self, gcp_project, gcp_location, structural_context, drawing_png, monkeypatch
    ):
        """run_planner passes image_path through to AgentProvider."""
        from cad_dxf_agent.core.semantic_model import build_planner_context
        from cad_dxf_agent.llm.planner import run_planner

        monkeypatch.setenv("CAD_LLM_PROVIDER", "agent")
        monkeypatch.setenv("CAD_GCP_PROJECT", gcp_project)
        monkeypatch.setenv("CAD_GCP_LOCATION", gcp_location)

        pc = build_planner_context(structural_context)
        changeset = run_planner(
            "Move a column mark east",
            pc,
            image_path=drawing_png,
        )
        assert changeset.op_count >= 1

    def test_vision_description_improves_context(
        self, gcp_project, drawing_png
    ):
        """Vision description is non-empty and contains structural terms."""
        from cad_dxf_agent.llm.vision_describer import describe_drawing

        description = describe_drawing(drawing_png)

        assert isinstance(description, str)
        assert len(description) > 50

        # At least some structural terms should appear
        desc_lower = description.lower()
        structural_terms = [
            "grid", "column", "line", "structural", "plan",
            "drawing", "foundation", "beam", "wall",
        ]
        matches = [t for t in structural_terms if t in desc_lower]
        assert len(matches) >= 1, (
            f"Description lacks structural terms: {description[:200]}"
        )
