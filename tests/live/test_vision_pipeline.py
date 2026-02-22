"""Live tests for the vision pipeline (describe_drawing) against real Vertex AI.

Tests that Gemini Flash can analyze a PNG render of a DXF drawing
and produce a meaningful text description.

Run with: make test-live  (or pytest tests/live/ -m live_api)
"""

from __future__ import annotations

import pytest


@pytest.mark.live_api
class TestVisionPipelineLive:
    """Vision describer produces meaningful descriptions from real Gemini."""

    @pytest.fixture
    def drawing_png(self, structural_drawing, tmp_path):
        """Render the structural drawing to PNG for vision tests."""
        try:
            from cad_dxf_agent.core.renderer import render_dxf_to_png

            png_path = tmp_path / "drawing.png"
            result = render_dxf_to_png(structural_drawing, png_path)
            if result.success:
                return png_path
        except ImportError:
            pass

        # Fallback: create a minimal PNG with pillow
        try:
            from PIL import Image

            img = Image.new("RGB", (800, 600), "white")
            png_path = tmp_path / "drawing.png"
            img.save(str(png_path))
            return png_path
        except ImportError:
            pytest.skip("Neither matplotlib nor Pillow available for PNG creation")

    def test_describe_drawing_returns_text(self, gcp_project, drawing_png):
        """describe_drawing returns a non-empty string description."""
        from cad_dxf_agent.llm.vision_describer import describe_drawing

        description = describe_drawing(drawing_png)

        assert isinstance(description, str)
        assert len(description) > 50, "Description too short to be meaningful"

    def test_description_mentions_structural_elements(self, gcp_project, drawing_png):
        """Description should reference drawing elements."""
        from cad_dxf_agent.llm.vision_describer import describe_drawing

        description = describe_drawing(drawing_png).lower()

        # At least some of these should appear in a structural drawing description
        structural_terms = ["grid", "column", "line", "structural", "plan", "drawing"]
        matches = [term for term in structural_terms if term in description]
        assert len(matches) >= 1, (
            f"Description doesn't mention any structural terms: {description[:200]}"
        )

    def test_vision_with_gemini_provider(
        self, gcp_project, gcp_location, planner_context, drawing_png
    ):
        """GeminiProvider with image_path produces valid ChangeSet."""
        from cad_dxf_agent.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(project=gcp_project, location=gcp_location)
        changeset = provider.plan(
            "Move a column mark 12 inches north",
            planner_context,
            image_path=drawing_png,
        )

        assert changeset is not None
        assert changeset.op_count >= 1
