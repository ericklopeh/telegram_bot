"""P38 — notificaciones enterprise (Telegram, email, webhook, throttling)."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.platform import NotificationDelivery, NotificationPreference

log = logging.getLogger(__name__)

EVENT_TYPES = (
    "sharepoint_failed",
    "case_stale_24h",
    "checklist_incomplete",
    "import_finished",
    "commission_generated",
    "workflow_approved",
    "critical_incident",
)

CHANNELS = ("telegram", "email", "webhook", "slack")

_throttle_cache: dict[str, float] = {}


class EnterpriseNotificationService:
    def is_enabled(
        self,
        db: Session,
        event_type: str,
        channel: str,
        *,
        user_id: int | None = None,
    ) -> bool:
        if event_type not in EVENT_TYPES:
            return False
        stmt = select(NotificationPreference).where(
            NotificationPreference.channel == channel,
            NotificationPreference.event_type == event_type,
        )
        if user_id:
            stmt = stmt.where(NotificationPreference.user_id == user_id)
        else:
            stmt = stmt.where(NotificationPreference.user_id.is_(None))
        pref = db.scalar(stmt)
        if pref is None:
            return True
        return bool(pref.enabled)

    def _throttle_key(self, channel: str, recipient: str, event_type: str) -> str:
        raw = f"{channel}:{recipient}:{event_type}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _should_throttle(self, key: str, window_seconds: int = 300) -> bool:
        now = time.time()
        last = _throttle_cache.get(key)
        if last and (now - last) < window_seconds:
            return True
        _throttle_cache[key] = now
        return False

    def notify(
        self,
        db: Session,
        event_type: str,
        message: str,
        *,
        channel: str = "webhook",
        recipient: str | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: int | None = None,
    ) -> NotificationDelivery:
        if not self.is_enabled(db, event_type, channel, user_id=user_id):
            delivery = NotificationDelivery(
                channel=channel,
                event_type=event_type,
                recipient=recipient or "disabled",
                status="skipped",
                message=message,
                metadata_json=metadata,
            )
            db.add(delivery)
            db.flush()
            return delivery

        recipient = recipient or self._default_recipient(channel)
        tkey = self._throttle_key(channel, recipient, event_type)
        if self._should_throttle(tkey):
            delivery = NotificationDelivery(
                channel=channel,
                event_type=event_type,
                recipient=recipient,
                status="throttled",
                message=message,
                metadata_json=metadata,
            )
            db.add(delivery)
            db.flush()
            return delivery

        delivery = NotificationDelivery(
            channel=channel,
            event_type=event_type,
            recipient=recipient,
            status="pending",
            message=message,
            metadata_json=metadata,
        )
        db.add(delivery)
        db.flush()

        try:
            self._deliver(channel, recipient, message, metadata)
            delivery.status = "sent"
            delivery.sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            delivery.attempts += 1
            delivery.status = "failed"
            delivery.last_error = str(exc)[:1000]
            log.warning("Notificación fallida %s/%s: %s", channel, event_type, exc)
        db.flush()
        return delivery

    def _default_recipient(self, channel: str) -> str:
        settings = get_settings()
        if channel == "telegram":
            return str(settings.chat_id_admin_alerts or "telegram:admin")
        if channel == "email":
            return settings.notification_email_from or "noreply@gaman.local"
        if channel == "slack":
            return settings.notification_slack_webhook or "slack:disabled"
        return settings.notification_webhook_url or "webhook:internal"

    def _deliver(
        self,
        channel: str,
        recipient: str,
        message: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        settings = get_settings()
        if channel == "webhook" and settings.notification_webhook_url:
            requests.post(
                settings.notification_webhook_url,
                json={"text": message, "metadata": metadata or {}},
                timeout=10,
            )
            return
        if channel == "slack" and settings.notification_slack_webhook:
            requests.post(
                settings.notification_slack_webhook,
                json={"text": message},
                timeout=10,
            )
            return
        if channel == "email" and settings.smtp_host:
            self._send_email(recipient, message)
            return
        if channel == "telegram" and settings.operational_alerts_telegram:
            log.info("Telegram notification [%s]: %s", recipient, message[:200])
            return
        log.info("Notificación [%s] -> %s: %s", channel, recipient, message[:200])

    def _send_email(self, to_addr: str, body: str) -> None:
        import smtplib
        from email.mime.text import MIMEText

        settings = get_settings()
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "[Sistema Gaman] Alerta operativa"
        msg["From"] = settings.notification_email_from or settings.smtp_user
        msg["To"] = to_addr
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_user:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)

    def notify_operational_event(
        self,
        db: Session,
        event_type: str,
        message: str,
        **kwargs: Any,
    ) -> list[NotificationDelivery]:
        """Envía por canales configurados (webhook + log telegram)."""
        results = []
        for ch in ("webhook", "telegram"):
            results.append(
                self.notify(db, event_type, message, channel=ch, **kwargs)
            )
        return results
