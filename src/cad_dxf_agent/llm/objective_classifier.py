"""Two-axis objective classifier — wraps IntentRouter with objective intelligence.

Classifies prompts along two axes:
  1. RequestClass (8 values: understand, estimate, recommend, optimize,
     modify, summarize, compare, validate)
  2. ObjectiveTag (15 values: cost_reduction, space_count, missing_items, etc.)

The classifier runs heuristic pattern matching first, falling back to the
existing IntentRouter for TaskFamily routing. Backward compatible — all
existing router behavior is preserved.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    ObjectiveTag,
    RequestClass,
)
from cad_dxf_agent.models.response_schema import TaskFamily

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ClassRule:
    """Pattern rule for RequestClass detection."""

    request_class: RequestClass
    patterns: tuple[str, ...]
    confidence: float = 0.90


@dataclass(frozen=True)
class _TagRule:
    """Pattern rule for ObjectiveTag detection."""

    tag: ObjectiveTag
    patterns: tuple[str, ...]


# --- RequestClass rules (priority-ordered, first match wins) ---

_CLASS_RULES: list[_ClassRule] = [
    _ClassRule(
        request_class=RequestClass.COMPARE,
        patterns=(
            r"\bcompare\b",
            r"\bdiff\b",
            r"\bwhat\s+changed\b",
            r"\bchanges?\s+between\b",
            r"\brevision\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.VALIDATE,
        patterns=(
            r"\bvalidat",
            r"\bcheck\s+(for\s+)?(compliance|completeness|consistency|missing)\b",
            r"\bcode\s+complian",
            r"\bmissing\s+(sheets?|notes?|dimensions?|labels?)\b",
            r"\bverify\b",
            r"\baudit\b",
            r"\bcompliant\b",
            r"\bmeeting?\s+(code|requirement|standard)\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.OPTIMIZE,
        patterns=(
            r"\bcheaper\b",
            r"\breduce\s+cost\b",
            r"\bcut\s+cost\b",
            r"\bdecrease.*cost\b",
            r"\bsave\s+money\b",
            r"\boptimize\b",
            r"\bmore\s+efficient\b",
            r"\breduce\s+labor\b",
            r"\bsimplify\b",
            r"\bstreamline\b",
            r"\b\d+%\s+(cheaper|less|smaller|reduction)\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.MODIFY,
        patterns=(
            r"\bshrink\b",
            r"\bgrow\b",
            r"\bexpand\b",
            r"\bmake\s+(this|the|it)\b.*\b(bigger|smaller|larger|wider|narrower)\b",
            r"\bmove\b",
            r"\bdelete\b",
            r"\bremove\b",
            r"\badd\b",
            r"\binsert\b",
            r"\breplace\b",
            r"\bchange\b",
            r"\bedit\b",
            r"\bmodify\b",
            r"\brelocate\b",
            r"\brotate\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.RECOMMEND,
        patterns=(
            r"\brecommend\b",
            r"\bsuggest\b",
            r"\bwhat\s+would\s+look\s+good\b",
            r"\bhow\s+many.*would\s+(look|be|fit)\b",
            r"\bwhat\s+options\b",
            r"\balternatives?\b",
            r"\bideas?\s+for\b",
            r"\bimprove\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.ESTIMATE,
        patterns=(
            r"\bhow\s+much\b.*\bcost\b",
            r"\bhow\s+much\b.*\bwould\b",
            r"\bestimate\b",
            r"\btakeoff\b",
            r"\bquantity\b",
            r"\bbill\s+of\b",
            r"\bmaterial\s+list\b",
            r"\bcount\b",
            r"\bhow\s+many\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.SUMMARIZE,
        patterns=(
            r"\bsummar(y|ize|ise)\b",
            r"\boverview\b",
            r"\bdescribe\b",
            r"\bfor\s+the\s+(customer|client|homeowner|contractor|reviewer)\b",
            r"\bpresentation\b",
            r"\bbrief\b",
            r"\bexplain\s+to\b",
        ),
    ),
    _ClassRule(
        request_class=RequestClass.UNDERSTAND,
        patterns=(
            r"\bwhat\s+is\b",
            r"\bwhere\s+is\b",
            r"\bwhich\s+layer\b",
            r"\bshow\s+me\b",
            r"\btell\s+me\b",
            r"\bwhat\s+are\b",
            r"\bhow\s+big\b",
            r"\bare\s+there\b",
            r"\bis\s+there\b",
            r"\bfind\b",
        ),
        confidence=0.85,
    ),
]

# --- ObjectiveTag rules (all matched, best wins) ---

_TAG_RULES: list[_TagRule] = [
    _TagRule(
        tag=ObjectiveTag.COST_REDUCTION,
        patterns=(
            r"\bcost\b",
            r"\bcheaper\b",
            r"\bexpens",
            r"\bprice\b",
            r"\bbudget\b",
            r"\bsave\s+money\b",
            r"\baffordable\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.LABOR_REDUCTION,
        patterns=(
            r"\blabor\b",
            r"\bwork\s+hours?\b",
            r"\binstall\s+time\b",
            r"\bcrew\b",
            r"\bman\s*hours?\b",
            r"\bfaster\s+to\s+(build|install)\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.AREA_CHANGE,
        patterns=(
            r"\bsq\s*ft\b",
            r"\bsquare\s+feet\b",
            r"\barea\b",
            r"\bshrink\b",
            r"\bexpand\b",
            r"\bsmaller\b",
            r"\bbigger\b",
            r"\broom\s+size\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.AESTHETICS,
        patterns=(
            r"\blook\s+good\b",
            r"\baesthetic",
            r"\bbeautif",
            r"\bvisual",
            r"\bappearance\b",
            r"\bstyle\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.QUANTITY_ESTIMATION,
        patterns=(
            r"\bhow\s+many\b",
            r"\bcount\b",
            r"\bquantity\b",
            r"\btakeoff\b",
            r"\binventory\b",
            r"\bbill\s+of\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.CUSTOMER_COMMUNICATION,
        patterns=(
            r"\bcustomer\b",
            r"\bclient\b",
            r"\bhomeowner\b",
            r"\bowner\b",
            r"\bfor\s+(the|my)\s+(customer|client|homeowner|owner)\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.CONTRACTOR_COMMUNICATION,
        patterns=(
            r"\bcontractor\b",
            r"\bsubcontractor\b",
            r"\bsub\b",
            r"\bfield\s+crew\b",
            r"\bfor\s+(the|my)\s+(contractor|sub|gc|builder)\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.REVIEWER_COMMUNICATION,
        patterns=(
            r"\breviewer\b",
            r"\bplan\s+check",
            r"\binspector\b",
            r"\bbuilding\s+department\b",
            r"\bpermit\s+review\b",
            r"\bfor\s+(the|my)\s+(reviewer|inspector)\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.CONSTRUCTABILITY,
        patterns=(
            r"\bconstructab",
            r"\bbuild(able|ability)\b",
            r"\bfield\s+(issue|problem|concern)\b",
            r"\binstall",
            r"\bfeasib",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.COMPLIANCE,
        patterns=(
            r"\bcode\s+complian",
            r"\bADA\b",
            r"\bsetback\b",
            r"\bzoning\b",
            r"\bpermit\b",
            r"\bregulat",
            r"\brequirement\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.REVISION_EXPLANATION,
        patterns=(
            r"\bwhat\s+changed\b",
            r"\brevision\b",
            r"\bdiff\b",
            r"\bcompare\b",
            r"\bchanges?\s+between\b",
            r"\bupdated\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.SPACE_COUNT,
        patterns=(
            r"\broom(s)?\b",
            r"\bspace(s)?\b",
            r"\bzone(s)?\b",
            r"\benclosure(s)?\b",
            r"\bhow\s+many\s+rooms?\b",
            r"\bfloor\s+plan\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.EQUIPMENT_COUNT,
        patterns=(
            r"\bfixture(s)?\b",
            r"\bdevice(s)?\b",
            r"\bequipment\b",
            r"\boutlet(s)?\b",
            r"\bswitch(es)?\b",
            r"\bpanel(s)?\b",
            r"\bappliance(s)?\b",
            r"\bplant(s)?\b",
            r"\btree(s)?\b",
            r"\bshrub(s)?\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.LAYOUT_IMPROVEMENT,
        patterns=(
            r"\blayout\b",
            r"\bplacement\b",
            r"\bspacing\b",
            r"\barrangement\b",
            r"\bflow\b",
            r"\bcirculation\b",
            r"\bdensity\b",
        ),
    ),
    _TagRule(
        tag=ObjectiveTag.MISSING_ITEMS,
        patterns=(
            r"\bmissing\b",
            r"\bincomplete\b",
            r"\bforgotten\b",
            r"\blacking\b",
            r"\bwhere\s+is\s+the\b",
            r"\bshould\s+(there\s+)?be\b",
        ),
    ),
]

# Pre-compile
_COMPILED_CLASS_RULES: list[tuple[_ClassRule, list[re.Pattern[str]]]] = [
    (rule, [re.compile(p, re.IGNORECASE) for p in rule.patterns])
    for rule in _CLASS_RULES
]

_COMPILED_TAG_RULES: list[tuple[_TagRule, list[re.Pattern[str]]]] = [
    (rule, [re.compile(p, re.IGNORECASE) for p in rule.patterns])
    for rule in _TAG_RULES
]


# --- Mapping: TaskFamily -> default RequestClass ---

_FAMILY_TO_CLASS: dict[TaskFamily, RequestClass] = {
    TaskFamily.COMPARE: RequestClass.COMPARE,
    TaskFamily.EDIT_PLAN: RequestClass.MODIFY,
    TaskFamily.APPLY_EDIT: RequestClass.MODIFY,
    TaskFamily.TAKEOFF_ESTIMATE: RequestClass.ESTIMATE,
    TaskFamily.DESIGN_ASSIST: RequestClass.RECOMMEND,
    TaskFamily.SUMMARY: RequestClass.SUMMARIZE,
    TaskFamily.QNA: RequestClass.UNDERSTAND,
    TaskFamily.REPEATED_CONDITION: RequestClass.UNDERSTAND,
    TaskFamily.MARKUP_INTERPRETATION: RequestClass.UNDERSTAND,
    TaskFamily.NEEDS_CLARIFICATION: RequestClass.UNDERSTAND,
    TaskFamily.UNSUPPORTED: RequestClass.UNDERSTAND,
}


class ObjectiveClassifier:
    """Two-axis intent classifier wrapping the existing IntentRouter.

    Adds objective context (RequestClass + ObjectiveTag) above the existing
    TaskFamily routing. Backward compatible — IntentRouter still runs for
    TaskFamily classification.
    """

    def classify(self, prompt: str) -> ObjectiveClassification:
        """Classify a prompt into RequestClass + optional ObjectiveTag."""
        start = time.monotonic()
        stripped = prompt.strip()

        if not stripped:
            elapsed = (time.monotonic() - start) * 1000
            return ObjectiveClassification(
                request_class=RequestClass.UNDERSTAND,
                confidence=1.0,
                source="heuristic",
                matched_patterns=["empty_prompt"],
                classification_time_ms=elapsed,
            )

        # Axis 1: RequestClass (priority-ordered, first match)
        request_class: RequestClass | None = None
        class_confidence = 0.85
        class_patterns: list[str] = []

        for rule, compiled in _COMPILED_CLASS_RULES:
            for pattern in compiled:
                if pattern.search(stripped):
                    request_class = rule.request_class
                    class_confidence = rule.confidence
                    class_patterns.append(pattern.pattern)
                    break
            if request_class is not None:
                break

        # Axis 2: ObjectiveTag (all matched, pick best by match count)
        tag_scores: dict[ObjectiveTag, int] = {}
        tag_patterns: list[str] = []
        for tag_rule, tag_compiled in _COMPILED_TAG_RULES:
            matched = [p for p in tag_compiled if p.search(stripped)]
            if matched:
                tag_scores[tag_rule.tag] = len(matched)
                tag_patterns.extend(p.pattern for p in matched)

        objective_tag: ObjectiveTag | None = None
        if tag_scores:
            # Deterministic: highest score wins, tie-break by tag name (asc)
            objective_tag = sorted(
                tag_scores, key=lambda t: (-tag_scores[t], t.value),
            )[0]

        # Fallback: if no class matched, infer from tag or default
        if request_class is None:
            if objective_tag in (
                ObjectiveTag.COST_REDUCTION,
                ObjectiveTag.LABOR_REDUCTION,
            ):
                request_class = RequestClass.OPTIMIZE
                class_confidence = 0.75
            elif objective_tag == ObjectiveTag.AREA_CHANGE:
                request_class = RequestClass.MODIFY
                class_confidence = 0.75
            elif objective_tag in (
                ObjectiveTag.QUANTITY_ESTIMATION,
                ObjectiveTag.SPACE_COUNT,
                ObjectiveTag.EQUIPMENT_COUNT,
            ):
                request_class = RequestClass.ESTIMATE
                class_confidence = 0.75
            elif objective_tag in (
                ObjectiveTag.CUSTOMER_COMMUNICATION,
                ObjectiveTag.CONTRACTOR_COMMUNICATION,
                ObjectiveTag.REVIEWER_COMMUNICATION,
            ):
                request_class = RequestClass.SUMMARIZE
                class_confidence = 0.75
            elif objective_tag == ObjectiveTag.MISSING_ITEMS:
                request_class = RequestClass.VALIDATE
                class_confidence = 0.75
            elif objective_tag == ObjectiveTag.LAYOUT_IMPROVEMENT:
                request_class = RequestClass.RECOMMEND
                class_confidence = 0.75
            else:
                request_class = RequestClass.UNDERSTAND
                class_confidence = 0.50

        elapsed = (time.monotonic() - start) * 1000
        return ObjectiveClassification(
            request_class=request_class,
            objective_tag=objective_tag,
            confidence=class_confidence,
            source="heuristic",
            matched_patterns=class_patterns + tag_patterns,
            classification_time_ms=elapsed,
        )

    def classify_with_family(
        self, prompt: str, task_family: TaskFamily,
    ) -> ObjectiveClassification:
        """Classify using both the objective heuristic and an existing TaskFamily.

        If the heuristic is confident, use it. Otherwise, infer RequestClass
        from the TaskFamily as a fallback.
        """
        result = self.classify(prompt)

        # If heuristic confidence is low, use TaskFamily mapping
        if result.confidence < 0.70 and task_family in _FAMILY_TO_CLASS:
            result.request_class = _FAMILY_TO_CLASS[task_family]
            result.confidence = 0.80
            result.source = "family_fallback"

        return result
