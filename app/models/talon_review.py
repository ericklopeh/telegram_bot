from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TalonReview(Base):
    __tablename__ = "talon_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ocr_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("ocr_results.id", ondelete="SET NULL"), nullable=True, index=True
    )
    percepciones: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deducciones: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    liquido: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    extra: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tiene_programados: Mapped[bool] = mapped_column(Boolean, nullable=False)
    monto_programados: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_70: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    saldo_70: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    liquidez_final: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    resultado: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case = relationship("Case", back_populates="talon_reviews")
    document = relationship("Document")
    ocr_result = relationship("OcrResult")
