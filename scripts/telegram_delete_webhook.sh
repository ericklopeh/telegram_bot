#!/usr/bin/env bash
# P74 — volver a modo polling (elimina webhook en Telegram)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${TELEGRAM_BOT_TOKEN:?}"

echo "==> deleteWebhook"
curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook" \
  -d "drop_pending_updates=false"
echo ""
echo "Listo. Reinicia el servicio bot con TELEGRAM_RUN_MODE=polling."
