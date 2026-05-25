#!/usr/bin/env bash
# P70 — verificar integridad de un backup
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Uso: $0 <directorio_backup prod_YYYYMMDD_HHMMSS>"
  exit 1
fi

ARCHIVE="$1"
FAIL=0

check() {
  if [ -e "$2" ]; then
    echo "OK   $1"
  else
    echo "FAIL $1 — falta $2"
    FAIL=1
  fi
}

check "manifest" "${ARCHIVE}/manifest.json"
check "postgresql" "$(find "${ARCHIVE}" -name 'pg_*.sql.gz' | head -1)"
check "storage_tar" "${ARCHIVE}/storage.tar.gz"

PG="$(find "${ARCHIVE}" -name 'pg_*.sql.gz' | head -1)"
if [ -n "${PG}" ]; then
  if gzip -t "${PG}" 2>/dev/null; then
    echo "OK   pg_dump gzip válido"
  else
    echo "FAIL pg_dump corrupto"
    FAIL=1
  fi
fi

if [ -f "${ARCHIVE}/storage.tar.gz" ]; then
  if tar -tzf "${ARCHIVE}/storage.tar.gz" >/dev/null 2>&1; then
    echo "OK   storage.tar.gz válido"
  else
    echo "FAIL storage.tar corrupto"
    FAIL=1
  fi
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "Verificación: OK"
  exit 0
fi
echo "Verificación: FAIL"
exit 1
