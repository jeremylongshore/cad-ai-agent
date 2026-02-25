"""DXF factory — programmatic builders for realistic test drawings.

Builds reproducible drawings with ezdxf. No stored DXF files needed.
Mimics real structural engineering drawings with grids, columns,
dimension chains, notes, and title blocks.

DXF Zoo builders (create_dense_drawing, create_mixed_entity_drawing, etc.)
produce edge-case drawings for robustness testing.
"""

from __future__ import annotations

import math
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


# ---------------------------------------------------------------------------
# DXF Zoo builders — edge-case drawings for robustness testing
# ---------------------------------------------------------------------------


def create_dense_drawing(
    tmp_path: Path,
    *,
    count: int = 1000,
    filename: str = "dense_1000.dxf",
) -> Path:
    """Build a drawing with many entities to stress-test the entity index.

    Places `count` entities in a grid pattern across multiple layers.
    Mix of lines, text, lwpolylines, and block inserts.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    layers = ["LAYER_A", "LAYER_B", "LAYER_C", "STRUCTURAL", "NOTES"]
    for name in layers:
        doc.layers.add(name, color=1)

    block = doc.blocks.new("MARK")
    block.add_circle((0, 0), radius=1)

    cols = int(math.ceil(math.sqrt(count)))
    spacing = 5.0

    for i in range(count):
        col = i % cols
        row = i // cols
        x = col * spacing
        y = row * spacing
        layer = layers[i % len(layers)]
        kind = i % 4

        if kind == 0:
            msp.add_line((x, y), (x + 3, y + 3), dxfattribs={"layer": layer})
        elif kind == 1:
            msp.add_text(
                f"E{i}",
                dxfattribs={"layer": layer, "height": 1.0, "insert": (x, y)},
            )
        elif kind == 2:
            pts = [(x, y), (x + 2, y), (x + 2, y + 2), (x, y + 2)]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
        else:
            msp.add_blockref("MARK", insert=(x, y), dxfattribs={"layer": layer})

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_mixed_entity_drawing(
    tmp_path: Path,
    *,
    filename: str = "mixed_entities.dxf",
) -> Path:
    """Build a drawing with every supported entity type plus unsupported ones.

    Tests the reader's skip logic for unsupported types and ensures all
    supported V1+V2 types parse correctly.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("MIX", color=2)

    # V1 types
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "MIX"})
    msp.add_lwpolyline([(0, 5), (5, 5), (5, 10), (0, 10)], close=True, dxfattribs={"layer": "MIX"})
    msp.add_text("Sample Text", dxfattribs={"layer": "MIX", "height": 2, "insert": (15, 0)})
    msp.add_mtext(
        "Sample MText",
        dxfattribs={"layer": "MIX", "insert": (15, 10), "char_height": 2.0},
    )
    block = doc.blocks.new("TEST_BLOCK")
    block.add_circle((0, 0), radius=1)
    msp.add_blockref("TEST_BLOCK", insert=(30, 0), dxfattribs={"layer": "MIX"})

    # V2 types
    msp.add_circle((40, 0), radius=5, dxfattribs={"layer": "MIX"})
    msp.add_arc((50, 0), radius=5, start_angle=0, end_angle=180, dxfattribs={"layer": "MIX"})
    msp.add_ellipse(
        center=(60, 0),
        major_axis=(5, 0, 0),
        ratio=0.5,
        dxfattribs={"layer": "MIX"},
    )
    msp.add_spline(
        [(70, 0), (75, 10), (80, 0), (85, 10)],
        dxfattribs={"layer": "MIX"},
    )
    dim = msp.add_aligned_dim(p1=(0, -10), p2=(10, -10), distance=-3, dxfattribs={"layer": "MIX"})
    dim.render()

    # Unsupported types that should be skipped
    # POINT and 3DFACE are not in EntityType enum
    msp.add_point((90, 0), dxfattribs={"layer": "MIX"})
    # SOLID is supported (V2)
    msp.add_solid([(0, -20), (5, -20), (5, -15)], dxfattribs={"layer": "MIX"})

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_unicode_drawing(
    tmp_path: Path,
    *,
    filename: str = "unicode_labels.dxf",
) -> Path:
    """Build a drawing with CJK, accented, and special-character text labels.

    Tests encoding resilience in the reader and writer.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("LABELS", color=3)

    labels = [
        ("Column-A", (0, 0)),
        ("\u67f1A", (20, 0)),  # CJK: "柱A"
        ("\u67f1B \u69cb\u9020", (40, 0)),  # CJK: "柱B 構造"
        ("Sa\u0308ule-1", (60, 0)),  # German: "Säule-1"
        ("Columna-\u00d1", (80, 0)),  # Spanish: "Columna-Ñ"
        ("\u041a\u043e\u043b\u043e\u043d\u043d\u0430-1", (100, 0)),  # Russian: "Колонна-1"
        ("Col\u2014Special\u2019s", (120, 0)),  # Em-dash and curly quote
        ("Line\nBreak", (0, 20)),  # Embedded newline
    ]

    for text, pos in labels:
        msp.add_text(
            text,
            dxfattribs={"layer": "LABELS", "height": 2.0, "insert": pos},
        )
        msp.add_mtext(
            f"Note: {text}",
            dxfattribs={"layer": "LABELS", "insert": (pos[0], pos[1] + 5), "char_height": 1.5},
        )

    # Some structural context
    for i in range(len(labels)):
        x = i * 20
        msp.add_line((x, -5), (x, 30), dxfattribs={"layer": "LABELS"})

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_overlapping_drawing(
    tmp_path: Path,
    *,
    filename: str = "overlapping.dxf",
) -> Path:
    """Build a drawing with multiple entities at identical coordinates.

    Tests spatial disambiguation and nearest-entity queries.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("LAYER_1", color=1)
    doc.layers.add("LAYER_2", color=2)
    doc.layers.add("LAYER_3", color=3)

    # Multiple entities at exactly (10, 10)
    msp.add_line((10, 10), (20, 20), dxfattribs={"layer": "LAYER_1"})
    msp.add_text(
        "Overlap-A",
        dxfattribs={"layer": "LAYER_1", "height": 1.5, "insert": (10, 10)},
    )
    msp.add_text(
        "Overlap-B",
        dxfattribs={"layer": "LAYER_2", "height": 1.5, "insert": (10, 10)},
    )
    msp.add_lwpolyline(
        [(10, 10), (15, 10), (15, 15), (10, 15)],
        close=True,
        dxfattribs={"layer": "LAYER_3"},
    )

    # Cluster at (50, 50)
    for i in range(5):
        msp.add_text(
            f"Stack-{i}",
            dxfattribs={"layer": f"LAYER_{(i % 3) + 1}", "height": 1.0, "insert": (50, 50)},
        )

    # Entities at (0, 0) origin
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "LAYER_1"})
    msp.add_line((0, 0), (0, 5), dxfattribs={"layer": "LAYER_2"})
    msp.add_text(
        "Origin",
        dxfattribs={"layer": "LAYER_1", "height": 1.0, "insert": (0, 0)},
    )

    # Spread-out entities for contrast
    for i in range(4):
        x = 100 + i * 30
        msp.add_text(
            f"Far-{i}",
            dxfattribs={"layer": "LAYER_1", "height": 2.0, "insert": (x, 0)},
        )

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_empty_layers_drawing(
    tmp_path: Path,
    *,
    filename: str = "empty_layers.dxf",
) -> Path:
    """Build a drawing with several defined layers that have zero entities.

    Tests that empty layers don't confuse the planner context builder.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    # Many layers, most empty
    for name in ["STRUCTURAL", "NOTES", "ELECTRICAL", "PLUMBING", "MECHANICAL", "FIRE_PROT"]:
        doc.layers.add(name, color=1)

    # Only a few entities on STRUCTURAL
    msp.add_line((0, 0), (50, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_text(
        "Lonely",
        dxfattribs={"layer": "STRUCTURAL", "height": 2.0, "insert": (10, 10)},
    )

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


def create_drawing_with_layout(
    tmp_path: Path,
    *,
    layout_name: str = "Sheet1",
    filename: str = "with_layout.dxf",
) -> Path:
    """Create a DXF with entities in both model space and a named paper space layout.

    Model space gets:
    - 2 lines on STRUCTURAL
    - 1 text on NOTES ("Model Note")
    - 1 block insert (COLUMN_MARK) on STRUCTURAL

    Paper space layout gets:
    - 1 text on NOTES ("Layout Note")
    - 1 line on STRUCTURAL
    - 1 mtext on NOTES ("Layout Detail")

    Returns path to the saved DXF.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    # Layers
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("TITLE", color=7)

    # Block definition
    block = doc.blocks.new("COLUMN_MARK")
    block.add_circle((0, 0), radius=2)

    # --- Model space entities ---
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_line((0, 0), (0, 100), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_text(
        "Model Note",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (10, 10)},
    )
    msp.add_blockref("COLUMN_MARK", insert=(50, 50), dxfattribs={"layer": "STRUCTURAL"})

    # --- Paper space layout ---
    layout = doc.layouts.new(layout_name)
    layout.add_text(
        "Layout Note",
        dxfattribs={"layer": "NOTES", "height": 3.0, "insert": (5, 5)},
    )
    layout.add_line((0, 0), (200, 0), dxfattribs={"layer": "STRUCTURAL"})
    layout.add_mtext(
        "Layout Detail",
        dxfattribs={"layer": "NOTES", "insert": (20, 20), "char_height": 2.0},
    )

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path
