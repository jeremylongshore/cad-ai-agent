"""Tests for precision_schema — PrecisionControls, MatchCandidate, ActionStatus, ActionDetail."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.precision_schema import (
    ActionDetail,
    ActionStatus,
    MatchCandidate,
    PrecisionControls,
)


class TestPrecisionControls:
    def test_defaults_are_empty(self):
        pc = PrecisionControls()
        assert pc.target_handles == []
        assert pc.target_layers == []
        assert pc.exclude_layers == []
        assert pc.target_types == []
        assert pc.model_space_only is False
        assert pc.exact_delta is None
        assert pc.confidence_threshold == 0.0
        assert pc.disable_inference is False

    def test_roundtrip_serialization(self):
        pc = PrecisionControls(
            target_handles=["A1", "B2"],
            target_layers=["WALLS"],
            confidence_threshold=0.75,
        )
        data = pc.model_dump()
        restored = PrecisionControls(**data)
        assert restored.target_handles == ["A1", "B2"]
        assert restored.target_layers == ["WALLS"]
        assert restored.confidence_threshold == 0.75

    def test_confidence_threshold_lower_bound(self):
        pc = PrecisionControls(confidence_threshold=0.0)
        assert pc.confidence_threshold == 0.0

    def test_confidence_threshold_upper_bound(self):
        pc = PrecisionControls(confidence_threshold=1.0)
        assert pc.confidence_threshold == 1.0

    def test_confidence_threshold_below_zero_raises(self):
        with pytest.raises(ValidationError):
            PrecisionControls(confidence_threshold=-0.1)

    def test_confidence_threshold_above_one_raises(self):
        with pytest.raises(ValidationError):
            PrecisionControls(confidence_threshold=1.1)

    def test_exact_delta_populated(self):
        pc = PrecisionControls(exact_delta={"dx": 10.5, "dy": -3.0})
        assert pc.exact_delta == {"dx": 10.5, "dy": -3.0}

    def test_disable_inference_flag(self):
        pc = PrecisionControls(disable_inference=True)
        assert pc.disable_inference is True

    def test_model_space_only_flag(self):
        pc = PrecisionControls(model_space_only=True)
        assert pc.model_space_only is True

    def test_all_fields_at_once(self):
        pc = PrecisionControls(
            target_handles=["H1"],
            target_layers=["LAYER_A"],
            exclude_layers=["REVISION"],
            target_types=["LINE"],
            model_space_only=True,
            exact_delta={"dx": 5.0},
            confidence_threshold=0.8,
            disable_inference=True,
        )
        assert pc.target_handles == ["H1"]
        assert pc.exclude_layers == ["REVISION"]
        assert pc.target_types == ["LINE"]
        assert pc.confidence_threshold == 0.8


class TestMatchCandidate:
    def test_minimal_construction(self):
        mc = MatchCandidate(handle="A1", layer="WALLS", entity_type="LINE", confidence=0.9)
        assert mc.handle == "A1"
        assert mc.match_reason == ""
        assert mc.location is None

    def test_confidence_lower_bound(self):
        mc = MatchCandidate(handle="A", layer="L", entity_type="TEXT", confidence=0.0)
        assert mc.confidence == 0.0

    def test_confidence_upper_bound(self):
        mc = MatchCandidate(handle="A", layer="L", entity_type="TEXT", confidence=1.0)
        assert mc.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            MatchCandidate(handle="A", layer="L", entity_type="TEXT", confidence=-0.1)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            MatchCandidate(handle="A", layer="L", entity_type="TEXT", confidence=1.1)

    def test_location_tuple(self):
        mc = MatchCandidate(
            handle="A", layer="L", entity_type="LINE", confidence=0.5, location=(10.0, 20.0)
        )
        assert mc.location == (10.0, 20.0)

    def test_match_reason(self):
        mc = MatchCandidate(
            handle="A", layer="L", entity_type="LINE", confidence=0.5, match_reason="exact_handle"
        )
        assert mc.match_reason == "exact_handle"


class TestActionStatus:
    def test_all_values(self):
        assert ActionStatus.PLANNED == "planned"
        assert ActionStatus.APPLIED == "applied"
        assert ActionStatus.SKIPPED == "skipped"
        assert ActionStatus.BLOCKED == "blocked"

    def test_has_four_members(self):
        assert len(ActionStatus) == 4


class TestActionDetail:
    def test_defaults(self):
        ad = ActionDetail(
            entity_handle="A1",
            entity_type="LINE",
            layer="WALLS",
            action="move_entity",
        )
        assert ad.status == ActionStatus.PLANNED
        assert ad.skip_reason is None
        assert ad.confidence == 1.0
        assert ad.before == {}
        assert ad.after == {}
        assert ad.evidence == []

    def test_full_construction(self):
        ad = ActionDetail(
            entity_handle="B2",
            entity_type="TEXT",
            layer="NOTES",
            action="edit_text",
            before={"text": "old"},
            after={"text": "new"},
            status=ActionStatus.BLOCKED,
            skip_reason="protected layer",
            confidence=0.85,
            evidence=["entity on layer NOTES"],
        )
        assert ad.entity_handle == "B2"
        assert ad.status == ActionStatus.BLOCKED
        assert ad.before["text"] == "old"
        assert ad.after["text"] == "new"
        assert ad.skip_reason == "protected layer"
        assert len(ad.evidence) == 1

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ActionDetail(
                entity_handle="A",
                entity_type="LINE",
                layer="L",
                action="move_entity",
                confidence=1.5,
            )

    def test_serialization_roundtrip(self):
        ad = ActionDetail(
            entity_handle="C3",
            entity_type="INSERT",
            layer="STRUCTURAL",
            action="delete_entity",
            status=ActionStatus.APPLIED,
        )
        data = ad.model_dump()
        assert data["status"] == "applied"
        assert data["entity_handle"] == "C3"
