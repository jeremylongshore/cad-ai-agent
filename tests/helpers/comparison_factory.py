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
