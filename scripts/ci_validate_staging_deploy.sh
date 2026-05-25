#!/usr/bin/env bash
# P72 — valida variables/secrets requeridos antes de deploy staging (CI).
set -euo pipefail

REQUIRED_VARS=(
  STAGING_SSH_HOST
  STAGING_SSH_USER
  STAGING_SSH_PRIVATE_KEY
  STAGING_APP_PATH
  STAGING_URL
)

missing=0
for name in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!name:-}" ]; then
    echo "FAIL: falta secret/variable ${name}"
    missing=1
  else
    echo "OK   ${name} definido"
  fi
done

if [ "${missing}" -ne 0 ]; then
  echo ""
  echo "Configura los secrets en GitHub: Settings → Secrets and variables → Actions"
  exit 1
fi

# Validación básica de URL (sin imprimir secretos)
case "${STAGING_URL}" in
  http://*|https://*) ;;
  *)
    echo "FAIL: STAGING_URL debe empezar con http:// o https://"
    exit 1
    ;;
esac

echo "Validación de secrets staging: OK"
