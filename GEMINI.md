# Code Review Style Guide — cad-dxf-agent

## Project Context
Local-first DXF layout editor evolving into a Drawing Intelligence Platform.
LLM returns structured JSON operations (never raw DXF). Original files never modified.

## Review Priorities
1. **Safety**: Protected layers (TITLE, TITLEBLOCK, SEAL, REVISION) must never be editable
2. **LLM boundary**: LLM must never produce raw DXF — only structured EditOperation objects
3. **Determinism**: Revision notes, file IDs, and apply logic must be deterministic
4. **Schema contracts**: Pydantic models are the source of truth for data shapes
5. **Test coverage**: New code needs tests; coverage threshold is 65%

## Patterns to Enforce
- Provider ABC pattern for LLM backends (never call Gemini/OpenAI directly)
- Save-as workflow (original file untouched)
- V1 entity types only in edit operations (LINE, LWPOLYLINE, TEXT, MTEXT, INSERT)
- All settings via CAD_* environment variables
- Conventional commits with Epic/Bead trailers

## Anti-patterns to Flag
- Hardcoded API keys or secrets
- Direct DXF manipulation outside edit_engine.py
- Skipping validation before apply
- Mutable global state in session handling
- Tests that depend on network calls without mocking
