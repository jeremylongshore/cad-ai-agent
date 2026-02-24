"""DXF Zoo unit tests — robustness checks without LLM.

Every zoo file is run through the non-LLM pipeline stages:
  load → build_planner_context → validate empty changeset

Catches regressions on new file formats, entity types, and encoding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet
from tests.helpers.dxf_factory import (
    create_dense_drawing,
    create_empty_layers_drawing,
    create_mixed_entity_drawing,
    create_overlapping_drawing,
    create_structural_drawing,
    create_unicode_drawing,
)

# ---------------------------------------------------------------------------
# Zoo file discovery
# ---------------------------------------------------------------------------

ZOO_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "dxf_zoo"

# Factory builders paired with their names (generated at test time via tmp_path)
FACTORY_BUILDERS = [
    ("structural", create_structural_drawing),
    ("dense_1000", create_dense_drawing),
    ("mixed_entities", create_mixed_entity_drawing),
    ("unicode_labels", create_unicode_drawing),
    ("overlapping", create_overlapping_drawing),
    ("empty_layers", create_empty_layers_drawing),
]


def _committed_zoo_files() -> list[Path]:
    """Discover pre-generated DXF files committed to the zoo directory."""
    if not ZOO_DIR.is_dir():
        return []
    return sorted(ZOO_DIR.glob("*.dxf"))


# ---------------------------------------------------------------------------
# Parametrized tests over committed zoo files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dxf_path",
    _committed_zoo_files(),
    ids=[p.stem for p in _committed_zoo_files()],
)
class TestCommittedZooFiles:
    """Tests over pre-generated DXF files in tests/fixtures/dxf_zoo/."""

    def test_loads_without_error(self, dxf_path: Path):
        ctx = load_dxf(dxf_path)
        assert ctx.entity_count >= 0

    def test_planner_context_builds(self, dxf_path: Path):
        ctx = load_dxf(dxf_path)
        pc = build_planner_context(ctx)
        assert "layers" in pc
        assert "entities" in pc

    def test_empty_changeset_validates(self, dxf_path: Path):
        ctx = load_dxf(dxf_path)
        cs = ChangeSet(prompt="noop", operations=[])
        result = validate_changeset(cs, ctx, RuleConfig())
        assert not result.blockers


# ---------------------------------------------------------------------------
# Parametrized tests over factory-built drawings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,builder", FACTORY_BUILDERS, ids=[n for n, _ in FACTORY_BUILDERS])
class TestFactoryZooFiles:
    """Tests over factory-built DXF drawings (generated into tmp_path)."""

    def test_loads_without_error(self, name: str, builder, tmp_path: Path):
        dxf_path = builder(tmp_path)
        ctx = load_dxf(dxf_path)
        assert ctx.entity_count >= 0

    def test_planner_context_builds(self, name: str, builder, tmp_path: Path):
        dxf_path = builder(tmp_path)
        ctx = load_dxf(dxf_path)
        pc = build_planner_context(ctx)
        assert "layers" in pc
        assert "entities" in pc
        assert isinstance(pc["entities"], list)

    def test_empty_changeset_validates(self, name: str, builder, tmp_path: Path):
        dxf_path = builder(tmp_path)
        ctx = load_dxf(dxf_path)
        cs = ChangeSet(prompt="noop", operations=[])
        result = validate_changeset(cs, ctx, RuleConfig())
        assert not result.blockers


# ---------------------------------------------------------------------------
# Targeted edge-case tests
# ---------------------------------------------------------------------------


class TestZooEdgeCases:
    """Targeted tests for specific zoo edge cases."""

    def test_dense_drawing_entity_count(self, tmp_path: Path):
        dxf_path = create_dense_drawing(tmp_path, count=1000)
        ctx = load_dxf(dxf_path)
        # Should have at least 500 supported entities (some may be unsupported)
        assert ctx.entity_count >= 500

    def test_dense_drawing_large_warning(self, tmp_path: Path):
        dxf_path = create_dense_drawing(tmp_path, count=1000)
        ctx = load_dxf(dxf_path)
        warning_codes = [w.code for w in ctx.load_warnings]
        assert "LARGE_DRAWING" in warning_codes

    def test_mixed_entities_has_unsupported(self, tmp_path: Path):
        dxf_path = create_mixed_entity_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        # POINT is unsupported, should be recorded
        assert len(ctx.unsupported_entity_types) >= 1

    def test_unicode_text_roundtrip(self, tmp_path: Path):
        dxf_path = create_unicode_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        texts = [e.text_content for e in ctx.entities if e.text_content]
        # Should contain CJK characters
        assert any("\u67f1" in t for t in texts), f"Expected CJK text in {texts}"

    def test_overlapping_entities_all_loaded(self, tmp_path: Path):
        dxf_path = create_overlapping_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        # Multiple entities at same position should all be loaded
        assert ctx.entity_count >= 10

    def test_empty_layers_no_crash(self, tmp_path: Path):
        dxf_path = create_empty_layers_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        pc = build_planner_context(ctx)
        # Should have layers listed even if most are empty
        assert len(pc["layers"]) >= 3
