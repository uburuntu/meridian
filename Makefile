.PHONY: help install sync test lint format check typecheck ci e2e \
       templates ai-docs build publish clean hooks

## —— Setup ——————————————————————————————————————————————

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ai-docs ## Install package in dev mode with all dependencies
	uv sync --extra dev --reinstall-package meridian-vpn

sync: install ## Alias for install

hooks: ## Install git pre-push hook
	git config core.hooksPath .githooks
	@echo "  ✓ Git hooks installed (.githooks/pre-push)"

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
	uv run mypy src/meridian/

check: lint format-check test ## Run all Python checks (lint + format + test)

templates: ## Validate Jinja2 template rendering
	uv run python tests/render_templates.py

## —— CI (runs everything) ———————————————————————————————

ci: check templates ## Run full CI locally

e2e: ## Run E2E provisioner tests in Docker (Linux only, needs docker socket)
	docker compose -f tests/e2e/docker-compose.e2e.yml up --build --abort-on-container-exit --exit-code-from e2e
	docker compose -f tests/e2e/docker-compose.e2e.yml down -v

## —— Build & Publish ————————————————————————————————————

ai-docs: ## Generate AI reference from human docs (strip frontmatter)
	@mkdir -p src/meridian/data
	@for f in website/src/content/docs/en/cli-reference.md \
	          website/src/content/docs/en/architecture.md \
	          website/src/content/docs/en/troubleshooting.md \
	          website/src/content/docs/en/deploy.md \
	          website/src/content/docs/en/relay.md \
	          website/src/content/docs/en/recovery.md; do \
		awk 'BEGIN{skip=0} /^---$$/{skip++;next} skip<2{next} {print}' "$$f"; \
		echo ""; \
	done > src/meridian/data/ai-reference.md

build: ai-docs ## Build wheel and sdist
	uv build

publish: build ## Publish to PyPI (requires trusted publisher or token)
	uv publish

clean: ## Remove build artifacts
	rm -rf dist/ build/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
