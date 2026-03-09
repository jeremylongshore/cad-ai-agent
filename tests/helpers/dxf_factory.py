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


def create_scaled_insert_drawing(
    tmp_path: Path,
    *,
    filename: str = "scaled_inserts.dxf",
) -> Path:
    """Build a drawing with INSERT entities at different scales and rotations.

    Block "LABELED_MARK" has an ATTDEF (tag=LABEL, height=2.0).
    Three INSERTs:
    - Default scale (1, 1, 0°)
    - xscale=2, yscale=0.5
    - rotation=30°
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("MARKS", color=1)

    # Block with ATTDEF
    block = doc.blocks.new("LABELED_MARK")
    block.add_circle((0, 0), radius=3)
    block.add_attdef("LABEL", (0, -5), dxfattribs={"height": 2.0})

    # INSERT 1: default scale
    ref1 = msp.add_blockref("LABELED_MARK", insert=(10, 10), dxfattribs={"layer": "MARKS"})
    ref1.add_auto_attribs({"LABEL": "MARK-A"})

    # INSERT 2: non-uniform scale
    ref2 = msp.add_blockref(
        "LABELED_MARK",
        insert=(50, 10),
        dxfattribs={"layer": "MARKS", "xscale": 2.0, "yscale": 0.5},
    )
    ref2.add_auto_attribs({"LABEL": "MARK-B"})

    # INSERT 3: rotated
    ref3 = msp.add_blockref(
        "LABELED_MARK",
        insert=(90, 10),
        dxfattribs={"layer": "MARKS", "rotation": 30.0},
    )
    ref3.add_auto_attribs({"LABEL": "MARK-C"})

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_rich_mtext_drawing(
    tmp_path: Path,
    *,
    filename: str = "rich_mtext.dxf",
) -> Path:
    """Build a drawing with MTEXT containing formatting codes.

    - MTEXT with paragraph breaks (\\n input becomes \\P in DXF)
    - MTEXT with explicit column width
    - Simple MTEXT without formatting
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("NOTES", color=3)

    # MTEXT with formatting — ezdxf converts \n to \P internally
    msp.add_mtext(
        "Line one\nLine two\nLine three",
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, 0),
            "char_height": 2.5,
        },
    )

    # MTEXT with explicit width
    msp.add_mtext(
        "Constrained width text that should wrap",
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, 30),
            "char_height": 2.0,
            "width": 40.0,
        },
    )

    # Simple MTEXT
    msp.add_mtext(
        "SIMPLE NOTE",
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, 60),
            "char_height": 3.0,
        },
    )

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_residential_drawing(
    tmp_path: Path,
    *,
    filename: str = "residential.dxf",
) -> Path:
    """Build a realistic residential floor plan with ~80-120 entities.

    Simulates a single-unit floor plan for compliance, zone detection,
    and RFI testing.

    Generates:
    - Outer walls as closed LWPOLYLINE on WALLS layer (60x40 footprint)
    - Interior partition walls as LINEs on WALLS layer (4-5 rooms)
    - Door swings as INSERTs (DOOR_SWING block: arc + line) on DOORS layer
    - Window blocks (WINDOW: rectangle) as INSERTs on WINDOWS layer
    - Room labels as TEXT on ROOMS layer
    - Simple furniture blocks as INSERTs on FURNITURE layer
    - Electrical outlet circles on ELECTRICAL layer
    - Title block text on TITLE layer (protected)

    Returns path to the saved DXF.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    # Layers
    doc.layers.add("WALLS", color=1)
    doc.layers.add("DOORS", color=2)
    doc.layers.add("WINDOWS", color=4)
    doc.layers.add("ROOMS", color=3)
    doc.layers.add("FURNITURE", color=5)
    doc.layers.add("ELECTRICAL", color=6)
    doc.layers.add("PLUMBING", color=4)
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("TITLE", color=7)
    doc.layers.add("TITLEBLOCK", color=7)

    # --- Block: DOOR_SWING (arc sweep + threshold line) ---
    door_block = doc.blocks.new("DOOR_SWING")
    door_block.add_arc((0, 0), radius=8, start_angle=0, end_angle=90)
    door_block.add_line((0, 0), (8, 0))

    # --- Block: WINDOW (glazing rectangle with centre line) ---
    win_block = doc.blocks.new("WINDOW")
    win_block.add_lwpolyline([(-6, -1), (6, -1), (6, 1), (-6, 1)], close=True)
    win_block.add_line((-6, 0), (6, 0))

    # --- Block: BED (simple rectangle with headboard line) ---
    bed_block = doc.blocks.new("BED")
    bed_block.add_lwpolyline([(-8, -5), (8, -5), (8, 5), (-8, 5)], close=True)
    bed_block.add_line((-8, 2), (8, 2))

    # --- Block: TABLE ---
    table_block = doc.blocks.new("TABLE")
    table_block.add_lwpolyline([(-5, -3), (5, -3), (5, 3), (-5, 3)], close=True)

    # --- Block: TOILET ---
    toilet_block = doc.blocks.new("TOILET")
    toilet_block.add_lwpolyline([(-3, -4), (3, -4), (3, 2), (-3, 2)], close=True)
    toilet_block.add_arc((0, 2), radius=3, start_angle=0, end_angle=180)

    # --- Outer walls: 60x40 rectangle ---
    msp.add_lwpolyline(
        [(0, 0), (60, 0), (60, 40), (0, 40)],
        close=True,
        dxfattribs={"layer": "WALLS"},
    )

    # --- Interior walls creating 5 rooms ---
    # Vertical wall x=20 splits left zone from middle
    msp.add_line((20, 0), (20, 40), dxfattribs={"layer": "WALLS"})
    # Vertical wall x=40 creates right third
    msp.add_line((40, 0), (40, 40), dxfattribs={"layer": "WALLS"})
    # Horizontal wall y=20 in left zone: bedroom 1 above, living room below
    msp.add_line((0, 20), (20, 20), dxfattribs={"layer": "WALLS"})
    # Horizontal wall y=20 in middle zone: kitchen above, hallway below
    msp.add_line((20, 20), (40, 20), dxfattribs={"layer": "WALLS"})
    # Horizontal wall y=25 in right zone: bathroom above, bedroom 2 below
    msp.add_line((40, 25), (60, 25), dxfattribs={"layer": "WALLS"})

    # --- Door inserts at room entrances ---
    door_positions = [
        (20, 8),  # living room → hallway
        (20, 30),  # bedroom 1 → hallway
        (40, 12),  # hallway → kitchen
        (40, 32),  # hallway → bathroom
        (50, 25),  # bedroom 2 entrance
        (10, 40),  # front entry
    ]
    for pos in door_positions:
        msp.add_blockref(
            "DOOR_SWING",
            insert=pos,
            dxfattribs={"layer": "DOORS"},
        )

    # --- Window inserts on exterior walls ---
    window_positions = [
        # Bottom wall
        ((10, 0), 0.0),
        ((30, 0), 0.0),
        ((50, 0), 0.0),
        # Top wall
        ((10, 40), 0.0),
        ((50, 40), 0.0),
        # Left wall
        ((0, 10), 90.0),
        ((0, 30), 90.0),
        # Right wall
        ((60, 10), 90.0),
        ((60, 35), 90.0),
    ]
    for pos, rot in window_positions:
        msp.add_blockref(
            "WINDOW",
            insert=pos,
            dxfattribs={"layer": "WINDOWS", "rotation": rot},
        )

    # --- Room labels ---
    room_labels = [
        ("LIVING ROOM", (7, 8)),
        ("BEDROOM 1", (7, 28)),
        ("KITCHEN", (27, 28)),
        ("HALLWAY", (27, 8)),
        ("BATHROOM", (47, 30)),
        ("BEDROOM 2", (47, 10)),
    ]
    for label, pos in room_labels:
        msp.add_text(
            label,
            dxfattribs={"layer": "ROOMS", "height": 2.0, "insert": pos},
        )

    # --- Furniture block inserts ---
    furniture_inserts = [
        ("BED", (10, 31)),  # bedroom 1
        ("BED", (50, 5)),  # bedroom 2
        ("TABLE", (28, 10)),  # kitchen/dining
        ("TOILET", (53, 37)),  # bathroom
    ]
    for block_name, pos in furniture_inserts:
        msp.add_blockref(
            block_name,
            insert=pos,
            dxfattribs={"layer": "FURNITURE"},
        )

    # --- Electrical outlets as circles ---
    outlet_positions = [
        (5, 2),
        (15, 2),
        (25, 2),
        (45, 2),
        (55, 2),
        (5, 38),
        (30, 38),
        (55, 38),
        (2, 10),
        (2, 25),
        (58, 15),
        (58, 32),
    ]
    for pos in outlet_positions:
        msp.add_circle(pos, radius=0.8, dxfattribs={"layer": "ELECTRICAL"})

    # --- Plumbing note ---
    msp.add_mtext(
        "PLUMBING ROUGH-IN\nSee plumbing drawings",
        dxfattribs={
            "layer": "PLUMBING",
            "insert": (42, 27),
            "char_height": 1.5,
        },
    )

    # --- Structural corner column marks ---
    for cx, cy in [
        (0, 0),
        (20, 0),
        (40, 0),
        (60, 0),
        (0, 40),
        (20, 40),
        (40, 40),
        (60, 40),
    ]:
        msp.add_circle((cx, cy), radius=1.5, dxfattribs={"layer": "STRUCTURAL"})

    # --- Extra wall segments (closet walls, chase walls) ---
    # Closet in bedroom 1 (left zone, upper)
    msp.add_line((0, 33), (8, 33), dxfattribs={"layer": "WALLS"})
    msp.add_line((8, 33), (8, 40), dxfattribs={"layer": "WALLS"})
    # Closet in bedroom 2 (right zone, lower)
    msp.add_line((40, 18), (50, 18), dxfattribs={"layer": "WALLS"})
    msp.add_line((50, 18), (50, 25), dxfattribs={"layer": "WALLS"})
    # Hallway niche (middle zone)
    msp.add_line((30, 0), (30, 8), dxfattribs={"layer": "WALLS"})
    msp.add_line((30, 8), (40, 8), dxfattribs={"layer": "WALLS"})

    # --- Extra window and door for closets/utility ---
    msp.add_blockref(
        "DOOR_SWING",
        insert=(4, 33),
        dxfattribs={"layer": "DOORS"},
    )
    msp.add_blockref(
        "DOOR_SWING",
        insert=(45, 18),
        dxfattribs={"layer": "DOORS"},
    )
    msp.add_blockref(
        "WINDOW",
        insert=(30, 40),
        dxfattribs={"layer": "WINDOWS", "rotation": 0.0},
    )

    # --- Room area annotations ---
    area_labels = [
        ("~ 120 SF", (7, 4)),
        ("~ 95 SF", (7, 23)),
        ("~ 90 SF", (27, 23)),
        ("~ 60 SF", (27, 4)),
        ("~ 55 SF", (47, 35)),
        ("~ 100 SF", (47, 5)),
    ]
    for label, pos in area_labels:
        msp.add_text(
            label,
            dxfattribs={"layer": "ROOMS", "height": 1.5, "insert": pos},
        )

    # --- Additional electrical circuits ---
    for pos in [(10, 20), (30, 20), (50, 20), (10, 0), (50, 0)]:
        msp.add_circle(pos, radius=0.8, dxfattribs={"layer": "ELECTRICAL"})

    # --- Dimension lines along outer perimeter ---
    dim_h = msp.add_aligned_dim(
        p1=(0, 0),
        p2=(60, 0),
        distance=-8,
        dxfattribs={"layer": "NOTES"},
    )
    dim_h.render()
    dim_v = msp.add_aligned_dim(
        p1=(0, 0),
        p2=(0, 40),
        distance=-8,
        dxfattribs={"layer": "NOTES"},
    )
    dim_v.render()

    # --- General notes ---
    msp.add_mtext(
        'ALL WALLS 2x4 STUD @ 16" O.C.\nU.N.O.',
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, -10),
            "char_height": 1.5,
        },
    )
    msp.add_mtext(
        "PROVIDE BLOCKING AT ALL\nWALL-MOUNTED FIXTURES",
        dxfattribs={
            "layer": "NOTES",
            "insert": (30, -10),
            "char_height": 1.5,
        },
    )
    msp.add_mtext(
        "GFA: ~520 SF\nOCCUPANCY: R-2",
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, -18),
            "char_height": 1.5,
        },
    )

    # --- Title block on protected layers ---
    msp.add_text(
        "RESIDENTIAL FLOOR PLAN",
        dxfattribs={"layer": "TITLE", "height": 5.0, "insert": (0, -28)},
    )
    msp.add_text(
        "PROJECT: UNIT 101 - SAMPLE RESIDENCE",
        dxfattribs={"layer": "TITLEBLOCK", "height": 3.0, "insert": (0, -36)},
    )
    msp.add_text(
        'SCALE: 1/4" = 1\'-0"',
        dxfattribs={"layer": "TITLEBLOCK", "height": 2.0, "insert": (0, -42)},
    )
    msp.add_text(
        "DRAWN BY: AI",
        dxfattribs={"layer": "TITLEBLOCK", "height": 2.0, "insert": (0, -47)},
    )

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path


def create_electrical_drawing(
    tmp_path: Path,
    *,
    filename: str = "electrical.dxf",
) -> Path:
    """Build a realistic electrical plan with ~60-100 entities.

    Simulates an MEP electrical plan for jargon, circuit, and panel testing.

    Generates:
    - Background reference grid as LINEs on STRUCTURAL layer (4x3 grid)
    - Panel schedule rectangles + labels on PANELS layer (PANEL-A, PANEL-B)
    - Circuit home-run lines on CIRCUITS layer connecting outlets to panels
    - Outlet symbols (OUTLET_SYMBOL block) as INSERTs on ELECTRICAL layer
    - Switch symbols (SWITCH_SYMBOL block) as INSERTs on ELECTRICAL layer
    - Light fixture symbols (LIGHT_FIXTURE block) as INSERTs on ELECTRICAL layer
    - Circuit annotation TEXT on NOTES layer
    - Title block text on TITLE layer (protected)

    Returns path to the saved DXF.
    """
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()

    # Layers
    doc.layers.add("ELECTRICAL", color=2)
    doc.layers.add("PANELS", color=1)
    doc.layers.add("CIRCUITS", color=5)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("STRUCTURAL", color=8)
    doc.layers.add("TITLE", color=7)

    # --- Block: OUTLET_SYMBOL (circle with vertical tick) ---
    outlet_block = doc.blocks.new("OUTLET_SYMBOL")
    outlet_block.add_circle((0, 0), radius=1.2)
    outlet_block.add_line((0, 0), (0, 2.5))

    # --- Block: SWITCH_SYMBOL (small diamond with leader) ---
    switch_block = doc.blocks.new("SWITCH_SYMBOL")
    switch_block.add_lwpolyline([(0, 1.5), (1.5, 0), (0, -1.5), (-1.5, 0)], close=True)
    switch_block.add_line((0, 1.5), (0, 3.5))

    # --- Block: LIGHT_FIXTURE (circle with crosshair) ---
    fixture_block = doc.blocks.new("LIGHT_FIXTURE")
    fixture_block.add_circle((0, 0), radius=2.5)
    fixture_block.add_line((-2.5, 0), (2.5, 0))
    fixture_block.add_line((0, -2.5), (0, 2.5))

    # --- Reference grid: 4 columns x 3 rows at 20-unit spacing ---
    grid_cols = 4
    grid_rows = 3
    grid_spacing = 20.0

    for col in range(grid_cols + 1):
        x = col * grid_spacing
        msp.add_line(
            (x, 0),
            (x, grid_rows * grid_spacing),
            dxfattribs={"layer": "STRUCTURAL"},
        )
    for row in range(grid_rows + 1):
        y = row * grid_spacing
        msp.add_line(
            (0, y),
            (grid_cols * grid_spacing, y),
            dxfattribs={"layer": "STRUCTURAL"},
        )

    # --- Panel schedule: PANEL-A (lower-left) ---
    panel_a_origin = (2, 2)
    msp.add_lwpolyline(
        [
            (panel_a_origin[0], panel_a_origin[1]),
            (panel_a_origin[0] + 14, panel_a_origin[1]),
            (panel_a_origin[0] + 14, panel_a_origin[1] + 8),
            (panel_a_origin[0], panel_a_origin[1] + 8),
        ],
        close=True,
        dxfattribs={"layer": "PANELS"},
    )
    msp.add_text(
        "PANEL-A",
        dxfattribs={
            "layer": "PANELS",
            "height": 2.0,
            "insert": (panel_a_origin[0] + 1, panel_a_origin[1] + 5),
        },
    )
    msp.add_text(
        "200A / 120/240V",
        dxfattribs={
            "layer": "PANELS",
            "height": 1.5,
            "insert": (panel_a_origin[0] + 1, panel_a_origin[1] + 2),
        },
    )

    # --- Panel schedule: PANEL-B (upper-right) ---
    panel_b_origin = (65, 52)
    msp.add_lwpolyline(
        [
            (panel_b_origin[0], panel_b_origin[1]),
            (panel_b_origin[0] + 14, panel_b_origin[1]),
            (panel_b_origin[0] + 14, panel_b_origin[1] + 8),
            (panel_b_origin[0], panel_b_origin[1] + 8),
        ],
        close=True,
        dxfattribs={"layer": "PANELS"},
    )
    msp.add_text(
        "PANEL-B",
        dxfattribs={
            "layer": "PANELS",
            "height": 2.0,
            "insert": (panel_b_origin[0] + 1, panel_b_origin[1] + 5),
        },
    )
    msp.add_text(
        "100A / 277/480V",
        dxfattribs={
            "layer": "PANELS",
            "height": 1.5,
            "insert": (panel_b_origin[0] + 1, panel_b_origin[1] + 2),
        },
    )

    # --- Outlet inserts (12 duplex outlets) ---
    outlet_positions = [
        (18, 5),
        (38, 5),
        (58, 5),
        (18, 25),
        (38, 25),
        (58, 25),
        (18, 45),
        (38, 45),
        (58, 45),
        (8, 15),
        (28, 35),
        (48, 55),
    ]
    for pos in outlet_positions:
        msp.add_blockref(
            "OUTLET_SYMBOL",
            insert=pos,
            dxfattribs={"layer": "ELECTRICAL"},
        )

    # --- Switch inserts (6 switches) ---
    switch_positions = [
        (22, 8),
        (42, 8),
        (22, 28),
        (42, 28),
        (22, 48),
        (42, 48),
    ]
    for pos in switch_positions:
        msp.add_blockref(
            "SWITCH_SYMBOL",
            insert=pos,
            dxfattribs={"layer": "ELECTRICAL"},
        )

    # --- Light fixture inserts (9 fixtures) ---
    fixture_positions = [
        (10, 10),
        (30, 10),
        (50, 10),
        (70, 10),
        (10, 30),
        (30, 30),
        (50, 30),
        (10, 50),
        (30, 50),
    ]
    for pos in fixture_positions:
        msp.add_blockref(
            "LIGHT_FIXTURE",
            insert=pos,
            dxfattribs={"layer": "ELECTRICAL"},
        )

    # --- Circuit home runs to panels ---
    panel_a_tap = (9, 6)
    panel_b_tap = (65, 55)

    circuit_runs = [
        # Circuits back to PANEL-A
        (18, 5, panel_a_tap[0], panel_a_tap[1]),
        (38, 5, panel_a_tap[0], panel_a_tap[1]),
        (18, 25, panel_a_tap[0], panel_a_tap[1]),
        (8, 15, panel_a_tap[0], panel_a_tap[1]),
        # Circuits back to PANEL-B
        (58, 45, panel_b_tap[0], panel_b_tap[1]),
        (38, 45, panel_b_tap[0], panel_b_tap[1]),
        (48, 55, panel_b_tap[0], panel_b_tap[1]),
    ]
    for x1, y1, x2, y2 in circuit_runs:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "CIRCUITS"})

    # --- Circuit annotation notes ---
    circuit_notes = [
        ("20A CIRCUIT", (20, 3)),
        ("GFCI", (58, 3)),
        ("DEDICATED CIRCUIT", (58, 23)),
        ("277V LIGHTING", (68, 28)),
        ("EMERGENCY CIRCUIT", (8, 52)),
        ("SPARE", (28, 52)),
    ]
    for note_text, pos in circuit_notes:
        msp.add_text(
            note_text,
            dxfattribs={"layer": "NOTES", "height": 1.5, "insert": pos},
        )

    # --- Legend box + text entries ---
    legend_origin = (0, 68)
    msp.add_lwpolyline(
        [
            (legend_origin[0], legend_origin[1]),
            (legend_origin[0] + 35, legend_origin[1]),
            (legend_origin[0] + 35, legend_origin[1] + 22),
            (legend_origin[0], legend_origin[1] + 22),
        ],
        close=True,
        dxfattribs={"layer": "NOTES"},
    )
    legend_entries = [
        ("DUPLEX OUTLET", (legend_origin[0] + 2, legend_origin[1] + 17)),
        ("SWITCH", (legend_origin[0] + 2, legend_origin[1] + 13)),
        ("LIGHT FIXTURE", (legend_origin[0] + 2, legend_origin[1] + 9)),
        ("HOME RUN TO PANEL", (legend_origin[0] + 2, legend_origin[1] + 5)),
        ("LEGEND", (legend_origin[0] + 12, legend_origin[1] + 19)),
    ]
    for entry_text, pos in legend_entries:
        msp.add_text(
            entry_text,
            dxfattribs={"layer": "NOTES", "height": 1.5, "insert": pos},
        )

    # --- Dimension lines along grid perimeter ---
    dim_h = msp.add_aligned_dim(
        p1=(0, 0),
        p2=(grid_cols * grid_spacing, 0),
        distance=-8,
        dxfattribs={"layer": "NOTES"},
    )
    dim_h.render()
    dim_v = msp.add_aligned_dim(
        p1=(0, 0),
        p2=(0, grid_rows * grid_spacing),
        distance=-8,
        dxfattribs={"layer": "NOTES"},
    )
    dim_v.render()

    # --- Column / row grid labels ---
    col_labels = ["A", "B", "C", "D"]
    for i, lbl in enumerate(col_labels):
        msp.add_text(
            lbl,
            dxfattribs={
                "layer": "STRUCTURAL",
                "height": 2.5,
                "insert": (i * grid_spacing + grid_spacing / 2 - 1, -6),
            },
        )
    for row in range(grid_rows):
        msp.add_text(
            str(row + 1),
            dxfattribs={
                "layer": "STRUCTURAL",
                "height": 2.5,
                "insert": (-6, row * grid_spacing + grid_spacing / 2 - 1),
            },
        )

    # --- General notes ---
    msp.add_mtext(
        "ALL WIRING IN EMT CONDUIT\nU.N.O.",
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, -8),
            "char_height": 1.5,
        },
    )
    msp.add_mtext(
        "COORDINATE ROUTING WITH\nMECHANICAL CONTRACTOR",
        dxfattribs={
            "layer": "NOTES",
            "insert": (40, -8),
            "char_height": 1.5,
        },
    )
    msp.add_mtext(
        "VERIFY PANEL LOCATIONS\nIN FIELD PRIOR TO ROUGH-IN",
        dxfattribs={
            "layer": "NOTES",
            "insert": (0, -16),
            "char_height": 1.5,
        },
    )

    # --- Title block on protected TITLE layer ---
    msp.add_text(
        "ELECTRICAL POWER PLAN",
        dxfattribs={"layer": "TITLE", "height": 5.0, "insert": (0, -26)},
    )
    msp.add_text(
        "PROJECT: SAMPLE BUILDING - LEVEL 1",
        dxfattribs={"layer": "TITLE", "height": 3.0, "insert": (0, -34)},
    )
    msp.add_text(
        "DRAWN BY: AI",
        dxfattribs={"layer": "TITLE", "height": 2.0, "insert": (0, -40)},
    )

    dxf_path = tmp_path / filename
    doc.saveas(str(dxf_path))
    return dxf_path
