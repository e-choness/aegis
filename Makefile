COMPOSE = docker compose

.PHONY: build test test-py test-sdk-py test-ts up down logs shell

build:
	$(COMPOSE) build

test: test-py test-sdk-py test-ts

test-py: build
	$(COMPOSE) --profile test run --rm test

test-sdk-py:
	$(COMPOSE) --profile test run --rm sdk-py-test

test-ts:
	$(COMPOSE) --profile test run --rm sdk-ts-test

up: build
	$(COMPOSE) up gateway ollama timescaledb vectordb prometheus grafana

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f gateway

shell:
	$(COMPOSE) run --rm --entrypoint bash gateway
