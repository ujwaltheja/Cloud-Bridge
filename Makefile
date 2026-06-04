# Cloud Bridge - Makefile
# Works on Windows (PowerShell + make or Git Bash) and Linux/macOS

.PHONY: help up down build logs test lint migrate shell-backend shell-worker clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# Core Docker Commands
# =============================================================================

up: ## Start all services in detached mode
	docker compose up -d --build

down: ## Stop and remove all containers
	docker compose down

build: ## Build all images without starting
	docker compose build

logs: ## Tail logs from all services
	docker compose logs -f

logs-backend: ## Tail backend logs
	docker compose logs -f backend

logs-worker: ## Tail Celery worker logs (very useful)
	docker compose logs -f worker

# =============================================================================
# Development Helpers
# =============================================================================

shell-backend: ## Open a shell inside the backend container
	docker compose exec backend bash

shell-worker: ## Open a shell inside the worker container
	docker compose exec worker bash

shell-db: ## Open psql inside the database
	docker compose exec postgres psql -U cloudbridge -d cloudbridge

# =============================================================================
# Database & Migrations
# =============================================================================

migrate: ## Apply all pending Alembic migrations
	docker compose exec backend alembic upgrade head

migrate-down: ## Downgrade one revision (use with caution)
	docker compose exec backend alembic downgrade -1

migration: ## Create a new migration (usage: make migration msg="your message")
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

# =============================================================================
# Quality & Testing
# =============================================================================

test: ## Run backend tests
	docker compose exec backend pytest -q

test-cov: ## Run backend tests with coverage report
	docker compose exec backend pytest --cov=app --cov-report=term-missing

lint: ## Run all linters and formatters (backend + frontend)
	docker compose exec backend ruff check .
	docker compose exec backend ruff format --check .
	docker compose exec backend mypy app || true
	cd frontend && npm run lint

format: ## Auto-format code (backend + frontend)
	docker compose exec backend ruff format .
	docker compose exec backend ruff check --fix .
	cd frontend && npm run format

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Remove generated files, caches, and local data volumes (destructive)
	docker compose down -v
	rm -rf backend/__pycache__ backend/.pytest_cache backend/.coverage
	rm -rf frontend/node_modules frontend/dist
	rm -rf minio_data postgres_data redis_data
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
