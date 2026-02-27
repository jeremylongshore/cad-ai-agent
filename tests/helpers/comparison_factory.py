"""Test DXF pair builders for comparison engine tests.

Each function creates a pair of DXF files with known differences
for deterministic testing.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf


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


def make_offset_pair(
    tmp_path: Path, dx: float = 5.0, dy: float = 3.0
) -> tuple[Path, Path]:
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


def make_anchor_pair(
    tmp_path: Path, dx: float = 10.0, dy: float = -5.0
) -> tuple[Path, Path]:
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
