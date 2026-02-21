"""Tests for context builder — full/subset serialization and token-economy summaries."""

from __future__ import annotations

from cad_dxf_agent.core.context_builder import (
    full_context,
    subset_context,
    token_economy_summary,
)
from cad_dxf_agent.models.cad_schema import DrawingContext

# --- full_context ---


def test_full_context_has_all_fields(sample_context):
    """Full context includes all required top-level keys."""
    result = full_context(sample_context)
    assert "file_path" in result
    assert "entity_count" in result
    assert "layers" in result
    assert "entities" in result
    assert "blocks" in result
    assert "summary" in result
    assert "metadata" in result


def test_full_context_entity_count(sample_context):
    """Full context entity count matches source."""
    result = full_context(sample_context)
    assert result["entity_count"] == 9


def test_full_context_entities_serialized(sample_context):
    """Full context serializes all entities as dicts with expected keys."""
    result = full_context(sample_context)
    assert len(result["entities"]) == 9
    entity = result["entities"][0]
    assert "handle" in entity
    assert "type" in entity
    assert "layer" in entity
    assert "insert_point" in entity


def test_full_context_layers_have_counts(sample_context):
    """Layer summaries include entity counts."""
    result = full_context(sample_context)
    structural = next(lr for lr in result["layers"] if lr["name"] == "STRUCTURAL")
    assert structural["entity_count"] == 5  # LINE + LWPOLYLINE + INSERT + CIRCLE + ARC


def test_full_context_includes_blocks(sample_context):
    """Full context includes block names."""
    result = full_context(sample_context)
    assert "COLUMN_MARK" in result["blocks"]


def test_full_context_summary_embedded(sample_context):
    """Full context embeds token-economy summary."""
    result = full_context(sample_context)
    summary = result["summary"]
    assert "entity_count" in summary
    assert "counts_by_layer" in summary
    assert "counts_by_type" in summary
    assert "top_text_labels" in summary


# --- subset_context ---


def test_subset_by_entity_ids(sample_context):
    """Subset context filtered by entity_ids returns only those entities."""
    handles = [sample_context.entities[0].handle, sample_context.entities[1].handle]
    result = subset_context(sample_context, entity_ids=handles)
    assert result["entity_count"] == 2
    assert result["total_entity_count"] == 9


def test_subset_by_layer(sample_context):
    """Subset context filtered by layer returns entities on that layer."""
    result = subset_context(sample_context, layers=["NOTES"])
    assert result["entity_count"] == 3  # TEXT + MTEXT + DIMENSION on NOTES


def test_subset_by_entity_type(sample_context):
    """Subset context filtered by entity type returns matching entities."""
    result = subset_context(sample_context, entity_types=["TEXT"])
    assert result["entity_count"] == 2  # TEXT on NOTES + TEXT on TITLE


def test_subset_by_spatial_radius(sample_context):
    """Subset context filtered by spatial radius returns nearby entities."""
    # Center at (10, 10) with radius=5 should get the TEXT at (10,10)
    result = subset_context(sample_context, center=(10.0, 10.0), radius=5.0)
    assert result["entity_count"] >= 1
    types = {e["type"] for e in result["entities"]}
    assert "TEXT" in types


def test_subset_combined_filters(sample_context):
    """Subset with multiple filters returns intersection."""
    result = subset_context(
        sample_context,
        layers=["NOTES"],
        entity_types=["TEXT"],
    )
    assert result["entity_count"] == 1
    assert result["entities"][0]["text"] == "Column C-4"


def test_subset_no_filters_returns_all(sample_context):
    """Subset with no filters returns all entities."""
    result = subset_context(sample_context)
    assert result["entity_count"] == 9


def test_subset_has_summary(sample_context):
    """Subset context includes a summary section."""
    result = subset_context(sample_context, layers=["STRUCTURAL"])
    assert "summary" in result
    assert result["summary"]["selected_count"] == 5
    assert result["summary"]["total_count"] == 9


# --- token_economy_summary ---


def test_token_economy_entity_count(sample_context):
    """Summary reports correct entity count."""
    summary = token_economy_summary(sample_context)
    assert summary["entity_count"] == 9


def test_token_economy_counts_by_layer(sample_context):
    """Summary breaks down counts by layer."""
    summary = token_economy_summary(sample_context)
    assert summary["counts_by_layer"]["STRUCTURAL"] == 5
    assert summary["counts_by_layer"]["NOTES"] == 3
    assert summary["counts_by_layer"]["TITLE"] == 1


def test_token_economy_counts_by_type(sample_context):
    """Summary breaks down counts by entity type."""
    summary = token_economy_summary(sample_context)
    assert summary["counts_by_type"]["TEXT"] == 2
    assert summary["counts_by_type"]["LINE"] == 1


def test_token_economy_top_text_labels(sample_context):
    """Summary includes top text labels from TEXT/MTEXT entities."""
    summary = token_economy_summary(sample_context)
    labels = summary["top_text_labels"]
    assert "Column C-4" in labels
    assert "Footing detail note" in labels
    assert "PROJECT TITLE" in labels


def test_token_economy_protected_layers(sample_context):
    """Summary lists protected layers."""
    summary = token_economy_summary(sample_context)
    protected = summary["protected_layers"]
    assert "TITLE" in protected
    assert "TITLEBLOCK" in protected
    assert "SEAL" in protected
    assert "REVISION" in protected


def test_token_economy_block_count(sample_context):
    """Summary reports block count."""
    summary = token_economy_summary(sample_context)
    assert summary["block_count"] >= 1  # COLUMN_MARK + dimension geometry block


def test_token_economy_empty_context():
    """Summary handles empty context gracefully."""
    ctx = DrawingContext(file_path="empty.dxf")
    summary = token_economy_summary(ctx)
    assert summary["entity_count"] == 0
    assert summary["counts_by_layer"] == {}
    assert summary["top_text_labels"] == []
