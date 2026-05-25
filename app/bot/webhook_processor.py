"""Procesamiento de updates Telegram vía webhook (P74)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Update

from app.bot.application_factory import build_telegram_application
from app.config import get_settings

log = logging.getLogger(__name__)

_application = None
_init_lock = asyncio.Lock()


async def _ensure_application():
    global _application
    if _application is not None:
        return _application
    async with _init_lock:
        if _application is None:
            app = build_telegram_application()
            await app.initialize()
            await app.start()
            _application = app
    return _application


def verify_webhook_secret(header_value: str | None, expected: str) -> bool:
    """Valida X-Telegram-Bot-Api-Secret-Token."""
    if not expected:
        return False
    return (header_value or "") == expected


async def process_telegram_update_payload(payload: dict[str, Any]) -> None:
    """Despacha un update JSON de Telegram Bot API."""
    app = await _ensure_application()
    update = Update.de_json(payload, app.bot)
    if update is None:
        log.warning("Webhook: payload no es un Update válido")
        return
    await app.process_update(update)
