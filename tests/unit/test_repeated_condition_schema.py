"""Tests for repeated-condition detection schemas (EPIC-CAD-05)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.cad_schema import Point2D
from cad_dxf_agent.models.repeated_condition_schema import (
    ApprovalState,
    ConditionMatch,
    RepeatedConditionResult,
    SimilarityConfig,
    SimilaritySignal,
    SimilaritySignalType,
)
from cad_dxf_agent.models.response_schema import EvidenceRef


class TestSimilaritySignalType:
    def test_all_signal_types_defined(self):
        expected = {
            "block_name",
            "text_content",
            "geometry_shape",
            "layer_context",
            "spatial_pattern",
            "text_geometry",
        }
        assert set(SimilaritySignalType) == expected

    def test_signal_type_is_str(self):
        assert isinstance(SimilaritySignalType.BLOCK_NAME, str)
        assert SimilaritySignalType.BLOCK_NAME == "block_name"


class TestApprovalState:
    def test_all_states(self):
        assert set(ApprovalState) == {"pending", "approved", "rejected"}

    def test_default_is_pending(self):
        match = ConditionMatch(
            entity_handles=["1"],
            confidence=0.8,
            centroid=Point2D(x=0, y=0),
        )
        assert match.approval_state == ApprovalState.PENDING


class TestSimilaritySignal:
    def test_basic_signal(self):
        signal = SimilaritySignal(
            signal_type=SimilaritySignalType.BLOCK_NAME,
            score=0.9,
            weight=0.3,
            detail="matching blocks: GRID",
        )
        assert signal.score == 0.9
        assert signal.weight == 0.3
        assert signal.weighted_score == pytest.approx(0.27)

    def test_weighted_score_with_trust(self):
        signal = SimilaritySignal(
            signal_type=SimilaritySignalType.TEXT_CONTENT,
            score=0.8,
            weight=0.25,
            trust_level=0.3,  # OCR text
        )
        assert signal.weighted_score == pytest.approx(0.06)

    def test_default_trust_level(self):
        signal = SimilaritySignal(
            signal_type=SimilaritySignalType.BLOCK_NAME,
            score=1.0,
            weight=0.3,
        )
        assert signal.trust_level == 1.0
        assert signal.weighted_score == pytest.approx(0.3)

    def test_score_bounds_validation(self):
        with pytest.raises(ValidationError):
            SimilaritySignal(
                signal_type=SimilaritySignalType.BLOCK_NAME,
                score=1.5,
                weight=0.3,
            )

    def test_serialization(self):
        signal = SimilaritySignal(
            signal_type=SimilaritySignalType.GEOMETRY_SHAPE,
            score=0.75,
            weight=0.2,
            detail="type overlap: 3/4",
            trust_level=0.95,
        )
        data = signal.model_dump()
        assert data["signal_type"] == "geometry_shape"
        assert data["score"] == 0.75
        assert data["trust_level"] == 0.95


class TestConditionMatch:
    def test_basic_match(self):
        match = ConditionMatch(
            entity_handles=["A", "B", "C"],
            confidence=0.85,
            centroid=Point2D(x=100.0, y=200.0),
            explanation="matching blocks: GRID; 2/2 texts matched",
        )
        assert len(match.entity_handles) == 3
        assert match.confidence == 0.85
        assert match.approval_state == ApprovalState.PENDING

    def test_with_signals_and_evidence(self):
        signals = [
            SimilaritySignal(
                signal_type=SimilaritySignalType.BLOCK_NAME,
                score=1.0,
                weight=0.3,
            ),
        ]
        evidence = [
            EvidenceRef(
                entity_handle="A",
                layer="GRID",
                description="INSERT block=GRID at (100, 200)",
            ),
        ]
        match = ConditionMatch(
            entity_handles=["A"],
            confidence=0.75,
            signals=signals,
            centroid=Point2D(x=100, y=200),
            evidence=evidence,
        )
        assert len(match.signals) == 1
        assert len(match.evidence) == 1

    def test_approval_state_transitions(self):
        match = ConditionMatch(
            entity_handles=["A"],
            confidence=0.9,
            centroid=Point2D(x=0, y=0),
        )
        approved = match.model_copy(update={"approval_state": ApprovalState.APPROVED})
        assert approved.approval_state == ApprovalState.APPROVED
        assert match.approval_state == ApprovalState.PENDING  # original unchanged

    def test_serialization_roundtrip(self):
        match = ConditionMatch(
            entity_handles=["A", "B"],
            confidence=0.82,
            centroid=Point2D(x=50, y=75),
            explanation="test",
        )
        data = match.model_dump()
        restored = ConditionMatch.model_validate(data)
        assert restored.confidence == match.confidence
        assert restored.entity_handles == match.entity_handles


class TestSimilarityConfig:
    def test_defaults(self):
        config = SimilarityConfig()
        assert config.min_confidence == 0.5
        assert config.max_results == 50
        assert config.block_name_weight == 0.30
        assert config.text_content_weight == 0.25
        assert config.geometry_shape_weight == 0.20
        assert config.layer_context_weight == 0.10
        assert config.spatial_pattern_weight == 0.10
        assert config.text_geometry_weight == 0.05
        # Weights sum to 1.0
        total = (
            config.block_name_weight
            + config.text_content_weight
            + config.geometry_shape_weight
            + config.layer_context_weight
            + config.spatial_pattern_weight
            + config.text_geometry_weight
        )
        assert total == pytest.approx(1.0)

    def test_custom_config(self):
        config = SimilarityConfig(
            min_confidence=0.7,
            max_results=10,
            block_name_weight=0.5,
        )
        assert config.min_confidence == 0.7
        assert config.max_results == 10
        assert config.block_name_weight == 0.5

    def test_caps(self):
        config = SimilarityConfig()
        assert config.single_entity_min_confidence == 0.70
        assert config.block_only_cap == 0.80
        assert config.ambiguity_threshold == 0.05


class TestRepeatedConditionResult:
    def test_empty_result(self):
        result = RepeatedConditionResult(
            exemplar_handles=["A", "B"],
            exemplar_centroid=Point2D(x=50, y=100),
            summary="No repeated conditions found.",
        )
        assert result.total_found == 0
        assert result.candidates == []
        assert result.ambiguity_flags == []

    def test_with_candidates(self):
        candidates = [
            ConditionMatch(
                entity_handles=["C", "D"],
                confidence=0.85,
                centroid=Point2D(x=200, y=100),
            ),
            ConditionMatch(
                entity_handles=["E", "F"],
                confidence=0.72,
                centroid=Point2D(x=350, y=100),
            ),
        ]
        result = RepeatedConditionResult(
            exemplar_handles=["A", "B"],
            exemplar_centroid=Point2D(x=50, y=100),
            candidates=candidates,
            total_found=2,
            search_radius=150.0,
            summary="Found 2 repeated conditions.",
        )
        assert result.total_found == 2
        assert result.candidates[0].confidence > result.candidates[1].confidence

    def test_serialization(self):
        result = RepeatedConditionResult(
            exemplar_handles=["A"],
            exemplar_centroid=Point2D(x=0, y=0),
            summary="test",
        )
        data = result.model_dump()
        restored = RepeatedConditionResult.model_validate(data)
        assert restored.exemplar_handles == ["A"]
        assert restored.config.min_confidence == 0.5
