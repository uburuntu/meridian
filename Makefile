.PHONY: help install sync test lint format check typecheck ci \
       ansible-lint ansible-check templates \
       build publish clean \
       server-test

PLAYBOOKS := src/meridian/playbooks

## —— Setup ——————————————————————————————————————————————

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install package in dev mode with all dependencies
	uv sync --extra dev

sync: install ## Alias for install

## —— Quality ————————————————————————————————————————————

test: ## Run Python tests
	uv run pytest tests/ -v --tb=short

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Auto-format code
	uv run ruff format src/ tests/

format-check: ## Check formatting without changes
	uv run ruff format --check src/ tests/

typecheck: ## Run mypy type checker
	uv run mypy src/meridian/ --ignore-missing-imports

check: lint format-check test ## Run all Python checks (lint + format + test)

## —— Ansible ————————————————————————————————————————————

ansible-lint: ## Run ansible-lint on playbooks
	cd $(PLAYBOOKS) && uv run ansible-lint

ansible-check: ## Syntax check all playbooks
	cd $(PLAYBOOKS) && uv run ansible-playbook playbook.yml --syntax-check
	cd $(PLAYBOOKS) && uv run ansible-playbook playbook-client.yml --syntax-check
	cd $(PLAYBOOKS) && uv run ansible-playbook -i inventory-chain.yml.example playbook-chain.yml --syntax-check
	cd $(PLAYBOOKS) && uv run ansible-playbook playbook-uninstall.yml --syntax-check

templates: ## Validate Jinja2 template rendering
	uv run python tests/render_templates.py

## —— CI (runs everything) ———————————————————————————————

ci: check ansible-lint ansible-check templates ## Run full CI locally

## —— Build & Publish ————————————————————————————————————

build: ## Build wheel and sdist
	uv build

publish: build ## Publish to PyPI (requires trusted publisher or token)
	uv publish

clean: ## Remove build artifacts
	rm -rf dist/ build/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
