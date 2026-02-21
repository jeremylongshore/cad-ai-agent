"""Shared test fixtures for cad-dxf-agent tests."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest


@pytest.fixture
def sample_dxf(tmp_path: Path) -> Path:
    """Create a minimal sample DXF file with V1-supported entity types."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    # Add layers
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("TITLE", color=7)  # Protected
    doc.layers.add("TITLEBLOCK", color=7)  # Protected
    doc.layers.add("SEAL", color=7)  # Protected
    doc.layers.add("REVISION", color=7)  # Protected

    # LINE on STRUCTURAL
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "STRUCTURAL"})

    # LWPOLYLINE on STRUCTURAL
    msp.add_lwpolyline(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )

    # TEXT on NOTES
    msp.add_text(
        "Column C-4",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (10, 10)},
    )

    # MTEXT on NOTES
    msp.add_mtext(
        "Footing detail note",
        dxfattribs={"layer": "NOTES", "insert": (20, 20), "char_height": 2.0},
    )

    # TEXT on protected layer (should be blocked from editing)
    msp.add_text(
        "PROJECT TITLE",
        dxfattribs={"layer": "TITLE", "height": 5.0, "insert": (0, -20)},
    )

    # Simple block definition + INSERT
    block = doc.blocks.new("COLUMN_MARK")
    block.add_circle((0, 0), radius=2)
    msp.add_blockref("COLUMN_MARK", insert=(25, 25), dxfattribs={"layer": "STRUCTURAL"})

    # V2 entity types
    msp.add_circle((60, 60), radius=5, dxfattribs={"layer": "STRUCTURAL"})
    msp.add_arc(
        (80, 80), radius=10, start_angle=0, end_angle=90, dxfattribs={"layer": "STRUCTURAL"}
    )
    dim = msp.add_aligned_dim(p1=(0, 0), p2=(100, 0), distance=5, dxfattribs={"layer": "NOTES"})
    dim.render()  # Generate dimension geometry block for renderer

    dxf_path = tmp_path / "sample.dxf"
    doc.saveas(str(dxf_path))
    return dxf_path


@pytest.fixture
def sample_context(sample_dxf):
    """Load the sample DXF into a DrawingContext."""
    from cad_dxf_agent.core.dxf_reader import load_dxf

    return load_dxf(sample_dxf)


@pytest.fixture
def rule_config():
    """Default rule configuration for tests."""
    from cad_dxf_agent.models.config_schema import RuleConfig

    return RuleConfig()
