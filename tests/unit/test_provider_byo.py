"""Bring-your-own-provider: dynamic loading of a custom PlannerProvider.

`get_provider()` accepts a dotted import path ("package.module:Attr" or
"package.module.Attr") and loads any PlannerProvider — no fork of the planner
dispatch required. Misconfiguration is a hard error, never a silent mock.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.planner import get_provider
from cad_dxf_agent.llm.providers import PlannerProvider

# This test module is already imported by pytest, so it is importable by name —
# we reference the providers defined below via "<this module>:<Attr>".
MOD = __name__


class GoodProvider(PlannerProvider):
    """A minimal valid custom provider, constructible with no arguments."""

    @property
    def name(self) -> str:
        return "byo-good"

    def plan(self, prompt, drawing_context, conversation_history=None):  # noqa: D102
        raise NotImplementedError("not exercised — these tests cover loading only")


# A module-level, already-constructed instance (loading an instance, not a class).
good_instance = GoodProvider()


class NotAProvider:
    """Deliberately NOT a PlannerProvider."""


class NeedsArgs(PlannerProvider):
    """Custom provider with a required constructor arg — must fail to load."""

    def __init__(self, required):  # no default → not no-arg constructible
        self._required = required

    @property
    def name(self) -> str:
        return "needs-args"

    def plan(self, prompt, drawing_context, conversation_history=None):  # noqa: D102
        raise NotImplementedError


class TestBringYourOwnProvider:
    def test_loads_class_via_colon(self):
        provider = get_provider(f"{MOD}:GoodProvider")
        assert isinstance(provider, PlannerProvider)
        assert provider.name == "byo-good"

    def test_loads_class_via_dotted_real_module(self):
        # Stable dotted path: the shipped MockProvider, loaded as a custom path.
        provider = get_provider("cad_dxf_agent.llm.mock_provider.MockProvider")
        assert isinstance(provider, PlannerProvider)
        assert provider.name == "mock"

    def test_loads_an_already_constructed_instance(self):
        provider = get_provider(f"{MOD}:good_instance")
        assert provider is good_instance

    def test_bad_module_raises_value_error(self):
        with pytest.raises(ValueError, match="could not import module"):
            get_provider("no.such.module_xyz:Whatever")

    def test_missing_attribute_raises_value_error(self):
        with pytest.raises(ValueError, match="no attribute"):
            get_provider(f"{MOD}:DoesNotExist")

    def test_attribute_not_a_provider_raises(self):
        with pytest.raises(ValueError, match="must be a PlannerProvider"):
            get_provider(f"{MOD}:NotAProvider")

    def test_constructor_requiring_args_raises_clear_error(self):
        with pytest.raises(ValueError, match="no arguments"):
            get_provider(f"{MOD}:NeedsArgs")

    def test_bare_unknown_name_still_falls_back_to_mock(self):
        # Regression: names without ':' or '.' are NOT import paths.
        provider = get_provider("totally-unknown-xyz")
        assert provider.name == "mock"

    def test_builtin_names_unaffected(self):
        assert get_provider("mock").name == "mock"
