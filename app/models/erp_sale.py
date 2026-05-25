"""Ventas ERP histórico (sales_sale / sales_saleitem)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ErpSale(Base):
    __tablename__ = "sales_sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers_customer.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    folio: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contract_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    vendedor: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    seccion: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer = relationship("ErpCustomer", back_populates="sales")
    items = relationship("ErpSaleItem", back_populates="sale", cascade="all, delete-orphan")
    installments = relationship("ErpInstallment", back_populates="sale", cascade="all, delete-orphan")
    payments = relationship("ErpPayment", back_populates="sale")
    contract = relationship("Contract", back_populates="erp_sale", uselist=False)


class ErpSaleItem(Base):
    __tablename__ = "sales_saleitem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales_sale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="1")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")

    sale = relationship("ErpSale", back_populates="items")
