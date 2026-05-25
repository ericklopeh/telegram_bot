"""Modelos importación histórica Excel (P32)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

STATUS_UPLOADED = "uploaded"
STATUS_PREVIEWED = "previewed"
STATUS_CONFIRMED = "confirmed"
STATUS_FAILED = "failed"
STATUS_ROLLED_BACK = "rolled_back"

SOURCE_VENTAS = "ventas"
SOURCE_CONTRATOS = "contratos"


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=STATUS_UPLOADED, index=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    preview_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    audit_trail: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    previewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    row_errors = relationship("ImportRowError", back_populates="batch", cascade="all, delete-orphan")
    sale_references = relationship(
        "ImportedSaleReference", back_populates="batch", cascade="all, delete-orphan"
    )


class ImportRowError(Base):
    __tablename__ = "import_row_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text(), nullable=False)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    batch = relationship("ImportBatch", back_populates="row_errors")


class ImportedSaleReference(Base):
    __tablename__ = "imported_sale_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    erp_sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales_sale.id", ondelete="SET NULL"), nullable=True
    )
    erp_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers_customer.id", ondelete="SET NULL"), nullable=True
    )
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True
    )
    folio: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contract_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_key: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    batch = relationship("ImportBatch", back_populates="sale_references")
