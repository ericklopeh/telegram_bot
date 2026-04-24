from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def compute_semana_activa_iso(timezone: str) -> str:
    """Semana calendario ISO: SEM WW-AAAA (p. ej. SEM 17-2026)."""
    now = datetime.now(ZoneInfo(timezone))
    y, w, _ = now.isocalendar()
    return f"SEM {w:02d}-{y}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    # Si es True, la semana se calcula con la fecha actual en DISPLAY_TIMEZONE (ISO). Si es False, usa SEMANA_ACTIVA.
    semana_activa_auto: bool = Field(default=True, alias="SEMANA_ACTIVA_AUTO")
    semana_activa: str = Field(default="SEM 00-0000", alias="SEMANA_ACTIVA")

    # SQLAlchemy / Alembic (obligatoria). Preferir postgresql+psycopg:// (psycopg3). Host `db` en Compose; `localhost` si el cliente corre en Windows contra el puerto publicado.
    database_url: str = Field(..., alias="DATABASE_URL")

    # Usadas por docker-compose para el servicio `db` (deben coincidir con usuario/clave/base en DATABASE_URL).
    postgres_db: str = Field(default="bot_gaman", alias="POSTGRES_DB")
    postgres_user: str = Field(default="bot_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="Bgaman_2026_Postgres_Seguro!", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="db", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    base_storage_path: str = Field(default="/app/storage", alias="BASE_STORAGE_PATH")
    pedidos_path: str = Field(default="/app/storage/pedidos", alias="PEDIDOS_PATH")
    revisiones_path: str = Field(default="/app/storage/revisiones", alias="REVISIONES_PATH")
    ruta_base_pedidos: str | None = Field(default=None, alias="RUTA_BASE_PEDIDOS")
    ruta_base_revisiones: str | None = Field(default=None, alias="RUTA_BASE_REVISIONES")

    chat_id_pedidos: int | None = Field(default=None, alias="CHAT_ID_PEDIDOS")
    chat_id_compulsas: int | None = Field(default=None, alias="CHAT_ID_COMPULSAS")
    compulsa_reminder_minutes: int = Field(default=60, alias="COMPULSA_REMINDER_MINUTES")
    seller_user_ids: str = Field(default="", alias="SELLER_USER_IDS")
    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")
    display_timezone: str = Field(default="America/Mexico_City", alias="DISPLAY_TIMEZONE")

    @property
    def sqlalchemy_database_uri(self) -> str:
        return self.database_url.strip().strip('"').strip("'")

    @property
    def effective_pedidos_path(self) -> str:
        return self.ruta_base_pedidos or self.pedidos_path

    @property
    def effective_revisiones_path(self) -> str:
        return self.ruta_base_revisiones or self.revisiones_path

    @property
    def effective_semana_activa(self) -> str:
        if self.semana_activa_auto:
            return compute_semana_activa_iso(self.display_timezone)
        manual = (self.semana_activa or "").strip()
        if manual and manual != "SEM 00-0000":
            return manual
        return compute_semana_activa_iso(self.display_timezone)

    @staticmethod
    def _parse_id_csv(raw: str) -> set[int]:
        ids: set[int] = set()
        for token in raw.split(","):
            value = token.strip()
            if not value:
                continue
            try:
                ids.add(int(value))
            except ValueError:
                continue
        return ids

    @property
    def seller_user_ids_set(self) -> set[int]:
        return self._parse_id_csv(self.seller_user_ids)

    @property
    def admin_user_ids_set(self) -> set[int]:
        return self._parse_id_csv(self.admin_user_ids)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
