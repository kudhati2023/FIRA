.PHONY: dev test lint format migrate seed down shell

dev:
	docker compose up --build

down:
	docker compose down -v

test:
	docker compose run --rm api pytest --cov=fira tests/

lint:
	docker compose run --rm api black --check src/ tests/
	docker compose run --rm api ruff check src/ tests/
	docker compose run --rm api mypy src/

format:
	docker compose run --rm api black src/ tests/
	docker compose run --rm api ruff check --fix src/ tests/

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m fira.db.seed
