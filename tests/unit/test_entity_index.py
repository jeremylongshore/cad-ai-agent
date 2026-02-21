"""Tests for EntityIndex — deterministic lookup by handle, layer, type, text, and proximity."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityType,
)

# --- Fixtures ---


@pytest.fixture
def entity_index(sample_context):
    """Build an EntityIndex from the standard sample_context."""
    return EntityIndex(sample_context)


# --- I-01: Lookup by handle succeeds ---


def test_get_by_handle_hit(entity_index, sample_context):
    """Known handle returns the correct EntityRef."""
    # Pick the first entity's handle from sample_context
    expected = sample_context.entities[0]
    result = entity_index.get_by_handle(expected.handle)
    assert result is not None
    assert result.handle == expected.handle
    assert result.entity_type == expected.entity_type


# --- I-02: Lookup by handle miss ---


def test_get_by_handle_miss(entity_index):
    """Unknown handle returns None."""
    assert entity_index.get_by_handle("FFFFF") is None


# --- get_by_id alias ---


def test_get_by_id_is_alias(entity_index, sample_context):
    """get_by_id is an alias for get_by_handle."""
    handle = sample_context.entities[0].handle
    assert entity_index.get_by_id(handle) is entity_index.get_by_handle(handle)


# --- I-03: Lookup by layer returns correct subset ---


def test_get_by_layer_structural(entity_index):
    """STRUCTURAL layer returns LINE, LWPOLYLINE, INSERT, CIRCLE, ARC."""
    results = entity_index.get_by_layer("STRUCTURAL")
    types = {e.entity_type for e in results}
    assert EntityType.LINE in types
    assert EntityType.LWPOLYLINE in types
    assert EntityType.INSERT in types
    assert EntityType.CIRCLE in types
    assert EntityType.ARC in types
    assert len(results) == 5


# --- I-04: Lookup by layer is case-insensitive ---


def test_get_by_layer_case_insensitive(entity_index):
    """Lowercase layer name returns same results as uppercase."""
    upper = entity_index.get_by_layer("STRUCTURAL")
    lower = entity_index.get_by_layer("structural")
    mixed = entity_index.get_by_layer("Structural")
    assert len(upper) == len(lower) == len(mixed)
    assert {e.handle for e in upper} == {e.handle for e in lower}


# --- I-05: Lookup by type ---


def test_get_by_type_text(entity_index):
    """TEXT type returns both TEXT entities (NOTES + TITLE)."""
    results = entity_index.get_by_type(EntityType.TEXT)
    assert len(results) == 2
    assert all(e.entity_type == EntityType.TEXT for e in results)


# --- I-06: Handles list complete ---


def test_handles_complete(entity_index, sample_context):
    """Handles list length matches entity count."""
    assert len(entity_index.handles()) == sample_context.entity_count


# --- I-07: Count property ---


def test_count_property(entity_index, sample_context):
    """Count matches entity_count of the source context."""
    assert entity_index.count == sample_context.entity_count
    assert entity_index.count == 9


# --- filter() combined layer + type ---


def test_filter_layer_and_type(entity_index):
    """Filter by both layer and type returns intersection."""
    results = entity_index.filter(layer="NOTES", entity_type="TEXT")
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_filter_layer_only(entity_index):
    """Filter by layer only returns all entities on that layer."""
    results = entity_index.filter(layer="NOTES")
    assert len(results) == 3  # TEXT + MTEXT + DIMENSION


def test_filter_type_only(entity_index):
    """Filter by type only returns all entities of that type."""
    results = entity_index.filter(entity_type="LINE")
    assert len(results) == 1


def test_filter_no_args(entity_index):
    """Filter with no args returns all entities."""
    results = entity_index.filter()
    assert len(results) == 9


def test_filter_invalid_type(entity_index):
    """Filter with invalid entity type returns empty list."""
    results = entity_index.filter(entity_type="VIEWPORT")
    assert results == []


# --- search_text() ---


def test_search_text_exact_match(entity_index):
    """Search for exact text content finds the entity."""
    results = entity_index.search_text("Column C-4")
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_search_text_partial_token(entity_index):
    """Search for a single token finds matching entities."""
    results = entity_index.search_text("column")
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_search_text_case_insensitive(entity_index):
    """Text search is case-insensitive."""
    results = entity_index.search_text("FOOTING")
    assert len(results) == 1
    assert results[0].text_content == "Footing detail note"


def test_search_text_multi_token(entity_index):
    """Search with multiple tokens requires all tokens present."""
    results = entity_index.search_text("footing detail")
    assert len(results) == 1
    results_miss = entity_index.search_text("footing column")
    assert len(results_miss) == 0


def test_search_text_empty_query(entity_index):
    """Empty query returns no results."""
    assert entity_index.search_text("") == []


def test_search_text_no_match(entity_index):
    """Query with no matching tokens returns empty."""
    assert entity_index.search_text("nonexistent") == []


# --- nearest() ---


def test_nearest_exact_point(entity_index):
    """Nearest to an exact insert_point returns that entity."""
    result = entity_index.nearest(10.0, 10.0)
    assert result is not None
    assert result.text_content == "Column C-4"


def test_nearest_with_type_filter(entity_index):
    """Nearest with type filter restricts candidates."""
    result = entity_index.nearest(10.0, 10.0, entity_type="INSERT")
    assert result is not None
    assert result.entity_type == EntityType.INSERT
    assert result.block_name == "COLUMN_MARK"


def test_nearest_with_layer_filter(entity_index):
    """Nearest with layer filter restricts candidates."""
    result = entity_index.nearest(0.0, 0.0, layer="NOTES")
    assert result is not None
    assert result.layer == "NOTES"


def test_nearest_returns_none_when_no_candidates():
    """Nearest returns None when no entities have insert_point."""
    ctx = DrawingContext(file_path="empty.dxf", entities=[], layers=[])
    index = EntityIndex(ctx)
    assert index.nearest(0, 0) is None


# --- Empty context ---


def test_empty_context():
    """EntityIndex built from empty context works without error."""
    ctx = DrawingContext(file_path="empty.dxf", entities=[], layers=[])
    index = EntityIndex(ctx)
    assert index.count == 0
    assert index.handles() == []
    assert index.get_by_handle("any") is None
    assert index.get_by_layer("any") == []
    assert index.search_text("any") == []
    assert index.nearest(0, 0) is None


# --- get_by_layer returns empty list for unknown layer ---


def test_get_by_layer_unknown(entity_index):
    """Unknown layer returns empty list, not None."""
    result = entity_index.get_by_layer("NONEXISTENT")
    assert result == []
    assert isinstance(result, list)
