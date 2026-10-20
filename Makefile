.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := cd backend &&

.PHONY: help up down logs ps migrate seed test test-unit lint fmt

help: ## Lista los comandos
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-10s %s\n", $$1, $$2}'

up: ## Levanta postgres, minio, mailpit y la API (aplica migraciones al iniciar)
	$(COMPOSE) up -d --build

down: ## Baja los servicios (los volúmenes quedan)
	$(COMPOSE) down

logs: ## Sigue los logs de la API
	$(COMPOSE) logs -f api

ps: ## Estado de los servicios
	$(COMPOSE) ps

migrate: ## alembic upgrade head dentro del contenedor de la API
	$(COMPOSE) exec api alembic upgrade head

seed: ## Vacía la base y recarga los datos de ejemplo
	$(COMPOSE) exec api python -m app.seed

test: ## Tests del backend contra el Postgres de compose (crea y borra bases *_test_*)
	$(BACKEND) uv run pytest

test-unit: ## Sólo tests unitarios (sin base)
	$(BACKEND) uv run pytest tests/unit

lint: ## ruff + mypy
	$(BACKEND) uv run ruff check . && uv run mypy app

fmt: ## Formatea y ordena imports
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .
