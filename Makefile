.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := cd backend &&

.PHONY: help up down logs ps migrate seed job test test-unit test-front lint lint-front fmt api-tipos

help: ## Lista los comandos
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-10s %s\n", $$1, $$2}'

up: ## Levanta postgres, minio, mailpit, la API y el front (http://localhost:5173)
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

job: ## Corre una tarea programada a mano: make job TAREA=orden_del_dia|cierre_de_jornada|recordatorios|mails|fedex
	$(COMPOSE) exec api python -m app.jobs $(TAREA)

test: ## Tests del backend contra el Postgres de compose (crea y borra bases *_test_*)
	$(BACKEND) uv run pytest

test-unit: ## Sólo tests unitarios (sin base)
	$(BACKEND) uv run pytest tests/unit

lint: ## ruff + mypy
	$(BACKEND) uv run ruff check . && uv run mypy app

test-front: ## Tests del front (Vitest)
	cd frontend && npm run test

lint-front: ## eslint + vue-tsc
	cd frontend && npm run lint && npm run typecheck

api-tipos: ## Regenera el cliente tipado del front desde el OpenAPI del backend
	$(BACKEND) uv run python -m app.openapi > openapi.json
	cd frontend && npm run api:tipos

fmt: ## Formatea y ordena imports
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .
