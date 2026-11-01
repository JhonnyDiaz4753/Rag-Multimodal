.PHONY: init up up-full up-ai down logs ps install test lint fmt

init:
	@python -c "import pathlib, shutil; dst = pathlib.Path('.env'); dst.exists() or shutil.copyfile('.env.example', dst)"

up: init
	docker compose up --build

up-full: init
	docker compose --profile ollama up --build

up-ai: up-full

down:
	docker compose --profile ollama down

logs:
	docker compose logs -f

ps:
	docker compose ps

install:
	cd backend && python -m pip install -r requirements-dev.txt

test:
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check src tests && ruff format --check src tests

fmt:
	cd backend && ruff check --fix src tests && ruff format src tests
