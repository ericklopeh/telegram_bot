#!/usr/bin/env bash
# Despliegue staging reproducible — Sistema Gaman (P30)
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.staging.yml}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [ ! -f .env ]; then
  echo "Falta .env — copia desde .env.example y configura secretos."
  exit 1
fi

mkdir -p storage logs backups

echo "==> Build imágenes"
docker compose -f "${COMPOSE_FILE}" build web nginx

echo "==> Levantar servicios"
docker compose -f "${COMPOSE_FILE}" up -d db web nginx

echo "==> Esperar health web"
sleep 5
docker compose -f "${COMPOSE_FILE}" ps

echo "==> Migraciones"
"${ROOT}/scripts/run_migrations.sh"

echo "==> Health check"
curl -sf "http://localhost:${NGINX_HTTP_PORT:-8080}/health" || true
curl -sf "http://localhost:${NGINX_HTTP_PORT:-8080}/health/full" | head -c 500 || true

echo ""
echo "Deploy staging completado. Panel: http://localhost:${NGINX_HTTP_PORT:-8080}"
