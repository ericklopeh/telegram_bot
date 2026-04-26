import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram.error import InvalidToken
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.handlers import (
    compulsa_reminder_job,
    error_handler,
    handle_callbacks,
    handle_files,
    handle_text,
    sharepoint_retry_job,
    sla_watchdog_job,
    start,
)
from app.config import get_settings
from app.utils.logging_config import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

log = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    try:
        settings = get_settings()
        token = settings.telegram_bot_token.strip()
        token_len = len(token)
        log.info("Configuracion cargada. TELEGRAM_BOT_TOKEN length=%d", token_len)
        if token in {"replace-me", "<SECRET>"} or ":" not in token or token_len < 20:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN no parece valido. Configuralo en .env con el token real de BotFather."
            )

        Path(settings.effective_pedidos_path).mkdir(parents=True, exist_ok=True)
        Path(settings.effective_revisiones_path).mkdir(parents=True, exist_ok=True)

        app = ApplicationBuilder().token(token).build()
        app.add_error_handler(error_handler)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(handle_callbacks))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_files))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        if app.job_queue is not None:
            interval_seconds = max(settings.compulsa_reminder_minutes, 1) * 60
            app.job_queue.run_repeating(compulsa_reminder_job, interval=interval_seconds, first=120)
            retry_interval = max(settings.sharepoint_retry_interval_minutes, 1) * 60
            app.job_queue.run_repeating(sharepoint_retry_job, interval=retry_interval, first=90)
            app.job_queue.run_repeating(sla_watchdog_job, interval=300, first=150)
            log.info("JobQueue habilitado. Intervalo compulsa=%s segundos", interval_seconds)
        else:
            log.warning(
                "JobQueue no disponible. Instala python-telegram-bot[job-queue] "
                "para habilitar recordatorios automáticos de compulsa."
            )

        log.info("Bot corriendo (PostgreSQL + persistencia activa).")
        log.info("Iniciando run_polling()...")
        app.run_polling()
        log.info("run_polling() finalizo.")
    except InvalidToken:
        log.exception(
            "Token de Telegram invalido. Verifica TELEGRAM_BOT_TOKEN en .env y regenera el token en BotFather si es necesario."
        )
        raise
    except Exception:
        log.exception("Fallo critico al iniciar o ejecutar el bot.")
        raise


if __name__ == "__main__":
    main()
