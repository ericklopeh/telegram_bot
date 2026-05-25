#!/usr/bin/env bash
# P71 — smoke HTTP /health (staging o local)
# Uso: ./scripts/smoke_health.sh
#      ./scripts/smoke_health.sh http://localhost:8080
set -euo pipefail

BASE="${1:-http://localhost:8080}"
BASE="${BASE%/}"

echo "==> GET ${BASE}/health"
code="$(curl -s -o /tmp/gaman_health.json -w "%{http_code}" "${BASE}/health")"
echo "HTTP ${code}"
cat /tmp/gaman_health.json
echo ""

if [ "${code}" != "200" ]; then
  echo "FAIL: /health no devolvió 200"
  exit 1
fi

if ! grep -q '"status"' /tmp/gaman_health.json && ! grep -q 'ok' /tmp/gaman_health.json; then
  echo "WARN: respuesta sin status ok visible"
fi

echo "OK: /health smoke passed"
