"""Pagos ERP histórico (payments_payment / payments_installment)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ErpInstallment(Base):
    __tablename__ = "payments_installment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales_sale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")

    sale = relationship("ErpSale", back_populates="installments")
    payments = relationship("ErpPayment", back_populates="installment")


class ErpPayment(Base):
    __tablename__ = "payments_payment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales_sale.id", ondelete="SET NULL"), nullable=True, index=True
    )
    installment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments_installment.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sale = relationship("ErpSale", back_populates="payments")
    installment = relationship("ErpInstallment", back_populates="payments")
