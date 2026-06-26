# Dev-Flow canonical commands.
# These are the discoverable entry points for humans, CI, and AI workers.
# `make verify` is the canonical gate CI runs (./scripts/release-check.sh).
#
# Speed tiers:
#   make lint    ~2s    static checks (ruff) - fast inner loop
#   make test    ~30s   full pytest suite    - fast inner loop
#   make verify  ~1-2m  release-check.sh      - pre-push / promotion gate

PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
RUFF   ?= .venv/bin/ruff
export PYTHONPATH := src:.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install the package in editable mode with dev tools (ruff, pytest).
	$(PYTHON) -m pip install -e ".[dev]"

.PHONY: repair
repair: ## Clear the macOS hidden flag that breaks `import devflow` (recurs on Desktop).
	$(PYTHON) -m devflow.cli doctor --repair

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
test: ## Run the full pytest suite (the same one release-check.sh runs).
	$(PYTEST) --ignore=scratch -q

.PHONY: verify
verify: ## Canonical gate: the full release-readiness check CI runs.
	./scripts/release-check.sh

.PHONY: serve
serve: ## Restart the operating-layer UI cleanly (kills any stale server on the port).
	$(PYTHON) -m devflow.cli operating-layer restart

.PHONY: health
health: ## Probe the running operating-layer server's real data path (/api/snapshot).
	$(PYTHON) -m devflow.cli operating-layer health
