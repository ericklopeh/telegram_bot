#!/usr/bin/env bash
# Reinicio de servicios staging (P30)
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"

docker compose -f "${COMPOSE_FILE}" restart web nginx
echo "Servicios web y nginx reiniciados."
