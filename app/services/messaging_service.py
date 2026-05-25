"""P53 — mensajería operacional Telegram/WhatsApp (preparado)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)


class MessagingService:
    """Capa unificada sobre Telegram existente + webhook WhatsApp futuro."""

    def send_case_link(self, chat_id: int | str, case_public_id: str, case_id: int) -> bool:
        settings = get_settings()
        if not settings.telegram_bot_token:
            log.info("Messaging: link caso %s (sin token)", case_public_id)
            return False
        text = f"📋 Caso {case_public_id}\nVer: /casos/{case_id}"
        return self._send_telegram(chat_id, text)

    def send_alert(self, chat_id: int | str, message: str) -> bool:
        return self._send_telegram(chat_id, message)

    def parse_quick_command(self, text: str) -> dict[str, Any] | None:
        t = (text or "").strip().lower()
        if t.startswith("/caso "):
            return {"cmd": "case_lookup", "arg": t[6:].strip()}
        if t.startswith("/aprobar "):
            return {"cmd": "quick_approve", "arg": t[9:].strip()}
        if t == "/pendientes":
            return {"cmd": "list_pending"}
        return None

    def _send_telegram(self, chat_id: int | str, text: str) -> bool:
        settings = get_settings()
        if not settings.telegram_bot_token:
            return False
        try:
            import requests

            url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text[:4000]}, timeout=10)
            return True
        except Exception:
            log.debug("Telegram send falló", exc_info=True)
            return False

    def whatsapp_notify(self, phone: str, message: str) -> bool:
        """Placeholder WhatsApp Business API."""
        log.info("WhatsApp [%s]: %s", phone, message[:120])
        return False
