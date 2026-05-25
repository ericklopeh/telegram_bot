#!/usr/bin/env bash
# P74 — registrar webhook en Telegram Bot API
# Uso: ./scripts/telegram_set_webhook.sh
# Requiere en .env: TELEGRAM_BOT_TOKEN, WEBHOOK_BASE_URL, WEBHOOK_SECRET
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN requerido}"
: "${WEBHOOK_BASE_URL:?WEBHOOK_BASE_URL requerido (ej. https://staging.example.com)}"
: "${WEBHOOK_SECRET:?WEBHOOK_SECRET requerido}"

BASE="${WEBHOOK_BASE_URL%/}"
URL="${BASE}/telegram/webhook"

echo "==> setWebhook url=${URL}"
resp="$(curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"${URL}\",\"secret_token\":\"${WEBHOOK_SECRET}\",\"drop_pending_updates\":false}")"
echo "${resp}"

if ! echo "${resp}" | grep -q '"ok":true'; then
  echo "FAIL: setWebhook no devolvió ok"
  exit 1
fi

echo "==> getWebhookInfo"
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | head -c 2000
echo ""
echo "OK: webhook registrado"
