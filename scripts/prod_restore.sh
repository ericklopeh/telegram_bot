#!/usr/bin/env bash
# P70 — restaurar backup producción (¡destructivo en DB!)
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Uso: $0 <directorio_backup prod_YYYYMMDD_HHMMSS>"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ARCHIVE="$1"

if [ ! -d "${ARCHIVE}" ]; then
  echo "No existe: ${ARCHIVE}"
  exit 1
fi

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

DB_NAME="${POSTGRES_DB:-bot_gaman}"
DB_USER="${POSTGRES_USER:-bot_user}"

PG_FILE="$(find "${ARCHIVE}" -name 'pg_*.sql.gz' | head -1)"
if [ -z "${PG_FILE}" ]; then
  echo "No se encontró dump SQL en ${ARCHIVE}"
  exit 1
fi

echo "ADVERTENCIA: restaurará ${DB_NAME} desde ${PG_FILE}"
read -r -p "Escriba RESTORE para continuar: " CONF
if [ "${CONF}" != "RESTORE" ]; then
  echo "Cancelado."
  exit 1
fi

echo "Restaurando PostgreSQL..."
gunzip -c "${PG_FILE}" | docker compose -f "${COMPOSE_FILE}" exec -T db \
  psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1

STORAGE_TAR="${ARCHIVE}/storage.tar.gz"
if [ -f "${STORAGE_TAR}" ]; then
  echo "Restaurando storage..."
  tar -xzf "${STORAGE_TAR}" -C "${ROOT}"
fi

echo "Restore completado. Reinicie servicios:"
echo "  docker compose -f ${COMPOSE_FILE} restart web worker nginx"
