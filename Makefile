.PHONY: install lint test test-cov format check clean demo demo-check demo-diff

install: 
	uv sync

lint:
	uv run ruff format
	uv run ruff check --fix --unsafe-fixes --exit-zero

format:
	uv run ruff format

check: 
	uv run ruff check

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=undersort --cov-report=term-missing --cov-report=html

clean:
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

update:
	uv lock --upgrade
	uv sync
