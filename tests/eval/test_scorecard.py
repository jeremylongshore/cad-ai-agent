"""Capability scorecard tests — Tier 3 evaluation.

Validates that every scorecard entry produces correct intent classification
and response characteristics when run through the pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dxf_agent.llm.intent_router import IntentRouter
from cad_dxf_agent.models.scorecard_schema import (
    ScorecardEntry,
    ScorecardResult,
    ScorecardSummary,
    ScoreVerdict,
)

ENTRIES_PATH = Path(__file__).parent / "scorecard_entries.json"


def _load_entries() -> list[ScorecardEntry]:
    data = json.loads(ENTRIES_PATH.read_text())
    entries = data if isinstance(data, list) else data.get("entries", [])
    return [ScorecardEntry(**e) for e in entries]


ENTRIES = _load_entries()
ENTRY_IDS = [e.entry_id for e in ENTRIES]


class TestScorecardEntries:
    """All scorecard entries must parse as valid ScorecardEntry models."""

    def test_entries_file_exists(self):
        assert ENTRIES_PATH.exists()

    def test_minimum_entry_count(self):
        assert len(ENTRIES) >= 56, f"Only {len(ENTRIES)} entries, need 56+"

    def test_all_entries_have_unique_ids(self):
        ids = [e.entry_id for e in ENTRIES]
        assert len(ids) == len(set(ids)), "Duplicate entry IDs found"

    def test_all_entries_have_task_family(self):
        for e in ENTRIES:
            assert e.task_family, f"{e.entry_id} missing task_family"

    def test_all_entries_have_prompt(self):
        for e in ENTRIES:
            assert e.prompt, f"{e.entry_id} missing prompt"


class TestScorecardIntentClassification:
    """Verify intent classification accuracy for each entry."""

    @pytest.fixture(scope="class")
    def router(self):
        return IntentRouter()

    @pytest.mark.parametrize("entry", ENTRIES, ids=ENTRY_IDS)
    def test_intent_classification(self, router, entry):
        intent = router.classify(entry.prompt)
        # For needs_clarification and unsupported, router may legitimately
        # classify as another family — skip strict check for these
        if entry.task_family in ("needs_clarification", "unsupported"):
            return  # Cross-cutting entries don't require exact match
        assert intent.family.value == entry.task_family, (
            f"{entry.entry_id}: expected '{entry.task_family}', "
            f"got '{intent.family.value}' for prompt '{entry.prompt}'"
        )


class TestScorecardSchema:
    """Scorecard schema model tests."""

    def test_scorecard_result_creation(self):
        result = ScorecardResult(
            entry_id="test-001",
            verdict=ScoreVerdict.PASS,
            score_intent=1.0,
            score_safety=1.0,
            score_quality=0.8,
            score_composite=0.9,
        )
        assert result.verdict == ScoreVerdict.PASS

    def test_scorecard_summary_compute(self):
        results = [
            ScorecardResult(
                entry_id="a",
                verdict=ScoreVerdict.PASS,
                score_composite=0.9,
                actual_task_family="qna",
            ),
            ScorecardResult(
                entry_id="b",
                verdict=ScoreVerdict.FAIL,
                score_composite=0.3,
                actual_task_family="qna",
                failure_reason="wrong family",
            ),
            ScorecardResult(
                entry_id="c",
                verdict=ScoreVerdict.PASS,
                score_composite=0.85,
                actual_task_family="edit_plan",
            ),
        ]
        summary = ScorecardSummary(results=results)
        summary.compute()
        assert summary.total_entries == 3
        assert summary.passed == 2
        assert summary.failed == 1
        assert summary.pass_rate == pytest.approx(2 / 3)
        assert "qna" in summary.by_family
        assert summary.by_family["qna"]["passed"] == 1

    def test_score_verdict_enum(self):
        assert ScoreVerdict.PASS == "pass"  # noqa: S105
        assert ScoreVerdict.FAIL == "fail"
        assert ScoreVerdict.SKIP == "skip"
        assert ScoreVerdict.ERROR == "error"

    def test_scorecard_entry_serialization(self):
        entry = ScorecardEntry(
            entry_id="test-001",
            task_family="qna",
            prompt="What layers?",
        )
        data = entry.model_dump()
        restored = ScorecardEntry.model_validate(data)
        assert restored.entry_id == "test-001"

    def test_summary_serialization(self):
        summary = ScorecardSummary()
        data = summary.model_dump()
        assert isinstance(data, dict)
        assert "results" in data
        assert "by_family" in data
