"""Tests for actionable load-time warnings."""

from __future__ import annotations

from pathlib import Path

from cad_dxf_agent.core.dxf_reader import load_dxf
from tests.helpers.dxf_factory import (
    create_empty_dxf,
    create_minimal_dxf,
    create_structural_drawing,
)


class TestLoadWarnings:
    def test_empty_drawing_produces_error_warning(self, tmp_path: Path):
        """Empty DXF should produce EMPTY_DRAWING error-level warning."""
        dxf_path = create_empty_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        assert len(ctx.load_warnings) >= 1
        codes = [w.code for w in ctx.load_warnings]
        assert "EMPTY_DRAWING" in codes
        empty_w = next(w for w in ctx.load_warnings if w.code == "EMPTY_DRAWING")
        assert empty_w.severity == "error"

    def test_normal_drawing_no_error_warnings(self, tmp_path: Path):
        """Normal structural drawing should not have error-level warnings."""
        dxf_path = create_structural_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        error_warnings = [w for w in ctx.load_warnings if w.severity == "error"]
        assert len(error_warnings) == 0

    def test_all_protected_warning(self, tmp_path: Path):
        """Drawing with all entities on protected layers gets ALL_PROTECTED warning."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("TITLE", color=7)
        msp.add_text("Title", dxfattribs={"layer": "TITLE", "height": 3.0, "insert": (0, 0)})
        dxf_path = tmp_path / "all_protected.dxf"
        doc.saveas(str(dxf_path))

        ctx = load_dxf(dxf_path)
        codes = [w.code for w in ctx.load_warnings]
        assert "ALL_PROTECTED" in codes
        prot_w = next(w for w in ctx.load_warnings if w.code == "ALL_PROTECTED")
        assert prot_w.severity == "warning"

    def test_unsupported_types_warning(self, tmp_path: Path):
        """DXF with unsupported entity types should produce UNSUPPORTED_TYPES warning."""
        import ezdxf

        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        # Add a supported entity
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
        # Add a 3DFACE entity (unsupported)
        msp.add_3dface(
            [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)],
            dxfattribs={"layer": "STRUCTURAL"},
        )
        dxf_path = tmp_path / "mixed_types.dxf"
        doc.saveas(str(dxf_path))

        ctx = load_dxf(dxf_path)
        codes = [w.code for w in ctx.load_warnings]
        assert "UNSUPPORTED_TYPES" in codes
        unsup_w = next(w for w in ctx.load_warnings if w.code == "UNSUPPORTED_TYPES")
        assert unsup_w.severity == "info"
        assert "3DFACE" in unsup_w.message

    def test_minimal_drawing_no_warnings(self, tmp_path: Path):
        """Minimal drawing with one line should produce no warnings."""
        dxf_path = create_minimal_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        # Should have 0 or minimal warnings (no error/warning level)
        serious = [w for w in ctx.load_warnings if w.severity in ("error", "warning")]
        assert len(serious) == 0

    def test_warnings_stored_on_context(self, tmp_path: Path):
        """Load warnings should be stored on DrawingContext.load_warnings."""
        dxf_path = create_empty_dxf(tmp_path)
        ctx = load_dxf(dxf_path)
        assert hasattr(ctx, "load_warnings")
        assert isinstance(ctx.load_warnings, list)
