"""Live test: PDF → convert → load → render → vision agent → validate → apply → save.

Exercises the complete user journey from uploading a PDF to producing an edited DXF.

Run with:
  CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/test_pdf_to_edit.py -v -m live_api -s
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from cad_dxf_agent.core.converter import convert_to_dxf
from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RuleConfig

logger = logging.getLogger(__name__)

TEST_PDFS = Path(__file__).resolve().parent.parent / "fixtures" / "test_pdfs"


def _render_to_png(dxf_path: Path, tmp_path: Path) -> Path | None:
    """Render DXF to PNG, return path or None if matplotlib unavailable."""
    try:
        from cad_dxf_agent.core.renderer import render_dxf_to_png

        result = render_dxf_to_png(dxf_path, tmp_path / "vision.png")
        if result.success:
            return result.output_path
    except ImportError:
        pass
    return None


@pytest.mark.live_api
class TestPdfToEditLive:
    """Full journey: PDF → convert → load → vision agent → validate → apply → save."""

    def test_structural_pdf_move(self, gcp_project, gcp_location, tmp_path):
        """Structural PDF → convert → vision agent move → save valid DXF."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        pdf_path = TEST_PDFS / "structural_plan.pdf"
        if not pdf_path.exists():
            pytest.skip("structural_plan.pdf not found in test fixtures")

        # 1. Convert PDF → working DXF
        conv = convert_to_dxf(pdf_path, output_dir=tmp_path)
        assert conv.success, f"PDF conversion failed: {conv.error}"
        logger.info("Converted %s → %s (%s)", pdf_path.name, conv.output_path, conv.source_format)

        # 2. Load into DrawingContext
        ctx = load_dxf(conv.output_path)
        assert ctx.entity_count > 0
        original_count = ctx.entity_count
        logger.info("Loaded %d entities from converted DXF", ctx.entity_count)

        # 3. Render to PNG for vision (optional but exercised)
        image_path = _render_to_png(conv.output_path, tmp_path)
        logger.info("Vision render: %s", image_path or "skipped (no matplotlib)")

        # 4. Build planner context + run agent WITH vision
        pc = build_planner_context(ctx)
        agent = AgentProvider(
            project=gcp_project,
            location=gcp_location,
            image_path=image_path,
        )
        changeset = agent.plan("Move the first line entity 10 units to the right", pc)

        assert changeset is not None
        assert changeset.planner_trace is not None
        logger.info(
            "Agent produced %d ops in %d turns",
            changeset.op_count,
            changeset.planner_trace.total_turns,
        )

        # 5. Validate
        result = validate_changeset(changeset, ctx, RuleConfig())
        logger.info("Validation: %d blockers, %d warnings", len(result.blockers), len(result.warnings))

        # 6. Apply & save (only if valid ops)
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "pdf_move_output.dxf"
            engine = EditEngine(conv.output_path)
            engine.apply_changeset(changeset)
            engine.save(out_path)
            assert out_path.exists()

            # 7. Round-trip verify
            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count == original_count  # move preserves count
            logger.info("Output DXF: %d entities (preserved)", out_ctx.entity_count)

    def test_foundation_pdf_edit_text(self, gcp_project, gcp_location, tmp_path):
        """Foundation PDF → convert → agent edit text → save valid DXF."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        pdf_path = TEST_PDFS / "foundation_detail.pdf"
        if not pdf_path.exists():
            pytest.skip("foundation_detail.pdf not found in test fixtures")

        # Convert
        conv = convert_to_dxf(pdf_path, output_dir=tmp_path)
        assert conv.success, f"PDF conversion failed: {conv.error}"

        # Load
        ctx = load_dxf(conv.output_path)
        assert ctx.entity_count > 0

        # Find text entities to confirm we have something to edit
        text_entities = [e for e in ctx.entities if e.entity_type in ("TEXT", "MTEXT")]
        logger.info("Found %d text entities in converted PDF", len(text_entities))

        # Vision render
        image_path = _render_to_png(conv.output_path, tmp_path)

        # Agent edit
        pc = build_planner_context(ctx)
        agent = AgentProvider(
            project=gcp_project,
            location=gcp_location,
            image_path=image_path,
        )

        if text_entities:
            prompt = f"Change the text '{text_entities[0].text_content}' to 'REVISED'"
        else:
            prompt = "Add a text note saying 'REVISED' near the center of the drawing"

        changeset = agent.plan(prompt, pc)
        assert changeset is not None
        assert changeset.planner_trace is not None

        # Validate & apply
        result = validate_changeset(changeset, ctx, RuleConfig())
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "pdf_edit_text_output.dxf"
            engine = EditEngine(conv.output_path)
            engine.apply_changeset(changeset)
            engine.save(out_path)
            assert out_path.exists()

            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count >= 1

    def test_simple_pdf_delete(self, gcp_project, gcp_location, tmp_path):
        """Simple PDF → convert → agent delete → save valid DXF with fewer entities."""
        from cad_dxf_agent.llm.agent_provider import AgentProvider

        pdf_path = TEST_PDFS / "simple_geometry.pdf"
        if not pdf_path.exists():
            pytest.skip("simple_geometry.pdf not found in test fixtures")

        # Convert
        conv = convert_to_dxf(pdf_path, output_dir=tmp_path)
        assert conv.success, f"PDF conversion failed: {conv.error}"

        # Load
        ctx = load_dxf(conv.output_path)
        assert ctx.entity_count > 0
        original_count = ctx.entity_count

        # Vision render
        image_path = _render_to_png(conv.output_path, tmp_path)

        # Agent delete
        pc = build_planner_context(ctx)
        agent = AgentProvider(
            project=gcp_project,
            location=gcp_location,
            image_path=image_path,
        )
        changeset = agent.plan("Delete the first line in the drawing", pc)

        assert changeset is not None
        assert changeset.planner_trace is not None

        # Validate & apply
        result = validate_changeset(changeset, ctx, RuleConfig())
        if not result.blockers and changeset.op_count > 0:
            out_path = tmp_path / "pdf_delete_output.dxf"
            engine = EditEngine(conv.output_path)
            engine.apply_changeset(changeset)
            engine.save(out_path)
            assert out_path.exists()

            out_ctx = load_dxf(out_path)
            assert out_ctx.entity_count <= original_count
            logger.info(
                "Delete: %d → %d entities", original_count, out_ctx.entity_count
            )
