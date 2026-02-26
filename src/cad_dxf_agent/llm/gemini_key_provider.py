"""Gemini planner provider — API key auth via google-generativeai SDK.

Uses the public Gemini API with an API key (no GCP project or ADC needed).
Set CAD_GEMINI_API_KEY and CAD_LLM_PROVIDER=gemini-key to use.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..models.ops_schema import ChangeSet
from ..otel import get_tracer
from ..settings import settings
from .prompt_templates import SYSTEM_PROMPT, format_planner_prompt
from .providers import PlannerProvider
from .response_parser import parse_planner_response

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class GeminiKeyProvider(PlannerProvider):
    """Gemini via public API key — no GCP credentials required."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.gemini_model
        self._max_retries = settings.gemini_max_retries
        self._model: Any = None

    @property
    def name(self) -> str:
        return f"gemini-key ({self._model_name})"

    @property
    def requires_api_key(self) -> bool:
        return True

    def plan(self, prompt: str, drawing_context: dict) -> ChangeSet:
        with tracer.start_as_current_span("cad.gemini_key_plan") as span:
            span.set_attribute("cad.gemini.model", self._model_name)

            model = self._get_model()
            context_json = json.dumps(drawing_context, indent=2, default=str)
            text_prompt = format_planner_prompt(prompt, context_json)

            raw_response = model.generate_content(text_prompt).text
            span.set_attribute("cad.gemini.response_length", len(raw_response))

            try:
                changeset = parse_planner_response(raw_response, prompt)
                span.set_attribute("cad.ops.count", changeset.op_count)
                return changeset
            except ValueError as e:
                logger.warning("Gemini response validation failed: %s", e)
                if self._max_retries < 1:
                    raise

                span.add_event("gemini_key_retry", {"error": str(e)})
                retry_text = (
                    f"{text_prompt}\n\n"
                    f"Your previous response was invalid:\n"
                    f"Response: {raw_response[:500]}\n"
                    f"Error: {e}\n\n"
                    f"Please fix and return valid JSON matching the operations schema."
                )
                raw_retry = model.generate_content(retry_text).text
                changeset = parse_planner_response(raw_retry, prompt)
                span.set_attribute("cad.ops.count", changeset.op_count)
                span.set_attribute("cad.gemini.retried", True)
                return changeset

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            import google.generativeai as genai  # type: ignore[import-untyped]
        except ImportError as err:
            raise ImportError(
                "google-generativeai not installed. Install with: pip install google-generativeai"
            ) from err

        api_key = settings.get_api_key("gemini-key")
        if not api_key:
            raise ValueError(
                "CAD_GEMINI_API_KEY not set. Get a key at https://aistudio.google.com/apikey"
            )

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            self._model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.types.GenerationConfig(
                temperature=settings.llm_temperature,
                top_p=settings.llm_top_p,
                top_k=settings.llm_top_k,
                max_output_tokens=settings.llm_max_output_tokens,
            ),
        )
        return self._model
