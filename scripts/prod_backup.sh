#!/usr/bin/env bash
# P70 — backup producción: PostgreSQL + storage (sin excel_masters escritura)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "${BACKUP_DIR}"

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

DB_NAME="${POSTGRES_DB:-bot_gaman}"
DB_USER="${POSTGRES_USER:-bot_user}"
ARCHIVE="${BACKUP_DIR}/prod_${TIMESTAMP}"

mkdir -p "${ARCHIVE}"

echo "=== Backup PostgreSQL ==="
PG_OUT="${ARCHIVE}/pg_${DB_NAME}.sql.gz"
docker compose -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --clean \
  | gzip -9 > "${PG_OUT}"
echo "OK ${PG_OUT}"

echo "=== Backup storage (cases, exports, attachments, tenants) ==="
STORAGE_TAR="${ARCHIVE}/storage.tar.gz"
tar -czf "${STORAGE_TAR}" \
  --exclude='storage/excel_masters' \
  -C "${ROOT}" \
  storage/cases \
  storage/excel_exports \
  storage/attachments \
  storage/tenants \
  storage/imports \
  2>/dev/null || tar -czf "${STORAGE_TAR}" -C "${ROOT}" storage 2>/dev/null || true
echo "OK ${STORAGE_TAR}"

MANIFEST="${ARCHIVE}/manifest.json"
cat > "${MANIFEST}" <<EOF
{"timestamp":"${TIMESTAMP}","db":"${PG_OUT}","storage":"${STORAGE_TAR}","retention_days":${RETENTION_DAYS}}
EOF

echo "=== Retención ${RETENTION_DAYS} días ==="
find "${BACKUP_DIR}" -maxdepth 1 -type d -name 'prod_*' -mtime +"${RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null || true

echo "Backup completo: ${ARCHIVE}"
ls -lh "${ARCHIVE}"
