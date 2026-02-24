#!/usr/bin/env python3
"""Generate DXF Zoo files for robustness testing.

Creates a curated set of DXF files across different versions (R12, R2000, R2018)
and edge cases using ezdxf.  Saves to tests/fixtures/dxf_zoo/.

Run once:  python scripts/download_zoo.py
Files are committed to the repo (total < 1 MB).
"""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

ZOO_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "dxf_zoo"


def _generate_r12_basic(dest: Path) -> None:
    """R12 format — oldest supported, ASCII-only, limited entity types."""
    doc = ezdxf.new(dxfversion="R12")
    msp = doc.modelspace()
    for i in range(10):
        msp.add_line((i * 10, 0), (i * 10, 50))
        msp.add_line((0, i * 5), (90, i * 5))
    for i in range(3):
        msp.add_text(
            f"NOTE-{i}",
            dxfattribs={"height": 2.0, "insert": (i * 30, -10)},
        )
    doc.saveas(str(dest))


def _generate_r2000_with_blocks(dest: Path) -> None:
    """R2000 format with block definitions and inserts."""
    doc = ezdxf.new(dxfversion="R2000")
    msp = doc.modelspace()
    doc.layers.add("STRUCT", color=1)
    doc.layers.add("ANNOT", color=3)

    blk = doc.blocks.new("BOLT")
    blk.add_circle((0, 0), radius=0.5)
    blk.add_line((-0.3, -0.3), (0.3, 0.3))

    for x in range(5):
        for y in range(5):
            msp.add_blockref("BOLT", insert=(x * 20, y * 20), dxfattribs={"layer": "STRUCT"})
            msp.add_text(
                f"B{x}{y}",
                dxfattribs={"layer": "ANNOT", "height": 1.5, "insert": (x * 20 + 2, y * 20 + 2)},
            )
    doc.saveas(str(dest))


def _generate_r2018_polylines(dest: Path) -> None:
    """R2018 format with complex polylines and arcs."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("GEOMETRY", color=5)

    # Several polylines of varying complexity
    import math

    for j in range(4):
        pts = [(math.cos(i * 0.5) * (10 + j * 5) + j * 30, math.sin(i * 0.5) * (10 + j * 5))
               for i in range(20)]
        msp.add_lwpolyline(pts, dxfattribs={"layer": "GEOMETRY"})

    for i in range(8):
        msp.add_arc(
            (i * 15, -20), radius=5 + i, start_angle=0, end_angle=90 + i * 30,
            dxfattribs={"layer": "GEOMETRY"},
        )

    for i in range(5):
        msp.add_circle((i * 20, -40), radius=3 + i, dxfattribs={"layer": "GEOMETRY"})

    doc.saveas(str(dest))


GENERATORS = [
    ("r12_basic.dxf", _generate_r12_basic),
    ("r2000_blocks.dxf", _generate_r2000_with_blocks),
    ("r2018_polylines.dxf", _generate_r2018_polylines),
]


def main() -> int:
    ZOO_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating DXF zoo files in {ZOO_DIR}\n")

    for name, gen_fn in GENERATORS:
        dest = ZOO_DIR / name
        if dest.exists():
            print(f"  SKIP {name} (already exists)")
            continue
        gen_fn(dest)
        size = dest.stat().st_size
        print(f"  OK   {name} ({size:,} bytes)")

    print(f"\nDone: {len(GENERATORS)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
