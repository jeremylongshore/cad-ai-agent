"""Gemini planner provider — Vertex AI multimodal vision pipeline.

Uses Gemini 1.5 Pro on Vertex AI for hybrid vision planning:
  1. DXF entity JSON (precise coordinates, handles, layers)
  2. PNG render of the drawing (visual layout context)
  3. User prompt

Gemini returns a ChangeSet JSON validated by Pydantic.
Retries once on validation failure with error feedback.
Falls back to MockProvider if Gemini is unavailable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..models.ops_schema import ChangeSet
from ..otel import get_tracer
from ..settings import settings
from .prompt_templates import SYSTEM_PROMPT, format_planner_prompt
from .providers import PlannerProvider
from .response_parser import parse_planner_response

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class GeminiProvider(PlannerProvider):
    """Gemini 1.5 Pro on Vertex AI — multimodal CAD planner.

    Sends drawing context (JSON + optional PNG) to Gemini and
    parses the structured ChangeSet response.
    """

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._project = project or settings.gcp_project
        self._location = location or settings.gcp_location
        self._model_name = model_name or settings.gemini_model
        self._max_retries = settings.gemini_max_retries
        self._model: Any = None  # lazy init

    @property
    def name(self) -> str:
        return f"gemini ({self._model_name})"

    @property
    def requires_api_key(self) -> bool:
        return False  # Uses GCP credentials, not API key

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        image_path: str | Path | None = None,
    ) -> ChangeSet:
        """Generate a ChangeSet from prompt + drawing context + optional image.

        Args:
            prompt: User's natural-language edit request.
            drawing_context: JSON-serializable drawing context.
            image_path: Optional path to a PNG render of the drawing.

        Returns:
            Validated ChangeSet with structured operations.
        """
        with tracer.start_as_current_span("cad.gemini_plan") as span:
            span.set_attribute("cad.gemini.model", self._model_name)
            span.set_attribute("cad.gemini.has_image", image_path is not None)

            model = self._get_model()
            contents = self._build_contents(prompt, drawing_context, image_path)

            # First attempt
            raw_response = self._call_gemini(model, contents)
            span.set_attribute("cad.gemini.response_length", len(raw_response))

            try:
                changeset = parse_planner_response(raw_response, prompt)
                span.set_attribute("cad.ops.count", changeset.op_count)
                return changeset
            except ValueError as e:
                logger.warning("Gemini response validation failed: %s", e)

                if self._max_retries < 1:
                    raise

                # Retry with error feedback
                span.add_event("gemini_retry", {"error": str(e)})
                retry_text = (
                    f"\nYour previous response was invalid:\n"
                    f"Response: {raw_response[:500]}\n"
                    f"Error: {e}\n\n"
                    f"Please fix and return valid JSON matching the operations schema."
                )
                retry_contents = contents + [retry_text]
                raw_retry = self._call_gemini(model, retry_contents)

                changeset = parse_planner_response(raw_retry, prompt)
                span.set_attribute("cad.ops.count", changeset.op_count)
                span.set_attribute("cad.gemini.retried", True)
                return changeset

    def _get_model(self):
        """Lazy-initialize the Gemini model."""
        if self._model is None:
            try:
                import vertexai  # type: ignore[import-untyped]
                from vertexai.generative_models import (
                    GenerativeModel,  # type: ignore[import-untyped]
                )

                vertexai.init(
                    project=self._project,
                    location=self._location,
                )
                self._model = GenerativeModel(
                    self._model_name,
                    system_instruction=SYSTEM_PROMPT,
                )
            except ImportError as err:
                raise ImportError(
                    "google-cloud-aiplatform not installed. "
                    "Install with: pip install google-cloud-aiplatform"
                ) from err
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Gemini: {e}") from e

        return self._model

    def _build_contents(
        self,
        prompt: str,
        drawing_context: dict,
        image_path: str | Path | None,
    ) -> list:
        """Build the content list for Gemini.

        For real Gemini calls, content includes Part objects.
        For mocked tests, content is simple strings.
        """
        parts: list = []

        # Add drawing image if available (vision pipeline)
        if image_path is not None:
            img_path = Path(image_path)
            if img_path.exists():
                try:
                    from vertexai.generative_models import (  # type: ignore[import-untyped]
                        Image,
                        Part,
                    )

                    image = Image.load_from_file(str(img_path))
                    parts.append(Part.from_image(image))
                    logger.info("Including drawing image: %s", img_path.name)
                except ImportError:
                    logger.warning("Cannot include image: vertexai not installed")

        # Add the text prompt with drawing context
        context_json = json.dumps(drawing_context, indent=2, default=str)
        text_prompt = format_planner_prompt(prompt, context_json)
        parts.append(text_prompt)

        return parts

    def _call_gemini(self, model, contents: list) -> str:
        """Call Gemini and return the text response.

        The model.generate_content() method accepts either Part objects
        or plain strings, so this works with both real SDK and mocks.
        """
        response = model.generate_content(contents)

        text = response.text if hasattr(response, "text") else str(response)
        if not text:
            raise ValueError("Gemini returned empty response")

        return text
