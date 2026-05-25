"""Contratos consolidados ERP (P27)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

CONTRACT_ACTIVE = "active"
CONTRACT_CLOSED = "closed"
CONTRACT_REFINANCED = "refinanced"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers_customer.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sales_sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales_sale.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    sale_capture_id: Mapped[int | None] = mapped_column(
        ForeignKey("sale_captures.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    folio: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    original_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    current_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    refinanced_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    total_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=CONTRACT_ACTIVE, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    customer = relationship("ErpCustomer", back_populates="contracts")
    erp_sale = relationship("ErpSale", back_populates="contract")
    installments = relationship(
        "ContractInstallment", back_populates="contract", cascade="all, delete-orphan"
    )
    refinances = relationship(
        "RefinanceOperation", back_populates="contract", cascade="all, delete-orphan"
    )


class ContractInstallment(Base):
    __tablename__ = "contract_installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payments_installment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments_installment.id", ondelete="SET NULL"), nullable=True
    )
    installment_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")

    contract = relationship("Contract", back_populates="installments")


class RefinanceOperation(Base):
    __tablename__ = "refinance_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    refinanced_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    new_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    contract = relationship("Contract", back_populates="refinances")
