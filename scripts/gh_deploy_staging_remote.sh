#!/usr/bin/env bash
# P72 — deploy remoto vía SSH (ejecutar desde GitHub Actions runner).
# Requiere: STAGING_SSH_HOST, STAGING_SSH_USER, STAGING_SSH_PRIVATE_KEY, STAGING_APP_PATH
# Uso: ./scripts/gh_deploy_staging_remote.sh <git_ref>
set -euo pipefail

REF="${1:-main}"

: "${STAGING_SSH_HOST:?}"
: "${STAGING_SSH_USER:?}"
: "${STAGING_APP_PATH:?}"

SSH_KEY="${STAGING_SSH_KEY_FILE:-$HOME/.ssh/staging_deploy_key}"
: "${STAGING_SSH_PRIVATE_KEY:?}"

mkdir -p "$(dirname "${SSH_KEY}")"
umask 077
printf '%s\n' "${STAGING_SSH_PRIVATE_KEY}" > "${SSH_KEY}"
chmod 600 "${SSH_KEY}"

KNOWN_HOSTS="${HOME}/.ssh/known_hosts_staging"
mkdir -p "${HOME}/.ssh"
ssh-keyscan -H "${STAGING_SSH_HOST}" >> "${KNOWN_HOSTS}" 2>/dev/null || true

echo "==> Deploy staging en ${STAGING_SSH_USER}@${STAGING_SSH_HOST}:${STAGING_APP_PATH} (ref=${REF})"

ssh -i "${SSH_KEY}" \
  -o UserKnownHostsFile="${KNOWN_HOSTS}" \
  -o StrictHostKeyChecking=accept-new \
  "${STAGING_SSH_USER}@${STAGING_SSH_HOST}" \
  "REF='${REF}' APP_PATH='${STAGING_APP_PATH}' bash -s" <<'REMOTE'
set -euo pipefail
cd "${APP_PATH}"
echo "Directorio: $(pwd)"
git fetch --all --prune
git checkout "${REF}"
git pull --ff-only origin "${REF}" 2>/dev/null || git pull origin "${REF}" || true
export COMPOSE_FILE=docker-compose.staging.yml
docker compose -f docker-compose.staging.yml build web nginx
docker compose -f docker-compose.staging.yml up -d db web nginx
docker compose -f docker-compose.staging.yml exec -T web alembic upgrade head
docker compose -f docker-compose.staging.yml ps
echo "Deploy remoto finalizado."
REMOTE

rm -f "${SSH_KEY}"
echo "SSH deploy step OK"
