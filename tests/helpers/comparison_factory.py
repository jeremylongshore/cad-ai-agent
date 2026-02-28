"""Test DXF pair builders for comparison engine tests.

Each function creates a pair of DXF files with known differences
for deterministic testing.  Also includes in-memory model builders
for EntityChange / ComparisonResult objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf

from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonConfig,
    ComparisonResult,
    EntityChange,
    GeometrySnapshot,
    MatchMethod,
)


def make_geometry_snapshot(
    *,
    handle: str = "A0",
    entity_type: EntityType = EntityType.LINE,
    layer: str = "STRUCTURAL",
    points: list[tuple[float, float]] | None = None,
    text_content: str | None = None,
    block_name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> GeometrySnapshot:
    """Build a GeometrySnapshot with sensible defaults."""
    pts = [Point2D(x=p[0], y=p[1]) for p in (points or [(0, 0), (10, 0)])]
    return GeometrySnapshot(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        points=pts,
        text_content=text_content,
        block_name=block_name,
        attributes=attributes or {},
    )


def make_entity_change(
    category: ChangeCategory = ChangeCategory.UNCHANGED,
    *,
    master_handle: str = "A0",
    revision_handle: str = "B0",
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    displacement: tuple[float, float] | None = None,
    modifications: dict[str, Any] | None = None,
    confidence: float = 1.0,
    match_method: MatchMethod | None = MatchMethod.fingerprint,
    master_points: list[tuple[float, float]] | None = None,
    revision_points: list[tuple[float, float]] | None = None,
    master_text: str | None = None,
    revision_text: str | None = None,
    master_block: str | None = None,
    revision_block: str | None = None,
    master_attributes: dict[str, Any] | None = None,
    revision_attributes: dict[str, Any] | None = None,
) -> EntityChange:
    """Build an EntityChange with flexible defaults per category."""
    m_snap = None
    r_snap = None

    if category != ChangeCategory.ADDED:
        m_snap = make_geometry_snapshot(
            handle=master_handle,
            entity_type=entity_type,
            layer=layer,
            points=master_points,
            text_content=master_text,
            block_name=master_block,
            attributes=master_attributes,
        )

    if category != ChangeCategory.REMOVED:
        r_snap = make_geometry_snapshot(
            handle=revision_handle,
            entity_type=entity_type,
            layer=layer,
            points=revision_points or master_points,
            text_content=revision_text or master_text,
            block_name=revision_block or master_block,
            attributes=revision_attributes or master_attributes,
        )

    disp = Point2D(x=displacement[0], y=displacement[1]) if displacement else None

    return EntityChange(
        category=category,
        master_snapshot=m_snap,
        revision_snapshot=r_snap,
        displacement=disp,
        modifications=modifications,
        confidence=confidence,
        match_method=match_method,
    )


def make_comparison_result(
    changes: list[EntityChange] | None = None,
) -> ComparisonResult:
    """Build a ComparisonResult with auto-computed summary."""
    changes = changes or []
    summary = {"added": 0, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0}
    for c in changes:
        summary[c.category.value] += 1
    return ComparisonResult(changes=changes, summary=summary, config=ComparisonConfig())


def make_identical_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two identical DXFs — zero changes expected."""
    master = _build_base(tmp_path / "master.dxf")
    revision = _build_base(tmp_path / "revision.dxf")
    return master, revision


def make_moved_entity_pair(tmp_path: Path, dx: float = 10.0, dy: float = 5.0) -> tuple[Path, Path]:
    """Revision has one line moved by (dx, dy)."""
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    # Master: line at (0,0)-(10,0) + text at (20,20)
    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("NOTES", color=3)
    msp_m.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_text("Label A", dxfattribs={"layer": "NOTES", "height": 2, "insert": (20, 20)})
    doc_m.saveas(str(master))

    # Revision: same line moved, text identical
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("NOTES", color=3)
    msp_r.add_line((0 + dx, 0 + dy), (10 + dx, 0 + dy), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_text("Label A", dxfattribs={"layer": "NOTES", "height": 2, "insert": (20, 20)})
    doc_r.saveas(str(revision))

    return master, revision


def make_added_removed_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Revision has one extra entity; master has one entity that revision lacks."""
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("NOTES", color=3)
    # Shared: line at origin
    msp_m.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    # Master-only: text that gets removed
    msp_m.add_text("Old Note", dxfattribs={"layer": "NOTES", "height": 2, "insert": (50, 50)})
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("NOTES", color=3)
    # Shared: same line
    msp_r.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    # Revision-only: new text added
    msp_r.add_text("New Note", dxfattribs={"layer": "NOTES", "height": 2, "insert": (80, 80)})
    doc_r.saveas(str(revision))

    return master, revision


def make_modified_text_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Same text entity at same location with different content."""
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("NOTES", color=3)
    msp_m.add_text("REV A", dxfattribs={"layer": "NOTES", "height": 2, "insert": (10, 10)})
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("NOTES", color=3)
    msp_r.add_text("REV B", dxfattribs={"layer": "NOTES", "height": 2, "insert": (10, 10)})
    doc_r.saveas(str(revision))

    return master, revision


def make_complex_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Mix of all change types: unchanged + moved + added + removed + modified."""
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("NOTES", color=3)

    # Unchanged: line at (0,0)-(10,0)
    msp_m.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    # Will be moved: line at (20,20)-(30,20)
    msp_m.add_line((20, 20), (30, 20), dxfattribs={"layer": "STRUCTURAL"})
    # Will be removed: text at (50,50)
    msp_m.add_text("Remove Me", dxfattribs={"layer": "NOTES", "height": 2, "insert": (50, 50)})
    # Will be modified: text at (80,80)
    msp_m.add_text("Version 1", dxfattribs={"layer": "NOTES", "height": 2, "insert": (80, 80)})
    # Will be modified: polyline
    msp_m.add_lwpolyline(
        [(100, 0), (110, 0), (110, 10), (100, 10)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("NOTES", color=3)

    # Unchanged: same line
    msp_r.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    # Moved: same line shifted by (5, 5)
    msp_r.add_line((25, 25), (35, 25), dxfattribs={"layer": "STRUCTURAL"})
    # (Remove Me text omitted — it's removed)
    # Modified: text content changed
    msp_r.add_text("Version 2", dxfattribs={"layer": "NOTES", "height": 2, "insert": (80, 80)})
    # Modified: polyline with different vertices
    msp_r.add_lwpolyline(
        [(100, 0), (115, 0), (115, 15), (100, 15)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    # Added: new circle
    msp_r.add_circle((200, 200), radius=5, dxfattribs={"layer": "STRUCTURAL"})
    doc_r.saveas(str(revision))

    return master, revision


def make_circle_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Master has a circle, revision has same circle with different radius."""
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    msp_m.add_circle((50, 50), radius=10, dxfattribs={"layer": "STRUCTURAL"})
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    msp_r.add_circle((50, 50), radius=15, dxfattribs={"layer": "STRUCTURAL"})
    doc_r.saveas(str(revision))

    return master, revision


def make_empty_vs_populated(tmp_path: Path) -> tuple[Path, Path]:
    """Master is empty, revision has entities (all added)."""
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    msp_r.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_text("Hello", dxfattribs={"layer": "STRUCTURAL", "height": 2, "insert": (5, 5)})
    doc_r.saveas(str(revision))

    return master, revision


def make_offset_pair(tmp_path: Path, dx: float = 5.0, dy: float = 3.0) -> tuple[Path, Path]:
    """Revision is uniformly translated by (dx, dy) — all entities shifted.

    Tests translation-only alignment. Both files have the same entities
    on the same layers, just offset in revision.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("GRID", color=7)
    doc_m.layers.add("NOTES", color=3)

    # Grid anchor blocks
    blk = doc_m.blocks.new("GRID_BUBBLE")
    blk.add_circle((0, 0), radius=1)
    msp_m.add_blockref("GRID_BUBBLE", (0, 0), dxfattribs={"layer": "GRID"})
    msp_m.add_blockref("GRID_BUBBLE", (100, 0), dxfattribs={"layer": "GRID"})
    msp_m.add_blockref("GRID_BUBBLE", (0, 100), dxfattribs={"layer": "GRID"})

    # Structural entities
    msp_m.add_line((10, 10), (90, 10), dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_line((10, 10), (10, 90), dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_lwpolyline(
        [(20, 20), (80, 20), (80, 80), (20, 80)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    msp_m.add_text("Room A", dxfattribs={"layer": "NOTES", "height": 2, "insert": (40, 40)})
    doc_m.saveas(str(master))

    # Revision: everything shifted by (dx, dy)
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("GRID", color=7)
    doc_r.layers.add("NOTES", color=3)

    blk_r = doc_r.blocks.new("GRID_BUBBLE")
    blk_r.add_circle((0, 0), radius=1)
    msp_r.add_blockref("GRID_BUBBLE", (0 + dx, 0 + dy), dxfattribs={"layer": "GRID"})
    msp_r.add_blockref("GRID_BUBBLE", (100 + dx, 0 + dy), dxfattribs={"layer": "GRID"})
    msp_r.add_blockref("GRID_BUBBLE", (0 + dx, 100 + dy), dxfattribs={"layer": "GRID"})

    msp_r.add_line((10 + dx, 10 + dy), (90 + dx, 10 + dy), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_line((10 + dx, 10 + dy), (10 + dx, 90 + dy), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_lwpolyline(
        [(20 + dx, 20 + dy), (80 + dx, 20 + dy), (80 + dx, 80 + dy), (20 + dx, 80 + dy)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    msp_r.add_text(
        "Room A", dxfattribs={"layer": "NOTES", "height": 2, "insert": (40 + dx, 40 + dy)}
    )
    doc_r.saveas(str(revision))

    return master, revision


def make_rotated_pair(
    tmp_path: Path, angle_deg: float = 15.0, cx: float = 50.0, cy: float = 50.0
) -> tuple[Path, Path]:
    """Revision is rotated by angle_deg around (cx, cy).

    Tests rigid alignment (rotation + translation). Master has entities
    at known positions; revision has the same entities rotated.
    """
    import math as _math

    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    # Master points (structural corners + grid anchors)
    master_pts = [
        (0.0, 0.0),
        (100.0, 0.0),
        (100.0, 100.0),
        (0.0, 100.0),
        (50.0, 0.0),
        (50.0, 100.0),
    ]

    def _rotate(x: float, y: float) -> tuple[float, float]:
        rad = _math.radians(angle_deg)
        dx, dy = x - cx, y - cy
        rx = dx * _math.cos(rad) - dy * _math.sin(rad) + cx
        ry = dx * _math.sin(rad) + dy * _math.cos(rad) + cy
        return (round(rx, 6), round(ry, 6))

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("GRID", color=7)

    # Grid anchors (blocks)
    blk = doc_m.blocks.new("COL_MARK")
    blk.add_circle((0, 0), radius=0.5)
    for pt in master_pts[:4]:
        msp_m.add_blockref("COL_MARK", pt, dxfattribs={"layer": "GRID"})

    # Structural lines
    msp_m.add_line(master_pts[0], master_pts[1], dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_line(master_pts[1], master_pts[2], dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_line(master_pts[2], master_pts[3], dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_line(master_pts[3], master_pts[0], dxfattribs={"layer": "STRUCTURAL"})
    doc_m.saveas(str(master))

    # Revision: everything rotated
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("GRID", color=7)

    blk_r = doc_r.blocks.new("COL_MARK")
    blk_r.add_circle((0, 0), radius=0.5)
    for pt in master_pts[:4]:
        rx, ry = _rotate(*pt)
        msp_r.add_blockref("COL_MARK", (rx, ry), dxfattribs={"layer": "GRID"})

    r0 = _rotate(*master_pts[0])
    r1 = _rotate(*master_pts[1])
    r2 = _rotate(*master_pts[2])
    r3 = _rotate(*master_pts[3])
    msp_r.add_line(r0, r1, dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_line(r1, r2, dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_line(r2, r3, dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_line(r3, r0, dxfattribs={"layer": "STRUCTURAL"})
    doc_r.saveas(str(revision))

    return master, revision


def make_anchor_pair(tmp_path: Path, dx: float = 10.0, dy: float = -5.0) -> tuple[Path, Path]:
    """Like make_offset_pair but ONLY has INSERT anchor blocks on GRID layer.

    Tests anchor alignment specifically with no structural geometry.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("GRID", color=7)
    blk = doc_m.blocks.new("GRID_LINE")
    blk.add_line((0, -5), (0, 5))
    msp_m.add_blockref("GRID_LINE", (0, 0), dxfattribs={"layer": "GRID"})
    msp_m.add_blockref("GRID_LINE", (50, 0), dxfattribs={"layer": "GRID"})
    msp_m.add_blockref("GRID_LINE", (100, 0), dxfattribs={"layer": "GRID"})
    msp_m.add_blockref("GRID_LINE", (0, 50), dxfattribs={"layer": "GRID"})
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("GRID", color=7)
    blk_r = doc_r.blocks.new("GRID_LINE")
    blk_r.add_line((0, -5), (0, 5))
    msp_r.add_blockref("GRID_LINE", (0 + dx, 0 + dy), dxfattribs={"layer": "GRID"})
    msp_r.add_blockref("GRID_LINE", (50 + dx, 0 + dy), dxfattribs={"layer": "GRID"})
    msp_r.add_blockref("GRID_LINE", (100 + dx, 0 + dy), dxfattribs={"layer": "GRID"})
    msp_r.add_blockref("GRID_LINE", (0 + dx, 50 + dy), dxfattribs={"layer": "GRID"})
    doc_r.saveas(str(revision))

    return master, revision


def make_ambiguous_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Master has one line; revision has two nearly-identical lines nearby.

    Tests ambiguous matching where the scorer can't confidently distinguish.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    msp_m.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    doc_m.saveas(str(master))

    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    # Two near-identical lines slightly offset from master
    msp_r.add_line((0.1, 0), (10.1, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_line((0.12, 0), (10.12, 0), dxfattribs={"layer": "STRUCTURAL"})
    doc_r.saveas(str(revision))

    return master, revision


def make_clean_revision_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Realistic structural revision: moved column, modified wall, added embed.

    Master: 3x2 column grid with walls (polylines) and a COLUMN_MARK block
    at each intersection.  One EQUIP_PAD embed near A-1.

    Revision changes:
      1. Column at C-2 moved 5 units east (INSERT repositioned)
      2. Wall between A-1 → B-1 modified (bump-out added to polyline)
      3. New OUTLET block inserted at (45, 15) — added embed
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"
    spacing = 30.0

    # --- shared helpers ---
    def _setup_doc() -> tuple[Any, Any]:
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("STRUCTURAL", color=1)
        doc.layers.add("GRID", color=7)
        doc.layers.add("NOTES", color=3)
        doc.layers.add("TITLE", color=7)

        # Block definitions
        col_blk = doc.blocks.new("COLUMN_MARK")
        col_blk.add_circle((0, 0), radius=1.5)
        col_blk.add_line((-1, -1), (1, 1))
        col_blk.add_line((-1, 1), (1, -1))

        equip_blk = doc.blocks.new("EQUIP_PAD")
        equip_blk.add_lwpolyline(
            [(-2, -2), (2, -2), (2, 2), (-2, 2)], close=True
        )

        outlet_blk = doc.blocks.new("OUTLET")
        outlet_blk.add_circle((0, 0), radius=0.8)
        outlet_blk.add_line((0, -0.8), (0, 0.8))

        return doc, msp

    # Grid positions: A=0, B=30, C=60  x  1=0, 2=30
    cols = {"A": 0.0, "B": spacing, "C": 2 * spacing}
    rows = {"1": 0.0, "2": spacing}

    # === MASTER ===
    doc_m, msp_m = _setup_doc()

    # Grid lines
    for _label, x in cols.items():
        msp_m.add_line((x, -5), (x, rows["2"] + 5), dxfattribs={"layer": "GRID"})
    for _label, y in rows.items():
        msp_m.add_line((-5, y), (cols["C"] + 5, y), dxfattribs={"layer": "GRID"})

    # Column marks at all 6 intersections
    for cl, x in cols.items():
        for rl, y in rows.items():
            msp_m.add_blockref(
                "COLUMN_MARK", insert=(x, y), dxfattribs={"layer": "STRUCTURAL"}
            )
            msp_m.add_text(
                f"{cl}-{rl}",
                dxfattribs={"layer": "NOTES", "height": 1.5, "insert": (x + 2, y + 2)},
            )

    # Walls as polylines
    # Wall A-1 → B-1 (bottom, straight)
    msp_m.add_lwpolyline(
        [(cols["A"], rows["1"]), (cols["B"], rows["1"])],
        dxfattribs={"layer": "STRUCTURAL"},
    )
    # Wall B-1 → C-1 (bottom)
    msp_m.add_lwpolyline(
        [(cols["B"], rows["1"]), (cols["C"], rows["1"])],
        dxfattribs={"layer": "STRUCTURAL"},
    )
    # Wall A-1 → A-2 (left)
    msp_m.add_lwpolyline(
        [(cols["A"], rows["1"]), (cols["A"], rows["2"])],
        dxfattribs={"layer": "STRUCTURAL"},
    )

    # Existing embed near A-1
    msp_m.add_blockref(
        "EQUIP_PAD", insert=(5, 5), dxfattribs={"layer": "STRUCTURAL"}
    )

    # Title (protected)
    msp_m.add_text(
        "FLOOR PLAN - LEVEL 1",
        dxfattribs={"layer": "TITLE", "height": 3.0, "insert": (0, -15)},
    )

    doc_m.saveas(str(master))

    # === REVISION ===
    doc_r, msp_r = _setup_doc()

    # Same grid lines
    for _label, x in cols.items():
        msp_r.add_line((x, -5), (x, rows["2"] + 5), dxfattribs={"layer": "GRID"})
    for _label, y in rows.items():
        msp_r.add_line((-5, y), (cols["C"] + 5, y), dxfattribs={"layer": "GRID"})

    # Column marks — C-2 moved 5 units east
    for cl, x in cols.items():
        for rl, y in rows.items():
            insert_x = x + 5.0 if (cl == "C" and rl == "2") else x
            msp_r.add_blockref(
                "COLUMN_MARK",
                insert=(insert_x, y),
                dxfattribs={"layer": "STRUCTURAL"},
            )
            msp_r.add_text(
                f"{cl}-{rl}",
                dxfattribs={
                    "layer": "NOTES",
                    "height": 1.5,
                    "insert": (insert_x + 2, y + 2),
                },
            )

    # Wall A-1 → B-1 MODIFIED: bump-out (extra vertices)
    msp_r.add_lwpolyline(
        [
            (cols["A"], rows["1"]),
            (10, rows["1"]),
            (10, rows["1"] + 5),  # bump out
            (20, rows["1"] + 5),  # bump out
            (20, rows["1"]),
            (cols["B"], rows["1"]),
        ],
        dxfattribs={"layer": "STRUCTURAL"},
    )
    # Wall B-1 → C-1 (unchanged)
    msp_r.add_lwpolyline(
        [(cols["B"], rows["1"]), (cols["C"], rows["1"])],
        dxfattribs={"layer": "STRUCTURAL"},
    )
    # Wall A-1 → A-2 (unchanged)
    msp_r.add_lwpolyline(
        [(cols["A"], rows["1"]), (cols["A"], rows["2"])],
        dxfattribs={"layer": "STRUCTURAL"},
    )

    # Existing embed (unchanged)
    msp_r.add_blockref(
        "EQUIP_PAD", insert=(5, 5), dxfattribs={"layer": "STRUCTURAL"}
    )

    # NEW: added OUTLET embed
    msp_r.add_blockref(
        "OUTLET", insert=(45, 15), dxfattribs={"layer": "STRUCTURAL"}
    )

    # Title (unchanged, protected)
    msp_r.add_text(
        "FLOOR PLAN - LEVEL 1",
        dxfattribs={"layer": "TITLE", "height": 3.0, "insert": (0, -15)},
    )

    doc_r.saveas(str(revision))

    return master, revision


def make_partial_revision_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Revision cloud covers only part of the drawing.

    Master: 4 columns spread across a wide area (x=0..120).
    Revision: only the left half (x=0..60) is re-drawn with one column moved.
    Entities in the right half (x=90, x=120) are absent from the revision —
    the pipeline must NOT classify them as removed.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("NOTES", color=3)

    positions = [(0, 0), (30, 0), (90, 0), (120, 0)]
    for i, (x, y) in enumerate(positions):
        msp_m.add_line((x, y), (x, 20), dxfattribs={"layer": "STRUCTURAL"})
        msp_m.add_text(
            f"COL-{i+1}",
            dxfattribs={"layer": "NOTES", "height": 1.5, "insert": (x + 2, y + 2)},
        )
    doc_m.saveas(str(master))

    # Revision: only left half present, COL-2 moved 5 east
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("NOTES", color=3)

    # COL-1 unchanged
    msp_r.add_line((0, 0), (0, 20), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_text(
        "COL-1", dxfattribs={"layer": "NOTES", "height": 1.5, "insert": (2, 2)}
    )
    # COL-2 moved east
    msp_r.add_line((35, 0), (35, 20), dxfattribs={"layer": "STRUCTURAL"})
    msp_r.add_text(
        "COL-2", dxfattribs={"layer": "NOTES", "height": 1.5, "insert": (37, 2)}
    )
    # COL-3 and COL-4 intentionally absent (outside revision extents)
    doc_r.saveas(str(revision))

    return master, revision


def make_unit_mismatch_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Master in inches, revision in millimeters (25.4x scale factor).

    Master: rectangle 10x8 inches at origin.
    Revision: same rectangle but coordinates are in mm (254x203.2).
    The pipeline should detect these are the same geometry at different scales.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    # Master: inches (INSUNITS=1)
    doc_m = ezdxf.new(dxfversion="R2018")
    doc_m.header["$INSUNITS"] = 1  # inches
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("NOTES", color=3)

    msp_m.add_lwpolyline(
        [(0, 0), (10, 0), (10, 8), (0, 8)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    msp_m.add_line((0, 0), (10, 8), dxfattribs={"layer": "STRUCTURAL"})
    msp_m.add_text(
        "Room A", dxfattribs={"layer": "NOTES", "height": 1.0, "insert": (3, 4)}
    )
    doc_m.saveas(str(master))

    # Revision: millimeters (INSUNITS=4), same geometry scaled
    scale = 25.4
    doc_r = ezdxf.new(dxfversion="R2018")
    doc_r.header["$INSUNITS"] = 4  # millimeters
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("NOTES", color=3)

    msp_r.add_lwpolyline(
        [
            (0 * scale, 0 * scale),
            (10 * scale, 0 * scale),
            (10 * scale, 8 * scale),
            (0 * scale, 8 * scale),
        ],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )
    msp_r.add_line(
        (0 * scale, 0 * scale),
        (10 * scale, 8 * scale),
        dxfattribs={"layer": "STRUCTURAL"},
    )
    msp_r.add_text(
        "Room A",
        dxfattribs={
            "layer": "NOTES",
            "height": 1.0 * scale,
            "insert": (3 * scale, 4 * scale),
        },
    )
    doc_r.saveas(str(revision))

    return master, revision


def make_rotation_shift_pair(
    tmp_path: Path,
    angle_deg: float = 12.0,
    dx: float = 8.0,
    dy: float = -3.0,
) -> tuple[Path, Path]:
    """Revision is rotated AND translated vs master.

    Master: L-shaped wall + 3 columns.
    Revision: same geometry rotated by angle_deg around centroid, then shifted
    by (dx, dy).  One column is also genuinely moved 4 units south (real change).
    """
    import math as _math

    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    cx, cy = 30.0, 15.0  # rotation center (approx centroid)

    def _transform(x: float, y: float) -> tuple[float, float]:
        rad = _math.radians(angle_deg)
        lx, ly = x - cx, y - cy
        rx = lx * _math.cos(rad) - ly * _math.sin(rad) + cx + dx
        ry = lx * _math.sin(rad) + ly * _math.cos(rad) + cy + dy
        return (round(rx, 4), round(ry, 4))

    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    doc_m.layers.add("GRID", color=7)

    blk = doc_m.blocks.new("COL")
    blk.add_circle((0, 0), radius=1)

    # L-shaped wall
    wall_pts = [(0, 0), (60, 0), (60, 10), (30, 10), (30, 30), (0, 30)]
    msp_m.add_lwpolyline(wall_pts, close=True, dxfattribs={"layer": "STRUCTURAL"})

    # Columns
    col_positions = [(10, 5), (50, 5), (15, 20)]
    for pos in col_positions:
        msp_m.add_blockref("COL", insert=pos, dxfattribs={"layer": "GRID"})
    doc_m.saveas(str(master))

    # Revision: transform everything, plus move one column
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)
    doc_r.layers.add("GRID", color=7)

    blk_r = doc_r.blocks.new("COL")
    blk_r.add_circle((0, 0), radius=1)

    # Transformed L-wall
    t_wall = [_transform(x, y) for x, y in wall_pts]
    msp_r.add_lwpolyline(t_wall, close=True, dxfattribs={"layer": "STRUCTURAL"})

    # Columns: first two just transformed, third moved 4 south then transformed
    for i, (px, py) in enumerate(col_positions):
        if i == 2:
            # Real change: moved 4 units south before transform
            px, py = px, py - 4
        tx, ty = _transform(px, py)
        msp_r.add_blockref("COL", insert=(tx, ty), dxfattribs={"layer": "GRID"})
    doc_r.saveas(str(revision))

    return master, revision


def make_block_attrib_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Block INSERT attributes changed between master and revision.

    Master: 3 door blocks with TAG/ROOM/SIZE attributes.
    Revision: same blocks, but DOOR-2 has changed ROOM and SIZE values,
    and DOOR-3 has a new attribute FIRE_RATING added.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    def _make_door_block(doc: Any) -> None:
        blk = doc.blocks.new("DOOR")
        blk.add_line((-1, 0), (1, 0))
        blk.add_arc((0, 0), radius=1, start_angle=0, end_angle=90)
        blk.add_attdef("TAG", insert=(0, 1.5), dxfattribs={"height": 0.8})
        blk.add_attdef("ROOM", insert=(0, 2.5), dxfattribs={"height": 0.6})
        blk.add_attdef("SIZE", insert=(0, 3.5), dxfattribs={"height": 0.6})

    # Master
    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    doc_m.layers.add("STRUCTURAL", color=1)
    _make_door_block(doc_m)

    doors_m = [
        {"pos": (10, 0), "TAG": "DOOR-1", "ROOM": "101", "SIZE": "36"},
        {"pos": (30, 0), "TAG": "DOOR-2", "ROOM": "102", "SIZE": "36"},
        {"pos": (50, 0), "TAG": "DOOR-3", "ROOM": "103", "SIZE": "30"},
    ]
    for d in doors_m:
        ref = msp_m.add_blockref(
            "DOOR", insert=d["pos"], dxfattribs={"layer": "STRUCTURAL"}
        )
        ref.add_auto_attribs(
            {"TAG": d["TAG"], "ROOM": d["ROOM"], "SIZE": d["SIZE"]}
        )
    doc_m.saveas(str(master))

    # Revision: DOOR-2 room/size changed, DOOR-3 gets extra attrib
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    doc_r.layers.add("STRUCTURAL", color=1)

    # Need attdef with FIRE_RATING for DOOR-3
    blk_r = doc_r.blocks.new("DOOR")
    blk_r.add_line((-1, 0), (1, 0))
    blk_r.add_arc((0, 0), radius=1, start_angle=0, end_angle=90)
    blk_r.add_attdef("TAG", insert=(0, 1.5), dxfattribs={"height": 0.8})
    blk_r.add_attdef("ROOM", insert=(0, 2.5), dxfattribs={"height": 0.6})
    blk_r.add_attdef("SIZE", insert=(0, 3.5), dxfattribs={"height": 0.6})
    blk_r.add_attdef("FIRE_RATING", insert=(0, 4.5), dxfattribs={"height": 0.6})

    doors_r = [
        {"pos": (10, 0), "attribs": {"TAG": "DOOR-1", "ROOM": "101", "SIZE": "36"}},
        {"pos": (30, 0), "attribs": {"TAG": "DOOR-2", "ROOM": "105", "SIZE": "42"}},
        {
            "pos": (50, 0),
            "attribs": {
                "TAG": "DOOR-3",
                "ROOM": "103",
                "SIZE": "30",
                "FIRE_RATING": "1HR",
            },
        },
    ]
    for d in doors_r:
        ref = msp_r.add_blockref(
            "DOOR", insert=d["pos"], dxfattribs={"layer": "STRUCTURAL"}
        )
        ref.add_auto_attribs(d["attribs"])
    doc_r.saveas(str(revision))

    return master, revision


def make_xref_pair(tmp_path: Path) -> tuple[Path, Path]:
    """External references present in one or both files.

    Master: structural drawing that attaches an xref "GRID_REF" (simulated
    as a block definition with XREF flag).
    Revision: same structural content plus a second xref "MECH_REF".
    The comparison pipeline must not confuse xref blocks with real inserts.
    """
    master = tmp_path / "master.dxf"
    revision = tmp_path / "revision.dxf"

    def _setup_structural(doc: Any, msp: Any) -> None:
        doc.layers.add("STRUCTURAL", color=1)
        doc.layers.add("NOTES", color=3)
        doc.layers.add("XREF", color=8)
        msp.add_line((0, 0), (50, 0), dxfattribs={"layer": "STRUCTURAL"})
        msp.add_line((0, 0), (0, 40), dxfattribs={"layer": "STRUCTURAL"})
        msp.add_lwpolyline(
            [(10, 10), (40, 10), (40, 30), (10, 30)],
            close=True,
            dxfattribs={"layer": "STRUCTURAL"},
        )
        msp.add_text(
            "Main Floor",
            dxfattribs={"layer": "NOTES", "height": 2, "insert": (15, 20)},
        )

    # Master with one xref
    doc_m = ezdxf.new(dxfversion="R2018")
    msp_m = doc_m.modelspace()
    _setup_structural(doc_m, msp_m)

    # Simulate xref as a block with is_xref flag
    xref_blk = doc_m.blocks.new("GRID_REF", base_point=(0, 0))
    xref_blk.add_line((0, 0), (100, 0))  # placeholder geometry
    # Mark as external reference via block flags
    xref_blk.block.dxf.flags = 4  # BLK_XREF flag
    msp_m.add_blockref("GRID_REF", insert=(0, 0), dxfattribs={"layer": "XREF"})
    doc_m.saveas(str(master))

    # Revision: same structural content + second xref
    doc_r = ezdxf.new(dxfversion="R2018")
    msp_r = doc_r.modelspace()
    _setup_structural(doc_r, msp_r)

    xref_blk1 = doc_r.blocks.new("GRID_REF", base_point=(0, 0))
    xref_blk1.add_line((0, 0), (100, 0))
    xref_blk1.block.dxf.flags = 4
    msp_r.add_blockref("GRID_REF", insert=(0, 0), dxfattribs={"layer": "XREF"})

    xref_blk2 = doc_r.blocks.new("MECH_REF", base_point=(0, 0))
    xref_blk2.add_line((0, 0), (80, 0))
    xref_blk2.block.dxf.flags = 4
    msp_r.add_blockref("MECH_REF", insert=(0, 0), dxfattribs={"layer": "XREF"})
    doc_r.saveas(str(revision))

    return master, revision


def _build_base(path: Path) -> Path:
    """Build a small DXF with reproducible entities."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)

    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_line((0, 0), (0, 10), dxfattribs={"layer": "STRUCTURAL"})
    msp.add_text("Test Note", dxfattribs={"layer": "NOTES", "height": 2, "insert": (5, 5)})
    msp.add_lwpolyline(
        [(20, 0), (30, 0), (30, 10), (20, 10)],
        close=True,
        dxfattribs={"layer": "STRUCTURAL"},
    )

    doc.saveas(str(path))
    return path
