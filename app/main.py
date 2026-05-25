import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram.error import InvalidToken

from app.bot.application_factory import build_telegram_application
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

        if settings.telegram_run_mode == "webhook":
            log.warning(
                "TELEGRAM_RUN_MODE=webhook: el servicio bot no debe usar polling. "
                "Use el endpoint POST /telegram/webhook en el servicio web."
            )
            return

        app = build_telegram_application()
        log.info("Bot corriendo (PostgreSQL + persistencia activa, modo polling).")
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
