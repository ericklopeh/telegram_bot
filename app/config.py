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
    web_session_secret: str = Field(default="CAMBIA_ESTA_CLAVE_DEMO_GAMAN_2026", alias="WEB_SESSION_SECRET")
    # Solo desarrollo local: ante un 500, respuesta texto con traceback y traza en consola. No usar en producción.
    web_debug: bool = Field(default=False, alias="WEB_DEBUG")
    # Si True, la web no aplica RBAC por rol (cualquier usuario logueado puede usar rutas de admin/autorización/revisión).
    # En producción debe ser False. En docker-compose suele activarse por defecto para pruebas locales.
    web_rbac_relaxed: bool = Field(default=False, alias="WEB_RBAC_RELAXED")
    # Si True y el chat no tiene users.telegram_id, el bot usa un usuario demo (primer admin/sistemas activo, o el primer activo). Solo desarrollo.
    telegram_dev_fallback_any_sender: bool = Field(default=False, alias="TELEGRAM_DEV_FALLBACK_ANY_SENDER")

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
    chat_id_admin_alerts: int | None = Field(default=None, alias="CHAT_ID_ADMIN_ALERTS")
    compulsa_reminder_minutes: int = Field(default=60, alias="COMPULSA_REMINDER_MINUTES")
    seller_user_ids: str = Field(default="", alias="SELLER_USER_IDS")
    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")
    display_timezone: str = Field(default="America/Mexico_City", alias="DISPLAY_TIMEZONE")
    business_hours_enabled: bool = Field(default=False, alias="BUSINESS_HOURS_ENABLED")
    business_hours_start: str = Field(default="09:00", alias="BUSINESS_HOURS_START")
    business_hours_end: str = Field(default="18:30", alias="BUSINESS_HOURS_END")
    ms_tenant_id: str = Field(default="", alias="MS_TENANT_ID")
    ms_client_id: str = Field(default="", alias="MS_CLIENT_ID")
    ms_client_secret: str = Field(default="", alias="MS_CLIENT_SECRET")
    ms_site_hostname: str = Field(default="", alias="MS_SITE_HOSTNAME")
    ms_site_path: str = Field(default="", alias="MS_SITE_PATH")
    ms_site_id: str = Field(default="", alias="MS_SITE_ID")
    ms_drive_name: str = Field(default="", alias="MS_DRIVE_NAME")
    ms_drive_id: str = Field(default="", alias="MS_DRIVE_ID")
    ms_root_folder: str = Field(default="", alias="MS_ROOT_FOLDER")
    sharepoint_retry_interval_minutes: int = Field(default=5, alias="SHAREPOINT_RETRY_INTERVAL_MINUTES")
    sharepoint_retry_max_attempts: int = Field(default=8, alias="SHAREPOINT_RETRY_MAX_ATTEMPTS")
    ms_graph_max_retries: int = Field(default=5, alias="MS_GRAPH_MAX_RETRIES")
    ms_graph_retry_base_seconds: float = Field(default=1.0, alias="MS_GRAPH_RETRY_BASE_SECONDS")
    ms_graph_upload_chunk_bytes: int = Field(
        default=10 * 320 * 1024, alias="MS_GRAPH_UPLOAD_CHUNK_BYTES"
    )
    ms_graph_request_timeout: int = Field(default=30, alias="MS_GRAPH_REQUEST_TIMEOUT")
    ms_graph_upload_timeout: int = Field(default=120, alias="MS_GRAPH_UPLOAD_TIMEOUT")
    ms_graph_small_file_max_bytes: int = Field(
        default=4 * 1024 * 1024, alias="MS_GRAPH_SMALL_FILE_MAX_BYTES"
    )
    sla_alert_interval_minutes: int = Field(default=120, alias="SLA_ALERT_INTERVAL_MINUTES")
    sla_revision_minutes: int = Field(default=240, alias="SLA_REVISION_MINUTES")
    sla_autorizacion_minutes: int = Field(default=240, alias="SLA_AUTORIZACION_MINUTES")
    sla_compulsa_minutes: int = Field(default=180, alias="SLA_COMPULSA_MINUTES")
    operational_alerts_telegram: bool = Field(
        default=False, alias="OPERATIONAL_ALERTS_TELEGRAM"
    )

    # P30 — operación / staging
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    storage_root: str = Field(default="/app/storage", alias="STORAGE_ROOT")
    demo_mode: bool = Field(default=False, alias="DEMO_MODE")
    # P34 — exige confirmaciones textuales y limita acciones masivas destructivas
    beta_safe_mode: bool = Field(default=False, alias="BETA_SAFE_MODE")

    # P36-P45 — plataforma enterprise
    redis_url: str = Field(default="", alias="REDIS_URL")
    jobs_async_enabled: bool = Field(default=True, alias="JOBS_ASYNC_ENABLED")
    slow_query_ms: int = Field(default=500, alias="SLOW_QUERY_MS")
    cache_ttl_seconds: int = Field(default=60, alias="CACHE_TTL_SECONDS")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    notification_email_from: str = Field(default="", alias="NOTIFICATION_EMAIL_FROM")
    notification_webhook_url: str = Field(default="", alias="NOTIFICATION_WEBHOOK_URL")
    notification_slack_webhook: str = Field(default="", alias="NOTIFICATION_SLACK_WEBHOOK")
    api_rate_limit_per_min: int = Field(default=120, alias="API_RATE_LIMIT_PER_MIN")
    default_company_id: int = Field(default=1, alias="DEFAULT_COMPANY_ID")
    default_branch_id: int = Field(default=1, alias="DEFAULT_BRANCH_ID")

    # P70 — producción
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")
    secure_cookies: bool | None = Field(default=None, alias="SECURE_COOKIES")
    max_upload_bytes: int = Field(default=128 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")
    backup_retention_days: int = Field(default=14, alias="BACKUP_RETENTION_DAYS")
    trusted_proxy: bool = Field(default=False, alias="TRUSTED_PROXY")

    @property
    def session_https_only(self) -> bool:
        if self.secure_cookies is not None:
            return self.secure_cookies
        return self.environment == "production"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

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
