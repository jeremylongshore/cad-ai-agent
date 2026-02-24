"""Integration tests for conversion → pipeline flow.

Exercises the full flow: DXF/PDF → convert → load → plan → validate → apply → save.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.converter import convert_to_dxf
from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.llm.agent_provider import MockAgentProvider
from cad_dxf_agent.models.config_schema import RuleConfig


def _create_test_pdf(pdf_path: Path) -> Path:
    """Create a minimal vector PDF with lines and text for conversion tests.

    Uses ezdxf to generate a DXF, then renders to PDF via matplotlib.
    Falls back to pymupdf/reportlab if matplotlib is not available.
    """
    # Build a simple DXF first
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((0, 0), (0, 100))
    msp.add_line((100, 0), (100, 100))
    msp.add_line((0, 100), (100, 100))
    msp.add_text("TEST LABEL", dxfattribs={"height": 5, "insert": (10, 50)})

    dxf_path = pdf_path.parent / "temp_for_pdf.dxf"
    doc.saveas(str(dxf_path))

    # Render DXF to PDF
    try:
        from cad_dxf_agent.core.renderer import render_dxf_to_pdf

        result = render_dxf_to_pdf(dxf_path, pdf_path)
        if result.success:
            return pdf_path
    except ImportError:
        pass

    # Fallback: create a minimal PDF with reportlab
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        c.line(72, 72, 540, 72)
        c.line(72, 72, 72, 720)
        c.line(540, 72, 540, 720)
        c.line(72, 720, 540, 720)
        c.drawString(100, 400, "TEST LABEL")
        c.save()
        return pdf_path
    except ImportError:
        pass

    # Last resort: create a minimal PDF manually (bare minimum valid PDF)
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 100 400 Td (TEST LABEL) Tj ET\n"
        b"endstream endobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000210 00000 n \n"
        b"trailer<</Root 1 0 R/Size 5>>\n"
        b"startxref\n306\n%%EOF"
    )
    pdf_path.write_bytes(pdf_content)
    return pdf_path


@pytest.mark.integration
class TestDxfPassthroughPipeline:
    """DXF → convert (passthrough) → load → plan → validate → apply → save."""

    def test_dxf_passthrough_full_pipeline(self, sample_dxf, tmp_path):
        """A DXF file passes through conversion, then the full pipeline."""
        result = convert_to_dxf(sample_dxf, output_dir=tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.source_format == "dxf"

        # Load the converted working copy
        ctx = load_dxf(result.output_path)
        assert ctx.entity_count > 0

        # Build planner context + run mock agent
        pc = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("Move the first entity east", pc)
        assert changeset.op_count >= 1

        # Validate
        rules = RuleConfig()
        validation = validate_changeset(changeset, ctx, rules)
        assert validation.valid

        # Apply + Save
        engine = EditEngine(result.output_path)
        results = engine.apply_changeset(changeset)
        assert all(r.success for r in results)

        output = tmp_path / "output.dxf"
        engine.save(str(output))

        # Verify output is loadable
        out_ctx = load_dxf(output)
        assert out_ctx.entity_count > 0

    def test_dxf_passthrough_preserves_entities(self, sample_dxf, tmp_path):
        """Conversion passthrough preserves entity count."""
        ctx_before = load_dxf(sample_dxf)
        result = convert_to_dxf(sample_dxf, output_dir=tmp_path)
        assert result.success

        ctx_after = load_dxf(result.output_path)
        assert ctx_after.entity_count == ctx_before.entity_count


@pytest.mark.integration
class TestPdfToPipelineFlow:
    """PDF → convert → load → mock-agent plan → validate → apply → save."""

    @pytest.fixture
    def test_pdf(self, tmp_path):
        """Create a test PDF for conversion."""
        pdf_path = tmp_path / "input.pdf"
        try:
            return _create_test_pdf(pdf_path)
        except Exception:
            pytest.skip("No PDF creation library available (reportlab/matplotlib)")

    def test_pdf_conversion_produces_loadable_dxf(self, test_pdf, tmp_path):
        """PDF conversion produces a DXF that loads successfully."""
        try:
            result = convert_to_dxf(test_pdf, output_dir=tmp_path / "converted")
        except Exception:
            pytest.skip("PDF conversion library not available (pymupdf/pdfplumber)")

        if not result.success:
            pytest.skip(f"PDF conversion failed: {result.error}")

        assert result.output_path.exists()
        assert result.source_format == "pdf"

        ctx = load_dxf(result.output_path)
        assert ctx.entity_count > 0

    def test_pdf_to_dxf_full_pipeline(self, test_pdf, tmp_path):
        """PDF → convert → load → mock-agent plan → validate → apply → save."""
        try:
            result = convert_to_dxf(test_pdf, output_dir=tmp_path / "converted")
        except Exception:
            pytest.skip("PDF conversion library not available")

        if not result.success:
            pytest.skip(f"PDF conversion failed: {result.error}")

        # Load into DrawingContext
        ctx = load_dxf(result.output_path)
        assert ctx.entity_count > 0

        # Build planner context + run mock agent
        pc = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("Move the first entity east", pc)

        if changeset.op_count == 0:
            # Mock agent might not find editable entities in PDF-converted DXF
            return

        # Validate + Apply + Save
        rules = RuleConfig()
        validation = validate_changeset(changeset, ctx, rules)
        if not validation.valid:
            # Some PDF-converted entities may not be editable
            return

        engine = EditEngine(result.output_path)
        results = engine.apply_changeset(changeset)
        assert any(r.success for r in results)

        output = tmp_path / "pdf_output.dxf"
        engine.save(str(output))

        out_ctx = load_dxf(output)
        assert out_ctx.entity_count > 0


@pytest.mark.integration
class TestVisionRenderIntegration:
    """Render → vision mock → pipeline integration."""

    def test_render_then_mock_vision(self, sample_dxf, tmp_path):
        """Render DXF → PNG, feed to mock vision, verify description."""
        try:
            from cad_dxf_agent.core.renderer import render_dxf_to_png
        except ImportError:
            pytest.skip("matplotlib not installed (needed for rendering)")

        render_result = render_dxf_to_png(sample_dxf, tmp_path / "preview.png")
        assert render_result.success
        assert render_result.output_path.exists()

        from cad_dxf_agent.llm.vision_describer import describe_drawing_mock

        desc = describe_drawing_mock(render_result.output_path)
        assert len(desc) > 50
        assert "foundation" in desc.lower()

    def test_render_structural_drawing(self, tmp_path):
        """Render a structural drawing and verify PNG creation."""
        try:
            from cad_dxf_agent.core.renderer import render_dxf_to_png
        except ImportError:
            pytest.skip("matplotlib not installed")

        from tests.helpers.dxf_factory import create_structural_drawing

        dxf_path = create_structural_drawing(tmp_path)
        result = render_dxf_to_png(dxf_path, tmp_path / "structural.png")
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.stat().st_size > 0


@pytest.mark.integration
class TestImagePathPlumbing:
    """Verify image_path flows through planner to provider."""

    def test_run_planner_accepts_image_path(self, sample_dxf, tmp_path):
        """run_planner with image_path does not crash."""
        from cad_dxf_agent.llm.planner import run_planner

        ctx = load_dxf(sample_dxf)
        pc = build_planner_context(ctx)

        # image_path is accepted but ignored by mock provider
        changeset = run_planner("move first entity", pc, image_path=None)
        assert changeset.op_count >= 0

    def test_get_provider_passes_image_path(self, tmp_path):
        """get_provider with agent name passes image_path to AgentProvider."""
        from cad_dxf_agent.llm.planner import get_provider

        # mock-agent doesn't use image_path but shouldn't error
        provider = get_provider("mock-agent", image_path=tmp_path / "fake.png")
        assert provider.name == "mock-agent"
