# Dev-Flow canonical commands.
# These are the discoverable entry points for humans, CI, and AI workers.
# `make verify` is the canonical gate CI runs (./scripts/release-check.sh).
#
# Speed tiers:
#   make lint      ~2s    static checks (ruff) - fast inner loop
#   make test-fast ~15s   fast tests only (no slow/ui_browser markers) - inner loop
#   make test      ~60s   full pytest suite (parallel) - fast inner loop
#   make verify    ~1-2m  release-check.sh      - pre-push / promotion gate

PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
RUFF   ?= .venv/bin/ruff
# Needed for subprocess CLI tests (`python -m devflow.cli`) that do not read pytest's pythonpath config.
export PYTHONPATH := src:.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install the package in editable mode with dev tools (ruff, pytest).
	$(PYTHON) -m pip install -e ".[dev]"


.PHONY: lint
lint: ## Static checks (ruff). Catches unused imports, dead vars, repeated dict keys.
	$(RUFF) check .

.PHONY: lint-fix
lint-fix: ## Auto-fix the safe lint violations (review the diff before committing).
	$(RUFF) check . --fix

.PHONY: compile
compile: ## Byte-compile all sources (fast syntax/build check).
	$(PYTHON) -m compileall src

.PHONY: test
test: ## Run the standard pytest suite in parallel (skips optional browser tests).
	$(PYTEST) -n auto --timeout=60 -m "not ui_browser and not ui_browser_live" -q

.PHONY: test-fast
test-fast: ## Run fast tests only (skips slow and ui_browser markers).
	$(PYTEST) -n auto --timeout=60 -m "not slow and not ui_browser and not ui_browser_live" -q

.PHONY: test-slow
test-slow: ## Run only slow-marked non-browser tests.
	$(PYTEST) -n auto --timeout=120 -m "slow and not ui_browser and not ui_browser_live" -q

.PHONY: test-ui
test-ui: ## Run optional Playwright browser UI tests.
	$(PYTEST) -n auto --timeout=120 -m "ui_browser or ui_browser_live" -q

.PHONY: verify
verify: ## Canonical gate: the full release-readiness check CI runs.
	./scripts/release-check.sh

.PHONY: serve
serve: ## Start the V2 brainstorm and pipeline-status surface on port 8770.
	$(PYTHON) -m devflow.cli status serve

.PHONY: health
health: ## Probe the V2 status board health endpoint.
	$(PYTHON) -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8770/healthz', timeout=5).read().decode())"
