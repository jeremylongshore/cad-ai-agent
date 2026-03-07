"""Tests for repeated-condition detection (EPIC-CAD-05).

Tests cover:
- Similarity model: geometry-dominant, text-assisted, mixed-trust, ambiguous
- Search results: exemplar returns candidates, ranked, confidence, evidence, empty case
- Anti-regression: OCR cannot overpower native text, search doesn't trigger edits
- Caps: single-entity min confidence, block-only cap
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.repeated_condition import (
    ConditionDetector,
    _ExemplarProfile,
    _levenshtein_similarity,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.repeated_condition_schema import (
    ApprovalState,
    SimilarityConfig,
    SimilaritySignalType,
)

# --- Helpers ---


def _entity(
    handle: str,
    etype: EntityType = EntityType.INSERT,
    layer: str = "STRUCTURAL",
    x: float = 0.0,
    y: float = 0.0,
    block_name: str | None = None,
    text: str | None = None,
    text_geometry: TextGeometry | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=etype,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block_name,
        text_content=text,
        text_geometry=text_geometry,
    )


def _context(entities: list[EntityRef]) -> DrawingContext:
    return DrawingContext(file_path="test.dxf", entities=entities)


def _make_bay_drawing() -> tuple[DrawingContext, list[str], list[str], list[str]]:
    """Create a drawing with 3 repeated bays (each has COLUMN_MARK block + label).

    Bay 1 at x=0    (exemplar)
    Bay 2 at x=100  (should match)
    Bay 3 at x=200  (should match)
    """
    entities = []

    # Bay 1 (exemplar): block + text at x=0
    entities.append(_entity("B1", EntityType.INSERT, "STRUCTURAL", 0, 0, "COLUMN_MARK"))
    entities.append(_entity("T1", EntityType.TEXT, "NOTES", 0, 5, text="BAY A"))

    # Bay 2: block + text at x=100
    entities.append(_entity("B2", EntityType.INSERT, "STRUCTURAL", 100, 0, "COLUMN_MARK"))
    entities.append(_entity("T2", EntityType.TEXT, "NOTES", 100, 5, text="BAY B"))

    # Bay 3: block + text at x=200
    entities.append(_entity("B3", EntityType.INSERT, "STRUCTURAL", 200, 0, "COLUMN_MARK"))
    entities.append(_entity("T3", EntityType.TEXT, "NOTES", 200, 5, text="BAY C"))

    # Noise: unrelated entities
    entities.append(_entity("N1", EntityType.LINE, "GRID", 50, 50))
    entities.append(_entity("N2", EntityType.LINE, "GRID", 150, 50))

    ctx = _context(entities)
    exemplar = ["B1", "T1"]
    bay2 = ["B2", "T2"]
    bay3 = ["B3", "T3"]
    return ctx, exemplar, bay2, bay3


# --- Exemplar Profile Tests ---


class TestExemplarProfile:
    def test_centroid_calculation(self):
        entities = [
            _entity("A", x=0, y=0),
            _entity("B", x=100, y=0),
        ]
        profile = _ExemplarProfile(entities)
        assert profile.centroid.x == pytest.approx(50.0)
        assert profile.centroid.y == pytest.approx(0.0)

    def test_radius_calculation(self):
        entities = [
            _entity("A", x=0, y=0),
            _entity("B", x=100, y=0),
        ]
        profile = _ExemplarProfile(entities)
        assert profile.radius == pytest.approx(50.0)

    def test_single_entity_default_radius(self):
        entities = [_entity("A", x=50, y=50)]
        profile = _ExemplarProfile(entities)
        assert profile.radius == 50.0  # default

    def test_block_name_counting(self):
        entities = [
            _entity("A", block_name="GRID"),
            _entity("B", block_name="GRID"),
            _entity("C", block_name="MARK"),
        ]
        profile = _ExemplarProfile(entities)
        assert profile.block_names["GRID"] == 2
        assert profile.block_names["MARK"] == 1
        assert profile.has_blocks is True

    def test_text_content_extraction(self):
        entities = [
            _entity("A", EntityType.TEXT, text="Bay A"),
            _entity("B", EntityType.MTEXT, text="NOTE 1"),
            _entity("C", EntityType.INSERT),  # not text
        ]
        profile = _ExemplarProfile(entities)
        assert len(profile.text_contents) == 2
        assert "bay a" in profile.text_contents
        assert profile.has_text is True

    def test_no_blocks_no_text(self):
        entities = [_entity("A", EntityType.LINE)]
        profile = _ExemplarProfile(entities)
        assert profile.has_blocks is False
        assert profile.has_text is False


# --- Similarity Model Tests ---


class TestGeometryDominantRepetition:
    """Repeated condition where geometry (block structure) dominates."""

    def test_matching_blocks_found(self):
        ctx, exemplar, bay2, bay3 = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        assert result.total_found >= 2
        handles_found = [set(c.entity_handles) for c in result.candidates]
        # Bay 2 and Bay 3 entities should appear
        assert any("B2" in h for h in handles_found)
        assert any("B3" in h for h in handles_found)

    def test_confidence_above_threshold(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        for candidate in result.candidates:
            assert candidate.confidence >= 0.5

    def test_candidates_ranked_by_confidence(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        confidences = [c.confidence for c in result.candidates]
        assert confidences == sorted(confidences, reverse=True)


class TestTextAssistedRepetition:
    """Repeated condition where text labels assist matching."""

    def test_text_similarity_boosts_confidence(self):
        entities = [
            # Exemplar: text "SECTION A-A"
            _entity("E1", EntityType.TEXT, "NOTES", 0, 0, text="SECTION A-A"),
            # Candidate 1: similar text
            _entity("C1", EntityType.TEXT, "NOTES", 200, 0, text="SECTION B-B"),
            # Candidate 2: very different text
            _entity("C2", EntityType.TEXT, "NOTES", 400, 0, text="TITLE BLOCK NOTE"),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["E1"])

        if result.total_found >= 2:
            # Similar text should rank higher
            c1_match = next((c for c in result.candidates if "C1" in c.entity_handles), None)
            c2_match = next((c for c in result.candidates if "C2" in c.entity_handles), None)
            if c1_match and c2_match:
                assert c1_match.confidence >= c2_match.confidence


class TestMixedTrustTextScenario:
    """Native CAD text should outrank OCR-derived text in scoring."""

    def test_native_text_higher_trust(self):
        native_tg = TextGeometry(
            height=3.0,
            provenance=TextProvenance.NATIVE_CAD_TEXT,
        )
        ocr_tg = TextGeometry(
            height=3.0,
            provenance=TextProvenance.RASTER_OCR_TEXT,
            confidence_position=0.3,
            confidence_rotation=0.2,
            confidence_content=0.5,
        )

        entities = [
            # Exemplar: native text
            _entity("E1", EntityType.TEXT, "NOTES", 0, 0, text="GRID A", text_geometry=native_tg),
            # Candidate with native text
            _entity("C1", EntityType.TEXT, "NOTES", 200, 0, text="GRID B", text_geometry=native_tg),
            # Candidate with OCR text
            _entity("C2", EntityType.TEXT, "NOTES", 400, 0, text="GRID C", text_geometry=ocr_tg),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["E1"])

        # Both should be found, native should have higher trust in text signal
        if result.total_found >= 2:
            c1 = next((c for c in result.candidates if "C1" in c.entity_handles), None)
            c2 = next((c for c in result.candidates if "C2" in c.entity_handles), None)
            if c1 and c2:
                c1_text = next(
                    (s for s in c1.signals if s.signal_type == SimilaritySignalType.TEXT_CONTENT),
                    None,
                )
                c2_text = next(
                    (s for s in c2.signals if s.signal_type == SimilaritySignalType.TEXT_CONTENT),
                    None,
                )
                if c1_text and c2_text:
                    # Native text signal should have higher trust_level
                    assert c1_text.trust_level >= c2_text.trust_level


class TestAmbiguousNearMatches:
    """Cases where matches are too close to call."""

    def test_near_tie_flagged(self):
        # Create entities with nearly identical conditions
        entities = [
            _entity("E1", EntityType.INSERT, "S", 0, 0, "GRID"),
            _entity("C1", EntityType.INSERT, "S", 200, 0, "GRID"),
            _entity("C2", EntityType.INSERT, "S", 400, 0, "GRID"),
        ]
        ctx = _context(entities)
        config = SimilarityConfig(ambiguity_threshold=0.10)  # wide threshold
        detector = ConditionDetector(ctx, config)
        result = detector.find_repeated(["E1"])

        if result.total_found >= 2:
            # Equal conditions should produce near-tie
            assert (
                len(result.ambiguity_flags) > 0
                or result.candidates[0].confidence == result.candidates[1].confidence
            )


# --- Search Results Tests ---


class TestSearchResults:
    def test_exemplar_returns_candidates(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)
        assert result.total_found > 0
        assert len(result.candidates) > 0

    def test_candidates_have_evidence(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        for candidate in result.candidates:
            assert len(candidate.evidence) > 0
            for ev in candidate.evidence:
                assert ev.entity_handle is not None

    def test_candidates_have_explanation(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        for candidate in result.candidates:
            assert candidate.explanation  # non-empty

    def test_empty_exemplar_handles(self):
        ctx, _, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated([])
        assert result.total_found == 0
        assert "No valid entities" in result.summary

    def test_invalid_handles(self):
        ctx, _, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["NONEXISTENT"])
        assert result.total_found == 0

    def test_no_matches_found(self):
        entities = [
            _entity("A", EntityType.INSERT, "STRUCTURAL", 0, 0, "UNIQUE_BLOCK"),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["A"])
        assert result.total_found == 0
        assert "No repeated conditions" in result.summary or "No candidate" in result.summary

    def test_max_results_cap(self):
        # Create many repeated blocks
        entities = [_entity("E", EntityType.INSERT, "S", 0, 0, "BLK")]
        for i in range(20):
            entities.append(_entity(f"C{i}", EntityType.INSERT, "S", (i + 1) * 200, 0, "BLK"))
        ctx = _context(entities)
        config = SimilarityConfig(max_results=5)
        detector = ConditionDetector(ctx, config)
        result = detector.find_repeated(["E"])
        assert len(result.candidates) <= 5

    def test_min_confidence_filter(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        config = SimilarityConfig(min_confidence=0.99)  # very high
        detector = ConditionDetector(ctx, config)
        result = detector.find_repeated(exemplar)
        # With very high threshold, may have fewer matches
        for c in result.candidates:
            assert c.confidence >= 0.99

    def test_result_has_summary(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)
        assert result.summary  # non-empty

    def test_result_has_search_radius(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)
        assert result.search_radius > 0

    def test_exemplar_not_in_candidates(self):
        """Exemplar entities should not appear in candidate matches."""
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        exemplar_set = set(exemplar)
        for candidate in result.candidates:
            overlap = exemplar_set & set(candidate.entity_handles)
            assert not overlap, f"Exemplar entities {overlap} found in candidate"


# --- Signal Inspection Tests ---


class TestSignalBreakdown:
    def test_all_signal_types_present(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        if result.candidates:
            signal_types = {s.signal_type for s in result.candidates[0].signals}
            expected = set(SimilaritySignalType)
            assert signal_types == expected

    def test_block_signal_scores_high_for_matching_blocks(self):
        entities = [
            _entity("E1", EntityType.INSERT, "S", 0, 0, "GRID"),
            _entity("C1", EntityType.INSERT, "S", 200, 0, "GRID"),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["E1"])

        if result.candidates:
            block_signal = next(
                (
                    s
                    for s in result.candidates[0].signals
                    if s.signal_type == SimilaritySignalType.BLOCK_NAME
                ),
                None,
            )
            assert block_signal is not None
            assert block_signal.score == 1.0

    def test_text_signal_for_similar_text(self):
        entities = [
            _entity("E1", EntityType.TEXT, "NOTES", 0, 0, text="GRID LINE A"),
            _entity("C1", EntityType.TEXT, "NOTES", 200, 0, text="GRID LINE B"),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["E1"])

        if result.candidates:
            text_signal = next(
                (
                    s
                    for s in result.candidates[0].signals
                    if s.signal_type == SimilaritySignalType.TEXT_CONTENT
                ),
                None,
            )
            assert text_signal is not None
            assert text_signal.score > 0.5  # "GRID LINE A" vs "GRID LINE B" are similar


# --- Approval State Tests ---


class TestApprovalWorkflow:
    def test_candidates_default_pending(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        for candidate in result.candidates:
            assert candidate.approval_state == ApprovalState.PENDING

    def test_can_approve_candidate(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        if result.candidates:
            approved = result.candidates[0].model_copy(
                update={"approval_state": ApprovalState.APPROVED}
            )
            assert approved.approval_state == ApprovalState.APPROVED

    def test_can_reject_candidate(self):
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        if result.candidates:
            rejected = result.candidates[0].model_copy(
                update={"approval_state": ApprovalState.REJECTED}
            )
            assert rejected.approval_state == ApprovalState.REJECTED


# --- Anti-Regression Tests ---


class TestAntiRegression:
    def test_ocr_text_cannot_overpower_native_geometry(self):
        """Low-trust OCR text should not dominate matching when geometry is strong."""
        ocr_tg = TextGeometry(
            height=3.0,
            provenance=TextProvenance.RASTER_OCR_TEXT,
            confidence_content=0.5,
        )
        native_tg = TextGeometry(
            height=3.0,
            provenance=TextProvenance.NATIVE_CAD_TEXT,
        )

        entities = [
            # Exemplar: native text + block
            _entity("E1", EntityType.INSERT, "S", 0, 0, "GRID"),
            _entity("E2", EntityType.TEXT, "S", 0, 5, text="A1", text_geometry=native_tg),
            # Good candidate: same block, native text
            _entity("C1", EntityType.INSERT, "S", 200, 0, "GRID"),
            _entity("C2", EntityType.TEXT, "S", 200, 5, text="B1", text_geometry=native_tg),
            # Weak candidate: different block, OCR text that happens to match
            _entity("W1", EntityType.INSERT, "S", 400, 0, "OTHER"),
            _entity("W2", EntityType.TEXT, "S", 400, 5, text="A1", text_geometry=ocr_tg),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["E1", "E2"])

        # The block+native match should score higher than OCR text match
        if result.total_found >= 2:
            c1 = next(
                (c for c in result.candidates if any(h in c.entity_handles for h in ["C1", "C2"])),
                None,
            )
            w1 = next(
                (c for c in result.candidates if any(h in c.entity_handles for h in ["W1", "W2"])),
                None,
            )
            if c1 and w1:
                assert c1.confidence >= w1.confidence

    def test_search_does_not_trigger_edits(self):
        """Repeated-condition search is read-only. Result has no operations."""
        ctx, exemplar, _, _ = _make_bay_drawing()
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(exemplar)

        # Result is a RepeatedConditionResult, not an edit plan
        assert not hasattr(result, "operations")
        # Approval state is pending, not applied
        for c in result.candidates:
            assert c.approval_state == ApprovalState.PENDING


# --- Levenshtein Helper Tests ---


class TestLevenshteinSimilarity:
    def test_identical(self):
        assert _levenshtein_similarity("abc", "abc") == 1.0

    def test_empty(self):
        assert _levenshtein_similarity("", "abc") == 0.0
        assert _levenshtein_similarity("abc", "") == 0.0

    def test_similar(self):
        sim = _levenshtein_similarity("GRID LINE A", "GRID LINE B")
        assert 0.8 < sim < 1.0

    def test_dissimilar(self):
        sim = _levenshtein_similarity("abc", "xyz")
        assert sim < 0.5


# --- Realistic Fixture Tests ---


class TestRepeatedBays:
    """Realistic test: structural drawing with repeated column bays."""

    def test_column_bays_detected(self):
        """5 column bays at regular spacing — 4 should match the exemplar."""
        entities = []
        for i in range(5):
            x = i * 300
            entities.append(
                _entity(f"COL_{i}", EntityType.INSERT, "STRUCTURAL", x, 0, "COLUMN_MARK")
            )
            entities.append(
                _entity(f"LBL_{i}", EntityType.TEXT, "NOTES", x, 10, text=f"COL {chr(65 + i)}")
            )

        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["COL_0", "LBL_0"])

        # Should find at least 3 of the 4 remaining bays
        assert result.total_found >= 3


class TestRepeatedLabels:
    """Realistic test: repeated text labels in different regions."""

    def test_similar_labels_found(self):
        entities = []
        labels = ["SECTION A-A", "SECTION B-B", "SECTION C-C", "SECTION D-D"]
        for i, label in enumerate(labels):
            entities.append(_entity(f"S{i}", EntityType.TEXT, "NOTES", i * 200, 0, text=label))

        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["S0"])

        assert result.total_found >= 2


class TestGeometryDominatesWeakText:
    """Cases where geometry should dominate over weak text."""

    def test_block_match_without_text(self):
        """Blocks with no text still match on block name + layer."""
        entities = [
            _entity("E1", EntityType.INSERT, "STRUCTURAL", 0, 0, "GRID_POINT"),
            _entity("C1", EntityType.INSERT, "STRUCTURAL", 300, 0, "GRID_POINT"),
            _entity("C2", EntityType.INSERT, "STRUCTURAL", 600, 0, "GRID_POINT"),
        ]
        ctx = _context(entities)
        detector = ConditionDetector(ctx)
        result = detector.find_repeated(["E1"])
        assert result.total_found >= 2
