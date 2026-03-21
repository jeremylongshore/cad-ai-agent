"""Tests for _augment_prompt_with_selection() — selection-to-edit binding."""

from __future__ import annotations

import pytest

from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType, Point2D

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")

from web.backend.main import _augment_prompt_with_selection  # noqa: E402


def _make_context(entities: list[EntityRef]) -> DrawingContext:
    return DrawingContext(file_path="test.dxf", entities=entities, layers=[], blocks=[])


def _line_entity(handle: str, layer: str = "WALLS") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.LINE,
        layer=layer,
        insert_point=Point2D(x=10.0, y=20.0),
    )


def _text_entity(handle: str, text: str, layer: str = "NOTES") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.TEXT,
        layer=layer,
        text_content=text,
        insert_point=Point2D(x=5.0, y=15.0),
    )


def _insert_entity(handle: str, block_name: str, layer: str = "FIXTURES") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.INSERT,
        layer=layer,
        block_name=block_name,
        insert_point=Point2D(x=30.0, y=40.0),
    )


class TestAugmentNoSelection:
    def test_none_selected_regions(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", None, ctx)
        assert result == "move it"

    def test_empty_list(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", [], ctx)
        assert result == "move it"

    def test_empty_handles(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", [{"handles": []}], ctx)
        assert result == "move it"

    def test_no_handles_key(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", [{"bounds": {}}], ctx)
        assert result == "move it"


class TestAugmentSingleEntity:
    def test_single_line(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it right", [{"handles": ["A1"]}], ctx)
        assert "[ACTIVE SELECTION]" in result
        assert "[/ACTIVE SELECTION]" in result
        assert 'Handle "A1"' in result
        assert "LINE" in result
        assert "WALLS" in result
        assert "1 entity" in result
        assert result.endswith("move it right")

    def test_includes_coordinates(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", [{"handles": ["A1"]}], ctx)
        assert "at (10.0, 20.0)" in result


class TestAugmentMultiEntity:
    def test_three_entities(self):
        ctx = _make_context(
            [
                _line_entity("A1"),
                _line_entity("A2", layer="DOORS"),
                _line_entity("A3", layer="WINDOWS"),
            ]
        )
        result = _augment_prompt_with_selection(
            "delete these", [{"handles": ["A1", "A2", "A3"]}], ctx
        )
        assert "3 entities" in result
        assert 'Handle "A1"' in result
        assert 'Handle "A2"' in result
        assert 'Handle "A3"' in result
        assert "these entities" in result
        assert result.endswith("delete these")


class TestAugmentUnknownHandles:
    def test_unknown_handle_skipped(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", [{"handles": ["A1", "GONE"]}], ctx)
        assert "[ACTIVE SELECTION]" in result
        assert 'Handle "A1"' in result
        assert "GONE" not in result
        assert "1 entity" in result

    def test_all_unknown_returns_original(self):
        ctx = _make_context([_line_entity("A1")])
        result = _augment_prompt_with_selection("move it", [{"handles": ["GONE1", "GONE2"]}], ctx)
        assert result == "move it"


class TestAugmentEntityTypes:
    def test_text_entity_includes_content(self):
        ctx = _make_context([_text_entity("T1", "ROOM 101")])
        result = _augment_prompt_with_selection("change text", [{"handles": ["T1"]}], ctx)
        assert '"ROOM 101"' in result
        assert "TEXT" in result

    def test_text_truncated_at_60(self):
        long_text = "A" * 100
        ctx = _make_context([_text_entity("T1", long_text)])
        result = _augment_prompt_with_selection("change text", [{"handles": ["T1"]}], ctx)
        # Should contain the truncated version (60 chars)
        assert f'"{long_text[:60]}"' in result
        assert long_text not in result

    def test_insert_entity_includes_block_name(self):
        ctx = _make_context([_insert_entity("B1", "DOOR_36")])
        result = _augment_prompt_with_selection("move it", [{"handles": ["B1"]}], ctx)
        assert "(DOOR_36)" in result
        assert "INSERT" in result


class TestAugmentPreservesPrompt:
    def test_original_prompt_at_end(self):
        ctx = _make_context([_line_entity("A1")])
        original = "move the selected item 10 feet to the right"
        result = _augment_prompt_with_selection(original, [{"handles": ["A1"]}], ctx)
        assert result.endswith(original)
        # The selection block is prepended, not appended
        assert result.index("[ACTIVE SELECTION]") < result.index(original)


class TestAugmentSelectionCap:
    """Fix 1: selection capped at MAX_SELECTION_ENTITIES (50)."""

    def test_augment_caps_at_50(self):
        """100 entities → only first 50 listed + 'and 50 more' note."""
        entities = [_line_entity(f"E{i}", layer=f"LAYER{i}") for i in range(100)]
        ctx = _make_context(entities)
        handles = [f"E{i}" for i in range(100)]
        result = _augment_prompt_with_selection("move them", [{"handles": handles}], ctx)
        assert "[ACTIVE SELECTION]" in result
        assert "100 entities" in result
        # First 50 should be present
        assert 'Handle "E0"' in result
        assert 'Handle "E49"' in result
        # 51st should NOT be listed individually
        assert 'Handle "E50"' not in result
        # Truncation note
        assert "50 more" in result
        assert "showing first 50" in result

    def test_augment_exactly_50_no_truncation(self):
        """Exactly 50 entities → all listed, no truncation note."""
        entities = [_line_entity(f"E{i}") for i in range(50)]
        ctx = _make_context(entities)
        handles = [f"E{i}" for i in range(50)]
        result = _augment_prompt_with_selection("move them", [{"handles": handles}], ctx)
        assert "[ACTIVE SELECTION]" in result
        assert "50 entities" in result
        assert 'Handle "E0"' in result
        assert 'Handle "E49"' in result
        assert "more" not in result
        assert "showing first" not in result


class TestAugmentProtectedLayers:
    """Fix 2: entities on protected layers are flagged in the selection block."""

    def test_augment_protected_layer_flagged(self):
        """Entity on TITLE layer → description includes [PROTECTED]."""
        ctx = _make_context([_line_entity("T1", layer="TITLE")])
        result = _augment_prompt_with_selection("move it", [{"handles": ["T1"]}], ctx)
        assert "[PROTECTED" in result
        assert "cannot be edited" in result
        assert "MUST NOT be targeted" in result

    def test_augment_mixed_protected_and_editable(self):
        """One protected + one editable → only the protected one flagged."""
        ctx = _make_context(
            [
                _line_entity("T1", layer="TITLE"),
                _line_entity("W1", layer="WALLS"),
            ]
        )
        result = _augment_prompt_with_selection("move them", [{"handles": ["T1", "W1"]}], ctx)
        # Protected entity should have the flag
        assert "[PROTECTED" in result
        # Check that WALLS entity line does NOT have the protected flag
        lines = result.split("\n")
        for line in lines:
            if "WALLS" in line and "Handle" in line:
                assert "PROTECTED" not in line
            if "TITLE" in line and "Handle" in line:
                assert "PROTECTED" in line

    def test_augment_no_protected_no_instruction(self):
        """No protected entities in selection → no MUST NOT instruction."""
        ctx = _make_context([_line_entity("W1", layer="WALLS")])
        result = _augment_prompt_with_selection("move it", [{"handles": ["W1"]}], ctx)
        assert "MUST NOT" not in result
