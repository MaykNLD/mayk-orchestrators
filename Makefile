# ─────────────────────────────────────────────────────────────────────────────
# Makefile — mayk.dev Ecosystem
# Comandos rápidos para gestionar el stack Docker localmente
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: up down logs restart build ps health clean

## Levantar todo el stack (en segundo plano)
up:
	docker compose up -d

## Parar todos los servicios
down:
	docker compose down

## Ver logs en tiempo real de todos los servicios
logs:
	docker compose logs -f

## Ver logs de un agente específico: make logs-agente a=agente-dev
logs-agente:
	docker compose logs -f $(a)

## Reconstruir imágenes y levantar (usar tras cambios de código)
build:
	docker compose up -d --build

## Reconstruir un solo agente: make rebuild a=agente-dev
rebuild:
	docker compose up -d --build $(a)

## Estado de los contenedores
ps:
	docker compose ps

## Comprobar salud de todos los agentes vía orquestador
health:
	curl -s http://localhost:8000/agents/health | python3 -m json.tool

## Parar y eliminar contenedores + red (mantiene imágenes)
clean:
	docker compose down --remove-orphans

## Parar, eliminar contenedores Y borrar imágenes (reset completo)
reset:
	docker compose down --rmi all --volumes --remove-orphans
