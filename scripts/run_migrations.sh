#!/usr/bin/env bash
# Alembic upgrade head en contenedor web (P30)
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"

echo "Ejecutando alembic upgrade head ..."
docker compose -f "${COMPOSE_FILE}" exec -T web alembic upgrade head
echo "Migraciones aplicadas."
