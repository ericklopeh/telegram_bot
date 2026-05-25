"""P74 — endpoint webhook Telegram (modo producción 24/7)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.bot.webhook_processor import process_telegram_update_payload, verify_webhook_secret
from app.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["telegram-webhook"])


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Recibe updates de Telegram cuando el bot usa webhook.
    Polling local no usa esta ruta (servicio `bot` con app/main.py).
    """
    settings = get_settings()
    secret = settings.telegram_webhook_secret.strip()
    if not secret:
        return JSONResponse(
            {"detail": "Webhook no configurado (WEBHOOK_SECRET vacío). Use polling en desarrollo."},
            status_code=503,
        )

    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not verify_webhook_secret(header, secret):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"detail": "Invalid payload"}, status_code=400)

    try:
        await process_telegram_update_payload(payload)
    except ValueError as exc:
        log.warning("Webhook: bot no inicializado — %s", exc)
        return JSONResponse({"detail": str(exc)}, status_code=503)
    except Exception:
        log.exception("Webhook: error procesando update")
        return JSONResponse({"detail": "Error interno"}, status_code=500)

    return {"ok": True}
