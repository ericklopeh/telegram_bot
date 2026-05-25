# P74 — Telegram webhook production mode

Preparación para operar el bot **24/7** vía webhook sin romper **polling** en desarrollo local.

## Polling vs webhook

| Modo | Cuándo | Cómo |
|------|--------|------|
| **Polling** | Local, Docker `bot`, staging simple | `python -m app.main` → `run_polling()` |
| **Webhook** | Staging/producción con HTTPS público | Telegram POST → `POST /telegram/webhook` en servicio **web** |

**Polling:** el proceso bot consulta a Telegram (long polling). Un solo proceso activo por token.

**Webhook:** Telegram envía updates a tu URL. Requiere HTTPS y secret token. El servicio `bot` en compose puede detenerse; el servicio `web` procesa updates.

## Variables requeridas

| Variable | Obligatorio webhook | Descripción |
|----------|---------------------|-------------|
| `TELEGRAM_BOT_TOKEN` | Sí | Token BotFather |
| `WEBHOOK_BASE_URL` | Sí | Base pública HTTPS sin path (ej. `https://staging.example.com`) |
| `WEBHOOK_SECRET` | Sí | Token aleatorio ≥ 16 chars; header `X-Telegram-Bot-Api-Secret-Token` |
| `TELEGRAM_RUN_MODE` | Recomendado | `polling` (default) o `webhook` |

En `.env.staging.example` / `.env.example` hay placeholders sin valores reales.

## Endpoint

- **Ruta:** `POST /telegram/webhook`
- **Código:** `app/web/routes/telegram_webhook.py`
- **Procesamiento:** `app/bot/webhook_processor.py` + `app/bot/application_factory.py`
- **Seguridad:** rechaza si `WEBHOOK_SECRET` vacío (503) o header incorrecto (403)
- **Rate limit:** excluido en `app/web/middleware/production.py`

## Registrar webhook

```bash
# En servidor o máquina con .env cargado
chmod +x scripts/telegram_set_webhook.sh
./scripts/telegram_set_webhook.sh
```

Equivale a:

```text
POST https://api.telegram.org/bot<TOKEN>/setWebhook
url = {WEBHOOK_BASE_URL}/telegram/webhook
secret_token = {WEBHOOK_SECRET}
```

Volver a polling:

```bash
./scripts/telegram_delete_webhook.sh
# TELEGRAM_RUN_MODE=polling y levantar servicio bot
docker compose -f docker-compose.staging.yml up -d bot
```

## Compose staging

**Opción A — polling (actual):** servicio `bot` activo, `TELEGRAM_RUN_MODE=polling`.

**Opción B — webhook:**  
- `TELEGRAM_RUN_MODE=webhook`  
- Detener o no levantar `bot`  
- `WEBHOOK_BASE_URL` = URL pública del nginx/web  
- Ejecutar `telegram_set_webhook.sh` una vez por entorno  

## Desarrollo local

- No registrar webhook contra `localhost` sin túnel (ngrok, cloudflared).
- Mantener `WEBHOOK_SECRET` vacío → endpoint responde 503 (webhook deshabilitado).
- Polling sigue en `docker-compose.yml` servicio `bot`.

## Tests

```bash
python -m pytest -q tests/test_p74_telegram_webhook.py
```

## Referencias

- `app/main.py` — sale si `TELEGRAM_RUN_MODE=webhook`
- `docs/P73_REAL_STAGING_ENVIRONMENT.md`
