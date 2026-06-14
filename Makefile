.PHONY: install lint format typecheck test test-unit test-integration test-web test-e2e test-cov smoke check run clean build build-clean scorecard audit-harness

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

test-web:
	pytest tests/web/ -v -m web

test-e2e:
	pytest tests/e2e/ -v -m e2e

test-cov:
	pytest --cov=cad_dxf_agent --cov-report=term-missing -v

smoke:
	python scripts/smoke_test.py

scorecard:
	pytest tests/eval/ -v --tb=short

security:
	bandit -r src/ -ll
	pip-audit --local

# Vendored audit-harness gates. `verify` is blocking (hash-pin tamper check);
# escape-scan/bias/arch are advisory locally (leading `-` ignores their exit).
audit-harness:
	bash scripts/audit-harness verify
	-bash scripts/audit-harness escape-scan --staged
	-bash scripts/audit-harness bias
	-bash scripts/audit-harness arch

check: lint format typecheck test smoke
	@echo "All checks passed."

run:
	python -m cad_dxf_agent.app

build:
	python scripts/build.py

build-clean:
	python scripts/build.py --clean

clean:
	rm -rf dist/ build/ *.egg-info .coverage htmlcov/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
