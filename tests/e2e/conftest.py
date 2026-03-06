"""Conftest for E2E tests — hybrid skip logic for sourced + factory fixtures.

Sourced DXF tests skip gracefully when files are not downloaded.
Factory tests always run (even in CI without downloads).

Download fixtures: bash scripts/download_e2e_fixtures.sh
"""

from __future__ import annotations

from pathlib import Path

import pytest

SOURCED_DIR = Path(__file__).parent.parent / "fixtures" / "e2e_sourced"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

E2E_SKIP_REASON = (
    "E2E sourced DXF not found. Run: bash scripts/download_e2e_fixtures.sh"
)


def _has_sourced_dxfs() -> bool:
    """True if at least one downloaded DXF exists."""
    return SOURCED_DIR.is_dir() and any(SOURCED_DIR.glob("*.dxf"))


def pytest_collection_modifyitems(config, items):
    """Auto-add e2e marker to all tests in this directory."""
    for item in items:
        if "tests/e2e" in str(item.fspath) or "tests\\e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


# ── Sourced DXF accessor ────────────────────────────────────────────


@pytest.fixture
def sourced_dxf():
    """Return a function that resolves a sourced DXF path, skipping if missing."""

    def _get(name: str) -> Path:
        p = SOURCED_DIR / name
        if not p.is_file():
            pytest.skip(f"{name}: {E2E_SKIP_REASON}")
        return p

    return _get


# ── Named sourced fixtures ──────────────────────────────────────────


@pytest.fixture
def gds_mtext_test_dxf(sourced_dxf):
    return sourced_dxf("gds-mtext-test.dxf")


@pytest.fixture
def jscad_texts_dxf(sourced_dxf):
    return sourced_dxf("jscad-texts.dxf")


@pytest.fixture
def jscad_blocks1_dxf(sourced_dxf):
    return sourced_dxf("jscad-blocks1.dxf")


@pytest.fixture
def jscad_blocks2_dxf(sourced_dxf):
    return sourced_dxf("jscad-blocks2.dxf")


@pytest.fixture
def jscad_floorplan_dxf(sourced_dxf):
    return sourced_dxf("jscad-floorplan.dxf")


@pytest.fixture
def jscad_custom_blocks_dxf(sourced_dxf):
    return sourced_dxf("jscad-CustomBlocks.dxf")


@pytest.fixture
def gds_blocks_dxf(sourced_dxf):
    return sourced_dxf("gds-blocks.dxf")


@pytest.fixture
def gds_api_cw750_dxf(sourced_dxf):
    return sourced_dxf("gds-api-cw750.dxf")


# ── Factory fixtures (always available) ─────────────────────────────


@pytest.fixture
def rich_mtext_dxf(tmp_path):
    from tests.helpers.dxf_factory import create_rich_mtext_drawing

    return create_rich_mtext_drawing(tmp_path)


@pytest.fixture
def scaled_insert_dxf(tmp_path):
    from tests.helpers.dxf_factory import create_scaled_insert_drawing

    return create_scaled_insert_drawing(tmp_path)


@pytest.fixture
def structural_dxf(tmp_path):
    from tests.helpers.dxf_factory import create_structural_drawing

    return create_structural_drawing(tmp_path)


# ── Committed fixture paths ─────────────────────────────────────────


@pytest.fixture
def real_columns_master():
    return FIXTURES_DIR / "revision" / "nasty" / "real_columns" / "master.dxf"


@pytest.fixture
def real_columns_revision():
    return FIXTURES_DIR / "revision" / "nasty" / "real_columns" / "revision.dxf"


@pytest.fixture
def r12_basic_dxf():
    return FIXTURES_DIR / "dxf_zoo" / "r12_basic.dxf"


@pytest.fixture
def r2000_blocks_dxf():
    return FIXTURES_DIR / "dxf_zoo" / "r2000_blocks.dxf"


@pytest.fixture
def block_attrib_master():
    return FIXTURES_DIR / "revision" / "nasty" / "block_attrib_changes" / "master.dxf"
