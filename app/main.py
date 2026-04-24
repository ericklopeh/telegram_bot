import logging
from pathlib import Path

from dotenv import load_dotenv
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
    start,
)
from app.config import get_settings
from app.utils.logging_config import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

log = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    settings = get_settings()

    Path(settings.effective_pedidos_path).mkdir(parents=True, exist_ok=True)
    Path(settings.effective_revisiones_path).mkdir(parents=True, exist_ok=True)

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_files))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    if app.job_queue is not None:
        interval_seconds = max(settings.compulsa_reminder_minutes, 1) * 60
        app.job_queue.run_repeating(compulsa_reminder_job, interval=interval_seconds, first=120)
    else:
        log.warning(
            "JobQueue no disponible. Instala python-telegram-bot[job-queue] "
            "para habilitar recordatorios automáticos de compulsa."
        )

    log.info("Bot corriendo (PostgreSQL + persistencia activa).")
    app.run_polling()


if __name__ == "__main__":
    main()
