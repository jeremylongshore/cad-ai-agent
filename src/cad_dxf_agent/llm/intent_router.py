"""Hybrid intent router — heuristic-first classification with optional LLM fallback.

Classifies user prompts into TaskFamily categories using keyword patterns.
LLM fallback is structured but disabled by default (CAD_ROUTER_LLM_ENABLED=false).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from pydantic import BaseModel, Field

from cad_dxf_agent.models.response_schema import TaskFamily
from cad_dxf_agent.otel import span as otel_span

logger = logging.getLogger(__name__)


class IntentResult(BaseModel):
    """Result of intent classification."""

    family: TaskFamily
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "heuristic"  # "heuristic" or "llm"
    matched_pattern: str | None = None
    router_time_ms: float = 0.0
    fallback_reason: str | None = None
    clarification_required: bool = False


@dataclass(frozen=True)
class HeuristicRule:
    """A keyword-based classification rule."""

    family: TaskFamily
    patterns: tuple[str, ...]
    confidence: float = 0.95
    requires_word_boundary: bool = True


# Priority-ordered heuristic rules (first match wins within same priority)
_RULES: list[HeuristicRule] = [
    # Priority 1: Compare/diff
    HeuristicRule(
        family=TaskFamily.COMPARE,
        patterns=(
            r"\bcompare\b",
            r"\bdiff\b",
            r"\bwhat\s+changed\b",
            r"\brevision\b",
            r"\bdifference",
            r"\bchanges?\s+between\b",
        ),
    ),
    # Priority 2: Markup interpretation
    HeuristicRule(
        family=TaskFamily.MARKUP_INTERPRETATION,
        patterns=(
            r"\bmarkup\b",
            r"\bcloud\b",
            r"\bredline\b",
            r"\brevision\s+cloud\b",
            r"\bdelta\s+cloud\b",
        ),
    ),
    # Priority 3: Edit plan
    HeuristicRule(
        family=TaskFamily.EDIT_PLAN,
        patterns=(
            r"\bmove\b",
            r"\bshift\b",
            r"\bdelete\b",
            r"\bremove\b",
            r"\bchange\s+text\b",
            r"\brename\b",
            r"\badd\b",
            r"\binsert\b",
            r"\brelocate\b",
            r"\breplace\b",
            r"\bmodify\b",
            r"\bedit\b",
            r"\bupdate\b",
            r"\brotate\b",
            r"\bscale\b",
        ),
    ),
    # Priority 4: Takeoff / estimation
    HeuristicRule(
        family=TaskFamily.TAKEOFF_ESTIMATE,
        patterns=(
            r"\btakeoff\b",
            r"\bquantity\b",
            r"\bestimate\b",
            r"\bcount\s+all\b",
            r"\bbill\s+of\b",
            r"\bmaterial\s+list\b",
            r"\bcount\b.*\b(door|window|room|wall|column|beam|fixture)s?\b",
            r"\bhow\s+many\b.*\b(door|window|room|wall|column|beam|fixture)s?\b",
        ),
    ),
    # Priority 5: Repeated condition
    HeuristicRule(
        family=TaskFamily.REPEATED_CONDITION,
        patterns=(
            r"\bfind\s+all\b",
            r"\bevery\s+instance\b",
            r"\brecurring\b",
            r"\bpattern\b",
            r"\brepeated\b",
            r"\ball\s+instances\b",
            r"\bbatch\b",
            r"\bcondition\s+report\b",
            r"\bcondition\s+plan\b",
        ),
    ),
    # Priority 6: Design assist
    HeuristicRule(
        family=TaskFamily.DESIGN_ASSIST,
        patterns=(
            r"\bsuggest\b",
            r"\bimprove\b",
            r"\boptimize\b",
            r"\brecommend\b",
            r"\bbetter\s+layout\b",
            r"\blayout\b",
            r"\bplacement\b",
            r"\bspacing\b",
            r"\barrangement\b",
            r"\bscope\s+of\s+work\b",
            r"\bfull\s+report\b",
            r"\bdesign\s+summary\b",
            r"\bgrid\s+summary\b",
            r"\bbay\b",
            r"\bstructural\s+grid\b",
            r"\bcolumn\s+grid\b",
            r"\bfield\s+summary\b",
            r"\bfield\s+report\b",
            r"\bconstruction\s+summary\b",
            r"\bsite\s+report\b",
        ),
    ),
    # Priority 7: Summary
    HeuristicRule(
        family=TaskFamily.SUMMARY,
        patterns=(
            r"\bsummar(y|ize|ise)\b",
            r"\boverview\b",
            r"\bdescribe\b",
            r"\bstatistics\b",
            r"\bstats\b",
            r"\brevision\s+summary\b",
            r"\bexplain\s+changes\b",
            r"\bwhat\s+was\s+updated\b",
            r"\bwhat.+this\s+(drawing|plan|blueprint)\b",
            r"\bbreak\s*down\b",
        ),
    ),
    # Priority 8: Q&A (broad — catches natural questions)
    HeuristicRule(
        family=TaskFamily.QNA,
        patterns=(
            r"\bwhat\s+is\b",
            r"\bwhich\s+layer\b",
            r"\bwhere\s+is\b",
            r"\bshow\s+me\b",
            r"\bhow\s+many\b",
            r"\blist\s+all\b",
            r"\btell\s+me\b",
            r"\bwhat\s+are\b",
            r"\bwhat\s+text\b",
            r"\bwhat\s+do\s+you\s+see\b",
            r"\bwhat.+in\s+this\b",
            r"\bare\s+there\b",
            r"\bis\s+there\b",
            r"\bdo\s+you\s+see\b",
            r"\bcan\s+you\s+see\b",
            r"\bhow\s+big\b",
            r"\bwhat.+drawing\b",
            r"\bwhat.+plan\b",
            r"\bwhat.+blueprint\b",
            r"\btell\s+me\s+about\b",
            r"\bwhat\s+does\b",
            r"\bfind\b",
            r"\bsearch\b",
            r"\blook\s+for\b",
            r"\bidentify\b",
        ),
    ),
]

# Pre-compile all patterns
_COMPILED_RULES: list[tuple[HeuristicRule, list[re.Pattern[str]]]] = [
    (rule, [re.compile(p, re.IGNORECASE) for p in rule.patterns]) for rule in _RULES
]


class IntentRouter:
    """Classifies user prompts into TaskFamily categories.

    Uses priority-ordered heuristic rules. LLM fallback is structured
    but returns needs_clarification by default (CAD_ROUTER_LLM_ENABLED=false).
    """

    def __init__(
        self,
        confidence_threshold: float = 0.9,
        llm_enabled: bool = False,
    ) -> None:
        self._confidence_threshold = confidence_threshold
        self._llm_enabled = llm_enabled

    @classmethod
    def from_settings(cls) -> IntentRouter:
        """Create router from application settings."""
        try:
            from cad_dxf_agent.settings import settings

            return cls(
                confidence_threshold=settings.router_confidence_threshold,
                llm_enabled=settings.router_llm_enabled,
            )
        except Exception:
            return cls()

    def classify(self, prompt: str) -> IntentResult:
        """Classify a user prompt into a TaskFamily.

        Returns IntentResult with family, confidence, and source.
        """
        with otel_span("cad.router.classify") as s:
            start = time.monotonic()

            # Empty/whitespace-only prompts
            stripped = prompt.strip()
            if not stripped:
                elapsed = (time.monotonic() - start) * 1000
                result = IntentResult(
                    family=TaskFamily.NEEDS_CLARIFICATION,
                    confidence=1.0,
                    source="heuristic",
                    matched_pattern="empty_prompt",
                    router_time_ms=elapsed,
                )
                _set_span_attrs(s, result)
                return result

            # Run heuristic rules in priority order
            heuristic_result = self._heuristic_classify(stripped)

            if (
                heuristic_result is not None
                and heuristic_result.confidence >= self._confidence_threshold
            ):
                elapsed = (time.monotonic() - start) * 1000
                heuristic_result.router_time_ms = elapsed
                _set_span_attrs(s, heuristic_result)
                return heuristic_result

            # LLM fallback (disabled by default)
            if self._llm_enabled:
                llm_result = self._llm_classify(stripped)
                if llm_result is not None:
                    elapsed = (time.monotonic() - start) * 1000
                    llm_result.router_time_ms = elapsed
                    _set_span_attrs(s, llm_result)
                    return llm_result

            # Default fallback
            elapsed = (time.monotonic() - start) * 1000
            fallback = IntentResult(
                family=TaskFamily.NEEDS_CLARIFICATION,
                confidence=0.5,
                source="heuristic",
                matched_pattern="no_match",
                router_time_ms=elapsed,
                fallback_reason="no_heuristic_match",
                clarification_required=True,
            )
            _set_span_attrs(s, fallback)
            return fallback

    def _heuristic_classify(self, prompt: str) -> IntentResult | None:
        """Run priority-ordered heuristic rules."""
        for rule, compiled in _COMPILED_RULES:
            for pattern in compiled:
                match = pattern.search(prompt)
                if match:
                    return IntentResult(
                        family=rule.family,
                        confidence=rule.confidence,
                        source="heuristic",
                        matched_pattern=pattern.pattern,
                    )
        return None

    def _llm_classify(self, prompt: str) -> IntentResult | None:
        """LLM-based classification (stub — returns needs_clarification).

        When CAD_ROUTER_LLM_ENABLED=true, this would call the LLM with
        a structured output schema. Currently returns needs_clarification
        to avoid doubling latency until we have data to justify it.
        """
        logger.debug("LLM classification requested but returning fallback")
        return IntentResult(
            family=TaskFamily.NEEDS_CLARIFICATION,
            confidence=0.6,
            source="llm",
            matched_pattern=None,
        )


def _set_span_attrs(s: object, result: IntentResult) -> None:
    """Set OTel span attributes from an IntentResult."""
    if hasattr(s, "set_attribute"):
        s.set_attribute("cad.router.family", result.family.value)
        s.set_attribute("cad.router.confidence", result.confidence)
        s.set_attribute("cad.router.source", result.source)
        s.set_attribute("cad.router.time_ms", result.router_time_ms)
