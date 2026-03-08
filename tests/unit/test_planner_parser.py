"""Tests for planner response parsing."""

from __future__ import annotations

import json

import pytest

from cad_dxf_agent.llm.response_parser import parse_planner_response
from cad_dxf_agent.models.ops_schema import OpType


class TestResponseParser:
    def test_parse_valid_json(self):
        response = json.dumps(
            {
                "operations": [
                    {
                        "op_type": "move_entity",
                        "target_handle": "A1",
                        "params": {"dx": 10, "dy": 5},
                    }
                ],
                "revision_label": "Column shift",
            }
        )

        changeset = parse_planner_response(response, prompt="test")
        assert changeset.op_count == 1
        assert changeset.operations[0].op_type == OpType.MOVE_ENTITY
        assert changeset.revision_label == "Column shift"

    def test_parse_bare_array(self):
        response = json.dumps(
            [
                {
                    "op_type": "delete_entity",
                    "target_handle": "B2",
                }
            ]
        )

        changeset = parse_planner_response(response, prompt="delete it")
        assert changeset.op_count == 1
        assert changeset.operations[0].op_type == OpType.DELETE_ENTITY

    def test_parse_with_code_fences(self):
        response = """```json
{
  "operations": [
    {"op_type": "edit_text", "target_handle": "C3", "params": {"new_text": "Updated"}}
  ]
}
```"""

        changeset = parse_planner_response(response)
        assert changeset.op_count == 1
        assert changeset.operations[0].params["new_text"] == "Updated"

    def test_reject_invalid_json(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_planner_response("this is not json")

    def test_reject_missing_operations(self):
        with pytest.raises(ValueError, match="missing 'operations'"):
            parse_planner_response(json.dumps({"result": "ok"}))

    def test_reject_invalid_op_type(self):
        payload = {"operations": [{"op_type": "explode_entity", "target_handle": "A1"}]}
        response = json.dumps(payload)
        with pytest.raises(ValueError, match="Invalid operation"):
            parse_planner_response(response)
