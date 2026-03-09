"""Tests for work_progress_schema — WorkProgress model."""

from __future__ import annotations

from cad_dxf_agent.models.work_progress_schema import WorkProgress


class TestWorkProgressDefaults:
    def test_required_fields_only(self):
        wp = WorkProgress(user_id="uid-1", doc_id="doc-abc")
        assert wp.user_id == "uid-1"
        assert wp.doc_id == "doc-abc"
        assert wp.tenant_id == ""
        assert wp.conversation_history == []
        assert wp.edit_count == 0
        assert wp.last_prompt == ""
        assert wp.has_working_dxf is False
        assert wp.audit_events == []
        assert wp.snapshot_labels == []
        assert wp.saved_at  # non-empty ISO string


class TestWorkProgressAllFields:
    def test_all_fields_accepted(self):
        wp = WorkProgress(
            user_id="uid-2",
            doc_id="doc-xyz",
            tenant_id="tid-001",
            saved_at="2026-03-01T10:00:00+00:00",
            conversation_history=[{"role": "user", "content": "Move wall north"}],
            edit_count=3,
            last_prompt="Move wall north",
            has_working_dxf=True,
            audit_events=[{"event": "edit_applied", "op": "move_entity"}],
            snapshot_labels=["before-demo", "after-demo"],
        )
        assert wp.tenant_id == "tid-001"
        assert wp.edit_count == 3
        assert wp.last_prompt == "Move wall north"
        assert wp.has_working_dxf is True
        assert len(wp.conversation_history) == 1
        assert len(wp.audit_events) == 1
        assert wp.snapshot_labels == ["before-demo", "after-demo"]


class TestWorkProgressMutability:
    def test_edit_count_can_be_incremented(self):
        wp = WorkProgress(user_id="u", doc_id="d")
        wp.edit_count += 1
        assert wp.edit_count == 1

    def test_conversation_history_can_be_appended(self):
        wp = WorkProgress(user_id="u", doc_id="d")
        wp.conversation_history.append({"role": "user", "content": "hello"})
        assert len(wp.conversation_history) == 1

    def test_snapshot_labels_can_be_appended(self):
        wp = WorkProgress(user_id="u", doc_id="d")
        wp.snapshot_labels.append("v1")
        wp.snapshot_labels.append("v2")
        assert wp.snapshot_labels == ["v1", "v2"]


class TestWorkProgressJsonRoundtrip:
    def test_roundtrip_minimal(self):
        wp = WorkProgress(user_id="uid-3", doc_id="doc-3")
        restored = WorkProgress.model_validate_json(wp.model_dump_json())
        assert restored.user_id == wp.user_id
        assert restored.doc_id == wp.doc_id
        assert restored.edit_count == 0
        assert restored.has_working_dxf is False
        assert restored.conversation_history == []

    def test_roundtrip_with_populated_lists(self):
        wp = WorkProgress(
            user_id="uid-4",
            doc_id="doc-4",
            tenant_id="tid-002",
            edit_count=5,
            last_prompt="Delete column",
            has_working_dxf=True,
            conversation_history=[{"role": "assistant", "content": "Done."}],
            audit_events=[{"event": "snapshot_taken", "label": "pre-delete"}],
            snapshot_labels=["pre-delete"],
        )
        restored = WorkProgress.model_validate_json(wp.model_dump_json())
        assert restored.tenant_id == "tid-002"
        assert restored.edit_count == 5
        assert restored.last_prompt == "Delete column"
        assert restored.has_working_dxf is True
        assert restored.conversation_history == [{"role": "assistant", "content": "Done."}]
        assert restored.snapshot_labels == ["pre-delete"]
        assert len(restored.audit_events) == 1
