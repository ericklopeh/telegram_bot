#!/usr/bin/env bash
# Restaurar PostgreSQL desde .sql.gz — Sistema Gaman (P30)
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Uso: $0 <archivo.sql.gz>"
  echo "Ejemplo: $0 ./backups/pg_bot_gaman_20260519_120000.sql.gz"
  exit 1
fi

DUMP_FILE="$1"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"

if [ ! -f "${DUMP_FILE}" ]; then
  echo "No existe: ${DUMP_FILE}"
  exit 1
fi

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

DB_NAME="${POSTGRES_DB:-bot_gaman}"
DB_USER="${POSTGRES_USER:-bot_user}"

echo "ADVERTENCIA: esto sobrescribe la base ${DB_NAME}. Ctrl+C para cancelar."
sleep 3

echo "Restaurando ${DUMP_FILE} ..."
gunzip -c "${DUMP_FILE}" | docker compose -f "${COMPOSE_FILE}" exec -T db \
  psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1

echo "Restore completado."
