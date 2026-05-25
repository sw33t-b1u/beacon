.PHONY: check vet lint format test audit generate validate setup \
        check-pir-schema-drift

# Full quality gate: vet → lint → test → drift
check: vet lint test audit check-pir-schema-drift

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
	PIPAPI_PYTHON_LOCATION=.venv/bin/python3 uv run pip-audit

generate:
	uv run python cmd/generate_pir.py $(ARGS)

validate:
	uv run python cmd/validate_pir.py $(ARGS)

check-pir-schema-drift:
	@if [ ! -d "../TRACE" ]; then \
		echo "WARNING: ../TRACE not present — skipping check-pir-schema-drift"; \
		exit 0; \
	fi
	uv run python ../TRACE/scripts/check_pir_schema_drift.py \
		schema/pir_output.schema.json \
		../TRACE/schema/pir.schema.json

setup:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit .githooks/pre-push
	@echo "Git hooks installed (pre-commit: vet+lint, pre-push: full check)."
