"""Comisiones por venta registrada (P21)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_CANCELLED = "cancelled"

PAYMENT_STATUSES = frozenset(
    {PAYMENT_STATUS_PENDING, PAYMENT_STATUS_PAID, PAYMENT_STATUS_CANCELLED}
)


class Commission(Base):
    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_capture_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sale_captures.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    seller_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qna: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    week: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    sale_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    commission_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    payment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PAYMENT_STATUS_PENDING, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sale_capture = relationship("SaleCapture", back_populates="commission")
