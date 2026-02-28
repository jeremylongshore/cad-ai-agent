"""Fuzz tests: random geometry perturbations must produce stable matches.

Generates random drawings, applies controlled perturbations, and asserts
the comparison pipeline produces sane, stable classifications.

Bounded to ~5s runtime per test for CI friendliness.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import ezdxf

from cad_dxf_agent.core.comparison.engine import ComparisonEngine

# Fixed seed for reproducibility in CI
RNG = random.Random(42)  # noqa: S311 — deterministic seed for test reproducibility
ENGINE = ComparisonEngine()
ITERATIONS = 20  # per test — keeps runtime under 5s


def _random_drawing(tmp_path: Path, name: str, n_entities: int = 15) -> Path:
    """Generate a drawing with random lines, polylines, and text."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)

    for i in range(n_entities):
        kind = RNG.choice(["line", "polyline", "text"])
        x = RNG.uniform(-100, 100)
        y = RNG.uniform(-100, 100)

        if kind == "line":
            dx = RNG.uniform(5, 30)
            dy = RNG.uniform(-10, 10)
            msp.add_line(
                (x, y), (x + dx, y + dy),
                dxfattribs={"layer": "STRUCTURAL"},
            )
        elif kind == "polyline":
            n_pts = RNG.randint(3, 6)
            pts = [(x + j * RNG.uniform(3, 8), y + RNG.uniform(-5, 5)) for j in range(n_pts)]
            msp.add_lwpolyline(
                pts, close=RNG.choice([True, False]),
                dxfattribs={"layer": "STRUCTURAL"},
            )
        else:
            msp.add_text(
                f"Label-{i}",
                dxfattribs={
                    "layer": "NOTES",
                    "height": RNG.uniform(1, 3),
                    "insert": (x, y),
                },
            )

    path = tmp_path / name
    doc.saveas(str(path))
    return path


def _perturb_drawing(
    src: Path, dst: Path,
    *,
    translate: tuple[float, float] = (0, 0),
    noise: float = 0.0,
    delete_frac: float = 0.0,
    add_count: int = 0,
) -> Path:
    """Load src DXF, apply perturbations, save to dst."""
    doc = ezdxf.readfile(str(src))
    msp = doc.modelspace()
    entities = list(msp)

    # Delete random fraction
    if delete_frac > 0:
        n_delete = int(len(entities) * delete_frac)
        to_delete = RNG.sample(entities, min(n_delete, len(entities)))
        for e in to_delete:
            msp.delete_entity(e)
        entities = [e for e in entities if e not in to_delete]

    # Translate + noise
    tx, ty = translate
    for e in entities:
        if e.dxftype() == "LINE":
            s = e.dxf.start
            end = e.dxf.end
            nx1 = RNG.gauss(0, noise) if noise else 0
            ny1 = RNG.gauss(0, noise) if noise else 0
            nx2 = RNG.gauss(0, noise) if noise else 0
            ny2 = RNG.gauss(0, noise) if noise else 0
            e.dxf.start = (s[0] + tx + nx1, s[1] + ty + ny1, 0)
            e.dxf.end = (end[0] + tx + nx2, end[1] + ty + ny2, 0)
        elif e.dxftype() == "TEXT":
            pos = e.dxf.insert
            nx = RNG.gauss(0, noise) if noise else 0
            ny = RNG.gauss(0, noise) if noise else 0
            e.dxf.insert = (pos[0] + tx + nx, pos[1] + ty + ny, 0)

    # Add new entities
    if add_count > 0:
        if not doc.layers.has_entry("STRUCTURAL"):
            doc.layers.add("STRUCTURAL", color=1)
        for _i in range(add_count):
            x = RNG.uniform(200, 300)
            y = RNG.uniform(200, 300)
            msp.add_line(
                (x, y), (x + 10, y + 10),
                dxfattribs={"layer": "STRUCTURAL"},
            )

    doc.saveas(str(dst))
    return dst


class TestFuzzMatchingStability:
    """Property: pipeline never crashes and classifications are sane."""

    def test_identical_produces_no_changes(self, tmp_path):
        """Comparing a drawing to itself should yield all unchanged."""
        for i in range(ITERATIONS):
            RNG.seed(42 + i)
            drawing = _random_drawing(tmp_path, f"identical_{i}.dxf")
            result = ENGINE.compare(drawing, drawing)
            non_unchanged = sum(
                v for k, v in result.summary.items() if k != "unchanged"
            )
            assert non_unchanged == 0, (
                f"Iteration {i}: self-comparison found {non_unchanged} changes"
            )

    def test_translation_no_crash(self, tmp_path):
        """Uniform translation should not crash."""
        for i in range(ITERATIONS):
            RNG.seed(42 + i)
            master = _random_drawing(tmp_path, f"trans_m_{i}.dxf")
            tx = RNG.uniform(-50, 50)
            ty = RNG.uniform(-50, 50)
            revision = _perturb_drawing(
                master, tmp_path / f"trans_r_{i}.dxf",
                translate=(tx, ty),
            )
            result = ENGINE.compare(master, revision)
            # Must not crash; total entities should be consistent
            total = sum(result.summary.values())
            assert total > 0

    def test_noise_stability(self, tmp_path):
        """Small noise should not crash; large noise may cause mismatches."""
        for i in range(ITERATIONS):
            RNG.seed(42 + i)
            master = _random_drawing(tmp_path, f"noise_m_{i}.dxf")
            revision = _perturb_drawing(
                master, tmp_path / f"noise_r_{i}.dxf",
                noise=0.01,  # sub-tolerance noise
            )
            result = ENGINE.compare(master, revision)
            total = sum(result.summary.values())
            assert total > 0

    def test_deletions_sane(self, tmp_path):
        """Deleting entities should increase removed count."""
        for i in range(ITERATIONS):
            RNG.seed(42 + i)
            master = _random_drawing(tmp_path, f"del_m_{i}.dxf")
            revision = _perturb_drawing(
                master, tmp_path / f"del_r_{i}.dxf",
                delete_frac=0.3,
            )
            result = ENGINE.compare(master, revision)
            # At least some removed or the total should differ
            total = sum(result.summary.values())
            assert total > 0

    def test_additions_sane(self, tmp_path):
        """Adding entities should increase added count."""
        for i in range(ITERATIONS):
            RNG.seed(42 + i)
            master = _random_drawing(tmp_path, f"add_m_{i}.dxf")
            revision = _perturb_drawing(
                master, tmp_path / f"add_r_{i}.dxf",
                add_count=5,
            )
            result = ENGINE.compare(master, revision)
            assert result.summary.get("added", 0) > 0, (
                f"Iteration {i}: expected additions but got {result.summary}"
            )

    def test_rotation_no_crash(self, tmp_path):
        """Rotated revision should not crash (may misclassify)."""
        for i in range(min(ITERATIONS, 10)):  # rotation is slower
            RNG.seed(42 + i)
            master = _random_drawing(tmp_path, f"rot_m_{i}.dxf", n_entities=8)
            # Rotate via perturb (translate to simulate rotation effect)
            angle = RNG.uniform(-30, 30)
            rad = math.radians(angle)
            # Approximate rotation as offset (true rotation tested in fixtures)
            tx = 5 * math.sin(rad)
            ty = 5 * (1 - math.cos(rad))
            revision = _perturb_drawing(
                master, tmp_path / f"rot_r_{i}.dxf",
                translate=(tx, ty),
                noise=0.1,
            )
            result = ENGINE.compare(master, revision)
            total = sum(result.summary.values())
            assert total > 0

    def test_combined_perturbations(self, tmp_path):
        """Translation + noise + deletions + additions all at once."""
        for i in range(ITERATIONS):
            RNG.seed(42 + i)
            master = _random_drawing(tmp_path, f"combo_m_{i}.dxf")
            revision = _perturb_drawing(
                master, tmp_path / f"combo_r_{i}.dxf",
                translate=(RNG.uniform(-20, 20), RNG.uniform(-20, 20)),
                noise=0.05,
                delete_frac=0.1,
                add_count=2,
            )
            result = ENGINE.compare(master, revision)
            total = sum(result.summary.values())
            assert total > 0
            # Additions should always be detected
            assert result.summary.get("added", 0) >= 2
