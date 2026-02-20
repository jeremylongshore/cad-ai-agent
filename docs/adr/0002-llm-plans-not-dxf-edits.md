# ADR 0002: LLM Plans Structured Operations, Never Edits DXF Directly

## Status
Accepted

## Context
LLMs can hallucinate, produce inconsistent output, and cannot reliably manipulate binary or structured text formats like DXF. Allowing an LLM to directly modify DXF content would introduce unpredictable corruption risks.

## Decision
The LLM planner is restricted to returning structured JSON operation objects. The only allowed operations in V1 are:
- `move_entity`
- `edit_text`
- `delete_entity`
- `add_block`

All planner output is validated against Pydantic schemas before any edit is applied. The LLM never sees or produces raw DXF text.

## Consequences
- **Positive**: All edits are deterministic and auditable.
- **Positive**: Validation catches invalid or dangerous operations before they touch the drawing.
- **Positive**: The same operation schema works with any planner backend (OpenAI, Anthropic, mock).
- **Negative**: The LLM cannot express operations outside the defined schema (limits flexibility).
- **Negative**: Complex multi-step operations may require schema extensions in future phases.

## Notes
If the planner returns invalid JSON or unsupported operation types, the entire changeset is rejected. Partial application is not allowed in V1.
