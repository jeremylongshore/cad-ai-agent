"""Response parser — validates and parses LLM planner output into ChangeSet."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from ..models.ops_schema import ChangeSet, EditOperation

logger = logging.getLogger(__name__)


def parse_planner_response(raw_response: str, prompt: str = "") -> ChangeSet:
    """Parse raw LLM response into a validated ChangeSet.

    Raises ValueError if the response cannot be parsed or validated.
    """
    # Strip markdown code fences if present
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Planner response is not valid JSON: {e}") from e

    if isinstance(data, list):
        # Bare array of operations
        data = {"operations": data, "prompt": prompt}
    elif isinstance(data, dict):
        if "operations" not in data:
            raise ValueError("Planner response missing 'operations' key")
        data.setdefault("prompt", prompt)
    else:
        raise ValueError(f"Unexpected response type: {type(data).__name__}")

    # Validate each operation
    try:
        ops = [EditOperation.model_validate(op) for op in data["operations"]]
    except ValidationError as e:
        raise ValueError(f"Invalid operation in planner response: {e}") from e

    return ChangeSet(
        operations=ops,
        prompt=data.get("prompt", prompt),
        revision_label=data.get("revision_label"),
        message=data.get("message"),
    )
