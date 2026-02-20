# ADR 0003: AI Revision Notes on Dedicated Safe Layer

## Status
Accepted

## Context
The client wants revision-style notes (e.g., "REV 8 - Column shift") to appear on edited drawings. However, title block revision tables are highly structured, vendor-specific, and vary across firms. Writing into them risks corruption or inconsistency.

## Decision
V1 inserts AI-generated revision notes on a dedicated layer (`AI_REV_NOTES`) rather than modifying the title block revision table.

Key design rules:
- Note text is generated **deterministically** from applied operations, not from LLM prose.
- The `AI_REV_NOTES` layer is created automatically if it does not exist.
- Protected layers (`TITLE`, `TITLEBLOCK`, `SEAL`, `REVISION`) are never modified.
- The note anchor point and text height are configurable.
- The feature can be toggled on/off via config.

Example notes:
- `REV 8 - Column shift`
- `REV 8 - Moved entity east 2'-0"`
- `REV 5 - Moved entity east 2'-0"; Deleted entity`

## Consequences
- **Positive**: No risk of corrupting existing title block or revision tables.
- **Positive**: Notes are predictable and reproducible (no LLM hallucination in note text).
- **Positive**: Easy for downstream users to filter or remove the `AI_REV_NOTES` layer.
- **Negative**: Notes are not in the "official" revision table — users must manually transfer if needed.

## Future
Revision table integration (writing structured attributes into a known revision block) is planned for a future phase once block attribute mapping standards are established.
