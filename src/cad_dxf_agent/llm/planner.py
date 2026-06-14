"""Planner — orchestrates prompt-to-changeset flow via provider backends."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path

from ..core.validators import validate_changeset
from ..models.cad_schema import DrawingContext
from ..models.config_schema import RuleConfig
from ..models.ops_schema import ChangeSet
from ..models.trace_schema import PlannerTrace
from ..otel import get_tracer
from ..settings import settings
from .errors import PlannerRetryExhaustedError, PlannerTimeoutError
from .mock_provider import MockProvider
from .providers import PlannerProvider

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _is_import_path(spec: str) -> bool:
    """True if ``spec`` looks like a dotted import path to a custom provider.

    Accepts ``package.module:Attr`` (canonical) or ``package.module.Attr``.
    Bare names like ``openai`` or ``totally-unknown-xyz`` are NOT import paths
    and fall through to the mock fallback, preserving existing behaviour.
    """
    return ":" in spec or "." in spec


def _load_custom_provider(spec: str) -> PlannerProvider:
    """Dynamically load a user-supplied :class:`PlannerProvider` (bring-your-own).

    ``spec`` is ``package.module:Attr`` (preferred) or ``package.module.Attr``.
    ``Attr`` may be a ``PlannerProvider`` subclass (instantiated with no
    arguments) or an already-constructed ``PlannerProvider`` instance. A custom
    provider reads its own configuration (keys, endpoints, model) from the
    environment in its constructor.

    Misconfiguration is a hard error — a broken custom provider never silently
    falls back to mock, so failures surface immediately instead of producing
    keyword-matched nonsense.

    Raises:
        ValueError: spec malformed, module/attribute unimportable, the attribute
            is not constructible with no arguments, or the loaded object is not a
            ``PlannerProvider``.
    """
    import importlib

    if ":" in spec:
        module_path, _, attr = spec.partition(":")
    else:
        module_path, _, attr = spec.rpartition(".")
    if not module_path or not attr:
        raise ValueError(
            f"CAD_LLM_PROVIDER='{spec}' is not a valid provider import path. "
            "Use 'your_package.module:YourProvider'."
        )

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ValueError(
            f"CAD_LLM_PROVIDER='{spec}': could not import module '{module_path}' ({exc})."
        ) from exc
    try:
        obj = getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(
            f"CAD_LLM_PROVIDER='{spec}': module '{module_path}' has no attribute '{attr}'."
        ) from exc

    if isinstance(obj, type):
        try:
            provider: object = obj()
        except Exception as exc:
            raise ValueError(
                f"CAD_LLM_PROVIDER='{spec}': could not instantiate {attr}() — a custom "
                "provider must be constructible with no arguments and read its config "
                f"from the environment ({exc})."
            ) from exc
    else:
        provider = obj

    if not isinstance(provider, PlannerProvider):
        raise ValueError(
            f"CAD_LLM_PROVIDER='{spec}': {attr} must be a PlannerProvider subclass or "
            f"instance, got {type(provider).__name__}."
        )
    logger.info("Loaded custom planner provider: %s", provider.name)
    return provider


def get_provider(
    provider_name: str | None = None,
    image_path: Path | None = None,
    request_class: str = "modify",
) -> PlannerProvider:
    """Get the configured planner provider.

    Defaults to mock provider if no provider is configured or if CAD_LLM_PROVIDER=mock.

    Args:
        provider_name: Override for the provider name.
        image_path: Optional path to a rendered PNG for vision-augmented planning.
        request_class: RequestClass value for tool narrowing (default "modify").
    """
    raw = provider_name or settings.llm_provider
    name = raw.lower()

    if name == "mock":
        return MockProvider()

    if name in ("gemini", "google", "vertex"):
        try:
            from .gemini_provider import GeminiProvider

            return GeminiProvider()
        except ImportError:
            logger.warning(
                "google-cloud-aiplatform not installed, falling back to mock. "
                "Install with: pip install google-cloud-aiplatform"
            )
            return MockProvider()

    if name == "agent":
        try:
            from .agent_provider import AgentProvider

            return AgentProvider(image_path=image_path, request_class=request_class)
        except ImportError:
            logger.warning(
                "google-cloud-aiplatform not installed, falling back to mock-agent. "
                "Install with: pip install google-cloud-aiplatform"
            )
            from .agent_provider import MockAgentProvider

            return MockAgentProvider()

    if name == "mock-agent":
        from .agent_provider import MockAgentProvider

        return MockAgentProvider()

    if name == "gemini-key":
        try:
            from .gemini_key_provider import GeminiKeyProvider

            return GeminiKeyProvider()
        except ImportError:
            logger.warning(
                "google-generativeai not installed, falling back to mock. "
                "Install with: pip install google-generativeai"
            )
            return MockProvider()

    if name in ("proxy", "proxy-agent"):
        try:
            from .proxy_client import ProxyAgentProvider

            return ProxyAgentProvider(image_path=image_path)
        except ValueError as e:
            logger.warning("Proxy provider misconfigured (%s), falling back to mock-agent", e)
            from .agent_provider import MockAgentProvider

            return MockAgentProvider()

    # Bring-your-own-provider: an unknown name shaped like a dotted import path
    # ("your_pkg.module:YourProvider") is loaded dynamically and validated as a
    # PlannerProvider. Bare unknown names fall back to mock.
    if _is_import_path(raw):
        return _load_custom_provider(raw)
    logger.warning("Unknown provider '%s', falling back to mock", name)
    return MockProvider()


def _call_with_timeout(
    provider: PlannerProvider,
    prompt: str,
    drawing_context: dict,
    timeout: int,
    conversation_history: list[dict] | None = None,
) -> ChangeSet:
    """Call provider.plan() with a wall-clock timeout."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(provider.plan, prompt, drawing_context, conversation_history)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            raise PlannerTimeoutError(timeout) from exc


def _format_validation_feedback(
    original_prompt: str,
    blockers: list,
) -> str:
    """Format validation blockers into a corrective prompt for the LLM."""
    blocker_lines = "\n".join(
        f"  - Op {b.operation_index}: {b.message}"
        if b.operation_index is not None
        else f"  - {b.message}"
        for b in blockers
    )
    return (
        f"Your previous changeset was rejected by validation with these errors:\n"
        f"{blocker_lines}\n\n"
        f"Please fix these issues and try again. Original request: {original_prompt}"
    )


def run_planner(
    prompt: str,
    drawing_context: dict,
    provider: PlannerProvider | None = None,
    image_path: Path | None = None,
    context: DrawingContext | None = None,
    rule_config: RuleConfig | None = None,
    conversation_history: list[dict] | None = None,
    request_class: str = "modify",
) -> ChangeSet:
    """Run the planner to generate a changeset from a user prompt.

    Tries deterministic planning first for obvious operations.
    Falls back to the LLM provider with timeout and retry logic.

    When *context* and *rule_config* are provided, validates the changeset
    after each LLM call.  If validation finds blockers, the errors are
    formatted into a corrective prompt and the LLM is re-called (up to
    ``settings.planner_max_validation_retries`` times).

    Args:
        prompt: Natural-language edit request from the user.
        drawing_context: Drawing context dict from semantic_model.build_planner_context().
        provider: Optional override for the planner provider.
        image_path: Optional path to a rendered PNG for vision-augmented planning.
        context: Optional DrawingContext for in-loop validation.
        rule_config: Optional RuleConfig for in-loop validation.

    Returns:
        Validated ChangeSet with structured operations.

    Raises:
        PlannerTimeoutError: If the planner exceeds wall-clock timeout.
        PlannerRetryExhaustedError: If all retry attempts fail.
    """
    with tracer.start_as_current_span("cad.run_planner") as span:
        if provider is None:
            provider = get_provider(image_path=image_path, request_class=request_class)

        # Try deterministic planner first (no LLM call needed)
        from .deterministic_planner import deterministic_plan

        det_result = deterministic_plan(prompt, drawing_context)
        if det_result is not None:
            span.set_attribute("cad.mode", "deterministic")
            span.set_attribute("cad.ops.count", det_result.op_count)
            logger.info(
                "Deterministic plan used (%d ops) for prompt: %s",
                det_result.op_count,
                prompt[:80],
            )
            det_result.planner_trace = PlannerTrace(
                provider_name="deterministic",
                total_turns=0,
                total_duration_ms=0.0,
                deterministic=True,
            )
            return det_result

        span.set_attribute("cad.mode", provider.name)
        logger.info("Running planner [%s] for prompt: %s", provider.name, prompt[:80])

        timeout = settings.planner_timeout
        max_retries = settings.planner_max_retries
        retry_delay = settings.planner_retry_delay
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                changeset = _call_with_timeout(
                    provider, prompt, drawing_context, timeout, conversation_history
                )
                span.set_attribute("cad.planner.attempt", attempt)
                logger.info(
                    "Planner returned %d operation(s) on attempt %d for prompt: %s",
                    changeset.op_count,
                    attempt,
                    prompt[:80],
                )

                # Validation feedback loop (only when context + rules provided)
                if context is not None and rule_config is not None:
                    max_val_retries = settings.planner_max_validation_retries
                    for val_attempt in range(1, max_val_retries + 1):
                        result = validate_changeset(changeset, context, rule_config)
                        if not result.blockers:
                            break
                        logger.warning(
                            "Validation found %d blocker(s) on attempt %d/%d: %s",
                            len(result.blockers),
                            val_attempt,
                            max_val_retries,
                            "; ".join(b.message for b in result.blockers),
                        )
                        if val_attempt >= max_val_retries:
                            logger.warning("Validation retries exhausted, returning last changeset")
                            break
                        corrective = _format_validation_feedback(prompt, result.blockers)
                        changeset = _call_with_timeout(
                            provider,
                            corrective,
                            drawing_context,
                            timeout,
                            conversation_history,
                        )

                span.set_attribute("cad.ops.count", changeset.op_count)
                return changeset
            except PlannerTimeoutError:
                raise  # Timeout is not retryable
            except Exception as exc:
                last_error = exc
                logger.warning("Planner attempt %d/%d failed: %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.info("Retrying in %.1fs...", delay)
                    time.sleep(delay)

        raise PlannerRetryExhaustedError(max_retries, last_error)
