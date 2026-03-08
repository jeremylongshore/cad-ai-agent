"""Document family heuristic detector — infers drawing type from content signals.

Analyzes layer names, block names, and text content to infer which of the 20
document families a drawing most likely belongs to. The result is a HINT that
refines output phrasing — it never gates capability.

Detection strategy:
1. Collect all signal strings (layer names, block names, text excerpts)
2. Score each family by keyword match count
3. Return the top-scoring family if it exceeds a minimum threshold
4. Fall back to UNKNOWN if no family scores high enough
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass

from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.objective_schema import DocumentFamilyHint

logger = logging.getLogger(__name__)

# Minimum matches required to declare a family (avoids false positives)
_MIN_SIGNAL_THRESHOLD = 2


@dataclass(frozen=True)
class FamilyDetectionResult:
    """Result of document family detection."""

    family: DocumentFamilyHint
    confidence: float  # 0.0-1.0
    signal_count: int  # total keyword matches
    top_signals: list[str]  # up to 5 matched keywords
    runner_up: DocumentFamilyHint | None = None


# --- Family signal patterns ---
# Each family has keywords that commonly appear in layer names, block names,
# or text labels for that document type. Patterns are case-insensitive.

_FAMILY_SIGNALS: dict[DocumentFamilyHint, list[str]] = {
    DocumentFamilyHint.RESIDENTIAL_ARCHITECTURAL: [
        "bedroom", "bathroom", "kitchen", "living",
        "garage", "porch", "closet", "foyer",
        "master", "dining", "laundry", "pantry",
        "residential", "house", "home",
    ],
    DocumentFamilyHint.COMMERCIAL_ARCHITECTURAL: [
        "lobby", "elevator", "stairwell", "corridor",
        "tenant", "suite", "office", "conference",
        "reception", "commercial", "retail", "storefront",
        "vestibule", "atrium",
    ],
    DocumentFamilyHint.STRUCTURAL: [
        "column", "beam", "footing", "foundation",
        "rebar", "steel", "concrete", "structural",
        "slab", "truss", "joist", "girder",
        "shear", "moment", "framing",
        r"s-\d", r"s\d",  # S-1, S1 layer naming
    ],
    DocumentFamilyHint.CIVIL_SITE: [
        "grading", "contour", "elevation", "topography",
        "storm", "drainage", "swale", "culvert",
        "pavement", "curb", "gutter", "sidewalk",
        "easement", "right-of-way", "civil", "site",
    ],
    DocumentFamilyHint.LANDSCAPE: [
        "plant", "tree", "shrub", "groundcover",
        "irrigation", "planting", "landscape", "turf",
        "mulch", "hedge", "flower", "garden",
        "hardscape", "paver", "boulder",
        r"l-\d", r"la-",  # L-1, LA- layer naming
    ],
    DocumentFamilyHint.ELECTRICAL: [
        "outlet", "switch", "panel", "circuit",
        "electrical", "conduit", "wire", "receptacle",
        "junction", "breaker", "transformer", "lighting",
        "fixture", "lamp", "watt",
        r"e-\d", r"e\d",  # E-1, E1 layer naming
    ],
    DocumentFamilyHint.MECHANICAL: [
        "duct", "hvac", "diffuser", "thermostat",
        "mechanical", "air handler", "ahu", "vav",
        "supply", "return", "exhaust", "damper",
        "furnace", "boiler", "chiller",
        r"m-\d", r"m\d",  # M-1, M1 layer naming
    ],
    DocumentFamilyHint.PLUMBING: [
        "plumbing", "pipe", "drain", "sewer",
        "water", "fixture", "toilet", "sink",
        "valve", "faucet", "riser", "cleanout",
        "hot water", "cold water", "waste",
        r"p-\d", r"p\d",  # P-1, P1 layer naming
    ],
    DocumentFamilyHint.FIRE_SAFETY: [
        "sprinkler", "fire alarm", "fire protection",
        "standpipe", "extinguisher", "smoke detector",
        "fire rated", "fire wall", "egress",
        "fire department", "hydrant",
        r"fp-", r"fa-",  # FP-, FA- layer naming
    ],
    DocumentFamilyHint.INTERIOR_DESIGN: [
        "finish", "furniture", "millwork", "casework",
        "interior", "cabinet", "countertop", "tile",
        "carpet", "flooring", "wallpaper", "upholstery",
        "drapery", "ceiling",
        r"id-",  # ID- layer naming
    ],
    DocumentFamilyHint.KITCHEN_BATH: [
        "kitchen", "bath", "vanity", "shower",
        "tub", "countertop", "backsplash", "cabinet",
        "appliance", "range", "refrigerator", "dishwasher",
    ],
    DocumentFamilyHint.PERMIT_SET: [
        "permit", "code", "occupancy", "egress",
        "accessibility", "ada", "building department",
        "zoning", "setback", "lot coverage",
        "general notes", "sheet index",
    ],
    DocumentFamilyHint.AS_BUILT: [
        "as-built", "as built", "existing", "field verify",
        "field measured", "actual", "surveyed",
        "record drawing", "existing conditions",
    ],
    DocumentFamilyHint.SHOP_FABRICATION: [
        "shop", "fabricat", "detail", "weld",
        "assembly", "part", "material", "gauge",
        "bend", "cut", "drill", "tolerance",
    ],
    DocumentFamilyHint.FACILITY_MAINTENANCE: [
        "maintenance", "facility", "asset", "equipment",
        "service", "replacement", "lifecycle",
        "inventory", "preventive", "corrective",
    ],
    DocumentFamilyHint.SURVEY_BOUNDARY: [
        "survey", "boundary", "property line", "lot line",
        "monument", "benchmark", "traverse",
        "bearing", "distance", "plat",
        "legal description", "parcel",
    ],
    DocumentFamilyHint.CONSTRUCTION_LOGISTICS: [
        "staging", "crane", "scaffold", "temporary",
        "construction entrance", "laydown",
        "barricade", "traffic control", "phasing",
        "logistics", "site access",
    ],
    DocumentFamilyHint.SOLAR_ENERGY: [
        "solar", "photovoltaic", "pv panel", "inverter",
        "array", "module", "racking", "combiner",
        "net meter", "renewable",
    ],
    DocumentFamilyHint.SIGNAGE_WAYFINDING: [
        "sign", "wayfinding", "directional", "monument sign",
        "ada sign", "room sign", "exit sign",
        "illuminated", "channel letter", "pylon",
    ],
}

# Pre-compile patterns for each family
_COMPILED_SIGNALS: dict[
    DocumentFamilyHint, list[re.Pattern[str]]
] = {
    family: [re.compile(p, re.IGNORECASE) for p in patterns]
    for family, patterns in _FAMILY_SIGNALS.items()
}


def detect_document_family(
    context: DrawingContext,
) -> FamilyDetectionResult:
    """Detect the document family from drawing content signals.

    Scans layer names, block names, and text content for industry keywords.
    Returns the best-matching family with confidence score.
    """
    # Collect signal strings from the drawing
    signals: list[str] = []

    # Layer names are the strongest signal
    for layer in context.layers:
        signals.append(layer.name)

    # Block names
    for block in context.blocks:
        signals.append(block)

    # Text content (sample — cap at 200 to avoid perf issues)
    text_count = 0
    for entity in context.entities:
        if entity.text_content and text_count < 200:
            signals.append(entity.text_content)
            text_count += 1

    # Score each family
    combined = " ".join(signals)
    scores: Counter[DocumentFamilyHint] = Counter()
    matched_keywords: dict[DocumentFamilyHint, list[str]] = {}

    for family, patterns in _COMPILED_SIGNALS.items():
        keywords: list[str] = []
        for pattern in patterns:
            if pattern.search(combined):
                scores[family] += 1
                keywords.append(pattern.pattern)
        if keywords:
            matched_keywords[family] = keywords

    if not scores:
        return FamilyDetectionResult(
            family=DocumentFamilyHint.UNKNOWN,
            confidence=0.0,
            signal_count=0,
            top_signals=[],
        )

    # Pick the top family
    top_family, top_score = scores.most_common(1)[0]

    # Runner-up for ambiguity detection
    runner_up = None
    if len(scores) >= 2:
        runner_up = scores.most_common(2)[1][0]

    # Confidence based on score relative to threshold and total signals
    if top_score < _MIN_SIGNAL_THRESHOLD:
        return FamilyDetectionResult(
            family=DocumentFamilyHint.UNKNOWN,
            confidence=float(top_score) / _MIN_SIGNAL_THRESHOLD * 0.3,
            signal_count=top_score,
            top_signals=matched_keywords.get(top_family, [])[:5],
            runner_up=top_family,
        )

    # Scale confidence: 2 matches = 0.5, 5+ = 0.8, 10+ = 0.95
    max_signals = len(_FAMILY_SIGNALS.get(top_family, []))
    ratio = min(top_score / max(max_signals, 1), 1.0)
    confidence = min(0.4 + ratio * 0.55, 0.95)

    return FamilyDetectionResult(
        family=top_family,
        confidence=confidence,
        signal_count=top_score,
        top_signals=matched_keywords.get(top_family, [])[:5],
        runner_up=runner_up,
    )
