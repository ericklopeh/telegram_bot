"""P70 — integración opcional Sentry."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def init_sentry() -> bool:
    from app.config import get_settings

    settings = get_settings()
    dsn = (getattr(settings, "sentry_dsn", None) or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.environment,
            release=settings.app_version,
            traces_sample_rate=0.1 if settings.environment == "production" else 0.0,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            send_default_pii=False,
        )
        log.info("Sentry inicializado env=%s", settings.environment)
        return True
    except ImportError:
        log.warning("sentry-sdk no instalado; omitiendo Sentry")
        return False
    except Exception:
        log.exception("Sentry init falló")
        return False
