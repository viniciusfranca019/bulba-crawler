.PHONY: help install-all test lint format crawl dump


help: ## Mostrar esta mensagem de ajuda
	@echo "Comandos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install-all: ## Install all dependency groups (production + dev)
	@echo "📦 Installing all dependencies (production + dev)..."
	uv sync --all-groups
	@echo "✅ All dependencies installed successfully!"

crawl: ## Crawl Bulbapedia Pokémon pages and store results in SQLite
	uv run python main.py crawl

dump: ## Export crawled Pokémon data to pokemon.json
	uv run python main.py export --output pokemon.json

lint: ## Lint code
	uv run ruff check . --fix

format: ## Format code
	uv run ruff format .