from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CaseEvent(Base):
    """Auditoría de eventos por caso.

    Registra cualquier acción significativa: cambios de estado, generación de
    documentos, errores, subidas a SharePoint, notificaciones Telegram, etc.
    """

    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Tipo de evento. Ejemplos:
    #   "status_change", "document_generated", "sharepoint_upload",
    #   "telegram_notification", "validation_error", "refinanciamiento_generated"
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Mensaje legible (para mostrar en UI/timeline)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Usuario que ejecutó la acción (nombre, username o "system")
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Origen de la acción: "web", "telegram", "system", "sharepoint", "bot"
    source: Mapped[str | None] = mapped_column(
        String(32), nullable=True, server_default="system", index=False
    )

    # Datos estructurados opcionales (doc_id, old_status, new_status, etc.)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Relaciones
    case = relationship("Case", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_user_id])
