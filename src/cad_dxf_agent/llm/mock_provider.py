"""Mock planner provider — returns deterministic operations for testing without an API key."""

from __future__ import annotations

import logging

from ..models.ops_schema import ChangeSet, EditOperation, OpType
from .providers import PlannerProvider

logger = logging.getLogger(__name__)


class MockProvider(PlannerProvider):
    """Mock planner that returns predictable operations for testing.

    Works fully offline — no API key required.
    """

    @property
    def name(self) -> str:
        return "mock"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(self, prompt: str, drawing_context: dict) -> ChangeSet:
        """Return mock operations based on simple keyword matching in the prompt.

        This is NOT a real planner. It exists so the full pipeline can be tested
        without an LLM API key.
        """
        logger.info("MockProvider processing prompt: %s", prompt)

        entities = drawing_context.get("entities", [])
        if not entities:
            return ChangeSet(prompt=prompt, operations=[])

        ops: list[EditOperation] = []
        prompt_lower = prompt.lower()

        if "move" in prompt_lower:
            # Find first non-protected entity and move it
            target = self._find_editable_entity(entities, drawing_context)
            if target:
                ops.append(
                    EditOperation(
                        op_type=OpType.MOVE_ENTITY,
                        target_handle=target["handle"],
                        target_layer=target.get("layer"),
                        params={"dx": 24.0, "dy": 0.0},
                    )
                )

        elif "delete" in prompt_lower or "remove" in prompt_lower:
            target = self._find_editable_entity(entities, drawing_context)
            if target:
                ops.append(
                    EditOperation(
                        op_type=OpType.DELETE_ENTITY,
                        target_handle=target["handle"],
                        target_layer=target.get("layer"),
                    )
                )

        elif "text" in prompt_lower or "label" in prompt_lower or "rename" in prompt_lower:
            # Find first text entity
            for e in entities:
                if e.get("type") in ("TEXT", "MTEXT") and e.get("text"):
                    ops.append(
                        EditOperation(
                            op_type=OpType.EDIT_TEXT,
                            target_handle=e["handle"],
                            target_layer=e.get("layer"),
                            params={"new_text": "UPDATED BY CAD-DXF-AGENT"},
                        )
                    )
                    break

        else:
            # Default: move the first editable entity
            target = self._find_editable_entity(entities, drawing_context)
            if target:
                ops.append(
                    EditOperation(
                        op_type=OpType.MOVE_ENTITY,
                        target_handle=target["handle"],
                        target_layer=target.get("layer"),
                        params={"dx": 12.0, "dy": 12.0},
                    )
                )

        return ChangeSet(
            prompt=prompt,
            operations=ops,
            revision_label=f"Mock edit: {prompt[:50]}",
        )

    def _find_editable_entity(
        self, entities: list[dict], context: dict
    ) -> dict | None:
        """Find the first entity not on a protected layer."""
        protected = {
            layer["name"].upper()
            for layer in context.get("layers", [])
            if layer.get("protected")
        }
        for entity in entities:
            if entity.get("layer", "").upper() not in protected:
                return entity
        return None
