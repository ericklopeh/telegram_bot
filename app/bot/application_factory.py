"""Factory del Application de Telegram — compartida entre polling y webhook (P74)."""

from __future__ import annotations

import logging
from pathlib import Path

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot.handlers import (
    admin_sessions,
    compulsa_reminder_job,
    error_handler,
    handle_callbacks,
    handle_files,
    handle_text,
    sharepoint_retry_job,
    sla_watchdog_job,
    start,
)
from app.bot.persistence import PostgresPersistence
from app.config import get_settings
from app.services.notification_service import run_daily_operational_summary_job

log = logging.getLogger(__name__)


def build_telegram_application() -> Application:
    """Construye la app PTB con handlers y JobQueue (sin iniciar polling)."""
    settings = get_settings()
    token = settings.telegram_bot_token.strip()
    if token in {"replace-me", "<SECRET>", "your_telegram_bot_token_here"} or ":" not in token:
        raise ValueError("TELEGRAM_BOT_TOKEN no configurado para el bot.")

    Path(settings.effective_pedidos_path).mkdir(parents=True, exist_ok=True)
    Path(settings.effective_revisiones_path).mkdir(parents=True, exist_ok=True)

    app = ApplicationBuilder().token(token).persistence(PostgresPersistence()).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sessions", admin_sessions))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_files))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    if app.job_queue is not None:
        interval_seconds = max(settings.compulsa_reminder_minutes, 1) * 60
        app.job_queue.run_repeating(compulsa_reminder_job, interval=interval_seconds, first=120)
        retry_interval = max(settings.sharepoint_retry_interval_minutes, 1) * 60
        app.job_queue.run_repeating(sharepoint_retry_job, interval=retry_interval, first=90)
        app.job_queue.run_repeating(sla_watchdog_job, interval=300, first=150)
        if settings.operational_alerts_telegram:
            app.job_queue.run_repeating(
                run_daily_operational_summary_job,
                interval=21600,
                first=300,
            )
            log.info("JobQueue: resumen operativo cada 6h")
        log.info("JobQueue habilitado. Intervalo compulsa=%s s", interval_seconds)
    else:
        log.warning(
            "JobQueue no disponible. Instala python-telegram-bot[job-queue] para recordatorios."
        )

    return app
