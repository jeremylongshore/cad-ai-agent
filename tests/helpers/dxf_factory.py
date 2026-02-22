"""DXF factory — programmatic builders for realistic test drawings.

Builds reproducible drawings with ezdxf. No stored DXF files needed.
Mimics real structural engineering drawings with grids, columns,
dimension chains, notes, and title blocks.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf


def create_structural_drawing(
    tmp_path: Path,
    *,
    grid_cols: int = 5,
    grid_rows: int = 4,
    grid_spacing: float = 30.0,
    add_title_block: bool = True,
    add_dimensions: bool = True,
    add_notes: bool = True,
    filename: str = "structural.dxf",
) -> Path:
    """Build a realistic structural drawing with 200+ entities.

    Generates:
    - Grid lines (STRUCTURAL layer)
    - Column marks as block inserts (STRUCTURAL layer)
    - Dimension chains (NOTES layer)
    - Text labels on columns (NOTES layer)
    - Title block text (TITLE layer, protected)
    - Revision text (REVISION layer, protected)

    Returns path to the saved DXF.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    # Layers
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("TITLE", color=7)
    doc.layers.add("TITLEBLOCK", color=7)
    doc.layers.add("SEAL", color=7)
    doc.layers.add("REVISION", color=7)

    # Block definition
    block = doc.blocks.new("COLUMN_MARK")
    block.add_circle((0, 0), radius=2)
    block.add_line((-1.5, -1.5), (1.5, 1.5))
    block.add_line((-1.5, 1.5), (1.5, -1.5))

    # Grid lines + column marks
    col_labels = [chr(65 + i) for i in range(grid_cols)]  # A, B, C, ...

    for col_idx in range(grid_cols):
        x = col_idx * grid_spacing
        # Vertical grid line
        msp.add_line(
            (x, 0),
            (x, (grid_rows - 1) * grid_spacing),
            dxfattribs={"layer": "STRUCTURAL"},
        )
        # Column label at top
        msp.add_text(
            col_labels[col_idx],
            dxfattribs={
                "layer": "NOTES",
                "height": 3.0,
                "insert": (x, (grid_rows - 1) * grid_spacing + 10),
            },
        )

    for row_idx in range(grid_rows):
        y = row_idx * grid_spacing
        # Horizontal grid line
        msp.add_line(
            (0, y),
            ((grid_cols - 1) * grid_spacing, y),
            dxfattribs={"layer": "STRUCTURAL"},
        )
        # Row label at left
        msp.add_text(
            str(row_idx + 1),
            dxfattribs={
                "layer": "NOTES",
                "height": 3.0,
                "insert": (-10, y),
            },
        )

    # Column marks at intersections
    for col_idx in range(grid_cols):
        for row_idx in range(grid_rows):
            x = col_idx * grid_spacing
            y = row_idx * grid_spacing
            label = f"{col_labels[col_idx]}-{row_idx + 1}"

            msp.add_blockref(
                "COLUMN_MARK",
                insert=(x, y),
                dxfattribs={"layer": "STRUCTURAL"},
            )
            msp.add_text(
                label,
                dxfattribs={
                    "layer": "NOTES",
                    "height": 1.5,
                    "insert": (x + 3, y + 3),
                },
            )

    # Dimension chains along bottom
    if add_dimensions:
        for col_idx in range(grid_cols - 1):
            x1 = col_idx * grid_spacing
            x2 = (col_idx + 1) * grid_spacing
            dim = msp.add_aligned_dim(
                p1=(x1, 0),
                p2=(x2, 0),
                distance=-8,
                dxfattribs={"layer": "NOTES"},
            )
            dim.render()

    # Extra notes
    if add_notes:
        msp.add_mtext(
            "FOOTING SCHEDULE\nSee detail A/S-3 for reinforcing",
            dxfattribs={
                "layer": "NOTES",
                "insert": (0, -25),
                "char_height": 2.0,
            },
        )
        msp.add_mtext(
            "ALL DIMENSIONS IN FEET-INCHES\nUNLESS OTHERWISE NOTED",
            dxfattribs={
                "layer": "NOTES",
                "insert": (60, -25),
                "char_height": 1.5,
            },
        )

    # Title block on protected layer
    if add_title_block:
        msp.add_text(
            "STRUCTURAL FOUNDATION PLAN",
            dxfattribs={"layer": "TITLE", "height": 5.0, "insert": (0, -50)},
        )
        msp.add_text(
            "PROJECT: DEMO BUILDING",
            dxfattribs={"layer": "TITLEBLOCK", "height": 3.0, "insert": (0, -58)},
        )
        msp.add_text(
            "SEAL: PE-12345",
            dxfattribs={"layer": "SEAL", "height": 2.0, "insert": (0, -65)},
        )
        msp.add_text(
            "REV 0 - ISSUED FOR CONSTRUCTION",
            dxfattribs={"layer": "REVISION", "height": 2.0, "insert": (0, -72)},
        )

    # Additional structural elements to push entity count up
    for i in range(8):
        pts = [
            (i * 15, -10),
            (i * 15 + 10, -10),
            (i * 15 + 10, -5),
            (i * 15, -5),
        ]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "STRUCTURAL"})

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_minimal_dxf(tmp_path: Path, *, filename: str = "minimal.dxf") -> Path:
    """Create a minimal DXF with just one entity for simple tests."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("STRUCTURAL", color=1)
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_empty_dxf(tmp_path: Path, *, filename: str = "empty.dxf") -> Path:
    """Create a DXF with no user entities (only standard DXF blocks)."""
    doc = ezdxf.new(dxfversion="R2018")
    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path
