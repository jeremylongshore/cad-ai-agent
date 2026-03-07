"""Tests for IntentRouter — heuristic classification, priority, edge cases, golden file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dxf_agent.llm.intent_router import IntentResult, IntentRouter
from cad_dxf_agent.models.response_schema import TaskFamily

GOLDEN_FILE = Path(__file__).parent.parent / "fixtures" / "router_golden.json"


@pytest.fixture
def router():
    return IntentRouter(confidence_threshold=0.9, llm_enabled=False)


@pytest.fixture
def golden_cases():
    return json.loads(GOLDEN_FILE.read_text())


# ---------------------------------------------------------------------------
# Basic classification per family
# ---------------------------------------------------------------------------


class TestHeuristicClassification:
    def test_compare_detected(self, router):
        result = router.classify("compare these two drawings")
        assert result.family == TaskFamily.COMPARE
        assert result.confidence >= 0.9

    def test_diff_detected(self, router):
        result = router.classify("show me the diff")
        assert result.family == TaskFamily.COMPARE

    def test_markup_detected(self, router):
        result = router.classify("interpret the markup clouds")
        assert result.family == TaskFamily.MARKUP_INTERPRETATION

    def test_redline_detected(self, router):
        result = router.classify("check the redline annotations")
        assert result.family == TaskFamily.MARKUP_INTERPRETATION

    def test_move_edit_plan(self, router):
        result = router.classify("move the wall 10 feet")
        assert result.family == TaskFamily.EDIT_PLAN

    def test_delete_edit_plan(self, router):
        result = router.classify("delete entity A1")
        assert result.family == TaskFamily.EDIT_PLAN

    def test_change_text_edit_plan(self, router):
        result = router.classify("change text on label to REVISED")
        assert result.family == TaskFamily.EDIT_PLAN

    def test_add_block_edit_plan(self, router):
        result = router.classify("add a door block at 50,100")
        assert result.family == TaskFamily.EDIT_PLAN

    def test_insert_edit_plan(self, router):
        result = router.classify("insert a window on the south wall")
        assert result.family == TaskFamily.EDIT_PLAN

    def test_takeoff_detected(self, router):
        result = router.classify("do a quantity takeoff for doors")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_estimate_detected(self, router):
        result = router.classify("estimate the material quantities")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_count_all_takeoff(self, router):
        result = router.classify("count all windows in the drawing")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_repeated_condition(self, router):
        result = router.classify("find all instances of the exit sign")
        assert result.family == TaskFamily.REPEATED_CONDITION

    def test_every_instance(self, router):
        result = router.classify("show every instance of block CHAIR")
        assert result.family == TaskFamily.REPEATED_CONDITION

    def test_design_assist_suggest(self, router):
        result = router.classify("suggest improvements for the layout")
        assert result.family == TaskFamily.DESIGN_ASSIST

    def test_design_assist_optimize(self, router):
        result = router.classify("optimize the corridor width")
        assert result.family == TaskFamily.DESIGN_ASSIST

    def test_summary_detected(self, router):
        result = router.classify("summarize this drawing")
        assert result.family == TaskFamily.SUMMARY

    def test_overview_summary(self, router):
        result = router.classify("give me an overview of the floor plan")
        assert result.family == TaskFamily.SUMMARY

    def test_qna_what_is(self, router):
        result = router.classify("what is on layer WALLS")
        assert result.family == TaskFamily.QNA

    def test_qna_which_layer(self, router):
        result = router.classify("which layer has the doors")
        assert result.family == TaskFamily.QNA

    def test_qna_how_many(self, router):
        # "how many layers" has no element-type word, so it routes to QNA.
        # (Prompts containing door/window/room/wall/etc. route to TAKEOFF_ESTIMATE.)
        result = router.classify("how many layers are there")
        assert result.family == TaskFamily.QNA


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    def test_compare_beats_edit_when_both_match(self, router):
        """'compare' should win over 'move' if both keywords present."""
        result = router.classify("compare the moved entities")
        assert result.family == TaskFamily.COMPARE

    def test_markup_beats_edit(self, router):
        result = router.classify("edit the markup cloud annotations")
        assert result.family == TaskFamily.MARKUP_INTERPRETATION

    def test_edit_plan_before_qna(self, router):
        """'move' should match edit_plan before 'what is' could match qna."""
        result = router.classify("move what is labeled A1")
        assert result.family == TaskFamily.EDIT_PLAN


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_prompt(self, router):
        result = router.classify("")
        assert result.family == TaskFamily.NEEDS_CLARIFICATION
        assert result.confidence == 1.0
        assert result.matched_pattern == "empty_prompt"

    def test_whitespace_only(self, router):
        result = router.classify("   ")
        assert result.family == TaskFamily.NEEDS_CLARIFICATION
        assert result.confidence == 1.0

    def test_no_match_fallback(self, router):
        result = router.classify("hello world")
        assert result.family == TaskFamily.NEEDS_CLARIFICATION
        assert result.confidence == 0.5
        assert result.matched_pattern == "no_match"

    def test_case_insensitive(self, router):
        result = router.classify("MOVE THE WALL")
        assert result.family == TaskFamily.EDIT_PLAN

    def test_mixed_case(self, router):
        result = router.classify("Compare These Drawings")
        assert result.family == TaskFamily.COMPARE

    def test_source_is_heuristic(self, router):
        result = router.classify("move entity A1")
        assert result.source == "heuristic"

    def test_router_time_populated(self, router):
        result = router.classify("delete entity A1")
        assert result.router_time_ms >= 0.0

    def test_matched_pattern_populated(self, router):
        result = router.classify("move the wall")
        assert result.matched_pattern is not None


# ---------------------------------------------------------------------------
# IntentResult model
# ---------------------------------------------------------------------------


class TestIntentResult:
    def test_confidence_clamped_min(self):
        with pytest.raises(ValueError):
            IntentResult(family=TaskFamily.EDIT_PLAN, confidence=-0.1)

    def test_confidence_clamped_max(self):
        with pytest.raises(ValueError):
            IntentResult(family=TaskFamily.EDIT_PLAN, confidence=1.1)

    def test_valid_confidence(self):
        result = IntentResult(family=TaskFamily.EDIT_PLAN, confidence=0.95)
        assert result.confidence == 0.95

    def test_serialization(self):
        result = IntentResult(
            family=TaskFamily.EDIT_PLAN,
            confidence=0.95,
            source="heuristic",
            matched_pattern=r"\bmove\b",
        )
        data = result.model_dump()
        assert data["family"] == "edit_plan"
        assert data["source"] == "heuristic"

    def test_fallback_reason_default_none(self):
        result = IntentResult(family=TaskFamily.EDIT_PLAN, confidence=0.95)
        assert result.fallback_reason is None

    def test_clarification_required_default_false(self):
        result = IntentResult(family=TaskFamily.EDIT_PLAN, confidence=0.95)
        assert result.clarification_required is False

    def test_fallback_fields_set_on_no_match(self):
        router = IntentRouter(confidence_threshold=0.9, llm_enabled=False)
        result = router.classify("hello world")
        assert result.fallback_reason == "no_heuristic_match"
        assert result.clarification_required is True

    def test_fallback_fields_not_set_on_match(self):
        router = IntentRouter(confidence_threshold=0.9, llm_enabled=False)
        result = router.classify("move the wall")
        assert result.fallback_reason is None
        assert result.clarification_required is False


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------


class TestLLMFallback:
    def test_llm_disabled_uses_heuristic_fallback(self):
        router = IntentRouter(confidence_threshold=0.9, llm_enabled=False)
        result = router.classify("hello")
        assert result.source == "heuristic"

    def test_llm_enabled_returns_clarification(self):
        router = IntentRouter(confidence_threshold=0.9, llm_enabled=True)
        result = router.classify("hello")
        assert result.family == TaskFamily.NEEDS_CLARIFICATION
        assert result.source == "llm"


# ---------------------------------------------------------------------------
# Golden file
# ---------------------------------------------------------------------------


class TestGoldenRouting:
    def test_golden_file_exists(self):
        assert GOLDEN_FILE.exists()

    def test_golden_file_has_50_entries(self, golden_cases):
        assert len(golden_cases) == 50

    def test_all_golden_cases_classify_correctly(self, router, golden_cases):
        failures = []
        for i, case in enumerate(golden_cases):
            result = router.classify(case["prompt"])
            if result.family.value != case["expected_family"]:
                failures.append(
                    f"Case {i}: prompt={case['prompt']!r} "
                    f"expected={case['expected_family']} got={result.family.value}"
                )
        assert failures == [], "Golden routing failures:\n" + "\n".join(failures)

    def test_all_golden_sources_correct(self, router, golden_cases):
        for case in golden_cases:
            result = router.classify(case["prompt"])
            assert result.source == case["expected_source"], (
                f"prompt={case['prompt']!r}: expected source={case['expected_source']} "
                f"got={result.source}"
            )


# ---------------------------------------------------------------------------
# New QNA patterns
# ---------------------------------------------------------------------------


class TestNewQNAPatterns:
    """Verify new natural-question patterns added to the QNA rule."""

    def test_are_there_bedrooms(self, router):
        result = router.classify("are there bedrooms")
        assert result.family == TaskFamily.QNA

    def test_is_there_a_stairwell(self, router):
        result = router.classify("is there a stairwell")
        assert result.family == TaskFamily.QNA

    def test_do_you_see_any_walls(self, router):
        result = router.classify("do you see any walls")
        assert result.family == TaskFamily.QNA

    def test_can_you_see_any_text(self, router):
        result = router.classify("can you see any text")
        assert result.family == TaskFamily.QNA

    def test_tell_me_about_this_plan(self, router):
        # "tell me" matches QNA; "tell me about" is also a QNA pattern
        result = router.classify("tell me about this plan")
        assert result.family == TaskFamily.QNA

    def test_find_the_kitchen(self, router):
        # bare "find" (without "all") routes to QNA, not REPEATED_CONDITION
        result = router.classify("find the kitchen")
        assert result.family == TaskFamily.QNA

    def test_search_for_exit_signs(self, router):
        result = router.classify("search for the exit signs")
        assert result.family == TaskFamily.QNA

    def test_look_for_annotations(self, router):
        result = router.classify("look for annotations")
        assert result.family == TaskFamily.QNA

    def test_identify_load_bearing_walls(self, router):
        result = router.classify("identify the load-bearing walls")
        assert result.family == TaskFamily.QNA

    def test_what_do_you_see_in_this_drawing(self, router):
        # "what...this drawing" matches the SUMMARY pattern before QNA's
        # "what do you see" pattern — SUMMARY takes higher priority.
        result = router.classify("what do you see in this drawing")
        assert result.family == TaskFamily.SUMMARY

    def test_what_rooms_are_in_this_blueprint(self, router):
        # "what...this blueprint" hits the SUMMARY pattern at priority 7
        # before QNA patterns are evaluated.
        result = router.classify("what rooms are in this blueprint")
        assert result.family == TaskFamily.SUMMARY

    def test_what_does_this_plan_show(self, router):
        result = router.classify("what does this plan show")
        assert result.family == TaskFamily.SUMMARY

    def test_what_do_you_see_no_drawing_keyword(self, router):
        # Without "drawing/plan/blueprint", "what do you see" routes to QNA
        result = router.classify("what do you see")
        assert result.family == TaskFamily.QNA

    def test_are_there_case_insensitive(self, router):
        result = router.classify("ARE THERE any columns")
        assert result.family == TaskFamily.QNA

    def test_find_not_find_all(self, router):
        # "find" alone is QNA; "find all" is REPEATED_CONDITION
        result = router.classify("find the exit")
        assert result.family == TaskFamily.QNA

    def test_find_all_still_repeated_condition(self, router):
        result = router.classify("find all instances of the sprinkler head")
        assert result.family == TaskFamily.REPEATED_CONDITION


# ---------------------------------------------------------------------------
# New TAKEOFF_ESTIMATE patterns
# ---------------------------------------------------------------------------


class TestNewTakeoffPatterns:
    """Verify new count/how-many patterns for specific element types."""

    def test_how_many_doors_are_there(self, router):
        result = router.classify("how many doors are there")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_how_many_windows(self, router):
        result = router.classify("how many windows does this plan have")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_count_the_windows(self, router):
        result = router.classify("count the windows")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_count_doors(self, router):
        result = router.classify("count doors on this floor")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_how_many_rooms(self, router):
        result = router.classify("how many rooms are on this level")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_count_columns(self, router):
        result = router.classify("count the columns in the structural plan")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_how_many_fixtures(self, router):
        result = router.classify("how many fixtures are in the bathroom")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_count_windows_case_insensitive(self, router):
        result = router.classify("COUNT THE WINDOWS")
        assert result.family == TaskFamily.TAKEOFF_ESTIMATE

    def test_how_many_without_element_type_routes_qna(self, router):
        # "how many layers" contains no element-type word (door/window/room/wall/
        # column/beam/fixture), so the TAKEOFF pattern does not match and it
        # falls through to QNA's \bhow\s+many\b pattern.
        result = router.classify("how many layers are there")
        assert result.family == TaskFamily.QNA


# ---------------------------------------------------------------------------
# New SUMMARY patterns
# ---------------------------------------------------------------------------


class TestNewSummaryPatterns:
    """Verify new summary-intent patterns added to the SUMMARY rule."""

    def test_what_is_this_drawing(self, router):
        result = router.classify("what is this drawing")
        assert result.family == TaskFamily.SUMMARY

    def test_break_down_this_drawing(self, router):
        result = router.classify("break down this drawing")
        assert result.family == TaskFamily.SUMMARY

    def test_breakdown_no_space(self, router):
        # Pattern uses \bbreak\s*down\b so zero or more spaces both match
        result = router.classify("breakdown this floor plan")
        assert result.family == TaskFamily.SUMMARY

    def test_what_is_this_plan(self, router):
        result = router.classify("what is this plan")
        assert result.family == TaskFamily.SUMMARY

    def test_what_is_this_blueprint(self, router):
        result = router.classify("what is this blueprint")
        assert result.family == TaskFamily.SUMMARY

    def test_break_down_case_insensitive(self, router):
        result = router.classify("BREAK DOWN this drawing")
        assert result.family == TaskFamily.SUMMARY

    def test_what_drawing_general(self, router):
        # "what...drawing" matches the SUMMARY pattern
        result = router.classify("what does this drawing represent")
        assert result.family == TaskFamily.SUMMARY


# ---------------------------------------------------------------------------
# from_settings constructor
# ---------------------------------------------------------------------------


class TestFromSettings:
    def test_from_settings_returns_router(self):
        router = IntentRouter.from_settings()
        assert isinstance(router, IntentRouter)

    def test_from_settings_classifies(self):
        router = IntentRouter.from_settings()
        result = router.classify("move the wall")
        assert result.family == TaskFamily.EDIT_PLAN
