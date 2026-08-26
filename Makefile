SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Workspace packages live outside site-packages during development, so tooling
# needs them on the path explicitly.
DOMAIN_PATH := python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence
export SMARTMATCH_DATABASE_URL ?= postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

.PHONY: setup
setup: ## Create the virtualenv and install pinned dev dependencies
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	# Hash-verified, so a compromised or newly-broken upstream release cannot be
	# picked up silently. Resolves security finding S-003.
	$(PIP) install -q --require-hashes -r requirements/dev.txt
	# Workspace packages, installed editable so local edits take effect.
	$(PIP) install -q --no-deps -e python/smartmatch_domain -e python/smartmatch_authz \
		-e python/smartmatch_providers -e python/smartmatch_persistence
	@echo "Setup complete. Run 'make check' to verify."

.PHONY: lock
lock: ## Recompile the dependency locks from requirements/*.in
	$(PIP) install -q pip-tools
	$(VENV)/bin/pip-compile --generate-hashes --strip-extras --quiet \
		--output-file=requirements/runtime.txt requirements/runtime.in
	$(VENV)/bin/pip-compile --generate-hashes --strip-extras --quiet \
		--output-file=requirements/dev.txt requirements/dev.in
	@echo "Locks regenerated. Review the diff before committing."

# ---------------------------------------------------------------------------
# Verification gates — these mirror CI exactly
# ---------------------------------------------------------------------------

.PHONY: check
check: format-check lint typecheck imports test scan memory licenses infra-check ## Run every gate CI runs

.PHONY: format-check
format-check: ## Verify formatting
	$(VENV)/bin/ruff format --check .

.PHONY: format
format: ## Apply formatting
	$(VENV)/bin/ruff format .

.PHONY: lint
lint: ## Lint
	$(VENV)/bin/ruff check .

.PHONY: typecheck
typecheck: ## Static typing (strict)
	$(VENV)/bin/mypy python/ services/

.PHONY: imports
imports: ## Enforce architectural import boundaries
	PYTHONPATH="$(DOMAIN_PATH)" $(VENV)/bin/lint-imports --config pyproject.toml

.PHONY: test
test: ## Run unit, golden, authz, and contract tests (no database needed)
	$(VENV)/bin/pytest tests/ -m "not integration"

.PHONY: test-integration
test-integration: ## Run integration tests (requires PostgreSQL)
	$(VENV)/bin/pytest tests/ -m integration

.PHONY: test-all
test-all: ## Run every test
	$(VENV)/bin/pytest tests/

.PHONY: scan
scan: ## Scan for forbidden legacy behavior
	$(PY) tools/scan_forbidden.py

.PHONY: memory
memory: ## Validate the approved agent-memory ledger
	$(PY) tools/agent_memory_check.py

.PHONY: licenses
licenses: ## Fail on a dependency license outside the policy
	$(PY) tools/supply_chain.py licenses

.PHONY: sbom
sbom: ## Generate the CycloneDX 1.5 SBOM for the runtime lock (dist/ is gitignored)
	$(PY) tools/supply_chain.py sbom --output dist/sbom.cyclonedx.json

.PHONY: infra-check
infra-check: ## Assert Terraform environments share no identifiers and apply nothing
	$(PY) tools/env_isolation_check.py

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

.PHONY: db-up
db-up: ## Start local PostgreSQL and create the dev database
	@service postgresql start >/dev/null 2>&1 || true
	@su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='smartmatch'\"" \
		| grep -q 1 || \
		su postgres -c "psql -c \"CREATE USER smartmatch WITH PASSWORD 'smartmatch' SUPERUSER;\""
	@su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='smartmatch'\"" \
		| grep -q 1 || su postgres -c "createdb -O smartmatch smartmatch"
	@echo "PostgreSQL ready at $(SMARTMATCH_DATABASE_URL)"

.PHONY: migrate
migrate: ## Apply migrations to head
	cd db && ../$(VENV)/bin/alembic upgrade head

.PHONY: migrate-check
migrate-check: ## Verify migrations apply cleanly from an empty database
	@su postgres -c "dropdb --if-exists smartmatch_migcheck"
	@su postgres -c "createdb -O smartmatch smartmatch_migcheck"
	cd db && SMARTMATCH_DATABASE_URL="postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch_migcheck" \
		../$(VENV)/bin/alembic upgrade head
	@su postgres -c "dropdb smartmatch_migcheck"
	@echo "Migrations apply cleanly from empty."

# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

.PHONY: openapi
openapi: ## Regenerate the OpenAPI document from the API application
	PYTHONPATH="$(DOMAIN_PATH):services/api" $(PY) tools/export_openapi.py \
		contracts/openapi/smartmatch.json

.PHONY: openapi-check
openapi-check: ## Fail if the committed OpenAPI document is stale
	PYTHONPATH="$(DOMAIN_PATH):services/api" $(PY) tools/export_openapi.py \
		contracts/openapi/smartmatch.json --check

# ---------------------------------------------------------------------------
# Local run — fixtures only, never a live provider
# ---------------------------------------------------------------------------

.PHONY: run-api
run-api: ## Run the API locally against fixtures
	PYTHONPATH="$(DOMAIN_PATH):services/api" \
		$(VENV)/bin/uvicorn smartmatch_api.main:app --reload --port 8000

.PHONY: run-worker
run-worker: ## Run the worker locally
	PYTHONPATH="$(DOMAIN_PATH):services/worker" \
		$(VENV)/bin/uvicorn smartmatch_worker.main:app --reload --port 8001
