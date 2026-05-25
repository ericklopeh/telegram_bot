"""Cliente ERP histórico (tabla legacy customers_customer)."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ErpCustomer(Base):
    __tablename__ = "customers_customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rfc: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    curp: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    seccion: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sales = relationship("ErpSale", back_populates="customer")
    contracts = relationship("Contract", back_populates="customer")
