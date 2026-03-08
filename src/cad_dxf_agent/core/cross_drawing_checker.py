"""Cross-drawing consistency checker.

Deterministic (no LLM) analysis of multiple DrawingContext objects from a
single drawing set (e.g., floor plan + RCP + electrical plan). The checker
runs five independent passes — room labels, layer naming, block consistency,
entity counts, and coordinate alignment — and aggregates all findings into a
ConsistencyReport.

Typical usage::

    from cad_dxf_agent.core.cross_drawing_checker import check_consistency
    from cad_dxf_agent.core.dxf_reader import load_drawing

    contexts = [load_drawing(p) for p in sheet_paths]
    report = check_consistency(contexts)
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.title}")

All public functions are pure and side-effect-free. Results are fully
deterministic: the same set of DrawingContext objects always produces
identical findings in identical order.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from itertools import combinations

from cad_dxf_agent.core.family_detector import detect_document_family
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.consistency_schema import (
    ConsistencyCategory,
    ConsistencyFinding,
    ConsistencyReport,
    ConsistencySeverity,
    SheetInfo,
)

# Room label detection — matches common room/space names in text content
_ROOM_PATTERN = re.compile(
    r"\b("
    r"bedroom|kitchen|bathroom|bath|living|dining|office|closet|"
    r"garage|master|foyer|laundry|pantry|hallway|corridor|lobby|"
    r"reception|conference|storage|utility|mechanical|studio|"
    r"den|nursery|library|loft|attic|basement|porch|deck|"
    r"balcony|entry|vestibule|mudroom|sunroom|family"
    r")\b",
    re.IGNORECASE,
)

# Default layers to exclude from "unique layer" comparisons
_DEFAULT_LAYERS = frozenset({"0", "defpoints", "Defpoints", "DEFPOINTS"})


def check_consistency(
    contexts: list[DrawingContext],
) -> ConsistencyReport:
    """Check multiple drawing sheets for cross-document consistency issues.

    Takes a list of DrawingContext objects (one per sheet in a drawing set)
    and verifies that room labels, layer naming, block usage, and entity
    counts are consistent across sheets.

    Returns a ConsistencyReport with findings categorized by severity.
    """
    if not contexts:
        return ConsistencyReport(sheets=[], checks_run=[])

    # Build sheet info for each context
    sheets = [_build_sheet_info(ctx) for ctx in contexts]

    findings: list[ConsistencyFinding] = []
    checks_run: list[str] = []

    # Run all checks
    findings.extend(_check_room_labels(sheets))
    checks_run.append("room_labels")

    findings.extend(_check_layer_naming(contexts))
    checks_run.append("layer_naming")

    findings.extend(_check_block_consistency(sheets))
    checks_run.append("block_consistency")

    findings.extend(_check_entity_counts(sheets))
    checks_run.append("entity_counts")

    findings.extend(_check_coordinate_alignment(contexts))
    checks_run.append("coordinate_alignment")

    # Count by severity
    error_count = sum(1 for f in findings if f.severity == ConsistencySeverity.ERROR)
    warning_count = sum(
        1 for f in findings if f.severity == ConsistencySeverity.WARNING
    )
    info_count = sum(1 for f in findings if f.severity == ConsistencySeverity.INFO)

    return ConsistencyReport(
        sheets=sheets,
        findings=findings,
        checks_run=checks_run,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
    )


def _build_sheet_info(context: DrawingContext) -> SheetInfo:
    """Extract metadata and signals from a single drawing context."""
    family_result = detect_document_family(context)

    # Extract room labels from text content
    room_labels: set[str] = set()
    for entity in context.entities:
        if entity.text_content:
            matches = _ROOM_PATTERN.findall(entity.text_content)
            for match in matches:
                room_labels.add(match.lower())

    # Collect unique block names from INSERT entities
    block_names: set[str] = set()
    for entity in context.entities:
        if entity.block_name:
            block_names.add(entity.block_name)

    return SheetInfo(
        file_path=context.file_path,
        family=family_result.family.value,
        layer_count=len(context.layers),
        entity_count=len(context.entities),
        room_labels=sorted(room_labels),
        block_names=sorted(block_names),
    )


def _generate_finding_id(
    category: str,
    title: str,
    sheet_a: str,
    sheet_b: str | None = None,
) -> str:
    """Generate a deterministic finding ID."""
    raw = f"{category}|{title}|{sheet_a}|{sheet_b or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


# --- Individual checks ---


def _check_room_labels(sheets: list[SheetInfo]) -> list[ConsistencyFinding]:
    """Compare room labels across sheets for mismatches."""
    findings: list[ConsistencyFinding] = []

    # Check for sheets with no room labels
    for sheet in sheets:
        if not sheet.room_labels:
            findings.append(
                ConsistencyFinding(
                    finding_id=_generate_finding_id(
                        "room_labels", "no_labels", sheet.file_path
                    ),
                    category=ConsistencyCategory.ROOM_LABELS,
                    severity=ConsistencySeverity.INFO,
                    title="No room labels detected",
                    description=(
                        f"No room/space labels found in '{sheet.file_path}'. "
                        "Cross-sheet label comparison skipped for this sheet."
                    ),
                    sheet_a=sheet.file_path,
                )
            )

    # Pairwise comparison of room labels
    sheets_with_labels = [s for s in sheets if s.room_labels]
    for sheet_a, sheet_b in combinations(sheets_with_labels, 2):
        labels_a = set(sheet_a.room_labels)
        labels_b = set(sheet_b.room_labels)

        only_in_a = labels_a - labels_b
        only_in_b = labels_b - labels_a

        for label in sorted(only_in_a):
            findings.append(
                ConsistencyFinding(
                    finding_id=_generate_finding_id(
                        "room_labels", f"missing_{label}", sheet_a.file_path,
                        sheet_b.file_path,
                    ),
                    category=ConsistencyCategory.ROOM_LABELS,
                    severity=ConsistencySeverity.WARNING,
                    title=f"Room label '{label}' missing from sheet",
                    description=(
                        f"Room '{label}' appears in '{sheet_a.file_path}' "
                        f"but not in '{sheet_b.file_path}'."
                    ),
                    sheet_a=sheet_a.file_path,
                    sheet_b=sheet_b.file_path,
                    details={"missing_label": label, "direction": "a_not_in_b"},
                )
            )

        for label in sorted(only_in_b):
            findings.append(
                ConsistencyFinding(
                    finding_id=_generate_finding_id(
                        "room_labels", f"missing_{label}", sheet_b.file_path,
                        sheet_a.file_path,
                    ),
                    category=ConsistencyCategory.ROOM_LABELS,
                    severity=ConsistencySeverity.WARNING,
                    title=f"Room label '{label}' missing from sheet",
                    description=(
                        f"Room '{label}' appears in '{sheet_b.file_path}' "
                        f"but not in '{sheet_a.file_path}'."
                    ),
                    sheet_a=sheet_b.file_path,
                    sheet_b=sheet_a.file_path,
                    details={"missing_label": label, "direction": "b_not_in_a"},
                )
            )

    return findings


def _check_layer_naming(
    contexts: list[DrawingContext],
) -> list[ConsistencyFinding]:
    """Check for layer naming inconsistencies across sheets."""
    findings: list[ConsistencyFinding] = []

    if len(contexts) < 2:
        return findings

    # Collect layer names per sheet
    layers_per_sheet: dict[str, set[str]] = {}
    all_layers: set[str] = set()
    for ctx in contexts:
        sheet_layers = {layer.name for layer in ctx.layers}
        layers_per_sheet[ctx.file_path] = sheet_layers
        all_layers.update(sheet_layers)

    # Check for case mismatches: same name different case across sheets
    layer_lower_map: dict[str, list[str]] = {}
    for layer in all_layers:
        lower = layer.lower()
        layer_lower_map.setdefault(lower, []).append(layer)

    for lower_name, variants in layer_lower_map.items():
        if len(set(variants)) > 1:
            findings.append(
                ConsistencyFinding(
                    finding_id=_generate_finding_id(
                        "layer_naming", f"case_{lower_name}",
                        contexts[0].file_path,
                    ),
                    category=ConsistencyCategory.LAYER_NAMING,
                    severity=ConsistencySeverity.WARNING,
                    title=f"Layer name case mismatch: {', '.join(sorted(set(variants)))}",
                    description=(
                        f"Layer '{lower_name}' appears with different cases "
                        f"across sheets: {sorted(set(variants))}. "
                        "Standardize to a single convention."
                    ),
                    sheet_a=contexts[0].file_path,
                    details={"variants": sorted(set(variants))},
                )
            )

    # Check for mixed delimiter convention (underscores, hyphens, spaces)
    non_default_all = all_layers - _DEFAULT_LAYERS
    has_underscore = any("_" in n for n in non_default_all)
    has_hyphen = any("-" in n for n in non_default_all)
    has_space = any(" " in n for n in non_default_all)
    delimiter_count = sum([has_underscore, has_hyphen, has_space])
    if delimiter_count > 1:
        used: list[str] = []
        if has_underscore:
            used.append("underscores")
        if has_hyphen:
            used.append("hyphens")
        if has_space:
            used.append("spaces")
        findings.append(
            ConsistencyFinding(
                finding_id=_generate_finding_id(
                    "layer_naming", "mixed_delimiters", contexts[0].file_path,
                ),
                category=ConsistencyCategory.LAYER_NAMING,
                severity=ConsistencySeverity.INFO,
                title="Mixed layer name delimiter convention",
                description=(
                    f"Layer names across the drawing set use mixed delimiters "
                    f"({', '.join(used)}). A single convention (e.g. hyphens for "
                    "AIA layer standards) improves readability and tooling compatibility."
                ),
                sheet_a=contexts[0].file_path,
                details={"delimiters_found": used},
            )
        )

    # Check for layers unique to a single sheet (excluding defaults)
    non_default_layers = all_layers - _DEFAULT_LAYERS
    for layer in sorted(non_default_layers):
        present_in = [
            fp for fp, layer_set in layers_per_sheet.items() if layer in layer_set
        ]
        if len(present_in) == 1 and len(contexts) > 1:
            findings.append(
                ConsistencyFinding(
                    finding_id=_generate_finding_id(
                        "layer_naming", f"unique_{layer}", present_in[0],
                    ),
                    category=ConsistencyCategory.LAYER_NAMING,
                    severity=ConsistencySeverity.INFO,
                    title=f"Layer '{layer}' only in one sheet",
                    description=(
                        f"Layer '{layer}' appears only in '{present_in[0]}' "
                        f"and not in the other {len(contexts) - 1} sheet(s)."
                    ),
                    sheet_a=present_in[0],
                )
            )

    return findings


def _check_block_consistency(
    sheets: list[SheetInfo],
) -> list[ConsistencyFinding]:
    """Check that shared block names appear consistently across sheets."""
    findings: list[ConsistencyFinding] = []

    if len(sheets) < 2:
        return findings

    # Count in how many sheets each block appears
    block_presence: Counter[str] = Counter()
    block_sheets: dict[str, list[str]] = {}
    for sheet in sheets:
        for block in sheet.block_names:
            block_presence[block] += 1
            block_sheets.setdefault(block, []).append(sheet.file_path)

    total = len(sheets)
    threshold = total / 2.0  # >50% of sheets

    for block, count in block_presence.items():
        if count > threshold and count < total:
            # Block is in majority but not all — flag missing sheets
            present_set = set(block_sheets[block])
            for sheet in sheets:
                if sheet.file_path not in present_set:
                    findings.append(
                        ConsistencyFinding(
                            finding_id=_generate_finding_id(
                                "block_consistency", f"missing_{block}",
                                sheet.file_path,
                            ),
                            category=ConsistencyCategory.BLOCK_CONSISTENCY,
                            severity=ConsistencySeverity.WARNING,
                            title=f"Block '{block}' missing from sheet",
                            description=(
                                f"Block '{block}' appears in {count}/{total} "
                                f"sheets but is missing from '{sheet.file_path}'."
                            ),
                            sheet_a=sheet.file_path,
                            details={
                                "block_name": block,
                                "present_in": sorted(present_set),
                            },
                        )
                    )

    return findings


def _check_entity_counts(
    sheets: list[SheetInfo],
) -> list[ConsistencyFinding]:
    """Flag sheets with anomalous entity counts."""
    findings: list[ConsistencyFinding] = []

    if not sheets:
        return findings

    # Check for empty sheets
    for sheet in sheets:
        if sheet.entity_count == 0:
            findings.append(
                ConsistencyFinding(
                    finding_id=_generate_finding_id(
                        "entity_counts", "empty", sheet.file_path,
                    ),
                    category=ConsistencyCategory.ENTITY_COUNTS,
                    severity=ConsistencySeverity.ERROR,
                    title="Empty sheet detected",
                    description=(
                        f"Sheet '{sheet.file_path}' contains no entities. "
                        "This may indicate a loading error or incorrect file."
                    ),
                    sheet_a=sheet.file_path,
                    details={"entity_count": 0},
                )
            )

    # Check for dramatic count differences (>5x median)
    counts = sorted(s.entity_count for s in sheets if s.entity_count > 0)
    if len(counts) >= 2:
        median = counts[len(counts) // 2]
        if median > 0:
            for sheet in sheets:
                if sheet.entity_count > 0 and sheet.entity_count > median * 5:
                    findings.append(
                        ConsistencyFinding(
                            finding_id=_generate_finding_id(
                                "entity_counts", "outlier", sheet.file_path,
                            ),
                            category=ConsistencyCategory.ENTITY_COUNTS,
                            severity=ConsistencySeverity.WARNING,
                            title="Unusually high entity count",
                            description=(
                                f"Sheet '{sheet.file_path}' has "
                                f"{sheet.entity_count} entities vs median "
                                f"{median}. This may indicate a different "
                                "drawing scale or scope."
                            ),
                            sheet_a=sheet.file_path,
                            details={
                                "entity_count": sheet.entity_count,
                                "median": median,
                            },
                        )
                    )

    return findings


def _check_coordinate_alignment(
    contexts: list[DrawingContext],
) -> list[ConsistencyFinding]:
    """Check that drawings share a compatible coordinate system."""
    findings: list[ConsistencyFinding] = []

    if len(contexts) < 2:
        return findings

    # Compute bounding box for each context
    bboxes: list[tuple[str, float, float, float, float]] = []
    for ctx in contexts:
        xs: list[float] = []
        ys: list[float] = []
        for entity in ctx.entities:
            if entity.insert_point:
                xs.append(entity.insert_point.x)
                ys.append(entity.insert_point.y)
        if xs and ys:
            bboxes.append((ctx.file_path, min(xs), min(ys), max(xs), max(ys)))

    # Pairwise overlap check
    for i, (path_a, ax1, ay1, ax2, ay2) in enumerate(bboxes):
        for path_b, bx1, by1, bx2, by2 in bboxes[i + 1 :]:
            # Check if bounding boxes overlap
            overlaps_x = ax1 <= bx2 and bx1 <= ax2
            overlaps_y = ay1 <= by2 and by1 <= ay2

            if not (overlaps_x and overlaps_y):
                findings.append(
                    ConsistencyFinding(
                        finding_id=_generate_finding_id(
                            "coordinate_alignment", "no_overlap", path_a, path_b,
                        ),
                        category=ConsistencyCategory.COORDINATE_ALIGNMENT,
                        severity=ConsistencySeverity.ERROR,
                        title="Drawings do not share coordinate space",
                        description=(
                            f"Bounding boxes of '{path_a}' and '{path_b}' "
                            "do not overlap. They may use different coordinate "
                            "systems or origins."
                        ),
                        sheet_a=path_a,
                        sheet_b=path_b,
                        details={
                            "bbox_a": [ax1, ay1, ax2, ay2],
                            "bbox_b": [bx1, by1, bx2, by2],
                        },
                    )
                )

            # Scale mismatch check runs independently of overlap
            size_a = max(ax2 - ax1, ay2 - ay1, 1.0)
            size_b = max(bx2 - bx1, by2 - by1, 1.0)
            ratio = max(size_a, size_b) / min(size_a, size_b)
            if ratio > 10.0:
                findings.append(
                    ConsistencyFinding(
                        finding_id=_generate_finding_id(
                            "coordinate_alignment", "scale_mismatch",
                            path_a, path_b,
                        ),
                        category=ConsistencyCategory.COORDINATE_ALIGNMENT,
                        severity=ConsistencySeverity.WARNING,
                        title="Possible scale mismatch between sheets",
                        description=(
                            f"Drawing '{path_a}' and '{path_b}' differ in "
                            f"extent by {ratio:.1f}x. They may use "
                            "different drawing scales."
                        ),
                        sheet_a=path_a,
                        sheet_b=path_b,
                        details={"scale_ratio": round(ratio, 1)},
                    )
                )

    return findings
