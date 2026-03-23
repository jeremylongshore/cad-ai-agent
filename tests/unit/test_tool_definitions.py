"""Tests for CAD tool definitions."""

from __future__ import annotations

from cad_dxf_agent.llm.tool_definitions import (
    ALL_TOOLS,
    EDIT_TOOLS,
    QUERY_TOOLS,
    get_tool_by_name,
    get_tools_for_request_class,
    is_edit_tool,
)


class TestToolDefinitions:
    """Verify tool schemas are well-formed and complete."""

    def test_all_tools_have_required_fields(self):
        for tool in ALL_TOOLS:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing 'description'"
            assert "parameters" in tool, f"Tool {tool['name']} missing 'parameters'"
            params = tool["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_tool_names_unique(self):
        names = [t["name"] for t in ALL_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_query_vs_edit_partition(self):
        query_names = {t["name"] for t in QUERY_TOOLS}
        edit_names = {t["name"] for t in EDIT_TOOLS}
        all_names = {t["name"] for t in ALL_TOOLS}
        assert query_names | edit_names == all_names
        assert query_names & edit_names == set()

    def test_get_tool_by_name_found(self):
        tool = get_tool_by_name("find_entities")
        assert tool is not None
        assert tool["name"] == "find_entities"

    def test_get_tool_by_name_not_found(self):
        assert get_tool_by_name("nonexistent") is None

    def test_is_edit_tool(self):
        assert is_edit_tool("move_entity")
        assert is_edit_tool("edit_text")
        assert is_edit_tool("delete_entity")
        assert is_edit_tool("add_block")
        assert not is_edit_tool("find_entities")
        assert not is_edit_tool("list_layers")
        assert not is_edit_tool("nonexistent")

    def test_expected_query_tools(self):
        names = {t["name"] for t in QUERY_TOOLS}
        expected = {"find_entities", "get_entity", "find_nearest", "list_layers", "is_protected"}
        assert names == expected

    def test_expected_edit_tools(self):
        names = {t["name"] for t in EDIT_TOOLS}
        expected = {
            # V1
            "move_entity",
            "edit_text",
            "delete_entity",
            "add_block",
            # V2 transforms
            "rotate_entity",
            "copy_entity",
            "scale_entity",
            "mirror_entity",
            # V2 creation
            "add_line",
            "add_polyline",
            "add_circle",
            "add_arc",
            "add_text",
            # V3 batch
            "batch_move",
            "batch_rotate",
            "batch_scale",
            "batch_delete",
            "batch_edit_text",
        }
        assert names == expected

    def test_move_entity_params(self):
        tool = get_tool_by_name("move_entity")
        assert tool is not None
        props = tool["parameters"]["properties"]
        assert "handle" in props
        assert "dx" in props
        assert "dy" in props
        assert set(tool["parameters"]["required"]) == {"handle", "dx", "dy"}

    def test_find_entities_no_required_params(self):
        tool = get_tool_by_name("find_entities")
        assert tool is not None
        assert tool["parameters"]["required"] == []


class TestToolNarrowing:
    """Verify request_class → tool subset mapping."""

    def test_modify_gets_all_tools(self):
        tools = get_tools_for_request_class("modify")
        assert tools == ALL_TOOLS

    def test_non_modify_gets_query_only(self):
        for rc in ("understand", "estimate", "recommend", "optimize",
                    "summarize", "compare", "validate"):
            tools = get_tools_for_request_class(rc)
            assert tools == QUERY_TOOLS, f"{rc} should get QUERY_TOOLS only"
            # Verify no edit tools leak through
            tool_names = {t["name"] for t in tools}
            edit_names = {t["name"] for t in EDIT_TOOLS}
            assert tool_names & edit_names == set(), f"Edit tools in {rc}"

    def test_query_tools_always_present(self):
        """Every request class gets at least the query tools."""
        for rc in ("modify", "understand", "estimate", "recommend",
                    "optimize", "summarize", "compare", "validate"):
            tools = get_tools_for_request_class(rc)
            tool_names = {t["name"] for t in tools}
            query_names = {t["name"] for t in QUERY_TOOLS}
            assert query_names.issubset(tool_names), f"Missing query tools in {rc}"

    def test_unknown_request_class_gets_query_only(self):
        """Unknown/future request classes default to query-only (safe)."""
        tools = get_tools_for_request_class("unknown_future_class")
        assert tools == QUERY_TOOLS
