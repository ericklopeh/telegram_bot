#!/usr/bin/env bash
# Respaldo PostgreSQL — Sistema Gaman (P30)
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "${BACKUP_DIR}"

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

DB_NAME="${POSTGRES_DB:-bot_gaman}"
DB_USER="${POSTGRES_USER:-bot_user}"
OUT="${BACKUP_DIR}/pg_${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "Exportando ${DB_NAME} -> ${OUT}"
docker compose -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --clean \
  | gzip -9 > "${OUT}"

echo "Backup listo: ${OUT}"
ls -lh "${OUT}"
