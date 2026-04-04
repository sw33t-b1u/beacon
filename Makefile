.PHONY: check vet lint format test audit generate validate

# Full quality gate: vet → lint → test
check: vet lint test audit

vet:
	uv run ruff check src/ cmd/ tests/

lint:
	uv run ruff format --check src/ cmd/ tests/

format:
	uv run ruff format src/ cmd/ tests/
	uv run ruff check --fix src/ cmd/ tests/

test:
	uv run python -m pytest tests/ -v -m "not integration"

test-integration:
	uv run python -m pytest tests/ -v -m integration

audit:
	uv run pip-audit

generate:
	uv run python cmd/generate_pir.py $(ARGS)

validate:
	uv run python cmd/validate_pir.py $(ARGS)
