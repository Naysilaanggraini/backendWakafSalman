COMPOSE = docker compose --env-file .env
PYTHON ?= python3

.PHONY: help build migrate migration-status deploy up down logs test backup
help:
	@echo 'build migrate migration-status deploy up down logs test backup'
	@echo 'First setup: read docs/PRODUCTION.md; configure .env.'
build:
	$(COMPOSE) build --pull api
migrate:
	$(COMPOSE) run --rm --no-deps api flask --app app db upgrade
migration-status:
	$(COMPOSE) run --rm --no-deps api flask --app app db current
deploy: build
	$(COMPOSE) stop api
	$(COMPOSE) run --rm --no-deps api flask --app app db upgrade
	$(COMPOSE) up -d --wait api
up:
	$(COMPOSE) up -d --wait api
down:
	$(COMPOSE) down
logs:
	$(COMPOSE) logs -f --tail=100 api
test:
	$(PYTHON) -m unittest discover -s tests -v
backup:
	./deploy/backup.sh
