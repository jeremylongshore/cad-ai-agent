"""Vision describer — Stage 1 of the two-stage hybrid vision pipeline.

Takes a PNG render of a drawing and produces a text description of the
layout using Gemini Flash vision. The description is then fed into
Stage 2 (the agent planner) as additional context, avoiding the need
to send the image on every turn of the tool-use loop.

This module is optional — if no image is available, the agent works
with entity JSON alone.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..otel import get_tracer
from ..settings import settings

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

VISION_PROMPT = (
    "You are a structural engineering drawing analyst. "
    "Describe this 2D CAD drawing concisely. Include:\n"
    "1. Drawing type (foundation plan, framing plan, detail, etc.)\n"
    "2. Grid line layout (labels and approximate spacing)\n"
    "3. Key structural elements (footings, walls, columns, beams) and their locations\n"
    "4. Text annotations and labels visible\n"
    "5. Title block content if visible\n"
    "6. Overall dimensions and scale if discernible\n\n"
    "Be factual and precise. Reference grid intersections when describing locations. "
    "Use the coordinate system visible in the drawing."
)


def describe_drawing(image_path: str | Path) -> str:
    """Send a drawing image to Gemini Flash for layout description.

    Args:
        image_path: Path to a PNG render of the drawing.

    Returns:
        Text description of the drawing layout.

    Raises:
        FileNotFoundError: If the image file doesn't exist.
        RuntimeError: If Gemini is unavailable or returns an error.
    """
    with tracer.start_as_current_span("cad.vision_describe") as span:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        span.set_attribute("cad.vision.image", image_path.name)

        model_name = settings.vision_model
        span.set_attribute("cad.vision.model", model_name)

        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, Image, Part

            vertexai.init(
                project=settings.gcp_project,
                location=settings.gcp_location,
            )

            model = GenerativeModel(model_name)
            image = Image.load_from_file(str(image_path))

            response = model.generate_content(
                [Part.from_image(image), VISION_PROMPT]  # type: ignore[arg-type]
            )

            description: str = str(response.text)
            if not description:
                raise RuntimeError("Gemini returned empty vision description")

            span.set_attribute("cad.vision.description_length", len(description))
            logger.info(
                "Vision description generated (%d chars) for %s",
                len(description),
                image_path.name,
            )
            return description

        except ImportError as err:
            raise RuntimeError(
                "google-cloud-aiplatform not installed. "
                "Install with: pip install google-cloud-aiplatform"
            ) from err


def describe_drawing_mock(image_path: str | Path | None = None) -> str:
    """Return a mock vision description for testing without API access.

    Produces a realistic structural drawing description that exercises
    the downstream planning pipeline.
    """
    return (
        "This is a structural foundation plan. "
        "Grid lines A through E run vertically (left to right) at 20-foot spacing. "
        "Grid lines 1 through 4 run horizontally (bottom to top) at 24-foot spacing. "
        "Spread footings F1 through F12 are located at grid intersections, "
        'typically 4\'-0" x 4\'-0" x 12" deep. '
        "A continuous wall footing runs along grid line A from grid 1 to grid 4. "
        "Column marks C1 through C12 are placed at each footing location. "
        "Text note at bottom: 'SEE STRUCTURAL DETAILS SHEET S-2'. "
        "Title block reads: 'FOUNDATION PLAN - BUILDING A'."
    )
