#!/usr/bin/env bash
# P77 — verificar integridad de un dump .sql.gz (sin restaurar)
# Uso: ./scripts/restore_check_db.sh backups/pg_gaman_staging_20260101_120000.sql.gz
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Uso: $0 <archivo.sql.gz>"
  exit 1
fi

FILE="$1"
if [ ! -f "${FILE}" ]; then
  echo "FAIL: no existe ${FILE}"
  exit 1
fi

if gzip -t "${FILE}"; then
  echo "OK   gzip válido: ${FILE}"
  bytes="$(gzip -l "${FILE}" | tail -1 | awk '{print $2}')"
  echo "     tamaño descomprimido aprox: ${bytes} bytes"
  exit 0
fi

echo "FAIL: archivo corrupto"
exit 1
