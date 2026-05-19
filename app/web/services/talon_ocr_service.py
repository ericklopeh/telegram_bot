"""Compatibilidad web: delega en OCRService."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ocr_result import OcrResult
from app.services.ocr_service import OCRService, extract_talon_fields

__all__ = ["extract_talon_fields", "process_ocr_document"]


def process_ocr_document(
    db: Session,
    document_id: int,
    action_user: str | None = None,
) -> OcrResult | None:
    return OCRService(db).process_document(document_id, action_user)
