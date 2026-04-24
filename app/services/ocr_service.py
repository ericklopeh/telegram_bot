"""OCR: implementación futura (Textract / Azure). Mantener interfaz estable."""


class OcrService:
    """Procesa documento y devuelve texto/campos estructurados."""

    def process_document(self, document_id: int) -> None:
        raise NotImplementedError("OCR pendiente de integración")
