.PHONY: up down logs install test lint fmt

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

install:
	cd backend && python -m pip install -r requirements-dev.txt

test:
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check src tests && ruff format --check src tests

fmt:
	cd backend && ruff check --fix src tests && ruff format src tests
