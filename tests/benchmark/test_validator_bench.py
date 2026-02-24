"""Micro-benchmarks for validator pipeline.

Uses pytest-benchmark to measure validation performance at different
drawing scales. Run with: pytest tests/benchmark/ -v

Benchmark results are printed to stdout. Use --benchmark-json=output.json
to save results for CI regression tracking.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType

pytestmark = pytest.mark.benchmark


# ── Fixtures ──────────────────────────────────────────────────


def _make_drawing(tmp_path: Path, entity_count: int) -> Path:
    """Build a DXF with *entity_count* lines on STRUCTURAL."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("STRUCTURAL", color=1)
    doc.layers.add("NOTES", color=3)
    doc.layers.add("TITLE", color=7)

    for i in range(entity_count):
        y = float(i)
        msp.add_line((0, y), (100, y), dxfattribs={"layer": "STRUCTURAL"})

    # Add some text entities for edit_text benchmarks
    for i in range(min(entity_count // 10, 50)):
        msp.add_text(
            f"Label-{i}",
            dxfattribs={"layer": "NOTES", "height": 2.0, "insert": (0, float(i) * 10)},
        )

    # Protected layer entities
    msp.add_text("TITLE", dxfattribs={"layer": "TITLE", "height": 5.0, "insert": (0, -10)})

    path = tmp_path / f"bench_{entity_count}.dxf"
    doc.saveas(str(path))
    return path


@pytest.fixture
def small_drawing(tmp_path):
    """50 entities — typical small detail."""
    return _make_drawing(tmp_path, 50)


@pytest.fixture
def medium_drawing(tmp_path):
    """500 entities — typical floor plan."""
    return _make_drawing(tmp_path, 500)


@pytest.fixture
def large_drawing(tmp_path):
    """2000 entities — large structural sheet."""
    return _make_drawing(tmp_path, 2000)


def _make_changeset(context, op_count: int) -> ChangeSet:
    """Build a changeset with *op_count* move operations targeting real handles."""
    entities = [e for e in context.entities if e.layer.upper() != "TITLE"]
    ops = []
    for i in range(min(op_count, len(entities))):
        ops.append(
            EditOperation(
                op_type=OpType.MOVE_ENTITY,
                target_handle=entities[i].handle,
                params={"dx": 1.0, "dy": 0.0},
            )
        )
    return ChangeSet(prompt="benchmark", operations=ops)


# ── Benchmarks: validate_changeset ────────────────────────────


class TestValidatorBenchSmall:
    """Benchmarks on a 50-entity drawing."""

    def test_validate_single_op(self, small_drawing, benchmark):
        ctx = load_dxf(small_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 1)
        benchmark(validate_changeset, cs, ctx, rules)

    def test_validate_10_ops(self, small_drawing, benchmark):
        ctx = load_dxf(small_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 10)
        benchmark(validate_changeset, cs, ctx, rules)


class TestValidatorBenchMedium:
    """Benchmarks on a 500-entity drawing."""

    def test_validate_single_op(self, medium_drawing, benchmark):
        ctx = load_dxf(medium_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 1)
        benchmark(validate_changeset, cs, ctx, rules)

    def test_validate_10_ops(self, medium_drawing, benchmark):
        ctx = load_dxf(medium_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 10)
        benchmark(validate_changeset, cs, ctx, rules)

    def test_validate_50_ops(self, medium_drawing, benchmark):
        ctx = load_dxf(medium_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 50)
        benchmark(validate_changeset, cs, ctx, rules)


class TestValidatorBenchLarge:
    """Benchmarks on a 2000-entity drawing."""

    def test_validate_single_op(self, large_drawing, benchmark):
        ctx = load_dxf(large_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 1)
        benchmark(validate_changeset, cs, ctx, rules)

    def test_validate_10_ops(self, large_drawing, benchmark):
        ctx = load_dxf(large_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 10)
        benchmark(validate_changeset, cs, ctx, rules)

    def test_validate_50_ops(self, large_drawing, benchmark):
        ctx = load_dxf(large_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 50)
        benchmark(validate_changeset, cs, ctx, rules)

    def test_validate_100_ops(self, large_drawing, benchmark):
        ctx = load_dxf(large_drawing)
        rules = RuleConfig()
        cs = _make_changeset(ctx, 100)
        benchmark(validate_changeset, cs, ctx, rules)


# ── Benchmarks: build_planner_context ─────────────────────────


class TestContextBuildBench:
    """Benchmark the semantic model context builder at different scales."""

    def test_build_context_small(self, small_drawing, benchmark):
        ctx = load_dxf(small_drawing)
        benchmark(build_planner_context, ctx)

    def test_build_context_medium(self, medium_drawing, benchmark):
        ctx = load_dxf(medium_drawing)
        benchmark(build_planner_context, ctx)

    def test_build_context_large(self, large_drawing, benchmark):
        ctx = load_dxf(large_drawing)
        benchmark(build_planner_context, ctx)


# ── Benchmarks: load_dxf ─────────────────────────────────────


class TestLoadDxfBench:
    """Benchmark DXF loading at different scales."""

    def test_load_small(self, small_drawing, benchmark):
        benchmark(load_dxf, small_drawing)

    def test_load_medium(self, medium_drawing, benchmark):
        benchmark(load_dxf, medium_drawing)

    def test_load_large(self, large_drawing, benchmark):
        benchmark(load_dxf, large_drawing)
