COMPOSE ?= docker compose

.PHONY: up down health

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

health:
	$(COMPOSE) exec -T postgres pg_isready -U familyos -d familyos
	$(COMPOSE) exec -T redis redis-cli ping
	$(COMPOSE) exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5)"
	@echo "OK: postgres, redis, S3 storage, backend"
