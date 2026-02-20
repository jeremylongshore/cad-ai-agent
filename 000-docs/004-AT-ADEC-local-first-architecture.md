# ADR 0001: Local-First Architecture

## Status
Accepted

## Context
DXF files are used in engineering and construction workflows where:
- Files may contain proprietary designs
- Internet connectivity is not always available on job sites
- File sizes can be large (10MB+)
- Users need fast, predictable response times

## Decision
The application runs entirely on the user's local machine. No cloud hosting is required for core functionality. The LLM API is an optional, pluggable component used only for planning — never for direct DXF editing.

A mock planner mode allows the full pipeline to work without any network access or API key.

## Consequences
- **Positive**: No data leaves the machine unless the user opts into LLM planning. Latency is predictable. Works offline.
- **Positive**: Users in restricted environments (government, defense, construction sites) can use the tool.
- **Negative**: LLM-powered planning quality is limited by API availability and cost.
- **Negative**: Updates require local installation (no auto-update from cloud).

## Notes
An optional local HTTP API layer is scaffolded for headless/scripting use cases but is not required for the desktop workflow.
