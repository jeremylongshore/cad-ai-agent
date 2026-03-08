"""Strategy selector registry — maps (RequestClass, ObjectiveTag?) to stage pipelines.

Given a two-axis classification (RequestClass + optional ObjectiveTag), the registry
returns a StagePipelineDefinition that determines which stages run and in what order.

This is the routing brain that sits between classification and execution.
"""

from __future__ import annotations

import logging

from cad_dxf_agent.models.objective_schema import (
    ObjectiveTag,
    RequestClass,
    StagePipelineDefinition,
)

logger = logging.getLogger(__name__)


# Default pipelines per RequestClass (when no tag-specific override exists)
_CLASS_DEFAULTS: dict[RequestClass, StagePipelineDefinition] = {
    RequestClass.UNDERSTAND: StagePipelineDefinition(
        stages=["analyze"],
        output_mode="direct",
        description="Direct analysis — answer the question from drawing context",
    ),
    RequestClass.ESTIMATE: StagePipelineDefinition(
        stages=["analyze", "quantify"],
        output_mode="direct",
        description="Count or measure from drawing context, return structured quantities",
    ),
    RequestClass.RECOMMEND: StagePipelineDefinition(
        stages=["analyze", "recommend"],
        output_mode="staged",
        description="Analyze drawing, then generate ranked recommendations with tradeoffs",
    ),
    RequestClass.OPTIMIZE: StagePipelineDefinition(
        stages=["analyze", "recommend", "plan"],
        output_mode="staged",
        description="Analyze for optimization targets, recommend options, plan edits",
    ),
    RequestClass.MODIFY: StagePipelineDefinition(
        stages=["plan", "preview"],
        output_mode="full",
        description="Plan edit operations, generate preview for user approval",
    ),
    RequestClass.SUMMARIZE: StagePipelineDefinition(
        stages=["analyze", "summarize"],
        output_mode="direct",
        description="Analyze drawing context, produce human-readable summary",
    ),
    RequestClass.COMPARE: StagePipelineDefinition(
        stages=["compare"],
        output_mode="direct",
        description="Run comparison pipeline between master and revision",
    ),
    RequestClass.VALIDATE: StagePipelineDefinition(
        stages=["analyze", "validate"],
        output_mode="direct",
        description="Check drawing for completeness, compliance, or consistency issues",
    ),
}

# Tag-specific overrides: (RequestClass, ObjectiveTag) -> pipeline
# These refine the default when a specific objective is detected
_TAG_OVERRIDES: dict[tuple[RequestClass, ObjectiveTag], StagePipelineDefinition] = {
    (RequestClass.OPTIMIZE, ObjectiveTag.COST_REDUCTION): StagePipelineDefinition(
        stages=["analyze", "quantify", "recommend", "plan"],
        output_mode="staged",
        description="Identify cost drivers, quantify savings candidates, recommend reductions",
    ),
    (RequestClass.OPTIMIZE, ObjectiveTag.LABOR_REDUCTION): StagePipelineDefinition(
        stages=["analyze", "quantify", "recommend"],
        output_mode="staged",
        description="Identify labor-intensive elements, suggest simplification options",
    ),
    (RequestClass.ESTIMATE, ObjectiveTag.SPACE_COUNT): StagePipelineDefinition(
        stages=["analyze", "detect_zones", "quantify"],
        output_mode="direct",
        description="Detect enclosed zones/rooms, count and measure spaces",
    ),
    (RequestClass.ESTIMATE, ObjectiveTag.EQUIPMENT_COUNT): StagePipelineDefinition(
        stages=["analyze", "quantify"],
        output_mode="direct",
        description="Count fixtures/devices/equipment by type and zone",
    ),
    (RequestClass.SUMMARIZE, ObjectiveTag.CUSTOMER_COMMUNICATION): StagePipelineDefinition(
        stages=["analyze", "summarize"],
        output_mode="direct",
        description="Produce plain-language summary suitable for homeowner/client",
    ),
    (RequestClass.SUMMARIZE, ObjectiveTag.CONTRACTOR_COMMUNICATION): StagePipelineDefinition(
        stages=["analyze", "quantify", "summarize"],
        output_mode="direct",
        description="Produce technical summary with quantities for field crew",
    ),
    (RequestClass.SUMMARIZE, ObjectiveTag.REVIEWER_COMMUNICATION): StagePipelineDefinition(
        stages=["analyze", "validate", "summarize"],
        output_mode="direct",
        description="Produce compliance-focused summary for plan reviewer",
    ),
    (RequestClass.RECOMMEND, ObjectiveTag.LAYOUT_IMPROVEMENT): StagePipelineDefinition(
        stages=["analyze", "recommend"],
        output_mode="staged",
        description="Analyze spatial layout, recommend density/placement improvements",
    ),
    (RequestClass.VALIDATE, ObjectiveTag.COMPLIANCE): StagePipelineDefinition(
        stages=["analyze", "validate"],
        output_mode="direct",
        description="Check drawing against code compliance indicators",
    ),
    (RequestClass.VALIDATE, ObjectiveTag.MISSING_ITEMS): StagePipelineDefinition(
        stages=["analyze", "validate"],
        output_mode="direct",
        description="Scan for missing sheets, labels, dimensions, or notes",
    ),
}


class StrategyRegistry:
    """Registry that maps classification results to stage pipeline definitions.

    Lookup order:
    1. Tag-specific override: (RequestClass, ObjectiveTag) exact match
    2. Class default: RequestClass default pipeline
    3. Fallback: single-stage analyze pipeline
    """

    def __init__(
        self,
        *,
        class_defaults: dict[RequestClass, StagePipelineDefinition] | None = None,
        tag_overrides: (
            dict[tuple[RequestClass, ObjectiveTag], StagePipelineDefinition] | None
        ) = None,
    ) -> None:
        self._class_defaults = class_defaults or dict(_CLASS_DEFAULTS)
        self._tag_overrides = tag_overrides or dict(_TAG_OVERRIDES)

    def lookup(
        self,
        request_class: RequestClass,
        objective_tag: ObjectiveTag | None = None,
    ) -> StagePipelineDefinition:
        """Find the best pipeline definition for a classification result."""
        # Try tag-specific override first
        if objective_tag is not None:
            key = (request_class, objective_tag)
            if key in self._tag_overrides:
                logger.debug(
                    "Strategy override: %s × %s",
                    request_class.value,
                    objective_tag.value,
                )
                return self._tag_overrides[key]

        # Fall back to class default
        if request_class in self._class_defaults:
            logger.debug("Strategy default: %s", request_class.value)
            return self._class_defaults[request_class]

        # Ultimate fallback
        logger.warning("No strategy for %s, using analyze fallback", request_class.value)
        return StagePipelineDefinition(
            stages=["analyze"],
            output_mode="direct",
            description="Fallback: single-stage analysis",
        )

    def register_override(
        self,
        request_class: RequestClass,
        objective_tag: ObjectiveTag,
        pipeline: StagePipelineDefinition,
    ) -> None:
        """Register a tag-specific pipeline override."""
        self._tag_overrides[(request_class, objective_tag)] = pipeline

    def register_default(
        self,
        request_class: RequestClass,
        pipeline: StagePipelineDefinition,
    ) -> None:
        """Register or replace a class-level default pipeline."""
        self._class_defaults[request_class] = pipeline

    @property
    def all_defaults(self) -> dict[RequestClass, StagePipelineDefinition]:
        return dict(self._class_defaults)

    @property
    def all_overrides(self) -> dict[tuple[RequestClass, ObjectiveTag], StagePipelineDefinition]:
        return dict(self._tag_overrides)
