"""Tests for deterministic selectors — target resolution without LLM."""

from __future__ import annotations

from cad_dxf_agent.core.selectors import (
    resolve_candidate_set,
    resolve_target_by_id,
    resolve_target_nearest_point,
    resolve_targets_by_layer_type,
    resolve_targets_by_text,
)
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityType

# --- resolve_target_by_id ---


def test_resolve_by_id_hit(sample_context):
    """Known handle resolves to the correct entity."""
    handle = sample_context.entities[0].handle
    result = resolve_target_by_id(sample_context, handle)
    assert result is not None
    assert result.handle == handle


def test_resolve_by_id_miss(sample_context):
    """Unknown handle returns None."""
    assert resolve_target_by_id(sample_context, "FFFFF") is None


# --- resolve_targets_by_layer_type ---


def test_resolve_by_layer(sample_context):
    """Resolve by layer returns all entities on that layer."""
    results = resolve_targets_by_layer_type(sample_context, layer="STRUCTURAL")
    assert len(results) == 3


def test_resolve_by_type(sample_context):
    """Resolve by type returns all entities of that type."""
    results = resolve_targets_by_layer_type(sample_context, entity_type="TEXT")
    assert len(results) == 2


def test_resolve_by_layer_and_type(sample_context):
    """Resolve by both layer and type returns intersection."""
    results = resolve_targets_by_layer_type(sample_context, layer="NOTES", entity_type="TEXT")
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_resolve_by_layer_type_no_match(sample_context):
    """No match returns empty list."""
    results = resolve_targets_by_layer_type(sample_context, layer="NOTES", entity_type="LINE")
    assert results == []


# --- resolve_targets_by_text ---


def test_resolve_by_text_match(sample_context):
    """Text query finds matching TEXT/MTEXT entities."""
    results = resolve_targets_by_text(sample_context, "Column")
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_resolve_by_text_case_insensitive(sample_context):
    """Text search is case-insensitive."""
    results = resolve_targets_by_text(sample_context, "footing")
    assert len(results) == 1


def test_resolve_by_text_no_match(sample_context):
    """No text match returns empty list."""
    results = resolve_targets_by_text(sample_context, "nonexistent")
    assert results == []


# --- resolve_target_nearest_point ---


def test_resolve_nearest(sample_context):
    """Nearest to (10, 10) returns the TEXT at that point."""
    result = resolve_target_nearest_point(sample_context, 10.0, 10.0)
    assert result is not None
    assert result.text_content == "Column C-4"


def test_resolve_nearest_with_filters(sample_context):
    """Nearest with type filter restricts candidates."""
    result = resolve_target_nearest_point(sample_context, 10.0, 10.0, entity_type="INSERT")
    assert result is not None
    assert result.entity_type == EntityType.INSERT


def test_resolve_nearest_empty():
    """Nearest on empty context returns None."""
    ctx = DrawingContext(file_path="empty.dxf")
    assert resolve_target_nearest_point(ctx, 0, 0) is None


# --- resolve_candidate_set ---


def test_candidate_set_by_id(sample_context):
    """Candidate set with id hint returns single entity."""
    handle = sample_context.entities[0].handle
    results = resolve_candidate_set(sample_context, {"id": handle})
    assert len(results) == 1
    assert results[0].handle == handle


def test_candidate_set_by_id_miss(sample_context):
    """Candidate set with unknown id returns empty."""
    results = resolve_candidate_set(sample_context, {"id": "FFFFF"})
    assert results == []


def test_candidate_set_by_layer(sample_context):
    """Candidate set filtered by layer."""
    results = resolve_candidate_set(sample_context, {"layer": "STRUCTURAL"})
    assert len(results) == 3


def test_candidate_set_by_text(sample_context):
    """Candidate set filtered by text search."""
    results = resolve_candidate_set(sample_context, {"text": "Column"})
    assert len(results) == 1


def test_candidate_set_combined(sample_context):
    """Candidate set with layer + type + text intersection."""
    results = resolve_candidate_set(
        sample_context,
        {"layer": "NOTES", "type": "TEXT", "text": "Column"},
    )
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_candidate_set_with_spatial(sample_context):
    """Candidate set with near_x/near_y returns nearest match."""
    results = resolve_candidate_set(
        sample_context,
        {"near_x": 10.0, "near_y": 10.0},
    )
    assert len(results) == 1
    assert results[0].text_content == "Column C-4"


def test_candidate_set_spatial_with_layer(sample_context):
    """Spatial + layer filter narrows to nearest on that layer."""
    results = resolve_candidate_set(
        sample_context,
        {"layer": "STRUCTURAL", "near_x": 0.0, "near_y": 0.0},
    )
    assert len(results) == 1
    assert results[0].entity_type in (EntityType.LINE, EntityType.LWPOLYLINE)


def test_candidate_set_empty_hints(sample_context):
    """Empty hints dict returns all entities."""
    results = resolve_candidate_set(sample_context, {})
    assert len(results) == 6


def test_candidate_set_id_takes_priority(sample_context):
    """When id is present and matches, other hints are ignored."""
    handle = sample_context.entities[0].handle
    results = resolve_candidate_set(
        sample_context,
        {"id": handle, "layer": "NONEXISTENT", "text": "nope"},
    )
    assert len(results) == 1
    assert results[0].handle == handle


# --- Stability tests ---


def test_results_are_deterministic(sample_context):
    """Same inputs produce same outputs across multiple calls."""
    r1 = resolve_targets_by_layer_type(sample_context, layer="STRUCTURAL")
    r2 = resolve_targets_by_layer_type(sample_context, layer="STRUCTURAL")
    assert [e.handle for e in r1] == [e.handle for e in r2]


def test_text_search_stable_order(sample_context):
    """Text search returns results in stable insertion order."""
    r1 = resolve_targets_by_text(sample_context, "title")
    r2 = resolve_targets_by_text(sample_context, "title")
    assert [e.handle for e in r1] == [e.handle for e in r2]
