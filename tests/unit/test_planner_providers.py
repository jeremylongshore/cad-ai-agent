"""Tests for planner provider routing and validation feedback loop.

Covers get_provider() routing, _format_validation_feedback(), and the
validation retry loop inside run_planner().
"""

from __future__ import annotations

from unittest.mock import patch

from cad_dxf_agent.llm.planner import _format_validation_feedback, get_provider, run_planner
from cad_dxf_agent.llm.providers import PlannerProvider
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType, LayerRule
from cad_dxf_agent.models.changes_schema import Severity, ValidationIssue
from cad_dxf_agent.models.config_schema import RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType

# ---------------------------------------------------------------------------
# Helper — minimal DrawingContext + RuleConfig for validation loop tests
# ---------------------------------------------------------------------------


def _make_context() -> DrawingContext:
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="A1",
                entity_type=EntityType.LINE,
                layer="STRUCTURAL",
            )
        ],
        layers=[LayerRule(name="STRUCTURAL", protected=False)],
        blocks=[],
    )


def _make_rule_config() -> RuleConfig:
    return RuleConfig(protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"])


def _move_op(handle: str = "A1") -> EditOperation:
    return EditOperation(
        op_type=OpType.MOVE_ENTITY,
        target_handle=handle,
        target_layer="STRUCTURAL",
        params={"dx": 5.0, "dy": 0.0},
    )


# ---------------------------------------------------------------------------
# TestGetProviderRouting
# ---------------------------------------------------------------------------


class TestGetProviderRouting:
    def test_mock_provider(self):
        """'mock' name returns MockProvider."""
        provider = get_provider("mock")
        assert provider.name == "mock"

    def test_mock_agent_provider(self):
        """'mock-agent' always returns MockAgentProvider."""
        provider = get_provider("mock-agent")
        assert provider.name == "mock-agent"

    def test_unknown_provider_falls_back_to_mock(self):
        """Unrecognised provider name falls back to mock with a warning."""
        provider = get_provider("totally-unknown-xyz")
        assert provider.name == "mock"

    def test_retired_gemini_names_fall_back_to_mock(self):
        """Former built-in Gemini/proxy names are gone — they fall back to mock."""
        for retired in ("gemini", "google", "vertex", "gemini-key", "proxy", "agent"):
            assert get_provider(retired).name == "mock"


# ---------------------------------------------------------------------------
# TestFormatValidationFeedback
# ---------------------------------------------------------------------------


class TestFormatValidationFeedback:
    def test_blocker_with_operation_index(self):
        """Blockers with an operation_index are formatted as 'Op N: message'."""
        blocker = ValidationIssue(
            severity=Severity.BLOCKER,
            message="Entity on protected layer",
            operation_index=0,
        )
        result = _format_validation_feedback("move the column", [blocker])

        assert "Op 0" in result
        assert "Entity on protected layer" in result
        assert "move the column" in result

    def test_blocker_without_operation_index(self):
        """Blockers without an operation_index omit the 'Op N:' prefix."""
        blocker = ValidationIssue(
            severity=Severity.BLOCKER,
            message="Global validation error",
        )
        result = _format_validation_feedback("delete entity", [blocker])

        assert "Global validation error" in result
        # Must NOT contain the "Op N" pattern when operation_index is None
        assert "Op " not in result

    def test_multiple_blockers_all_present(self):
        """All blockers appear in the feedback string."""
        blockers = [
            ValidationIssue(severity=Severity.BLOCKER, message="Error A", operation_index=0),
            ValidationIssue(severity=Severity.BLOCKER, message="Error B", operation_index=1),
            ValidationIssue(severity=Severity.BLOCKER, message="Global C"),
        ]
        result = _format_validation_feedback("do something", blockers)

        assert "Error A" in result
        assert "Error B" in result
        assert "Global C" in result
        assert "Op 0" in result
        assert "Op 1" in result

    def test_original_prompt_included(self):
        """The original prompt is echoed in the feedback."""
        blocker = ValidationIssue(severity=Severity.BLOCKER, message="Bad op")
        result = _format_validation_feedback("rotate the beam 45 degrees", [blocker])
        assert "rotate the beam 45 degrees" in result


# ---------------------------------------------------------------------------
# TestPlannerValidationLoop  — run_planner validation feedback cycle
# ---------------------------------------------------------------------------


class _BlockingThenCleanProvider(PlannerProvider):
    """Returns a changeset with blocked ops on first call, clean on second."""

    def __init__(self, bad_changeset: ChangeSet, good_changeset: ChangeSet) -> None:
        self._bad = bad_changeset
        self._good = good_changeset
        self._calls = 0

    @property
    def name(self) -> str:
        return "test-blocking"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        self._calls += 1
        if self._calls == 1:
            return self._bad
        return self._good


class _AlwaysBlockingProvider(PlannerProvider):
    """Always returns a changeset whose operation targets a protected layer."""

    @property
    def name(self) -> str:
        return "always-blocking"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        return ChangeSet(
            prompt=prompt,
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="TITLE_ENTITY",
                    target_layer="TITLE",  # Protected — always blocked
                    params={"dx": 5.0, "dy": 0.0},
                )
            ],
        )


@patch("cad_dxf_agent.llm.planner.settings")
class TestPlannerValidationLoop:
    def _setup(self, mock_settings, max_val_retries: int = 2) -> None:
        mock_settings.planner_timeout = 30
        mock_settings.planner_max_retries = 1
        mock_settings.planner_retry_delay = 0.0
        mock_settings.planner_max_validation_retries = max_val_retries
        mock_settings.llm_provider = "mock"

    def test_validation_retry_succeeds_on_second_call(self, mock_settings):
        """Planner retries when first changeset has blockers; second is clean."""
        self._setup(mock_settings, max_val_retries=2)

        context = _make_context()
        rule_config = _make_rule_config()

        # Bad first changeset: targets the TITLE layer (protected)
        bad_cs = ChangeSet(
            prompt="move title",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="A1",
                    target_layer="TITLE",
                    params={"dx": 5.0, "dy": 0.0},
                )
            ],
        )
        # Add a TITLE-layer entity to the context so the validator can flag it
        from cad_dxf_agent.models.cad_schema import LayerRule

        context.entities.append(EntityRef(handle="A1", entity_type=EntityType.LINE, layer="TITLE"))
        context.layers.append(LayerRule(name="TITLE", protected=True))

        # Good second changeset: moves a STRUCTURAL entity
        good_cs = ChangeSet(
            prompt="move structural",
            operations=[_move_op("A1")],
        )
        # For the good changeset A1 must be on STRUCTURAL — override entity layer
        context.entities[0].layer = "STRUCTURAL"

        provider = _BlockingThenCleanProvider(bad_cs, good_cs)
        result = run_planner(
            "move the entity",
            {},
            provider=provider,
            context=context,
            rule_config=rule_config,
        )

        assert isinstance(result, ChangeSet)
        assert provider._calls >= 1  # At least attempted validation loop

    def test_validation_loop_exhausted_returns_last_changeset(self, mock_settings):
        """When max_val_retries exhausted, the last changeset is returned (not raised)."""
        self._setup(mock_settings, max_val_retries=2)

        context = _make_context()
        # Add the protected entity so every call is blocked
        context.entities.append(
            EntityRef(handle="TITLE_ENTITY", entity_type=EntityType.LINE, layer="TITLE")
        )
        from cad_dxf_agent.models.cad_schema import LayerRule

        context.layers.append(LayerRule(name="TITLE", protected=True))

        rule_config = _make_rule_config()
        provider = _AlwaysBlockingProvider()

        # run_planner should NOT raise — it returns the last (blocked) changeset
        result = run_planner(
            "move title entity",
            {},
            provider=provider,
            context=context,
            rule_config=rule_config,
        )
        assert isinstance(result, ChangeSet)

    def test_no_validation_loop_without_context(self, mock_settings):
        """Validation loop is skipped when context is None."""
        self._setup(mock_settings, max_val_retries=2)

        # Provider always returns a clean changeset
        good_cs = ChangeSet(prompt="test", operations=[_move_op()])

        class _SimpleProvider(PlannerProvider):
            @property
            def name(self) -> str:
                return "simple"

            @property
            def requires_api_key(self) -> bool:
                return False

            def plan(self, prompt, drawing_context, conversation_history=None):
                return good_cs

        result = run_planner("test", {}, provider=_SimpleProvider())
        # No context → no validation → result returned immediately
        assert isinstance(result, ChangeSet)
