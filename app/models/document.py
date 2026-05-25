from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    replaced_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    upload_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="PENDING_UPLOAD", index=True
    )
    sharepoint_web_url: Mapped[str | None] = mapped_column(String(1500), nullable=True)
    upload_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    upload_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="PENDING_REVIEW", index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    ocr_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="OCR_PENDING", index=True
    )
    ocr_extracted_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def storage_path(self) -> str:
        return self.file_path

    case = relationship("Case", back_populates="documents")
    ocr_results = relationship("OcrResult", back_populates="document", cascade="all, delete-orphan")


CaseDocument = Document
