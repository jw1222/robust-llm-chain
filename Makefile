.PHONY: setup lint format type test cov check clean

setup:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

type:
	uv run mypy --strict src/robust_llm_chain

test:
	uv run pytest tests/ -m "not integration and not e2e"

cov:
	uv run pytest tests/ -m "not integration and not e2e" \
		--cov=src/robust_llm_chain --cov-report=term-missing

check: lint type test

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
