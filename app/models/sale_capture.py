"""Captura de ventas desde web (P19/P20) — persistencia y vínculo con casos."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Legacy status (compatibilidad P19)
SALE_STATUS_DRAFT = "draft"
SALE_STATUS_PENDING_VALIDATION = "pending_validation"
SALE_STATUS_REGISTERED = "registered"
SALE_STATUS_EXPORT_FAILED = "export_failed"
SALE_STATUS_CANCELLED = "cancelled"

# P20: estados formales de registro Excel
REG_STATUS_DRAFT = "draft"
REG_STATUS_PENDING_VALIDATION = "pending_validation"
REG_STATUS_PENDING_REGISTRATION = "pending_registration"
REG_STATUS_PROCESSING_REGISTRATION = "processing_registration"
REG_STATUS_REGISTERED = "registered"
REG_STATUS_REGISTRATION_FAILED = "registration_failed"

REGISTRATION_FAILED_STATUSES = frozenset(
    {REG_STATUS_REGISTRATION_FAILED, SALE_STATUS_EXPORT_FAILED}
)


def sync_legacy_status_from_registration(sale: "SaleCapture") -> None:
    """Mantiene columna status alineada con registration_status."""
    rs = sale.registration_status or REG_STATUS_DRAFT
    if rs == REG_STATUS_REGISTERED:
        sale.status = SALE_STATUS_REGISTERED
    elif rs == REG_STATUS_REGISTRATION_FAILED:
        sale.status = SALE_STATUS_EXPORT_FAILED
    elif rs == REG_STATUS_PENDING_VALIDATION:
        sale.status = SALE_STATUS_PENDING_VALIDATION
    elif rs in (REG_STATUS_PENDING_REGISTRATION, REG_STATUS_PROCESSING_REGISTRATION):
        sale.status = SALE_STATUS_PENDING_VALIDATION
    else:
        sale.status = SALE_STATUS_DRAFT


def effective_registration_status(sale: "SaleCapture") -> str:
    if sale.registration_status:
        return sale.registration_status
    if sale.status == SALE_STATUS_EXPORT_FAILED:
        return REG_STATUS_REGISTRATION_FAILED
    if sale.status == SALE_STATUS_REGISTERED:
        return REG_STATUS_REGISTERED
    if sale.status == SALE_STATUS_PENDING_VALIDATION:
        return REG_STATUS_PENDING_VALIDATION
    return REG_STATUS_DRAFT


def is_registration_complete(sale: "SaleCapture") -> bool:
    return effective_registration_status(sale) == REG_STATUS_REGISTERED


def can_retry_registration(sale: "SaleCapture") -> bool:
    rs = effective_registration_status(sale)
    return rs == REG_STATUS_REGISTRATION_FAILED or sale.status == SALE_STATUS_EXPORT_FAILED


class SaleCapture(Base):
    __tablename__ = "sale_captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default=SALE_STATUS_DRAFT)
    registration_status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, default=REG_STATUS_DRAFT
    )
    folio: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)

    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendedor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    seccion: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qna: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cliente: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rfc: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    codigo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    producto: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_venta: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plazo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    costo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    venta: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    venta_refinanciamiento: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_venta: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    precio_comision: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    venta_sin_agregado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    recuperacion: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tipo_cotizacion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    semana: Mapped[str | None] = mapped_column(String(32), nullable=True)

    case_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    validated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    ventas_export_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contratos_export_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ventas_excel_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contratos_excel_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contratos_sheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    export_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_registration_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", foreign_keys=[case_id])
    commission = relationship(
        "Commission",
        back_populates="sale_capture",
        uselist=False,
    )
