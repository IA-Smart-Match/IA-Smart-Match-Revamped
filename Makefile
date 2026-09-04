SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
# Overridable so `make e2e` can run on a CI runner that installed the pinned
# requirements into its own interpreter instead of into ./.venv.
PYTEST ?= $(VENV)/bin/pytest

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
	$(PIP) install -q 'pip-tools==7.6.1'  # must match .github/workflows/verify.yml
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
	$(VENV)/bin/pytest tests/ -m "not integration and not e2e"

.PHONY: test-integration
test-integration: ## Run integration tests (requires PostgreSQL)
	$(VENV)/bin/pytest tests/ -m integration

.PHONY: test-all
test-all: ## Run every test that does not need a running appliance
	# `not e2e` for the same reason `test` excludes it: tests/e2e talks HTTP to
	# a stack `docker compose up` has to have started, which no gate in `check`
	# brings up. It is not dropped silently — `make e2e` is the target that
	# runs it, and the pilot-e2e CI job is what runs that.
	$(VENV)/bin/pytest tests/ -m "not e2e"

.PHONY: e2e
e2e: ## Click through the synthetic pilot against a RUNNING compose appliance
	# Requires `docker compose up --build -d` first. This target deliberately
	# does not bring the stack up or tear it down: CI owns `up` and an
	# always-run `down -v` so logs survive a failure, and a developer running
	# it by hand wants the stack still standing afterwards to look at.
	#
	# `-ra` is not decoration. Several steps in this suite cannot run on this
	# appliance at all — rewards is gated on the `student` role pending the D6
	# decision, and the portal pages have no backend in this repository — and
	# each one calls pytest.skip naming its reason. `-ra` prints every one of
	# them in the summary, so a skipped step can never be read as a passed one.
	#
	# $(PYTEST) rather than $(VENV)/bin/pytest directly: the CI job for this
	# target installs the same pinned requirements into the runner's own
	# interpreter rather than into ./.venv, and overrides PYTEST accordingly.
	# Every other target keeps the literal venv path it already had.
	$(PYTEST) tests/e2e -m e2e -ra

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

.PHONY: seed-pilot
seed-pilot: ## Seed one synthetic local-pilot principal; set SEED_PILOT_ARGS="--subject ... --email ... --role ..."
	PYTHONPATH="$(DOMAIN_PATH):services/api" $(PY) tools/seed_pilot.py $(SEED_PILOT_ARGS)

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
