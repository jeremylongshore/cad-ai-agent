"""Tests for ADK-pattern typed tool functions.

Validates that the auto-generated schemas from typed Python functions
match the hand-written dict schemas, ensuring the two representations
stay in sync as we migrate toward ADK.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.tool_definitions import (
    ALL_TOOLS,
    EDIT_TOOL_FUNCTIONS,
    EDIT_TOOLS,
    QUERY_TOOL_FUNCTIONS,
    QUERY_TOOLS,
    ToolPoint2D,
    _fn_to_tool_schema,
    _hint_to_json_schema,
    _tools_as_schemas,
)


class TestToolFunctionSchemas:
    """Verify typed functions produce equivalent schemas to hand-written dicts."""

    def test_query_tool_count_matches(self):
        """Same number of query tools in both representations."""
        assert len(QUERY_TOOL_FUNCTIONS) == len(QUERY_TOOLS)

    def test_tool_names_match(self):
        """Function names (minus _fn suffix) match dict names."""
        fn_names = {fn.__name__.removesuffix("_fn") for fn in QUERY_TOOL_FUNCTIONS}
        dict_names = {t["name"] for t in QUERY_TOOLS}
        assert fn_names == dict_names

    def test_required_params_match(self):
        """Required parameters match between typed functions and dicts."""
        for fn in QUERY_TOOL_FUNCTIONS:
            schema = _fn_to_tool_schema(fn)
            name = schema["name"]
            dict_schema = next(t for t in QUERY_TOOLS if t["name"] == name)
            assert set(schema["parameters"]["required"]) == set(
                dict_schema["parameters"]["required"]
            ), f"Required params mismatch for {name}"

    def test_parameter_names_match(self):
        """Parameter names match between typed functions and dicts."""
        for fn in QUERY_TOOL_FUNCTIONS:
            schema = _fn_to_tool_schema(fn)
            name = schema["name"]
            dict_schema = next(t for t in QUERY_TOOLS if t["name"] == name)
            fn_params = set(schema["parameters"]["properties"].keys())
            dict_params = set(dict_schema["parameters"]["properties"].keys())
            assert fn_params == dict_params, f"Param names mismatch for {name}"

    def test_all_functions_have_docstrings(self):
        """Every tool function has a docstring."""
        for fn in QUERY_TOOL_FUNCTIONS:
            assert fn.__doc__, f"{fn.__name__} missing docstring"

    def test_tools_as_schemas_returns_list(self):
        """_tools_as_schemas returns a list of well-formed dicts covering all tool functions."""
        schemas = _tools_as_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) == len(QUERY_TOOL_FUNCTIONS) + len(EDIT_TOOL_FUNCTIONS)
        for s in schemas:
            assert "name" in s
            assert "description" in s
            assert "parameters" in s

    def test_schema_description_not_empty(self):
        """Auto-generated descriptions are non-trivially long."""
        for fn in QUERY_TOOL_FUNCTIONS:
            schema = _fn_to_tool_schema(fn)
            assert len(schema["description"]) > 10, (
                f"{schema['name']} has a suspiciously short description"
            )

    def test_schemas_have_type_object_parameters(self):
        """Every generated schema has parameters.type == 'object'."""
        for schema in _tools_as_schemas():
            assert schema["parameters"]["type"] == "object", (
                f"{schema['name']} parameters.type is not 'object'"
            )

    def test_functions_raise_not_implemented(self):
        """Stub functions raise NotImplementedError — dispatch stays in ToolExecutor."""
        from cad_dxf_agent.llm.tool_definitions import (
            find_entities_fn,
            find_nearest_fn,
            get_entity_fn,
            is_protected_fn,
            list_layers_fn,
        )

        with pytest.raises(NotImplementedError):
            find_entities_fn()
        with pytest.raises(NotImplementedError):
            get_entity_fn("somehandle")
        with pytest.raises(NotImplementedError):
            find_nearest_fn(0.0, 0.0)
        with pytest.raises(NotImplementedError):
            list_layers_fn()
        with pytest.raises(NotImplementedError):
            is_protected_fn("STRUCTURAL")

    def test_fn_name_suffix_stripped(self):
        """_fn suffix is stripped when deriving the tool name."""
        from cad_dxf_agent.llm.tool_definitions import find_entities_fn

        schema = _fn_to_tool_schema(find_entities_fn)
        assert schema["name"] == "find_entities"
        assert not schema["name"].endswith("_fn")

    def test_optional_params_are_not_required(self):
        """Optional parameters (default=None) are absent from required list."""
        from cad_dxf_agent.llm.tool_definitions import find_entities_fn

        schema = _fn_to_tool_schema(find_entities_fn)
        # All four params of find_entities_fn have defaults, so required must be empty.
        assert schema["parameters"]["required"] == []

    def test_positional_params_are_required(self):
        """Params without defaults appear in the required list."""
        from cad_dxf_agent.llm.tool_definitions import get_entity_fn, is_protected_fn

        for fn, expected_required in [
            (get_entity_fn, {"handle"}),
            (is_protected_fn, {"layer"}),
        ]:
            schema = _fn_to_tool_schema(fn)
            assert set(schema["parameters"]["required"]) == expected_required, (
                f"{fn.__name__}: required mismatch"
            )

    def test_find_nearest_required_coords(self):
        """find_nearest requires x and y, the rest are optional."""
        from cad_dxf_agent.llm.tool_definitions import find_nearest_fn

        schema = _fn_to_tool_schema(find_nearest_fn)
        assert set(schema["parameters"]["required"]) == {"x", "y"}

    def test_list_layers_has_no_parameters(self):
        """list_layers has no parameters and empty required list."""
        from cad_dxf_agent.llm.tool_definitions import list_layers_fn

        schema = _fn_to_tool_schema(list_layers_fn)
        assert schema["parameters"]["properties"] == {}
        assert schema["parameters"]["required"] == []

    def test_param_descriptions_populated(self):
        """Parameters documented in Args: section have description fields."""
        from cad_dxf_agent.llm.tool_definitions import find_entities_fn, get_entity_fn

        for fn in (find_entities_fn, get_entity_fn):
            schema = _fn_to_tool_schema(fn)
            for pname, prop in schema["parameters"]["properties"].items():
                assert "description" in prop, (
                    f"{fn.__name__}.{pname} missing description in generated schema"
                )


class TestHintToJsonSchema:
    """Unit tests for the _hint_to_json_schema helper."""

    def test_str(self):
        assert _hint_to_json_schema(str) == {"type": "string"}

    def test_int(self):
        assert _hint_to_json_schema(int) == {"type": "integer"}

    def test_float(self):
        assert _hint_to_json_schema(float) == {"type": "number"}

    def test_bool(self):
        assert _hint_to_json_schema(bool) == {"type": "boolean"}

    def test_dict(self):
        assert _hint_to_json_schema(dict) == {"type": "object"}

    def test_list(self):
        assert _hint_to_json_schema(list) == {"type": "array"}

    def test_optional_str(self):
        """str | None collapses to string schema."""
        hint = str | None
        assert _hint_to_json_schema(hint) == {"type": "string"}

    def test_optional_float(self):
        """float | None collapses to number schema."""
        hint = float | None
        assert _hint_to_json_schema(hint) == {"type": "number"}

    def test_optional_int(self):
        """int | None collapses to integer schema."""
        hint = int | None
        assert _hint_to_json_schema(hint) == {"type": "integer"}

    def test_unknown_falls_back_to_string(self):
        """Unrecognised types fall back to string schema without raising."""

        class _Custom:
            pass

        result = _hint_to_json_schema(_Custom)
        assert result == {"type": "string"}


class TestEditToolFunctionSchemas:
    """Verify edit typed functions produce equivalent schemas to hand-written dicts."""

    def test_edit_tool_count_matches(self):
        """Same number of edit tool functions and edit tool dicts (should be 18)."""
        assert len(EDIT_TOOL_FUNCTIONS) == len(EDIT_TOOLS)
        assert len(EDIT_TOOL_FUNCTIONS) == 18

    def test_edit_tool_names_match(self):
        """Function names (minus _fn suffix) match dict names for edit tools."""
        fn_names = {fn.__name__.removesuffix("_fn") for fn in EDIT_TOOL_FUNCTIONS}
        dict_names = {t["name"] for t in EDIT_TOOLS}
        assert fn_names == dict_names

    def test_edit_required_params_match(self):
        """Required parameters match between typed edit functions and dicts."""
        for fn in EDIT_TOOL_FUNCTIONS:
            schema = _fn_to_tool_schema(fn)
            name = schema["name"]
            dict_schema = next(t for t in EDIT_TOOLS if t["name"] == name)
            assert set(schema["parameters"]["required"]) == set(
                dict_schema["parameters"]["required"]
            ), f"Required params mismatch for {name}"

    def test_edit_parameter_names_match(self):
        """Parameter names match between typed edit functions and dicts."""
        for fn in EDIT_TOOL_FUNCTIONS:
            schema = _fn_to_tool_schema(fn)
            name = schema["name"]
            dict_schema = next(t for t in EDIT_TOOLS if t["name"] == name)
            fn_params = set(schema["parameters"]["properties"].keys())
            dict_params = set(dict_schema["parameters"]["properties"].keys())
            assert fn_params == dict_params, f"Param names mismatch for {name}"

    def test_all_edit_functions_have_docstrings(self):
        """Every edit tool function has a docstring."""
        for fn in EDIT_TOOL_FUNCTIONS:
            assert fn.__doc__, f"{fn.__name__} missing docstring"

    def test_edit_schema_descriptions_not_empty(self):
        """All auto-generated edit tool descriptions are non-trivially long."""
        for fn in EDIT_TOOL_FUNCTIONS:
            schema = _fn_to_tool_schema(fn)
            assert len(schema["description"]) > 10, (
                f"{schema['name']} has a suspiciously short description"
            )

    def test_edit_functions_raise_not_implemented(self):
        """All 18 edit stub functions raise NotImplementedError."""
        from cad_dxf_agent.llm.tool_definitions import (
            add_arc_fn,
            add_block_fn,
            add_circle_fn,
            add_line_fn,
            add_polyline_fn,
            add_text_fn,
            batch_delete_fn,
            batch_edit_text_fn,
            batch_move_fn,
            batch_rotate_fn,
            batch_scale_fn,
            copy_entity_fn,
            delete_entity_fn,
            edit_text_fn,
            mirror_entity_fn,
            move_entity_fn,
            rotate_entity_fn,
            scale_entity_fn,
        )

        stubs_and_args: list[tuple] = [
            (move_entity_fn, ("abc", 1.0, 2.0)),
            (edit_text_fn, ("abc", "new")),
            (delete_entity_fn, ("abc",)),
            (add_block_fn, ("DOOR", 0.0, 0.0)),
            (rotate_entity_fn, ("abc", 90.0)),
            (copy_entity_fn, ("abc", 5.0, 0.0)),
            (scale_entity_fn, ("abc", 2.0)),
            (mirror_entity_fn, ("abc", "x")),
            (add_line_fn, (ToolPoint2D(0, 0), ToolPoint2D(10, 0))),
            (add_polyline_fn, ([ToolPoint2D(0, 0), ToolPoint2D(5, 5)],)),
            (add_circle_fn, (ToolPoint2D(0, 0), 5.0)),
            (add_arc_fn, (ToolPoint2D(0, 0), 5.0, 0.0, 90.0)),
            (add_text_fn, ("hello", ToolPoint2D(0, 0))),
            (batch_move_fn, (1.0, 2.0)),
            (batch_rotate_fn, (45.0,)),
            (batch_scale_fn, (2.0,)),
            (batch_delete_fn, ()),
            (batch_edit_text_fn, ("old", "new")),
        ]

        for fn, args in stubs_and_args:
            with pytest.raises(NotImplementedError):
                fn(*args)

    def test_all_tools_typed(self):
        """Critical CI gate: every tool in ALL_TOOLS has a corresponding typed stub.

        len(EDIT_TOOL_FUNCTIONS) + len(QUERY_TOOL_FUNCTIONS) must equal len(ALL_TOOLS).
        This ensures that as new tools are added to the hand-written dicts, typed
        stubs are added as well.
        """
        assert len(EDIT_TOOL_FUNCTIONS) + len(QUERY_TOOL_FUNCTIONS) == len(ALL_TOOLS)


class TestSchemaEdgeCases:
    """Edge-case coverage for _hint_to_json_schema and _fn_to_tool_schema."""

    def test_literal_type_produces_enum(self):
        """typing.Literal['x', 'y'] produces a string enum schema."""
        from typing import Literal

        hint = Literal["x", "y"]
        result = _hint_to_json_schema(hint)
        assert result["type"] == "string"
        assert result["enum"] == ["x", "y"]

    def test_literal_entity_types(self):
        """A full entity-type Literal produces the correct enum list."""
        from typing import Literal

        hint = Literal["LINE", "LWPOLYLINE", "TEXT", "MTEXT", "INSERT", "CIRCLE", "ARC"]
        result = _hint_to_json_schema(hint)
        assert "enum" in result
        assert "LINE" in result["enum"]
        assert len(result["enum"]) == 7

    def test_dataclass_produces_object_schema(self):
        """ToolPoint2D dataclass produces a nested object schema with x and y."""
        result = _hint_to_json_schema(ToolPoint2D)
        assert result["type"] == "object"
        assert "x" in result["properties"]
        assert "y" in result["properties"]
        assert result["properties"]["x"]["type"] == "number"
        assert result["properties"]["y"]["type"] == "number"

    def test_list_str_produces_array_schema(self):
        """list[str] produces an array schema with string items."""
        result = _hint_to_json_schema(list[str])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_list_dataclass_produces_array_of_objects(self):
        """list[ToolPoint2D] produces an array-of-objects schema."""
        result = _hint_to_json_schema(list[ToolPoint2D])
        assert result["type"] == "array"
        assert result["items"]["type"] == "object"
        assert "x" in result["items"]["properties"]
        assert "y" in result["items"]["properties"]

    def test_colon_in_description_edge_case(self):
        """A colon inside a param description line is not treated as a new parameter."""

        def _colon_test_fn(mode: str) -> dict:
            """Test function.

            Args:
                mode: The mode to use. Note: case-insensitive matching is applied
            """
            raise NotImplementedError

        schema = _fn_to_tool_schema(_colon_test_fn)
        desc = schema["parameters"]["properties"]["mode"]["description"]
        assert "Note:" in desc  # The colon should not split the description

    def test_function_with_no_args_section(self):
        """A function with a docstring but no Args: section produces empty properties."""

        def _no_args_fn() -> dict:
            """A function with no parameters."""
            raise NotImplementedError

        schema = _fn_to_tool_schema(_no_args_fn)
        assert schema["parameters"]["properties"] == {}
        assert schema["parameters"]["required"] == []

    def test_list_str_type_hint(self):
        """A list[str] parameter in a function generates an array schema."""

        def _list_fn(tags: list[str]) -> dict:
            """A function with a list param.

            Args:
                tags: Tag strings to apply
            """
            raise NotImplementedError

        schema = _fn_to_tool_schema(_list_fn)
        tags_prop = schema["parameters"]["properties"]["tags"]
        assert tags_prop["type"] == "array"
        assert tags_prop["items"] == {"type": "string"}
        assert "tags" in schema["parameters"]["required"]
