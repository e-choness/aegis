COMPOSE = docker compose

.PHONY: build test up down logs shell

build:
	$(COMPOSE) build

test: build
	$(COMPOSE) --profile test run --rm test

up: build
	$(COMPOSE) up gateway timescaledb prometheus grafana

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f gateway

shell:
	$(COMPOSE) run --rm --entrypoint bash gateway