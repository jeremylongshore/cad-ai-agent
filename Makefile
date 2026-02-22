.PHONY: install lint format typecheck test test-unit test-integration test-cov smoke check run clean

install:
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

test:
	pytest -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m integration

test-cov:
	pytest --cov=cad_dxf_agent --cov-report=term-missing -v

smoke:
	python scripts/smoke_test.py

security:
	bandit -r src/ -ll
	pip-audit

check: lint format typecheck test smoke
	@echo "All checks passed."

run:
	python -m cad_dxf_agent.app

clean:
	rm -rf dist/ build/ *.egg-info .coverage htmlcov/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
