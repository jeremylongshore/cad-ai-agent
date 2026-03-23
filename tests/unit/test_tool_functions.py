"""Tests for ADK-pattern typed tool functions.

Validates that the auto-generated schemas from typed Python functions
match the hand-written dict schemas, ensuring the two representations
stay in sync as we migrate toward ADK.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.tool_definitions import (
    QUERY_TOOL_FUNCTIONS,
    QUERY_TOOLS,
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
        """_tools_as_schemas returns a list of well-formed dicts."""
        schemas = _tools_as_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) == len(QUERY_TOOL_FUNCTIONS)
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
