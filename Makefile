.PHONY: help install dev lint format typecheck test cov doctor sync dry-run clean

PYTHON ?= python3

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	$(PYTHON) -m pip install .

dev: ## Install with dev dependencies (editable)
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Run ruff lint checks
	ruff check src tests

format: ## Auto-format with ruff
	ruff format src tests
	ruff check --fix src tests

typecheck: ## Run mypy
	mypy

test: ## Run the test suite
	pytest

cov: ## Run tests with coverage report
	pytest --cov=githublab_sync --cov-report=term-missing

doctor: ## Verify config, tokens and connectivity
	githublab-sync doctor

dry-run: ## Preview a sync without making changes
	githublab-sync sync --dry-run

sync: ## Run a full sync
	githublab-sync sync

clean: ## Remove build/test artefacts
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache .mypy_cache \
		.coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
