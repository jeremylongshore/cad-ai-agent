"""Snapshot tests for ChangeSet structure — catch accidental changes.

Uses syrupy to snapshot the serialized ChangeSet from the MockProvider.
If the prompt→changeset mapping changes, the snapshot will fail,
forcing an explicit --snapshot-update.
"""

from __future__ import annotations

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.llm.planner import run_planner


def _changeset_to_comparable(changeset):
    """Convert changeset to a snapshot-friendly dict.

    Strips handles (they vary per DXF creation) but keeps op types,
    params, and structure intact.
    """
    ops = []
    for op in changeset.operations:
        ops.append(
            {
                "op_type": op.op_type.value,
                "params": op.params,
                "has_target_handle": op.target_handle is not None,
                "has_target_layer": op.target_layer is not None,
            }
        )
    return {
        "op_count": changeset.op_count,
        "prompt": changeset.prompt,
        "operations": ops,
    }


class TestChangeSetSnapshots:
    def test_move_prompt_snapshot(self, sample_dxf, snapshot):
        """Snapshot: 'move' prompt produces a stable changeset structure."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)
        changeset = run_planner("move this column", planner_ctx)

        result = _changeset_to_comparable(changeset)
        assert result == snapshot

    def test_delete_prompt_snapshot(self, sample_dxf, snapshot):
        """Snapshot: 'delete' prompt produces a stable changeset structure."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)
        changeset = run_planner("delete this element", planner_ctx)

        result = _changeset_to_comparable(changeset)
        assert result == snapshot

    def test_text_prompt_snapshot(self, sample_dxf, snapshot):
        """Snapshot: 'text' prompt produces a stable changeset structure."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)
        changeset = run_planner("change text label", planner_ctx)

        result = _changeset_to_comparable(changeset)
        assert result == snapshot
