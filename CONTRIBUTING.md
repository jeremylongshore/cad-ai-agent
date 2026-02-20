# Contributing to cad-dxf-agent

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
4. Install in development mode: `pip install -e ".[dev]"`
5. Install pre-commit hooks: `pre-commit install`

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Run linting: `ruff check src/ tests/`
4. Run type checks: `mypy src/`
5. Run tests: `pytest`
6. Commit with clear messages (see commit conventions below)
7. Open a PR against `main`

## Commit Message Convention

Use conventional commits:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — adding/updating tests
- `ci:` — CI/CD changes
- `chore:` — tooling, dependencies, scaffolding
- `refactor:` — code restructure without behavior change

Scope is optional but encouraged: `feat(core):`, `fix(llm):`, `test(validator):`

## Architecture Rules

- **LLM must never directly edit DXF text.** Planner returns structured ops only.
- **Protected layers are sacred.** Never bypass the validator for protected layers.
- **Save-as only.** Never overwrite original DXF files.
- **Local-first.** No cloud dependencies for core functionality.

## Testing

- Unit tests go in `tests/unit/`
- Fixtures go in `tests/fixtures/`
- Smoke tests go in `tests/smoke/`
- All mock planner tests must work without an API key

## Code Style

- Python 3.11+
- Formatting/linting: `ruff`
- Type hints: use them, checked by `mypy`
- Pydantic v2 for all schemas
